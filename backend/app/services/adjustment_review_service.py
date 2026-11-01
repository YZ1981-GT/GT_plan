"""调整分录提交复核 / 撤回提交 / 批量复核（spec adjustment-hall-entry-review-closure 需求 4.1~4.4）。

状态迁移仍由 ``AdjustmentService.change_review_status`` 执行；本模块负责持久化复核任务、
指定复核人授权、职责分离、批量逐笔保存点和通知。service 只 flush 不 commit，
由路由统一提交（任务、通知与状态变更同一事务）。
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
from app.services.adjustment_review_coordinator import AdjustmentReviewCoordinator
from app.services import adjustment_review_task_service as review_tasks

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

    svc = AdjustmentService(db)
    risks: dict[str, dict[str, Any]] = {}
    for group_id in dict.fromkeys(group_ids):
        rows = await svc._get_group_rows(project_id, group_id)
        if not rows:
            continue
        from app.services.adjustment_risk_projection import project_adjustment_risk
        risks[str(group_id)] = await project_adjustment_risk(
            db, project_id=project_id, year=int(rows[0].year), rows=rows,
        )
    if any(risk["required_level"] == "partner" for risk in risks.values()):
        partner_ids = {
            candidate["user_id"] for candidate in candidates
            if candidate.get("system_role") in {"admin", "partner"}
            or candidate.get("project_role") in {"partner", "signing_partner"}
        }
        chosen = [reviewer for reviewer in chosen if reviewer in partner_ids]
        if not chosen:
            raise ReviewFlowError(
                "PARTNER_REVIEWER_REQUIRED",
                "所选分录达到执行重要性或命中高风险事项，请指定项目合伙人复核",
            )
    chosen = [reviewer for reviewer in chosen if reviewer != str(actor.id)]
    if not chosen:
        raise ReviewFlowError(
            "NO_REVIEWER",
            "本项目没有其他可接收任务的复核人，请先在项目团队中委派项目经理或合伙人",
        )
    done, failed = await _transition_each(
        db, project_id, group_ids,
        allowed_from={ReviewStatus.draft, ReviewStatus.rejected},
        blocked_reason="不能提交复核",
        make_change=lambda _gid: ReviewStatusChange(status=ReviewStatus.pending_review),
        actor_id=actor.id,
    )
    for info in done:
        try:
            rows = await svc._get_group_rows(project_id, UUID(info["entry_group_id"]))
            risk = risks.get(info["entry_group_id"], {"required_level": "manager"})
            task = await review_tasks.create_task(
                db,
                project_id=project_id,
                year=int(info["year"]),
                rows=rows,
                reviewer_ids=chosen,
                submitted_by=actor.id,
                note=note,
                required_level=risk["required_level"],
            )
            info["review_task_id"] = str(task.id)
            info["review_task_revision"] = task.revision
            info["risk"] = risk
        except review_tasks.AdjustmentReviewTaskError as exc:
            raise ReviewFlowError(exc.code, str(exc), exc.detail) from exc

    notified = await notify.notify_status_change(
        db, project_id, done, actor_id=actor.id, actor_name=await _actor_name(db, actor),
        reviewer_ids=chosen, note=(note or "").strip() or None,
    )
    warning = None
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
    try:
        await review_tasks.withdraw_task(
            db,
            project_id=project_id,
            entry_group_id=group_id,
            actor_id=actor.id,
        )
    except review_tasks.AdjustmentReviewTaskError as exc:
        raise ReviewFlowError(exc.code, str(exc), exc.detail) from exc
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
    """批量通过 / 驳回有效复核任务，逐笔保存点隔离并合并通知。"""
    if status not in (ReviewStatus.approved, ReviewStatus.rejected):
        raise ReviewFlowError("INVALID_STATUS", "批量复核只能通过或驳回")
    reasons = {str(k): (v or "").strip() for k, v in (reasons or {}).items()}
    default_reason = (reason or "").strip()
    svc = AdjustmentService(db)
    coordinator = AdjustmentReviewCoordinator(db)
    done: list[dict] = []
    failed: list[dict] = []

    for gid in dict.fromkeys(group_ids):
        rows = await svc._get_group_rows(project_id, gid)
        adj_no = rows[0].adjustment_no if rows else None
        if not rows:
            failed.append({"entry_group_id": str(gid), "adjustment_no": None, "reason": "分录不存在或已删除"})
            continue
        if rows[0].review_status != ReviewStatus.pending_review:
            failed.append({
                "entry_group_id": str(gid),
                "adjustment_no": adj_no,
                "reason": f"当前为「{_STATUS_LABEL.get(rows[0].review_status, rows[0].review_status)}」，请先提交复核",
            })
            continue
        decision_reason = reasons.get(str(gid)) or default_reason
        if status == ReviewStatus.rejected and not decision_reason:
            failed.append({"entry_group_id": str(gid), "adjustment_no": adj_no, "reason": "驳回必须填写原因"})
            continue
        try:
            async with db.begin_nested():
                decision = await coordinator.decide(
                    project_id=project_id,
                    entry_group_id=gid,
                    status=status,
                    actor=actor,
                    reason=decision_reason or None,
                )
                info = decision.info
            done.append(info)
        except Exception as exc:  # noqa: BLE001 — 每笔保存点隔离，核心失败不得批准
            failed.append({
                "entry_group_id": str(gid),
                "adjustment_no": adj_no,
                "reason": str(exc),
                "error_code": getattr(exc, "code", None),
            })

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
