"""金标准 SQL 助手（advanced-query-linkage-closure design §10.2；实施计划 §0.13）。

金标准一律在测试内用独立 SQL 现算，不调用被测代码；数值随真库变化，测试里不写死。

- 🔴 本模块**不再提供项目代号**。原先写死的 9 个项目 UUID（华氏 / 和平药房 / 宜宾 / 辽宁 / 医疗器械 / 和平物流与三个
  【UAT】项目）2026-11-01 现算在 ``projects`` 表里全都查不到行，用例拿空集跟空金标准互相印证而假绿。真实分布判据改按
  数据能力动态解析（``project_picks``，夹具 ``picks``），写入与结构分支改在回滚事务里自建【测试】项目
  （``writable_projects``，夹具 ``new_project`` / ``writable_project`` / ``no_active_dataset_project``）。不要把代号加回来。
- ``AUDIT_YEAR``：只剩两种用法 —— 不经真实项目的合成世界（``pg_world`` 等）的年度，以及按项目名称定位的旧用例的
  年度；按能力解析出的项目一律用 ``Pick.audit_year``（不一定是 2025）。
- ``active_sql(alias)``：四表（tb_balance / tb_ledger / tb_aux_balance / tb_aux_ledger）的生效数据集口径，
  与 ``dataset_query.get_active_filter`` 同口径：有 active 数据集时按其中 ``activated_at`` 最新（空值在后）、
  其次 ``created_at`` 最新的一条过滤；没有 active 数据集时只按未删。参数名默认 ``:pid`` / ``:year``。
- ``LIVE_PROJECTS_SQL``：统计口径排除软删项目（跨项目汇总一律 JOIN 它）。
- ``Gold``：金标准读取器（夹具 ``gold``），每条查询独立连接、只读事务；``require_pg_only``：真库夹具的前置检查。
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

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
