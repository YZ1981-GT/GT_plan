"""ClientQualityTrendService 单元测试

Validates: Requirements 7 (Round 3)
- 按 client_name 精确匹配聚合近 N 年评级/错报/重要性
- 缺失年份返回空槽 {year: YYYY, data: null} 不报错
- 多项目同客户聚合
- 无项目时全部返回空槽
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text as sa_text
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.qc_rating_models import ProjectQualityRating

# Import models so they're registered with Base.metadata
import app.models.core  # noqa: F401
import app.models.audit_platform_models  # noqa: F401
import app.models.phase15_models  # noqa: F401

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每个测试独立的内存数据库会话。"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CLIENT_NAME = "ABC审计客户"
CURRENT_YEAR = datetime.now(timezone.utc).year


async def _seed_project(
    db: AsyncSession,
    project_id: uuid.UUID | None = None,
    client_name: str = CLIENT_NAME,
    audit_period_end: date | None = None,
    materiality_level: float | None = None,
) -> uuid.UUID:
    """插入测试项目。"""
    pid = project_id or uuid.uuid4()
    ape = audit_period_end or date(CURRENT_YEAR, 12, 31)
    await db.execute(
        sa_text(
            "INSERT INTO projects "
            "(id, name, client_name, is_deleted, status, version, consol_level, "
            "audit_period_end, materiality_level) "
            "VALUES (:id, :name, :client_name, 0, 'created', 1, 1, :ape, :mat)"
        ),
        {
            "id": str(pid),
            "name": f"项目-{str(pid)[:8]}",
            "client_name": client_name,
            "ape": ape.isoformat(),
            "mat": materiality_level,
        },
    )
    await db.flush()
    return pid


async def _seed_rating(
    db: AsyncSession,
    project_id: uuid.UUID,
    year: int,
    rating: str = "B",
    score: int = 78,
):
    """插入评级记录。"""
    rid = uuid.uuid4()
    await db.execute(
        sa_text(
            "INSERT INTO project_quality_ratings "
            "(id, project_id, year, rating, score, computed_at, computed_by_rule_version) "
            "VALUES (:id, :pid, :year, :rating, :score, :computed_at, 1)"
        ),
        {
            "id": str(rid),
            "pid": str(project_id),
            "year": year,
            "rating": rating,
            "score": score,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    await db.flush()


async def _seed_issue(
    db: AsyncSession,
    project_id: uuid.UUID,
    created_at: datetime | None = None,
):
    """插入问题单。"""
    iid = uuid.uuid4()
    ts = created_at or datetime.now(timezone.utc)
    await db.execute(
        sa_text(
            "INSERT INTO issue_tickets "
            "(id, project_id, source, severity, category, title, owner_id, "
            "status, trace_id, created_at, updated_at) "
            "VALUES (:id, :pid, 'Q', 'major', 'data_mismatch', '测试问题', "
            ":owner, 'open', :trace, :ts, :ts)"
        ),
        {
            "id": str(iid),
            "pid": str(project_id),
            "owner": str(uuid.uuid4()),
            "trace": str(uuid.uuid4())[:64],
            "ts": ts.isoformat(),
        },
    )
    await db.flush()


async def _seed_misstatement(
    db: AsyncSession,
    project_id: uuid.UUID,
    year: int,
    amount: float = 10000.0,
):
    """插入错报记录。"""
    mid = uuid.uuid4()
    await db.execute(
        sa_text(
            "INSERT INTO unadjusted_misstatements "
            "(id, project_id, year, misstatement_description, "
            "misstatement_amount, misstatement_type, is_deleted, "
            "is_carried_forward, created_at, updated_at) "
            "VALUES (:id, :pid, :year, '测试错报', :amount, 'factual', "
            "0, 0, :ts, :ts)"
        ),
        {
            "id": str(mid),
            "pid": str(project_id),
            "year": year,
            "amount": amount,
            "ts": datetime.now(timezone.utc).isoformat(),
        },
    )
    await db.flush()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_projects_returns_empty_slots(db_session: AsyncSession):
    """无项目时所有年份返回空槽。"""
    from app.services.client_quality_trend_service import client_quality_trend_service

    result = await client_quality_trend_service.get_quality_trend(
        db_session, client_name="不存在的客户", years=3
    )

    assert result["client_name"] == "不存在的客户"
    assert result["years_requested"] == 3
    assert len(result["trend"]) == 3
    for slot in result["trend"]:
        assert slot["data"] is None
        assert "year" in slot


@pytest.mark.asyncio
async def test_missing_years_return_null_data(db_session: AsyncSession):
    """缺失年份返回 data=null 不报错。"""
    from app.services.client_quality_trend_service import client_quality_trend_service

    # 只在当前年有项目和评级
    pid = await _seed_project(db_session, client_name=CLIENT_NAME)
    await _seed_rating(db_session, pid, CURRENT_YEAR, "A", 92)
    await db_session.commit()

    result = await client_quality_trend_service.get_quality_trend(
        db_session, client_name=CLIENT_NAME, years=3
    )

    assert len(result["trend"]) == 3
    # 当前年有数据
    current_slot = next(s for s in result["trend"] if s["year"] == CURRENT_YEAR)
    assert current_slot["data"] is not None
    assert current_slot["data"]["rating"] == "A"

    # 前两年无数据
    for slot in result["trend"]:
        if slot["year"] != CURRENT_YEAR:
            assert slot["data"] is None


@pytest.mark.asyncio
async def test_aggregates_ratings_issues_misstatements(db_session: AsyncSession):
    """聚合评级、问题数、错报金额。"""
    from app.services.client_quality_trend_service import client_quality_trend_service

    pid = await _seed_project(
        db_session,
        client_name=CLIENT_NAME,
        audit_period_end=date(CURRENT_YEAR, 12, 31),
        materiality_level=500000.0,
    )
    await _seed_rating(db_session, pid, CURRENT_YEAR, "B", 78)
    # 3 个问题
    for _ in range(3):
        await _seed_issue(
            db_session, pid, datetime(CURRENT_YEAR, 6, 15, tzinfo=timezone.utc)
        )
    # 2 笔错报
    await _seed_misstatement(db_session, pid, CURRENT_YEAR, 10000.0)
    await _seed_misstatement(db_session, pid, CURRENT_YEAR, 5000.0)
    await db_session.commit()

    result = await client_quality_trend_service.get_quality_trend(
        db_session, client_name=CLIENT_NAME, years=1
    )

    assert len(result["trend"]) == 1
    data = result["trend"][0]["data"]
    assert data is not None
    assert data["rating"] == "B"
    assert data["score"] == 78.0
    assert data["issue_count"] == 3
    assert data["misstatement_amount"] == 15000.0
    assert data["materiality_level"] == 500000.0


@pytest.mark.asyncio
async def test_multiple_projects_same_client(db_session: AsyncSession):
    """同一客户多个项目聚合。"""
    from app.services.client_quality_trend_service import client_quality_trend_service

    pid1 = await _seed_project(
        db_session,
        client_name=CLIENT_NAME,
        audit_period_end=date(CURRENT_YEAR, 12, 31),
        materiality_level=300000.0,
    )
    pid2 = await _seed_project(
        db_session,
        client_name=CLIENT_NAME,
        audit_period_end=date(CURRENT_YEAR, 12, 31),
        materiality_level=500000.0,
    )
    # 两个项目各有评级
    await _seed_rating(db_session, pid1, CURRENT_YEAR, "B", 80)
    await _seed_rating(db_session, pid2, CURRENT_YEAR, "C", 65)
    # 各有问题
    await _seed_issue(
        db_session, pid1, datetime(CURRENT_YEAR, 3, 1, tzinfo=timezone.utc)
    )
    await _seed_issue(
        db_session, pid2, datetime(CURRENT_YEAR, 4, 1, tzinfo=timezone.utc)
    )
    await db_session.commit()

    result = await client_quality_trend_service.get_quality_trend(
        db_session, client_name=CLIENT_NAME, years=1
    )

    data = result["trend"][0]["data"]
    assert data is not None
    # 最差评级 C > B
    assert data["rating"] == "C"
    # 平均分
    assert data["score"] == 72.5
    # 问题数合计
    assert data["issue_count"] == 2
    # 项目数
    assert data["project_count"] == 2
    # 重要性取最大
    assert data["materiality_level"] == 500000.0


@pytest.mark.asyncio
async def test_exact_client_name_match(db_session: AsyncSession):
    """精确匹配 client_name，不模糊。"""
    from app.services.client_quality_trend_service import client_quality_trend_service

    await _seed_project(db_session, client_name="ABC公司")
    await _seed_project(db_session, client_name="ABC公司有限")
    await db_session.commit()

    result = await client_quality_trend_service.get_quality_trend(
        db_session, client_name="ABC公司", years=1
    )
    # 只匹配 "ABC公司"，不匹配 "ABC公司有限"
    assert result["client_name"] == "ABC公司"


@pytest.mark.asyncio
async def test_years_parameter_controls_range(db_session: AsyncSession):
    """years 参数控制返回年份范围。"""
    from app.services.client_quality_trend_service import client_quality_trend_service

    result = await client_quality_trend_service.get_quality_trend(
        db_session, client_name="任意客户", years=5
    )

    assert result["years_requested"] == 5
    assert len(result["trend"]) == 5
    # 年份从 current_year-4 到 current_year
    years_in_result = [s["year"] for s in result["trend"]]
    expected_years = list(range(CURRENT_YEAR - 4, CURRENT_YEAR + 1))
    assert years_in_result == expected_years
