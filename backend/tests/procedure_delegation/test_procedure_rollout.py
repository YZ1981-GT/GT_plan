# Feature: procedure-delegation-notification — Task 15 部署阶段/回滚
"""ProcedureRollout 测试：Property P34（部署阶段单调与回滚保留）+ 三开关行为矩阵。

Task 15 / 需求 13.1-13.9 / Design Deployment and Rollback：

- **P34（部署阶段单调与回滚保留）**：Requirements 13.1-13.8 —— 任意阶段跳跃在 guard 未满足时
  被拒绝（单调、逐阶段）；生产回滚关闭写/dispatcher 后不产生任何破坏性 DDL，V105 表列保留。
- **三开关行为矩阵**：Requirements 13.2/13.3 —— expand/dual-read/backfill/cutover/contract 各阶段
  允许的 (TASKS_ENABLED, WRITE_MODE, DISPATCHER) 组合确定。
- **cutover 前置校验**：Requirement 13.6 —— coverage/冲突阈值/投影一致性/backlog/回滚演练全过才放行。

纯逻辑（无 DB），PBT 用项目 fast profile（max_examples=5，由 conftest 收敛）。
"""
from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.procedure_rollout import (
    PHASE_BACKFILL,
    PHASE_CONTRACT,
    PHASE_CUTOVER,
    PHASE_DUAL_READ,
    PHASE_EXPAND,
    PHASES,
    RETAINED_V105_TABLES,
    ROLLBACK_TARGET_PHASE,
    WRITE_MODE_DUAL,
    WRITE_MODE_LEGACY,
    WRITE_MODE_TASK_SOURCE,
    WRITE_MODES,
    can_advance,
    detect_phase,
    evaluate_cutover_preconditions,
    expected_flags,
    flags_match_phase,
    is_task_write_allowed,
    phase_index,
    production_rollback_flags,
)

_phase_st = st.sampled_from(PHASES)


# ===========================================================================
# 三开关行为矩阵（Req 13.2 / 13.3）
# ===========================================================================
class TestPhaseMatrix:
    def test_expand_is_structure_only(self):
        pf = expected_flags(PHASE_EXPAND)
        assert pf.tasks_enabled is False
        assert pf.write_modes == frozenset({WRITE_MODE_LEGACY})
        assert pf.dispatcher_enabled is False

    def test_dual_read_allows_legacy_or_dual_no_task_source(self):
        pf = expected_flags(PHASE_DUAL_READ)
        assert pf.tasks_enabled is True
        assert WRITE_MODE_LEGACY in pf.write_modes and WRITE_MODE_DUAL in pf.write_modes
        assert WRITE_MODE_TASK_SOURCE not in pf.write_modes
        assert pf.dispatcher_enabled is False

    def test_backfill_is_dual_write_no_dispatcher(self):
        pf = expected_flags(PHASE_BACKFILL)
        assert pf.tasks_enabled is True
        assert pf.write_modes == frozenset({WRITE_MODE_DUAL})
        assert pf.dispatcher_enabled is False

    def test_cutover_and_contract_are_task_source_with_dispatcher(self):
        for phase in (PHASE_CUTOVER, PHASE_CONTRACT):
            pf = expected_flags(phase)
            assert pf.tasks_enabled is True
            assert pf.write_modes == frozenset({WRITE_MODE_TASK_SOURCE})
            assert pf.dispatcher_enabled is True

    def test_unknown_phase_raises(self):
        with pytest.raises(ValueError):
            expected_flags("nope")

    def test_task_write_allowed_only_dual_or_task_source(self):
        assert is_task_write_allowed(WRITE_MODE_DUAL)
        assert is_task_write_allowed(WRITE_MODE_TASK_SOURCE)
        assert not is_task_write_allowed(WRITE_MODE_LEGACY)

    @given(phase=_phase_st)
    @settings(max_examples=5, deadline=None)
    def test_expected_flags_match_phase(self, phase):
        pf = expected_flags(phase)
        # 该阶段声明的任一允许 write_mode 都应被 flags_match_phase 接受。
        for wm in pf.write_modes:
            assert flags_match_phase(
                phase,
                tasks_enabled=pf.tasks_enabled,
                write_mode=wm,
                dispatcher_enabled=pf.dispatcher_enabled,
            )

    def test_detect_phase_roundtrip_for_unique_combos(self):
        # cutover/contract 由 dispatcher+task-source 唯一识别（contract 靠后取胜）。
        assert detect_phase(
            tasks_enabled=True, write_mode=WRITE_MODE_TASK_SOURCE, dispatcher_enabled=True
        ) == PHASE_CONTRACT
        assert detect_phase(
            tasks_enabled=False, write_mode=WRITE_MODE_LEGACY, dispatcher_enabled=False
        ) == PHASE_EXPAND
        # 非法组合 → None
        assert detect_phase(
            tasks_enabled=False, write_mode=WRITE_MODE_TASK_SOURCE, dispatcher_enabled=True
        ) is None


