"""调整分录状态机定义 — V3 收官增强 Req 10"""

from app.services.state_machines.base import StateMachine, Transition

ADJUSTMENT_SM = StateMachine(
    name="adjustment",
    states=["draft", "pending_review", "approved", "rejected", "posted"],
    transitions=[
        Transition(
            from_="draft", action="submit", to="pending_review",
            role_required={"editor", "manager", "admin"},
            guards=["no_pending_ai_content"],
        ),
        Transition(
            from_="pending_review", action="approve", to="approved",
            role_required={"manager", "partner"},
        ),
        Transition(
            from_="pending_review", action="reject", to="rejected",
            role_required={"manager", "partner"},
        ),
        Transition(
            from_="rejected", action="resubmit", to="pending_review",
            role_required={"editor", "manager"},
        ),
        Transition(
            from_="approved", action="post", to="posted",
            role_required={"manager", "partner", "admin"},
        ),
    ],
    # 状态与动作用语与系统字典「调整分录状态」、调整分录页同一套（草稿 / 待复核 / 已批准 / 已驳回）。原先这里写
    # 「待审批 / 已退回」「提交审批 / 退回」，可解释状态机面板与调整分录页对同一条分录叫法不同
    # （spec consol-autotree-residual-closure R4；守卫 test_adjustment_status_labels.py 直比字典）。
    action_labels_zh={
        "submit": "提交复核",
        "approve": "批准",
        "reject": "驳回",
        "resubmit": "重新提交",
        "post": "过账",
    },
    status_labels_zh={
        "draft": "草稿",
        "pending_review": "待复核",
        "approved": "已批准",
        "rejected": "已驳回",
        "posted": "已过账",
    },
)
