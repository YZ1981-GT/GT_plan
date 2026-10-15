"""附注各章最近一次批量写入的来源（Task 50 来源标记，AC-11.1~11.3）。

只读：从 ``note_text_batch_applications``（每次原子写入一行，``detail`` 逐章记录目标章节）反查每章最近一次
来源，供编辑器在章节标题旁显示。溯源只在平台界面与审计记录里出现，不写进附注正文、不进导出（AC-11.3）。

- 「最近一次」按写入时间；同一章被多次批量写入只取最新一次；
- ``modified_after``：当前已保存正文与该次写入结果的 hash 不同（写入后有人改过），复核时据此判断是否还是原样；
- 写入人姓名与模板保存人同口径（人员档案姓名优先、回退登录名）。
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note_content_template_models import NoteTextBatchApplication
from app.models.report_models import DisclosureNote
from app.services.note_content_template_snapshot import _saver_names
from app.services.note_text_batch_apply import _sha256

#: 只看最近 500 次批量写入（每次一行）：只在更早写入、之后 500 次都没再碰的章节上不显示标记，
#: 一个项目年度实际远达不到；换来的是一次请求的读取量有上限
_MAX_APPLICATIONS = 500


def _note_uuid(entry: Any) -> UUID | None:
    """detail 里的目标章节 id；坏行（非对象 / 缺字段 / 非 UUID）跳过，不让一行坏数据拖垮整页标记。"""
    try:
        return UUID(str(entry["target_note_id"]))
    except (TypeError, KeyError, ValueError):
        return None


def _source_fields(app: NoteTextBatchApplication) -> dict[str, Any]:
    meta = app.source_metadata or {}
    if app.source_kind == "content_template":
        return {"template_name": meta.get("template_name"), "version_no": meta.get("version_no")}
    if app.source_kind == "upload":
        return {"file_name": meta.get("file_name")}
    return {"documents": [{"document_name": d.get("document_name"), "doc_version": d.get("doc_version")}
                          for d in meta.get("documents") or [] if isinstance(d, dict)]}


async def latest_note_sources(db: AsyncSession, *, project_id: UUID, year: int) -> dict[str, dict[str, Any]]:
    """``{note_id: 最近一次批量写入的来源}``；从未被批量写入的章节不在结果里。"""
    apps = (await db.execute(
        sa.select(NoteTextBatchApplication)
        .where(NoteTextBatchApplication.target_project_id == project_id, NoteTextBatchApplication.target_year == year)
        .order_by(NoteTextBatchApplication.applied_at.desc(), NoteTextBatchApplication.id.desc())
        .limit(_MAX_APPLICATIONS)
    )).scalars().all()
    latest: dict[UUID, tuple[NoteTextBatchApplication, dict[str, Any]]] = {}
    for app in apps:
        for entry in app.detail or []:
            uid = _note_uuid(entry)
            if uid is not None and uid not in latest:
                latest[uid] = (app, entry)
    if not latest:
        return {}
    texts = dict((await db.execute(
        sa.select(DisclosureNote.id, DisclosureNote.text_content).where(
            DisclosureNote.id.in_(list(latest)), DisclosureNote.project_id == project_id,
            DisclosureNote.is_deleted == sa.false())
    )).all())
    names = await _saver_names(db, [app.applied_by for app, _ in latest.values()])
    out: dict[str, dict[str, Any]] = {}
    for uid, (app, entry) in latest.items():
        if uid not in texts:  # 章节已删除或不属于本项目：不展示
            continue
        out[str(uid)] = {
            "application_id": str(app.id), "source_kind": app.source_kind, "mode": entry.get("mode"),
            "source_title": entry.get("source_title"),
            "applied_at": app.applied_at.isoformat() if app.applied_at else None,
            "applied_by_name": names.get(app.applied_by),
            "modified_after": _sha256(texts[uid]) != entry.get("after_hash"),
            **_source_fields(app),
        }
    return out
