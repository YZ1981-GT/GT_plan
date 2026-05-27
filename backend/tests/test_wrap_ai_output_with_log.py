"""wrap_ai_output_with_log 单元测试 — V3 收官增强 Req 6.2

覆盖：
- test_wrap_without_db_no_log_written — db=None 时不写表，返回不含 ai_content_log_id
- test_wrap_without_required_args_no_log_written — 缺 project_id/user_id/instance_* 任一时不写表
- test_wrap_with_full_args_writes_log — 5 参齐全时写表 + 返回 ai_content_log_id
- test_wrap_returns_pending_action — 写表后 confirm_action='pending'
- test_wrap_content_hash_consistency — 同 content 产生同 hash（sha256 64 字符）
- test_wrap_prompt_hash_from_text — prompt_text 提供时自动算 hash
- test_wrap_prompt_hash_explicit_overrides_text — 同时给 hash + text 时优先用 hash
- test_wrap_persists_to_db — 数据库实际写入一行 + 字段正确
- test_wrap_writes_audit_log — 写表时同步写一条 ai_content_lifecycle 审计

Validates: Requirements 6.2
"""

from __future__ import annotations

import hashlib
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# SQLite 兼容 JSONB + ARRAY（先于模型导入）
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

from app.models.base import Base  # noqa: E402

# 仅注册测试所需的模型
import app.models.core  # noqa: E402, F401
import app.models.audit_log_models  # noqa: E402, F401
import app.models.v3_refinement_models  # noqa: E402, F401

from app.models.audit_log_models import AuditLogEntry  # noqa: E402
from app.models.v3_refinement_models import AiContentLog  # noqa: E402
from app.services.wp_ai_service import wrap_ai_output_with_log  # noqa: E402


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


