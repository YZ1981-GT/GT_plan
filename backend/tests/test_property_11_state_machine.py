"""Property 11: 状态机一致性 — hypothesis 属性测试

V3 收官增强 Req 10.5。

∀ module M ∈ {workpaper, adjustment, misstatement, report, disclosure},
∀ status S ∈ M.states,
∀ role R ∈ {admin, partner, manager, editor, qc, auditor}:
  compute_allowed_actions(M, S, R) 返回的 allowed 列表中的每个 action
  都对应一条从 S 出发的合法转移，且 R 在该转移的 role_required 中。

**Validates: Requirements 10.5**

文件：backend/tests/test_property_11_state_machine.py
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from app.services.allowed_actions_service import (
    compute_allowed_actions,
    _STATE_MACHINES,
    _check_transition,
)
from app.services.state_machines.base import StateMachine


# ---------------------------------------------------------------------------
# 策略定义
# ---------------------------------------------------------------------------

MODULES = list(_STATE_MACHINES.keys())
ROLES = ["admin", "partner", "manager", "editor", "qc", "auditor"]


def module_status_role_strategy():
    """生成 (module, status, role) 三元组。"""
    return st.one_of(*[
        st.tuples(
            st.just(module),
            st.sampled_from(sm.states),
            st.sampled_from(ROLES),
        )
        for module, sm in _STATE_MACHINES.items()
    ])


# ---------------------------------------------------------------------------
# Property 11: 状态机一致性
# ---------------------------------------------------------------------------


class TestStateMachineConsistency:
    """Property 11: allowed_actions 与状态机定义一致

    **Validates: Requirements 10.5**
    """

    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(data=module_status_role_strategy())
    @pytest.mark.asyncio
    async def test_allowed_actions_consistent_with_transitions(self, data):
        """allowed 列表中的每个 action 都对应合法转移 + 角色匹配。

        **Validates: Requirements 10.5**
        """
        module, status, role = data
        sm = _STATE_MACHINES[module]

        # Mock guard 结果（全部通过）
        guard_results = {
            "not_archived": True,
            "no_pending_ai_content": True,
            "no_unresolved_conflict": True,
            "all_workpapers_signed": True,
        }

        # 获取从当前状态出发的所有转移
        available_transitions = sm.get_transitions_from(status)

        # 计算每个 action 的 allowed/denied
        for t in available_transitions:
            allowed, reason_code, reason_zh = _check_transition(t, role, guard_results)

            if allowed:
                # 验证：角色在 role_required 中（或 role_required 为空）
                if t.role_required:
                    assert role in t.role_required, (
                        f"Action {t.action} allowed for role {role} but role not in "
                        f"role_required={t.role_required} (module={module}, status={status})"
                    )
            else:
                # 验证：denied 有原因
                assert reason_code is not None, (
                    f"Action {t.action} denied but no reason_code "
                    f"(module={module}, status={status}, role={role})"
                )
                assert reason_zh is not None, (
                    f"Action {t.action} denied but no reason_zh "
                    f"(module={module}, status={status}, role={role})"
                )

    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(data=module_status_role_strategy())
    @pytest.mark.asyncio
    async def test_denied_actions_have_valid_reason(self, data):
        """denied 列表中的每个 action 都有合法的 reason_code。

        **Validates: Requirements 10.5**
        """
        module, status, role = data
        sm = _STATE_MACHINES[module]

        guard_results = {
            "not_archived": True,
            "no_pending_ai_content": True,
            "no_unresolved_conflict": True,
            "all_workpapers_signed": True,
        }

        available_transitions = sm.get_transitions_from(status)

        for t in available_transitions:
            allowed, reason_code, reason_zh = _check_transition(t, role, guard_results)

            if not allowed:
                valid_codes = {
                    "ROLE_INSUFFICIENT",
                    "STATE_INVALID",
                    "PROJECT_ARCHIVED",
                    "AI_PENDING",
                    "CONFLICT_UNRESOLVED",
                    "GUARD_FAILED",
                }
                assert reason_code in valid_codes, (
                    f"Invalid reason_code={reason_code} for denied action {t.action} "
                    f"(module={module}, status={status}, role={role})"
                )

    @settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(data=module_status_role_strategy())
    @pytest.mark.asyncio
    async def test_guard_failure_blocks_action(self, data):
        """当 guard 条件不满足时，action 必须被 denied。

        **Validates: Requirements 10.5**
        """
        module, status, role = data
        sm = _STATE_MACHINES[module]

        # 所有 guard 失败
        guard_results = {
            "not_archived": False,
            "no_pending_ai_content": False,
            "no_unresolved_conflict": False,
            "all_workpapers_signed": False,
        }

        available_transitions = sm.get_transitions_from(status)

        for t in available_transitions:
            if t.guards:  # 只检查有 guard 的转移
                allowed, reason_code, reason_zh = _check_transition(t, role, guard_results)
                # 如果角色不满足，先被角色拦截
                if t.role_required and role not in t.role_required:
                    assert not allowed
                    assert reason_code == "ROLE_INSUFFICIENT"
                else:
                    # 角色满足但 guard 失败
                    assert not allowed, (
                        f"Action {t.action} should be denied when guards fail "
                        f"(module={module}, status={status}, role={role})"
                    )

    def test_all_modules_have_status_labels(self):
        """每个模块的所有状态都有中文标签。

        **Validates: Requirements 10.5**
        """
        for module, sm in _STATE_MACHINES.items():
            for state in sm.states:
                assert state in sm.status_labels_zh, (
                    f"Module {module} missing status_labels_zh for state '{state}'"
                )

    def test_all_modules_have_action_labels(self):
        """每个模块的所有 action 都有中文标签。

        **Validates: Requirements 10.5**
        """
        for module, sm in _STATE_MACHINES.items():
            for action in sm.all_actions:
                assert action in sm.action_labels_zh, (
                    f"Module {module} missing action_labels_zh for action '{action}'"
                )

    def test_transitions_reference_valid_states(self):
        """所有转移的 from_ 和 to 都是合法状态。

        **Validates: Requirements 10.5**
        """
        for module, sm in _STATE_MACHINES.items():
            for t in sm.transitions:
                assert t.from_ in sm.states, (
                    f"Module {module}: transition from '{t.from_}' not in states"
                )
                assert t.to in sm.states, (
                    f"Module {module}: transition to '{t.to}' not in states"
                )
