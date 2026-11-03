"""调整分录状态中文名一致（spec consol-autotree-residual-closure R4）。

系统字典「调整分录状态」是单一来源（调整分录页、前端 ``ADJUSTMENT_STATUS_LABELS`` 用的都是它）：

- 可解释状态机面板的状态名、当前状态与字典逐值相等，动作用同一套「复核 / 驳回」措辞
  （原先状态机写「待审批 / 已退回」「提交审批 / 退回」，同一条分录两处叫法不同）；
- 合并抵销分录是另一业务对象，保留「待审批 / 已审批」，「已驳回」与调整分录一致。

前端一侧（集中登记标签、前后端交叉直读）见 ``constants/__tests__/adjustmentStatusLabels.spec.ts``。
"""
from __future__ import annotations

import uuid

import pytest

from app.models.audit_platform_models import ReviewStatus
from app.routers.system_dicts import _DICTS
from app.services import allowed_actions_service, consol_elimination_sheet_service, elimination_service
from app.services.adjustment_service import _VALID_TRANSITIONS
from app.services.state_machines.adjustment_sm import ADJUSTMENT_SM

DICT = {entry["value"]: entry["label"] for entry in _DICTS["adjustment_status"]}


def test_dict_is_the_review_wording() -> None:
    assert DICT == {"draft": "草稿", "pending_review": "待复核", "approved": "已批准", "rejected": "已驳回"}


@pytest.mark.parametrize("status", sorted(DICT))
def test_state_machine_status_label_equals_dict(status: str) -> None:
    assert ADJUSTMENT_SM.status_labels_zh[status] == DICT[status]


def test_state_machine_actions_use_review_wording() -> None:
    labels = ADJUSTMENT_SM.action_labels_zh
    assert (labels["submit"], labels["approve"], labels["reject"]) == ("提交复核", "批准", "驳回")
    stale = {k: v for k, v in {**labels, **ADJUSTMENT_SM.status_labels_zh}.items() if "审批" in v or "退回" in v}
    assert not stale, f"调整分录状态机仍有审批 / 退回措辞：{stale}"


def test_state_machine_exactly_matches_current_production_four_state_graph() -> None:
    """草稿直批/直驳是当前兼容边，后续须与生产复核任务门同批删除。"""
    assert set(ADJUSTMENT_SM.states) == {status.value for status in ReviewStatus}
    actual_edges = {(transition.from_, transition.to) for transition in ADJUSTMENT_SM.transitions}
    production_edges = {
        (source.value, target.value)
        for source, targets in _VALID_TRANSITIONS.items()
        for target in targets
    }
    assert actual_edges == production_edges
    assert "posted" not in ADJUSTMENT_SM.states
    assert "post" not in ADJUSTMENT_SM.all_actions
    assert {("draft", "approved"), ("draft", "rejected")} <= actual_edges


@pytest.mark.parametrize(("status", "role", "expected_status", "expected_actions"), [
    ("draft", "editor", "草稿", ["提交复核"]),
    ("draft", "manager", "草稿", ["提交复核", "批准", "驳回"]),
    ("pending_review", "manager", "待复核", ["批准", "驳回", "撤回提交"]),
    ("rejected", "manager", "已驳回", ["修改为草稿", "重新提交"]),
    ("approved", "partner", "已批准", ["撤回复核"]),
])
async def test_allowed_actions_panel_shows_dict_wording(
    monkeypatch, status, role, expected_status, expected_actions,
) -> None:
    """面板实际收到的文字（经 compute_allowed_actions），守卫条件查询换成全部满足（只看文字）。"""

    async def _guards(*_args, **_kwargs):
        return {"no_pending_ai_content": True, "not_archived": True, "no_unresolved_conflict": True}

    monkeypatch.setattr(allowed_actions_service, "_evaluate_guards", _guards)
    result = await allowed_actions_service.compute_allowed_actions(
        None, module="adjustment", instance_id=uuid.uuid4(), current_status=status,
        user_role=role, project_id=uuid.uuid4(),
    )
    assert result["current_status_zh"] == expected_status
    assert [a["label_zh"] for a in result["allowed"]] == expected_actions


def test_consol_elimination_keeps_approval_wording_and_shares_rejected() -> None:
    sheet = consol_elimination_sheet_service.STATUS_LABELS
    service = {status.value: label for status, label in elimination_service._STATUS_LABELS.items()}
    assert sheet == service, "抵销分录两处状态名不一致"
    assert (sheet["pending_review"], sheet["approved"]) == ("待审批", "已审批")
    assert sheet["rejected"] == DICT["rejected"] == "已驳回"
