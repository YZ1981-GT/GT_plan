"""合并模块 Phase 2 编排者 PBT：S1 DAG 顺序 / S2 失败隔离 / S6 幂等（hypothesis）

`consol_cascade_refresh_service.refresh_all` 是合并链路唯一编排者（A6/C2，ADR-CONSOL-201）。
它**只编排不重算**——把 build_tree / recalc_full / recalculate_trial /
reconcile_worksheet_vs_trial / generate_consol_reports_sync / refresh_notes_exclusive
按 DAG 自底向上串起来。因此本文件 mock 掉所有底层 service，只验证编排器自身的：

- S1（6.1）DAG 顺序：全部成功时 steps_completed 恒为
  [tree, worksheet, trial, reconcile, report, notes]，progress_cb 收到同序步骤。
- S2（6.2）失败隔离：关键步（worksheet/trial）抛错 → 中断，下游不进 steps_completed；
  下游步（reconcile/report/notes）抛错 → 回滚本步、记 errors 但继续，后续步仍尝试。
- S6（6.5）幂等：deterministic 依赖下连续两次 refresh_all 的 steps_completed /
  nodes_refreshed 完全一致（编排器对确定性依赖是确定性的）。

notes 步 = 合并推送同一附注刷新（``consol_push_service.refresh_notes_exclusive``，同一把锁）；
刷新统计 ``note_status`` 为 partial / failed 记错误不算完成，skipped 记 steps_skipped
（spec consol-note-header-library-and-node-reaggregate R6.1：原 V2 生成器已下线）。

Validates: Requirements 1.2, 1.3, 1.4 (Properties S1, S2, S6)
"""

from __future__ import annotations

import asyncio
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from hypothesis import given, settings, strategies as st

from app.schemas.consol_context import ConsolContext
from app.services.consol_context_service import context_from_tree, tree_fingerprint
from app.services.consol_cascade_refresh_service import (
    STEP_NOTES,
    STEP_RECONCILE,
    STEP_REPORT,
    STEP_TREE,
    STEP_TRIAL,
    STEP_WORKSHEET,
    CascadeRefreshResult,
    refresh_all,
)

_MODULE = "app.services.consol_cascade_refresh_service"

# DAG 期望顺序（属性 S1 不变式）
_EXPECTED_ORDER = [
    STEP_TREE,
    STEP_WORKSHEET,
    STEP_TRIAL,
    STEP_RECONCILE,
    STEP_REPORT,
    STEP_NOTES,
]

# 下游步骤名 → 在模块里对应的被 patch 符号（失败隔离 6.2 用）
_DOWNSTREAM_STEP_TO_SYMBOL = {
    STEP_RECONCILE: "reconcile_worksheet_vs_trial",
    STEP_REPORT: "generate_consol_reports_sync",
    STEP_NOTES: "refresh_notes_exclusive",
}

# 关键步骤名 → 被 patch 符号（中断 6.2 用）
_CRITICAL_STEP_TO_SYMBOL = {
    STEP_WORKSHEET: "recalc_full",
    STEP_TRIAL: "recalculate_trial",
}

_PATCH_KEYS = (
    "build_tree", "build_consol_context", "get_descendants", "recalc_full", "recalculate_trial",
    "reconcile_worksheet_vs_trial", "generate_consol_reports_sync", "refresh_notes_exclusive",
)


def _note_stats(note_status: str = "persisted", *, refreshed: int = 4, kept: int = 0, failed: int = 0) -> dict:
    """``consol_push_service._refresh_notes`` 同形统计。"""
    return {
        "stale_marked": 6, "distinct_section_count": 3, "node_count": 2,
        "refreshed_count": refreshed, "kept_pulled_count": kept, "failed_count": failed,
        "skipped_count": 0, "note_status": note_status,
    }


def _fake_tree(node_count: int):
    """构造一个 build_tree 返回的 TreeNode 替身（company_code + 后代数可控）。

    refresh_all 用 `1 + len(get_descendants(tree))` 统计 nodes_refreshed，
    因此我们让 get_descendants 返回 node_count-1 个占位后代。
    """
    return SimpleNamespace(
        company_code="ROOT",
        project_id=uuid4(),
        node_key="ROOT:consol",
        role="consol",
        kind="aggregate",
        host_project_id=None,
        report_scope="consolidated",
        children=[],
    )


