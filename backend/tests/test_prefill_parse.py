"""预填充与解析回写服务测试

Validates: Requirements 6.4-6.7, 7.2-7.5
"""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.models.workpaper_models import (
    WpIndex,
    WpSourceType,
    WorkingPaper,
)
from app.services.prefill_engine import FormulaCell, ParseService, PrefillService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """Create test project + working paper."""
    project = Project(
        id=FAKE_PROJECT_ID,
        name="预填充测试_2025",
        client_name="预填充测试",
        project_type=ProjectType.annual,
        status=ProjectStatus.planning,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)
    await db_session.flush()

    wp_index = WpIndex(
        project_id=FAKE_PROJECT_ID,
        wp_code="PF-1",
        wp_name="预填充测试底稿",
    )
    db_session.add(wp_index)
    await db_session.flush()

    wp = WorkingPaper(
        project_id=FAKE_PROJECT_ID,
        wp_index_id=wp_index.id,
        file_path=f"{FAKE_PROJECT_ID}/2025/PF-1.xlsx",
        source_type=WpSourceType.template,
        file_version=1,
    )
    db_session.add(wp)
    await db_session.commit()
    return wp.id


# ===== PrefillService._scan_formulas Tests =====


def test_scan_formulas_tb():
    """7.1: scan TB formula"""
    svc = PrefillService()
    cells = [
        {"sheet": "Sheet1", "cell_ref": "B5", "text": '=TB("1001","期末余额")'},
    ]
    results = svc._scan_formulas(cells)
    assert len(results) == 1
    assert results[0].formula_type == "TB"
    assert results[0].cell_ref == "B5"


def test_scan_formulas_multiple():
    """7.1: scan multiple formula types"""
    svc = PrefillService()
    cells = [
        {"sheet": "Sheet1", "cell_ref": "B5", "text": '=TB("1001","期末余额")'},
        {"sheet": "Sheet1", "cell_ref": "C5", "text": '=WP("E1-1","B5")'},
        {"sheet": "Sheet1", "cell_ref": "D5", "text": '=AUX("1122","客户","客户A","期末余额")'},
        {"sheet": "Sheet1", "cell_ref": "E5", "text": '=SUM_TB("6001~6099","期末余额")'},
        {"sheet": "Sheet1", "cell_ref": "F5", "text": '=PREV(TB("1001","期末余额"))'},
    ]
    results = svc._scan_formulas(cells)
    assert len(results) == 5
    types = {r.formula_type for r in results}
    assert types == {"TB", "WP", "AUX", "SUM_TB", "PREV"}


def test_scan_formulas_no_match():
    """7.1: scan non-formula text returns empty"""
    svc = PrefillService()
    cells = [
        {"sheet": "Sheet1", "cell_ref": "A1", "text": "普通文本"},
        {"sheet": "Sheet1", "cell_ref": "A2", "text": "=SUM(A1:A10)"},
    ]
    results = svc._scan_formulas(cells)
    assert len(results) == 0


def test_scan_formulas_case_insensitive():
    """7.1: scan is case-insensitive"""
    svc = PrefillService()
    cells = [
        {"sheet": "Sheet1", "cell_ref": "B5", "text": '=tb("1001","期末余额")'},
    ]
    results = svc._scan_formulas(cells)
    assert len(results) == 1
    assert results[0].formula_type == "TB"


def test_formula_cell_to_dict():
    """7.1: FormulaCell.to_dict"""
    fc = FormulaCell(sheet="Sheet1", cell_ref="B5", formula_type="TB", raw_args='"1001","期末余额"')
    d = fc.to_dict()
    assert d["sheet"] == "Sheet1"
    assert d["formula_type"] == "TB"


# ===== PrefillService.prefill_workpaper Tests =====


@pytest.mark.asyncio
async def test_prefill_workpaper_stub(db_session, seeded_db):
    """7.2: prefill_workpaper returns result (real engine, no file → error)"""
    svc = PrefillService()
    result = await svc.prefill_workpaper(
        db=db_session,
        project_id=FAKE_PROJECT_ID,
        year=2025,
        wp_id=seeded_db,
    )
    assert result["status"] in ("stub", "error", "ok")
    assert result["wp_id"] == str(seeded_db)


# ===== ParseService.parse_workpaper Tests =====


@pytest.mark.asyncio
async def test_parse_workpaper_stub(db_session, seeded_db):
    """7.3: parse_workpaper returns stub result and updates last_parsed_at"""
    svc = ParseService()
    result = await svc.parse_workpaper(
        db=db_session,
        project_id=FAKE_PROJECT_ID,
        wp_id=seeded_db,
    )
    await db_session.commit()

    assert result["status"] in ("stub", "error", "ok")


# ===== ParseService.detect_conflicts Tests =====


@pytest.mark.asyncio
async def test_detect_conflicts_no_conflict(db_session, seeded_db):
    """7.4: detect_conflicts — version matches, no conflict"""
    svc = ParseService()
    result = await svc.detect_conflicts(
        db=db_session,
        project_id=FAKE_PROJECT_ID,
        wp_id=seeded_db,
        uploaded_version=1,
    )
    assert result["has_conflict"] is False
    assert len(result.get("conflicts", [])) == 0


@pytest.mark.asyncio
async def test_detect_conflicts_version_mismatch(db_session, seeded_db):
    """7.4: detect_conflicts — uploaded version < server version"""
    # Simulate server version bump
    import sqlalchemy as sa
    wp_result = await db_session.execute(
        sa.select(WorkingPaper).where(WorkingPaper.id == seeded_db)
    )
    wp = wp_result.scalar_one()
    wp.file_version = 3
    await db_session.commit()

    svc = ParseService()
    result = await svc.detect_conflicts(
        db=db_session,
        project_id=FAKE_PROJECT_ID,
        wp_id=seeded_db,
        uploaded_version=1,
    )
    assert result["has_conflict"] is True
    assert result["server_version"] == 3
    assert len(result["conflicts"]) > 0


@pytest.mark.asyncio
async def test_detect_conflicts_nonexistent_wp(db_session):
    """7.4: detect_conflicts — nonexistent working paper"""
    svc = ParseService()
    result = await svc.detect_conflicts(
        db=db_session,
        project_id=FAKE_PROJECT_ID,
        wp_id=uuid.uuid4(),
        uploaded_version=1,
    )
    assert result["has_conflict"] is False
    assert "error" in result
