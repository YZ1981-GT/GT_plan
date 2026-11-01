"""管理层声明书只读取正式 ``unadjusted_misstatements`` 的契约测试。"""
from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import (
    Adjustment,
    Materiality,
    MisstatementType,
    UnadjustedMisstatement,
)
from app.models.base import Base, UserRole
from app.models.core import Project, ProjectStatus, ProjectType, User
from app.services.misstatement_summary_service import MisstatementSummaryService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
_TABLES = [
    User.__table__, Project.__table__, Adjustment.__table__,
    UnadjustedMisstatement.__table__, Materiality.__table__,
]


def _run(body):
    async def runner():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                await body(session)
        finally:
            await engine.dispose()
    asyncio.run(runner())


async def _seed_project(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    user_id, project_id = uuid.uuid4(), uuid.uuid4()
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


async def _misstatement(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID,
    *, year: int = 2025, amount: str = "1000", description: str = "测试错报",
    deleted: bool = False, reversed_: bool = False,
) -> None:
    session.add(UnadjustedMisstatement(
        id=uuid.uuid4(), project_id=project_id, year=year,
        misstatement_description=description,
        misstatement_amount=Decimal(amount), misstatement_type=MisstatementType.factual,
        management_reason="管理层认为金额不重大",
        prior_year_status="reversed" if reversed_ else "new",
        is_deleted=deleted, created_by=user_id,
    ))
    await session.flush()


def test_no_formal_misstatement_returns_empty_indicator():
    async def body(session: AsyncSession):
        _, project_id = await _seed_project(session)
        assert await MisstatementSummaryService(session).get_for_representation_letter(project_id, 2025) == "无未更正错报。"
    _run(body)


def test_legacy_passed_reason_is_not_a_second_truth_source():
    async def body(session: AsyncSession):
        user_id, project_id = await _seed_project(session)
        session.add(Adjustment(
            project_id=project_id, year=2025, company_code="001", adjustment_no="AJE-1",
            adjustment_type="aje", account_code="1001", debit_amount=Decimal("500"),
            credit_amount=Decimal("0"), entry_group_id=uuid.uuid4(),
            passed_reason="遗留原因不应再进入声明书", created_by=user_id,
        ))
        await session.flush()
        text = await MisstatementSummaryService(session).get_for_representation_letter(project_id, 2025)
        assert text == "无未更正错报。"
    _run(body)


def test_deleted_and_reversed_formal_records_are_excluded():
    async def body(session: AsyncSession):
        user_id, project_id = await _seed_project(session)
        await _misstatement(session, user_id, project_id, deleted=True)
        await _misstatement(session, user_id, project_id, reversed_=True)
        assert await MisstatementSummaryService(session).get_for_representation_letter(project_id, 2025) == "无未更正错报。"
    _run(body)


def test_formal_records_render_amounts_and_truncate_after_ten():
    async def body(session: AsyncSession):
        user_id, project_id = await _seed_project(session)
        for index in range(12):
            await _misstatement(
                session, user_id, project_id,
                amount=str(1000 + index), description=f"错报项{index + 1}",
            )
        text = await MisstatementSummaryService(session).get_for_representation_letter(project_id, 2025)
        assert "未更正错报清单" in text
        assert "错报项1" in text and "1,000.00" in text
        assert "共12项" in text
        assert sum(1 for line in text.splitlines() if line[:1].isdigit()) == 10
    _run(body)


def test_formal_records_are_isolated_by_year():
    async def body(session: AsyncSession):
        user_id, project_id = await _seed_project(session)
        await _misstatement(session, user_id, project_id, year=2024, description="去年错报")
        service = MisstatementSummaryService(session)
        assert await service.get_for_representation_letter(project_id, 2025) == "无未更正错报。"
        assert "去年错报" in await service.get_for_representation_letter(project_id, 2024)
    _run(body)


def test_communication_updates_formal_record_only():
    async def body(session: AsyncSession):
        user_id, project_id = await _seed_project(session)
        row = UnadjustedMisstatement(
            id=uuid.uuid4(), project_id=project_id, year=2025,
            misstatement_description="应收账款少计", misstatement_amount=Decimal("25000"),
            misstatement_type=MisstatementType.factual, created_by=user_id,
        )
        session.add(row)
        await session.flush()
        result = await MisstatementSummaryService(session).record_communication(
            project_id, 2025, row.id, "2025-12-31T10:00:00+08:00", "管理层不予更正",
        )
        assert result["management_reason"] == "管理层不予更正"
        assert row.management_communication_at is not None
    _run(body)
