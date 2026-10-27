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

from app.routers.system_dicts import _DICTS
from app.services import allowed_actions_service, consol_elimination_sheet_service, elimination_service
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


@pytest.mark.parametrize(("status", "role", "expected_status", "expected_actions"), [
    ("draft", "editor", "草稿", ["提交复核"]),
    ("pending_review", "manager", "待复核", ["批准", "驳回"]),
    ("rejected", "manager", "已驳回", ["重新提交"]),
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
