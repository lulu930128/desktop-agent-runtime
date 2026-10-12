"""Read-only stdlib JSON summary; compatible with Windows PowerShell 5.1.

Explicit input paths only. Does not repair evidence or infer acceptance.
Exit 1 for observed FAIL, 2 for missing/BLOCKED evidence, 0 otherwise (UNVERIFIED).
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from w1_geometry_diagnostics import fractional_diagnosis

HERE = Path(__file__).resolve().parent
KICKER = ".today-frame > header > .section-kicker"
DATE = '.schedule-toolbar input[type="date"]'


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def summarize(path):
    path = path.resolve()
    if not path.is_relative_to(HERE / ".runtime"):
        raise ValueError("Only explicit task-local synthetic evidence is allowed")
    if path.is_dir():
        path = path / "ParityResult.json"
    row = {"path": str(path), "gateW1": "UNVERIFIED"}
    if not path.is_file():
        return dict(row, status="UNVERIFIED", error="missing receipt", pairs=[])
    receipt = load(path)
    row.update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
               status=receipt.get("captureStatus", receipt.get("smokeStatus", "UNVERIFIED")),
               gateW1=receipt.get("gateW1", "UNVERIFIED"),
               error=receipt.get("error"), browserVersion=receipt.get("browserVersion"), pairs=[])
    # Also retain the failed first pair when Comparison.json contains zero rows.
    for baseline_path in sorted(path.parent.glob("*-baseline.json")):
        stem = baseline_path.name.removesuffix("-baseline.json")
        qt_path = path.parent / (stem + "-qt.json")
        if not qt_path.is_file():
            row["pairs"].append({"pair": stem, "status": "UNVERIFIED", "error": "missing Qt metadata"})
            continue
        baseline, host = load(baseline_path), load(qt_path)
        qt = host.get("geometry", {})
        pair = {"pair": stem, "status": host.get("status"), "qtVersion": host.get("qt"),
                "edgeViewport": baseline.get("viewport"), "qtViewport": qt.get("viewport"),
                "fractional": fractional_diagnosis(baseline, qt), "today": {}}
        for selector in (KICKER, ".today-frame > header > .today-question", ".local-schedule", DATE):
            values = []
            for measurement in (baseline, qt):
                nodes = measurement.get("deepGeometry", {}).get(selector, [])
                node = nodes[0] if nodes else {}
                values.append({k: node.get(k) for k in ("rect", "css", "textRects")} |
                              {"text": node.get("text") if selector == KICKER else None,
                               "value": node.get("value") if selector == DATE else None})
            pair["today"][selector] = values
        row["pairs"].append(pair)
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipts", type=Path, nargs="+")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output and (not args.output.resolve().is_relative_to(HERE / ".runtime") or args.output.exists()):
        parser.error("Use a new task .runtime summary file; never overwrite evidence")
    rows = []
    for path in args.receipts:
        try:
            rows.append(summarize(path))
        except (OSError, ValueError, TypeError, KeyError) as exc:
            rows.append({"path": str(path), "status": "BLOCKED", "gateW1": "UNVERIFIED", "error": str(exc), "pairs": []})
    result = {"gateW1": "FAIL" if any(r.get("gateW1") == "FAIL" or r["status"] == "FAIL" for r in rows) else "UNVERIFIED",
              "reviewer": "UNVERIFIED", "receipts": rows}
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
    print("W1=" + result["gateW1"] + "; independent human review required")
    for row in rows:
        print(f"{row['path']}\n  status={row['status']} gateW1={row.get('gateW1')} error={row.get('error')}")
        for pair in row["pairs"]:
            print(f"  {pair['pair']}: Edge={pair.get('edgeViewport')} Qt={pair.get('qtViewport')} QtVersion={pair.get('qtVersion')}")
            if "fractional" in pair:
                print(f"    exactGeometry={pair['fractional']['strictGeometryEqual']} exactDeep={pair['fractional']['strictDeepEqual']} numericDeltas={len(pair['fractional']['rows'])}")
            kicker = pair.get("today", {}).get(KICKER, [])
            if kicker and kicker[0].get("text") is not None:
                # ASCII-safe on every PowerShell console; full UTF-8 in JSON artifact.
                print("    kicker=" + json.dumps(kicker, ensure_ascii=True))
    if result["gateW1"] == "FAIL":
        return 1
    return 2 if any(r["status"] not in ("PASS", "FAIL") for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
