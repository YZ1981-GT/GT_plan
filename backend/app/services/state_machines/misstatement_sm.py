"""错报状态机定义 — V3 收官增强 Req 10"""

from app.services.state_machines.base import StateMachine, Transition

MISSTATEMENT_SM = StateMachine(
    name="misstatement",
    states=["draft", "confirmed", "corrected", "waived"],
    transitions=[
        Transition(
            from_="draft", action="confirm", to="confirmed",
            role_required={"editor", "manager", "admin"},
        ),
        Transition(
            from_="confirmed", action="correct", to="corrected",
            role_required={"editor", "manager"},
        ),
        Transition(
            from_="confirmed", action="waive", to="waived",
            role_required={"manager", "partner"},
        ),
        Transition(
            from_="corrected", action="reopen", to="confirmed",
            role_required={"manager", "partner"},
        ),
        Transition(
            from_="waived", action="reopen", to="confirmed",
            role_required={"manager", "partner"},
        ),
    ],
    action_labels_zh={
        "confirm": "确认错报",
        "correct": "标记已更正",
        "waive": "豁免",
        "reopen": "重新打开",
    },
    status_labels_zh={
        "draft": "草稿",
        "confirmed": "已确认",
        "corrected": "已更正",
        "waived": "已豁免",
    },
)
