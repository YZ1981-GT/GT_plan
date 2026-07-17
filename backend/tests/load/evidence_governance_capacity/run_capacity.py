"""Capacity/chaos orchestration entrypoint.

Spec: attachment-ocr-ai-evidence-governance-hardening — Task 8.2

Two modes:

  ``python -m tests.load.evidence_governance_capacity.run_capacity plan``
      Validate the scenario + connection budget, (re)write ``scenario.json``,
      and print the machine-readable chaos toggle timeline. Runs anywhere; no
      capacity environment required. This is the deliverable that proves the
      tooling is coherent without faking a 6000 VU result.

  ``python -m tests.load.evidence_governance_capacity.run_capacity run \
        --host http://<capacity-host>:9980``
      Preflight the budget, then exec Locust headless with the bundled
      ``StepLoadShape`` (30 min steady + 10 min burst). Requires a dedicated
      capacity environment and Locust installed. On stop the harness writes the
      capacity report JSON.

Windows note: uses ``python`` and ``;``-free single commands.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# Support both "python -m ..." and direct execution.
try:
    from .chaos import build_default_fault_plan
    from .connection_budget import check_budget
    from .scenario import LOAD_PROFILE, SCENARIO, write_scenario_json
except ImportError:  # pragma: no cover - direct-run fallback
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from tests.load.evidence_governance_capacity.chaos import build_default_fault_plan
    from tests.load.evidence_governance_capacity.connection_budget import check_budget
    from tests.load.evidence_governance_capacity.scenario import (
        LOAD_PROFILE,
        SCENARIO,
        write_scenario_json,
    )


_HARNESS = Path(__file__).with_name("locustfile_evidence_capacity.py")


def _burst_offsets() -> tuple[int, int]:
    """(burst_start_offset_s, burst_duration_s) derived from the load profile."""
    offset = 0
    burst_start = 0
    burst_dur = SCENARIO.burst_seconds
    for phase in LOAD_PROFILE:
        ramp = int(phase.users / phase.spawn_rate)
        if phase.kind == "burst":
            burst_start = offset + ramp
            burst_dur = phase.duration_s
            break
        offset += ramp + phase.duration_s
    return burst_start, burst_dur


def cmd_plan(_args: argparse.Namespace) -> int:
    SCENARIO.validate()
    out = write_scenario_json()
    budget = check_budget()
    burst_start, burst_dur = _burst_offsets()
    plan = build_default_fault_plan(
        burst_start_offset_s=burst_start, burst_duration_s=burst_dur
    )

    summary = {
        "scenario_json": str(out),
        "target_virtual_users": SCENARIO.target_virtual_users,
        "steady_seconds": SCENARIO.steady_state_seconds,
        "burst_seconds": SCENARIO.burst_seconds,
        "traffic_model": {c.name: c.weight_pct for c in SCENARIO.traffic_model},
        "connection_budget": budget.to_dict(),
        "chaos_timeline": plan.to_env_timeline(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if not budget.ok:
        print("[FAIL] connection budget invariant violated; run is blocked", file=sys.stderr)
        return 1
    print("[OK] scenario + budget valid; chaos timeline emitted")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    budget = check_budget()
    if not budget.ok:
        print("[FAIL] connection budget invariant violated; refusing to run", file=sys.stderr)
        for r in budget.reasons:
            print(f"  - {r}", file=sys.stderr)
        return 1

    if not args.host:
        print("[FAIL] --host is required for run mode", file=sys.stderr)
        return 2

    cmd = [
        sys.executable, "-m", "locust",
        "-f", str(_HARNESS),
        "--host", args.host,
        "--headless",
        "--autostart",
    ]
    print(f"[RUN] {' '.join(cmd)}")
    print("      chaos toggles must be scheduled per the 'plan' timeline "
          "(EVIDENCE_CHAOS_* env in the target deployment).")
    return subprocess.call(cmd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evidence Governance capacity/chaos runner")
    sub = parser.add_subparsers(dest="mode", required=True)

    p_plan = sub.add_parser("plan", help="validate + emit scenario.json + chaos timeline")
    p_plan.set_defaults(func=cmd_plan)

    p_run = sub.add_parser("run", help="preflight budget then exec locust headless")
    p_run.add_argument("--host", required=False, help="capacity target base URL")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
