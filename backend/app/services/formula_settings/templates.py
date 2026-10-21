"""公式模板：订阅关系与模板定义读取（R13，design §16）。

模板行存 ``formula_setting``（layer=template）；每次发布冻结为 ``formula_template_version.snapshot``
（``{domain: {slot_key: definition}}``）。订阅已物化为本项目层行（``base_origin='template'``）。
暂缓（pinned）的订阅读订阅版本的快照，不跟随模板新版本。
"""
from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.formula_setting_models import (
    FormulaSetting,
    FormulaTemplate,
    FormulaTemplateSubscription,
    FormulaTemplateVersion,
)


async def active_subscription(db: AsyncSession, project_id: uuid.UUID,
                              domain: str) -> FormulaTemplateSubscription | None:
    return (await db.execute(sa.select(FormulaTemplateSubscription).where(
        FormulaTemplateSubscription.project_id == project_id,
        FormulaTemplateSubscription.domain == domain,
        FormulaTemplateSubscription.is_active == sa.true(),
    ))).scalars().first()


async def template_rows(db: AsyncSession, template_id: uuid.UUID, domain: str) -> dict[str, FormulaSetting]:
    rows = (await db.execute(sa.select(FormulaSetting).where(
        FormulaSetting.layer == "template", FormulaSetting.template_id == template_id,
        FormulaSetting.domain == domain, FormulaSetting.is_deleted == sa.false(),
    ))).scalars().all()
    return {r.slot_key: r for r in rows}


async def snapshot_definitions(db: AsyncSession, template_id: uuid.UUID, version: int,
                               domain: str) -> dict[str, dict]:
    snap = (await db.execute(sa.select(FormulaTemplateVersion.snapshot).where(
        FormulaTemplateVersion.template_id == template_id, FormulaTemplateVersion.version == version,
    ))).scalar_one_or_none()
    return dict((snap or {}).get(domain) or {})


async def subscribed_definitions(db: AsyncSession, sub: FormulaTemplateSubscription) -> tuple[dict[str, dict], int]:
    """订阅当前生效的模板定义与版本（暂缓订阅读快照）。"""
    if sub.pinned:
        return await snapshot_definitions(db, sub.template_id, sub.template_version, sub.domain), sub.template_version
    tpl = await db.get(FormulaTemplate, sub.template_id)
    rows = await template_rows(db, sub.template_id, sub.domain)
    return {k: dict(r.definition or {}) for k, r in rows.items()}, (tpl.version if tpl else sub.template_version)


async def current_template_definition(db: AsyncSession, project_id: uuid.UUID, domain: str,
                                      slot_key: str) -> dict[str, Any] | None:
    """本项目订阅的模板对该公式位的定义；未订阅或模板未定义该位时为 ``None``。"""
    sub = await active_subscription(db, project_id, domain)
    if sub is None:
        return None
    defs, version = await subscribed_definitions(db, sub)
    if slot_key not in defs:
        return None
    return {"definition": defs[slot_key], "version": version, "template_id": sub.template_id}
