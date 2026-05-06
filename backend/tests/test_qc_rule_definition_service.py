"""QcRuleDefinitionService 单元测试

Validates: Requirements 1 (Round 3)
- CRUD 操作
- PATCH 时 version+1
- GET 过滤（scope/severity/enabled）
- DELETE 软删除
- rule_code 唯一性校验
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.qc_rule_models import QcRuleDefinition

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每个测试独立的内存数据库会话。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


def _rule_data(**overrides) -> dict:
    """生成默认规则数据，可覆盖任意字段。"""
    base = {
        "rule_code": f"QC-TEST-{uuid.uuid4().hex[:6].upper()}",
        "severity": "warning",
        "scope": "workpaper",
        "category": "数据完整性",
        "title": "测试规则",
        "description": "这是一条测试规则",
        "standard_ref": [{"code": "1301", "section": "6.2", "name": "审计工作底稿"}],
        "expression_type": "python",
        "expression": "app.services.qc_engine.ConclusionNotEmptyRule",
        "parameters_schema": None,
        "enabled": True,
    }
    base.update(overrides)
    return base


# ═══ CREATE ═══════════════════════════════════════════════════════


class TestCreateRule:
    """创建规则"""

    @pytest.mark.asyncio
    async def test_create_success(self, db_session: AsyncSession):
        from app.services.qc_rule_definition_service import qc_rule_definition_service

        user_id = uuid.uuid4()
        data = _rule_data(rule_code="QC-CREATE-01")

        result = await qc_rule_definition_service.create_rule(
            db_session, data=data, created_by=user_id
        )

        assert result["rule_code"] == "QC-CREATE-01"
        assert result["version"] == 1
        assert result["severity"] == "warning"
        assert result["scope"] == "workpaper"
        assert result["enabled"] is True
        assert result["created_by"] == str(user_id)
        assert result["id"] is not None

    @pytest.mark.asyncio
    async def test_create_duplicate_rule_code_raises_409(self, db_session: AsyncSession):
        from fastapi import HTTPException

        from app.services.qc_rule_definition_service import qc_rule_definition_service

        user_id = uuid.uuid4()
        data = _rule_data(rule_code="QC-DUP-01")

        await qc_rule_definition_service.create_rule(
            db_session, data=data, created_by=user_id
        )

        with pytest.raises(HTTPException) as exc_info:
            await qc_rule_definition_service.create_rule(
                db_session, data=data, created_by=user_id
            )
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_create_with_jsonpath_expression(self, db_session: AsyncSession):
        from app.services.qc_rule_definition_service import qc_rule_definition_service

        data = _rule_data(
            rule_code="QC-JP-01",
            expression_type="jsonpath",
            expression="$.parsed_data.conclusion",
        )

        result = await qc_rule_definition_service.create_rule(
            db_session, data=data, created_by=uuid.uuid4()
        )

        assert result["expression_type"] == "jsonpath"
        assert result["expression"] == "$.parsed_data.conclusion"


# ═══ READ (LIST) ═════════════════════════════════════════════════


class TestListRules:
    """列表与过滤"""

    @pytest.mark.asyncio
    async def test_list_empty(self, db_session: AsyncSession):
        from app.services.qc_rule_definition_service import qc_rule_definition_service

        result = await qc_rule_definition_service.list_rules(db_session)

        assert result["items"] == []
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_list_with_data(self, db_session: AsyncSession):
        from app.services.qc_rule_definition_service import qc_rule_definition_service

        user_id = uuid.uuid4()
        for i in range(3):
            await qc_rule_definition_service.create_rule(
                db_session,
                data=_rule_data(rule_code=f"QC-LIST-{i:02d}"),
                created_by=user_id,
            )

        result = await qc_rule_definition_service.list_rules(db_session)

        assert result["total"] == 3
        assert len(result["items"]) == 3

    @pytest.mark.asyncio
    async def test_filter_by_scope(self, db_session: AsyncSession):
        from app.services.qc_rule_definition_service import qc_rule_definition_service

        user_id = uuid.uuid4()
        await qc_rule_definition_service.create_rule(
            db_session,
            data=_rule_data(rule_code="QC-SCOPE-WP", scope="workpaper"),
            created_by=user_id,
        )
        await qc_rule_definition_service.create_rule(
            db_session,
            data=_rule_data(rule_code="QC-SCOPE-PJ", scope="project"),
            created_by=user_id,
        )

        result = await qc_rule_definition_service.list_rules(
            db_session, scope="workpaper"
        )

        assert result["total"] == 1
        assert result["items"][0]["scope"] == "workpaper"

    @pytest.mark.asyncio
    async def test_filter_by_severity(self, db_session: AsyncSession):
        from app.services.qc_rule_definition_service import qc_rule_definition_service

        user_id = uuid.uuid4()
        await qc_rule_definition_service.create_rule(
            db_session,
            data=_rule_data(rule_code="QC-SEV-B", severity="blocking"),
            created_by=user_id,
        )
        await qc_rule_definition_service.create_rule(
            db_session,
            data=_rule_data(rule_code="QC-SEV-W", severity="warning"),
            created_by=user_id,
        )

        result = await qc_rule_definition_service.list_rules(
            db_session, severity="blocking"
        )

        assert result["total"] == 1
        assert result["items"][0]["severity"] == "blocking"

    @pytest.mark.asyncio
    async def test_filter_by_enabled(self, db_session: AsyncSession):
        from app.services.qc_rule_definition_service import qc_rule_definition_service

        user_id = uuid.uuid4()
        await qc_rule_definition_service.create_rule(
            db_session,
            data=_rule_data(rule_code="QC-EN-T", enabled=True),
            created_by=user_id,
        )
        await qc_rule_definition_service.create_rule(
            db_session,
            data=_rule_data(rule_code="QC-EN-F", enabled=False),
            created_by=user_id,
        )

        result = await qc_rule_definition_service.list_rules(
            db_session, enabled=False
        )

        assert result["total"] == 1
        assert result["items"][0]["enabled"] is False


# ═══ READ (GET) ══════════════════════════════════════════════════


class TestGetRule:
    """获取单条规则"""

    @pytest.mark.asyncio
    async def test_get_existing(self, db_session: AsyncSession):
        from app.services.qc_rule_definition_service import qc_rule_definition_service

        created = await qc_rule_definition_service.create_rule(
            db_session,
            data=_rule_data(rule_code="QC-GET-01"),
            created_by=uuid.uuid4(),
        )

        result = await qc_rule_definition_service.get_rule(
            db_session, uuid.UUID(created["id"])
        )

        assert result["rule_code"] == "QC-GET-01"

    @pytest.mark.asyncio
    async def test_get_nonexistent_raises_404(self, db_session: AsyncSession):
        from fastapi import HTTPException

        from app.services.qc_rule_definition_service import qc_rule_definition_service

        with pytest.raises(HTTPException) as exc_info:
            await qc_rule_definition_service.get_rule(db_session, uuid.uuid4())
        assert exc_info.value.status_code == 404


# ═══ UPDATE (PATCH) ══════════════════════════════════════════════


class TestUpdateRule:
    """更新规则 + 版本递增"""

    @pytest.mark.asyncio
    async def test_update_increments_version(self, db_session: AsyncSession):
        from app.services.qc_rule_definition_service import qc_rule_definition_service

        created = await qc_rule_definition_service.create_rule(
            db_session,
            data=_rule_data(rule_code="QC-UPD-01"),
            created_by=uuid.uuid4(),
        )
        assert created["version"] == 1

        updated = await qc_rule_definition_service.update_rule(
            db_session,
            uuid.UUID(created["id"]),
            data={"title": "更新后的标题"},
        )

        assert updated["version"] == 2
        assert updated["title"] == "更新后的标题"

    @pytest.mark.asyncio
    async def test_multiple_updates_increment_version(self, db_session: AsyncSession):
        from app.services.qc_rule_definition_service import qc_rule_definition_service

        created = await qc_rule_definition_service.create_rule(
            db_session,
            data=_rule_data(rule_code="QC-UPD-02"),
            created_by=uuid.uuid4(),
        )

        rule_id = uuid.UUID(created["id"])

        await qc_rule_definition_service.update_rule(
            db_session, rule_id, data={"severity": "blocking"}
        )
        result = await qc_rule_definition_service.update_rule(
            db_session, rule_id, data={"severity": "info"}
        )

        assert result["version"] == 3
        assert result["severity"] == "info"

    @pytest.mark.asyncio
    async def test_update_no_change_no_version_bump(self, db_session: AsyncSession):
        """如果没有实际变更，version 不递增。"""
        from app.services.qc_rule_definition_service import qc_rule_definition_service

        created = await qc_rule_definition_service.create_rule(
            db_session,
            data=_rule_data(rule_code="QC-UPD-03", title="原标题"),
            created_by=uuid.uuid4(),
        )

        result = await qc_rule_definition_service.update_rule(
            db_session,
            uuid.UUID(created["id"]),
            data={"title": "原标题"},  # 相同值
        )

        assert result["version"] == 1  # 未变

    @pytest.mark.asyncio
    async def test_update_rule_code_uniqueness(self, db_session: AsyncSession):
        """更新 rule_code 时检查唯一性。"""
        from fastapi import HTTPException

        from app.services.qc_rule_definition_service import qc_rule_definition_service

        user_id = uuid.uuid4()
        await qc_rule_definition_service.create_rule(
            db_session,
            data=_rule_data(rule_code="QC-EXIST"),
            created_by=user_id,
        )
        second = await qc_rule_definition_service.create_rule(
            db_session,
            data=_rule_data(rule_code="QC-SECOND"),
            created_by=user_id,
        )

        with pytest.raises(HTTPException) as exc_info:
            await qc_rule_definition_service.update_rule(
                db_session,
                uuid.UUID(second["id"]),
                data={"rule_code": "QC-EXIST"},
            )
        assert exc_info.value.status_code == 409


# ═══ DELETE ══════════════════════════════════════════════════════


class TestDeleteRule:
    """软删除"""

    @pytest.mark.asyncio
    async def test_delete_soft_deletes(self, db_session: AsyncSession):
        from app.services.qc_rule_definition_service import qc_rule_definition_service

        created = await qc_rule_definition_service.create_rule(
            db_session,
            data=_rule_data(rule_code="QC-DEL-01"),
            created_by=uuid.uuid4(),
        )

        result = await qc_rule_definition_service.delete_rule(
            db_session, uuid.UUID(created["id"])
        )

        assert result["deleted"] is True

        # 列表中不再出现
        list_result = await qc_rule_definition_service.list_rules(db_session)
        assert list_result["total"] == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_raises_404(self, db_session: AsyncSession):
        from fastapi import HTTPException

        from app.services.qc_rule_definition_service import qc_rule_definition_service

        with pytest.raises(HTTPException) as exc_info:
            await qc_rule_definition_service.delete_rule(db_session, uuid.uuid4())
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_deleted_rule_not_in_list(self, db_session: AsyncSession):
        """软删除后，规则不出现在列表中但 DB 唯一约束仍保留。"""
        from app.services.qc_rule_definition_service import qc_rule_definition_service

        user_id = uuid.uuid4()
        created = await qc_rule_definition_service.create_rule(
            db_session,
            data=_rule_data(rule_code="QC-REUSE"),
            created_by=user_id,
        )
        await qc_rule_definition_service.delete_rule(
            db_session, uuid.UUID(created["id"])
        )

        # 列表中不再出现
        list_result = await qc_rule_definition_service.list_rules(db_session)
        assert all(
            item["rule_code"] != "QC-REUSE" for item in list_result["items"]
        )
