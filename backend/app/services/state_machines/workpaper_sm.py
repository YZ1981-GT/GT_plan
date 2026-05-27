"""底稿状态机定义 — V3 收官增强 Req 10"""

from app.services.state_machines.base import StateMachine, Transition

WORKPAPER_SM = StateMachine(
    name="workpaper",
    states=["draft", "pending_review", "under_review", "review_passed", "rejected", "archived"],
    transitions=[
        Transition(
            from_="draft", action="submit", to="pending_review",
            role_required={"editor", "manager", "admin"},
            guards=["no_pending_ai_content", "no_unresolved_conflict"],
        ),
        Transition(
            from_="pending_review", action="start_review", to="under_review",
            role_required={"manager", "qc", "partner"},
        ),
        Transition(
            from_="under_review", action="approve", to="review_passed",
            role_required={"manager", "partner"},
        ),
        Transition(
            from_="under_review", action="reject", to="rejected",
            role_required={"manager", "partner"},
        ),
        Transition(
            from_="rejected", action="resubmit", to="pending_review",
            role_required={"editor", "manager"},
            guards=["no_pending_ai_content", "no_unresolved_conflict"],
        ),
        Transition(
            from_="review_passed", action="archive", to="archived",
            role_required={"partner", "admin"},
            guards=["no_pending_ai_content", "no_unresolved_conflict"],
        ),
    ],
    action_labels_zh={
        "submit": "提交复核",
        "start_review": "开始复核",
        "approve": "通过",
        "reject": "退回",
        "resubmit": "重新提交",
        "archive": "归档",
    },
    status_labels_zh={
        "draft": "草稿",
        "pending_review": "待复核",
        "under_review": "复核中",
        "review_passed": "复核通过",
        "rejected": "已退回",
        "archived": "已归档",
    },
)
