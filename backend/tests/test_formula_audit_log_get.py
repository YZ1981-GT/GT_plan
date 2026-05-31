"""formula_audit_log GET 端点单元测试

验证 GET /api/formula-audit-log/{project_id}/{year} 改查 audit_log_entries
WHERE action_type='formula.changed'，payload JSONB 过滤 module/row_code。

Task 15: formula_audit_log GET 改查哈希链
需求: 4.3
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

# SQLite 兼容 JSONB + ARRAY
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

import app.models.core  # noqa: F401
import app.models.audit_log_models  # noqa: F401

from app.models.audit_log_models import AuditLogEntry

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每个测试独立的内存数据库会话。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        tables_to_create = [
            Base.metadata.tables["users"],
            Base.metadata.tables["audit_log_entries"],
        ]
        await conn.run_sync(Base.metadata.create_all, tables=tables_to_create)
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


# --------------------------------------------------------------------------
# 辅助：插入测试数据
# --------------------------------------------------------------------------

async def _insert_formula_changed_entry(
    db: AsyncSession,
    project_id: str,
    module: str = "report",
    row_code: str = "R001",
    action: str = "update",
    old_formula: str = "TB('1002','期末余额')",
    new_formula: str = "TB('1002','期末余额')+TB('1003','期末余额')",
    result_value: str = "1000.00",
) -> uuid.UUID:
    """插入一条 formula.changed 审计日志条目。"""
    entry_id = uuid.uuid4()
    entry = AuditLogEntry(
        id=entry_id,
        ts=datetime.now(timezone.utc),
        user_id=uuid.uuid4(),
        session_id=None,
        action_type="formula.changed",
        object_type="report_config",
        object_id=None,
        payload={
            "project_id": project_id,
            "event_type": "formula_changed",
            "module": module,
            "row_code": row_code,
            "action": action,
            "old_formula": old_formula,
            "new_formula": new_formula,
            "result_value": result_value,
            "trace": ["TB('1002','期末余额') → 500.00"],
        },
        ip=None,
        ua=None,
        trace_id=None,
        prev_hash="0" * 64,
        entry_hash=uuid.uuid4().hex + uuid.uuid4().hex[:32],
    )
    db.add(entry)
    await db.flush()
    return entry_id


async def _insert_other_action_entry(db: AsyncSession, project_id: str) -> uuid.UUID:
    """插入一条非 formula.changed 的审计日志（不应被 GET 返回）。"""
    entry_id = uuid.uuid4()
    entry = AuditLogEntry(
        id=entry_id,
        ts=datetime.now(timezone.utc),
        user_id=uuid.uuid4(),
        session_id=None,
        action_type="archive_unarchive",
        object_type="project",
        object_id=None,
        payload={"project_id": project_id, "event_type": "archive_unarchive", "reason": "test", "previous_status": "active"},
        ip=None,
        ua=None,
        trace_id=None,
        prev_hash="0" * 64,
        entry_hash=uuid.uuid4().hex + uuid.uuid4().hex[:32],
    )
    db.add(entry)
    await db.flush()
    return entry_id


# --------------------------------------------------------------------------
# 测试
# --------------------------------------------------------------------------

class TestFormulaAuditLogGet:
    """GET /api/formula-audit-log/{project_id}/{year} 端点测试。"""

    @pytest.mark.asyncio
    async def test_returns_formula_changed_entries(self, db_session: AsyncSession):
        """查询返回 action_type='formula.changed' 的条目。"""
        pid = str(uuid.uuid4())
        await _insert_formula_changed_entry(db_session, pid, module="report", row_code="R001")
        await _insert_formula_changed_entry(db_session, pid, module="report", row_code="R002")
        await _insert_other_action_entry(db_session, pid)  # 不应返回
        await db_session.commit()

        # 直接调用路由函数测试
        from app.routers.formula_audit_log import get_audit_log

        result = await get_audit_log(pid, 2025, db=db_session)
        assert len(result) == 2
        # 验证返回结构
        for item in result:
            assert "id" in item
            assert "module" in item
            assert "row_code" in item
            assert "action" in item
            assert "old_formula" in item
            assert "new_formula" in item
            assert "result_value" in item
            assert "trace" in item
            assert "created_at" in item

    @pytest.mark.asyncio
    async def test_filters_by_module(self, db_session: AsyncSession):
        """module 参数过滤 payload->>'module'。"""
        pid = str(uuid.uuid4())
        await _insert_formula_changed_entry(db_session, pid, module="report", row_code="R001")
        await _insert_formula_changed_entry(db_session, pid, module="consol", row_code="C001")
        await db_session.commit()

        from app.routers.formula_audit_log import get_audit_log

        result = await get_audit_log(pid, 2025, module="consol", db=db_session)
        assert len(result) == 1
        assert result[0]["module"] == "consol"
        assert result[0]["row_code"] == "C001"

    @pytest.mark.asyncio
    async def test_filters_by_row_code(self, db_session: AsyncSession):
        """row_code 参数过滤 payload->>'row_code'。"""
        pid = str(uuid.uuid4())
        await _insert_formula_changed_entry(db_session, pid, module="report", row_code="R001")
        await _insert_formula_changed_entry(db_session, pid, module="report", row_code="R002")
        await db_session.commit()

        from app.routers.formula_audit_log import get_audit_log

        result = await get_audit_log(pid, 2025, row_code="R002", db=db_session)
        assert len(result) == 1
        assert result[0]["row_code"] == "R002"

    @pytest.mark.asyncio
    async def test_response_structure_matches_old_table(self, db_session: AsyncSession):
        """返回结构与旧 formula_audit_log 表完全一致（前端零改动）。"""
        pid = str(uuid.uuid4())
        await _insert_formula_changed_entry(
            db_session, pid,
            module="report", row_code="R001", action="execute",
            old_formula="TB('1002','期末余额')",
            new_formula="TB('1002','期末余额')+TB('1003','期末余额')",
            result_value="1500.50",
        )
        await db_session.commit()

        from app.routers.formula_audit_log import get_audit_log

        result = await get_audit_log(pid, 2025, db=db_session)
        assert len(result) == 1
        entry = result[0]
        assert entry["module"] == "report"
        assert entry["row_code"] == "R001"
        assert entry["action"] == "execute"
        assert entry["old_formula"] == "TB('1002','期末余额')"
        assert entry["new_formula"] == "TB('1002','期末余额')+TB('1003','期末余额')"
        assert entry["result_value"] == 1500.50
        assert entry["trace"] == ["TB('1002','期末余额') → 500.00"]
        assert entry["created_at"] is not None

    @pytest.mark.asyncio
    async def test_empty_result_for_unknown_project(self, db_session: AsyncSession):
        """未知 project_id 返回空列表。"""
        pid = str(uuid.uuid4())
        await _insert_formula_changed_entry(db_session, pid, module="report", row_code="R001")
        await db_session.commit()

        from app.routers.formula_audit_log import get_audit_log

        result = await get_audit_log(str(uuid.uuid4()), 2025, db=db_session)
        assert result == []

    @pytest.mark.asyncio
    async def test_limit_parameter(self, db_session: AsyncSession):
        """limit 参数限制返回条数。"""
        pid = str(uuid.uuid4())
        for i in range(5):
            await _insert_formula_changed_entry(db_session, pid, row_code=f"R{i:03d}")
        await db_session.commit()

        from app.routers.formula_audit_log import get_audit_log

        result = await get_audit_log(pid, 2025, limit=3, db=db_session)
        assert len(result) == 3
