"""知识库扫描件后台 OCR（spec dsh-kb-ocr-local-first-routing ADR-DKR-005 / 006）。

上传时正文为空且可 OCR 的文档标 ``pending``（上传请求内不做 OCR：多页扫描件会超过 2 分钟上传超时）；
后台 worker（``workers/knowledge_ocr_worker.py``）认领后经统一 OCR 路由（``UnifiedOCRService.recognize``：
本机优先、服务器兜底）识别，写回 ``content_text`` 并刷新检索索引。

状态机（列含义见 V198）::

    pending ──认领──▶ running ──识别出文字──▶ done
       ▲                │  └──没有文字──────▶ empty
       └──服务不可用────┤  └──文件问题 / 次数用尽▶ failed
          （退避重试）   └──租约过期（进程崩溃）⇒ 可被重新认领

并发：多 worker 进程各自认领，PG 用 ``FOR UPDATE SKIP LOCKED`` + 条件更新（SQLite 只有条件更新）；
写回以 ``ocr_attempts`` 为围栏，租约已被别人接手的旧结果直接丢弃。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_models import KnowledgeDocument, KnowledgeFolder, strip_nul

logger = logging.getLogger(__name__)

#: 可 OCR 的类型：PDF 与常见图片（上传入口目前只放 PDF；图片经接口上传同样识别）
OCR_SUFFIXES = frozenset({".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"})
#: 最多认领次数（含进程崩溃导致的租约过期）
MAX_ATTEMPTS = 3
#: 识别中租约：超过即视为 worker 已退出，可被重新认领
LEASE = timedelta(minutes=15)
#: 服务不可用时第 n 次失败后的等待（秒）
BACKOFF_SECONDS = (60, 300, 900)
#: 写回正文的长度上限（与上传抽取同一口径）
_ERROR_MAX_CHARS = 2000

SessionFactory = Callable[[], Any]
Recognize = Callable[[str], Awaitable[dict]]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _default_session_factory() -> Any:
    from app.core.database import async_session

    return async_session()


def is_ocr_eligible(name: str | None, file_type: str | None = None) -> bool:
    """按扩展名（优先 ``file_type``）判断能否 OCR。"""
    suffix = f".{file_type.lower().lstrip('.')}" if file_type else Path(name or "").suffix.lower()
    return suffix in OCR_SUFFIXES


def mark_pending(doc: KnowledgeDocument) -> None:
    """标为待识别（立即可认领）。"""
    doc.ocr_status = "pending"
    doc.ocr_attempts = 0
    doc.ocr_error = None
    doc.ocr_due_at = None


class OcrRetryRejected(ValueError):
    """不能发起重新识别（类型不支持 / 正在识别 / 已有正文）。"""


def request_retry(doc: KnowledgeDocument) -> None:
    """用户发起「重新识别」：失败 / 没识别出文字 / 存量无正文的扫描件可以，已有正文的不行（避免覆盖）。"""
    if not is_ocr_eligible(doc.name, doc.file_type):
        raise OcrRetryRejected("该文件类型不支持识别（仅 PDF 与图片）")
    if doc.ocr_status in ("pending", "running"):
        raise OcrRetryRejected("该文档正在排队或识别中")
    if (doc.content_text or "").strip():
        raise OcrRetryRejected("该文档已有正文，无需识别")
    mark_pending(doc)


@dataclass(frozen=True)
class OcrClaim:
    doc_id: UUID
    attempt: int
    storage_path: str | None
    name: str


def _claimable(now: datetime):
    pending_due = and_(
        KnowledgeDocument.ocr_status == "pending",
        or_(KnowledgeDocument.ocr_due_at.is_(None), KnowledgeDocument.ocr_due_at <= now),
    )
    lease_expired = and_(
        KnowledgeDocument.ocr_status == "running", KnowledgeDocument.ocr_due_at <= now
    )
    return and_(KnowledgeDocument.is_deleted.is_(False), or_(pending_due, lease_expired))


async def claim_next(db: AsyncSession) -> OcrClaim | None:
    """认领一份到期的文档（标 running、次数 +1、写租约）并提交；没有可认领的返回 None。"""
    for _ in range(20):
        now = _utcnow()
        stmt = (
            select(
                KnowledgeDocument.id,
                KnowledgeDocument.ocr_status,
                KnowledgeDocument.ocr_attempts,
                KnowledgeDocument.storage_path,
                KnowledgeDocument.name,
            )
            .where(_claimable(now))
            .order_by(KnowledgeDocument.ocr_due_at.asc().nulls_first(), KnowledgeDocument.created_at.asc())
            .limit(1)
        )
        if db.get_bind().dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)
        row = (await db.execute(stmt)).first()
        if row is None:
            await db.rollback()
            return None
        fence = and_(
            KnowledgeDocument.id == row.id,
            KnowledgeDocument.ocr_status == row.ocr_status,
            KnowledgeDocument.ocr_attempts == row.ocr_attempts,
        )
        if row.ocr_status == "running" and row.ocr_attempts >= MAX_ATTEMPTS:
            # 租约过期且次数用尽：多半是这份文件反复拖垮进程，不再自动认领
            await db.execute(
                update(KnowledgeDocument).where(fence).values(
                    ocr_status="failed",
                    ocr_due_at=None,
                    ocr_error="识别多次中断（进程重启或超时），已停止自动重试，可点「重新识别」",
                )
            )
            await db.commit()
            continue
        attempt = row.ocr_attempts + 1
        result = await db.execute(
            update(KnowledgeDocument).where(fence).values(
                ocr_status="running", ocr_attempts=attempt, ocr_due_at=now + LEASE
            )
        )
        await db.commit()
        if result.rowcount == 1:
            return OcrClaim(row.id, attempt, row.storage_path, row.name)
    return None


async def _recognize(path: str) -> dict:
    from app.services.unified_ocr_service import UnifiedOCRService

    return await UnifiedOCRService().recognize(path)


async def process(
    claim: OcrClaim,
    *,
    session_factory: SessionFactory | None = None,
    recognize: Recognize | None = None,
) -> str:
    """识别一份已认领的文档并写回；返回最终状态（租约已被接手时为 ``stale``）。"""
    from app.services.knowledge_folder_service import CONTENT_TEXT_MAX_CHARS
    from app.services.unified_ocr_service import OCRServiceUnavailableError

    factory = session_factory or _default_session_factory
    if not claim.storage_path:
        return await _finish(factory, claim, "failed", error="文档没有存储文件，无法识别")
    try:
        result = await (recognize or _recognize)(claim.storage_path)
    except FileNotFoundError:
        return await _finish(factory, claim, "failed", error="文件不存在（可能已被删除或移动），无法识别")
    except OCRServiceUnavailableError as exc:
        kinds = tuple(getattr(exc, "kinds", ()) or ())
        if kinds and all(kind == "request" for kind in kinds):
            return await _finish(factory, claim, "failed", error=f"OCR 服务拒绝了这份文件：{exc}")
        return await _retry_or_fail(factory, claim, str(exc) or "OCR 服务暂不可用")
    except Exception as exc:  # noqa: BLE001 — 未预期错误按可重试处理，次数用尽再判失败
        logger.exception("[KB OCR] 识别 %s 出错", claim.name)
        return await _retry_or_fail(factory, claim, f"识别出错（{type(exc).__name__}）")

    text = strip_nul(str(result.get("text") or "")).strip()[:CONTENT_TEXT_MAX_CHARS]
    if not text:
        return await _finish(factory, claim, "empty")
    final = await _finish(factory, claim, "done", text=text)
    if final == "done":
        await _refresh_index(factory, claim.doc_id)
    return final


async def _retry_or_fail(factory: SessionFactory, claim: OcrClaim, reason: str) -> str:
    if claim.attempt >= MAX_ATTEMPTS:
        return await _finish(factory, claim, "failed", error=f"多次识别失败：{reason}")
    delay = BACKOFF_SECONDS[min(claim.attempt, len(BACKOFF_SECONDS)) - 1]
    return await _finish(
        factory, claim, "pending", error=reason, due=_utcnow() + timedelta(seconds=delay)
    )


async def _finish(
    factory: SessionFactory,
    claim: OcrClaim,
    status: str,
    *,
    text: str | None = None,
    error: str | None = None,
    due: datetime | None = None,
) -> str:
    """围栏写回：只有仍持有本次租约（running 且次数一致）才落库。"""
    values: dict[str, Any] = {
        "ocr_status": status,
        "ocr_error": strip_nul(error)[:_ERROR_MAX_CHARS] if error else None,
        "ocr_due_at": due,
    }
    if text is not None:
        values["content_text"] = text
    async with factory() as db:
        result = await db.execute(
            update(KnowledgeDocument)
            .where(
                KnowledgeDocument.id == claim.doc_id,
                KnowledgeDocument.ocr_status == "running",
                KnowledgeDocument.ocr_attempts == claim.attempt,
            )
            .values(**values)
        )
        await db.commit()
    if result.rowcount != 1:
        logger.warning("[KB OCR] %s 的租约已被接手，丢弃第 %d 次识别结果", claim.name, claim.attempt)
        return "stale"
    logger.info("[KB OCR] %s 第 %d 次识别 → %s", claim.name, claim.attempt, status)
    return status


async def _refresh_index(factory: SessionFactory, doc_id: UUID) -> None:
    """写回正文后刷新检索索引（与上传同一套钩子；失败只记日志，正文已可被词法检索命中）。"""
    from app.services.indexing_pipeline import run_indexing_pipeline
    from app.services.knowledge_upload_service import trigger_index_update

    try:
        async with factory() as db:
            row = (
                await db.execute(
                    select(
                        KnowledgeDocument.content_text,
                        KnowledgeDocument.project_ids,
                        KnowledgeDocument.version,
                        KnowledgeFolder.project_ids,
                    )
                    .join(KnowledgeFolder, KnowledgeFolder.id == KnowledgeDocument.folder_id)
                    .where(KnowledgeDocument.id == doc_id)
                )
            ).first()
        if row is not None:
            content, doc_pids, version, folder_pids = row
            await trigger_index_update(doc_pids or folder_pids, doc_id, content, doc_version=version)
        await run_indexing_pipeline(doc_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[KB OCR] 刷新索引失败 doc=%s: %s", doc_id, exc)
