"""归档章节 §05 — AI 贡献明细生成器测试

V3 收官增强 Req 6.6 验证：

- test_no_ai_logs_returns_none — 无 ai_content_log 记录时返回 None
- test_pending_logs_grouped — pending/confirmed 混合时按状态分组
- test_instance_type_grouped — workpaper/adjustment/misstatement 按类型分组
- test_register_section_in_archive — registry.list_all 含 prefix='05'
- test_full_report_format — 完整文本含项目名/日期/计数/明细
- test_content_preview_truncated — 长内容截断到 80 字符
- test_revised_content_shown_when_revised — revised 状态显示修订后内容

Validates: Requirements 6.6
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
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

from app.services import ai_content_log_service  # noqa: E402
from app.services.archive_generators.ai_contributions_generator import (  # noqa: E402
    generate_ai_contributions_report,
)
from app.services import archive_section_registry  # noqa: E402

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
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
async def user_and_project(db_session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID, str]:
    """预先写入 users / projects 各一条，返回 (user_id, project_id, project_name)。"""
    from app.models.base import ProjectStatus, UserRole
    from app.models.core import Project, User

    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    project_name = "AI 贡献测试项目"

    user = User(
        id=user_id,
        username=f"tester-{user_id.hex[:8]}",
        email=f"{user_id.hex[:8]}@test.local",
        hashed_password="hashed",
        role=UserRole.auditor,
        is_active=True,
    )
    project = Project(
        id=project_id,
        name=project_name,
        client_name="测试客户",
        status=ProjectStatus.execution,
    )
    db_session.add(user)
    db_session.add(project)
    await db_session.commit()
    return user_id, project_id, project_name


async def _create_log(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    instance_type: str = "workpaper",
    target_cell: str | None = "narrative",
    content: str = "AI 生成内容样例：本期收入同比增长 12%，主要源于新产品销售。",
    model: str = "qwen3.5-27b",
    content_hash: str | None = None,
):
    return await ai_content_log_service.create(
        db=db_session,
        project_id=project_id,
        user_id=user_id,
        instance_type=instance_type,
        instance_id=uuid.uuid4(),
        target_cell=target_cell,
        model=model,
        prompt_hash="p" * 64,
        content_hash=content_hash or uuid.uuid4().hex + uuid.uuid4().hex[:32],
        generated_content=content,
        confidence=Decimal("0.85"),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNoLogsReturnsNone:
    @pytest.mark.asyncio
    async def test_no_ai_logs_returns_none(
        self, db_session: AsyncSession, user_and_project
    ):
        """无 ai_content_log 记录时返回 None。"""
        _, project_id, _ = user_and_project
        result = await generate_ai_contributions_report(project_id, db_session)
        assert result is None


class TestStatusGrouping:
    @pytest.mark.asyncio
    async def test_pending_logs_grouped(
        self, db_session: AsyncSession, user_and_project
    ):
        """pending/confirmed/revised/rejected 混合时各状态分组计数正确。"""
        user_id, project_id, _ = user_and_project

        # 2 pending
        await _create_log(db_session, user_id, project_id, content_hash="a" * 64)
        await _create_log(db_session, user_id, project_id, content_hash="b" * 64)
        # 1 confirmed
        log_c = await _create_log(
            db_session, user_id, project_id, content_hash="c" * 64
        )
        # 1 revised
        log_d = await _create_log(
            db_session, user_id, project_id, content_hash="d" * 64
        )
        # 1 rejected
        log_e = await _create_log(
            db_session, user_id, project_id, content_hash="e" * 64
        )
        await db_session.commit()

        await ai_content_log_service.confirm(
            db=db_session, log_id=log_c.id, user_id=user_id
        )
        await ai_content_log_service.revise(
            db=db_session,
            log_id=log_d.id,
            user_id=user_id,
            revised_content="审计师修订后的版本",
        )
        await ai_content_log_service.reject(
            db=db_session, log_id=log_e.id, user_id=user_id
        )
        await db_session.commit()

        result = await generate_ai_contributions_report(project_id, db_session)
        assert result is not None

        text = result.decode("utf-8")
        # 总数 5
        assert "AI 内容总数: 5" in text
        # 按状态分组（中英对照）
        assert "待确认 (pending): 2" in text
        assert "已确认 (confirmed): 1" in text
        assert "已修订 (revised): 1" in text
        assert "已拒绝 (rejected): 1" in text


class TestInstanceTypeGrouping:
    @pytest.mark.asyncio
    async def test_instance_type_grouped(
        self, db_session: AsyncSession, user_and_project
    ):
        """workpaper/adjustment/misstatement 按 instance_type 分组。"""
        user_id, project_id, _ = user_and_project

        # 2 workpaper
        await _create_log(
            db_session,
            user_id,
            project_id,
            instance_type="workpaper",
            content_hash="1" * 64,
        )
        await _create_log(
            db_session,
            user_id,
            project_id,
            instance_type="workpaper",
            content_hash="2" * 64,
        )
        # 1 adjustment
        await _create_log(
            db_session,
            user_id,
            project_id,
            instance_type="adjustment",
            content_hash="3" * 64,
        )
        # 1 misstatement
        await _create_log(
            db_session,
            user_id,
            project_id,
            instance_type="misstatement",
            content_hash="4" * 64,
        )
        await db_session.commit()

        result = await generate_ai_contributions_report(project_id, db_session)
        assert result is not None

        text = result.decode("utf-8")
        # 各分组标题
        assert "[workpaper] 共 2 条" in text
        assert "[adjustment] 共 1 条" in text
        assert "[misstatement] 共 1 条" in text


class TestRegistry:
    def test_register_section_in_archive(self):
        """archive_section_registry.list_all 含 prefix='05' 的 AI 贡献明细。"""
        # 模块导入时已自动注册
        sections = archive_section_registry.list_all()
        prefixes = {s.order_prefix: s for s in sections}
        assert "05" in prefixes, (
            f"prefix='05' 应已注册，当前: {sorted(prefixes.keys())}"
        )

        section = prefixes["05"]
        assert section.filename == "05-AI贡献明细.txt"
        assert "AI 贡献明细" in section.description
        assert callable(section.generator_func)


class TestFullReportFormat:
    @pytest.mark.asyncio
    async def test_full_report_format(
        self, db_session: AsyncSession, user_and_project
    ):
        """完整文本含：项目名 / 日期 / 计数 / 明细字段。"""
        user_id, project_id, project_name = user_and_project

        log = await _create_log(
            db_session,
            user_id,
            project_id,
            instance_type="workpaper",
            target_cell="narrative",
            content="AI 关于销售收入分析的输出",
            model="qwen3.5-27b",
            content_hash="f" * 64,
        )
        await db_session.commit()
        # confirm 一条以验证 confirmed_by/confirmed_at 字段存在
        await ai_content_log_service.confirm(
            db=db_session, log_id=log.id, user_id=user_id
        )
        await db_session.commit()

        result = await generate_ai_contributions_report(project_id, db_session)
        assert result is not None
        text = result.decode("utf-8")

        # 标题 + 项目名 + 日期
        assert "AI 贡献明细" in text
        assert f"项目: {project_name}" in text
        assert "日期:" in text
        assert "UTC" in text

        # 计数
        assert "AI 内容总数: 1" in text

        # 状态分组
        assert "已确认 (confirmed): 1" in text

        # 明细：模型 / 目标 / 内容预览 / 状态 / 确认人 / 确认时间
        assert "模型: qwen3.5-27b" in text
        assert "目标: workpaper:" in text
        assert "AI 关于销售收入分析的输出" in text
        assert "确认人:" in text
        assert "确认时间:" in text

    @pytest.mark.asyncio
    async def test_content_preview_truncated_to_80_chars(
        self, db_session: AsyncSession, user_and_project
    ):
        """超长内容截断到 80 字符 + '…'。"""
        user_id, project_id, _ = user_and_project

        long_content = "A" * 200
        await _create_log(
            db_session,
            user_id,
            project_id,
            content=long_content,
            content_hash="9" * 64,
        )
        await db_session.commit()

        result = await generate_ai_contributions_report(project_id, db_session)
        assert result is not None
        text = result.decode("utf-8")
        # 应包含 80 个 A 后跟省略号
        assert "A" * 80 + "…" in text
        # 不应包含完整 200 个 A
        assert "A" * 200 not in text

    @pytest.mark.asyncio
    async def test_revised_content_shown_when_revised(
        self, db_session: AsyncSession, user_and_project
    ):
        """revised 状态时显示修订后内容（而非原始）。"""
        user_id, project_id, _ = user_and_project

        log = await _create_log(
            db_session,
            user_id,
            project_id,
            content="AI 原始输出（不应在报告中显示）",
            content_hash="r" * 64,
        )
        await db_session.commit()

        revised_text = "审计师修订后的最终版本说明文字"
        await ai_content_log_service.revise(
            db=db_session,
            log_id=log.id,
            user_id=user_id,
            revised_content=revised_text,
        )
        await db_session.commit()

        result = await generate_ai_contributions_report(project_id, db_session)
        assert result is not None
        text = result.decode("utf-8")

        assert revised_text in text
        # revised 状态下原始 generated_content 不应出现在内容预览中
        assert "AI 原始输出（不应在报告中显示）" not in text
        assert "已修订 (revised): 1" in text
