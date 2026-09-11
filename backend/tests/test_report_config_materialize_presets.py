"""预设公式落入项目级配置（``project:{id}``）的守卫。

## 为什么需要这条能力

公式管理中心的「全局公式」只统计项目级公式（``wp_formula``），而报表预设存在
``report_config`` 且是**模板级**（唯一键 ``report_type+row_code+applicable_standard``
不含 project_id）。用户反馈「预设带不进项目」即指此。

平台已有的项目级约定是 ``report_config.applicable_standard = 'project:{project_id}'``，
且该口径**确有真实消费方**（都按 project 优先、standard 兜底）：
``report_account_mapping`` / ``four_table.report_line_accounts`` /
``four_table.semantic_account_resolver`` / ``four_table.i_cycle_accounts``。
因此把预设落成项目级行不是死数据，会真实影响取数。

## 本文件锁死

1. ``materialize_project_presets`` 只落**有公式**的行（无公式结构行不影响取数）；
2. 幂等：重复执行 created=0、skipped=N；
3. ``overwrite=True`` 才覆盖已有项目级公式；
4. 分类/说明/来源一并复制（此前 ``clone_report_config`` 只复制 formula ⇒
   项目级行全变「未分类」且丢说明）。
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.report_models import FinancialReportType, ReportConfig
from app.services.report_config_service import ReportConfigService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

STANDARD = "test_materialize_standard"

_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


def _master_row(row_code: str, formula: str | None, row_number: int) -> ReportConfig:
    return ReportConfig(
        id=uuid.uuid4(),
        report_type=FinancialReportType.balance_sheet,
        row_number=row_number,
        row_code=row_code,
        row_name=f"行 {row_code}",
        indent_level=0,
        formula=formula,
        formula_category="auto_calc" if formula else None,
        formula_description="从余额表取数" if formula else None,
        formula_source="preset_seed" if formula else None,
        applicable_standard=STANDARD,
        is_total_row=False,
    )


@pytest_asyncio.fixture
async def master_rows(db_session: AsyncSession):
    """两条带公式 + 一条无公式的模板行。"""
    rows = [
        _master_row("MT-001", "TB('1001','期末余额')", 1),
        _master_row("MT-002", "TB('1122','期末余额')", 2),
        _master_row("MT-003", None, 3),
    ]
    for r in rows:
        db_session.add(r)
    await db_session.flush()
    return rows


async def _project_rows(db_session: AsyncSession, project_id: uuid.UUID) -> list[ReportConfig]:
    result = await db_session.execute(
        sa.select(ReportConfig).where(
            ReportConfig.applicable_standard == f"project:{project_id}",
            ReportConfig.is_deleted == sa.false(),
        )
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_only_rows_with_formula_are_materialized(
    db_session: AsyncSession, master_rows
):
    svc = ReportConfigService(db_session)
    pid = uuid.uuid4()

    result = await svc.materialize_project_presets(pid, applicable_standard=STANDARD)

    assert result["master_with_formula"] == 2
    assert result["created"] == 2
    assert result["skipped"] == 0
    codes = sorted(r.row_code for r in await _project_rows(db_session, pid))
    assert codes == ["MT-001", "MT-002"], "无公式的结构行不应落入项目级"


@pytest.mark.asyncio
async def test_category_description_and_source_are_copied(
    db_session: AsyncSession, master_rows
):
    svc = ReportConfigService(db_session)
    pid = uuid.uuid4()

    await svc.materialize_project_presets(pid, applicable_standard=STANDARD)

    rows = {r.row_code: r for r in await _project_rows(db_session, pid)}
    hit = rows["MT-001"]
    assert hit.formula == "TB('1001','期末余额')"
    assert hit.formula_category == "auto_calc"
    assert hit.formula_description == "从余额表取数"
    assert hit.formula_source == "preset_seed"


@pytest.mark.asyncio
async def test_idempotent_second_run_creates_nothing(
    db_session: AsyncSession, master_rows
):
    svc = ReportConfigService(db_session)
    pid = uuid.uuid4()

    first = await svc.materialize_project_presets(pid, applicable_standard=STANDARD)
    second = await svc.materialize_project_presets(pid, applicable_standard=STANDARD)

    assert first["created"] == 2
    assert second["created"] == 0
    assert second["skipped"] == 2
    assert len(await _project_rows(db_session, pid)) == 2, "重复执行不得产生重复行"


@pytest.mark.asyncio
async def test_project_edit_preserved_unless_overwrite(
    db_session: AsyncSession, master_rows
):
    svc = ReportConfigService(db_session)
    pid = uuid.uuid4()
    await svc.materialize_project_presets(pid, applicable_standard=STANDARD)

    rows = {r.row_code: r for r in await _project_rows(db_session, pid)}
    rows["MT-001"].formula = "TB('1001','期初余额')"  # 项目侧改过
    await db_session.flush()

    keep = await svc.materialize_project_presets(pid, applicable_standard=STANDARD)
    assert keep["updated"] == 0
    after = {r.row_code: r for r in await _project_rows(db_session, pid)}
    assert after["MT-001"].formula == "TB('1001','期初余额')", "默认不得覆盖项目侧改动"

    forced = await svc.materialize_project_presets(
        pid, applicable_standard=STANDARD, overwrite=True
    )
    assert forced["updated"] == 1
    after2 = {r.row_code: r for r in await _project_rows(db_session, pid)}
    assert after2["MT-001"].formula == "TB('1001','期末余额')"


@pytest.mark.asyncio
async def test_legacy_clone_also_copies_category(db_session: AsyncSession, master_rows):
    """历史的全量克隆同样要带分类/说明（此前只复制 formula）。"""
    svc = ReportConfigService(db_session)
    pid = uuid.uuid4()

    count = await svc.clone_report_config(pid, applicable_standard=STANDARD)

    assert count == 3, "strict 模式是全量克隆（含无公式结构行）"
    rows = {r.row_code: r for r in await _project_rows(db_session, pid)}
    assert rows["MT-001"].formula_category == "auto_calc"
    assert rows["MT-001"].formula_description == "从余额表取数"
