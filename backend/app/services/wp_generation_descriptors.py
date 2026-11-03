"""两阶段生成 Phase A 的只读描述符解析。

把模板集旧路径中的名称/循环/项目模板覆盖规则集中成单一函数；本模块不创建底稿行、不落文件。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workpaper_models import WpTemplate, WpTemplateSet
from app.services.procedure_scope_retention import GenerationPlan, plan_generation
from app.services.template_engine import select_generation_codes
from app.services.wp_name_source import resolve_wp_name

_DATA = Path(__file__).resolve().parent.parent.parent / "data"


@dataclass(frozen=True)
class GenerationDescriptor:
    wp_code: str
    wp_name: str
    audit_cycle: str | None
    library_file: str | None = None


@lru_cache(maxsize=1)
def _template_library() -> dict[str, dict[str, Any]]:
    path = _DATA / "gt_template_library.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    rows = raw.get("templates", []) if isinstance(raw, dict) else raw
    return {
        str(row.get("code") or row.get("wp_code")): row
        for row in rows if isinstance(row, dict) and (row.get("code") or row.get("wp_code"))
    }


@lru_cache(maxsize=1)
def _wp_names() -> dict[str, str]:
    path = _DATA / "wp_account_mapping.json"
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    rows = raw.get("mappings", []) if isinstance(raw, dict) else raw
    return {
        str(row["wp_code"]): str(row["wp_name"])
        for row in rows if isinstance(row, dict) and row.get("wp_code") and row.get("wp_name")
    }


async def _project_template_files(db: AsyncSession, project_id: UUID) -> dict[str, str]:
    from app.models.template_library_models import ProjectTemplateSelection, TemplateLibraryItem

    stmt = (
        sa.select(TemplateLibraryItem.wp_code, TemplateLibraryItem.file_path)
        .join(ProjectTemplateSelection, ProjectTemplateSelection.template_id == TemplateLibraryItem.id)
        .where(
            ProjectTemplateSelection.project_id == project_id,
            ProjectTemplateSelection.is_active == sa.true(),
            TemplateLibraryItem.wp_code.isnot(None),
            TemplateLibraryItem.file_path.isnot(None),
            TemplateLibraryItem.is_deleted == sa.false(),
        )
    )
    try:
        async with db.begin_nested():
            rows = (await db.execute(stmt)).all()
    except SQLAlchemyError:
        return {}
    return {str(code): str(path) for code, path in rows if code and path}


async def _latest_templates(db: AsyncSession, codes: list[str]) -> dict[str, WpTemplate]:
    if not codes:
        return {}
    try:
        latest = (
            sa.select(
                WpTemplate.template_code,
                sa.func.max(WpTemplate.created_at).label("max_created"),
            )
            .where(WpTemplate.template_code.in_(codes), WpTemplate.is_deleted == sa.false())
            .group_by(WpTemplate.template_code)
            .subquery()
        )
        async with db.begin_nested():
            rows = (await db.execute(
                sa.select(WpTemplate).join(
                    latest,
                    sa.and_(
                        WpTemplate.template_code == latest.c.template_code,
                        WpTemplate.created_at == latest.c.max_created,
                    ),
                ).where(WpTemplate.is_deleted == sa.false())
            )).scalars().all()
    except SQLAlchemyError:
        return {}
    return {str(row.template_code): row for row in rows}


async def descriptors_for_codes(
    db: AsyncSession,
    project_id: UUID,
    codes: list[str],
) -> list[GenerationDescriptor]:
    library = _template_library()
    names = _wp_names()
    overrides = await _project_template_files(db, project_id)
    templates = await _latest_templates(db, codes)
    result: list[GenerationDescriptor] = []
    for code in codes:
        row = library.get(code, {})
        template = templates.get(code)
        explicit_name = template.template_name if template else (row.get("name") or row.get("wp_name"))
        name = resolve_wp_name(code, explicit_name, names.get(code))
        cycle = (template.audit_cycle if template else (row.get("cycle_prefix") or row.get("audit_cycle"))) or None
        if not cycle:
            cycle = code[:1] if code[:1].isalpha() else None
        result.append(GenerationDescriptor(code, name, cycle, overrides.get(code)))
    return result


async def prepare_template_set_descriptors(
    db: AsyncSession,
    project_id: UUID,
    template_set_id: UUID,
    selected_codes: list[str] | None,
) -> tuple[GenerationPlan, list[GenerationDescriptor], list[str], list[str]]:
    """返回 plan、仅待建描述符、ignored、模板集交集编码；调用期在项目锁事务内。"""
    template_set = (await db.execute(sa.select(WpTemplateSet).where(
        WpTemplateSet.id == template_set_id,
        WpTemplateSet.is_deleted == sa.false(),
    ))).scalar_one_or_none()
    if template_set is None:
        raise ValueError("模板集不存在")
    codes, ignored = select_generation_codes(template_set.template_codes or [], selected_codes)
    plan = await plan_generation(db, project_id, codes)
    return plan, await descriptors_for_codes(db, project_id, plan.to_create), ignored, codes


async def prepare_code_descriptors(
    db: AsyncSession,
    project_id: UUID,
    requested_codes: list[str],
) -> tuple[GenerationPlan, list[GenerationDescriptor], list[str]]:
    codes = list(dict.fromkeys(code for code in requested_codes if code))
    plan = await plan_generation(db, project_id, codes)
    return plan, await descriptors_for_codes(db, project_id, plan.to_create), codes
