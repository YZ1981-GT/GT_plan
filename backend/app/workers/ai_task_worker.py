"""耐久 AI 批任务 worker：DB 认领、租约围栏、逐项事务和重启恢复。"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import os
import socket
from typing import Any
from uuid import uuid4

from app.services.ai_task_job_service import (
    AiTaskClaim,
    canonical_hash,
    claim_next,
    finish_failure,
    finish_success,
    renew_lease,
)

logger = logging.getLogger(__name__)
_WAKE = asyncio.Event()


def wake() -> None:
    _WAKE.set()


def _worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"


class AiTaskTargetStale(ValueError):
    """目标在生成期间被修改，旧结果不得形成可采纳产物。"""


async def _verify_target_baseline(db, claim: AiTaskClaim) -> None:
    """按创建任务时的版本/hash复核目标；执行前后各调用一次。"""
    import sqlalchemy as sa

    if claim.target_type == "note_section":
        from app.models.report_models import DisclosureNote

        row = (await db.execute(sa.select(
            DisclosureNote.updated_at,
            DisclosureNote.text_content,
            DisclosureNote.is_local_override,
        ).where(
            DisclosureNote.id == claim.target_id,
            DisclosureNote.project_id == claim.project_id,
            DisclosureNote.year == claim.year,
            DisclosureNote.is_deleted == sa.false(),
        ))).first()
        if row is None:
            raise AiTaskTargetStale("目标附注不存在或已删除")
        current_version = str(row.updated_at or "")
        current_hash = hashlib.sha256((row.text_content or "").encode("utf-8")).hexdigest()
        if row.is_local_override:
            raise AiTaskTargetStale("目标附注已由人工改写，请重新发起")
    elif claim.target_type == "workpaper":
        from app.models.workpaper_models import WorkingPaper

        row = (await db.execute(sa.select(
            WorkingPaper.content_revision,
            WorkingPaper.current_content_version_id,
            WorkingPaper.updated_at,
        ).where(
            WorkingPaper.id == claim.target_id,
            WorkingPaper.project_id == claim.project_id,
            WorkingPaper.is_deleted == sa.false(),
        ))).first()
        if row is None:
            raise AiTaskTargetStale("目标底稿不存在或已删除")
        current_version = str(int(row.content_revision or 0))
        current_hash = canonical_hash({
            "content_revision": int(row.content_revision or 0),
            "content_version_id": (
                str(row.current_content_version_id)
                if row.current_content_version_id else None
            ),
            "updated_at": str(row.updated_at or ""),
        })
    else:
        raise ValueError(f"未知 AI 批任务目标类型：{claim.target_type}")

    if claim.baseline_version is not None and current_version != claim.baseline_version:
        raise AiTaskTargetStale("目标版本已变化，请重新发起")
    if claim.before_hash is not None and current_hash != claim.before_hash:
        raise AiTaskTargetStale("目标内容已变化，请重新发起")


async def _renew_claim_loop(
    claim: AiTaskClaim,
    *,
    session_factory,
    stop: asyncio.Event,
    lost: asyncio.Event,
) -> None:
    """长模型调用期间续租；取消或重领后置 lost，由完成围栏回滚业务产物。"""
    interval = max(0.5, min(60.0, claim.lease_seconds / 3))
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
            return
        except TimeoutError:
            pass
        try:
            async with session_factory() as db:
                won = await renew_lease(
                    db, claim, lease_seconds=claim.lease_seconds
                )
                if won:
                    await db.commit()
                else:
                    await db.rollback()
                    lost.set()
                    return
        except Exception:
            # 临时数据库错误不立刻宣布丢租约；最终 finish CAS 仍是权威围栏。
            logger.warning("AI task item %s 续租失败", claim.item_id, exc_info=True)


async def _process_note(db, claim: AiTaskClaim) -> tuple[dict[str, Any], Any]:
    from app.models.core import User
    from app.services import doc_chat_persistence
    from app.services.ai_chat.contracts import HostType
    from app.services.llm_route import served_model_label
    from app.services.note_knowledge_enricher import NoteKnowledgeEnricher

    user = await db.get(User, claim.actor_id)
    if user is None:
        raise RuntimeError("任务发起人不存在")
    section = claim.target_key or str(claim.request_payload.get("note_section") or "")
    draft = await NoteKnowledgeEnricher(db).generate_note_text(
        claim.project_id,
        claim.year,
        section,
        str(claim.request_payload.get("section_title") or section),
        str(claim.request_payload.get("account_name") or ""),
        account_code=claim.request_payload.get("account_code"),
        audit_area=claim.request_payload.get("audit_area"),
        user=user,
        doc_filter=claim.request_payload.get("doc_filter"),
    )
    if not draft.text:
        raise ValueError("没有生成可供采纳的附注草稿")
    session = await doc_chat_persistence.get_or_create_session(
        db, HostType.note.value, str(claim.target_id), claim.actor_id,
        claim.project_id, audit_year=claim.year,
    )
    message = await doc_chat_persistence.append_message(
        db,
        session,
        "assistant",
        draft.text,
        context_manifest={
            "task_code": "note.policy_draft",
            "generation_id": str(claim.generation_id),
            "job_id": str(claim.job_id),
        },
        model_used=served_model_label(),
    )
    citations = [
        {
            "source_id": str(getattr(c, "source_id", "")),
            "document_name": getattr(c, "document_name", None),
            "folder_path": getattr(c, "folder_path", None),
            "is_stale": bool(getattr(c, "is_stale", False)),
        }
        for c in draft.citations
    ]
    return {
        "generation_id": str(claim.generation_id),
        "message_id": str(message.id),
        "note_section": section,
        "status": "generated",
        "text_preview": draft.text[:200],
        "citations": citations,
    }, message.id


async def _process_review(db, claim: AiTaskClaim) -> tuple[dict[str, Any], None]:
    from app.models.core import User
    from app.services.ai_review_artifact import persist_review_findings
    from app.services.batch_review_service import BatchReviewService

    user = await db.get(User, claim.actor_id)
    if user is None:
        raise RuntimeError("任务发起人不存在")
    role = getattr(getattr(user, "role", None), "value", getattr(user, "role", None))
    result = await BatchReviewService()._review_single_sheet(
        {
            "wp_id": str(claim.target_id),
            "wp_code": str(claim.request_payload.get("wp_code") or claim.target_key or "WP"),
            "sheet_name": str(claim.request_payload.get("sheet_name") or claim.target_key or "底稿"),
        },
        str(claim.job_id),
        "unknown",
        str(role) if role is not None else None,
    )
    if result.pass_status in {"review_error", "manual_review_required"} and result.error_message:
        raise RuntimeError(result.error_message)
    persisted_findings = await persist_review_findings(
        db,
        project_id=claim.project_id,
        workpaper_id=claim.target_id,
        job_id=claim.job_id,
        generation_id=claim.generation_id,
        wp_code=result.wp_code,
        sheet_name=result.sheet_name,
        model_used=result.model_used,
        prompt_source=result.prompt_source,
        findings=result.findings,
    )
    return {
        "generation_id": str(claim.generation_id),
        "wp_id": result.wp_id,
        "wp_code": result.wp_code,
        "sheet_name": result.sheet_name,
        "review_status": result.pass_status,
        "model_used": result.model_used,
        "reviewed_at": result.reviewed_at,
        "prompt_source": result.prompt_source,
        "findings": persisted_findings,
        "deterministic_checks": result.deterministic_checks,
        "risk_summary": result.risk_summary,
        "error_message": result.error_message,
    }, None


def _broadcast_job_update(claim: AiTaskClaim, item_status: str) -> None:
    """发轻量进度提示；DB snapshot 始终是断线恢复后的权威状态。"""
    try:
        from app.services.event_bus import event_bus

        event_bus.broadcast_raw("ai.task.updated", {
            "project_id": str(claim.project_id),
            "year": claim.year,
            "job_id": str(claim.job_id),
            "item_id": str(claim.item_id),
            "item_status": item_status,
        })
    except Exception:
        logger.debug("AI task 进度事件发送失败", exc_info=True)


async def process_claim(claim: AiTaskClaim, *, session_factory=None) -> str:
    if session_factory is None:
        from app.core.database import async_session
        session_factory = async_session

    stop_renewal = asyncio.Event()
    lease_lost = asyncio.Event()
    renewal = asyncio.create_task(_renew_claim_loop(
        claim,
        session_factory=session_factory,
        stop=stop_renewal,
        lost=lease_lost,
    ))
    try:
        async with session_factory() as db:
            await _verify_target_baseline(db, claim)
            if claim.task_kind == "note_batch_prefill":
                summary, message_id = await _process_note(db, claim)
            elif claim.task_kind == "workpaper_batch_review":
                summary, message_id = await _process_review(db, claim)
            else:
                raise ValueError(f"未知 AI 批任务类型：{claim.task_kind}")
            # 生成期间目标被改动时，连同本事务里的 message/finding 一起回滚。
            await _verify_target_baseline(db, claim)
            if lease_lost.is_set():
                await db.rollback()
                return "stale"
            won = await finish_success(
                db, claim, result_summary=summary, message_id=message_id
            )
            if not won:
                # 迟到 claimant、运行中取消都不得提交孤儿业务产物。
                await db.rollback()
                return "stale"
            await db.commit()
        _broadcast_job_update(claim, "succeeded")
        return "succeeded"
    except Exception as exc:  # noqa: BLE001
        retryable = not isinstance(exc, (ValueError, AiTaskTargetStale))
        error_code = "target_stale" if isinstance(exc, AiTaskTargetStale) else "item_execution_failed"
        async with session_factory() as db:
            won = await finish_failure(
                db, claim,
                error_code=error_code,
                error_message=str(exc) or type(exc).__name__,
                retryable=retryable,
            )
            if won:
                await db.commit()
            else:
                await db.rollback()
        if not won:
            return "stale"
        status = "retry_wait" if retryable and claim.attempt < claim.max_attempts else "failed"
        _broadcast_job_update(claim, status)
        logger.warning("AI task item %s 第 %d 次失败：%s", claim.item_id, claim.attempt, exc)
        return status
    finally:
        stop_renewal.set()
        with contextlib.suppress(asyncio.CancelledError):
            await renewal


async def drain(*, limit: int = 10, worker_id: str | None = None) -> int:
    from app.core.database import async_session

    worker = worker_id or _worker_id()
    lease_seconds = max(30, int(os.getenv("AI_TASK_LEASE_SECONDS", "300")))
    processed = 0
    for _ in range(max(1, limit)):
        async with async_session() as db:
            claim = await claim_next(
                db, worker_id=worker, lease_seconds=lease_seconds
            )
            await db.commit()
        if claim is None:
            break
        await process_claim(claim)
        processed += 1
    return processed


async def run(stop_event: asyncio.Event) -> None:
    if os.getenv("AI_TASK_WORKER_ENABLED", "1").lower() in {"0", "false", "no"}:
        return
    poll = max(0.5, float(os.getenv("AI_TASK_WORKER_POLL_SECONDS", "3")))
    worker = _worker_id()
    from app.workers.worker_helpers import write_heartbeat

    while not stop_event.is_set():
        try:
            await write_heartbeat("ai_task_worker", version="1.0")
            await drain(limit=10, worker_id=worker)
        except Exception:
            logger.exception("AI task worker 本轮执行失败")
        _WAKE.clear()
        wake_wait = asyncio.create_task(_WAKE.wait())
        stop_wait = asyncio.create_task(stop_event.wait())
        done, pending = await asyncio.wait(
            {wake_wait, stop_wait}, timeout=poll,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        if stop_wait in done and stop_event.is_set():
            return

#: 注册到统一唤醒表：业务域只调 `wake_worker("ai_task_worker")`，不 import 本模块
#: （🔴 2026-11-14 解 domain-boundary 的 `<domain> -> backend-workers` 反向依赖）。
from app.core.worker_wakeup import register_waker as _register_waker  # noqa: E402

_register_waker("ai_task_worker", wake)