# ---------------------------------------------------------------------------
# Fixtures（与 test_ai_content_log_service.py 对齐）
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每个测试独立的内存数据库会话。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        tables_to_create = [
            Base.metadata.tables["users"],
            Base.metadata.tables["projects"],
            Base.metadata.tables["audit_log_entries"],
            Base.metadata.tables["ai_content_log"],
        ]
        await conn.run_sync(Base.metadata.create_all, tables=tables_to_create)

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def user_and_project(db_session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """预先写入 users / projects 各一条供 FK 引用。"""
    from app.models.base import ProjectStatus, UserRole
    from app.models.core import Project, User

    user_id = uuid.uuid4()
    project_id = uuid.uuid4()

    db_session.add(
        User(
            id=user_id,
            username=f"tester-{user_id.hex[:8]}",
            email=f"{user_id.hex[:8]}@test.local",
            hashed_password="hashed",
            role=UserRole.auditor,
            is_active=True,
        )
    )
    db_session.add(
        Project(
            id=project_id,
            name="测试项目",
            client_name="测试客户",
            status=ProjectStatus.execution,
        )
    )
    await db_session.commit()
    return user_id, project_id


# ---------------------------------------------------------------------------
# 向后兼容分支：缺参时不写表
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """V3 Req 6.2 兼容性优先：缺 db / project_id / user_id / instance_* 任一时跳过写表。"""

    @pytest.mark.asyncio
    async def test_wrap_without_db_no_log_written(self):
        """不传 db 时不写表，返回 dict 不含 ai_content_log_id。"""
        result = await wrap_ai_output_with_log(
            content="AI 生成的分析文本",
            confidence=0.85,
            target_cell="E5",
        )
        assert result["type"] == "ai_generated"
        assert result["content"] == "AI 生成的分析文本"
        assert result["confidence"] == 0.85
        assert "ai_content_log_id" not in result
        # confirm_action 默认 None（未写表）
        assert result["confirm_action"] is None
        # content_hash 始终计算
        assert result["content_hash"] is not None
        assert len(result["content_hash"]) == 64

    @pytest.mark.asyncio
    async def test_wrap_without_project_id_no_log_written(
        self, db_session: AsyncSession
    ):
        """传 db 但缺 project_id 仍跳过写表。"""
        result = await wrap_ai_output_with_log(
            content="test",
            db=db_session,
            user_id=uuid.uuid4(),
            instance_type="workpaper",
            instance_id=uuid.uuid4(),
        )
        assert "ai_content_log_id" not in result
        assert result["confirm_action"] is None

    @pytest.mark.asyncio
    async def test_wrap_without_instance_type_no_log_written(
        self, db_session: AsyncSession, user_and_project
    ):
        """传 db + project_id + user_id 但缺 instance_type 仍跳过写表。"""
        user_id, project_id = user_and_project
        result = await wrap_ai_output_with_log(
            content="test",
            db=db_session,
            project_id=project_id,
            user_id=user_id,
            instance_id=uuid.uuid4(),
        )
        assert "ai_content_log_id" not in result


# ---------------------------------------------------------------------------
# 强制写日志分支
# ---------------------------------------------------------------------------


class TestForceWriteLog:
    """5 参齐全时强制写 ai_content_log + 返回新增字段。"""

    @pytest.mark.asyncio
    async def test_wrap_with_full_args_writes_log(
        self, db_session: AsyncSession, user_and_project
    ):
        """db + project_id + user_id + instance_type + instance_id 齐全时写表。"""
        user_id, project_id = user_and_project
        instance_id = uuid.uuid4()

        result = await wrap_ai_output_with_log(
            content="审计结论：余额变动合理",
            confidence=0.85,
            target_cell="narrative",
            db=db_session,
            project_id=project_id,
            user_id=user_id,
            instance_type="workpaper",
            instance_id=instance_id,
        )
        await db_session.commit()

        assert "ai_content_log_id" in result
        assert result["confirm_action"] == "pending"
        # ai_content_log_id 是有效 UUID
        log_uuid = uuid.UUID(result["ai_content_log_id"])
        assert isinstance(log_uuid, uuid.UUID)

    @pytest.mark.asyncio
    async def test_wrap_returns_pending_action(
        self, db_session: AsyncSession, user_and_project
    ):
        """写表后 confirm_action='pending'（与 6.1 默认值对齐）。"""
        user_id, project_id = user_and_project
        result = await wrap_ai_output_with_log(
            content="test pending",
            db=db_session,
            project_id=project_id,
            user_id=user_id,
            instance_type="adjustment",
            instance_id=uuid.uuid4(),
        )
        await db_session.commit()
        assert result["confirm_action"] == "pending"
        assert result["confirmed_by"] is None
        assert result["confirmed_at"] is None

    @pytest.mark.asyncio
    async def test_wrap_persists_to_db(
        self, db_session: AsyncSession, user_and_project
    ):
        """实际查 DB 验证一行被写入 + 字段正确。"""
        user_id, project_id = user_and_project
        instance_id = uuid.uuid4()
        wp_id = uuid.uuid4()

        result = await wrap_ai_output_with_log(
            content="实际写表内容",
            confidence=0.9,
            target_cell="conclusion",
            db=db_session,
            project_id=project_id,
            user_id=user_id,
            instance_type="workpaper",
            instance_id=instance_id,
            wp_id=wp_id,
            source_model="qwen3.5-27b",
            prompt_text="请分析该科目变动",
        )
        await db_session.commit()

        # 查回数据库
        log_id = uuid.UUID(result["ai_content_log_id"])
        row = (
            await db_session.execute(
                select(AiContentLog).where(AiContentLog.id == log_id)
            )
        ).scalar_one()

        assert row.project_id == project_id
        assert row.user_id == user_id
        assert row.wp_id == wp_id
        assert row.confirm_action == "pending"
        assert row.generated_content == "实际写表内容"
        assert row.model == "qwen3.5-27b"
        assert row.confidence == Decimal("0.9")
        assert row.content_hash == result["content_hash"]
        assert row.prompt_hash == result["prompt_hash"]
        # target_cell 被前缀化（'workpaper:<uuid>:conclusion'）
        assert row.target_cell.startswith("workpaper:")
        assert "conclusion" in row.target_cell

    @pytest.mark.asyncio
    async def test_wrap_writes_audit_log(
        self, db_session: AsyncSession, user_and_project
    ):
        """写表时同步写 ai_content_lifecycle 审计日志（继承 6.1 行为）。"""
        user_id, project_id = user_and_project
        result = await wrap_ai_output_with_log(
            content="带审计的 AI 输出",
            db=db_session,
            project_id=project_id,
            user_id=user_id,
            instance_type="workpaper",
            instance_id=uuid.uuid4(),
        )
        await db_session.commit()

        entries = (
            await db_session.execute(
                select(AuditLogEntry).where(
                    AuditLogEntry.object_type == "ai_content_log"
                )
            )
        ).scalars().all()
        assert len(entries) == 1
        assert entries[0].action_type == "ai_content_generate"
        assert (entries[0].payload or {}).get("event_type") == "ai_content_lifecycle"
        assert (entries[0].payload or {}).get("ai_content_log_id") == result[
            "ai_content_log_id"
        ]


# ---------------------------------------------------------------------------
# Hash 字段
# ---------------------------------------------------------------------------


class TestHashFields:
    """content_hash / prompt_hash 计算逻辑。"""

    @pytest.mark.asyncio
    async def test_wrap_content_hash_consistency(self):
        """同 content 产生相同的 hash（sha256 64 字符）。"""
        r1 = await wrap_ai_output_with_log(content="完全一致的文本")
        r2 = await wrap_ai_output_with_log(content="完全一致的文本")
        assert r1["content_hash"] == r2["content_hash"]
        assert len(r1["content_hash"]) == 64

        # 与显式 sha256 计算结果对齐
        expected = hashlib.sha256("完全一致的文本".encode("utf-8")).hexdigest()
        assert r1["content_hash"] == expected

    @pytest.mark.asyncio
    async def test_wrap_content_hash_differs_for_different_content(self):
        """不同 content 产生不同 hash。"""
        r1 = await wrap_ai_output_with_log(content="文本 A")
        r2 = await wrap_ai_output_with_log(content="文本 B")
        assert r1["content_hash"] != r2["content_hash"]

    @pytest.mark.asyncio
    async def test_wrap_prompt_hash_from_text(self):
        """prompt_text 提供且 prompt_hash=None 时自动计算。"""
        prompt = "请根据科目变动分析原因"
        result = await wrap_ai_output_with_log(
            content="x",
            prompt_text=prompt,
        )
        expected = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        assert result["prompt_hash"] == expected
        assert len(result["prompt_hash"]) == 64

    @pytest.mark.asyncio
    async def test_wrap_prompt_hash_explicit_overrides_text(self):
        """同时给 prompt_hash + prompt_text 时优先用 prompt_hash。"""
        explicit = "a" * 64
        result = await wrap_ai_output_with_log(
            content="x",
            prompt_hash=explicit,
            prompt_text="某些不同的 prompt 文本",
        )
        assert result["prompt_hash"] == explicit

    @pytest.mark.asyncio
    async def test_wrap_prompt_hash_none_when_neither_provided(self):
        """既不传 prompt_hash 也不传 prompt_text 时为 None。"""
        result = await wrap_ai_output_with_log(content="x")
        assert result["prompt_hash"] is None
