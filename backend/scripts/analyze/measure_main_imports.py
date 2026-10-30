"""Fresh-process `app.main` import measurement and importtime report.

This is a diagnostic, not a CI timing gate. Wall-clock thresholds vary by machine. The follow-up
spec only permits a lazy-import change when alternating fresh-process trials prove >=50 ms median
net reduction and a first-call functional test exists.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
TARGETS = ("jieba", "pypinyin", "httpx", "openpyxl", "redis.asyncio")
PROBE = """
import json, sys, time
started = time.perf_counter()
import app.main
print(json.dumps({
    'elapsed_ms': (time.perf_counter() - started) * 1000,
    'loaded': {name: name in sys.modules for name in %r},
}))
""" % (TARGETS,)
IMPORT_ONLY = "import time; s=time.perf_counter(); import %s; print((time.perf_counter()-s)*1000)"
_IMPORT_LINE = re.compile(r"^import time:\s+(\d+)\s+\|\s+(\d+)\s+\|\s+(.+?)\s*$")


def run(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args], cwd=BACKEND, env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
    )


def last_json(stdout: str) -> dict:
    for line in reversed(stdout.splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "elapsed_ms" in value:
            return value
    raise RuntimeError(f"probe did not emit JSON: {stdout[-1000:]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=5)
    ns = parser.parse_args()
    if ns.rounds < 3:
        parser.error("--rounds must be >= 3")
    env = dict(os.environ, PYTHONHASHSEED="0", PYTHONIOENCODING="utf-8")

    trials = []
    loaded = None
    for _ in range(ns.rounds):
        proc = run(["-c", PROBE], env)
        if proc.returncode:
            raise RuntimeError(proc.stderr[-3000:])
        sample = last_json(proc.stdout)
        trials.append(float(sample["elapsed_ms"]))
        loaded = sample["loaded"]

    cold = {}
    for name in TARGETS:
        proc = run(["-c", IMPORT_ONLY % name], env)
        cold[name] = round(float(proc.stdout.strip().splitlines()[-1]), 1) if proc.returncode == 0 else None

    traced = run(["-X", "importtime", "-c", "import app.main"], env)
    if traced.returncode:
        raise RuntimeError(traced.stderr[-3000:])
    rows = []
    for line in traced.stderr.splitlines():
        match = _IMPORT_LINE.match(line)
        if match:
            rows.append({"self_us": int(match[1]), "cumulative_us": int(match[2]), "module": match[3]})

    report = {
        "rounds": ns.rounds,
        "app_main_ms": {
            "samples": [round(v, 1) for v in trials],
            "median": round(statistics.median(trials), 1),
            "min": round(min(trials), 1),
            "max": round(max(trials), 1),
        },
        "target_loaded_after_app_main": loaded,
        "target_cold_import_ms": cold,
        "top_self_imports": sorted(rows, key=lambda row: row["self_us"], reverse=True)[:15],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
