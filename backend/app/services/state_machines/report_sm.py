"""报表状态机定义 — V3 收官增强 Req 10"""

from app.services.state_machines.base import StateMachine, Transition

REPORT_SM = StateMachine(
    name="report",
    states=["draft", "generating", "generated", "reviewing", "approved", "signed"],
    transitions=[
        Transition(
            from_="draft", action="generate", to="generating",
            role_required={"editor", "manager", "admin"},
        ),
        Transition(
            from_="generating", action="complete_gen", to="generated",
            role_required={"editor", "manager", "admin"},
        ),
        Transition(
            from_="generated", action="submit_review", to="reviewing",
            role_required={"editor", "manager"},
            guards=["no_pending_ai_content", "no_unresolved_conflict"],
        ),
        Transition(
            from_="reviewing", action="approve", to="approved",
            role_required={"manager", "partner"},
        ),
        Transition(
            from_="reviewing", action="reject", to="generated",
            role_required={"manager", "partner"},
        ),
        Transition(
            from_="approved", action="sign", to="signed",
            role_required={"partner"},
        ),
    ],
    action_labels_zh={
        "generate": "生成报表",
        "complete_gen": "完成生成",
        "submit_review": "提交复核",
        "approve": "批准",
        "reject": "退回",
        "sign": "签发",
    },
    status_labels_zh={
        "draft": "草稿",
        "generating": "生成中",
        "generated": "已生成",
        "reviewing": "复核中",
        "approved": "已批准",
        "signed": "已签发",
    },
)
