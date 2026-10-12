"""Pure evidence diagnostics. No tolerances here can change strict parity."""
import math


def measurement_stable(previous, current, view):
    keys = ("viewport", "geometry", "deepGeometry", "fontStatus", "history")
    return (previous is not None and current.get("fontStatus") == "loaded"
            and all(previous.get(k) == current.get(k) for k in keys)
            and (view != "history" or (current.get("history", {}).get("opened") is True
                                      and current.get("history", {}).get("animationsSettled") is True)))


def viewport_diagnosis(requested, actual, sample):
    """Capacity is measured, not inferred from a nine-pixel discrepancy."""
    width, height = requested
    frame = sample.get("frameGeometry", {})
    widget = sample.get("widgetSize", {})
    available = sample.get("screen", {}).get("availableGeometry", {})
    extra_w = frame.get("width", 0) - widget.get("width", 0)
    extra_h = frame.get("height", 0) - widget.get("height", 0)
    capacity = None
    if frame and widget and available:
        capacity = width + extra_w <= available["width"] and height + extra_h <= available["height"]
    exact = actual.get("width") == width and actual.get("height") == height
    return {"requested": {"width": width, "height": height}, "actual": actual,
            "exact": exact, "requestedDecoratedWindowFitsAvailableArea": capacity,
            "decorationExtent": {"width": extra_w, "height": extra_h},
            "status": "EXACT" if exact else "FAIL",
            "reason": "exact DOM viewport" if exact else
                      "requested decorated client exceeds measured available area; clamp cause still requires timeline review"
                      if capacity is False else "viewport mismatch; inspect resize timeline, no automatic acceptance"}


def fractional_diagnosis(left, right):
    """Report exact deltas and grid residuals, not a quantized comparison."""
    dpr = right.get("viewport", {}).get("devicePixelRatio")
    rows = []
    non_numeric = []
    def walk(a, b, path):
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) & set(b)):
                walk(a[key], b[key], path + "." + key)
        elif isinstance(a, list) and isinstance(b, list):
            for i, (x, y) in enumerate(zip(a, b)):
                walk(x, y, f"{path}[{i}]")
        elif (type(a) in (int, float) and type(b) in (int, float) and a != b
              and math.isfinite(a) and math.isfinite(b)):
            row = {"path": path, "edge": a, "qt": b, "deltaCssPx": b - a}
            if type(dpr) in (int, float) and math.isfinite(dpr) and dpr > 0:
                # Blink layout unit (1/64), CSS grid vs scaled device grid.
                row.update(deltaDevicePx=(b-a)*dpr,
                           edgeCss64Residual=abs(a*64-round(a*64)),
                           qtCss64Residual=abs(b*64-round(b*64)),
                           qtDevice64Residual=abs(b*dpr*64-round(b*dpr*64)),
                           qtNearestDevicePixelResidual=abs(b*dpr-round(b*dpr)))
            rows.append(row)
        elif a != b:
            non_numeric.append({"path": path, "edge": a, "qt": b})
    for key in ("geometry", "deepGeometry"):
        walk(left.get(key, {}), right.get(key, {}), key)
    return {"strictGeometryEqual": left.get("geometry") == right.get("geometry"),
            "strictDeepEqual": left.get("deepGeometry") == right.get("deepGeometry"),
            "viewportEqual": left.get("viewport") == right.get("viewport"), "rows": rows,
            "nonNumericDifferences": non_numeric,
            "classification": "UNVERIFIED: grid alignment is a diagnostic signature, not proof of cause",
            "gatePolicy": "Exact raw comparison only; never round, normalize, or accept subpixel differences"}
