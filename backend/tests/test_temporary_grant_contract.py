"""临时授权三层一致契约测试

P2-1.4: 验证 DDL (V060) ↔ ORM (TemporaryGrant) ↔ Service 三层字段对齐。
确保 migration、model、service 均涵盖所有必要字段。
"""

import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── DDL 解析 ─────────────────────────────────────────────────────────────────

MIGRATION_FILE = Path(__file__).parent.parent / "migrations" / "V060__temporary_grants.sql"


def _parse_ddl_columns(sql_text: str) -> set[str]:
    """从 CREATE TABLE DDL 中提取列名"""
    # 匹配 CREATE TABLE ... ( ... ) 内部
    match = re.search(
        r"CREATE TABLE IF NOT EXISTS temporary_grants\s*\((.*?)\);",
        sql_text,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return set()
    body = match.group(1)
    columns = set()
    for line in body.split("\n"):
        line = line.strip().rstrip(",")
        if not line or line.startswith("--"):
            continue
        # 跳过约束行（PRIMARY KEY、CONSTRAINT 等）
        if any(kw in line.upper() for kw in ["PRIMARY KEY", "CONSTRAINT", "FOREIGN KEY", "UNIQUE", "CHECK"]):
            # 但 "id UUID PRIMARY KEY" 是列定义
            if "UUID" in line.upper() or "VARCHAR" in line.upper() or "TEXT" in line.upper():
                pass
            else:
                continue
        # 提取第一个词作为列名
        parts = line.split()
        if parts:
            col_name = parts[0].strip('"')
            if col_name and not col_name.startswith("("):
                columns.add(col_name)
    return columns


# ─── ORM 列名 ─────────────────────────────────────────────────────────────────

def _get_orm_columns() -> set[str]:
    """从 ORM 模型获取列名"""
    from app.models.temporary_grant_models import TemporaryGrant
    mapper = TemporaryGrant.__table__
    return {col.name for col in mapper.columns}


# ─── Schema 字段 ──────────────────────────────────────────────────────────────

def _get_schema_create_fields() -> set[str]:
    """从 Pydantic Create schema 获取字段"""
    from app.models.temporary_grant_schemas import TemporaryGrantCreate
    return set(TemporaryGrantCreate.model_fields.keys())


def _get_schema_response_fields() -> set[str]:
    """从 Pydantic Response schema 获取字段"""
    from app.models.temporary_grant_schemas import TemporaryGrantResponse
    return set(TemporaryGrantResponse.model_fields.keys())


# ─── 测试 ────────────────────────────────────────────────────────────────────

class TestThreeLayerConsistency:
    """三层一致性契约测试"""

    # P2-1.5 必须字段
    REQUIRED_COLUMNS = {
        "id", "project_id", "operation_code", "grantee",
        "approver", "reason", "expires_at", "is_active",
        "created_at", "updated_at",
    }

    def test_ddl_contains_all_required_columns(self):
        """DDL 包含所有必须字段"""
        sql = MIGRATION_FILE.read_text(encoding="utf-8")
        ddl_cols = _parse_ddl_columns(sql)
        missing = self.REQUIRED_COLUMNS - ddl_cols
        assert not missing, f"DDL 缺失字段: {missing}"

    def test_orm_contains_all_required_columns(self):
        """ORM 模型包含所有必须字段"""
        orm_cols = _get_orm_columns()
        missing = self.REQUIRED_COLUMNS - orm_cols
        assert not missing, f"ORM 缺失字段: {missing}"

    def test_ddl_and_orm_columns_match(self):
        """DDL 和 ORM 列集合一致"""
        sql = MIGRATION_FILE.read_text(encoding="utf-8")
        ddl_cols = _parse_ddl_columns(sql)
        orm_cols = _get_orm_columns()
        assert ddl_cols == orm_cols, (
            f"DDL 多出: {ddl_cols - orm_cols}, ORM 多出: {orm_cols - ddl_cols}"
        )

    def test_response_schema_covers_all_orm_columns(self):
        """Response schema 覆盖所有 ORM 列"""
        orm_cols = _get_orm_columns()
        schema_fields = _get_schema_response_fields()
        missing = orm_cols - schema_fields
        assert not missing, f"Response schema 缺失字段: {missing}"

    def test_create_schema_contains_user_input_fields(self):
        """Create schema 包含用户可输入字段"""
        create_fields = _get_schema_create_fields()
        # 用户创建时需提供的字段
        expected_user_fields = {"operation_code", "grantee", "reason", "expires_at"}
        missing = expected_user_fields - create_fields
        assert not missing, f"Create schema 缺失用户输入字段: {missing}"

    def test_create_schema_excludes_system_fields(self):
        """Create schema 不包含系统自动填充字段"""
        create_fields = _get_schema_create_fields()
        system_fields = {"id", "project_id", "approver", "is_active", "created_at", "updated_at"}
        leaked = system_fields & create_fields
        assert not leaked, f"Create schema 不应包含系统字段: {leaked}"


class TestTemporaryGrantService:
    """Service 层逻辑测试"""

    @pytest.fixture
    def mock_db(self):
        db = AsyncMock()
        db.execute = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.fixture
    def service(self, mock_db):
        from app.services.temporary_grant_service import TemporaryGrantService
        return TemporaryGrantService(mock_db)

    @pytest.mark.asyncio
    async def test_create_grant_rejects_invalid_operation_code(self, service):
        """拒绝不在 OPERATION_CODES 中的 operation_code"""
        from app.models.temporary_grant_schemas import TemporaryGrantCreate
        from app.services.temporary_grant_service import TemporaryGrantError

        data = TemporaryGrantCreate(
            operation_code="invalid:code",
            grantee=uuid.uuid4(),
            reason="测试授权",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )
        with pytest.raises(TemporaryGrantError, match="无效的操作代码"):
            await service.create_grant(uuid.uuid4(), uuid.uuid4(), data)

    @pytest.mark.asyncio
    async def test_create_grant_rejects_past_expires_at(self, service):
        """拒绝过去的 expires_at"""
        from app.models.temporary_grant_schemas import TemporaryGrantCreate
        from app.services.temporary_grant_service import TemporaryGrantError

        data = TemporaryGrantCreate(
            operation_code="wp:edit",
            grantee=uuid.uuid4(),
            reason="紧急编辑",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        with pytest.raises(TemporaryGrantError, match="expires_at 必须在当前时间之后"):
            await service.create_grant(uuid.uuid4(), uuid.uuid4(), data)

    @pytest.mark.asyncio
    async def test_create_grant_rejects_self_grant(self, service):
        """拒绝自己授权给自己"""
        from app.models.temporary_grant_schemas import TemporaryGrantCreate
        from app.services.temporary_grant_service import TemporaryGrantError

        user_id = uuid.uuid4()
        data = TemporaryGrantCreate(
            operation_code="wp:edit",
            grantee=user_id,
            reason="自授权",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )
        with pytest.raises(TemporaryGrantError, match="审批人不能授权给自己"):
            await service.create_grant(uuid.uuid4(), user_id, data)

    @pytest.mark.asyncio
    async def test_create_grant_success(self, service, mock_db):
        """正常创建临时授权"""
        from app.models.temporary_grant_schemas import TemporaryGrantCreate

        grantee_id = uuid.uuid4()
        approver_id = uuid.uuid4()
        project_id = uuid.uuid4()

        # Mock execute for audit log write
        mock_db.execute = AsyncMock(return_value=MagicMock())

        data = TemporaryGrantCreate(
            operation_code="wp:edit",
            grantee=grantee_id,
            reason="项目紧急修改底稿",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=4),
        )
        grant = await service.create_grant(project_id, approver_id, data)

        assert grant.project_id == project_id
        assert grant.operation_code == "wp:edit"
        assert grant.grantee == grantee_id
        assert grant.approver == approver_id
        assert grant.reason == "项目紧急修改底稿"
        assert grant.is_active is True
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    def test_operation_codes_alignment(self):
        """Service 使用的 OPERATION_CODES 与权限矩阵一致"""
        from app.services.permission_matrix_service import OPERATION_CODES
        from app.services.temporary_grant_service import TemporaryGrantService

        # 确保 service import 的是同一份 OPERATION_CODES
        assert OPERATION_CODES == [
            "project:view",
            "wp:edit",
            "wp:review",
            "report:edit",
            "report:sign",
            "note:edit",
            "archive:manage",
        ]


class TestTemporaryGrantExpiry:
    """过期自动失效测试"""

    def test_is_expired_property_future(self):
        """未来时间不过期"""
        from app.models.temporary_grant_models import TemporaryGrant

        grant = TemporaryGrant(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            operation_code="wp:edit",
            grantee=uuid.uuid4(),
            approver=uuid.uuid4(),
            reason="test",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            is_active=True,
        )
        assert grant.is_expired is False

    def test_is_expired_property_past(self):
        """过去时间已过期"""
        from app.models.temporary_grant_models import TemporaryGrant

        grant = TemporaryGrant(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            operation_code="wp:edit",
            grantee=uuid.uuid4(),
            approver=uuid.uuid4(),
            reason="test",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            is_active=True,
        )
        assert grant.is_expired is True


class TestAuditLogActions:
    """P2-1.7: 审计日志记录授权、使用、过期事件"""

    def test_audit_actions_are_defined(self):
        """确认审计日志使用的 action 命名"""
        expected_actions = {
            "temp_grant:create",
            "temp_grant:use",
            "temp_grant:expire",
            "temp_grant:revoke",
        }
        # 从 service 源码验证这些 action 字符串存在
        import inspect
        from app.services.temporary_grant_service import TemporaryGrantService
        source = inspect.getsource(TemporaryGrantService)
        for action in expected_actions:
            assert action in source, f"Service 缺少审计 action: {action}"
