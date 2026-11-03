# -*- coding: utf-8 -*-
"""HTML store 载荷列口径（spec oo-writeback-template-parity-closure R3 批 B3）。

前端各 store item 的载荷写在 ``checklist_responses`` 的哪一列并不统一：多数写 ``remark``；G1-2 / G3-2 / G6-5
只写 ``conclusion``；G 循环 storage contract（G4-7 / G5-2）两列同写、读时 ``conclusion`` 优先、``remark`` 兜底。
provider 用 ``PAYLOAD_COLUMN`` / ``PAYLOAD_COLUMN_MODE`` 声明（单一来源，契约 review.html_store 也取它）。

原先回写镜像（``store_mirror``）、出方向投影（``store_projection_response``）、采纳覆盖（``adopt_*``）一律
读写 ``remark`` ⇒ 只写 conclusion 的那几张两个方向都不通：出方向读到空，回写写进前端不读的列；两列同写的那一族
回写只改 remark，前端读 conclusion 看到的还是旧值。

口径（按 provider 声明推出，不另立第二份清单）：

* ``PAYLOAD_COLUMN == "conclusion"`` ⇒ 只读写 conclusion；
* ``PAYLOAD_COLUMN_MODE == "dual_write"`` ⇒ 读 conclusion 优先、remark 兜底，写两列（与前端
  ``readCanonicalRaw`` / ``buildCanonicalPayload`` 同口径；I4 前端读 remark 优先，两列同写后两种读法结果相同）；
* 其余 ⇒ 只读写 remark。SQL 与原各调用点逐字相同（原行为不变）。H 循环的
  ``dual_write_remark_and_conclusion`` 是「行数组在 remark、conclusion 另有他用」，不能当两列同写。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Mapping

REMARK: Final[str] = "remark"
CONCLUSION: Final[str] = "conclusion"
_KNOWN: Final[frozenset[str]] = frozenset({REMARK, CONCLUSION})


@dataclass(frozen=True)
class PayloadColumns:
    #: 读：按序取第一个非空白的列
    read_order: tuple[str, ...]
    #: 写：回写同时写的列
    write: tuple[str, ...]

    def __post_init__(self) -> None:
        bad = (set(self.read_order) | set(self.write)) - _KNOWN
        if bad or not self.read_order or not self.write:
            raise ValueError(f"store 载荷列口径非法：read={self.read_order!r} write={self.write!r}")

    def select_sql(self, *, limit: bool = False) -> str:
        cols = ", ".join(self.read_order)
        tail = " LIMIT 1" if limit else ""
        return f"SELECT {cols} FROM checklist_responses WHERE wp_id = :wp AND item_id = :item{tail}"

    def raw_of(self, result: Any) -> str | None:
        """``session.execute(select_sql)`` 的结果 → 该口径下的载荷原文（行不存在 ⇒ None）。

        单列口径走 ``scalar_one_or_none()``（与原调用点逐字等价，含空串原样返回）；多列口径取第一个非空白的列，
        都空白时退回最后一列的原值。
        """
        if len(self.read_order) == 1:
            value = result.scalar_one_or_none()
            return None if value is None else str(value)
        row: Mapping[str, Any] | None = result.mappings().first()
        if row is None:
            return None
        for column in self.read_order:
            value = row.get(column)
            if value is not None and str(value).strip():
                return str(value)
        last = row.get(self.read_order[-1])
        return None if last is None else str(last)

    @property
    def update_sql(self) -> str:
        sets = ", ".join(f"{c} = :val" for c in self.write)
        return (
            f"UPDATE checklist_responses SET {sets}, updated_at = now() "
            "WHERE wp_id = :wp AND item_id = :item"
        )

    @property
    def insert_sql(self) -> str:
        cols = ", ".join(self.write)
        vals = ", ".join(":val" for _ in self.write)
        return (
            "INSERT INTO checklist_responses "
            f"(id, project_id, wp_id, item_id, {cols}, created_at, updated_at) "
            f"VALUES (gen_random_uuid(), :pid, :wp, :item, {vals}, now(), now())"
        )


REMARK_ONLY: Final[PayloadColumns] = PayloadColumns((REMARK,), (REMARK,))
CONCLUSION_ONLY: Final[PayloadColumns] = PayloadColumns((CONCLUSION,), (CONCLUSION,))
DUAL_WRITE: Final[PayloadColumns] = PayloadColumns((CONCLUSION, REMARK), (CONCLUSION, REMARK))


def payload_columns_of(provider: Any) -> PayloadColumns:
    """provider 声明 → 载荷列口径（未声明 = remark，原行为）。声明了不认识的列直接抛，不静默退回 remark。"""
    column = str(getattr(provider, "PAYLOAD_COLUMN", REMARK) or REMARK)
    if column not in _KNOWN:
        raise ValueError(
            f"{getattr(provider, '__name__', provider)!r} 的 PAYLOAD_COLUMN={column!r} 不是 remark / conclusion"
        )
    if column == CONCLUSION:
        return CONCLUSION_ONLY
    if str(getattr(provider, "PAYLOAD_COLUMN_MODE", "") or "") == "dual_write":
        return DUAL_WRITE
    return REMARK_ONLY


def payload_columns_for_adapter(adapter_id: str) -> PayloadColumns:
    """adapter → 其回写镜像 bridge（``STORE_MERGE_REGISTRY`` 的 provider_module）的载荷列口径。

    与 ``store_mirror`` 取 bridge 的路径相同，采纳覆盖的快照 / 删除侧与回写镜像不会各认一列。
    无 store 计划的 adapter ⇒ remark（原行为）。
    """
    import importlib

    from app.services.workpaper_sync.store_item_registry import store_merge_plan_or_skip

    plan = store_merge_plan_or_skip(str(adapter_id))
    if plan is None:
        return REMARK_ONLY
    return payload_columns_of(
        importlib.import_module(f"app.services.workpaper_sync.{plan.provider_module}")
    )


async def read_payload(
    session: Any, *, wp_id: Any, item_id: str, columns: PayloadColumns, limit: bool = False
) -> str | None:
    """按口径读一个 store item 的载荷原文（行不存在 ⇒ None）。"""
    import sqlalchemy as sa

    result = await session.execute(
        sa.text(columns.select_sql(limit=limit)), {"wp": str(wp_id), "item": item_id}
    )
    return columns.raw_of(result)
