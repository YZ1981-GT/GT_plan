"""合并模块 Phase 2 编排者 PBT：S1 DAG 顺序 / S2 失败隔离 / S6 幂等（hypothesis）

`consol_cascade_refresh_service.refresh_all` 是合并链路唯一编排者（A6/C2，ADR-CONSOL-201）。
它**只编排不重算**——把 build_tree / recalc_full / recalculate_trial /
reconcile_worksheet_vs_trial / generate_consol_reports_sync / generate_full_consol_notes
按 DAG 自底向上串起来。因此本文件 mock 掉所有底层 service，只验证编排器自身的：

- S1（6.1）DAG 顺序：全部成功时 steps_completed 恒为
  [tree, worksheet, trial, reconcile, report, notes]，progress_cb 收到同序步骤。
- S2（6.2）失败隔离：关键步（worksheet/trial）抛错 → 中断，下游不进 steps_completed；
  下游步（reconcile/report/notes）抛错 → 记 errors 但继续，后续步仍尝试。
- S6（6.5）幂等：deterministic 依赖下连续两次 refresh_all 的 steps_completed /
  nodes_refreshed 完全一致（编排器对确定性依赖是确定性的）。

Validates: Requirements 1.2, 1.3, 1.4 (Properties S1, S2, S6)
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from hypothesis import given, settings, strategies as st

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
    STEP_NOTES: "generate_full_consol_notes",
}

# 关键步骤名 → 被 patch 符号（中断 6.2 用）
_CRITICAL_STEP_TO_SYMBOL = {
    STEP_WORKSHEET: "recalc_full",
    STEP_TRIAL: "recalculate_trial",
}


def _fake_tree(node_count: int):
    """构造一个 build_tree 返回的 TreeNode 替身（company_code + 后代数可控）。

    refresh_all 用 `1 + len(get_descendants(tree))` 统计 nodes_refreshed，
    因此我们让 get_descendants 返回 node_count-1 个占位后代。
    """
    return SimpleNamespace(company_code="ROOT", project_id=uuid4())


def _patch_all(
    *,
    node_count: int = 1,
    notes_v2_enabled: bool = True,
):
    """统一 patch 编排器的全部底层依赖。返回 (patchers_cm, mocks_dict)。

    - build_tree: AsyncMock 返回 fake tree
    - get_descendants: MagicMock 返回 node_count-1 个占位后代
    - recalc_full / recalculate_trial / reconcile / generate_consol_reports_sync / generate_full_consol_notes: AsyncMock
    - settings.CONSOL_NOTES_V2_ENABLED: 控制 notes 是否真正执行 V2
    """
    descendants = [object()] * max(node_count - 1, 0)
    fake_settings = SimpleNamespace(CONSOL_NOTES_V2_ENABLED=notes_v2_enabled)

    patchers = {
        "build_tree": patch(f"{_MODULE}.build_tree", new=AsyncMock(return_value=_fake_tree(node_count))),
        "get_descendants": patch(f"{_MODULE}.get_descendants", new=MagicMock(return_value=descendants)),
        "recalc_full": patch(f"{_MODULE}.recalc_full", new=AsyncMock(return_value=None)),
        "recalculate_trial": patch(f"{_MODULE}.recalculate_trial", new=AsyncMock(return_value=None)),
        "reconcile_worksheet_vs_trial": patch(
            f"{_MODULE}.reconcile_worksheet_vs_trial", new=AsyncMock(return_value=MagicMock())
        ),
        "generate_consol_reports_sync": patch(
            f"{_MODULE}.generate_consol_reports_sync", new=AsyncMock(return_value=None)
        ),
        "generate_full_consol_notes": patch(
            f"{_MODULE}.generate_full_consol_notes", new=AsyncMock(return_value=[])
        ),
        "settings": patch(f"{_MODULE}.settings", new=fake_settings),
    }
    return patchers


def _make_db() -> AsyncMock:
    """构造带 AsyncMock commit 的 db 替身。"""
    db = AsyncMock()
    db.commit = AsyncMock(return_value=None)
    return db


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


# ===========================================================================
# S1（6.1）DAG 顺序不变
# ===========================================================================


class TestS1DagOrder:
    """S1 DAG 顺序：全部成功时 steps_completed 恒为 DAG 顺序，progress_cb 同序。

    **Validates: Requirements 1.2**
    """

    @given(node_count=st.integers(min_value=1, max_value=12))
    @settings(max_examples=15)
    @pytest.mark.asyncio
    async def test_steps_completed_in_exact_dag_order(self, node_count):
        """随机有效节点数 → steps_completed 顺序恒为 [tree,worksheet,trial,reconcile,report,notes]。"""
        patchers = _patch_all(node_count=node_count, notes_v2_enabled=True)
        recorder = _ProgressRecorder()
        with patchers["build_tree"], patchers["get_descendants"], patchers["recalc_full"], \
                patchers["recalculate_trial"], patchers["reconcile_worksheet_vs_trial"], \
                patchers["generate_consol_reports_sync"], patchers["generate_full_consol_notes"], \
                patchers["settings"]:
            result = await refresh_all(_make_db(), uuid4(), 2025, progress_cb=recorder)

        assert isinstance(result, CascadeRefreshResult)
        # 顺序恒定（不变式）
        assert result.steps_completed == _EXPECTED_ORDER
        assert result.errors == []
        # nodes_refreshed = 1 + 后代数
        assert result.nodes_refreshed == node_count
        # progress_cb 收到的成功步骤同序
        assert recorder.completed_steps_in_order() == _EXPECTED_ORDER

    @given(node_count=st.integers(min_value=1, max_value=8))
    @settings(max_examples=10)
    @pytest.mark.asyncio
    async def test_notes_after_report_after_trial(self, node_count):
        """关键 DAG 偏序：notes 必在 report 后，report 必在 trial 后。"""
        patchers = _patch_all(node_count=node_count, notes_v2_enabled=True)
        with patchers["build_tree"], patchers["get_descendants"], patchers["recalc_full"], \
                patchers["recalculate_trial"], patchers["reconcile_worksheet_vs_trial"], \
                patchers["generate_consol_reports_sync"], patchers["generate_full_consol_notes"], \
                patchers["settings"]:
            result = await refresh_all(_make_db(), uuid4(), 2025)

        steps = result.steps_completed
        assert steps.index(STEP_TRIAL) < steps.index(STEP_REPORT) < steps.index(STEP_NOTES)
        assert steps.index(STEP_WORKSHEET) < steps.index(STEP_TRIAL)


# ===========================================================================
# S2（6.2）失败隔离
# ===========================================================================


class TestS2FailureIsolation:
    """S2 失败隔离：关键步失败中断、下游步失败继续。

    **Validates: Requirements 1.3**
    """

    @given(critical_step=st.sampled_from(list(_CRITICAL_STEP_TO_SYMBOL.keys())))
    @settings(max_examples=10)
    @pytest.mark.asyncio
    async def test_critical_step_failure_aborts_cascade(self, critical_step):
        """worksheet 或 trial 抛错 → 该步记 errors，下游 report/notes 不进 steps_completed。"""
        patchers = _patch_all(node_count=3, notes_v2_enabled=True)
        symbol = _CRITICAL_STEP_TO_SYMBOL[critical_step]
        # 覆盖关键步为抛错
        boom = AsyncMock(side_effect=RuntimeError(f"{critical_step} boom"))
        patchers[symbol] = patch(f"{_MODULE}.{symbol}", new=boom)

        with patchers["build_tree"], patchers["get_descendants"], patchers["recalc_full"], \
                patchers["recalculate_trial"], patchers["reconcile_worksheet_vs_trial"], \
                patchers["generate_consol_reports_sync"], patchers["generate_full_consol_notes"], \
                patchers["settings"]:
            result = await refresh_all(_make_db(), uuid4(), 2025)

        # 失败步记入 errors
        error_steps = {e["step"] for e in result.errors}
        assert critical_step in error_steps
        # 失败的关键步不在 steps_completed
        assert critical_step not in result.steps_completed
        # 下游步骤被中断，绝不出现
        assert STEP_REPORT not in result.steps_completed
        assert STEP_NOTES not in result.steps_completed
        assert STEP_RECONCILE not in result.steps_completed
        if critical_step == STEP_WORKSHEET:
            # worksheet 失败 → trial 也不应执行
            assert STEP_TRIAL not in result.steps_completed

    @given(downstream_step=st.sampled_from(list(_DOWNSTREAM_STEP_TO_SYMBOL.keys())))
    @settings(max_examples=10)
    @pytest.mark.asyncio
    async def test_downstream_step_failure_continues_cascade(self, downstream_step):
        """reconcile/report/notes 抛错 → 记 errors 但不中断，关键步保留、后续下游仍尝试。"""
        patchers = _patch_all(node_count=3, notes_v2_enabled=True)
        symbol = _DOWNSTREAM_STEP_TO_SYMBOL[downstream_step]
        # 全部下游步现均 async（Phase 1 A3 后 generate_consol_reports_sync 也改 async）→ AsyncMock side_effect
        boom = AsyncMock(side_effect=RuntimeError(f"{downstream_step} boom"))
        patchers[symbol] = patch(f"{_MODULE}.{symbol}", new=boom)

        with patchers["build_tree"], patchers["get_descendants"], patchers["recalc_full"], \
                patchers["recalculate_trial"], patchers["reconcile_worksheet_vs_trial"], \
                patchers["generate_consol_reports_sync"], patchers["generate_full_consol_notes"], \
                patchers["settings"]:
            result = await refresh_all(_make_db(), uuid4(), 2025)

        # 失败下游步记入 errors，不进 steps_completed
        error_steps = {e["step"] for e in result.errors}
        assert downstream_step in error_steps
        assert downstream_step not in result.steps_completed
        # 关键步（含建树）始终保留（未被污染，S2）
        assert STEP_TREE in result.steps_completed
        assert STEP_WORKSHEET in result.steps_completed
        assert STEP_TRIAL in result.steps_completed
        # 级联未中断：失败步之后的下游步骤仍被尝试并完成
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

    编排器只委托 deterministic 的底层 service；本测试断言编排器本身对确定性
    输入是确定性的（steps_completed / nodes_refreshed 两次一致）。

    **Validates: Requirements 1.4**
    """

    @given(node_count=st.integers(min_value=1, max_value=10))
    @settings(max_examples=15)
    @pytest.mark.asyncio
    async def test_two_runs_same_result(self, node_count):
        """同 project/year + 同 mock 返回值 → 两次 steps_completed/nodes_refreshed 一致。"""
        project_id = uuid4()

        async def _run_once():
            patchers = _patch_all(node_count=node_count, notes_v2_enabled=True)
            with patchers["build_tree"], patchers["get_descendants"], patchers["recalc_full"], \
                    patchers["recalculate_trial"], patchers["reconcile_worksheet_vs_trial"], \
                    patchers["generate_consol_reports_sync"], patchers["generate_full_consol_notes"], \
                    patchers["settings"]:
                return await refresh_all(_make_db(), project_id, 2025)

        r1 = await _run_once()
        r2 = await _run_once()

        assert r1.steps_completed == r2.steps_completed
        assert r1.nodes_refreshed == r2.nodes_refreshed
        assert r1.errors == r2.errors == []
        assert r1.steps_completed == _EXPECTED_ORDER


