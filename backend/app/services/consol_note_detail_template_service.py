"""合并附注明细模板与绑定 service（Phase 1 Task 3/5/6）。

spec: consol-note-detail-template-and-mapping

Service 只 flush 不 commit（router 层 commit）。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Sequence
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consol_note_mapping_models import (
    ConsolNoteDetailTemplate,
    ConsolNoteDetailTemplateVersion,
    ConsolNoteMappingBinding,
    ConsolNoteMappingRule,
    ConsolNoteTemplateBinding,
)

logger = logging.getLogger(__name__)


# ─── 错误 ────────────────────────────────────────────────────────────────────


class TemplateServiceError(Exception):
    """模板/绑定操作错误。"""

    def __init__(self, status: int, code: str, message: str, detail: Any = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.detail = detail


# ─── 模板 CRUD（Task 3） ─────────────────────────────────────────────────────


async def create_template(
    db: AsyncSession,
    *,
    template_type: str,
    section_id: str,
    name: str = "",
    visibility: str = "project",
    rows: list[dict[str, Any]] | None = None,
    change_note: str | None = None,
    created_by: UUID | None = None,
) -> dict[str, Any]:
    """创建模板并附带第一个版本（v1）。"""
    if template_type not in ("soe", "listed"):
        raise TemplateServiceError(400, "INVALID_TEMPLATE_TYPE", "template_type 必须是 soe 或 listed")
    if visibility not in ("draft", "project", "firm"):
        raise TemplateServiceError(400, "INVALID_VISIBILITY", "visibility 必须是 draft / project / firm")
    if not section_id or not section_id.strip():
        raise TemplateServiceError(400, "MISSING_SECTION_ID", "section_id 不能为空")

    # 为每个目标行确保有 target_row_id
    validated_rows = _validate_template_rows(rows or [])

    template = ConsolNoteDetailTemplate(
        template_type=template_type,
        section_id=section_id.strip(),
        name=name.strip() if name else "",
        visibility=visibility,
        created_by=created_by,
    )
    db.add(template)
    await db.flush()  # 取得 template.id

    version = ConsolNoteDetailTemplateVersion(
        template_id=template.id,
        version_number=1,
        rows=validated_rows,
        change_note=change_note or "初始版本",
        created_by=created_by,
    )
    db.add(version)
    await db.flush()

    return _template_to_dict(template, latest_version=version)


async def list_templates(
    db: AsyncSession,
    *,
    template_type: str | None = None,
    section_id: str | None = None,
    visibility: str | None = None,
    created_by: UUID | None = None,
) -> list[dict[str, Any]]:
    """列出模板（可按 template_type / section_id / visibility / 创建人筛选）。"""
    q = sa.select(ConsolNoteDetailTemplate).where(
        ConsolNoteDetailTemplate.is_deleted == sa.false(),
    )
    if template_type:
        q = q.where(ConsolNoteDetailTemplate.template_type == template_type)
    if section_id:
        q = q.where(ConsolNoteDetailTemplate.section_id == section_id)
    if visibility:
        q = q.where(ConsolNoteDetailTemplate.visibility == visibility)
    if created_by is not None:
        q = q.where(ConsolNoteDetailTemplate.created_by == created_by)
    q = q.order_by(ConsolNoteDetailTemplate.created_at.desc())

    result = await db.execute(q)
    templates = list(result.scalars().all())

    # 批量取最新版本
    # TODO: N+1 查询——模板数增多后应改为 window function 一次取全部 latest
    out: list[dict[str, Any]] = []
    for tmpl in templates:
        latest = await _get_latest_version(db, tmpl.id)
        out.append(_template_to_dict(tmpl, latest_version=latest))
    return out


async def get_template(
    db: AsyncSession,
    template_id: UUID,
) -> dict[str, Any] | None:
    """获取单个模板详情（含最新版本）。"""
    tmpl = await _load_template(db, template_id)
    if tmpl is None:
        return None
    latest = await _get_latest_version(db, tmpl.id)
    return _template_to_dict(tmpl, latest_version=latest)


async def add_version(
    db: AsyncSession,
    template_id: UUID,
    *,
    rows: list[dict[str, Any]],
    change_note: str | None = None,
    created_by: UUID | None = None,
) -> dict[str, Any]:
    """追加新版本（不可变）。"""
    tmpl = await _load_template(db, template_id)
    if tmpl is None:
        raise TemplateServiceError(404, "TEMPLATE_NOT_FOUND", "模板不存在")

    validated_rows = _validate_template_rows(rows)
    latest = await _get_latest_version(db, template_id)
    next_num = (latest.version_number + 1) if latest else 1

    version = ConsolNoteDetailTemplateVersion(
        template_id=template_id,
        version_number=next_num,
        rows=validated_rows,
        change_note=change_note,
        created_by=created_by,
    )
    db.add(version)
    await db.flush()
    return _version_to_dict(version)


async def get_versions(
    db: AsyncSession,
    template_id: UUID,
) -> list[dict[str, Any]]:
    """查看版本历史。"""
    tmpl = await _load_template(db, template_id)
    if tmpl is None:
        raise TemplateServiceError(404, "TEMPLATE_NOT_FOUND", "模板不存在")

    result = await db.execute(
        sa.select(ConsolNoteDetailTemplateVersion)
        .where(ConsolNoteDetailTemplateVersion.template_id == template_id)
        .order_by(ConsolNoteDetailTemplateVersion.version_number.desc())
    )
    return [_version_to_dict(v) for v in result.scalars().all()]


async def soft_delete_template(
    db: AsyncSession,
    template_id: UUID,
) -> dict[str, Any]:
    """软删除模板。"""
    tmpl = await _load_template(db, template_id)
    if tmpl is None:
        raise TemplateServiceError(404, "TEMPLATE_NOT_FOUND", "模板不存在")
    tmpl.is_deleted = True
    await db.flush()
    return {"id": str(template_id), "deleted": True}


async def change_visibility(
    db: AsyncSession,
    template_id: UUID,
    *,
    visibility: str,
) -> dict[str, Any]:
    """修改模板可见范围。"""
    if visibility not in ("draft", "project", "firm"):
        raise TemplateServiceError(400, "INVALID_VISIBILITY", "visibility 必须是 draft / project / firm")
    tmpl = await _load_template(db, template_id)
    if tmpl is None:
        raise TemplateServiceError(404, "TEMPLATE_NOT_FOUND", "模板不存在")
    tmpl.visibility = visibility
    await db.flush()
    latest = await _get_latest_version(db, tmpl.id)
    return _template_to_dict(tmpl, latest_version=latest)


# ─── 模板绑定（Task 5） ─────────────────────────────────────────────────────


async def bind_template_version(
    db: AsyncSession,
    *,
    project_id: UUID,
    section_id: str,
    template_version_id: UUID,
    bound_by: UUID | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """项目绑定/切换模板版本。

    切换已有绑定时必须传 confirm=True，否则返回 affected_count 让前端二次确认。
    """
    # 验证版本存在
    version = (await db.execute(
        sa.select(ConsolNoteDetailTemplateVersion)
        .where(ConsolNoteDetailTemplateVersion.id == template_version_id)
    )).scalar_one_or_none()
    if version is None:
        raise TemplateServiceError(404, "VERSION_NOT_FOUND", "模板版本不存在")

    # 查现有绑定
    existing = (await db.execute(
        sa.select(ConsolNoteTemplateBinding).where(
            ConsolNoteTemplateBinding.project_id == project_id,
            ConsolNoteTemplateBinding.section_id == section_id,
        )
    )).scalar_one_or_none()

    if existing is not None and existing.template_version_id != template_version_id:
        # 切换版本——检查受影响的映射规则数
        affected = await _count_affected_rules(db, project_id, section_id, existing.template_version_id)
        if affected > 0 and not confirm:
            return {
                "action": "confirm_required",
                "current_version_id": str(existing.template_version_id),
                "new_version_id": str(template_version_id),
                "affected_rule_count": affected,
                "message": f"切换版本将影响 {affected} 条映射规则，请确认",
            }

    now = datetime.now(timezone.utc)
    if existing is not None:
        existing.template_version_id = template_version_id
        existing.bound_by = bound_by
        existing.bound_at = now
    else:
        binding = ConsolNoteTemplateBinding(
            project_id=project_id,
            section_id=section_id,
            template_version_id=template_version_id,
            bound_by=bound_by,
            bound_at=now,
        )
        db.add(binding)
    await db.flush()
    return {
        "action": "bound",
        "project_id": str(project_id),
        "section_id": section_id,
        "template_version_id": str(template_version_id),
    }


async def get_bindings(
    db: AsyncSession,
    project_id: UUID,
) -> list[dict[str, Any]]:
    """查看当前项目所有章节的模板绑定。"""
    result = await db.execute(
        sa.select(ConsolNoteTemplateBinding)
        .where(ConsolNoteTemplateBinding.project_id == project_id)
        .order_by(ConsolNoteTemplateBinding.section_id)
    )
    bindings = list(result.scalars().all())
    out: list[dict[str, Any]] = []
    for b in bindings:
        version = (await db.execute(
            sa.select(ConsolNoteDetailTemplateVersion)
            .where(ConsolNoteDetailTemplateVersion.id == b.template_version_id)
        )).scalar_one_or_none()
        out.append({
            "id": str(b.id),
            "project_id": str(b.project_id),
            "section_id": b.section_id,
            "template_version_id": str(b.template_version_id),
            "version_number": version.version_number if version else None,
            "bound_by": str(b.bound_by) if b.bound_by else None,
            "bound_at": b.bound_at.isoformat() if b.bound_at else None,
        })
    return out


async def get_binding(
    db: AsyncSession,
    project_id: UUID,
    section_id: str,
) -> dict[str, Any] | None:
    """查看单个章节的模板绑定。"""
    b = (await db.execute(
        sa.select(ConsolNoteTemplateBinding).where(
            ConsolNoteTemplateBinding.project_id == project_id,
            ConsolNoteTemplateBinding.section_id == section_id,
        )
    )).scalar_one_or_none()
    if b is None:
        return None
    version = (await db.execute(
        sa.select(ConsolNoteDetailTemplateVersion)
        .where(ConsolNoteDetailTemplateVersion.id == b.template_version_id)
    )).scalar_one_or_none()
    return {
        "id": str(b.id),
        "project_id": str(b.project_id),
        "section_id": b.section_id,
        "template_version_id": str(b.template_version_id),
        "version_number": version.version_number if version else None,
        "bound_by": str(b.bound_by) if b.bound_by else None,
        "bound_at": b.bound_at.isoformat() if b.bound_at else None,
    }


# ─── 模板编辑约束（Task 6） ─────────────────────────────────────────────────


async def check_row_deletion_impact(
    db: AsyncSession,
    template_id: UUID,
    target_row_ids: Sequence[str],
) -> dict[str, Any]:
    """检查删除模板行的影响：返回受影响的规则数和企业数。

    调用方（add_version）删除已引用行前应先调用此接口，让前端展示影响后二次确认。
    """
    if not target_row_ids:
        return {"affected_rule_count": 0, "affected_entity_count": 0, "details": []}

    # 取所有引用该模板的活跃版本 ID
    version_ids = (await db.execute(
        sa.select(ConsolNoteDetailTemplateVersion.id)
        .where(ConsolNoteDetailTemplateVersion.template_id == template_id)
    )).scalars().all()

    if not version_ids:
        return {"affected_rule_count": 0, "affected_entity_count": 0, "details": []}

    # 查引用这些版本的活跃规则中，mappings 里包含被删 target_row_id 的规则
    rules = (await db.execute(
        sa.select(ConsolNoteMappingRule).where(
            ConsolNoteMappingRule.template_version_id.in_(version_ids),
            ConsolNoteMappingRule.is_active == sa.true(),
        )
    )).scalars().all()

    affected_rules: list[dict[str, Any]] = []
    affected_entity_node_keys: set[str] = set()

    target_set = set(str(rid) for rid in target_row_ids)
    for rule in rules:
        mappings_list = rule.mappings if isinstance(rule.mappings, list) else []
        hits = [m for m in mappings_list if str(m.get("target_row_id", "")) in target_set]
        if hits:
            affected_rules.append({
                "rule_id": str(rule.id),
                "section_id": rule.section_id,
                "source_structure_hash": rule.source_structure_hash,
                "hit_count": len(hits),
            })
            # 查引用该规则的企业绑定
            bindings = (await db.execute(
                sa.select(ConsolNoteMappingBinding.entity_node_key).where(
                    ConsolNoteMappingBinding.rule_id == rule.id,
                )
            )).scalars().all()
            affected_entity_node_keys.update(bindings)

    return {
        "affected_rule_count": len(affected_rules),
        "affected_entity_count": len(affected_entity_node_keys),
        "details": affected_rules,
    }


# ─── 内部辅助 ────────────────────────────────────────────────────────────────


def _validate_template_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """校验并规范化模板行。确保每行有 target_row_id、canonical_name、row_type。"""
    validated: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise TemplateServiceError(400, "INVALID_ROW", f"第 {i + 1} 行不是对象")
        canonical_name = str(row.get("canonical_name", "")).strip()
        if not canonical_name:
            raise TemplateServiceError(400, "MISSING_NAME", f"第 {i + 1} 行缺少 canonical_name")
        target_row_id = str(row.get("target_row_id", "")).strip()
        if not target_row_id:
            target_row_id = str(uuid.uuid4())
        row_type = str(row.get("row_type", "data")).strip()
        if row_type not in ("data", "total", "subtotal"):
            row_type = "data"
        aliases = row.get("aliases", [])
        if not isinstance(aliases, list):
            aliases = []
        aliases = [str(a).strip() for a in aliases if str(a).strip()]
        try:
            sort_order = int(row.get("sort_order", i * 10))
        except (TypeError, ValueError):
            sort_order = i * 10
        # V200: 推荐科目码——可选 string[]，不校验科目码格式
        rec_codes_raw = row.get("recommended_account_codes")
        rec_codes: list[str] | None = None
        if isinstance(rec_codes_raw, list):
            rec_codes = [str(c).strip() for c in rec_codes_raw if str(c).strip()]
            if not rec_codes:
                rec_codes = None
        validated.append({
            "target_row_id": target_row_id,
            "canonical_name": canonical_name,
            "aliases": aliases,
            "sort_order": sort_order,
            "row_type": row_type,
            # V200: 推荐科目码（可选，不校验格式）
            **({"recommended_account_codes": rec_codes} if rec_codes else {}),
        })
    return validated


async def _load_template(db: AsyncSession, template_id: UUID) -> ConsolNoteDetailTemplate | None:
    return (await db.execute(
        sa.select(ConsolNoteDetailTemplate).where(
            ConsolNoteDetailTemplate.id == template_id,
            ConsolNoteDetailTemplate.is_deleted == sa.false(),
        )
    )).scalar_one_or_none()


async def _get_latest_version(
    db: AsyncSession, template_id: UUID,
) -> ConsolNoteDetailTemplateVersion | None:
    return (await db.execute(
        sa.select(ConsolNoteDetailTemplateVersion)
        .where(ConsolNoteDetailTemplateVersion.template_id == template_id)
        .order_by(ConsolNoteDetailTemplateVersion.version_number.desc())
        .limit(1)
    )).scalar_one_or_none()


async def _count_affected_rules(
    db: AsyncSession, project_id: UUID, section_id: str, template_version_id: UUID,
) -> int:
    result = await db.execute(
        sa.select(sa.func.count()).select_from(ConsolNoteMappingRule).where(
            ConsolNoteMappingRule.project_id == project_id,
            ConsolNoteMappingRule.section_id == section_id,
            ConsolNoteMappingRule.template_version_id == template_version_id,
            ConsolNoteMappingRule.is_active == sa.true(),
        )
    )
    return result.scalar_one()


def _template_to_dict(
    tmpl: ConsolNoteDetailTemplate,
    latest_version: ConsolNoteDetailTemplateVersion | None = None,
) -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": str(tmpl.id),
        "template_type": tmpl.template_type,
        "section_id": tmpl.section_id,
        "name": tmpl.name,
        "visibility": tmpl.visibility,
        "created_by": str(tmpl.created_by) if tmpl.created_by else None,
        "created_at": tmpl.created_at.isoformat() if tmpl.created_at else None,
    }
    if latest_version is not None:
        d["latest_version"] = _version_to_dict(latest_version)
    return d


def _version_to_dict(v: ConsolNoteDetailTemplateVersion) -> dict[str, Any]:
    return {
        "id": str(v.id),
        "template_id": str(v.template_id),
        "version_number": v.version_number,
        "rows": v.rows if isinstance(v.rows, list) else [],
        "change_note": v.change_note,
        "created_by": str(v.created_by) if v.created_by else None,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }
