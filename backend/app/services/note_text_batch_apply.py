"""附注正文原子批量 apply — 锁行 + 服务端重算预览复核 + 写入 + 审计 + 逐章事件。

spec: disclosure-note-doc-upload-and-batch-fill Phase 5 Task 27~33（第二轮复盘 R-06 / R-09 / R-12 修订）

调用约定（apply 端点）：
1. :func:`lock_target_notes` 按稳定 UUID 顺序 ``SELECT … FOR UPDATE`` 锁定所选目标；
2. 用**服务端**重新解析/加载的来源 + 当前目标状态重算 ``build_preview``；
3. :func:`apply_batch` 先整体校验、后整体写入，service 只 flush；
4. ``DisclosureMutationCoordinator`` 统一 commit，并用 :func:`build_note_saved_events` 逐章发事件。

🔴 写入值只取服务端预览结果；请求里的 ``proposed_html`` 一律不用（R-09：首轮直接写浏览器提交的正文，
   可绕过 preview 写任意内容）。
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.note_content_template_models import NoteTextBatchApplication
from app.models.report_models import DisclosureNote, NoteStatus
from app.services.note_html_sanitizer import has_visible_text
from app.services.note_lineage import CONTENT_TEMPLATES_KEY, append_lineage_entry

logger = logging.getLogger(__name__)

__all__ = [
    "ApplyError",
    "append_content_template_lineage",
    "apply_batch",
    "build_note_saved_events",
    "lock_target_notes",
]


class ApplyError(Exception):
    """apply 业务错误（端点转 409/422）；``stale_notes`` 为预览后被他人修改的章节号。"""

    def __init__(self, code: str, message: str, *, stale_notes: list[str] | None = None):
        self.code = code
        self.message = message
        self.stale_notes = stale_notes or []
        super().__init__(f"{code}: {message}")


def _sha256(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _as_uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _same_instant(expected: Any, current: datetime | None) -> bool:
    """``expected_updated_at`` 复核；任一侧缺失视为不比对（时间戳只是辅助，正文 hash 才是主判据）。"""
    if expected in (None, "") or current is None:
        return True
    if isinstance(expected, str):
        try:
            expected = datetime.fromisoformat(expected.replace("Z", "+00:00"))
        except ValueError:
            return False

    def _utc(value: datetime) -> datetime:
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value

    return _utc(expected) == _utc(current)


async def lock_target_notes(
    db: AsyncSession, project_id: UUID, year: int, note_ids: list[Any]
) -> dict[UUID, DisclosureNote]:
    """按稳定 UUID 顺序锁定本项目本年度未删除的目标章节（防死锁）；不属于本项目的 ID 不返回。"""
    ids = sorted({_as_uuid(i) for i in note_ids}, key=str)
    if not ids:
        return {}
    rows = await db.execute(
        sa.select(DisclosureNote)
        .where(
            DisclosureNote.id.in_(ids),
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.is_deleted == sa.false(),
        )
        .order_by(DisclosureNote.id)
        .with_for_update()
    )
    return {note.id: note for note in rows.scalars().all()}


def append_content_template_lineage(existing: Any, entry: dict[str, Any]) -> dict[str, Any]:
    """追加到 ``template_lineage.content_templates``，返回新 dict（R-06：原地改写不落库）。

    与集团基线 ``group_baselines``、裁剪、国企↔上市转换的键共存（AC-11.2，见 ``note_lineage``）。
    """
    return append_lineage_entry(existing, CONTENT_TEMPLATES_KEY, entry)


def _validate(
    locked_notes: dict[UUID, DisclosureNote],
    preview: dict[str, Any],
    request_digest: str,
    selections: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], DisclosureNote, dict[str, Any], str]]:
    """整体校验（零写入）；返回 [(selection, note, preview_item, final_html)]。"""
    if not selections:
        raise ApplyError("EMPTY_SELECTIONS", "批次为空")
    targets = [_as_uuid(s["target_note_id"]) for s in selections]
    sources = [s["source_id"] for s in selections]
    if len(set(targets)) != len(targets) or len(set(sources)) != len(sources):
        raise ApplyError("DUPLICATE_SELECTION", "同一来源或目标章节在批次中重复")
    missing = [str(t) for t in targets if t not in locked_notes]
    if missing:
        raise ApplyError("NOTE_NOT_FOUND", "目标章节不存在、已删除或不属于当前项目")

    stale = [
        locked_notes[t].note_section
        for s, t in zip(selections, targets)
        if s.get("before_hash") != _sha256(locked_notes[t].text_content)
        or not _same_instant(s.get("expected_updated_at"), locked_notes[t].updated_at)
    ]
    if stale:
        raise ApplyError("NOTE_BATCH_STALE_PREVIEW",
                         f"以下章节在预览后已被修改，请重新预览：{'、'.join(stale[:10])}", stale_notes=stale)
    if preview.get("preview_digest") != request_digest:
        raise ApplyError("PREVIEW_DIGEST_MISMATCH", "来源内容或章节映射与预览时不一致，请重新预览")

    items = {i["source_id"]: i for i in preview.get("items") or []}
    plan: list[tuple[dict[str, Any], DisclosureNote, dict[str, Any], str]] = []
    unchanged: list[str] = []
    for sel, target_id in zip(selections, targets):
        item = items.get(sel["source_id"])
        if item is None:
            raise ApplyError("SELECTION_NOT_IN_PREVIEW", f"来源章节不在本次预览中：{sel['source_id']}")
        if item.get("target_note_id") != str(target_id):
            raise ApplyError("SELECTION_MAPPING_MISMATCH", f"来源「{item.get('source_title')}」的目标章节与预览不一致")
        if item.get("category") == "unavailable":
            raise ApplyError("SELECTION_UNAVAILABLE", f"章节不可应用：{item.get('unavailable_reason') or ''}")
        mode = sel.get("mode") or "replace"
        if mode == "append":
            if item.get("append_html") is None:
                raise ApplyError("APPEND_NOT_APPLICABLE", "目标章节没有已有正文，只能替换")
            final, expected = item["append_html"], item["append_hash"]
        elif mode == "replace":
            final, expected = item["proposed_html"], item["proposed_hash"]
        else:
            raise ApplyError("INVALID_MODE", f"不支持的写入方式：{mode}")
        if sel.get("proposed_hash") != expected or _sha256(final) != expected:
            raise ApplyError("PROPOSED_HASH_MISMATCH", "拟写入内容与预览不一致，请重新预览")
        if final == item.get("before_html"):
            # 写入后与现有内容相同（追加的段落已全部在现有正文中）：写了只会重置状态、置本地改写、留痕（第 26 组）
            unchanged.append(locked_notes[target_id].note_section)
        plan.append((sel, locked_notes[target_id], item, final))
    if unchanged:
        raise ApplyError("SELECTION_NO_CHANGE",
                         f"以下章节写入后与现有内容相同，无需写入：{'、'.join(unchanged[:10])}。"
                         "追加时来源段落已全部在现有正文中，可改选「替换」或取消勾选")
    return plan


async def apply_batch(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    locked_notes: dict[UUID, DisclosureNote],
    preview: dict[str, Any],
    request_digest: str,
    selections: list[dict[str, Any]],
    source_kind: str,
    template_version_id: UUID | None,
    template_content_hash: str | None,
    source_metadata: dict[str, Any],
    mutation_id: str,
    request_fingerprint: str,
    user_id: UUID,
) -> dict[str, Any]:
    """原子批量写入：先整体校验（任一失败零写入）、后整体写入；只 flush 不 commit。"""
    plan = _validate(locked_notes, preview, request_digest, selections)
    now = datetime.now(timezone.utc)
    application_id = uuid4()
    detail: list[dict[str, Any]] = []
    # design §3.3「新增 / 替换 / 追加统计」，与勾选摘要同口径：写进没有可见正文的章算新增（第 20 组：
    # 首版只按写入方式计 ⇒ 用户确认「新增 2」，回执报「替换 2」）。逐章 detail.mode 仍记实际写入方式
    mode_counts = {"new": 0, "replace": 0, "append": 0}
    changed: list[dict[str, str]] = []

    for sel, note, item, final in plan:
        mode = sel.get("mode") or "replace"
        mode_counts["new" if mode == "replace" and not has_visible_text(note.text_content) else mode] += 1
        before_hash = _sha256(note.text_content)
        note.text_content = final
        note.status = NoteStatus.draft
        note.is_local_override = True
        note.updated_at = now
        note.updated_by = user_id
        if template_version_id is not None:
            note.template_lineage = append_content_template_lineage(note.template_lineage, {
                "kind": "content_template",
                "template_version_id": str(template_version_id),
                "content_hash": template_content_hash,
                "application_id": str(application_id),
                "mutation_id": mutation_id,
                "applied_at": now.isoformat(),
            })
        changed.append({"id": str(note.id), "note_section": note.note_section})
        detail.append({
            "source_id": item["source_id"], "source_title": item.get("source_title"),
            "target_note_id": str(note.id), "note_section": note.note_section,
            "match_kind": item.get("match_kind"), "mode": mode,
            "before_hash": before_hash, "after_hash": _sha256(final),
            "replacements": item.get("replacements") or [],
        })

    db.add(NoteTextBatchApplication(
        id=application_id, source_kind=source_kind, template_version_id=template_version_id,
        source_metadata=source_metadata, target_project_id=project_id, target_year=year,
        mutation_id=mutation_id, request_fingerprint=request_fingerprint,
        preview_digest=request_digest, applied_count=len(plan), mode_summary=mode_counts,
        detail=detail, status="succeeded", applied_by=user_id,
        # 与章节 updated_at、模板引用记录同一时刻，且取在加锁之后：库默认 now() 是事务开始时间，
        # 先开事务后拿到锁的一方会记得更早，「最近一次写入」（来源标记 / 最近引用）就会认错
        applied_at=now,
    ))
    await db.flush()
    return {
        "application_id": str(application_id), "mutation_id": mutation_id, "source_kind": source_kind,
        "applied_count": len(plan), "summary": mode_counts, "changed_notes": changed,
        "changed_note_ids": [c["id"] for c in changed], "warnings": [],
    }


def build_note_saved_events(project_id: UUID, year: int, response: dict[str, Any]) -> list[EventPayload]:
    """每个被改写章节一个 ``NOTE_SECTION_SAVED``（与单章保存同键 ``section_code``，AC-11.4）。"""
    return [
        EventPayload(
            event_type=EventType.NOTE_SECTION_SAVED,
            project_id=project_id,
            year=year,
            extra={
                "section_code": changed["note_section"],
                "note_id": changed["id"],
                "action": "batch_text_apply",
                "application_id": response.get("application_id"),
                "source_kind": response.get("source_kind"),
            },
        )
        for changed in response.get("changed_notes") or []
    ]
