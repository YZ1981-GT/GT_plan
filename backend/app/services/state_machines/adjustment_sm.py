"""调整分录可解释状态机。

本定义只解释当前生产可达的四态。草稿直批/直驳是复核任务落地前的
过渡兼容边；后续生产门禁止该入口时，须与服务转换表同批删除。
"""

from app.services.state_machines.base import StateMachine, Transition

_EDIT_ROLES = {"editor", "auditor", "qc", "manager", "partner", "admin"}
_REVIEW_ROLES = {"manager", "partner", "admin"}

ADJUSTMENT_SM = StateMachine(
    name="adjustment",
    states=["draft", "pending_review", "approved", "rejected"],
    transitions=[
        Transition(
            from_="draft", action="submit", to="pending_review",
            role_required=_EDIT_ROLES,
            guards=["no_pending_ai_content"],
        ),
        # 当前生产兼容：review/review-batch 尚允许草稿直批、直驳。
        Transition(
            from_="draft", action="approve", to="approved",
            role_required=_REVIEW_ROLES,
        ),
        Transition(
            from_="draft", action="reject", to="rejected",
            role_required=_REVIEW_ROLES,
        ),
        Transition(
            from_="pending_review", action="approve", to="approved",
            role_required=_REVIEW_ROLES,
        ),
        Transition(
            from_="pending_review", action="reject", to="rejected",
            role_required=_REVIEW_ROLES,
        ),
        Transition(
            from_="pending_review", action="withdraw", to="draft",
            role_required=_EDIT_ROLES,
        ),
        Transition(
            from_="rejected", action="revise", to="draft",
            role_required=_EDIT_ROLES,
        ),
        Transition(
            from_="rejected", action="resubmit", to="pending_review",
            role_required=_EDIT_ROLES,
            guards=["no_pending_ai_content"],
        ),
        Transition(
            from_="approved", action="revoke", to="draft",
            role_required=_REVIEW_ROLES,
        ),
    ],
    action_labels_zh={
        "submit": "提交复核",
        "approve": "批准",
        "reject": "驳回",
        "withdraw": "撤回提交",
        "revise": "修改为草稿",
        "resubmit": "重新提交",
        "revoke": "撤回复核",
    },
    status_labels_zh={
        "draft": "草稿",
        "pending_review": "待复核",
        "approved": "已批准",
        "rejected": "已驳回",
    },
)
