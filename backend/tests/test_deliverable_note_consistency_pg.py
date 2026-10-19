"""check_note_consistency 保存点隔离 —— 真实 PostgreSQL 守卫（deliverable-writeback-and-online-edit-integrity 复盘修复）。

合成 SQLite / mock 测不出：PG 上一条语句失败会让整个事务 aborted，build_readiness 内部吞掉异常也救不回来，
调用方随后的导出写入全部失败（「fail-open」实际是 fail-500）。
故障注入在 build_readiness 的**下一层**（latest_findings_by_section 执行非法 SQL 并吞掉，与生产代码同形），断言：
1. check_note_consistency 不抛、照常返回结论；
2. 同一会话之后的查询照常可用（= 已回滚到保存点，调用方事务没停在 aborted）。
只读真实项目；结尾 rollback，不改数据。
"""
from __future__ import annotations

from uuid import UUID

import pytest
import sqlalchemy as sa

from app.core.database import async_session
from app.services import note_readiness_service as nrs
from app.services.deliverable_note_consistency import check_note_consistency

pytestmark = pytest.mark.pg_only

PROJECT = UUID("0ec33ac9-3de5-4e65-b3bf-f9dccd7b2a49")  # 重药安徽（只读）


@pytest.mark.asyncio
async def test_swallowed_failure_inside_readiness_does_not_abort_caller_transaction(monkeypatch):
    async def _broken_findings(db, project_id, year):
        try:
            await db.execute(sa.text("SELECT definitely_missing_column FROM note_validation_results LIMIT 1"))
        except Exception:  # noqa: BLE001 — 与生产代码同形：吞掉，PG 事务此时已 aborted
            pass
        return {}, None

    monkeypatch.setattr(nrs, "latest_findings_by_section", _broken_findings)
    async with async_session() as db:
        try:
            result = await check_note_consistency(db, PROJECT, 2025)
            assert set(result) == {"consistent", "never_synced", "stale"}
            # 🔴 关键：调用方的事务仍可用（不回滚到保存点，这里报 InFailedSqlTransaction）
            assert (await db.execute(sa.text("SELECT 1"))).scalar() == 1
        finally:
            await db.rollback()
