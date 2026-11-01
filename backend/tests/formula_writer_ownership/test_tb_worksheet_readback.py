"""R3：试算平衡表持久化 content.rows 读回 + CAS（后端端点契约）。

直接调 `routers.consol_worksheet_data` 的协程（CAS 逻辑在函数体内），用真实 SQLite
会话落库，不走 HTTP —— 鉴权依赖是 FastAPI Depends，直接调用时由参数传入假用户。
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.base import Base  # noqa: E402
from app.models.consol_worksheet_data_models import ConsolWorksheetData  # noqa: E402
from app.routers.consol_worksheet_data import (  # noqa: E402
    WorksheetDataSave,
    get_worksheet_data,
    save_worksheet_data,
)

PID = uuid.uuid4()
YEAR = 2025
SHEET = "tb_summary_balance_sheet"
USER = SimpleNamespace(id=uuid.uuid4())

# 零值、断开公式、手工重分类三类必须逐字读回。
ROWS = [
    {"row_code": "1", "row_name": "货币资金", "unadjusted": 0, "rcl_dr": 0, "rcl_cr": None,
     "formula_detached": True, "manual_rcl_dr": True},
    {"row_code": "2", "row_name": "应收账款", "unadjusted": 1234.56, "rcl_dr": 10, "rcl_cr": 20,
     "formula_detached": False},
]


@pytest.fixture
async def db() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(
            c, tables=[ConsolWorksheetData.__table__]))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _save(db: AsyncSession, rows, expected_version=None):
    return await save_worksheet_data(
        PID, YEAR, SHEET,
        WorksheetDataSave(sheet_key=SHEET, data={"rows": rows}, expected_version=expected_version),
        db=db, user=USER,
    )


@pytest.mark.asyncio
async def test_first_save_returns_content_rows_and_version(db: AsyncSession):
    resp = await _save(db, ROWS)
    assert resp.content == {"rows": ROWS}
    assert resp.version == 0  # 新建后逻辑版本 0
    got = await get_worksheet_data(PID, YEAR, SHEET, db=db, user=USER)
    # 零值、None、formula_detached、手工标记逐字读回，不被真假值判断吞掉
    assert got.content["rows"][0]["unadjusted"] == 0
    assert got.content["rows"][0]["rcl_dr"] == 0
    assert got.content["rows"][0]["rcl_cr"] is None
    assert got.content["rows"][0]["formula_detached"] is True
    assert got.content["rows"][0]["manual_rcl_dr"] is True
    assert got.content["rows"][1]["unadjusted"] == 1234.56


@pytest.mark.asyncio
async def test_cas_update_bumps_version_and_reads_back(db: AsyncSession):
    await _save(db, ROWS)
    updated = [dict(ROWS[0], unadjusted=999), ROWS[1]]
    resp = await _save(db, updated, expected_version=0)
    assert resp.version == 1
    got = await get_worksheet_data(PID, YEAR, SHEET, db=db, user=USER)
    assert got.content["rows"][0]["unadjusted"] == 999
    assert got.version == 1


@pytest.mark.asyncio
async def test_stale_expected_version_conflicts_and_keeps_old_value(db: AsyncSession):
    await _save(db, ROWS)
    await _save(db, [dict(ROWS[0], unadjusted=999), ROWS[1]], expected_version=0)
    with pytest.raises(HTTPException) as exc:
        await _save(db, [dict(ROWS[0], unadjusted=-1), ROWS[1]], expected_version=0)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "worksheet_version_conflict"
    # 冲突后库里仍是上一次成功写入的 999，不被本次拒绝的 -1 污染
    row = (await db.execute(
        sa.select(ConsolWorksheetData).where(ConsolWorksheetData.project_id == PID)
    )).scalar_one()
    assert row.data["rows"][0]["unadjusted"] == 999
    assert row.version == 1


@pytest.mark.asyncio
async def test_missing_sheet_returns_empty_content_not_error(db: AsyncSession):
    got = await get_worksheet_data(PID, YEAR, "never_saved", db=db, user=USER)
    assert got.content == {}
    assert got.version == 0
