# Feature: procedure-delegation-visibility-isolation — Task 18 最终 Completion Guard（组件 C18 Evidence）
"""Task 18 / Requirements 15.1–15.12, 16.21–16.24 / Design Property 20.

对 ``app.security.completion_guard`` 做稳定回归：latest-run-per-task/criterion 语义、
最新 run artifact 的 SHA-256/size/path/schema 干净、smoke 不冒充 correctness、覆盖/漂移
守卫干净、以及全部必做叶子任务(1–18)最新 run 均 passed。此测试是 Task 18 的稳定 test id，
挂 CI；绝不假绿——它直接调用真实守卫（含真实 app 覆盖扫描 + 真实 manifest 重算哈希）。
"""
from __future__ import annotations

from app.security.completion_guard import (
    REQUIRED_LEAF_TASKS,
    TASK18_CRITERIA,
    latest_run_per_criterion,
    latest_runs_per_task,
    run_completion_guard,
)
from app.security.evidence_manifest import load_manifest


def test_completion_guard_strict_all_green():
    """严格模式：1–18 全部最新 run passed + 全部门禁通过（无假绿）。"""
    res = run_completion_guard(allow_missing_tasks=frozenset())
    assert res.ok, "Completion Guard 未通过:\n" + "\n".join(res.problems)
    assert res.report["verdict"] == "pass"
    assert res.report["coverage_guard"]["clean"] is True
    assert res.report["criteria"]["all_latest_passed"] is True


def test_every_required_leaf_task_latest_passed():
    manifest = load_manifest()
    latest = latest_runs_per_task(manifest)
    for tk in REQUIRED_LEAF_TASKS:
        assert tk in latest, f"必做任务缺失最新 run: Task {tk}"
        assert latest[tk]["status"] == "passed", f"Task {tk} 最新 run 非 passed"


def test_task18_declared_criteria_covered_by_passing_latest_run():
    manifest = load_manifest()
    by_crit = latest_run_per_criterion(manifest)
    for c in TASK18_CRITERIA:
        assert c in by_crit, f"Task 18 声明 criterion 未覆盖: {c}"
        assert by_crit[c]["status"] == "passed", f"criterion {c} 最新 run 非 passed"
