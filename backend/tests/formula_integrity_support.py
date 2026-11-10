"""公式完整性专用夹具：只有隔离内存库，不使用应用默认引擎。"""
from types import SimpleNamespace
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.audit_platform_models import TrialBalance
from app.models.bad_debt_models import BadDebtDetailRow
from app.models.base import Base
from app.models.core import Project
from app.models.report_generation_models import ReportGenerationRun
from app.models.report_models import DisclosureNote, FinancialReport, FinancialReportType
from app.models.workpaper_models import WorkingPaper, WpIndex, WpSourceType


@pytest_asyncio.fixture
async def integrity_world():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [model.__table__ for model in (
        Project, WpIndex, WorkingPaper, BadDebtDetailRow, DisclosureNote,
        TrialBalance, ReportGenerationRun, FinancialReport,
    )]
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=tables))
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            project = Project(id=uuid4(), name="【测试】公式完整性甲", client_name="隔离甲", audit_year=2025)
            other = Project(id=uuid4(), name="【测试】公式完整性乙", client_name="隔离乙", audit_year=2025)
            db.add_all([project, other])
            await db.flush()
            try:
                yield SimpleNamespace(db=db, project=project, other=other)
            finally:
                await db.rollback()
    finally:
        await engine.dispose()


async def add_wp(world, code, parsed_data, *, project=None, index_project=None,
                 index_deleted=False, paper_deleted=False):
    project = project or world.project
    index_project = index_project or project
    index = WpIndex(id=uuid4(), project_id=index_project.id, wp_code=code,
                    wp_name=f"【测试】{code}", is_deleted=index_deleted)
    paper = WorkingPaper(id=uuid4(), project_id=project.id, wp_index_id=index.id,
                         file_path="isolated-formula-integrity.xlsx",
                         source_type=WpSourceType.template, parsed_data=parsed_data,
                         is_deleted=paper_deleted)
    world.db.add_all([index, paper])
    await world.db.flush()
    return index, paper


async def add_note(world, table_data, *, project=None, year=2025,
                   section="五、1", deleted=False):
    note = DisclosureNote(project_id=(project or world.project).id, year=year,
                          note_section=section, section_title="【测试】货币资金",
                          table_data=table_data, is_deleted=deleted)
    world.db.add(note)
    await world.db.flush()
    return note


def note_table(current="23.50", prior="7.25"):
    return {"headers": ["项目", "期末余额", "期初余额"],
            "rows": [{"label": "合计", "values": [current, prior]}]}


def report_config(code="BS999", formula="1", **kwargs):
    fields = dict(row_code=code, row_name=f"【测试】{code}", formula=formula,
                  formula_category="amount", formula_description=None,
                  formula_source="system", indent_level=0, is_total_row=False,
                  aje_formula=None, rje_formula=None)
    fields.update(kwargs)
    return SimpleNamespace(**fields)


async def add_report(world, code, amount, *, project=None, year=2025, deleted=False, **kwargs):
    row = FinancialReport(project_id=(project or world.project).id, year=year,
                          report_type=FinancialReportType.balance_sheet, row_code=code,
                          row_name=f"【测试】{code}", current_period_amount=amount,
                          is_deleted=deleted, **kwargs)
    world.db.add(row)
    await world.db.flush()
    return row