def _patch_all(*, node_count: int = 1, note_status: str = "persisted", **stats_kw):
    """统一 patch 编排器的全部底层依赖，返回 patchers 字典（含各 mock，供断言）。"""
    descendants = [object()] * max(node_count - 1, 0)
    tree = _fake_tree(node_count)
    context_box: list[ConsolContext] = []

    async def _build_context(_db, project_id, year, *, tree=None):
        context = context_from_tree(project_id, year, tree)
        context_box.append(context)
        return context

    build_context_mock = AsyncMock(side_effect=_build_context)
    recalc_full_mock = AsyncMock(return_value=None)
    recalculate_trial_mock = AsyncMock(return_value=None)
    reconcile_mock = AsyncMock(return_value=MagicMock())
    report_mock = AsyncMock(return_value=None)
    notes_mock = AsyncMock(return_value=_note_stats(note_status, **stats_kw))
    return {
        "tree": tree,
        "context_box": context_box,
        "build_tree": patch(f"{_MODULE}.build_tree", new=AsyncMock(return_value=tree)),
        "build_consol_context": patch(f"{_MODULE}.build_consol_context", new=build_context_mock),
        "build_context_mock": build_context_mock,
        "get_descendants": patch(f"{_MODULE}.get_descendants", new=MagicMock(return_value=descendants)),
        "recalc_full": patch(f"{_MODULE}.recalc_full", new=recalc_full_mock),
        "recalc_full_mock": recalc_full_mock,
        "recalculate_trial": patch(f"{_MODULE}.recalculate_trial", new=recalculate_trial_mock),
        "recalculate_trial_mock": recalculate_trial_mock,
        "reconcile_worksheet_vs_trial": patch(f"{_MODULE}.reconcile_worksheet_vs_trial", new=reconcile_mock),
        "reconcile_mock": reconcile_mock,
        "generate_consol_reports_sync": patch(f"{_MODULE}.generate_consol_reports_sync", new=report_mock),
        "report_mock": report_mock,
        "refresh_notes_exclusive": patch(f"{_MODULE}.refresh_notes_exclusive", new=notes_mock),
        "notes_mock": notes_mock,
    }


def _make_db() -> AsyncMock:
    db = AsyncMock()
    db.commit = AsyncMock(return_value=None)
    db.rollback = AsyncMock(return_value=None)
    return db


async def _run(patchers, *, db=None, project_id=None, progress_cb=None) -> CascadeRefreshResult:
    with ExitStack() as stack:
        for key in _PATCH_KEYS:
            stack.enter_context(patchers[key])
        return await refresh_all(db or _make_db(), project_id or uuid4(), 2025, progress_cb=progress_cb)


def _assert_shared_identity(patchers, *steps: str) -> None:
    """断言级联只构造一次上下文，并把同一 tree/context 透传给各阶段。"""
    assert patchers["build_context_mock"].await_count == 1
    assert len(patchers["context_box"]) == 1
    context = patchers["context_box"][0]
    tree = patchers["tree"]
    assert context.tree_fingerprint == tree_fingerprint(tree)
    for step in steps:
        mock = patchers[f"{step}_mock"]
        assert mock.await_count == 1, step
        call = mock.await_args
        assert call.kwargs["tree"] is tree, step
        assert call.kwargs["context"] is context, step


class _ProgressRecorder:
    """记录 progress_cb 收到的步骤序列（仅 completed/skipped 状态计入顺序）。"""

    def __init__(self):
        self.events: list[tuple] = []

    def __call__(self, step, current, total, current_node, status):
        self.events.append((step, current, total, current_node, status))

    def completed_steps_in_order(self) -> list[str]:
        # 编排器对每步先 emit running 再 emit completed/skipped；取成功类终态保留顺序
        return [
            step
            for (step, _c, _t, _node, status) in self.events
            if status in ("completed", "skipped")
        ]

    def final_status(self, step: str) -> str | None:
        statuses = [status for (s, _c, _t, _node, status) in self.events if s == step]
        return statuses[-1] if statuses else None


# ===========================================================================
# S1（6.1）DAG 顺序不变
# ===========================================================================


