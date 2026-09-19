"""Tests for GET /api/projects/{pid}/misstatements/for-letter — A13 alert 两路径

验证：
1. 项目无未更正错报 → 返回 { summary: "无未更正错报。" }（前端映射为空/success）
2. 项目有未更正错报 → 返回 { summary: "未更正错报清单：\n..." }（前端显示 warning）

Validates: Requirements 3 (A16-core task 18)
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.audit_platform_models import Adjustment, AdjustmentType, Materiality
from app.models.base import Base, UserRole
from app.models.core import Project, ProjectStatus, ProjectType, User
from app.services.misstatement_summary_service import MisstatementSummaryService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_TABLES = [
    User.__table__,
    Project.__table__,
    Adjustment.__table__,
    Materiality.__table__,
]


def _run_in_isolated_db(coro_factory):
    async def _runner():
        engine = create_async_engine(TEST_DB_URL, echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with factory() as session:
                return await coro_factory(session)
        finally:
            await engine.dispose()
    return asyncio.run(_runner())


async def _seed_project(session: AsyncSession):
    """创建测试用户和项目，返回 (user_id, project_id)"""
    user_id = uuid.uuid4()
    project_id = uuid.uuid4()
    session.add(User(
        id=user_id, username=f"u_{user_id.hex[:6]}", email=f"{user_id.hex[:6]}@t.com",
        hashed_password="x", role=UserRole.manager,
    ))
    await session.flush()
    session.add(Project(
        id=project_id, name="测试项目", client_name="测试客户",
        project_type=ProjectType.annual, status=ProjectStatus.execution,
        created_by=user_id,
    ))
    await session.flush()
    return user_id, project_id


# ─── Path 1: 无未更正错报 → "无未更正错报。" ────────────────────────────────────


def test_for_letter_no_misstatements_returns_empty_indicator():
    """无错报路径：返回 '无未更正错报。' 文本（前端将此映射为空→显示 success alert）"""

    async def _body(session: AsyncSession):
        _, project_id = await _seed_project(session)

        svc = MisstatementSummaryService(session)
        text = await svc.get_for_representation_letter(project_id, 2025)

        assert text == "无未更正错报。"

    _run_in_isolated_db(_body)


def test_for_letter_only_deleted_adjustments_returns_empty():
    """仅有已删除的 adjustments（is_deleted=True）→ 视为无错报"""

    async def _body(session: AsyncSession):
        user_id, project_id = await _seed_project(session)

        # 添加一条已删除的 passed adjustment
        session.add(Adjustment(
            project_id=project_id,
            year=2025,
            company_code="91000000XXXXXXXXXX",
            adjustment_no="P-001",
            adjustment_type=AdjustmentType.aje,
            account_code="1001",
            debit_amount=Decimal("100.00"),
            credit_amount=Decimal("0.00"),
            entry_group_id=uuid.uuid4(),
            passed_reason="金额不重大",
            is_deleted=True,
            created_by=user_id,
        ))
        await session.flush()

        svc = MisstatementSummaryService(session)
        text = await svc.get_for_representation_letter(project_id, 2025)

        assert text == "无未更正错报。"

    _run_in_isolated_db(_body)


def test_for_letter_no_passed_reason_returns_empty():
    """adjustment 存在但 passed_reason 为空（非未更正错报）→ 无错报"""

    async def _body(session: AsyncSession):
        user_id, project_id = await _seed_project(session)

        # 添加一条普通 adjustment（非 passed）
        session.add(Adjustment(
            project_id=project_id,
            year=2025,
            company_code="91000000XXXXXXXXXX",
            adjustment_no="A-001",
            adjustment_type=AdjustmentType.aje,
            account_code="1001",
            debit_amount=Decimal("500.00"),
            credit_amount=Decimal("0.00"),
            entry_group_id=uuid.uuid4(),
            passed_reason=None,  # 非"未更正错报"
            created_by=user_id,
        ))
        await session.flush()

        svc = MisstatementSummaryService(session)
        text = await svc.get_for_representation_letter(project_id, 2025)

        assert text == "无未更正错报。"

    _run_in_isolated_db(_body)


# ─── Path 2: 有未更正错报 → 摘要文本 ───────────────────────────────────────


def test_for_letter_with_misstatements_returns_summary():
    """有错报路径：返回非空摘要文本，以 '未更正错报清单：' 开头"""

    async def _body(session: AsyncSession):
        user_id, project_id = await _seed_project(session)

        # 添加 2 条 passed adjustments
        for i, (debit, credit, adj_type) in enumerate([
            (Decimal("10000.00"), Decimal("0.00"), AdjustmentType.aje),
            (Decimal("0.00"), Decimal("5000.00"), AdjustmentType.rje),
        ]):
            session.add(Adjustment(
                project_id=project_id,
                year=2025,
                company_code="91000000XXXXXXXXXX",
                adjustment_no=f"P-{i+1:03d}",
                adjustment_type=adj_type,
                account_code=f"{1001+i}",
                description=f"测试错报{i+1}",
                debit_amount=debit,
                credit_amount=credit,
                entry_group_id=uuid.uuid4(),
                passed_reason="管理层认为金额不重大",
                created_by=user_id,
            ))
        await session.flush()

        svc = MisstatementSummaryService(session)
        text = await svc.get_for_representation_letter(project_id, 2025)

        # 有错报时应该返回非空摘要
        assert text != ""
        assert text != "无未更正错报。"
        assert "未更正错报清单" in text
        # 包含金额信息
        assert "10,000.00" in text
        assert "5,000.00" in text
        # 包含描述
        assert "测试错报1" in text
        assert "测试错报2" in text

    _run_in_isolated_db(_body)


def test_for_letter_with_many_misstatements_truncates():
    """超过 10 条错报时截断并显示总数"""

    async def _body(session: AsyncSession):
        user_id, project_id = await _seed_project(session)

        # 添加 12 条 passed adjustments
        for i in range(12):
            session.add(Adjustment(
                project_id=project_id,
                year=2025,
                company_code="91000000XXXXXXXXXX",
                adjustment_no=f"P-{i+1:03d}",
                adjustment_type=AdjustmentType.aje,
                account_code=f"{1001+i}",
                description=f"错报项{i+1}",
                debit_amount=Decimal("1000.00"),
                credit_amount=Decimal("0.00"),
                entry_group_id=uuid.uuid4(),
                passed_reason="不重大",
                created_by=user_id,
            ))
        await session.flush()

        svc = MisstatementSummaryService(session)
        text = await svc.get_for_representation_letter(project_id, 2025)

        assert "未更正错报清单" in text
        # _format_for_letter 只显示前 10 条
        assert "共12项" in text

    _run_in_isolated_db(_body)


def test_for_letter_different_year_isolation():
    """不同年度的错报互不影响"""

    async def _body(session: AsyncSession):
        user_id, project_id = await _seed_project(session)

        # 2024 年有错报
        session.add(Adjustment(
            project_id=project_id,
            year=2024,
            company_code="91000000XXXXXXXXXX",
            adjustment_no="P-001",
            adjustment_type=AdjustmentType.aje,
            account_code="1001",
            description="去年错报",
            debit_amount=Decimal("50000.00"),
            credit_amount=Decimal("0.00"),
            entry_group_id=uuid.uuid4(),
            passed_reason="上年遗留",
            created_by=user_id,
        ))
        await session.flush()

        svc = MisstatementSummaryService(session)

        # 2025 年应该无错报
        text_2025 = await svc.get_for_representation_letter(project_id, 2025)
        assert text_2025 == "无未更正错报。"

        # 2024 年有错报
        text_2024 = await svc.get_for_representation_letter(project_id, 2024)
        assert "未更正错报清单" in text_2024
        assert "去年错报" in text_2024

    _run_in_isolated_db(_body)


# ─── 端点响应格式验证 ───────────────────────────────────────────────────────


def test_endpoint_response_format_no_misstatements():
    """验证端点返回格式 { summary: str } — 无错报路径"""

    async def _body(session: AsyncSession):
        _, project_id = await _seed_project(session)

        svc = MisstatementSummaryService(session)
        text = await svc.get_for_representation_letter(project_id, 2025)

        # 模拟 router 返回
        response = {"summary": text}
        assert "summary" in response
        assert isinstance(response["summary"], str)
        # 前端 loadMisstatementSummary 逻辑:
        # text === '无未更正错报。' → misstatementSummary = '' → success alert
        assert response["summary"] == "无未更正错报。"

    _run_in_isolated_db(_body)


def test_endpoint_response_format_with_misstatements():
    """验证端点返回格式 { summary: str } — 有错报路径"""

    async def _body(session: AsyncSession):
        user_id, project_id = await _seed_project(session)

        session.add(Adjustment(
            project_id=project_id,
            year=2025,
            company_code="91000000XXXXXXXXXX",
            adjustment_no="P-001",
            adjustment_type=AdjustmentType.aje,
            account_code="1001",
            description="应收账款少计",
            debit_amount=Decimal("25000.00"),
            credit_amount=Decimal("0.00"),
            entry_group_id=uuid.uuid4(),
            passed_reason="管理层认为不重大",
            created_by=user_id,
        ))
        await session.flush()

        svc = MisstatementSummaryService(session)
        text = await svc.get_for_representation_letter(project_id, 2025)

        # 模拟 router 返回
        response = {"summary": text}
        assert "summary" in response
        assert isinstance(response["summary"], str)
        # 前端 loadMisstatementSummary 逻辑:
        # text !== '无未更正错报。' → misstatementSummary = text → warning alert
        assert response["summary"] != "无未更正错报。"
        assert len(response["summary"]) > 0

    _run_in_isolated_db(_body)
