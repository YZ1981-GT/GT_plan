"""ClientCommunicationService — commitments 升级测试

验证：
1. 读时兼容 string（自动包装为结构化数组）
2. 写时强制数组
3. 每条 commitment 创建 IssueTicket(source='client_commitment')，回写 issue_ticket_id
4. PATCH 标完成：关闭关联 ticket + 时间线追加"✅ 已完成"

Validates: Refinement Round 2 需求 5
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import get_db
from app.deps import get_current_user
from app.models.base import Base, ProjectStatus, ProjectType, UserRole
from app.models.core import Project
from app.models.phase15_models import IssueTicket
from app.routers.pm_dashboard import router as pm_router
from app.services.pm_service import ClientCommunicationService

# SQLite JSONB 兼容
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

PROJECT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


class _FakeUser:
    def __init__(self, uid: uuid.UUID, role: UserRole = UserRole.admin):
        self.id = uid
        self.username = "pm_user"
        self.email = "pm@test.com"
        self.role = role
        self.is_active = True
        self.is_deleted = False


@pytest_asyncio.fixture
async def db_session():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """创建一个带 wizard_state 的项目"""
    project = Project(
        id=PROJECT_ID,
        name="测试项目",
        client_name="测试客户",
        status=ProjectStatus.execution,
        project_type=ProjectType.annual,
        created_by=USER_ID,
        wizard_state={
            "communications": [
                {
                    "id": "old-comm-1",
                    "created_at": "2026-01-01T00:00:00",
                    "created_by": str(USER_ID),
                    "date": "2026-01-01",
                    "contact_person": "张三",
                    "topic": "资料催收",
                    "content": "讨论了银行函证事宜",
                    "commitments": "本周五前提供银行询证函回函",
                    "related_wp_codes": [],
                    "related_accounts": [],
                }
            ]
        },
    )
    db_session.add(project)
    await db_session.commit()
    return db_session


def _make_client(db_session: AsyncSession, user_id: uuid.UUID) -> AsyncClient:
    app = FastAPI()
    app.include_router(pm_router)

    fake_user = _FakeUser(user_id)

    async def _override_db():
        yield db_session

    async def _override_user():
        return fake_user

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = _override_user

    # 绕过 require_project_access
    from app.deps import require_project_access as _rpa

    def _fake_rpa(level: str):
        async def _dep():
            return fake_user
        return _dep

    import app.deps
    app.dependency_overrides[app.deps.require_project_access("readonly")] = _override_user
    app.dependency_overrides[app.deps.require_project_access("edit")] = _override_user

    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    )


# ---------------------------------------------------------------------------
# 单元测试：_normalize_commitments
# ---------------------------------------------------------------------------

class TestNormalizeCommitments:
    """测试读时兼容逻辑"""

    def test_string_wrapped_to_array(self):
        result = ClientCommunicationService._normalize_commitments("本周五提供银行流水")
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["content"] == "本周五提供银行流水"
        assert result[0]["status"] == "pending"
        assert result[0]["due_date"] is None
        assert result[0]["issue_ticket_id"] is None

    def test_empty_string_returns_empty_list(self):
        result = ClientCommunicationService._normalize_commitments("")
        assert result == []

    def test_whitespace_string_returns_empty_list(self):
        result = ClientCommunicationService._normalize_commitments("   ")
        assert result == []

    def test_none_returns_empty_list(self):
        result = ClientCommunicationService._normalize_commitments(None)
        assert result == []

    def test_list_passthrough(self):
        data = [{"id": "abc", "content": "test", "status": "pending"}]
        result = ClientCommunicationService._normalize_commitments(data)
        assert result == data

    def test_empty_list_passthrough(self):
        result = ClientCommunicationService._normalize_commitments([])
        assert result == []


# ---------------------------------------------------------------------------
# 集成测试：Service 层
# ---------------------------------------------------------------------------

class TestClientCommunicationServiceCommitments:
    """测试 commitments 升级后的 Service 行为"""

    @pytest.mark.asyncio
    async def test_list_normalizes_old_string_commitments(self, seeded_db):
        """读取旧格式 string commitments 时自动包装为数组"""
        svc = ClientCommunicationService(seeded_db)
        comms = await svc.list_communications(PROJECT_ID)

        assert len(comms) == 1
        commitments = comms[0]["commitments"]
        assert isinstance(commitments, list)
        assert len(commitments) == 1
        assert commitments[0]["content"] == "本周五前提供银行询证函回函"
        assert commitments[0]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_add_communication_with_array_commitments(self, seeded_db):
        """写入时 commitments 为数组，每条创建 IssueTicket"""
        svc = ClientCommunicationService(seeded_db)
        data = {
            "date": "2026-05-10",
            "contact_person": "李四",
            "topic": "PBC 催收",
            "content": "讨论了 PBC 提交时间",
            "commitments": [
                {"content": "周五前提供银行流水", "due_date": "2026-05-15"},
                {"content": "下周一提供合同清单", "due_date": "2026-05-18"},
            ],
            "related_wp_codes": [],
            "related_accounts": [],
        }
        result = await svc.add_communication(PROJECT_ID, USER_ID, data)
        await seeded_db.commit()

        # 验证 commitments 是数组
        assert isinstance(result["commitments"], list)
        assert len(result["commitments"]) == 2

        # 验证每条都有 issue_ticket_id
        for c in result["commitments"]:
            assert c["issue_ticket_id"] is not None
            assert c["status"] == "pending"
            assert c["id"] is not None

        # 验证 IssueTicket 已创建
        from sqlalchemy import select
        tickets = (await seeded_db.execute(
            select(IssueTicket).where(
                IssueTicket.project_id == PROJECT_ID,
                IssueTicket.source == "client_commitment",
            )
        )).scalars().all()
        assert len(tickets) == 2
        assert tickets[0].owner_id == USER_ID
        assert tickets[0].status == "open"

    @pytest.mark.asyncio
    async def test_add_communication_with_string_commitments(self, seeded_db):
        """写入时 commitments 为旧格式 string，自动包装并创建 ticket"""
        svc = ClientCommunicationService(seeded_db)
        data = {
            "date": "2026-05-10",
            "contact_person": "王五",
            "topic": "函证",
            "content": "讨论了函证回函",
            "commitments": "下周三前提供函证回函",
            "related_wp_codes": [],
            "related_accounts": [],
        }
        result = await svc.add_communication(PROJECT_ID, USER_ID, data)
        await seeded_db.commit()

        assert isinstance(result["commitments"], list)
        assert len(result["commitments"]) == 1
        assert result["commitments"][0]["content"] == "下周三前提供函证回函"
        assert result["commitments"][0]["issue_ticket_id"] is not None

    @pytest.mark.asyncio
    async def test_complete_commitment(self, seeded_db):
        """标记承诺完成：关闭 ticket + 时间线追加"""
        svc = ClientCommunicationService(seeded_db)

        # 先添加一条带承诺的沟通记录
        data = {
            "date": "2026-05-10",
            "contact_person": "赵六",
            "topic": "资料",
            "content": "讨论了资料提交",
            "commitments": [
                {"content": "提供银行流水", "due_date": "2026-05-15"},
            ],
        }
        record = await svc.add_communication(PROJECT_ID, USER_ID, data)
        await seeded_db.commit()

        comm_id = record["id"]
        commitment_id = record["commitments"][0]["id"]
        ticket_id = record["commitments"][0]["issue_ticket_id"]

        # 标记完成
        result = await svc.complete_commitment(PROJECT_ID, comm_id, commitment_id, USER_ID)
        await seeded_db.commit()

        assert result["status"] == "done"
        assert result["completed_at"] is not None

        # 验证 ticket 已关闭
        from sqlalchemy import select
        ticket = (await seeded_db.execute(
            select(IssueTicket).where(IssueTicket.id == uuid.UUID(ticket_id))
        )).scalar_one()
        assert ticket.status == "closed"
        assert ticket.closed_at is not None

        # 验证时间线追加
        comms = await svc.list_communications(PROJECT_ID)
        target_comm = next(c for c in comms if c["id"] == comm_id)
        assert "✅ 提供银行流水 已完成" in target_comm["content"]

    @pytest.mark.asyncio
    async def test_complete_commitment_already_done_raises(self, seeded_db):
        """重复标记完成应报错"""
        svc = ClientCommunicationService(seeded_db)

        data = {
            "date": "2026-05-10",
            "contact_person": "钱七",
            "topic": "测试",
            "content": "测试",
            "commitments": [{"content": "测试承诺", "due_date": "2026-05-15"}],
        }
        record = await svc.add_communication(PROJECT_ID, USER_ID, data)
        await seeded_db.commit()

        comm_id = record["id"]
        commitment_id = record["commitments"][0]["id"]

        # 第一次完成
        await svc.complete_commitment(PROJECT_ID, comm_id, commitment_id, USER_ID)
        await seeded_db.commit()

        # 第二次应报错
        with pytest.raises(ValueError, match="承诺已完成"):
            await svc.complete_commitment(PROJECT_ID, comm_id, commitment_id, USER_ID)

    @pytest.mark.asyncio
    async def test_delete_communication_closes_tickets(self, seeded_db):
        """删除沟通记录时级联关闭关联 tickets"""
        svc = ClientCommunicationService(seeded_db)

        data = {
            "date": "2026-05-10",
            "contact_person": "孙八",
            "topic": "删除测试",
            "content": "测试删除",
            "commitments": [
                {"content": "承诺A", "due_date": "2026-05-15"},
                {"content": "承诺B", "due_date": "2026-05-16"},
            ],
        }
        record = await svc.add_communication(PROJECT_ID, USER_ID, data)
        await seeded_db.commit()

        ticket_ids = [c["issue_ticket_id"] for c in record["commitments"]]

        # 删除
        ok = await svc.delete_communication(PROJECT_ID, record["id"])
        await seeded_db.commit()
        assert ok is True

        # 验证 tickets 已关闭
        from sqlalchemy import select
        for tid in ticket_ids:
            ticket = (await seeded_db.execute(
                select(IssueTicket).where(IssueTicket.id == uuid.UUID(tid))
            )).scalar_one()
            assert ticket.status == "closed"
