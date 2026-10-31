"""调整分录提交复核 / 撤回提交 / 批量复核（spec adjustment-hall-entry-review-closure 需求 4.1~4.4）。

状态迁移仍由 ``AdjustmentService.change_review_status`` 执行（含 @audit_log 留痕）；本模块负责
批量逐笔处理（每笔一个 SAVEPOINT，一笔失败不影响其余）、友好的拒绝原因与通知。
service 只 flush 不 commit，由路由统一提交（通知与状态变更同一事务）。
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_models import ReviewStatus
from app.models.audit_platform_schemas import ReviewStatusChange
from app.services import adjustment_hall_notify as notify
from app.services.adjustment_service import AdjustmentService

_STATUS_LABEL = {
    ReviewStatus.draft: "草稿",
    ReviewStatus.pending_review: "待复核",
    ReviewStatus.approved: "已批准",
    ReviewStatus.rejected: "已驳回",
}


class ReviewFlowError(ValueError):
    """复核流转业务错误（携错误码供路由转 4xx）。"""

    def __init__(self, code: str, message: str, detail: Any = None):
        super().__init__(message)
        self.code = code
        self.detail = detail


async def _actor_name(db: AsyncSession, actor: Any) -> str:
    names = await notify.display_names(db, [actor.id])
    return names.get(str(actor.id)) or getattr(actor, "username", "") or "有人"


async def _transition_each(
    db: AsyncSession,
    project_id: UUID,
    group_ids: Sequence[UUID],
    *,
    allowed_from: set[ReviewStatus],
    blocked_reason: str,
    make_change,
    actor_id: UUID,
    **status_kwargs: Any,
) -> tuple[list[dict], list[dict]]:
    """逐笔迁移状态：每笔独立 SAVEPOINT，返回 (成功的影响范围, 失败原因)。"""
    svc = AdjustmentService(db)
    done: list[dict] = []
    failed: list[dict] = []
    for gid in dict.fromkeys(group_ids):
        rows = await svc._get_group_rows(project_id, gid)
        if not rows:
            failed.append({"entry_group_id": str(gid), "adjustment_no": None, "reason": "分录不存在或已删除"})
            continue
        # 先取成标量：保存点回滚会让本笔 ORM 行过期，之后再读属性会触发异步懒加载
        adj_no, current = rows[0].adjustment_no, rows[0].review_status
        if current not in allowed_from:
            failed.append({
                "entry_group_id": str(gid), "adjustment_no": adj_no,
                "reason": f"当前为「{_STATUS_LABEL.get(current, current)}」，{blocked_reason}",
            })
            continue
        change = make_change(str(gid))
        if change is None:
            failed.append({"entry_group_id": str(gid), "adjustment_no": adj_no, "reason": "驳回必须填写原因"})
            continue
        try:
            async with db.begin_nested():
                info = await svc.change_review_status(project_id, gid, change, actor_id, **status_kwargs)
        except ValueError as exc:
            failed.append({"entry_group_id": str(gid), "adjustment_no": adj_no, "reason": str(exc)})
            continue
        if change.reason:
            info["reason"] = change.reason
        done.append(info)
    return done, failed


async def submit_for_review(
    db: AsyncSession,
    project_id: UUID,
    *,
    group_ids: Sequence[UUID],
    actor: Any,
    reviewer_ids: Sequence[UUID] | None = None,
    note: str | None = None,
) -> dict:
    """草稿 / 已驳回 → 待复核，并通知所选复核人（未选则通知全部候选）。"""
    candidates = await notify.review_candidates(db, project_id)
    candidate_ids = {c["user_id"] for c in candidates}
    if reviewer_ids:
        chosen = list(dict.fromkeys(str(r) for r in reviewer_ids))
        invalid = [r for r in chosen if r not in candidate_ids]
        if invalid:
            raise ReviewFlowError("INVALID_REVIEWER", "所选复核人不是本项目有复核权限的成员", {"user_ids": invalid})
    else:
        chosen = [c["user_id"] for c in candidates]
    done, failed = await _transition_each(
        db, project_id, group_ids,
        allowed_from={ReviewStatus.draft, ReviewStatus.rejected},
        blocked_reason="不能提交复核",
        make_change=lambda _gid: ReviewStatusChange(status=ReviewStatus.pending_review),
        actor_id=actor.id,
    )
    notified = await notify.notify_status_change(
        db, project_id, done, actor_id=actor.id, actor_name=await _actor_name(db, actor),
        reviewer_ids=chosen, note=(note or "").strip() or None,
    )
    warning = None
    if done and not [r for r in chosen if r != str(actor.id)]:
        warning = "本项目没有其他有复核权限的成员，未发送通知；请在项目团队中委派项目经理或合伙人"
    return {"succeeded": done, "failed": failed, "notified": notified, "warning": warning}


async def withdraw_submission(db: AsyncSession, project_id: UUID, group_id: UUID, *, actor: Any) -> dict:
    """待复核 → 草稿（撤回提交，不通知）。"""
    done, failed = await _transition_each(
        db, project_id, [group_id],
        allowed_from={ReviewStatus.pending_review},
        blocked_reason="只有待复核的分录可以撤回提交",
        make_change=lambda _gid: ReviewStatusChange(status=ReviewStatus.draft),
        actor_id=actor.id,
        allow_withdraw=True,
    )
    if failed:
        raise ReviewFlowError("WITHDRAW_BLOCKED", failed[0]["reason"], failed[0])
    return done[0]


async def review_groups(
    db: AsyncSession,
    project_id: UUID,
    *,
    group_ids: Sequence[UUID],
    status: ReviewStatus,
    actor: Any,
    reason: str | None = None,
    reasons: dict[str, str] | None = None,
) -> dict:
    """批量通过 / 驳回（草稿或待复核），逐笔结果 + 合并通知。"""
    if status not in (ReviewStatus.approved, ReviewStatus.rejected):
        raise ReviewFlowError("INVALID_STATUS", "批量复核只能通过或驳回")
    reasons = {str(k): (v or "").strip() for k, v in (reasons or {}).items()}
    default_reason = (reason or "").strip()

    def _change(gid: str) -> ReviewStatusChange | None:
        if status == ReviewStatus.approved:
            return ReviewStatusChange(status=status)
        text = reasons.get(gid) or default_reason
        return ReviewStatusChange(status=status, reason=text) if text else None

    done, failed = await _transition_each(
        db, project_id, group_ids,
        allowed_from={ReviewStatus.draft, ReviewStatus.pending_review},
        blocked_reason="只有草稿或待复核的分录可以通过 / 驳回",
        make_change=_change,
        actor_id=actor.id,
    )
    notified = await notify.notify_status_change(
        db, project_id, done, actor_id=actor.id, actor_name=await _actor_name(db, actor),
    )
    return {"succeeded": done, "failed": failed, "notified": notified}


async def notify_single_change(db: AsyncSession, project_id: UUID, info: dict, *, actor: Any, reason: str | None = None) -> list[dict]:
    """单笔 /review、/revoke-review 端点的通知（与批量同一套规则）。"""
    if reason:
        info = {**info, "reason": reason}
    return await notify.notify_status_change(
        db, project_id, [info], actor_id=actor.id, actor_name=await _actor_name(db, actor),
    )