# ===========================================================================
# P34（上半）：阶段单调推进 guard
# Validates: Requirements 13.1
# ===========================================================================
class TestP34PhaseMonotonic:
    def test_single_step_forward_with_checks_ok(self):
        ok, _ = can_advance(PHASE_EXPAND, PHASE_DUAL_READ, checks_passed=True)
        assert ok

    def test_single_step_forward_blocked_when_checks_fail(self):
        ok, reason = can_advance(PHASE_BACKFILL, PHASE_CUTOVER, checks_passed=False)
        assert not ok and "guard" in reason

    def test_skip_phase_rejected(self):
        ok, reason = can_advance(PHASE_EXPAND, PHASE_BACKFILL, checks_passed=True)
        assert not ok and "跳阶段" in reason

    def test_backward_rejected(self):
        ok, reason = can_advance(PHASE_CUTOVER, PHASE_DUAL_READ, checks_passed=True)
        assert not ok

    def test_noop_same_phase_allowed(self):
        ok, _ = can_advance(PHASE_CUTOVER, PHASE_CUTOVER, checks_passed=False)
        assert ok

    @given(
        ci=st.integers(min_value=0, max_value=len(PHASES) - 1),
        ti=st.integers(min_value=0, max_value=len(PHASES) - 1),
        checks=st.booleans(),
    )
    @settings(max_examples=5, deadline=None)
    def test_advance_is_monotonic_single_step(self, ci, ti, checks):
        """P34：任意 (current, target)，只有恰好前进一步且 guard 通过才允许；
        跳跃/回退一律拒绝（单调）。"""
        current, target = PHASES[ci], PHASES[ti]
        ok, _ = can_advance(current, target, checks_passed=checks)
        if ti == ci:
            assert ok  # no-op
        elif ti == ci + 1:
            assert ok is bool(checks)  # 恰好下一步：取决于 guard
        else:
            assert not ok  # 跳跃或回退


# ===========================================================================
# cutover 前置校验（Req 13.6）
# ===========================================================================
class TestCutoverPreconditions:
    def test_all_pass(self):
        pre = evaluate_cutover_preconditions(
            coverage_ratio=1.0,
            conflict_count=0,
            projection_mismatches=0,
            dispatcher_backlog=0,
            rollback_drill_passed=True,
        )
        assert pre.passed and pre.failures() == []

    def test_low_coverage_fails(self):
        pre = evaluate_cutover_preconditions(
            coverage_ratio=0.9,
            conflict_count=0,
            projection_mismatches=0,
            dispatcher_backlog=0,
            rollback_drill_passed=True,
        )
        assert not pre.passed and "coverage" in pre.failures()

    def test_each_gate_independently_blocks(self):
        assert "conflict_threshold" in evaluate_cutover_preconditions(
            coverage_ratio=1.0, conflict_count=1, projection_mismatches=0,
            dispatcher_backlog=0, rollback_drill_passed=True,
        ).failures()
        assert "projection_consistency" in evaluate_cutover_preconditions(
            coverage_ratio=1.0, conflict_count=0, projection_mismatches=3,
            dispatcher_backlog=0, rollback_drill_passed=True,
        ).failures()
        assert "dispatcher_backlog" in evaluate_cutover_preconditions(
            coverage_ratio=1.0, conflict_count=0, projection_mismatches=0,
            dispatcher_backlog=5, rollback_drill_passed=True,
        ).failures()
        assert "rollback_drill" in evaluate_cutover_preconditions(
            coverage_ratio=1.0, conflict_count=0, projection_mismatches=0,
            dispatcher_backlog=0, rollback_drill_passed=False,
        ).failures()


# ===========================================================================
# P34（下半）：生产非破坏回滚保留
# Validates: Requirements 13.7, 13.8
# ===========================================================================
class TestP34RollbackRetention:
    def test_rollback_stops_writes_and_dispatcher_non_destructive(self):
        plan = production_rollback_flags(
            tasks_enabled=True, write_mode=WRITE_MODE_TASK_SOURCE, dispatcher_enabled=True
        )
        # 停 task 新写：退回 legacy-safe。
        assert plan.write_mode == WRITE_MODE_LEGACY
        assert not is_task_write_allowed(plan.write_mode)
        # 停 dispatcher。
        assert plan.dispatcher_enabled is False
        # dual-read fallback 仍需读 task overlay。
        assert plan.tasks_enabled is True
        assert plan.target_phase == ROLLBACK_TARGET_PHASE == PHASE_DUAL_READ
        # 非破坏：不删任何 V105 表。
        assert plan.destructive is False
        assert set(plan.retained_tables) == set(RETAINED_V105_TABLES)
        assert "procedure_row_tasks" in plan.retained_tables

    @given(
        tasks=st.booleans(),
        write_mode=st.sampled_from(sorted(WRITE_MODES)),
        dispatcher=st.booleans(),
    )
    @settings(max_examples=5, deadline=None)
    def test_rollback_always_non_destructive_and_retains(self, tasks, write_mode, dispatcher):
        """P34：任意起始三开关，回滚后一律 legacy-safe + dispatcher off + 保留全部 V105 表，
        绝不破坏性 down。"""
        plan = production_rollback_flags(
            tasks_enabled=tasks, write_mode=write_mode, dispatcher_enabled=dispatcher
        )
        assert plan.destructive is False
        assert plan.write_mode == WRITE_MODE_LEGACY
        assert plan.dispatcher_enabled is False
        assert set(plan.retained_tables) == set(RETAINED_V105_TABLES)