class TestS1DagOrder:
    """S1 DAG 顺序：全部成功时 steps_completed 恒为 DAG 顺序，progress_cb 同序。

    **Validates: Requirements 1.2**
    """

    @given(node_count=st.integers(min_value=1, max_value=12))
    @settings(max_examples=5)
    @pytest.mark.asyncio
    async def test_steps_completed_in_exact_dag_order(self, node_count):
        """随机有效节点数 → steps_completed 顺序恒为 [tree,worksheet,trial,reconcile,report,notes]。"""
        patchers = _patch_all(node_count=node_count)
        recorder = _ProgressRecorder()
        result = await _run(patchers, progress_cb=recorder)

        assert isinstance(result, CascadeRefreshResult)
        assert result.steps_completed == _EXPECTED_ORDER
        assert result.errors == []
        assert result.nodes_refreshed == node_count
        assert recorder.completed_steps_in_order() == _EXPECTED_ORDER
        _assert_shared_identity(patchers, "recalc_full", "recalculate_trial", "report", "notes")

    @given(node_count=st.integers(min_value=1, max_value=8))
    @settings(max_examples=5)
    @pytest.mark.asyncio
    async def test_notes_after_report_after_trial(self, node_count):
        """关键 DAG 偏序：notes 必在 report 后，report 必在 trial 后。"""
        patchers = _patch_all(node_count=node_count)
        result = await _run(patchers)

        steps = result.steps_completed
        assert steps.index(STEP_TRIAL) < steps.index(STEP_REPORT) < steps.index(STEP_NOTES)
        assert steps.index(STEP_WORKSHEET) < steps.index(STEP_TRIAL)
        _assert_shared_identity(patchers, "recalc_full", "recalculate_trial", "report", "notes")


# ===========================================================================
# S2（6.2）失败隔离
# ===========================================================================


class TestS2FailureIsolation:
    """S2 失败隔离：关键步失败中断、下游步失败回滚本步后继续。

    **Validates: Requirements 1.3**
    """

    @given(critical_step=st.sampled_from(list(_CRITICAL_STEP_TO_SYMBOL.keys())))
    @settings(max_examples=5)
    @pytest.mark.asyncio
    async def test_critical_step_failure_aborts_cascade(self, critical_step):
        """worksheet 或 trial 抛错 → 该步记 errors，下游 report/notes 不进 steps_completed。"""
        patchers = _patch_all(node_count=3)
        symbol = _CRITICAL_STEP_TO_SYMBOL[critical_step]
        patchers[symbol] = patch(f"{_MODULE}.{symbol}", new=AsyncMock(side_effect=RuntimeError(f"{critical_step} boom")))

        result = await _run(patchers)

        assert critical_step in {e["step"] for e in result.errors}
        assert critical_step not in result.steps_completed
        assert STEP_REPORT not in result.steps_completed
        assert STEP_NOTES not in result.steps_completed
        assert STEP_RECONCILE not in result.steps_completed
        patchers["notes_mock"].assert_not_awaited()
        if critical_step == STEP_WORKSHEET:
            assert STEP_TRIAL not in result.steps_completed

    @given(downstream_step=st.sampled_from(list(_DOWNSTREAM_STEP_TO_SYMBOL.keys())))
    @settings(max_examples=5)
    @pytest.mark.asyncio
    async def test_downstream_step_failure_continues_cascade(self, downstream_step):
        """reconcile/report/notes 抛错 → 回滚本步、记 errors 但不中断，关键步保留、后续下游仍尝试。"""
        patchers = _patch_all(node_count=3)
        symbol = _DOWNSTREAM_STEP_TO_SYMBOL[downstream_step]
        patchers[symbol] = patch(f"{_MODULE}.{symbol}", new=AsyncMock(side_effect=RuntimeError(f"{downstream_step} boom")))
        db = _make_db()

        result = await _run(patchers, db=db)

        assert downstream_step in {e["step"] for e in result.errors}
        assert downstream_step not in result.steps_completed
        assert STEP_TREE in result.steps_completed
        assert STEP_WORKSHEET in result.steps_completed
        assert STEP_TRIAL in result.steps_completed
        # PG 上失败语句让事务 aborted：下游步失败必须回滚，否则后续步骤连带失败
        db.rollback.assert_awaited()
        later_steps = _EXPECTED_ORDER[_EXPECTED_ORDER.index(downstream_step) + 1:]
        for later in later_steps:
            assert later in result.steps_completed, (
                f"下游步 {downstream_step} 失败后，后续步 {later} 应仍尝试完成"
            )


# ===========================================================================
# S6（6.5）一键刷新幂等
# ===========================================================================


class TestS6Idempotency:
    """S6 幂等：deterministic 依赖下连续两次 refresh_all 结果数值一致。

    **Validates: Requirements 1.4**
    """

    @given(node_count=st.integers(min_value=1, max_value=10))
    @settings(max_examples=5)
    @pytest.mark.asyncio
    async def test_two_runs_same_result(self, node_count):
        project_id = uuid4()
        r1 = await _run(_patch_all(node_count=node_count), project_id=project_id)
        r2 = await _run(_patch_all(node_count=node_count), project_id=project_id)

        assert r1.steps_completed == r2.steps_completed
        assert r1.nodes_refreshed == r2.nodes_refreshed
        assert r1.errors == r2.errors == []
        assert r1.steps_completed == _EXPECTED_ORDER


