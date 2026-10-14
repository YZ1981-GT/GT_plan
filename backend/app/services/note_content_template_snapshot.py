"""附注内容模板快照生成与不可变版本管理。

spec: disclosure-note-doc-upload-and-batch-fill Phase 7 Task 41~44
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.models.note_content_template_models import (
    NoteContentTemplate,
    NoteContentTemplateVersion,
)
from app.models.report_models import DisclosureNote
from app.services.note_content_template_service import (
    can_manage_group_template,
    can_view_template,
    resolve_canonical_group_root,
)
from app.services.note_quality_scanner import compute_quality_summary, scan_section_quality
from app.services.note_section_catalog import normalize_report_scope, normalize_template_type
from app.services.note_section_kind import classify_note_section

logger = logging.getLogger(__name__)

__all__ = [
    "generate_snapshot",
    "snapshot_preview",
    "save_snapshot",
    "list_templates",
    "get_template_detail",
    "list_versions",
    "soft_delete_template",
]

# ── 容量限制 ──────────────────────────────────────────────────────────────

_MAX_SECTIONS_DATA_BYTES = 10 * 1024 * 1024  # 10 MiB


async def generate_snapshot(
    db: AsyncSession,
    project_id: UUID,
    year: int,
) -> dict[str, Any]:
    """后端一次查询生成全套附注正文快照（不含 table_data）。"""
    # 加载项目元数据
    proj = await db.get(Project, project_id)
    if not proj:
        raise ValueError("项目不存在")

    # 查全部活动附注
    stmt = (
        sa.select(DisclosureNote)
        .where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.is_deleted == sa.false(),
        )
        .order_by(DisclosureNote.sort_index)
    )
    result = await db.execute(stmt)
    notes = list(result.scalars().all())

    # 生成 sections_data（不含 table_data）
    sections: list[dict[str, Any]] = []
    qualities = []
    for note in notes:
        text = note.text_content or ""
        # R-16：account_name 真库全部非空，不可作类型判据；统一走 Word 权威分类器
        section_kind = classify_note_section(
            note.note_section, proj.template_type, proj.report_scope, section_title=note.section_title,
        )
        quality = scan_section_quality(
            text_content=text,
            status=note.status.value if hasattr(note.status, "value") else str(note.status),
            is_stale=note.is_stale,
            section_kind=section_kind,
            section_title=note.section_title,
        )
        qualities.append(quality)

        sections.append({
            "source_note_id": str(note.id),
            "section_id": note.section_id,
            "note_section": note.note_section,
            "section_title": note.section_title,
            "section_kind": section_kind,
            "parent_section_id": note.parent_section_id,
            "content_type": note.content_type.value if hasattr(note.content_type, "value") else str(note.content_type or "text"),
            "text_content": text,
            "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "status": note.status.value if hasattr(note.status, "value") else str(note.status),
            "is_stale": note.is_stale,
            "quality_flags": quality.flags,
        })

    quality_summary = compute_quality_summary(qualities)

    # canonical hash
    canonical = json.dumps(
        [{"ns": s["note_section"], "h": s["content_hash"]} for s in sections],
        sort_keys=True, ensure_ascii=False,
    )
    content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    byte_size = len(json.dumps(sections, ensure_ascii=False).encode("utf-8"))

    # snapshot_digest
    digest_input = json.dumps({
        "project_id": str(project_id),
        "year": year,
        "content_hash": content_hash,
    }, sort_keys=True)
    snapshot_digest = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()

    return {
        "sections_data": sections,
        "quality_summary": quality_summary,
        "content_hash": content_hash,
        "byte_size": byte_size,
        "snapshot_digest": snapshot_digest,
        "source_project_id": str(project_id),
        "source_project_name": proj.name or proj.client_name or "",
        "source_year": year,
        "template_type": normalize_template_type(getattr(proj, "template_type", None)),
        "report_scope": normalize_report_scope(getattr(proj, "report_scope", None)),
    }


async def snapshot_preview(
    db: AsyncSession,
    project_id: UUID,
    year: int,
) -> dict[str, Any]:
    """生成快照预览（不落库）。"""
    snap = await generate_snapshot(db, project_id, year)
    # 不返回 sections_data 正文（只返回摘要）
    return {
        "snapshot_digest": snap["snapshot_digest"],
        "content_hash": snap["content_hash"],
        "byte_size": snap["byte_size"],
        "source_project_name": snap["source_project_name"],
        "source_year": snap["source_year"],
        "template_type": snap["template_type"],
        "report_scope": snap["report_scope"],
        "quality_summary": snap["quality_summary"],
    }


async def save_snapshot(
    db: AsyncSession,
    *,
    project_id: UUID,
    year: int,
    name: str,
    description: str | None,
    owner_scope: str,
    snapshot_digest: str,
    user: Any,
) -> dict[str, Any]:
    """正式保存模板快照（重算 digest，不一致则 409）。"""
    snap = await generate_snapshot(db, project_id, year)

    if snap["snapshot_digest"] != snapshot_digest:
        raise ValueError("STALE_SNAPSHOT: 来源附注在预检后已变化，请重新预览")

    if snap["byte_size"] > _MAX_SECTIONS_DATA_BYTES:
        raise ValueError(f"快照体积 {snap['byte_size']:,} 超过上限 {_MAX_SECTIONS_DATA_BYTES:,}")

    user_id = user.id if hasattr(user, "id") else user

    # 确定 owner
    if owner_scope == "personal":
        owner_user_id = user_id
        owner_group_project_id = None
    else:
        owner_user_id = None
        owner_group_project_id = await resolve_canonical_group_root(db, project_id)
        if not owner_group_project_id:
            raise ValueError("无法解析集团根项目，不能保存集团模板")

    # 查或建模板目录
    template = await _find_or_create_template(
        db,
        name=name,
        description=description,
        owner_scope=owner_scope,
        owner_user_id=owner_user_id,
        owner_group_project_id=owner_group_project_id,
        user_id=user_id,
    )

    # 检查同 hash 是否已有版本
    existing = await db.scalar(
        sa.select(NoteContentTemplateVersion.id).where(
            NoteContentTemplateVersion.template_id == template.id,
            NoteContentTemplateVersion.content_hash == snap["content_hash"],
        )
    )
    if existing:
        return {
            "template_id": str(template.id),
            "version_id": str(existing),
            "content_hash": snap["content_hash"],
            "reused": True,
        }

    # 新版本号
    max_ver = await db.scalar(
        sa.select(sa.func.max(NoteContentTemplateVersion.version_no)).where(
            NoteContentTemplateVersion.template_id == template.id,
        )
    )
    next_ver = (max_ver or 0) + 1

    version = NoteContentTemplateVersion(
        id=uuid4(),
        template_id=template.id,
        version_no=next_ver,
        source_project_id=project_id,
        source_year=year,
        source_project_name=snap["source_project_name"],
        template_type=snap["template_type"],
        report_scope=snap["report_scope"],
        sections_data=snap["sections_data"],
        quality_summary=snap["quality_summary"],
        content_hash=snap["content_hash"],
        byte_size=snap["byte_size"],
        created_by=user_id,
    )
    db.add(version)

    template.current_version_id = version.id
    template.updated_at = datetime.now(timezone.utc)
    await db.flush()

    return {
        "template_id": str(template.id),
        "version_id": str(version.id),
        "version_no": next_ver,
        "content_hash": snap["content_hash"],
        "reused": False,
    }


async def _find_or_create_template(
    db: AsyncSession,
    *,
    name: str,
    description: str | None,
    owner_scope: str,
    owner_user_id: UUID | None,
    owner_group_project_id: UUID | None,
    user_id: UUID,
) -> NoteContentTemplate:
    """查找活动同名模板或新建。"""
    filters = [
        NoteContentTemplate.owner_scope == owner_scope,
        NoteContentTemplate.is_deleted == sa.false(),
        sa.func.lower(NoteContentTemplate.name) == name.strip().lower(),
    ]
    if owner_scope == "personal":
        filters.append(NoteContentTemplate.owner_user_id == owner_user_id)
    else:
        filters.append(NoteContentTemplate.owner_group_project_id == owner_group_project_id)

    existing = await db.scalar(sa.select(NoteContentTemplate).where(*filters))
    if existing:
        if description is not None:
            existing.description = description
        return existing

    template = NoteContentTemplate(
        id=uuid4(),
        name=name.strip(),
        description=description,
        owner_scope=owner_scope,
        owner_user_id=owner_user_id,
        owner_group_project_id=owner_group_project_id,
        created_by=user_id,
    )
    db.add(template)
    await db.flush()
    return template


async def list_templates(
    db: AsyncSession,
    *,
    project_id: UUID,
    user: Any,
) -> list[dict[str, Any]]:
    """列出当前用户可见的附注内容模板（不返回正文）。"""
    user_id = user.id if hasattr(user, "id") else user

    stmt = (
        sa.select(NoteContentTemplate)
        .where(NoteContentTemplate.is_deleted == sa.false())
        .order_by(NoteContentTemplate.updated_at.desc())
    )
    result = await db.execute(stmt)
    all_templates = list(result.scalars().all())

    visible = []
    for t in all_templates:
        if await can_view_template(db, user, t, viewer_project_id=project_id):
            visible.append({
                "id": str(t.id),
                "name": t.name,
                "description": t.description,
                "owner_scope": t.owner_scope,
                "current_version_id": str(t.current_version_id) if t.current_version_id else None,
                "created_by": str(t.created_by) if t.created_by else None,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            })

    return visible


async def get_template_detail(
    db: AsyncSession,
    template_id: UUID,
    *,
    project_id: UUID,
    user: Any,
) -> dict[str, Any] | None:
    """获取模板详情（含当前版本元数据，不含正文）。"""
    template = await db.get(NoteContentTemplate, template_id)
    if not template or template.is_deleted:
        return None
    if not await can_view_template(db, user, template, viewer_project_id=project_id):
        return None

    result = {
        "id": str(template.id),
        "name": template.name,
        "description": template.description,
        "owner_scope": template.owner_scope,
        "created_by": str(template.created_by) if template.created_by else None,
        "created_at": template.created_at.isoformat() if template.created_at else None,
        "updated_at": template.updated_at.isoformat() if template.updated_at else None,
        "current_version": None,
    }

    if template.current_version_id:
        ver = await db.get(NoteContentTemplateVersion, template.current_version_id)
        if ver:
            result["current_version"] = {
                "id": str(ver.id),
                "version_no": ver.version_no,
                "source_project_name": ver.source_project_name,
                "source_year": ver.source_year,
                "template_type": ver.template_type,
                "report_scope": ver.report_scope,
                "quality_summary": ver.quality_summary,
                "content_hash": ver.content_hash,
                "byte_size": ver.byte_size,
                "created_at": ver.created_at.isoformat() if ver.created_at else None,
            }

    return result


async def list_versions(
    db: AsyncSession,
    template_id: UUID,
    *,
    project_id: UUID,
    user: Any,
) -> list[dict[str, Any]] | None:
    """列出模板的不可变版本元数据。"""
    template = await db.get(NoteContentTemplate, template_id)
    if not template or template.is_deleted:
        return None
    if not await can_view_template(db, user, template, viewer_project_id=project_id):
        return None

    stmt = (
        sa.select(NoteContentTemplateVersion)
        .where(NoteContentTemplateVersion.template_id == template_id)
        .order_by(NoteContentTemplateVersion.version_no.desc())
    )
    result = await db.execute(stmt)
    versions = result.scalars().all()

    return [
        {
            "id": str(v.id),
            "version_no": v.version_no,
            "source_project_name": v.source_project_name,
            "source_year": v.source_year,
            "template_type": v.template_type,
            "report_scope": v.report_scope,
            "quality_summary": v.quality_summary,
            "content_hash": v.content_hash,
            "byte_size": v.byte_size,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v in versions
    ]


async def soft_delete_template(
    db: AsyncSession,
    template_id: UUID,
    *,
    project_id: UUID,
    user: Any,
) -> bool:
    """软删除模板（保留版本和应用历史）。"""
    template = await db.get(NoteContentTemplate, template_id)
    if not template or template.is_deleted:
        return False
    if not await can_view_template(db, user, template, viewer_project_id=project_id):
        return False

    # 权限检查：personal 仅本人，group 仅 manager/partner
    user_id = user.id if hasattr(user, "id") else user
    if template.owner_scope == "personal":
        if template.owner_user_id != user_id:
            return False
    elif template.owner_scope == "group":
        if not await can_manage_group_template(db, user, template.owner_group_project_id):
            return False

    template.is_deleted = True
    template.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    return True
