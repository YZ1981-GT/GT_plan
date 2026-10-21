"""真实 PostgreSQL 双事务验证 wp_formula 条件 UPDATE CAS。"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.workpaper_models import (
    WorkingPaper,
    WpFileStatus,
    WpFormula,
    WpIndex,
    WpReviewStatus,
    WpSourceType,
    WpStatus,
)
from app.services.wp_formula_service import FormulaVersionConflict, WpFormulaService

pytestmark = pytest.mark.pg_only


def _pg_url() -> str:
    url = str(settings.DATABASE_URL)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


@pytest.mark.asyncio
async def test_two_transactions_with_same_expected_version_only_one_succeeds():
    url = _pg_url()
    assert url.startswith("postgresql+asyncpg://"), "本测试必须使用真实 PostgreSQL"
    connect_args = {"ssl": False} if getattr(settings, "DB_DISABLE_SSL", False) else {}
    engine = create_async_engine(url, poolclass=NullPool, connect_args=connect_args)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    formula_id = uuid.uuid4()
    project_id = uuid.uuid4()
    wp_index_id = uuid.uuid4()
    wp_id = uuid.uuid4()
    sheet_name = f"_FMCAS_{uuid.uuid4().hex}"

    try:
        async with Session() as setup:
            setup.add(Project(
                id=project_id,
                name=f"【测试】公式CAS_{project_id.hex[:8]}",
                client_name="公式CAS测试",
                project_type=ProjectType.annual,
                status=ProjectStatus.planning,
                template_type="soe",
                report_scope="standalone",
            ))
            await setup.flush()
            setup.add(WpIndex(
                id=wp_index_id, project_id=project_id, wp_code="A99",
                wp_name="CAS测试底稿", status=WpStatus.not_started, is_deleted=False,
            ))
            await setup.flush()
            setup.add(WorkingPaper(
                id=wp_id, project_id=project_id, wp_index_id=wp_index_id,
                file_path="/tmp/formula-cas.xlsx", source_type=WpSourceType.template,
                status=WpFileStatus.draft, review_status=WpReviewStatus.not_submitted,
                is_deleted=False,
            ))
            await setup.flush()
            setup.add(WpFormula(
                id=formula_id,
                project_id=project_id,
                wp_id=wp_id,
                sheet_name=sheet_name,
                target_cell="Z999",
                expression="1 + 1",
                formula_type="auto_calc",
                category="auto_calc",
                definition_version=1,
            ))
            await setup.commit()

        ready = asyncio.Event()
        entered = 0
        lock = asyncio.Lock()

        async def contender(expression: str) -> str:
            nonlocal entered
            async with Session() as session:
                async with lock:
                    entered += 1
                    if entered == 2:
                        ready.set()
                await ready.wait()
                try:
                    saved, issues = await WpFormulaService().save(
                        session,
                        project_id=project_id,
                        wp_id=wp_id,
                        sheet_name=sheet_name,
                        target_cell="Z999",
                        expression=expression,
                        year=2025,
                        expected_version=1,
                    )
                    assert saved is not None and not issues
                    await session.commit()
                    return "saved"
                except FormulaVersionConflict:
                    await session.rollback()
                    return "conflict"

        outcomes = await asyncio.gather(contender("2 + 2"), contender("3 + 3"))
        assert sorted(outcomes) == ["conflict", "saved"]

        async with Session() as verify:
            row = (
                await verify.execute(sa.select(WpFormula).where(WpFormula.id == formula_id))
            ).scalar_one()
            assert row.definition_version == 2
            assert row.expression in {"2 + 2", "3 + 3"}
    finally:
        try:
            async with Session() as cleanup:
                await cleanup.execute(sa.delete(WpFormula).where(WpFormula.id == formula_id))
                await cleanup.execute(sa.delete(WorkingPaper).where(WorkingPaper.id == wp_id))
                await cleanup.execute(sa.delete(WpIndex).where(WpIndex.id == wp_index_id))
                await cleanup.execute(sa.delete(Project).where(Project.id == project_id))
                await cleanup.commit()
        finally:
            await engine.dispose()
