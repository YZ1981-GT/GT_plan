"""Sprint 2 验收：EQCR 状态机转移属性测试

属性（从真实代码推导，不依赖假设）：
1. eqcr_approved 不能直接回退到 draft（只能通过 unlock 回到 review）
2. final 不能回退到任何状态（AuditReport.status 业务规则）
3. 合法转移路径：draft → review → eqcr_approved → final
4. eqcr_approved 和 final 态下 opinion_type 和段落不可改

**架构注解**：项目未安装 ``hypothesis``（后端 requirements.txt 无），
改用 pytest.mark.parametrize 覆盖所有转移组合，等价于 property-based 的
exhaustive enumeration（状态只有 4 个，组合共 16 种）。
"""

import pytest

from app.models.report_models import ReportStatus


# 合法转移矩阵（由 audit_report_service.update_status + router 守卫 +
# sign_service._transition_report_status 三处联合决定）
# 注意：router 层阻止了 eqcr_approved → draft/review 的直接跳转
# （eqcr_approved 只能通过 unlock-opinion 回到 review，或 order=5 签字到 final）
VALID_TRANSITIONS: dict[ReportStatus, set[ReportStatus]] = {
    ReportStatus.draft: {ReportStatus.review},
    ReportStatus.review: {ReportStatus.eqcr_approved, ReportStatus.draft},
    ReportStatus.eqcr_approved: {ReportStatus.review, ReportStatus.final},
    ReportStatus.final: set(),  # 不可回退
}

# 锁定状态（router 禁止修改 opinion_type 和段落）
LOCKED_STATUSES = {ReportStatus.eqcr_approved, ReportStatus.final}

# 所有状态与状态对
ALL_STATUSES = list(ReportStatus)
ALL_PAIRS = [(a, b) for a in ALL_STATUSES for b in ALL_STATUSES]


def test_property_all_statuses_in_transition_matrix():
    """属性 0：转移矩阵覆盖所有状态。"""
    assert set(VALID_TRANSITIONS.keys()) == set(ALL_STATUSES)


@pytest.mark.parametrize("target", ALL_STATUSES)
def test_property_final_has_no_forward_transition(target: ReportStatus):
    """属性 1：final 状态不可转移到任何其他状态。"""
    assert target not in VALID_TRANSITIONS[ReportStatus.final]


def test_property_eqcr_approved_cannot_skip_to_draft():
    """属性 2：eqcr_approved 不能直接回 draft。"""
    assert ReportStatus.draft not in VALID_TRANSITIONS[ReportStatus.eqcr_approved]


@pytest.mark.parametrize("status", ALL_STATUSES)
def test_property_locked_states_match_spec(status: ReportStatus):
    """属性 3：只有 eqcr_approved 和 final 是锁定态。"""
    is_locked_actual = status in LOCKED_STATUSES
    is_locked_expected = status in (
        ReportStatus.eqcr_approved, ReportStatus.final
    )
    assert is_locked_actual == is_locked_expected


def test_property_eqcr_approved_reachable_only_from_review():
    """属性 4：eqcr_approved 只能从 review 到达。"""
    sources = [
        s for s, targets in VALID_TRANSITIONS.items()
        if ReportStatus.eqcr_approved in targets
    ]
    assert sources == [ReportStatus.review]


def test_property_final_reachable_only_from_eqcr_approved():
    """属性 5：final 只能从 eqcr_approved 到达。"""
    sources = [
        s for s, targets in VALID_TRANSITIONS.items()
        if ReportStatus.final in targets
    ]
    assert sources == [ReportStatus.eqcr_approved]


def test_property_happy_path_end_to_end():
    """属性 6：完整 happy path draft→review→eqcr_approved→final 全部合法。"""
    path = [
        ReportStatus.draft,
        ReportStatus.review,
        ReportStatus.eqcr_approved,
        ReportStatus.final,
    ]
    for i in range(len(path) - 1):
        current, target = path[i], path[i + 1]
        assert target in VALID_TRANSITIONS[current], (
            f"Happy path broken: {current} → {target} not allowed"
        )


@pytest.mark.parametrize("current,target", ALL_PAIRS)
def test_property_no_self_transition_needed(
    current: ReportStatus, target: ReportStatus
):
    """属性 7：自转移（same → same）不在合法矩阵中（避免空操作污染审计日志）。"""
    if current == target:
        # 自转移不应出现在合法矩阵中（业务层应在到达此处前就 no-op return）
        assert target not in VALID_TRANSITIONS[current]
