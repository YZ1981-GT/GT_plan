"""底稿公式写入口接入公式设置同步内核（spec formula-management-repair-closure R2）。

``wp_formula`` 的 custom / preset / reference 行就是底稿域的「本项目适配」层（``domain_stores.WpStore``）。
公式管理里保存 / 删除底稿公式、底稿内用户公式的写入，原先只写行与 ``base_*`` 跟踪列，不登记变化 ⇒
用到该底稿编码的底稿不标 ``prefill_stale``、传播事件不发、联动状态看不到 —— 与「全局发布 / 本项目适配接口」
两条路径口径不一。这里给路由用：执行字段（表达式 / 公式类型）真的变了才登记，同事务标过期并入队；
路由 ``commit`` 之后调 :func:`publish`。公式位口径与 ``/effective`` 一致：``{wp_index.wp_code}|{sheet}|{cell}``。
"""
from __future__ import annotations

import uuid
from typing import Any, Iterable, Mapping

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.formula_settings import outbox
from app.services.formula_settings.definitions import same_exec
from app.services.formula_settings.domain_stores import wp_slot

SOURCE = "project_edit"


def exec_def(row: Any) -> dict[str, Any] | None:
    """一行 ``wp_formula`` 的执行字段快照（普通 dict：服务层 refresh 之后同一 ORM 对象已是新值）。"""
    if row is None:
        return None
    return {"expression": getattr(row, "expression", None), "formula_type": getattr(row, "formula_type", None)}


def changed(old: Mapping[str, Any] | None, new: Mapping[str, Any] | None) -> bool:
    """有效定义是否变化（只比执行字段，与同步内核同口径）。"""
    return not same_exec("wp", old, new)


def is_project_layer(row: Any) -> bool:
    """该行是否属于底稿域的本项目层（custom / preset / reference；其他来源的行删了不改有效定义）。"""
    from app.services.formula_settings.domain_stores import WP_SOURCES

    return row is not None and getattr(row, "formula_source", None) in WP_SOURCES


async def wp_code_of(db: AsyncSession, wp_index_id: uuid.UUID | None) -> str | None:
    """底稿的 ``wp_index.wp_code``（同步内核按它聚合项目层；不用去后缀的主编码）。"""
    if wp_index_id is None:
        return None
    from app.models.workpaper_models import WpIndex

    return (await db.execute(sa.select(WpIndex.wp_code).where(WpIndex.id == wp_index_id))).scalar_one_or_none()


async def record_cells(db: AsyncSession, *, project_id: uuid.UUID, wp_code: str | None,
                       cells: Iterable[tuple[str | None, str | None]]) -> list[str]:
    """登记变化的格（只 flush，不 commit）；返回登记的公式位。"""
    slots = sorted({wp_slot(wp_code, sheet or "", cell) for sheet, cell in cells if cell}) if wp_code else []
    if slots:
        await outbox.record_changes(db, domain="wp", source=SOURCE,
                                    events=[{"project_id": str(project_id), "slot_keys": slots}])
    return slots


async def publish(db: AsyncSession) -> dict[str, Any]:
    """路由 ``commit`` 之后调用：交后台投递（失败由派发口记 failed，worker 重放）。"""
    return await outbox.publish_pending(db)
