"""附注内容模板快照生成与不可变版本管理。

spec: disclosure-note-doc-upload-and-batch-fill Phase 7 Task 41~45（第二轮复盘 R-03 / R-04 / R-13 / R-15 / R-17）

- 快照由服务端按 project_id + year 一次查询生成（不含 table_data），来源元数据全部取自服务端；
- 保存前重算 digest，来源变化 ⇒ 409；集团模板须集团根项目的经理 / 合伙人才能发布（R-04）；
- 同名模板目录行 ``FOR UPDATE`` 串行化版本号分配；并发首建撞部分唯一索引时回滚 SAVEPOINT、改取胜者（R-13）；
- 版本不可变：同 hash 复用（回退到历史内容 ⇒ current 指回该版本），新 hash 递增 version_no；
- 列表在 SQL 层按可见性过滤并分页，不逐行判权（R-15）；
- 版本元数据读时解析保存人姓名（AC-8.2）；列表带本项目最近一次引用的版本，供「有新版本」只读提示（AC-8.4）。
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project, User
from app.models.note_content_template_models import (
    NoteContentTemplate,
    NoteContentTemplateVersion,
    NoteTextBatchApplication,
)
from app.models.report_models import DisclosureNote
from app.models.staff_models import StaffMember
from app.services.note_content_template_service import (
    can_manage_group_template,
    can_view_template,
    resolve_canonical_group_root,
    visible_template_clause,
)
from app.services.note_html_sanitizer import has_visible_text
from app.services.note_quality_scanner import compute_quality_summary, scan_section_quality
from app.services.note_section_catalog import (
    normalize_report_scope,
    normalize_template_type,
    section_allowed_for_project,
)
from app.services.note_section_kind import classify_note_section, has_table_payload

logger = logging.getLogger(__name__)

__all__ = [
    "TemplateError",
    "generate_snapshot",
    "get_template_detail",
    "list_templates",
    "list_versions",
    "save_snapshot",
    "snapshot_preview",
    "soft_delete_template",
]

_MAX_SECTIONS_DATA_BYTES = 10 * 1024 * 1024  # design §11.2 硬上限


class TemplateError(Exception):
    """模板业务错误（端点按 ``status`` 返回，``code`` 进 ``detail.error_code``）。"""

    def __init__(self, code: str, message: str, status: int = 422) -> None:
        self.code, self.message, self.status = code, message, status
        super().__init__(f"{code}: {message}")


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "")


async def generate_snapshot(db: AsyncSession, project_id: UUID, year: int) -> dict[str, Any]:
    """后端一次查询生成全套附注正文快照（不含 table_data）。"""
    proj = await db.get(Project, project_id)
    if not proj:
        raise TemplateError("PROJECT_NOT_FOUND", "项目不存在", 404)
    notes = (await db.execute(
        sa.select(DisclosureNote)
        .where(DisclosureNote.project_id == project_id, DisclosureNote.year == year,
               DisclosureNote.is_deleted == sa.false())
        # 模板章节按来源项目的全文顺序（sort_order）；sort_index 是同层级内序号，不能当全文顺序
        .order_by(DisclosureNote.sort_order.asc().nulls_last(), DisclosureNote.sort_index, DisclosureNote.note_section)
    )).scalars().all()

    sections: list[dict[str, Any]] = []
    qualities = []
    parents = {n.parent_section_id for n in notes if n.parent_section_id}
    for note in notes:
        # 与章节读取同一判据：口径不适用（如单体项目里的合并专属章）不进模板，免得把旁路长出的章节扩散出去
        if not section_allowed_for_project(note.note_section, proj.template_type, proj.report_scope):
            continue
        text = note.text_content or ""
        # R-16：account_name 真库全部非空，不可作类型判据；统一走 Word 权威分类器。
        # 容器判据与章节读取（load_target_sections）同口径：同一章节在模板里与目标侧类型一致
        section_kind = classify_note_section(
            note.note_section, proj.template_type, proj.report_scope, section_title=note.section_title,
            has_children=bool(note.section_id) and note.section_id in parents,
            has_body=has_visible_text(text) or has_table_payload(note.table_data),
        )
        status = _enum_value(note.status)
        quality = scan_section_quality(text_content=text, status=status, is_stale=note.is_stale,
                                       section_kind=section_kind, section_title=note.section_title)
        qualities.append(quality)
        sections.append({
            "source_note_id": str(note.id),
            "section_id": note.section_id,
            "note_section": note.note_section,
            "section_title": note.section_title,
            "section_kind": section_kind,
            "parent_section_id": note.parent_section_id,
            "content_type": _enum_value(note.content_type) or "text",
            "text_content": text,
            "content_hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "status": status,
            "is_stale": note.is_stale,
            "quality_flags": quality.flags,
        })

    canonical = json.dumps([{"ns": s["note_section"], "h": s["content_hash"]} for s in sections],
                           sort_keys=True, ensure_ascii=False)
    content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    digest_input = json.dumps({"project_id": str(project_id), "year": year, "content_hash": content_hash},
                              sort_keys=True)
    return {
        "sections_data": sections,
        "quality_summary": compute_quality_summary(qualities),
        "content_hash": content_hash,
        "byte_size": len(json.dumps(sections, ensure_ascii=False).encode("utf-8")),
        "snapshot_digest": hashlib.sha256(digest_input.encode("utf-8")).hexdigest(),
        "source_project_id": str(project_id),
        "source_project_name": proj.name or proj.client_name or "",
        "source_year": year,
        "template_type": normalize_template_type(getattr(proj, "template_type", None)),
        "report_scope": normalize_report_scope(getattr(proj, "report_scope", None)),
    }


async def _resolve_owner(db: AsyncSession, project_id: UUID, user: Any,
                         owner_scope: str) -> tuple[UUID | None, UUID | None]:
    """(owner_user_id, owner_group_project_id)；归属由服务端解析，客户端不能指定集团根（AC-7.6）。"""
    if owner_scope == "personal":
        return user.id, None
    if owner_scope != "group":
        raise TemplateError("OWNER_SCOPE_INVALID", "模板归属只能是个人或集团")
    root = await resolve_canonical_group_root(db, project_id)
    if root is None:
        raise TemplateError("GROUP_ROOT_UNRESOLVED", "无法解析集团根项目（项目链缺失或成环），不能保存集团模板")
    if not await can_manage_group_template(db, user, root):
        raise TemplateError("GROUP_PUBLISH_FORBIDDEN", "只有集团根项目的经理或合伙人可以发布集团模板", 403)
    return None, root


async def snapshot_preview(db: AsyncSession, project_id: UUID, year: int, *, user: Any,
                           owner_scope: str = "personal") -> dict[str, Any]:
    """保存前预检（不落库）：质量摘要 + digest；集团发布在此即校验权限并给出发布范围。"""
    _owner_user, group_root = await _resolve_owner(db, project_id, user, owner_scope)
    snap = await generate_snapshot(db, project_id, year)
    result = {key: snap[key] for key in ("snapshot_digest", "content_hash", "byte_size", "source_project_name",
                                         "source_year", "template_type", "report_scope", "quality_summary")}
    result.update(owner_scope=owner_scope, section_count=len(snap["sections_data"]))
    if group_root is not None:
        root = await db.get(Project, group_root)
        result.update(group_root_project_id=str(group_root),
                      group_root_project_name=(root.name or root.client_name) if root else None)
    return result


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
    """正式保存：重算快照与 digest（来源变化 ⇒ 409），锁目录后创建或复用不可变版本；只 flush。"""
    clean_name = (name or "").strip()
    if not clean_name:
        raise TemplateError("TEMPLATE_NAME_INVALID", "模板名称不能为空")
    owner_user_id, owner_group_project_id = await _resolve_owner(db, project_id, user, owner_scope)
    snap = await generate_snapshot(db, project_id, year)
    if snap["snapshot_digest"] != snapshot_digest:
        raise TemplateError("STALE_SNAPSHOT", "来源附注在预检后已变化，请重新预检后再保存", 409)
    if snap["byte_size"] > _MAX_SECTIONS_DATA_BYTES:
        raise TemplateError("SNAPSHOT_TOO_LARGE", f"快照超过上限 {_MAX_SECTIONS_DATA_BYTES // (1024 * 1024)}MB", 413)

    template = await _lock_or_create_template(
        db, name=clean_name, description=description, owner_scope=owner_scope,
        owner_user_id=owner_user_id, owner_group_project_id=owner_group_project_id, user_id=user.id,
    )
    now = datetime.now(timezone.utc)
    existing = await db.scalar(sa.select(NoteContentTemplateVersion).where(
        NoteContentTemplateVersion.template_id == template.id,
        NoteContentTemplateVersion.content_hash == snap["content_hash"],
    ))
    if existing is not None:
        # 同内容不制造重复版本（AC-7.4）；内容回退到历史版本时，当前版本指回它（默认展示用户最后保存的内容）
        if template.current_version_id != existing.id:
            template.current_version_id = existing.id
            template.updated_at = now
            await db.flush()
        return {"template_id": str(template.id), "version_id": str(existing.id), "version_no": existing.version_no,
                "content_hash": existing.content_hash, "reused": True}

    max_ver = await db.scalar(sa.select(sa.func.max(NoteContentTemplateVersion.version_no))
                              .where(NoteContentTemplateVersion.template_id == template.id))
    version = NoteContentTemplateVersion(
        id=uuid4(), template_id=template.id, version_no=(max_ver or 0) + 1,
        source_project_id=project_id, source_year=year, source_project_name=snap["source_project_name"],
        template_type=snap["template_type"], report_scope=snap["report_scope"],
        sections_data=snap["sections_data"], quality_summary=snap["quality_summary"],
        content_hash=snap["content_hash"], byte_size=snap["byte_size"], created_by=user.id,
    )
    db.add(version)
    # 先落版本再改指针：current_version_id 外键不可延迟，同一 flush 里先 UPDATE 目录会撞外键
    await db.flush()
    template.current_version_id = version.id
    template.updated_at = now
    await db.flush()
    return {"template_id": str(template.id), "version_id": str(version.id), "version_no": version.version_no,
            "content_hash": version.content_hash, "reused": False}


def _template_filters(name: str, owner_scope: str, owner_user_id: UUID | None,
                      owner_group_project_id: UUID | None) -> list[Any]:
    owner = (NoteContentTemplate.owner_user_id == owner_user_id if owner_scope == "personal"
             else NoteContentTemplate.owner_group_project_id == owner_group_project_id)
    return [NoteContentTemplate.owner_scope == owner_scope, NoteContentTemplate.is_deleted == sa.false(),
            sa.func.lower(NoteContentTemplate.name) == name.lower(), owner]


async def _lock_or_create_template(
    db: AsyncSession,
    *,
    name: str,
    description: str | None,
    owner_scope: str,
    owner_user_id: UUID | None,
    owner_group_project_id: UUID | None,
    user_id: UUID,
) -> NoteContentTemplate:
    """锁定同名活动模板目录（不存在则新建）；返回时已持有该目录行锁。

    R-13：首版无锁 ⇒ 并发保存撞 ``ux_nctv_template_version`` 成 500 或丢版本。版本号分配在目录行锁内进行；
    并发首建时后到者的 INSERT 撞部分唯一索引，回滚 SAVEPOINT 后再 ``FOR UPDATE`` 取胜者已提交的行。
    """
    filters = _template_filters(name, owner_scope, owner_user_id, owner_group_project_id)
    stmt = sa.select(NoteContentTemplate).where(*filters).with_for_update()
    template = (await db.execute(stmt)).scalar_one_or_none()
    if template is None:
        candidate = NoteContentTemplate(
            id=uuid4(), name=name, description=description, owner_scope=owner_scope,
            owner_user_id=owner_user_id, owner_group_project_id=owner_group_project_id, created_by=user_id,
        )
        try:
            async with db.begin_nested():
                db.add(candidate)
                await db.flush()
            return candidate
        except IntegrityError:
            template = (await db.execute(stmt)).scalar_one_or_none()
            if template is None:
                raise
    if description is not None and template.description != description:
        template.description = description
    return template


def _version_meta(v: Any, names: dict[UUID, str] | None = None) -> dict[str, Any] | None:
    if v is None or getattr(v, "id", None) is None:
        return None
    return {
        "id": str(v.id), "version_no": v.version_no, "source_project_id": str(v.source_project_id),
        "source_project_name": v.source_project_name, "source_year": v.source_year,
        "template_type": v.template_type, "report_scope": v.report_scope, "quality_summary": v.quality_summary,
        "content_hash": v.content_hash, "byte_size": v.byte_size,
        "created_by": str(v.created_by) if v.created_by else None,
        "created_by_name": (names or {}).get(v.created_by),
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


async def _saver_names(db: AsyncSession, user_ids: list[UUID | None]) -> dict[UUID, str]:
    """保存人展示名（AC-8.2）：优先人员档案姓名，回退登录名；读时解析，改名即生效、不落冗余列。

    同一用户可有多份人员档案（真库存在）⇒ 按 user_id 聚合取 ``MIN(name)``：结果确定，且不会因联表把版本行翻倍。
    """
    ids = {u for u in user_ids if u is not None}
    if not ids:
        return {}
    rows = (await db.execute(
        sa.select(StaffMember.user_id, sa.func.min(StaffMember.name).label("name"))
        .where(StaffMember.user_id.in_(ids), StaffMember.is_deleted.is_(False))
        .group_by(StaffMember.user_id)
    )).all()
    names = {r.user_id: r.name for r in rows if r.name}
    missing = ids - names.keys()
    if missing:
        names.update({r.id: r.username for r in (await db.execute(
            sa.select(User.id, User.username).where(User.id.in_(missing)))).all()})
    return names


async def _last_applied_versions(db: AsyncSession, *, project_id: UUID, year: int | None,
                                 template_ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    """本项目（给了年度就只看该年度）对这些模板**最近一次**成功引用的版本（AC-8.4「有新版本」只读提示用）。

    按引用时间取最近一次而不是取最大版本号：用户可能刻意引回旧版本，此时同样应提示与当前版本不同。
    """
    if not template_ids:
        return {}
    app, ver = NoteTextBatchApplication, NoteContentTemplateVersion
    stmt = (sa.select(ver.template_id, ver.id, ver.version_no, app.applied_at)
            .select_from(app).join(ver, ver.id == app.template_version_id)
            .where(app.target_project_id == project_id, app.source_kind == "content_template",
                   app.status == "succeeded", ver.template_id.in_(template_ids))
            .order_by(app.applied_at.desc(), app.id.desc()))
    if year is not None:
        stmt = stmt.where(app.target_year == year)
    out: dict[UUID, dict[str, Any]] = {}
    for r in (await db.execute(stmt)).all():
        out.setdefault(r.template_id, {"version_id": str(r.id), "version_no": r.version_no,
                                       "applied_at": r.applied_at.isoformat() if r.applied_at else None})
    return out


def _template_meta(t: NoteContentTemplate, current: Any, names: dict[UUID, str] | None = None) -> dict[str, Any]:
    return {
        "id": str(t.id), "name": t.name, "description": t.description, "owner_scope": t.owner_scope,
        "current_version_id": str(t.current_version_id) if t.current_version_id else None,
        "current_version": _version_meta(current, names),
        "created_by": str(t.created_by) if t.created_by else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


#: 列表只取版本元数据列，不取 sections_data（NFR-8：模板列表不返回整包正文）
_VERSION_META_COLUMNS = (
    NoteContentTemplateVersion.id, NoteContentTemplateVersion.version_no,
    NoteContentTemplateVersion.source_project_id, NoteContentTemplateVersion.source_project_name,
    NoteContentTemplateVersion.source_year, NoteContentTemplateVersion.template_type,
    NoteContentTemplateVersion.report_scope, NoteContentTemplateVersion.quality_summary,
    NoteContentTemplateVersion.content_hash, NoteContentTemplateVersion.byte_size,
    NoteContentTemplateVersion.created_by, NoteContentTemplateVersion.created_at,
)


async def list_templates(db: AsyncSession, *, project_id: UUID, user: Any, limit: int = 50,
                         offset: int = 0, year: int | None = None) -> dict[str, Any]:
    """当前用户在本项目可见的模板（SQL 层过滤 + 分页，附当前版本元数据，不含正文）。

    每项带 ``last_applied``：本项目（``year`` 给定时只看该年度）最近一次引用的版本，从未引用为 None。
    """
    clause = visible_template_clause(user.id, await resolve_canonical_group_root(db, project_id))
    total = await db.scalar(sa.select(sa.func.count()).select_from(NoteContentTemplate).where(clause))
    rows = (await db.execute(
        sa.select(NoteContentTemplate, *_VERSION_META_COLUMNS)
        .outerjoin(NoteContentTemplateVersion, NoteContentTemplateVersion.id == NoteContentTemplate.current_version_id)
        .where(clause)
        .order_by(NoteContentTemplate.updated_at.desc(), NoteContentTemplate.id)
        .limit(limit).offset(offset)
    )).all()
    names = await _saver_names(db, [row.created_by for row in rows])
    applied = await _last_applied_versions(db, project_id=project_id, year=year,
                                           template_ids=[row[0].id for row in rows])
    items = []
    for row in rows:
        meta = _template_meta(row[0], row, names)
        meta["last_applied"] = applied.get(row[0].id)
        items.append(meta)
    return {"items": items, "total": int(total or 0)}


async def _visible_template(db: AsyncSession, template_id: UUID, *, project_id: UUID,
                            user: Any) -> NoteContentTemplate | None:
    template = await db.get(NoteContentTemplate, template_id)
    if template is None or not await can_view_template(db, user, template, viewer_project_id=project_id):
        return None
    return template


async def get_template_detail(db: AsyncSession, template_id: UUID, *, project_id: UUID,
                              user: Any) -> dict[str, Any] | None:
    """模板详情（含当前版本元数据，不含正文）；不可见返回 None（端点 404，不泄露存在性）。"""
    template = await _visible_template(db, template_id, project_id=project_id, user=user)
    if template is None:
        return None
    current = (await db.get(NoteContentTemplateVersion, template.current_version_id)
               if template.current_version_id else None)
    return _template_meta(template, current, await _saver_names(db, [current.created_by if current else None]))


async def list_versions(db: AsyncSession, template_id: UUID, *, project_id: UUID,
                        user: Any) -> list[dict[str, Any]] | None:
    """不可变版本元数据（新→旧）；不可见返回 None。"""
    if await _visible_template(db, template_id, project_id=project_id, user=user) is None:
        return None
    rows = (await db.execute(
        sa.select(*_VERSION_META_COLUMNS).where(NoteContentTemplateVersion.template_id == template_id)
        .order_by(NoteContentTemplateVersion.version_no.desc())
    )).all()
    names = await _saver_names(db, [row.created_by for row in rows])
    return [_version_meta(row, names) for row in rows]


async def soft_delete_template(db: AsyncSession, template_id: UUID, *, project_id: UUID, user: Any) -> bool:
    """软删目录（版本与应用记录保留，AC-11.5）。不可见 ⇒ False（404）；可见但无权 ⇒ 403。"""
    template = await _visible_template(db, template_id, project_id=project_id, user=user)
    if template is None:
        return False
    allowed = (template.owner_user_id == user.id if template.owner_scope == "personal"
               else await can_manage_group_template(db, user, template.owner_group_project_id))
    if not allowed:
        raise TemplateError("TEMPLATE_DELETE_FORBIDDEN", "只有模板所有人（集团模板为集团经理或合伙人）可以删除", 403)
    template.is_deleted = True
    template.deleted_at = datetime.now(timezone.utc)
    await db.flush()
    return True
