"""R11.1：时间线审计源按年度过滤（formula-hub-release-blockers）。

修复前 `_audit_log_events` 接收 year 参数但 SQL 不按年度过滤，
`/formula-timeline/{project}/2025` 会混入 2024 的条目。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from tests.formula_settings._env import make_db


async def _insert_audit(db: AsyncSession, *, project_id: uuid.UUID, year: str) -> uuid.UUID:
    """往 audit_log_entries 插一条公式变更审计记录。"""
    from app.models.audit_log_models import AuditLogEntry

    entry_id = uuid.uuid4()
    db.add(AuditLogEntry(
        id=entry_id,
        user_id=None,
        action_type="formula.changed",
        object_type="formula_setting",
        object_id=None,
        payload={"project_id": str(project_id), "year": year, "event_type": "formula_changed",
                 "module": "report", "action": "update", "row_code": "BS-001",
                 "old_formula": "", "new_formula": "TB('1001','期末余额')"},
        prev_hash="",
        entry_hash=uuid.uuid4().hex,
        ts=datetime.now(timezone.utc),
    ))
    await db.flush()
    return entry_id


@pytest.mark.asyncio
async def test_timeline_only_returns_specified_year():
    """插入 2025 和 2024 两条审计记录，调用 build_timeline(year=2025)，只返回 2025。"""
    from app.services.formula_timeline_service import build_timeline

    async with make_db() as factory:
        async with factory() as db:
            pid = uuid.uuid4()
            id_2025 = await _insert_audit(db, project_id=pid, year="2025")
            id_2024 = await _insert_audit(db, project_id=pid, year="2024")
            await db.commit()

        async with factory() as db:
            result = await build_timeline(db, pid, 2025, limit=100)
            events = result["events"]
            # 只应有 2025 的那一条 formula_changed
            formula_events = [e for e in events if e["type"] == "formula_changed"]
            assert len(formula_events) == 1
            assert formula_events[0]["detail"]["year"] == "2025"


@pytest.mark.asyncio
async def test_timeline_excludes_entries_without_year():
    """旧条目没有 year 字段 → 不出现在按年度查询的结果中。"""
    from app.services.formula_timeline_service import build_timeline

    async with make_db() as factory:
        async with factory() as db:
            pid = uuid.uuid4()
            from app.models.audit_log_models import AuditLogEntry
            db.add(AuditLogEntry(
                id=uuid.uuid4(), user_id=None, action_type="formula.changed",
                object_type="formula_setting", object_id=None,
                payload={"project_id": str(pid), "event_type": "formula_changed",
                         "module": "report", "action": "update", "row_code": "BS-002",
                         "old_formula": "", "new_formula": "ROW('BS-001')"},
                prev_hash="", entry_hash=uuid.uuid4().hex,
                ts=datetime.now(timezone.utc),
            ))
            await db.commit()

        async with factory() as db:
            result = await build_timeline(db, pid, 2025, limit=100)
            formula_events = [e for e in result["events"] if e["type"] == "formula_changed"]
            assert formula_events == [], "没有 year 字段的旧条目不应出现"
