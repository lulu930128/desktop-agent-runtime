"""Deterministic read-only geometry comparison; a diagnosis is never a W1 PASS."""
import argparse
import json
from pathlib import Path
from diagnose_parity import value_diffs

REQUIRED = (".today-frame > header", ".today-frame > header > .section-kicker",
            ".today-frame > header > .today-question", ".today-frame > header > .today-summary",
            ".today-primary > section > .block-heading", ".priority-list", ".local-schedule",
            '.schedule-toolbar input[type="date"]')


def compare(left, right):
    right = right.get("geometry", right) if "status" in right else right
    keys = ("viewport", "language", "timezone", "fontStatus", "tokens", "deepGeometry", "deepCoverage", "fontChecks", "intl")
    missing = [key for key in keys if key not in left or key not in right]
    diffs = [row for key in keys for row in value_diffs(left.get(key), right.get(key), key)]
    empty = [f"{side}:{selector}" for side, value in (("baseline", left), ("qt", right))
             for selector in REQUIRED if value.get("deepCoverage", {}).get("required", {}).get(selector, 0) < 1
             or not value.get("deepGeometry", {}).get(selector)]
    return {"gateW1": "FAIL" if empty else "UNVERIFIED" if missing else "FAIL" if diffs else "UNVERIFIED",
            "emptyRequiredSelectors": empty,
            "missing": missing, "differences": diffs,
            "reason": "Matching measurements alone do not establish visual/security/native-interaction acceptance; native date internals need Windows inspection."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("qt", type=Path)
    args = parser.parse_args()
    result = compare(json.loads(args.baseline.read_text(encoding="utf-8")), json.loads(args.qt.read_text(encoding="utf-8")))
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    raise SystemExit(1 if result["differences"] or result["missing"] or result["emptyRequiredSelectors"] else 0)
