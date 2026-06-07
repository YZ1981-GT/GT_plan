"""审计日志统一写入 helper 单元测试

验证 append_audit_log 函数 + 8 种 event_type schema 校验。
Task 0.5: audit_log_helper 统一写入
Task 14: formula_changed schema + 写入收口
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

# SQLite 兼容 JSONB + ARRAY
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

# 仅注册审计日志测试所需的模型
import app.models.core  # noqa: F401
import app.models.audit_log_models  # noqa: F401

from app.models.audit_log_models import AuditLogEntry
from app.services.audit_log_helper import (
    AuditLogPayload,
    EVENT_TYPE_SCHEMAS,
    GENESIS_HASH,
    EventType,
    append_audit_log,
    validate_event_type_details,
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每个测试独立的内存数据库会话。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        # 仅创建测试所需的表（避免其他模型的 PG 特有语法在 SQLite 报错）
        tables_to_create = [
            Base.metadata.tables["users"],
            Base.metadata.tables["audit_log_entries"],
        ]
        await conn.run_sync(
            Base.metadata.create_all, tables=tables_to_create
        )
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


# --------------------------------------------------------------------------
# 基础功能测试
# --------------------------------------------------------------------------


class TestAppendAuditLog:
    """append_audit_log 基础功能测试。"""

    @pytest.mark.asyncio
    async def test_basic_write_returns_uuid(self, db_session: AsyncSession):
        """基本写入返回有效 UUID。"""
        payload: AuditLogPayload = {
            "user_id": uuid.uuid4(),
            "project_id": uuid.uuid4(),
            "action": "test_action",
            "resource_type": "test_resource",
            "resource_id": str(uuid.uuid4()),
            "details": {"event_type": "archive_unarchive", "reason": "测试", "previous_status": "archived"},
        }
        entry_id = await append_audit_log(db_session, payload)
        assert isinstance(entry_id, uuid.UUID)

    @pytest.mark.asyncio
    async def test_entry_persisted_in_db(self, db_session: AsyncSession):
        """写入后可从数据库查询到条目。"""
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        payload: AuditLogPayload = {
            "user_id": user_id,
            "project_id": project_id,
            "action": "create",
            "resource_type": "workpaper",
            "resource_id": str(uuid.uuid4()),
            "details": {"event_type": "delete_with_confirm", "object_type": "底稿", "object_name": "D2-1", "soft_or_hard": "soft", "recoverable": True},
        }
        entry_id = await append_audit_log(db_session, payload)
        await db_session.commit()

        from sqlalchemy import select

        stmt = select(AuditLogEntry).where(AuditLogEntry.id == entry_id)
        result = await db_session.execute(stmt)
        entry = result.scalar_one()

        assert entry.user_id == user_id
        assert entry.action_type == "create"
        assert entry.object_type == "workpaper"
        assert entry.payload["event_type"] == "delete_with_confirm"

    @pytest.mark.asyncio
    async def test_hash_chain_genesis(self, db_session: AsyncSession):
        """第一条记录的 prev_hash 为创世哈希。"""
        payload: AuditLogPayload = {
            "user_id": uuid.uuid4(),
            "project_id": uuid.uuid4(),
            "action": "first_action",
            "resource_type": "project",
            "resource_id": None,
            "details": {},
        }
        entry_id = await append_audit_log(db_session, payload)
        await db_session.commit()

        from sqlalchemy import select

        stmt = select(AuditLogEntry).where(AuditLogEntry.id == entry_id)
        result = await db_session.execute(stmt)
        entry = result.scalar_one()

        assert entry.prev_hash == GENESIS_HASH
        assert len(entry.entry_hash) == 64

    @pytest.mark.asyncio
    async def test_hash_chain_continuity(self, db_session: AsyncSession):
        """连续写入两条记录，第二条的 prev_hash 等于第一条的 entry_hash。"""
        project_id = uuid.uuid4()

        payload1: AuditLogPayload = {
            "user_id": uuid.uuid4(),
            "project_id": project_id,
            "action": "action_1",
            "resource_type": "project",
            "resource_id": None,
            "details": {"project_id": str(project_id)},
        }
        id1 = await append_audit_log(db_session, payload1)
        await db_session.flush()

        payload2: AuditLogPayload = {
            "user_id": uuid.uuid4(),
            "project_id": project_id,
            "action": "action_2",
            "resource_type": "project",
            "resource_id": None,
            "details": {"project_id": str(project_id)},
        }
        id2 = await append_audit_log(db_session, payload2)
        await db_session.commit()

        from sqlalchemy import select

        stmt1 = select(AuditLogEntry).where(AuditLogEntry.id == id1)
        result1 = await db_session.execute(stmt1)
        entry1 = result1.scalar_one()

        stmt2 = select(AuditLogEntry).where(AuditLogEntry.id == id2)
        result2 = await db_session.execute(stmt2)
        entry2 = result2.scalar_one()

        assert entry2.prev_hash == entry1.entry_hash

    @pytest.mark.asyncio
    async def test_project_id_none(self, db_session: AsyncSession):
        """project_id 为 None 时正常写入（全局链）。"""
        payload: AuditLogPayload = {
            "user_id": uuid.uuid4(),
            "project_id": None,
            "action": "system_action",
            "resource_type": "system",
            "resource_id": None,
            "details": {},
        }
        entry_id = await append_audit_log(db_session, payload)
        assert isinstance(entry_id, uuid.UUID)


# --------------------------------------------------------------------------
# 6 种 event_type 写入测试
# --------------------------------------------------------------------------


class TestEventTypeWrite:
    """验证 6 种 event_type 均可正常写入。"""

    @pytest.mark.asyncio
    async def test_archived_exception_access(self, db_session: AsyncSession):
        """archived_exception_access 事件写入。"""
        payload: AuditLogPayload = {
            "user_id": uuid.uuid4(),
            "project_id": uuid.uuid4(),
            "action": "exception_access",
            "resource_type": "project",
            "resource_id": str(uuid.uuid4()),
            "details": {
                "event_type": "archived_exception_access",
                "reason": "质控独立审阅需要",
                "approver_id": str(uuid.uuid4()),
                "endpoint": "/api/projects/xxx/adjustments",
                "original_status": "archived",
            },
        }
        entry_id = await append_audit_log(db_session, payload)
        assert isinstance(entry_id, uuid.UUID)

    @pytest.mark.asyncio
    async def test_archive_unarchive(self, db_session: AsyncSession):
        """archive_unarchive 事件写入。"""
        payload: AuditLogPayload = {
            "user_id": uuid.uuid4(),
            "project_id": uuid.uuid4(),
            "action": "unarchive",
            "resource_type": "project",
            "resource_id": str(uuid.uuid4()),
            "details": {
                "event_type": "archive_unarchive",
                "reason": "发现遗漏调整分录需补充",
                "previous_status": "archived",
            },
        }
        entry_id = await append_audit_log(db_session, payload)
        assert isinstance(entry_id, uuid.UUID)

    @pytest.mark.asyncio
    async def test_delete_with_confirm(self, db_session: AsyncSession):
        """delete_with_confirm 事件写入。"""
        payload: AuditLogPayload = {
            "user_id": uuid.uuid4(),
            "project_id": uuid.uuid4(),
            "action": "delete",
            "resource_type": "adjustment",
            "resource_id": str(uuid.uuid4()),
            "details": {
                "event_type": "delete_with_confirm",
                "object_type": "调整分录",
                "object_name": "RJE-001",
                "soft_or_hard": "soft",
                "recoverable": True,
            },
        }
        entry_id = await append_audit_log(db_session, payload)
        assert isinstance(entry_id, uuid.UUID)

    @pytest.mark.asyncio
    async def test_ai_content_lifecycle(self, db_session: AsyncSession):
        """ai_content_lifecycle 事件写入。"""
        payload: AuditLogPayload = {
            "user_id": uuid.uuid4(),
            "project_id": uuid.uuid4(),
            "action": "ai_confirm",
            "resource_type": "ai_content",
            "resource_id": str(uuid.uuid4()),
            "details": {
                "event_type": "ai_content_lifecycle",
                "ai_content_log_id": str(uuid.uuid4()),
                "action": "confirm",
            },
        }
        entry_id = await append_audit_log(db_session, payload)
        assert isinstance(entry_id, uuid.UUID)

    @pytest.mark.asyncio
    async def test_cross_module_conflict_resolved(self, db_session: AsyncSession):
        """cross_module_conflict_resolved 事件写入。"""
        payload: AuditLogPayload = {
            "user_id": uuid.uuid4(),
            "project_id": uuid.uuid4(),
            "action": "resolve_conflict",
            "resource_type": "conflict",
            "resource_id": str(uuid.uuid4()),
            "details": {
                "event_type": "cross_module_conflict_resolved",
                "conflict_id": str(uuid.uuid4()),
                "resolution": "keep_manual",
                "upstream_value": "1000.00",
                "manual_value": "999.50",
                "final_value": "999.50",
            },
        }
        entry_id = await append_audit_log(db_session, payload)
        assert isinstance(entry_id, uuid.UUID)

    @pytest.mark.asyncio
    async def test_time_machine_restore(self, db_session: AsyncSession):
        """time_machine_restore 事件写入。"""
        payload: AuditLogPayload = {
            "user_id": uuid.uuid4(),
            "project_id": uuid.uuid4(),
            "action": "restore",
            "resource_type": "workpaper",
            "resource_id": str(uuid.uuid4()),
            "details": {
                "event_type": "time_machine_restore",
                "from_snapshot_id": str(uuid.uuid4()),
                "to_snapshot_id": str(uuid.uuid4()),
                "instance_type": "workpaper",
                "instance_id": str(uuid.uuid4()),
            },
        }
        entry_id = await append_audit_log(db_session, payload)
        assert isinstance(entry_id, uuid.UUID)

    @pytest.mark.asyncio
    async def test_formula_changed(self, db_session: AsyncSession):
        """formula_changed 事件写入 — 公式变更/执行留痕。"""
        project_id = uuid.uuid4()
        payload: AuditLogPayload = {
            "user_id": uuid.uuid4(),
            "project_id": project_id,
            "action": "formula.changed",
            "resource_type": "report_config",
            "resource_id": "BS-002",
            "details": {
                "event_type": "formula_changed",
                "module": "report",
                "row_code": "BS-002",
                "action": "execute",
                "old_formula": "",
                "new_formula": "TB('1001','期末余额')",
                "result_value": "12345.67",
                "trace": ["TB(1001, 期末余额) = 12345.67"],
            },
        }
        entry_id = await append_audit_log(db_session, payload)
        assert isinstance(entry_id, uuid.UUID)

        # 验证持久化内容
        await db_session.commit()
        from sqlalchemy import select
        stmt = select(AuditLogEntry).where(AuditLogEntry.id == entry_id)
        result = await db_session.execute(stmt)
        entry = result.scalar_one()

        assert entry.action_type == "formula.changed"
        assert entry.object_type == "report_config"
        assert entry.payload["event_type"] == "formula_changed"
        assert entry.payload["module"] == "report"
        assert entry.payload["row_code"] == "BS-002"
        assert entry.payload["new_formula"] == "TB('1001','期末余额')"
        assert entry.payload["result_value"] == "12345.67"
        assert entry.payload["trace"] == ["TB(1001, 期末余额) = 12345.67"]

    @pytest.mark.asyncio
    async def test_formula_changed_consol_module(self, db_session: AsyncSession):
        """formula_changed 事件写入 — consol 模块公式执行留痕。"""
        project_id = uuid.uuid4()
        payload: AuditLogPayload = {
            "user_id": uuid.uuid4(),
            "project_id": project_id,
            "action": "formula.changed",
            "resource_type": "report_config",
            "resource_id": "PL-001",
            "details": {
                "event_type": "formula_changed",
                "module": "consol",
                "row_code": "PL-001",
                "action": "execute",
                "old_formula": "",
                "new_formula": "SUM_TB('6001~6099','本期发生额')",
                "result_value": "500000.00",
                "trace": ["report_type=income_statement", "row_name=营业收入"],
            },
        }
        entry_id = await append_audit_log(db_session, payload)
        assert isinstance(entry_id, uuid.UUID)

    @pytest.mark.asyncio
    async def test_formula_changed_update_action(self, db_session: AsyncSession):
        """formula_changed 事件写入 — update 动作（公式编辑）含 old/new 对比。"""
        payload: AuditLogPayload = {
            "user_id": uuid.uuid4(),
            "project_id": uuid.uuid4(),
            "action": "formula.changed",
            "resource_type": "report_config",
            "resource_id": str(uuid.uuid4()),
            "details": {
                "event_type": "formula_changed",
                "module": "report",
                "row_code": "BS-010",
                "action": "update",
                "old_formula": "TB('1001','期末余额')",
                "new_formula": "TB('1001','期末余额')+TB('1002','期末余额')",
                "result_value": "",
                "trace": [],
            },
        }
        entry_id = await append_audit_log(db_session, payload)
        assert isinstance(entry_id, uuid.UUID)

    @pytest.mark.asyncio
    async def test_formula_changed_missing_field_raises(self, db_session: AsyncSession):
        """formula_changed 缺少必需字段时抛出 ValueError。"""
        payload: AuditLogPayload = {
            "user_id": uuid.uuid4(),
            "project_id": uuid.uuid4(),
            "action": "formula.changed",
            "resource_type": "report_config",
            "resource_id": "BS-002",
            "details": {
                "event_type": "formula_changed",
                "module": "report",
                "row_code": "BS-002",
                # 缺少 action, old_formula, new_formula, result_value
            },
        }
        with pytest.raises(ValueError, match="缺少必需字段"):
            await append_audit_log(db_session, payload)


# --------------------------------------------------------------------------
# event_type schema 校验测试
# --------------------------------------------------------------------------


class TestEventTypeValidation:
    """验证 event_type 的 details schema 校验逻辑。"""

    @pytest.mark.asyncio
    async def test_missing_required_field_raises(self, db_session: AsyncSession):
        """缺少必需字段时抛出 ValueError。"""
        payload: AuditLogPayload = {
            "user_id": uuid.uuid4(),
            "project_id": uuid.uuid4(),
            "action": "exception_access",
            "resource_type": "project",
            "resource_id": None,
            "details": {
                "event_type": "archived_exception_access",
                "reason": "测试",
                # 缺少 approver_id, endpoint, original_status
            },
        }
        with pytest.raises(ValueError, match="缺少必需字段"):
            await append_audit_log(db_session, payload)

    def test_validate_event_type_details_all_present(self):
        """所有必需字段齐全时不抛异常。"""
        details = {
            "event_type": "archive_unarchive",
            "reason": "测试解除归档",
            "previous_status": "archived",
        }
        # 不应抛异常
        validate_event_type_details(details)

    def test_validate_event_type_details_missing_field(self):
        """缺少字段时抛出 ValueError。"""
        details = {
            "event_type": "delete_with_confirm",
            "object_type": "底稿",
            # 缺少 object_name, soft_or_hard, recoverable
        }
        with pytest.raises(ValueError, match="缺少必需字段"):
            validate_event_type_details(details)

    def test_validate_unknown_event_type_passes(self):
        """未知 event_type 不做校验（向前兼容）。"""
        details = {
            "event_type": "unknown_future_type",
            "some_field": "value",
        }
        # 不应抛异常
        validate_event_type_details(details)

    def test_validate_no_event_type_passes(self):
        """无 event_type 字段时不做校验。"""
        details = {"some_field": "value"}
        # 不应抛异常
        validate_event_type_details(details)

    def test_all_event_type_schemas_defined(self):
        """确认所有 event_type 的 schema 均已定义。"""
        expected_types = {
            "archived_exception_access",
            "archive_unarchive",
            "delete_with_confirm",
            "ai_content_lifecycle",
            "cross_module_conflict_resolved",
            "time_machine_restore",
            "consol_lifecycle",
            "formula_changed",
            "report_config_changed",
            "onlyoffice_callback_rejected",
        }
        assert set(EVENT_TYPE_SCHEMAS.keys()) == expected_types