# ===========================================================================
# 单元测试：进度回调失败不影响编排 / flag 关闭跳过 notes
# ===========================================================================


class TestCascadeUnit:
    """补充单元测试（具体边界）。"""

    @pytest.mark.asyncio
    async def test_progress_cb_exception_does_not_break_cascade(self):
        """progress_cb 抛异常被吞掉，编排链路仍完整完成。"""
        patchers = _patch_all(node_count=2, notes_v2_enabled=True)

        def _boom_cb(*_args, **_kwargs):
            raise ValueError("progress cb boom")

        with patchers["build_tree"], patchers["get_descendants"], patchers["recalc_full"], \
                patchers["recalculate_trial"], patchers["reconcile_worksheet_vs_trial"], \
                patchers["generate_consol_reports_sync"], patchers["generate_full_consol_notes"], \
                patchers["settings"]:
            result = await refresh_all(_make_db(), uuid4(), 2025, progress_cb=_boom_cb)

        assert result.steps_completed == _EXPECTED_ORDER
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_notes_flag_disabled_skips_v2_but_marks_step(self):
        """CONSOL_NOTES_V2_ENABLED=False → 不调 V2，notes 仍记为完成（skipped 终态）。"""
        patchers = _patch_all(node_count=2, notes_v2_enabled=False)
        v2_mock = AsyncMock(return_value=[])
        patchers["generate_full_consol_notes"] = patch(
            f"{_MODULE}.generate_full_consol_notes", new=v2_mock
        )
        with patchers["build_tree"], patchers["get_descendants"], patchers["recalc_full"], \
                patchers["recalculate_trial"], patchers["reconcile_worksheet_vs_trial"], \
                patchers["generate_consol_reports_sync"], patchers["generate_full_consol_notes"], \
                patchers["settings"]:
            result = await refresh_all(_make_db(), uuid4(), 2025)

        assert STEP_NOTES in result.steps_completed
        v2_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_build_tree_none_aborts_with_zero_nodes(self):
        """build_tree 返回 None → nodes_refreshed=0，tree 步仍完成，但下游正常跑。"""
        patchers = _patch_all(node_count=1, notes_v2_enabled=True)
        patchers["build_tree"] = patch(f"{_MODULE}.build_tree", new=AsyncMock(return_value=None))
        with patchers["build_tree"], patchers["get_descendants"], patchers["recalc_full"], \
                patchers["recalculate_trial"], patchers["reconcile_worksheet_vs_trial"], \
                patchers["generate_consol_reports_sync"], patchers["generate_full_consol_notes"], \
                patchers["settings"]:
            result = await refresh_all(_make_db(), uuid4(), 2025)

        assert result.nodes_refreshed == 0
        assert STEP_TREE in result.steps_completed
