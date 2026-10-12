"""Read-only PNG/JSON analysis of saved synthetic W1 evidence; Python stdlib only.

No Qt, browser, provider, or image editing. Output directory must be new.
PNG decoder deliberately accepts only noninterlaced 8-bit RGB/RGBA captures.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import zlib

HERE = Path(__file__).resolve().parent


def read_png(path):
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"Not PNG: {path}")
    offset, compressed, header = 8, bytearray(), None
    while offset < len(data):
        length = struct.unpack_from(">I", data, offset)[0]
        kind = data[offset + 4:offset + 8]
        chunk = data[offset + 8:offset + 8 + length]
        crc = struct.unpack_from(">I", data, offset + 8 + length)[0]
        if zlib.crc32(kind + chunk) != crc:
            raise ValueError("PNG CRC mismatch")
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", chunk)
        elif kind == b"IDAT":
            compressed.extend(chunk)
        offset += length + 12
        if kind == b"IEND":
            break
    if header is None:
        raise ValueError("No PNG header")
    width, height, depth, color, compression, filtering, interlace = header
    if depth != 8 or color not in (2, 6) or any((compression, filtering, interlace)):
        raise ValueError(f"Unsupported PNG header: {header}")
    if not (0 < width <= 6000 and 0 < height <= 6000):
        raise ValueError("Capture dimensions outside diagnostic bounds")
    channels = 3 if color == 2 else 4
    stride = width * channels
    raw = zlib.decompress(compressed)
    if len(raw) != (stride + 1) * height:
        raise ValueError("PNG decompressed size mismatch")
    previous, pixels = bytearray(stride), bytearray()
    for y in range(height):
        start = y * (stride + 1)
        method = raw[start]
        row = bytearray(raw[start + 1:start + 1 + stride])
        if method not in range(5):
            raise ValueError("Unsupported PNG filter")
        for i in range(stride):
            left = row[i - channels] if i >= channels else 0
            above = previous[i]
            corner = previous[i - channels] if i >= channels else 0
            if method == 1:
                predictor = left
            elif method == 2:
                predictor = above
            elif method == 3:
                predictor = (left + above) // 2
            elif method == 4:
                p = left + above - corner
                distances = (abs(p - left), abs(p - above), abs(p - corner))
                predictor = (left, above, corner)[distances.index(min(distances))]
            else:
                predictor = 0
            row[i] = (row[i] + predictor) & 255
        if channels == 4:
            if any(row[i] != 255 for i in range(3, stride, 4)):
                raise ValueError("Unexpected translucent capture")
            pixels.extend(value for i, value in enumerate(row) if i % 4 != 3)
        else:
            pixels.extend(row)
        previous = row
    return width, height, pixels


def metrics(a, b, rect, qt_dy=0):
    width, height, left = a
    if b[:2] != a[:2]:
        raise ValueError("Image sizes differ")
    right = b[2]
    x0, y0, x1, y1 = rect
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height
            and 0 <= y0 + qt_dy < y1 + qt_dy <= height):
        raise ValueError("Region outside image")
    sums, squares, counts = [0] * 3, [0] * 3, [0] * 3
    row_counts = []
    for y in range(y0, y1):
        row_changed = 0
        for x in range(x0, x1):
            i, j = (y * width + x) * 3, ((y + qt_dy) * width + x) * 3
            delta = [abs(left[i + c] - right[j + c]) for c in range(3)]
            magnitude = max(delta)
            row_changed += magnitude > 0
            for n, threshold in enumerate((0, 8, 32)):
                counts[n] += magnitude > threshold
            for c in range(3):
                sums[c] += delta[c]
                squares[c] += delta[c] ** 2
        row_counts.append([y, row_changed])
    count = (x1 - x0) * (y1 - y0)
    return {"rectXYXY": rect, "qtSampleYOffset": qt_dy, "pixels": count,
            "changedPixels": counts[0], "changedPixelFraction": counts[0] / count,
            "maxChannelDeltaGreaterThan8": counts[1], "maxChannelDeltaGreaterThan32": counts[2],
            "meanAbsoluteErrorRGB": [value / count for value in sums],
            "rmsRGB": [math.sqrt(value / count) for value in squares],
            "topChangedRows": sorted(row_counts, key=lambda row: (-row[1], row[0]))[:12]}


def value_diffs(left, right, path=""):
    if isinstance(left, dict) and isinstance(right, dict):
        return [item for key in sorted(left.keys() | right.keys())
                for item in value_diffs(left.get(key), right.get(key), f"{path}/{key}")]
    if left == right:
        return []
    result = {"path": path, "baseline": left, "qt": right}
    if type(left) in (int, float) and type(right) in (int, float):
        result["qtMinusBaseline"] = right - left
    return [result]


def manifest(source):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(source.iterdir()) if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, output = args.evidence.resolve(), args.output.resolve()
    if not source.is_relative_to(HERE / ".runtime") or not output.is_relative_to(HERE / ".runtime"):
        parser.error("Only task-local runtime evidence/output allowed")
    output.mkdir(parents=True, exist_ok=False)
    before = manifest(source)
    receipt = json.loads((source / "ParityResult.json").read_text(encoding="utf-8"))
    result = {"evidence": str(source), "gateW1": receipt["gateW1"], "runtimeExecuted": False,
              "browserVersion": receipt["browserVersion"],
              "method": "stdlib PNG decode; native view_image reviewed separately; thresholds are descriptive, not acceptance tolerances",
              "evidenceHashesBefore": before, "views": {}}
    comparison = json.loads((source / "Comparison.json").read_text(encoding="utf-8"))
    for reference in comparison:
        if reference["viewport"] != [1280, 720] or reference["scale"] != 1:
            raise ValueError("This bounded diagnosis expects the initial 1280x720 DPR1 evidence")
        view = reference["view"]
        stem = f"{view}-1280x720"
        baseline = json.loads((source / (stem + "-baseline.json")).read_text(encoding="utf-8"))
        qt = json.loads((source / (stem + "-qt.json")).read_text(encoding="utf-8"))
        a, b, saved_diff = [read_png(source / (stem + suffix + ".png"))
                            for suffix in ("-baseline", "-qt", "-diff")]
        if a[:2] != (1280, 720) or a[:2] != b[:2] or a[:2] != saved_diff[:2]:
            raise ValueError("Unexpected image dimensions")
        if any(abs(x - y) != d for x, y, d in zip(a[2], b[2], saved_diff[2])):
            raise ValueError("Saved diff is not exact absolute RGB difference")
        full = metrics(a, b, [0, 0, 1280, 720])
        for key in ("changedPixelFraction", "meanAbsoluteErrorRGB", "rmsRGB"):
            if full[key] != reference[key]:
                raise ValueError(f"Independent PNG calculation disagrees with Comparison.json: {view}/{key}")
        regions = {"shell": [0, 0, 1280, 103], "rail": [0, 103, 78, 720]}
        if view == "today":
            regions.update(header=[78, 103, 1280, 260], priority=[78, 260, 1280, 480], schedule=[78, 480, 1280, 720])
        elif view == "chat":
            regions.update(header=[78, 103, 1280, 210], messages=[78, 210, 1280, 560], composer=[78, 560, 1280, 720])
        else:
            regions.update(content=[78, 103, 1280, 720])
        measured = {name: metrics(a, b, rect) for name, rect in regions.items()}
        for region in measured.values():
            region["shareOfAllChangedPixels"] = region["changedPixels"] / full["changedPixels"] if full["changedPixels"] else 0
        entry = {"allValueDiffs": value_diffs(baseline, qt["geometry"]),
                 "selectorValueDiffs": value_diffs(baseline["geometry"], qt["geometry"]["geometry"]),
                 "tokenDiffs": value_diffs(baseline["tokens"], qt["geometry"]["tokens"]),
                 "contexts": {"baseline": {k: baseline[k] for k in ("userAgent", "language", "timezone", "fontStatus", "viewport", "screen")},
                              "qt": {k: qt["geometry"][k] for k in ("userAgent", "language", "timezone", "fontStatus", "viewport", "screen")}},
                 "qtHost": {k: qt[k] for k in ("status", "qt", "offTheRecord", "platform", "bridgeRequests", "logicalDpi")},
                 "fullImage": full, "regions": measured, "savedDiffVerified": True}
        if view == "today":
            entry["translationExperiments"] = {
                name: [metrics(a, b, rect, offset) for offset in (0, 1, 2, 3)]
                for name, rect in {"heading": [122, 153, 1227, 205], "summary": [122, 210, 1227, 247],
                                   "priority": [122, 260, 1227, 470], "schedule": [122, 490, 1227, 716],
                                   "dateKicker": [122, 130, 330, 152]}.items()}
        result["views"][view] = entry
    after = manifest(source)
    result["evidenceHashesAfter"] = after
    result["evidenceUnchanged"] = before == after
    if before != after:
        raise ValueError("Evidence changed during read-only analysis")
    (output / "Diagnosis.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"diagnostic": str(output / "Diagnosis.json"), "evidenceUnchanged": True,
                      "savedDiffAndMetricsVerified": list(result["views"]), "gateW1": result["gateW1"]}))


if __name__ == "__main__":
    main()
