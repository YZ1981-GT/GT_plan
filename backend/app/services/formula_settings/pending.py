"""待确认事项（``formula_sync_item``）的写入与读取（R4.4 / R5）。

同一项目同一公式位只保留一条 pending：再次发布时更新它的「新上游」，保留原基线与原因。
修订号 ``revision``（spec formula-hub-integrity-closure 需求 8.1，ADR-FHIC-11）：新建为 1，每次覆盖原子 +1，
三种来源（全局设置 / 公式模板 / 其他项目）一律携带并在列表输出；处理待确认以它为唯一 CAS 依据。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
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


#: 冲突目标 = 部分唯一索引 ``uq_formula_sync_item_pending``（V199，PG 与 SQLite 都声明）。谓词须是字面量：
#: 写成绑定参数时 PostgreSQL 推断不出仲裁索引。
_PENDING_INDEX = ["project_id", "domain", "slot_key"]
_PENDING_WHERE = "status = 'pending'"
_DIALECT_INSERTS = {"postgresql": pg_insert, "sqlite": sqlite_insert}


def _dialect_insert(db: AsyncSession):
    name = db.get_bind().dialect.name
    if name not in _DIALECT_INSERTS:
        raise RuntimeError(f"待确认事项的原子写入不支持数据库方言 {name}")
    return _DIALECT_INSERTS[name]


async def upsert_pending(db: AsyncSession, *, project_id: uuid.UUID, domain: str, slot_key: str,
                         slot_label: str, reason: str, base_definition: dict | None,
                         upstream_definition: dict | None, upstream_version: int | None,
                         local_definition: dict | None, publish_id: uuid.UUID | None,
                         upstream_origin: str = "global",
                         upstream_template_id: uuid.UUID | None = None) -> FormulaSyncItem:
    """新建或覆盖该公式位唯一的 pending：一条 ``INSERT … ON CONFLICT DO UPDATE … RETURNING``（ADR-FHIC-11）。

    新建：修订号 1，记下基线与原因。覆盖：换新上游、上游版本、本项目当前、发布记录与来源（标签非空才换），
    基线与原因不变，修订号在库内 +1 —— 两个会话同时覆盖拿到不同的修订号（2、3），同时新建则一个插入、
    一个转为覆盖（1、2），不抛唯一约束错误。返回 RETURNING 的行（同会话先前读到的同一行对象一并刷新）。
    """
    now = _now()
    stmt = _dialect_insert(db)(FormulaSyncItem).values(
        id=uuid.uuid4(), project_id=project_id, domain=domain, slot_key=slot_key, slot_label=slot_label,
        reason=reason, base_definition=_plain(base_definition), status="pending", revision=1,
        upstream_definition=_plain(upstream_definition), upstream_version=upstream_version,
        local_definition=_plain(local_definition), publish_id=publish_id, upstream_origin=upstream_origin,
        upstream_template_id=upstream_template_id, updated_at=now,
    )
    new = stmt.excluded
    stmt = stmt.on_conflict_do_update(
        index_elements=_PENDING_INDEX, index_where=sa.text(_PENDING_WHERE),
        set_={
            "upstream_definition": new.upstream_definition, "upstream_version": new.upstream_version,
            "local_definition": new.local_definition, "publish_id": new.publish_id,
            "upstream_origin": new.upstream_origin, "upstream_template_id": new.upstream_template_id,
            "slot_label": sa.func.coalesce(sa.func.nullif(new.slot_label, ""), FormulaSyncItem.slot_label),
            "revision": FormulaSyncItem.revision + 1, "updated_at": now,
        },
    ).returning(FormulaSyncItem)
    result = await db.execute(stmt, execution_options={"populate_existing": True})
    return result.scalars().one()


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
        "revision": item.revision,
        "publish_id": str(item.publish_id) if item.publish_id else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }
