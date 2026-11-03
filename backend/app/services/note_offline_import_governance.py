"""附注离线导入的持久版本与哈希链审计，同业务事务提交。"""
from __future__ import annotations

import hashlib
import uuid
from copy import deepcopy
from typing import Any

import sqlalchemy as sa


def _snapshot(section: Any) -> dict[str, Any]:
    if isinstance(section, dict):
        return {
            "section_id": section.get("section_id"),
            "note_section": section.get("note_section"),
            "section_title": section.get("section_title"),
            "guidance_text": section.get("guidance_text") or "",
            "table_data": deepcopy(section.get("table_data") or {}),
        }
    return {
        "section_id": section.section_id,
        "note_section": section.note_section,
        "section_title": section.section_title,
        "guidance_text": section.guidance_text or "",
        "table_data": deepcopy(section.table_data or {}),
    }


def _actor(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except (TypeError, ValueError):
        return None


async def record_import_governance(
    db: Any,
    *,
    project_id: uuid.UUID,
    year: int,
    user_id: Any,
    file_bytes: bytes,
    result: Any,
    before_sections: list[dict[str, Any]],
    decisions: dict[str, Any],
) -> tuple[list[str], str]:
    """写章节 pre/post 快照和审计链；任一步失败由 router 回滚全部导入。"""
    from app.models.report_models import DisclosureNote, NoteSectionVersionTree
    from app.services.audit_log_helper import append_audit_log
    from app.services.note_section_version_tree_service import create_version_node

    actor = _actor(user_id)
    before = {
        str(section.get("section_id") or section.get("note_section") or ""): section
        for section in before_sections
    }
    changed = set(result.changed_sections or [])
    notes = []
    if changed:
        notes = list((await db.execute(
            sa.select(DisclosureNote).where(
                DisclosureNote.project_id == project_id,
                DisclosureNote.year == year,
                DisclosureNote.is_deleted == sa.false(),
                DisclosureNote.note_section.in_(sorted(changed)),
            )
        )).scalars().all())
    version_ids: list[str] = []
    for note in notes:
        sid = str(note.section_id or note.note_section or "")
        node_data = create_version_node(sid, project_id, str(actor or ""))
        candidates = list((await db.execute(
            sa.select(NoteSectionVersionTree)
            .where(
                NoteSectionVersionTree.project_id == project_id,
                NoteSectionVersionTree.note_section_id == sid,
            )
            .order_by(NoteSectionVersionTree.created_at.desc())
            .limit(20)
        )).scalars().all())
        parent = next(
            (item for item in candidates if (item.snapshot_data or {}).get("year") == year),
            None,
        )
        node = NoteSectionVersionTree(
            id=uuid.uuid4(),
            project_id=project_id,
            note_section_id=sid,
            branch="main",
            parent_node_id=parent.id if parent else None,
            snapshot_data={
                "year": year,
                "source": "offline_import",
                "file_hash": hashlib.sha256(file_bytes).hexdigest(),
                "before": _snapshot(before.get(sid) or {}),
                "after": _snapshot(note),
            },
            created_by=actor,
            label=node_data["label"],
        )
        db.add(node)
        version_ids.append(str(node.id))
    await db.flush()

    audit_id = await append_audit_log(db, {
        "user_id": actor,
        "project_id": project_id,
        "action": "note_offline_import",
        "resource_type": "disclosure_notes",
        "resource_id": None,
        "details": {
            "year": year,
            "file_hash": hashlib.sha256(file_bytes).hexdigest(),
            "changed_sections": sorted(changed),
            "tables_written": int(result.tables_written or 0),
            "decisions": {str(k): str(getattr(v, "value", v)) for k, v in decisions.items()},
            "version_node_ids": version_ids,
        },
    })
    return version_ids, str(audit_id)
