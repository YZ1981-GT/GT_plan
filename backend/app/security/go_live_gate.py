"""H7 Go_Live_Gate · 上线终局门（skeleton, Task 1）

Feature: visibility-isolation-go-live-hardening
Requirements: 7.1–7.10 (Task 1 wires 7.1/7.2/7.3/7.4; the full 6-item LIVE/ACCEPTED
verdict is exercised end-to-end by Task 8).

Confirms whether all **6 Go_Live_Items** (the 6 上线 GAP = R1..R6, mapped to spec Tasks
2..7) are truly LIVE/ACCEPTED — not merely "已构建". It **reuses** the parent
Completion_Guard machinery verbatim:

  * ``latest_runs_per_task`` — latest-run-per-task semantics;
  * ``_verify_run_artifacts`` — recompute SHA-256 + size and reject relative paths that
    contain ``..`` or are absolute;
  * ``_validate_schema`` — JSON-Schema conformance;
  * ``_SMOKE_MARKERS`` — refuse to let a Smoke_Profile run masquerade as acceptance.

At this stage (only Task 1's baseline evidence exists) the gate MUST conclude **NOT
live** and block, because Go_Live_Items 1..6 have no accepted (passing) run yet. This is
honest fail-closed behaviour, not a placeholder that always returns green.

This module only **reads and verifies** evidence; it never mutates recorded runs.

CLI:
  python -m app.security.go_live_gate            # evaluate + print verdict
  python -m app.security.go_live_gate --report   # also (re)write deterministic report
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.security.completion_guard import (
    _SMOKE_MARKERS,
    _validate_schema,
    _verify_run_artifacts,
    latest_runs_per_task,
)
from app.security.go_live_evidence import (
    MANIFEST_PATH,
    SCHEMA_PATH,
    SPEC_DIR,
    SPEC_NAME,
    load_manifest,
)

# ---------------------------------------------------------------------------
# The 6 Go_Live_Items (the 6 上线 GAP). Each maps to a spec Task (2..7) and the
# top-level Requirement it discharges. An item is LIVE/ACCEPTED only when its Task
# has a latest run whose status is ``passed`` (and that run is not smoke-as-acceptance).
# ---------------------------------------------------------------------------
GO_LIVE_ITEMS: tuple[dict[str, str], ...] = (
    {"id": "GLI-1", "task": "2", "requirement": "1",
     "title": "启用编辑器令牌强制 (OnlyOffice/WOPI ONLYOFFICE_JWT_ENFORCE)"},
    {"id": "GLI-2", "task": "3", "requirement": "2",
     "title": "挂载 epoch 失效 Redis dispatcher 到 app.main lifespan"},
    {"id": "GLI-3", "task": "4", "requirement": "3",
     "title": "审计 72 条 native_authz 入口并接门/豁免"},
    {"id": "GLI-4", "task": "5", "requirement": "4",
     "title": "真实 6000 并发容量验收与冻结生产 Rate_Limit_Profile"},
    {"id": "GLI-5", "task": "6", "requirement": "5",
     "title": "Playwright 8 角色 fresh-context 验收"},
    {"id": "GLI-6", "task": "7", "requirement": "6",
     "title": "PR 提交与依赖 spec 交互验证"},
)

_GATE_REPORT_REL = "evidence/artifacts/task1/go_live_gate_report.json"


@dataclass
class GoLiveResult:
    live: bool                      # True == all 6 items LIVE/ACCEPTED
    blocked: bool                   # True == gate blocks the go-live claim
    problems: list[str] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)


def _run_is_smoke_acceptance(run: dict[str, Any]) -> bool:
    cmd = run.get("command") or ""
    return any(pat.search(cmd) for pat in _SMOKE_MARKERS)


def evaluate(
    *,
    manifest_path: Path = MANIFEST_PATH,
    schema_path: Path = SCHEMA_PATH,
    spec_dir: Path = SPEC_DIR,
) -> GoLiveResult:
    """Evaluate the Go_Live_Gate against this spec's evidence manifest.

    fail-closed: any missing manifest/schema/artifact, any non-passing latest
    Go_Live_Item run, any smoke-as-acceptance, or any item still 已构建-not-LIVE
    blocks the go-live claim (7.5–7.9).
    """
    problems: list[str] = []

    # (7.5) manifest / schema must exist.
    if not Path(manifest_path).exists():
        return GoLiveResult(
            live=False, blocked=True,
            problems=[f"[7.5] Evidence_Manifest 缺失: {manifest_path}"],
            report={"spec": SPEC_NAME, "gate": "go_live_gate", "verdict": "blocked"},
        )

    manifest = load_manifest(manifest_path)
    _validate_schema(manifest, schema_path, problems)  # (7.5) schema conformance

    latest_by_task = latest_runs_per_task(manifest)

    # (7.3/7.4) latest-run artifacts: recompute SHA-256/size, reject unsafe paths.
    artifacts_checked = 0
    for _tk, run in latest_by_task.items():
        artifacts_checked += _verify_run_artifacts(run, spec_dir, problems)

    # (7.6/7.7/7.8/7.9) classify each of the 6 Go_Live_Items.
    items_report: list[dict[str, Any]] = []
    live_count = 0
    for item in GO_LIVE_ITEMS:
        run = latest_by_task.get(item["task"])
        if run is None:
            state = "built-not-live"
            problems.append(
                f"[7.8] {item['id']} (Task {item['task']}, R{item['requirement']}) "
                f"仅已构建，无 LIVE/ACCEPTED run: {item['title']}"
            )
        elif run.get("status") != "passed":
            state = "not-accepted"
            problems.append(
                f"[7.6] {item['id']} (Task {item['task']}) 最新 run 非 passed: "
                f"{run.get('status')}"
            )
        elif _run_is_smoke_acceptance(run):
            state = "smoke-not-accepted"
            problems.append(
                f"[7.9] {item['id']} (Task {item['task']}) 以 Smoke_Profile 冒充验收: "
                f"command={run.get('command')!r}"
            )
        else:
            state = "live-accepted"
            live_count += 1
        items_report.append({
            "id": item["id"],
            "task": item["task"],
            "requirement": item["requirement"],
            "title": item["title"],
            "latest_seq": (run or {}).get("seq"),
            "latest_status": (run or {}).get("status"),
            "state": state,
        })

    live = live_count == len(GO_LIVE_ITEMS) and not problems
    report = _build_report(
        manifest=manifest,
        items_report=items_report,
        live_count=live_count,
        artifacts_checked=artifacts_checked,
        problems=problems,
        live=live,
    )
    return GoLiveResult(live=live, blocked=not live, problems=problems, report=report)


def _build_report(
    *,
    manifest: dict[str, Any],
    items_report: list[dict[str, Any]],
    live_count: int,
    artifacts_checked: int,
    problems: list[str],
    live: bool,
) -> dict[str, Any]:
    """Deterministic report (hash-pinnable: no timestamps, sorted keys on write)."""
    return {
        "spec": SPEC_NAME,
        "gate": "go_live_gate",
        "semantics": "latest-run-per-task; LIVE/ACCEPTED != 已构建",
        "verdict": "live" if live else "blocked",
        "go_live_items_total": len(GO_LIVE_ITEMS),
        "go_live_items_live": live_count,
        "go_live_items": sorted(items_report, key=lambda r: r["id"]),
        "latest_artifacts_verified": {
            "checked": artifacts_checked,
            "clean": not any(
                ("SHA-256" in p or "size" in p or "artifact 缺失" in p or "路径" in p)
                for p in problems
            ),
        },
        "total_runs": len(manifest.get("runs", [])),
        "problem_count": len(problems),
        "note": (
            "Go_Live_Gate 骨架：仅当 6 个 Go_Live_Item 均有最新 passed run（且非 smoke 冒充）"
            "才判定 live。基线阶段 Task 2..7 尚无 run，故 6 项均 built-not-live，门 fail-closed 阻断。"
        ),
    }


def write_report(report: dict[str, Any], spec_dir: Path = SPEC_DIR) -> Path:
    """Write the deterministic gate report artifact (sorted keys, no timestamps)."""
    import json

    path = spec_dir / _GATE_REPORT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _main() -> int:
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    res = evaluate()
    print("== Go_Live_Gate: 6 Go_Live_Items ==")
    for row in res.report.get("go_live_items", []):
        print(f"  {row['id']} (Task {row['task']}, R{row['requirement']}): "
              f"state={row['state']} latest_status={row['latest_status']}")
    print(f"verdict={res.report.get('verdict')} live={res.live} blocked={res.blocked}")
    if "--report" in sys.argv:
        p = write_report(res.report)
        print(f"gate report written: {p}")
    if res.problems:
        print(f"\n[go-live-gate] BLOCKED — {len(res.problems)} problem(s):")
        for p in res.problems:
            print(f"  - {p}")
    else:
        print("\n[go-live-gate] LIVE — all 6 Go_Live_Items accepted")
    # Exit 0 always for skeleton CLI: blocking is the expected baseline verdict.
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
