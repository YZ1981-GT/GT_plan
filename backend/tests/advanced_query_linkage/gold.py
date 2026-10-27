"""金标准 SQL 助手与真库项目代号（advanced-query-linkage-closure design §10.2；实施计划 §0.13）。

金标准一律在测试内用独立 SQL 现算，不调用被测代码；数值随真库变化，测试里不写死。

- 项目代号：只读的真实项目（只做 SELECT 与 R4.2 的 NOWAIT 加锁验证）与可写入的【UAT】项目（只在回滚事务里写）。
- ``active_sql(alias)``：四表（tb_balance / tb_ledger / tb_aux_balance / tb_aux_ledger）的生效数据集口径，
  与 ``dataset_query.get_active_filter`` 同口径：有 active 数据集时按其中 ``activated_at`` 最新（空值在后）、
  其次 ``created_at`` 最新的一条过滤；没有 active 数据集时只按未删。参数名默认 ``:pid`` / ``:year``。
- ``LIVE_PROJECTS_SQL``：统计口径排除软删项目（跨项目汇总一律 JOIN 它）。
- ``Gold``：金标准读取器（夹具 ``gold``），每条查询独立连接、只读事务；``require_pg_only``：真库夹具的前置检查。
"""
from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

# ── 真实项目（只读）──
HS = uuid.UUID("005a6f2d-cecd-4e30-bcbd-9fb01236c194")  # 华氏
HP = uuid.UUID("5942c12e-65fb-4187-ace3-79d45a90cb53")  # 重庆和平药房连锁
YB = uuid.UUID("14fb8c10-9462-45f6-8f56-d023f5b6df13")  # 宜宾临港店
LN = uuid.UUID("d9295a0c-f347-4aa5-a1d1-faf7847d379b")  # 辽宁卫生服务（现行项目；旧 37814426 已软删）
MD = uuid.UUID("5e193c68-f53c-4e95-8d03-5d9c996c402d")  # 医疗器械
WL = uuid.UUID("94031b0e-b9d5-4f2d-ac25-2a13000cbaca")  # 和平物流（tb_balance 有行、没有 active 数据集）

# ── 可写入（只在回滚事务里写）──
UA = uuid.UUID("0c0f8b87-1cb6-4759-b589-413fa88ce215")  # 【UAT】子公司A
UB = uuid.UUID("a3132905-2600-41c8-a590-0008aedd8a3b")  # 【UAT】子公司B
UP = uuid.UUID("e07ff3df-0b3d-4e33-b3b7-467ad03938e1")  # 【UAT】合成集团母公司（consolidated）

WRITABLE_PROJECTS: frozenset[uuid.UUID] = frozenset({UA, UB, UP})
AUDIT_YEAR = 2025

#: 未软删的项目（统计排除软删项目）
LIVE_PROJECTS_SQL = "SELECT id FROM projects WHERE NOT is_deleted"


def require_pg_only(node: Any) -> None:
    """真库夹具的前置：用例必须带 ``pytest.mark.pg_only``（否则在 SQLite 环境里会误连库、或被跳过而无人察觉）。"""
    if node.get_closest_marker("pg_only") is None:
        pytest.fail(f"{node.nodeid} 用到真库夹具，必须带 pytest.mark.pg_only")


class Gold:
    """金标准读取器：每条查询一个独立连接上的只读事务，结束回滚。"""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine

    async def _run(self, sql: str, params: Mapping[str, Any]) -> list[Any]:
        async with self.engine.connect() as conn:
            await conn.exec_driver_sql("SET TRANSACTION READ ONLY")
            try:
                return list((await conn.execute(text(sql), dict(params))).all())
            finally:
                await conn.rollback()

    async def rows(self, sql: str, **params: Any) -> list[tuple]:
        return [tuple(row) for row in await self._run(sql, params)]

    async def scalar(self, sql: str, **params: Any) -> Any:
        rows = await self._run(sql, params)
        if len(rows) != 1 or len(rows[0]) != 1:
            raise AssertionError(f"金标准应恰好一行一列，实得 {len(rows)} 行：{sql}")
        return rows[0][0]


def active_sql(alias: str = "t", *, pid: str = ":pid", year: str = ":year") -> str:
    """四表生效数据集口径的 WHERE 片段（§0.13 的 ``ACTIVE(t)``），``alias`` 为四表之一的别名。"""
    return (
        f"{alias}.project_id = {pid} AND {alias}.year = {year} AND NOT {alias}.is_deleted AND ("
        f"{alias}.dataset_id = (SELECT d.id FROM ledger_datasets d WHERE d.project_id = {pid} AND d.year = {year} "
        "AND d.status = 'active' ORDER BY d.activated_at DESC NULLS LAST, d.created_at DESC LIMIT 1) "
        f"OR NOT EXISTS (SELECT 1 FROM ledger_datasets d2 WHERE d2.project_id = {pid} AND d2.year = {year} "
        "AND d2.status = 'active'))"
    )