# ===========================================================================
# notes 步：推送同一附注刷新的统计如实上报
# ===========================================================================


class TestNotesStep:
    """notes 步按刷新统计 ``note_status`` 上报：persisted 完成、skipped 跳过、partial / failed 记错误。"""

    @pytest.mark.asyncio
    async def test_persisted_completes(self):
        patchers = _patch_all(node_count=2, note_status="persisted", refreshed=6, kept=2)
        recorder = _ProgressRecorder()
        project_id = uuid4()
        result = await _run(patchers, project_id=project_id, progress_cb=recorder)

        assert STEP_NOTES in result.steps_completed
        assert recorder.final_status(STEP_NOTES) == "completed"
        call = patchers["notes_mock"].await_args
        assert call.args[1:] == (project_id, 2025)   # (db, project_id, year)

    @pytest.mark.asyncio
    async def test_skipped_is_not_reported_as_completed(self):
        patchers = _patch_all(node_count=2, note_status="skipped", refreshed=0)
        recorder = _ProgressRecorder()
        result = await _run(patchers, progress_cb=recorder)

        assert STEP_NOTES not in result.steps_completed
        assert STEP_NOTES in result.steps_skipped
        assert result.errors == []
        assert recorder.final_status(STEP_NOTES) == "skipped"

    @pytest.mark.parametrize("note_status, word", [("partial", "部分失败"), ("failed", "失败")])
    @pytest.mark.asyncio
    async def test_partial_or_failed_records_error(self, note_status, word):
        patchers = _patch_all(node_count=2, note_status=note_status, refreshed=3, kept=1, failed=2)
        recorder = _ProgressRecorder()
        result = await _run(patchers, progress_cb=recorder)

        assert STEP_NOTES not in result.steps_completed
        assert STEP_NOTES not in result.steps_skipped
        errors = [e for e in result.errors if e["step"] == STEP_NOTES]
        assert len(errors) == 1
        assert f"合并附注刷新{word}" in errors[0]["error"]
        assert "失败 2 个章节×节点" in errors[0]["error"]
        assert "保留单体附注拉数 1" in errors[0]["error"]
        assert recorder.final_status(STEP_NOTES) == "error"


class TestCascadeUnit:
    """补充单元测试（具体边界）。"""

    @pytest.mark.asyncio
    async def test_progress_cb_exception_does_not_break_cascade(self):
        """progress_cb 抛异常被吞掉，编排链路仍完整完成。"""
        def _boom_cb(*_args, **_kwargs):
            raise ValueError("progress cb boom")

        result = await _run(_patch_all(node_count=2), progress_cb=_boom_cb)

        assert result.steps_completed == _EXPECTED_ORDER
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_build_tree_none_aborts_with_zero_nodes(self):
        """build_tree 返回 None → nodes_refreshed=0，tree 步仍完成，但下游正常跑。"""
        patchers = _patch_all(node_count=1)
        patchers["build_tree"] = patch(f"{_MODULE}.build_tree", new=AsyncMock(return_value=None))
        result = await _run(patchers)

        assert result.nodes_refreshed == 0
        assert STEP_TREE in result.steps_completed


# ===========================================================================
# refresh_notes_exclusive：与合并推送 / 重新汇总同一把锁
# ===========================================================================


class TestRefreshNotesExclusive:

    @pytest.mark.asyncio
    async def test_waits_for_the_push_target_lock(self):
        """推送 / 重新汇总持有目标锁时，一键刷新的附注步等它释放后才刷新（同一把进程锁）。"""
        from app.services import consol_push_service as push

        project_id, year = uuid4(), 2025
        order: list[str] = []

        async def fake_refresh(_db, pid, yr, *, context=None, tree=None):
            order.append("refresh")
            return _note_stats()

        db = AsyncMock()
        db.get_bind = MagicMock(return_value=SimpleNamespace(dialect=SimpleNamespace(name="sqlite")))
        with patch.object(push, "_refresh_notes", new=fake_refresh):
            async with push._process_lock("target", project_id, year):
                task = asyncio.create_task(push.refresh_notes_exclusive(db, project_id, year))
                await asyncio.sleep(0.05)
                assert order == [], "持锁期间不应开始刷新"
                order.append("released")
            stats = await asyncio.wait_for(task, timeout=2)

        assert order == ["released", "refresh"]
        assert stats["note_status"] == "persisted"
