"""既有 ``ai_content_log`` 上的 DraftArtifact facade。

AIChatMessage 证明“模型说了什么”；本 facade 证明“基于哪个业务版本，准备把什么
写到哪里”，并在人工确认时执行目标 CAS。所有函数只 flush，由 router 统一 commit。
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import assert_project_permission, check_consol_lock
from app.models.core import User
from app.models.report_models import DisclosureNote
from app.models.v3_refinement_models import AiContentLog
from app.services import ai_content_log_service
from app.services.audit_log_helper import append_audit_log


class DraftArtifactStale(ValueError):
    pass


class DraftArtifactConflict(ValueError):
    pass


def text_hash(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


def _version(note: DisclosureNote) -> str:
    return note.updated_at.isoformat() if note.updated_at else ""


def _proposed(
    before: str,
    fragment: str,
    operation: str,
    replace_fragment: str | None = None,
) -> str:
    if operation == "replace":
        return fragment.strip()
    if operation == "replace_fragment":
        if not replace_fragment or before.count(replace_fragment) != 1:
            raise DraftArtifactConflict("待改写原文在已保存附注中不存在或不唯一，请先保存并重新选择")
        return before.replace(replace_fragment, fragment.strip(), 1)
    separator = "\n\n---\n\n" if before.strip() else ""
    return before + separator + fragment.strip()


def serialize_artifact(log: AiContentLog) -> dict[str, Any]:
    fragment = log.revised_content if log.revised_content is not None else log.generated_content
    locator = dict(log.target_locator or {})
    operation = str(locator.get("operation") or "append")
    proposed = _proposed(
        log.before_content or "",
        fragment or "",
        operation,
        locator.get("replace_fragment"),
    )
    return {
        "id": str(log.id),
        "ai_content_log_id": str(log.id),
        "generation_id": str(log.generation_id) if log.generation_id else None,
        "source_message_id": str(log.source_message_id) if log.source_message_id else None,
        "task_code": log.task_code,
        "prompt_version": log.prompt_version,
        "instance_type": (log.target_locator or {}).get("type"),
        "target_cell": log.target_cell,
        "target_position": (log.target_locator or {}).get("field"),
        "target_locator": log.target_locator,
        "model": log.model,
        "confidence": float(log.confidence) if log.confidence is not None else None,
        "generated_at": log.generated_at.isoformat() if log.generated_at else None,
        "content": fragment,
        "before_content": log.before_content,
        "proposed_content": proposed,
        "before_hash": log.before_hash,
        "proposed_hash": text_hash(proposed),
        "baseline_version": log.baseline_version,
        "applied_version": log.applied_version,
        "applied_hash": log.applied_hash,
        "preview_diff": log.preview_diff,
        "artifact_version": int(log.artifact_version or 0),
        "writeback_status": log.writeback_status,
        "confirm_action": log.confirm_action,
        "is_stale": bool(log.is_stale),
        "stale_reason": log.stale_reason,
        "can_undo": log.writeback_status == "applied",
    }


async def prepare_note_artifact(
    db: AsyncSession,
    *,
    project_id: UUID,
    user_id: UUID,
    note_id: UUID,
    content: str,
    model: str,
    source_message_id: UUID | None = None,
    generation_id: UUID | None = None,
    task_code: str = "chat.general",
    prompt_hash: str | None = None,
    prompt_version: str | None = None,
    context_manifest: dict[str, Any] | None = None,
    operation: str = "append",
    replace_fragment: str | None = None,
) -> AiContentLog:
    """服务端读取当前附注并形成待确认 diff；不修改附注正文。"""
    if operation not in {"append", "replace", "replace_fragment"}:
        raise ValueError("附注草稿只支持 append/replace/replace_fragment")
    if not content or not content.strip():
        raise ValueError("AI 草稿为空")
    note = (await db.execute(sa.select(DisclosureNote).where(
        DisclosureNote.id == note_id,
        DisclosureNote.project_id == project_id,
        DisclosureNote.is_deleted == sa.false(),
    ))).scalar_one_or_none()
    if note is None:
        raise DraftArtifactConflict("附注不存在或不属于当前项目")

    if source_message_id is not None:
        existing = (await db.execute(sa.select(AiContentLog).where(
            AiContentLog.project_id == project_id,
            AiContentLog.source_message_id == source_message_id,
            AiContentLog.target_cell.like(f"note:{note_id}:%"),
        ).order_by(AiContentLog.generated_at.desc()).limit(1))).scalar_one_or_none()
        if existing is not None:
            if existing.content_hash != text_hash(content):
                raise DraftArtifactConflict("同一消息的待确认产物正文哈希不一致")
            return existing

    before = note.text_content or ""
    proposed = _proposed(before, content, operation, replace_fragment)
    return await ai_content_log_service.create(
        db=db,
        project_id=project_id,
        user_id=user_id,
        instance_type="note",
        instance_id=note.id,
        target_cell="text_content",
        model=model or "unknown",
        prompt_hash=prompt_hash,
        content_hash=text_hash(content),
        generated_content=content,
        confidence=None,
        generation_id=generation_id,
        task_code=task_code,
        source_message_id=source_message_id,
        prompt_version=prompt_version,
        context_manifest=context_manifest,
        target_locator={
            "type": "note", "note_id": str(note.id),
            "field": "text_content", "operation": operation,
            "replace_fragment": replace_fragment if operation == "replace_fragment" else None,
        },
        baseline_version=_version(note),
        before_hash=text_hash(before),
        before_content=before,
        proposed_hash=text_hash(proposed),
        preview_diff={
            "operation": operation,
            "before_chars": len(before),
            "proposed_chars": len(proposed),
            "added_chars": len(content.strip()),
        },
    )


async def _mark_stale(
    db: AsyncSession,
    log: AiContentLog,
    *,
    user_id: UUID,
    reason: str,
) -> None:
    log.is_stale = True
    log.stale_reason = reason
    log.writeback_status = "stale"
    log.artifact_version = int(log.artifact_version or 0) + 1
    await db.flush()
    await append_audit_log(db, {
        "user_id": user_id,
        "project_id": log.project_id,
        "action": "ai_content_stale",
        "resource_type": "ai_content_log",
        "resource_id": str(log.id),
        "details": {
            "event_type": "ai_content_lifecycle",
            "ai_content_log_id": str(log.id),
            "action": "stale",
            "reason": reason,
        },
    })


async def apply_note_artifact(
    db: AsyncSession,
    *,
    log_id: UUID,
    user: User,
    revised_content: str | None = None,
    client_instance: str | None = None,
) -> dict[str, Any]:
    """锁定 artifact 与附注，校验 baseline/hash 后应用预览过的变更。"""
    log = await ai_content_log_service.load_pending_for_update(db, log_id)
    locator = dict(log.target_locator or {})
    if locator.get("type") != "note" or locator.get("field") != "text_content":
        raise DraftArtifactConflict("该 AI 草稿没有可自动写回的附注目标")
    try:
        note_id = UUID(str(locator.get("note_id")))
    except (TypeError, ValueError) as exc:
        raise DraftArtifactConflict("附注目标定位无效") from exc

    await assert_project_permission(db, user, log.project_id, "review")
    await assert_project_permission(db, user, log.project_id, "edit")
    await check_consol_lock(project_id=log.project_id, db=db)
    from app.services.editing_lock_service import find_blocking_lock

    if await find_blocking_lock(
        db, "disclosure_note", str(note_id), user.id, client_instance
    ):
        raise DraftArtifactConflict("附注正在其他窗口编辑，请稍后重试")

    note = (await db.execute(sa.select(DisclosureNote).where(
        DisclosureNote.id == note_id,
        DisclosureNote.project_id == log.project_id,
        DisclosureNote.is_deleted == sa.false(),
    ).with_for_update())).scalar_one_or_none()
    if note is None:
        await _mark_stale(db, log, user_id=user.id, reason="目标附注不存在或已删除")
        raise DraftArtifactStale(log.stale_reason)
    before = note.text_content or ""
    if text_hash(before) != log.before_hash or _version(note) != (log.baseline_version or ""):
        await _mark_stale(db, log, user_id=user.id, reason="附注在预览后已被修改，请重新生成")
        raise DraftArtifactStale(log.stale_reason)

    fragment = revised_content if revised_content is not None else log.generated_content
    if not fragment or not fragment.strip():
        raise DraftArtifactConflict("待写入内容为空")
    operation = str(locator.get("operation") or "append")
    proposed = _proposed(
        before,
        fragment,
        operation,
        locator.get("replace_fragment"),
    )
    if revised_content is None and text_hash(proposed) != log.proposed_hash:
        raise DraftArtifactConflict("待写入内容与预览哈希不一致")

    from app.services.disclosure_engine import DisclosureEngine

    updated = await DisclosureEngine(db).update_note(
        note.id, text_content=proposed, user_id=user.id
    )
    if updated is None:
        raise DraftArtifactConflict("附注写入失败")
    await db.flush()
    await db.refresh(updated, attribute_names=["updated_at", "text_content"])
    if revised_content is None:
        log = await ai_content_log_service.confirm(db=db, log_id=log.id, user_id=user.id)
    else:
        log = await ai_content_log_service.revise(
            db=db, log_id=log.id, user_id=user.id, revised_content=revised_content
        )
        log.proposed_hash = text_hash(proposed)
    log.writeback_status = "applied"
    log.applied_version = _version(updated)
    log.applied_hash = text_hash(updated.text_content)
    log.writeback_receipt = {
        "target_type": "note",
        "target_id": str(note.id),
        "field": "text_content",
        "operation": operation,
        "before_version": log.baseline_version,
        "before_hash": log.before_hash,
        "after_version": log.applied_version,
        "after_hash": log.applied_hash,
        "generation_id": str(log.generation_id) if log.generation_id else None,
        "source_message_id": str(log.source_message_id) if log.source_message_id else None,
    }
    log.artifact_version = int(log.artifact_version or 0) + 1
    await db.flush()
    return {
        "artifact": serialize_artifact(log),
        "written": True,
        "project_id": str(log.project_id),
        "note_id": str(note.id),
        "note_section": note.note_section,
        "note_year": note.year,
    }


async def reject_artifact(
    db: AsyncSession, *, log_id: UUID, user: User
) -> AiContentLog:
    log = await ai_content_log_service.load_pending_for_update(db, log_id)
    await assert_project_permission(db, user, log.project_id, "review")
    log = await ai_content_log_service.reject(db=db, log_id=log.id, user_id=user.id)
    log.writeback_status = "rejected"
    log.artifact_version = int(log.artifact_version or 0) + 1
    await db.flush()
    return log


async def undo_note_artifact(
    db: AsyncSession,
    *,
    log_id: UUID,
    user: User,
    client_instance: str | None = None,
) -> dict[str, Any]:
    stmt = sa.select(AiContentLog).where(AiContentLog.id == log_id).with_for_update()
    log = (await db.execute(stmt)).scalar_one_or_none()
    if log is None:
        raise ai_content_log_service.AiContentLogNotFoundError("AI 内容记录不存在")
    if log.writeback_status != "applied":
        raise DraftArtifactConflict("仅已应用且未撤销的 AI 内容可以撤销")
    locator = dict(log.target_locator or {})
    if locator.get("type") != "note":
        raise DraftArtifactConflict("该 AI 内容不支持自动撤销")
    note_id = UUID(str(locator.get("note_id")))
    await assert_project_permission(db, user, log.project_id, "review")
    await assert_project_permission(db, user, log.project_id, "edit")
    await check_consol_lock(project_id=log.project_id, db=db)
    from app.services.editing_lock_service import find_blocking_lock

    if await find_blocking_lock(
        db, "disclosure_note", str(note_id), user.id, client_instance
    ):
        raise DraftArtifactConflict("附注正在其他窗口编辑，不能撤销")
    note = (await db.execute(sa.select(DisclosureNote).where(
        DisclosureNote.id == note_id,
        DisclosureNote.project_id == log.project_id,
        DisclosureNote.is_deleted == sa.false(),
    ).with_for_update())).scalar_one_or_none()
    if note is None:
        raise DraftArtifactConflict("目标附注不存在")
    if text_hash(note.text_content) != log.applied_hash or _version(note) != log.applied_version:
        raise DraftArtifactConflict("应用后附注已再次修改，不能自动撤销")

    from app.services.disclosure_engine import DisclosureEngine

    restored = await DisclosureEngine(db).update_note(
        note.id, text_content=log.before_content or "", user_id=user.id
    )
    if restored is None:
        raise DraftArtifactConflict("附注撤销失败")
    await db.flush()
    await db.refresh(restored, attribute_names=["updated_at", "text_content"])
    log.writeback_status = "undone"
    log.undone_by = user.id
    log.undone_at = datetime.now(timezone.utc)
    log.artifact_version = int(log.artifact_version or 0) + 1
    receipt = dict(log.writeback_receipt or {})
    receipt["undo"] = {
        "restored_version": _version(restored),
        "restored_hash": text_hash(restored.text_content),
        "undone_by": str(user.id),
        "undone_at": log.undone_at.isoformat(),
    }
    log.writeback_receipt = receipt
    await db.flush()
    await append_audit_log(db, {
        "user_id": user.id,
        "project_id": log.project_id,
        "action": "ai_content_undo",
        "resource_type": "ai_content_log",
        "resource_id": str(log.id),
        "details": {
            "event_type": "ai_content_lifecycle",
            "ai_content_log_id": str(log.id),
            "action": "undo",
        },
    })
    return {
        "artifact": serialize_artifact(log),
        "written": True,
        "project_id": str(log.project_id),
        "note_id": str(note.id),
        "note_section": note.note_section,
        "note_year": note.year,
    }
