"""Merge Wave 9 UAT Playwright JSON reporter outputs (two configs) into a single
aggregated results.json consumed by the evidence-governance release gate.

Derives the top-level `stats` by SUMMING the real per-run stats (expected /
unexpected / skipped / flaky). Does NOT hand-write any counts — everything comes
from the actual Playwright JSON output files.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1]
GROUP_FILES = [
    FRONTEND / "uat-json" / "groupA.json",
    FRONTEND / "uat-json" / "groupB.json",
]
OUT = FRONTEND / "playwright-uat-report" / "results.json"


def load(p: Path) -> dict:
    # Playwright writes UTF-8; tolerate BOM.
    text = p.read_text(encoding="utf-8-sig")
    return json.loads(text)


def main() -> int:
    merged_suites: list = []
    merged_errors: list = []
    total = {"expected": 0, "unexpected": 0, "skipped": 0, "flaky": 0}
    start_times: list[str] = []
    duration_sum = 0.0
    sources = []

    for p in GROUP_FILES:
        if not p.exists():
            print(f"[merge] MISSING group file: {p}", file=sys.stderr)
            return 2
        doc = load(p)
        st = doc.get("stats", {})
        for k in total:
            total[k] += int(st.get(k, 0) or 0)
        duration_sum += float(st.get("duration", 0) or 0)
        if st.get("startTime"):
            start_times.append(st["startTime"])
        merged_suites.extend(doc.get("suites", []))
        merged_errors.extend(doc.get("errors", []))
        sources.append({"file": str(p.relative_to(FRONTEND)), "stats": st})
        print(f"[merge] {p.name}: {st}")

    merged = {
        "config": {
            "note": (
                "Aggregated Wave 9 UAT evidence merged from two Playwright configs "
                "(default e2e + playwright-uat.config.ts e2e-uat). Stats are the SUM "
                "of the real per-run stats; not hand-written."
            ),
            "version": "1.60.0",
            "sources": sources,
        },
        "suites": merged_suites,
        "errors": merged_errors,
        "stats": {
            "startTime": min(start_times) if start_times else None,
            "duration": round(duration_sum, 3),
            "expected": total["expected"],
            "unexpected": total["unexpected"],
            "skipped": total["skipped"],
            "flaky": total["flaky"],
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[merge] wrote {OUT}")
    print(f"[merge] combined stats: {merged['stats']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
