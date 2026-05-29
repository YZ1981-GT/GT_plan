"""附注状态机定义 — V3 收官增强 Req 10"""

from app.services.state_machines.base import StateMachine, Transition

DISCLOSURE_SM = StateMachine(
    name="disclosure",
    states=["draft", "filling", "reviewing", "approved", "locked"],
    transitions=[
        Transition(
            from_="draft", action="start_fill", to="filling",
            role_required={"editor", "manager", "admin"},
        ),
        Transition(
            from_="filling", action="submit_review", to="reviewing",
            role_required={"editor", "manager"},
            guards=["no_pending_ai_content"],
        ),
        Transition(
            from_="reviewing", action="approve", to="approved",
            role_required={"manager", "partner"},
        ),
        Transition(
            from_="reviewing", action="reject", to="filling",
            role_required={"manager", "partner"},
        ),
        Transition(
            from_="approved", action="lock", to="locked",
            role_required={"partner", "admin"},
        ),
    ],
    action_labels_zh={
        "start_fill": "开始填写",
        "submit_review": "提交复核",
        "approve": "批准",
        "reject": "退回",
        "lock": "锁定",
    },
    status_labels_zh={
        "draft": "草稿",
        "filling": "填写中",
        "reviewing": "复核中",
        "approved": "已批准",
        "locked": "已锁定",
    },
)
