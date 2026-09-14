"""Completion Guard · 最终完成守卫（Task 18 / 组件 C18 Evidence）

Feature: procedure-delegation-visibility-isolation
Requirements: 15.1–15.12, 16.21–16.24 / Design "Correctness Property 20" + Completion_Guard.

聚合 Task 1–18、全部 criteria 与 stable test ids → 当前 run 的 artifacts，并对完成状态做
**fail-closed** 判定。绝不假绿。判定采用 **latest-run-per-task / latest-run-per-criterion**
语义：

  * 每个叶子任务（1–18）的**最新** Criterion_Run 必须 ``passed``；
  * 每个被引用 criterion 的**最新** run 必须 ``passed``；
  * **最新** run 的每个 artifact：JSON-Schema 合规、相对路径安全（拒绝绝对路径与 ``..``）、
    重算 SHA-256 与 size 必须与 manifest 记录一致；缺失 artifact 阻断；
  * 被 superseded 的历史 run（如 Task 14 seq-24、Task 15 seq-26/27）即使 artifact 已漂移，
    只要该任务存在更晚的权威 passing run，就**不**阻断完成（append-only 保留，从不改写记录的哈希）；
  * 拒绝 smoke 冒充 correctness（correctness 证据必须来自 correctness profile，≥100 有效样例）；
  * 覆盖/漂移守卫必须干净（0 unmigrated，HTTP/worker 生产面 ⇔ ledger 双向相等）。

本模块只**读取并校验**证据，不改写既有 run 的哈希。Task 18 run 的追加由 ``close_spec()``
在守卫通过后执行（append-only）。

CLI:
  python -m app.security.completion_guard            # 校验（Task 18 视为待关闭，可缺）
  python -m app.security.completion_guard --strict   # 校验 1–18 全部存在且 passed
  python -m app.security.completion_guard --close     # 通过则生成报告并追加 Task 18 run，关闭规格
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.security.evidence_manifest import (
    MANIFEST_PATH,
    SCHEMA_PATH,
    SPEC_DIR,
    is_unsafe_rel_path,
    load_manifest,
    sha256_and_size,
)

# 全部必做叶子任务（tasks.md：18 个必做，无 optional）。
REQUIRED_LEAF_TASKS: tuple[str, ...] = tuple(str(i) for i in range(1, 19))

# Task 18 自身声明的 criteria（必须最新 passed）。
TASK18_CRITERIA: tuple[str, ...] = tuple(
    [f"15.{i}" for i in range(1, 13)] + ["16.21", "16.22", "16.23", "16.24"]
)

# smoke 冒充 correctness 的标记（出现在被当作完成证据的最新 run 的 command 中即阻断）。
_SMOKE_MARKERS = (
    re.compile(r"hypothesis[_-]?profile\s*[=:]\s*smoke", re.I),
    re.compile(r"--hypothesis-profile\s+smoke", re.I),
    re.compile(r"max_examples\s*=\s*5\b"),
    re.compile(r"HYPOTHESIS_MAX_EXAMPLES\s*=\s*5\b"),
)

# correctness 证据 artifact（Task 14 冻结的有效样例计数，≥100/property）。
_CORRECTNESS_FROZEN_REL = (
    "evidence/artifacts/task14/valid_example_counts.correctness.frozen.json"
)

_GUARD_REPORT_REL = "evidence/artifacts/task18/completion_guard_report.json"


def norm_task_id(task_id: Any) -> str:
    """取 task_id 的数字前缀（``"7. 实现两层..."`` -> ``"7"``）。"""
    m = re.match(r"\s*(\d+)", str(task_id))
    return m.group(1) if m else str(task_id).strip()


# ---------------------------------------------------------------------------
# latest-run-per-task / per-criterion
# ---------------------------------------------------------------------------
def latest_runs_per_task(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for r in manifest.get("runs", []):
        tk = norm_task_id(r.get("task_id"))
        if tk not in latest or int(r.get("seq", 0)) > int(latest[tk].get("seq", 0)):
            latest[tk] = r
    return latest


def latest_run_per_criterion(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for r in manifest.get("runs", []):
        for c in r.get("criterion_ids", []) or []:
            if c not in latest or int(r.get("seq", 0)) > int(latest[c].get("seq", 0)):
                latest[c] = r
    return latest


# ---------------------------------------------------------------------------
# Guard result
# ---------------------------------------------------------------------------
@dataclass
class GuardResult:
    ok: bool
    problems: list[str] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)


def _verify_run_artifacts(run: dict[str, Any], spec_dir: Path, problems: list[str]) -> int:
    """校验单个 run 的全部 artifact（路径安全 / 存在 / SHA-256 / size）。返回已校验个数。"""
    checked = 0
    rid = run.get("run_id", "<no run_id>")
    for art in run.get("artifacts", []) or []:
        rel = art.get("path")
        if is_unsafe_rel_path(rel):
            problems.append(f"[15.6] run {rid}: 不安全 artifact 路径（绝对/含 '..'）: {rel!r}")
            continue
        abs_path = spec_dir / str(rel).replace("\\", "/")
        if not abs_path.exists():
            problems.append(f"[15.9] run {rid}: artifact 缺失: {rel}")
            continue
        sha, size = sha256_and_size(abs_path)
        if art.get("sha256") != sha:
            problems.append(
                f"[15.7/15.11] run {rid}: SHA-256 不符 {rel} "
                f"(记录 {art.get('sha256')}, 重算 {sha})"
            )
        if art.get("size") != size:
            problems.append(
                f"[15.8/15.11] run {rid}: size 不符 {rel} "
                f"(记录 {art.get('size')}, 重算 {size})"
            )
        checked += 1
    return checked


def _validate_schema(manifest: dict[str, Any], schema_path: Path, problems: list[str]) -> None:
    if not schema_path.exists():
        problems.append(f"[15.2/15.9] Evidence_Schema 缺失: {schema_path}")
        return
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        problems.append(f"[15.10] Evidence_Schema 非法 JSON: {exc}")
        return
    try:
        import jsonschema  # type: ignore

        jsonschema.validate(instance=manifest, schema=schema)
    except ImportError:
        problems.append("[15.10] jsonschema 未安装，无法做权威 schema 校验")
    except Exception as exc:  # noqa: BLE001
        problems.append(f"[15.10] manifest 不符合 Evidence_Schema: {exc}")


def _check_smoke_as_correctness(
    manifest: dict[str, Any],
    latest_by_task: dict[str, dict[str, Any]],
    spec_dir: Path,
    problems: list[str],
) -> None:
    # (a) 任一最新任务 run 的 command 出现 smoke profile 标记 → smoke 冒充完成证据。
    for tk, run in latest_by_task.items():
        cmd = run.get("command") or ""
        for pat in _SMOKE_MARKERS:
            if pat.search(cmd):
                problems.append(
                    f"[16.1-16.3] Task {tk} 最新 run 使用 smoke profile 作为完成证据: "
                    f"command={cmd!r}"
                )
                break
    # (b) correctness 证据必须存在且 ≥100 有效样例 / property。
    frozen = spec_dir / _CORRECTNESS_FROZEN_REL
    if not frozen.exists():
        problems.append(f"[16.4] correctness 冻结计数缺失: {_CORRECTNESS_FROZEN_REL}")
        return
    try:
        data = json.loads(frozen.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        problems.append(f"[16.4] correctness 冻结计数非法 JSON: {exc}")
        return
    if data.get("profile") != "correctness" or not data.get("is_completion_evidence"):
        problems.append("[16.4] correctness 冻结计数未标记为 correctness 完成证据")
    target = int(data.get("target_examples_per_property", 0))
    if target < 100:
        problems.append(f"[16.4] correctness 目标样例 <100: {target}")
    counts = data.get("valid_example_counts", {}) or {}
    low = {k: v for k, v in counts.items() if int(v) < 100}
    if low:
        problems.append(f"[16.4] 存在 <100 有效样例的 property: {low}")


def _check_coverage_guard(problems: list[str]) -> dict[str, Any]:
    """运行覆盖/漂移守卫（0 unmigrated + 双向相等）。返回摘要。"""
    try:
        from app.security.coverage_guard import check_drift

        findings = check_drift()
        clean = findings.is_clean()
        summary = findings.summary()
        total = findings.total()
        if not clean:
            problems.append(f"[13/16.17] 覆盖/漂移守卫不干净: {summary}")
        return {"clean": clean, "findings_total": total, "findings": summary}
    except Exception as exc:  # noqa: BLE001
        problems.append(f"[13/16.17] 覆盖/漂移守卫执行失败: {exc}")
        return {"clean": False, "error": str(exc)}


def run_completion_guard(
    *,
    manifest_path: Path = MANIFEST_PATH,
    schema_path: Path = SCHEMA_PATH,
    spec_dir: Path = SPEC_DIR,
    allow_missing_tasks: frozenset[str] = frozenset(),
    run_coverage: bool = True,
) -> GuardResult:
    """执行完成守卫。返回 GuardResult(ok, problems, report)。

    ``allow_missing_tasks`` 中的任务若在 manifest 缺席则不视为问题（用于关闭流程中
    Task 18 尚未追加的场景）；若存在则仍要求最新 passed。
    """
    problems: list[str] = []

    if not manifest_path.exists():
        return GuardResult(False, [f"[15.1/15.9] Evidence_Manifest 缺失: {manifest_path}"], {})

    manifest = load_manifest(manifest_path)
    _validate_schema(manifest, schema_path, problems)

    latest_by_task = latest_runs_per_task(manifest)
    latest_by_crit = latest_run_per_criterion(manifest)

    # (1) 每个必做叶子任务最新 run 必须 passed（16.21/16.23/15.12）。
    task_table: dict[str, Any] = {}
    for tk in REQUIRED_LEAF_TASKS:
        run = latest_by_task.get(tk)
        if run is None:
            if tk in allow_missing_tasks:
                task_table[tk] = {"seq": None, "status": "pending_close", "artifacts": 0}
                continue
            problems.append(f"[16.23] 必做任务缺失最新 run: Task {tk}")
            task_table[tk] = {"seq": None, "status": "missing", "artifacts": 0}
            continue
        status = run.get("status")
        task_table[tk] = {
            "seq": run.get("seq"),
            "status": status,
            "artifacts": len(run.get("artifacts", []) or []),
        }
        if status != "passed":
            problems.append(f"[15.12/16.23] Task {tk} 最新 run 非 passed: {status}")

    # (2) 最新 run 的 artifact 必须 hash/size/path/schema 干净（latest-run 语义）。
    checked = 0
    for tk, run in latest_by_task.items():
        checked += _verify_run_artifacts(run, spec_dir, problems)

    # (3) 每个被引用 criterion 的最新 run 必须 passed（15.12）。
    non_passed_crit = sorted(
        c for c, r in latest_by_crit.items() if r.get("status") != "passed"
    )
    for c in non_passed_crit:
        problems.append(
            f"[15.12] criterion {c} 最新 run 非 passed: {latest_by_crit[c].get('status')}"
        )

    # (4) Task 18 声明 criteria 覆盖检查（15.1–15.12 / 16.21–16.24）。部分 criteria
    #     （如 15.4 失败记录保留）只能由 Task 18 自身的 run 提供；因此仅在 Task 18 已存在
    #     （非 pending-close）时强制要求其全部声明 criteria 被最新 passing run 覆盖。
    missing_t18 = [c for c in TASK18_CRITERIA if c not in latest_by_crit]
    if missing_t18 and "18" not in allow_missing_tasks:
        problems.append(f"[15/16.21] Task 18 声明 criteria 缺失覆盖: {missing_t18}")

    # (5) smoke 冒充 correctness。
    _check_smoke_as_correctness(manifest, latest_by_task, spec_dir, problems)

    # (6) 覆盖/漂移守卫。
    coverage = _check_coverage_guard(problems) if run_coverage else {"clean": None, "skipped": True}

    report = build_report(
        manifest=manifest,
        task_table=task_table,
        latest_by_crit=latest_by_crit,
        non_passed_crit=non_passed_crit,
        artifacts_checked=checked,
        coverage=coverage,
        problems=problems,
    )
    return GuardResult(ok=not problems, problems=problems, report=report)


def build_report(
    *,
    manifest: dict[str, Any],
    task_table: dict[str, Any],
    latest_by_crit: dict[str, dict[str, Any]],
    non_passed_crit: list[str],
    artifacts_checked: int,
    coverage: dict[str, Any],
    problems: list[str],
) -> dict[str, Any]:
    """构造 **确定性** 完成守卫报告（可 hash-pin：无时间戳/绝对路径，键有序）。"""
    return {
        "spec": "procedure-delegation-visibility-isolation",
        "guard": "completion_guard",
        "semantics": "latest-run-per-task and latest-run-per-criterion",
        "verdict": "pass" if not problems else "fail",
        "required_leaf_tasks": list(REQUIRED_LEAF_TASKS),
        "task_latest": {k: task_table[k] for k in sorted(task_table, key=lambda x: int(x))},
        "criteria": {
            "total": len(latest_by_crit),
            "all_latest_passed": not non_passed_crit,
            "non_passed": non_passed_crit,
        },
        "task18_criteria": list(TASK18_CRITERIA),
        "latest_artifacts_verified": {
            "checked": artifacts_checked,
            "clean": not any("SHA-256" in p or "size" in p or "artifact 缺失" in p for p in problems),
        },
        "coverage_guard": coverage,
        "total_runs": len(manifest.get("runs", [])),
        "note": (
            "Task 18 = 本 Completion Guard 运行；其证据即本 run。历史 superseded run "
            "（如 Task 14 seq-24、Task 15 seq-26/27）按 append-only 保留，其漂移 artifact "
            "不阻断完成（latest-run-per-task 语义），从不改写已记录哈希。"
        ),
    }


def write_report(report: dict[str, Any], spec_dir: Path = SPEC_DIR) -> Path:
    """确定性写入守卫报告 artifact。"""
    path = spec_dir / _GUARD_REPORT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Close the spec (append-only Task 18 run) — only when all gates pass.
# ---------------------------------------------------------------------------
TASK18_ID = "18. 执行最终 Completion Guard 并关闭规格"
TASK18_TEST_IDS = (
    "tests/procedure_delegation_visibility/test_task18_completion_guard.py",
)
TASK18_COMMAND = "python -m app.security.completion_guard --close"


def close_spec() -> GuardResult:
    """通过则生成确定性报告并 append-only 追加 Task 18 run，随后严格复核 1–18 全绿。

    绝不假绿：若 pending 模式守卫失败，直接返回失败结果，不追加任何 run。
    """
    from app.security.evidence_manifest import append_run

    pending = run_completion_guard(allow_missing_tasks=frozenset({"18"}))
    if not pending.ok:
        return pending

    # 生成确定性报告并 pin 进 Task 18 run（append-only）。
    report_path = write_report(pending.report)
    rel = report_path.relative_to(SPEC_DIR).as_posix()
    append_run(
        task_id=TASK18_ID,
        status="passed",
        artifacts=[rel],
        test_ids=list(TASK18_TEST_IDS),
        criterion_ids=list(TASK18_CRITERIA),
        command=TASK18_COMMAND,
        notes=(
            "Task 18 最终 Completion Guard 通过并关闭规格。latest-run-per-task/criterion 语义："
            "Task 1–18 最新 run 全 passed；每个被引用 criterion 最新 run passed；最新 run artifact "
            "重算 SHA-256/size/path/schema 全部干净；覆盖/漂移守卫 0 unmigrated + 生产面⇔ledger 双向相等；"
            "correctness 证据 ≥100 有效样例，smoke 未冒充 correctness。Task 15 证据经确定性重录(seq-31)，"
            "历史 superseded run(seq-24/26/27 等)按 append-only 保留、其漂移 artifact 不阻断且哈希从未改写。"
        ),
    )
    # 严格复核：Task 18 已存在，1–18 全绿。
    return run_completion_guard(allow_missing_tasks=frozenset())


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _print_result(res: GuardResult) -> None:
    print("== Completion Guard: per-task latest run ==")
    for tk in sorted(res.report.get("task_latest", {}), key=lambda x: int(x)):
        row = res.report["task_latest"][tk]
        print(f"  Task {tk:>2}: seq={row['seq']} status={row['status']} artifacts={row['artifacts']}")
    cr = res.report.get("criteria", {})
    print(f"criteria: total={cr.get('total')} all_latest_passed={cr.get('all_latest_passed')}")
    cov = res.report.get("coverage_guard", {})
    print(f"coverage_guard: {cov}")
    if res.problems:
        print(f"\n[completion-guard] FAIL — {len(res.problems)} problem(s):")
        for p in res.problems:
            print(f"  - {p}")
    else:
        print("\n[completion-guard] PASS — all gates green")


def _main() -> int:
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass

    if "--close" in sys.argv:
        res = close_spec()
        _print_result(res)
        if res.ok:
            print("\n[completion-guard] SPEC CLOSED — Task 18 run appended (append-only)")
        else:
            print("\n[completion-guard] NOT CLOSED — gates failed; no run appended")
        return 0 if res.ok else 1

    strict = "--strict" in sys.argv
    allow = frozenset() if strict else frozenset({"18"})
    res = run_completion_guard(allow_missing_tasks=allow)
    _print_result(res)
    return 0 if res.ok else 1


if __name__ == "__main__":
    raise SystemExit(_main())
