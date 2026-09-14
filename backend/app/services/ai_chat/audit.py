"""AI Chat 哈希链审计模块（dsh-agent-panel-integration Task 12 / Req 12.6–12.7）

所有 AI Chat Run 生命周期事件写入平台哈希链：
- run started / done / error / cancelled
- access denied
- note saved / adopt requested
- attachment cleanup

🔴 审计只存 ID、hash、计数、字节数、时长和 error code。
   禁止记录 token、完整正文、附件内容或未脱敏上下文。
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.audit_log_helper import AuditLogPayload, append_audit_log

logger = logging.getLogger(__name__)

__all__ = [
    "audit_run_started",
    "audit_run_terminal",
    "audit_access_denied",
    "audit_note_saved",
    "audit_adopt_requested",
    "audit_attachment_cleanup",
    "audit_tool_started",
    "audit_tool_finished",
]


def _safe_hash(text: str | None) -> str:
    """对正文取 SHA-256 摘要（只存 hash，不存原文 — Req 12.7）。"""
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# run started
# ---------------------------------------------------------------------------


async def audit_run_started(
    db: AsyncSession,
    *,
    user_id: UUID,
    project_id: UUID | None,
    run_id: UUID,
    engine: str,
    host_type: str | None = None,
) -> None:
    """run 进入有界队列时写入哈希链（Req 12.6：EVERY run 有 started）。"""
    try:
        payload: AuditLogPayload = {
            "user_id": user_id,
            "project_id": project_id,
            "action": "ai_chat_run_started",
            "resource_type": "ai_chat_run",
            "resource_id": str(run_id),
            "details": {
                "event_type": "ai_chat_run_lifecycle",
                "run_id": str(run_id),
                "status": "started",
                "engine": engine,
                "host_type": host_type or "",
            },
        }
        await append_audit_log(db, payload)
    except Exception:  # noqa: BLE001
        # 审计写入失败不阻断 run 执行（降级 WARNING，但不吞掉）
        logger.warning("audit_run_started 写入失败 run=%s", run_id, exc_info=True)


# ---------------------------------------------------------------------------
# run terminal (done / error / cancelled)
# ---------------------------------------------------------------------------


async def audit_run_terminal(
    db: AsyncSession,
    *,
    user_id: UUID,
    project_id: UUID | None,
    run_id: UUID,
    status: str,
    engine: str,
    error_code: str | None = None,
    latency_ms: int | None = None,
    tokens_total: int | None = None,
) -> None:
    """run 进入终态时写入哈希链（Req 12.6：EVERY run 有唯一 terminal event）。

    🔴 审计 payload 只存 ID/status/error_code/latency/tokens 计数，不存正文。
    """
    try:
        payload: AuditLogPayload = {
            "user_id": user_id,
            "project_id": project_id,
            "action": f"ai_chat_run_{status}",
            "resource_type": "ai_chat_run",
            "resource_id": str(run_id),
            "details": {
                "event_type": "ai_chat_run_lifecycle",
                "run_id": str(run_id),
                "status": status,
                "engine": engine,
                "error_code": error_code or "",
                "latency_ms": latency_ms or 0,
                "tokens_total": tokens_total or 0,
            },
        }
        await append_audit_log(db, payload)
    except Exception:  # noqa: BLE001
        logger.warning("audit_run_terminal 写入失败 run=%s status=%s", run_id, status, exc_info=True)


# ---------------------------------------------------------------------------
# access denied
# ---------------------------------------------------------------------------


async def audit_access_denied(
    db: AsyncSession,
    *,
    user_id: UUID,
    project_id: UUID | None,
    run_id: UUID | None,
    denial_code: str,
    resource_type: str,
    resource_id: str | None = None,
) -> None:
    """授权拒绝时写入哈希链（Req 12.6）。"""
    try:
        payload: AuditLogPayload = {
            "user_id": user_id,
            "project_id": project_id,
            "action": "ai_chat_access_denied",
            "resource_type": "ai_chat_run",
            "resource_id": str(run_id) if run_id else "",
            "details": {
                "event_type": "ai_chat_access_denied",
                "run_id": str(run_id) if run_id else "",
                "denial_code": denial_code,
                "resource_type": resource_type,
                "resource_id": resource_id or "",
            },
        }
        await append_audit_log(db, payload)
    except Exception:  # noqa: BLE001
        logger.warning("audit_access_denied 写入失败 user=%s code=%s", user_id, denial_code, exc_info=True)


# ---------------------------------------------------------------------------
# note saved
# ---------------------------------------------------------------------------


async def audit_note_saved(
    db: AsyncSession,
    *,
    user_id: UUID,
    project_id: UUID | None,
    run_id: UUID,
    message_id: UUID,
    note_id: UUID,
    content_hash: str,
) -> None:
    """项目笔记转存成功时写入哈希链（Req 12.6）。"""
    try:
        payload: AuditLogPayload = {
            "user_id": user_id,
            "project_id": project_id,
            "action": "ai_chat_note_saved",
            "resource_type": "ai_chat_note",
            "resource_id": str(note_id),
            "details": {
                "event_type": "ai_chat_note_saved",
                "run_id": str(run_id),
                "message_id": str(message_id),
                "note_id": str(note_id),
                "content_hash": content_hash[:16],  # 只存摘要 hash
            },
        }
        await append_audit_log(db, payload)
    except Exception:  # noqa: BLE001
        logger.warning("audit_note_saved 写入失败 note=%s", note_id, exc_info=True)


# ---------------------------------------------------------------------------
# adopt requested
# ---------------------------------------------------------------------------


async def audit_adopt_requested(
    db: AsyncSession,
    *,
    user_id: UUID,
    project_id: UUID | None,
    run_id: UUID,
    message_id: UUID,
    content_hash: str,
    host_type: str,
) -> None:
    """AI 内容采纳请求成功时写入哈希链（Req 12.6）。"""
    try:
        payload: AuditLogPayload = {
            "user_id": user_id,
            "project_id": project_id,
            "action": "ai_chat_adopt_requested",
            "resource_type": "ai_chat_adopt",
            "resource_id": str(message_id),
            "details": {
                "event_type": "ai_chat_adopt_requested",
                "run_id": str(run_id),
                "message_id": str(message_id),
                "content_hash": content_hash[:16],
                "host_type": host_type,
            },
        }
        await append_audit_log(db, payload)
    except Exception:  # noqa: BLE001
        logger.warning("audit_adopt_requested 写入失败 message=%s", message_id, exc_info=True)


# ---------------------------------------------------------------------------
# attachment cleanup
# ---------------------------------------------------------------------------


async def audit_attachment_cleanup(
    db: AsyncSession,
    *,
    user_id: UUID,
    project_id: UUID | None,
    run_id: UUID | None,
    attachment_id: UUID,
    status: str,
    bytes_freed: int = 0,
) -> None:
    """附件清理事件写入哈希链（成功/失败均记录 — Req 12.6）。"""
    try:
        payload: AuditLogPayload = {
            "user_id": user_id,
            "project_id": project_id,
            "action": f"ai_chat_attachment_{status}",
            "resource_type": "ai_chat_attachment",
            "resource_id": str(attachment_id),
            "details": {
                "event_type": "ai_chat_attachment_cleanup",
                "run_id": str(run_id) if run_id else "",
                "attachment_id": str(attachment_id),
                "status": status,
                "bytes_freed": bytes_freed,
            },
        }
        await append_audit_log(db, payload)
    except Exception:  # noqa: BLE001
        logger.warning("audit_attachment_cleanup 写入失败 attachment=%s", attachment_id, exc_info=True)


# ---------------------------------------------------------------------------
# tool call started (Property 32: 每个 tool call 恰有 started + finished/failed)
# ---------------------------------------------------------------------------


async def audit_tool_started(
    db: AsyncSession,
    *,
    user_id: UUID,
    project_id: UUID | None,
    run_id: UUID,
    tool_call_id: str,
    tool_name: str,
) -> None:
    """工具调用开始时写入哈希链（Property 32 / Req 12.6：EVERY tool call 有 started）。

    🔴 审计 payload 只存 run/tool_call_id/tool_name，不存工具入参或 scoped token。
    """
    try:
        payload: AuditLogPayload = {
            "user_id": user_id,
            "project_id": project_id,
            "action": "ai_chat_tool_started",
            "resource_type": "ai_chat_tool_call",
            "resource_id": tool_call_id,
            "details": {
                "event_type": "ai_chat_tool_lifecycle",
                "run_id": str(run_id),
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "status": "started",
            },
        }
        await append_audit_log(db, payload)
    except Exception:  # noqa: BLE001
        logger.warning(
            "audit_tool_started 写入失败 run=%s tool=%s", run_id, tool_name, exc_info=True
        )


# ---------------------------------------------------------------------------
# tool call finished / failed (Property 32)
# ---------------------------------------------------------------------------


async def audit_tool_finished(
    db: AsyncSession,
    *,
    user_id: UUID,
    project_id: UUID | None,
    run_id: UUID,
    tool_call_id: str,
    tool_name: str,
    status: str,
    result_bytes: int = 0,
    duration_ms: int = 0,
    error_code: str | None = None,
) -> None:
    """工具调用结束时写入哈希链（Property 32 / Req 12.6：EVERY tool call 有 finished/failed）。

    🔴 审计 payload 只存 ID/status/error_code/result_bytes/duration，不存完整入参/正文/附件内容。
    """
    try:
        payload: AuditLogPayload = {
            "user_id": user_id,
            "project_id": project_id,
            "action": f"ai_chat_tool_{status}",
            "resource_type": "ai_chat_tool_call",
            "resource_id": tool_call_id,
            "details": {
                "event_type": "ai_chat_tool_lifecycle",
                "run_id": str(run_id),
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "status": status,
                "result_bytes": result_bytes,
                "duration_ms": duration_ms,
                "error_code": error_code or "",
            },
        }
        await append_audit_log(db, payload)
    except Exception:  # noqa: BLE001
        logger.warning(
            "audit_tool_finished 写入失败 run=%s tool=%s status=%s",
            run_id, tool_name, status, exc_info=True
        )
