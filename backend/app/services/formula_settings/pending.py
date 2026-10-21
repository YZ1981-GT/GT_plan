"""待确认事项（``formula_sync_item``）的写入与读取（R4.4 / R5）。

同一项目同一公式位只保留一条 pending：再次发布时更新它的「新上游」，保留原基线与原因。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.formula_setting_models import FormulaSyncItem
from app.services.formula_settings.definitions import display_formula

REASON_LABELS = {"conflict": "冲突", "deferred": "管理员暂缓"}
ORIGIN_LABELS = {"global": "全局设置", "template": "公式模板", "project": "其他项目"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _plain(definition: dict | None) -> dict | None:
    if definition is None:
        return None
    return {k: v for k, v in dict(definition).items() if k != "_structure"}


async def find_pending(db: AsyncSession, project_id: uuid.UUID, domain: str,
                       slot_key: str) -> FormulaSyncItem | None:
    return (await db.execute(sa.select(FormulaSyncItem).where(
        FormulaSyncItem.project_id == project_id,
        FormulaSyncItem.domain == domain,
        FormulaSyncItem.slot_key == slot_key,
        FormulaSyncItem.status == "pending",
    ))).scalars().first()


async def upsert_pending(db: AsyncSession, *, project_id: uuid.UUID, domain: str, slot_key: str,
                         slot_label: str, reason: str, base_definition: dict | None,
                         upstream_definition: dict | None, upstream_version: int | None,
                         local_definition: dict | None, publish_id: uuid.UUID | None,
                         upstream_origin: str = "global",
                         upstream_template_id: uuid.UUID | None = None) -> FormulaSyncItem:
    item = await find_pending(db, project_id, domain, slot_key)
    if item is None:
        item = FormulaSyncItem(
            project_id=project_id, domain=domain, slot_key=slot_key, slot_label=slot_label,
            reason=reason, base_definition=_plain(base_definition), status="pending",
        )
        db.add(item)
    item.upstream_definition = _plain(upstream_definition)
    item.upstream_version = upstream_version
    item.local_definition = _plain(local_definition)
    item.publish_id = publish_id
    item.upstream_origin = upstream_origin
    item.upstream_template_id = upstream_template_id
    item.slot_label = slot_label or item.slot_label
    item.updated_at = _now()
    await db.flush()
    return item


async def close_pending(db: AsyncSession, project_id: uuid.UUID, domain: str, slot_keys: Iterable[str], *,
                        status: str = "superseded", resolution: str | None = None,
                        user_id: uuid.UUID | None = None) -> int:
    keys = list(dict.fromkeys(slot_keys))
    if not keys:
        return 0
    values: dict[str, Any] = {"status": status, "updated_at": _now()}
    if status == "resolved":
        values.update(resolution=resolution, resolved_by=user_id, resolved_at=_now())
    result = await db.execute(sa.update(FormulaSyncItem).where(
        FormulaSyncItem.project_id == project_id,
        FormulaSyncItem.domain == domain,
        FormulaSyncItem.slot_key.in_(keys),
        FormulaSyncItem.status == "pending",
    ).values(**values).execution_options(synchronize_session=False))
    return int(result.rowcount or 0)


async def list_pending(db: AsyncSession, project_id: uuid.UUID, domain: str | None = None) -> list[FormulaSyncItem]:
    q = sa.select(FormulaSyncItem).where(FormulaSyncItem.project_id == project_id,
                                         FormulaSyncItem.status == "pending")
    if domain:
        q = q.where(FormulaSyncItem.domain == domain)
    return list((await db.execute(q.order_by(FormulaSyncItem.domain, FormulaSyncItem.slot_key))).scalars().all())


async def count_pending(db: AsyncSession, project_id: uuid.UUID) -> int:
    return int((await db.execute(sa.select(sa.func.count()).select_from(FormulaSyncItem).where(
        FormulaSyncItem.project_id == project_id, FormulaSyncItem.status == "pending"))).scalar() or 0)


def item_to_dict(item: FormulaSyncItem) -> dict[str, Any]:
    d = item.domain
    return {
        "id": str(item.id),
        "project_id": str(item.project_id),
        "domain": d,
        "slot_key": item.slot_key,
        "slot_label": item.slot_label or item.slot_key,
        "reason": item.reason,
        "reason_label": REASON_LABELS.get(item.reason, item.reason),
        "upstream_origin": item.upstream_origin,
        "upstream_origin_label": ORIGIN_LABELS.get(item.upstream_origin, item.upstream_origin),
        "upstream_template_id": str(item.upstream_template_id) if item.upstream_template_id else None,
        "base_definition": item.base_definition,
        "upstream_definition": item.upstream_definition,
        "upstream_deleted": item.upstream_definition is None,
        "local_definition": item.local_definition,
        "base_formula": display_formula(d, item.base_definition),
        "upstream_formula": display_formula(d, item.upstream_definition) if item.upstream_definition is not None
        else "（已删除）",
        "local_formula": display_formula(d, item.local_definition),
        "upstream_version": item.upstream_version,
        "publish_id": str(item.publish_id) if item.publish_id else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }
