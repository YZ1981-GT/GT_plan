"""附注正文原子批量 apply — 锁行 + hash 校验 + 写入 + 审计 + 事件。

spec: disclosure-note-doc-upload-and-batch-fill Phase 5 Task 27~33
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note_content_template_models import NoteTextBatchApplication
from app.models.report_models import DisclosureNote
from app.services.note_html_sanitizer import sanitize_note_html

logger = logging.getLogger(__name__)

__all__ = ["apply_batch", "ApplyError"]


class ApplyError(Exception):
    """apply 业务错误（非 HTTP 异常，由调用方转换）。"""

    def __init__(self, code: str, message: str, *, stale_notes: list[str] | None = None):
        self.code = code
        self.message = message
        self.stale_notes = stale_notes or []
        super().__init__(f"{code}: {message}")


async def apply_batch(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    source_kind: str,
    template_version_id: UUID | None,
    source_metadata: dict[str, Any],
    preview_digest: str,
    mutation_id: str,
    request_fingerprint: str,
    selections: list[dict[str, Any]],
    user_id: UUID,
) -> dict[str, Any]:
    """原子批量写入附注正文。

    全成全败：任一章节冲突/异常 → 整体回滚（由 coordinator commit）。
    只 flush 不 commit（遵循 service 只 flush 铁律）。
    """
    if not selections:
        raise ApplyError("EMPTY_SELECTIONS", "批次为空")

    # ── 1. 按稳定 UUID 排序防死锁 ─────────────────────────────────────────
    note_ids = sorted(set(s["target_note_id"] for s in selections))

    # ── 2. SELECT ... FOR UPDATE 锁全部目标 ──────────────────────────────
    stmt = (
        sa.select(DisclosureNote)
        .where(
            DisclosureNote.id.in_(note_ids),
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.is_deleted == sa.false(),
        )
        .with_for_update()
        .order_by(DisclosureNote.id)
    )

    result = await db.execute(stmt)
    locked_notes = {n.id: n for n in result.scalars().all()}

    # ── 3. 校验目标归属 ──────────────────────────────────────────────────
    missing = [str(nid) for nid in note_ids if nid not in locked_notes]
    if missing:
        raise ApplyError(
            "NOTE_NOT_FOUND",
            f"目标章节不存在或不属于当前项目：{', '.join(missing[:5])}",
        )

    # ── 4. 复核 hash / updated_at ────────────────────────────────────────
    stale: list[str] = []
    sel_map = {s["target_note_id"]: s for s in selections}

    for nid, note in locked_notes.items():
        sel = sel_map.get(nid)
        if not sel:
            continue
        current_text = note.text_content or ""
        current_hash = hashlib.sha256(current_text.encode("utf-8")).hexdigest()
        if sel.get("before_hash") and sel["before_hash"] != current_hash:
            stale.append(note.note_section)

    if stale:
        raise ApplyError(
            "NOTE_BATCH_STALE_PREVIEW",
            f"以下章节在预览后已被修改，请重新预览：{', '.join(stale[:10])}",
            stale_notes=stale,
        )

    # ── 5. 执行写入 ─────────────────────────────────────────────────────
    changed_note_ids: list[UUID] = []
    detail_records: list[dict[str, Any]] = []
    mode_counts = {"replace": 0, "append": 0}
    now = datetime.now(timezone.utc)

    for sel in selections:
        note = locked_notes[sel["target_note_id"]]
        mode = sel.get("mode", "replace")
        proposed_html = sanitize_note_html(sel.get("proposed_html", ""))

        before_text = note.text_content or ""
        before_hash = hashlib.sha256(before_text.encode("utf-8")).hexdigest()

        if mode == "append" and before_text.strip():
            # 追加：用规范空段连接，去重完全相同段落
            final = _append_html(before_text, proposed_html)
        else:
            final = proposed_html

        final_hash = hashlib.sha256(final.encode("utf-8")).hexdigest()

        # 写入
        note.text_content = final
        note.status = "draft"
        note.is_local_override = True
        note.updated_at = now

        # 追加 template_lineage（如有），不覆盖既有
        if template_version_id:
            lineage = note.template_lineage or {}
            lineage["content_template"] = {
                "template_version_id": str(template_version_id),
                "applied_at": now.isoformat(),
                "mutation_id": mutation_id,
            }
            note.template_lineage = lineage

        changed_note_ids.append(note.id)
        mode_counts[mode] = mode_counts.get(mode, 0) + 1

        detail_records.append({
            "target_note_id": str(note.id),
            "note_section": note.note_section,
            "mode": mode,
            "before_hash": before_hash,
            "after_hash": final_hash,
        })

    # ── 6. 写审计记录 ────────────────────────────────────────────────────
    application = NoteTextBatchApplication(
        id=uuid4(),
        source_kind=source_kind,
        template_version_id=template_version_id,
        source_metadata=source_metadata,
        target_project_id=project_id,
        target_year=year,
        mutation_id=mutation_id,
        request_fingerprint=request_fingerprint,
        preview_digest=preview_digest,
        applied_count=len(changed_note_ids),
        mode_summary=mode_counts,
        detail=detail_records,
        status="succeeded",
        applied_by=user_id,
    )
    db.add(application)
    await db.flush()

    return {
        "application_id": str(application.id),
        "mutation_id": mutation_id,
        "applied_count": len(changed_note_ids),
        "summary": mode_counts,
        "changed_note_ids": [str(nid) for nid in changed_note_ids],
        "warnings": [],
    }


def _append_html(existing: str, new: str) -> str:
    """追加正文：用空段连接，去重完全相同的段落。"""
    separator = "<p>&nbsp;</p>"
    combined = f"{existing.rstrip()}{separator}{new.lstrip()}"
    # 简单去重：如果 new 的每个段落都已在 existing 中，不重复追加
    # 这里只做完全子串检查（design §7.2 要求）
    if new.strip() and new.strip() in existing:
        return existing
    return combined
