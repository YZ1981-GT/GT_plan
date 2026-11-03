"""多项目数据集谓词 ``dataset_query.active_rows_predicate``（advanced-query-linkage-closure 任务 3；R1.2；design §3.4、§10.2）。

口径与平台单项目入口 ``get_active_filter`` 逐 (项目, 年度) 相同：有 active 数据集的组合只取按
``activated_at DESC NULLS LAST, created_at DESC`` 最新的一个，没有的组合只按未删。

- SQLite：编译执行不报错；两个 active 数据集取最新、superseded 与软删行不出现、无数据集的项目按未删；
- 真 PG：四表 × 每个活项目年度，两种谓词的行集合逐行相等（同一次扫描里计「只在一边成立」的行数 = 0），
  且多项目一次调用 = 各项目单独口径之和（宜宾临港店有多个数据集、和平物流没有 active 数据集都在其中）。
"""
from __future__ import annotations

import datetime as dt
import uuid

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.audit_platform_models import TbAuxBalance, TbAuxLedger, TbBalance, TbLedger
from app.models.base import ProjectStatus
from app.models.core import Project
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.services.dataset_query import active_rows_predicate, get_active_filter
from tests.advanced_query_linkage.builder_tables import create_tables_with_closure
from tests.advanced_query_linkage.gold import WL, YB

FOUR_TABLES = (TbBalance.__table__, TbLedger.__table__, TbAuxBalance.__table__, TbAuxLedger.__table__)

P1 = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
P2 = uuid.UUID("00000000-0000-0000-0000-0000000000a2")


@pytest_asyncio.fixture
async def sqlite_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(create_tables_with_closure, (TbBalance.__table__, LedgerDataset.__table__, Project.__table__))
    async with AsyncSession(engine, expire_on_commit=False) as session:
        for pid in (P1, P2):
            session.add(Project(id=pid, name=f"【测试】aql 数据集谓词 {pid.hex[-2:]}", client_name="aql",
                                status=ProjectStatus.created))
        t0 = dt.datetime(2026, 1, 1)
        newest = LedgerDataset(project_id=P1, year=2025, status=DatasetStatus.active, activated_at=t0 + dt.timedelta(days=2))
        older = LedgerDataset(project_id=P1, year=2025, status=DatasetStatus.active, activated_at=t0 + dt.timedelta(days=1))
        superseded = LedgerDataset(project_id=P1, year=2025, status=DatasetStatus.superseded, activated_at=t0)
        session.add_all([newest, older, superseded])
        await session.flush()

        def row(pid, code, dataset_id, *, deleted=False):
            return TbBalance(project_id=pid, year=2025, company_code="001", account_code=code,
                             dataset_id=dataset_id, is_deleted=deleted)

        session.add_all([
            row(P1, "1001-new", newest.id), row(P1, "1002-new", newest.id), row(P1, "1003-new-del", newest.id, deleted=True),
            row(P1, "1001-older", older.id), row(P1, "1001-sup", superseded.id),
            row(P2, "1001-none", None), row(P2, "1002-none-del", None, deleted=True),
        ])
        await session.commit()
        yield session
    await engine.dispose()


async def _codes(db: AsyncSession, where) -> set[str]:
    t = TbBalance.__table__
    return set((await db.execute(sa.select(t.c.account_code).where(where))).scalars())


async def test_sqlite_newest_active_dataset_and_no_dataset_project(sqlite_db) -> None:
    t = TbBalance.__table__
    multi = await active_rows_predicate(sqlite_db, t, project_ids=[P1, P2], year=2025)
    scoped = sa.and_(t.c.project_id.in_([P1, P2]), t.c.year == 2025, multi)
    assert await _codes(sqlite_db, scoped) == {"1001-new", "1002-new", "1001-none"}
    single = set()
    for pid in (P1, P2):
        single |= await _codes(sqlite_db, await get_active_filter(sqlite_db, t, pid, 2025, strict=True))
    assert single == {"1001-new", "1002-new", "1001-none"}, "与平台单项目口径逐项目相同"
    unbounded = await active_rows_predicate(sqlite_db, t, project_ids=None, year=None)
    assert await _codes(sqlite_db, unbounded) == {"1001-new", "1002-new", "1001-none"}, "不限项目 / 年度时同口径"
    empty = await active_rows_predicate(sqlite_db, t, project_ids=[], year=2025)
    assert "1001-sup" in await _codes(sqlite_db, empty), "空项目集合只给未删谓词（项目范围由调用方的作用域谓词约束）"


async def test_dataset_lookup_failure_propagates(sqlite_db, monkeypatch) -> None:
    async def boom(*_a, **_kw):
        raise RuntimeError("ledger_datasets 查询失败")

    monkeypatch.setattr(sqlite_db, "execute", boom)
    with pytest.raises(RuntimeError, match="ledger_datasets"):
        await active_rows_predicate(sqlite_db, TbBalance.__table__, project_ids=[P1], year=2025)


# ─── 真 PG ───────────────────────────────────────────────────────────────────


async def _live_pairs(db: AsyncSession, table: sa.Table) -> list[tuple[uuid.UUID, int]]:
    live = sa.select(Project.id).where(Project.is_deleted.is_(False))
    stmt = (sa.select(table.c.project_id, table.c.year).where(table.c.project_id.in_(live))
            .group_by(table.c.project_id, table.c.year).order_by(table.c.project_id, table.c.year))
    return [(pid, year) for pid, year in (await db.execute(stmt)).all()]


def _definite(predicate):
    return sa.func.coalesce(predicate, sa.false())


@pytest.mark.pg_only
@pytest.mark.parametrize("table", FOUR_TABLES, ids=[t.name for t in FOUR_TABLES])
async def test_pg_equivalent_to_get_active_filter(pg_rollback_session, table: sa.Table) -> None:
    db = pg_rollback_session
    pairs = await _live_pairs(db, table)
    assert pairs, f"{table.name} 没有活项目的数据，这条用例证明不了口径"
    total_single = 0
    for pid, year in pairs:
        a = await active_rows_predicate(db, table, project_ids=[pid], year=year)
        b = await get_active_filter(db, table, pid, year, strict=True)
        in_a, in_b, differ = (await db.execute(
            sa.select(
                sa.func.count().filter(_definite(a)),
                sa.func.count().filter(_definite(b)),
                sa.func.count().filter(_definite(a) != _definite(b)),
            ).where(table.c.project_id == pid, table.c.year == year)
        )).one()
        assert differ == 0 and in_a == in_b, f"{table.name} {pid} {year}：两种口径行集合不同（{in_a} / {in_b}，差 {differ}）"
        total_single += in_b
    pids = sorted({pid for pid, _ in pairs})
    multi = await active_rows_predicate(db, table, project_ids=pids, year=None)
    in_multi = (await db.execute(
        sa.select(sa.func.count()).select_from(table).where(table.c.project_id.in_(pids), multi)
    )).scalar_one()
    assert in_multi == total_single, f"{table.name}：多项目一次调用 {in_multi} ≠ 各项目单独口径之和 {total_single}"


@pytest.mark.pg_only
async def test_pg_covers_multi_dataset_and_no_dataset_projects(pg_rollback_session, gold) -> None:
    """宜宾临港店有非生效数据集的行（口径比只按未删更窄）、和平物流没有 active 数据集（口径 = 只按未删）。"""
    t = TbBalance.__table__
    for pid, narrower in ((YB, True), (WL, False)):
        where = await active_rows_predicate(pg_rollback_session, t, project_ids=[pid], year=2025)
        got = (await pg_rollback_session.execute(
            sa.select(sa.func.count()).select_from(t).where(t.c.project_id == pid, t.c.year == 2025, where)
        )).scalar_one()
        undeleted = await gold.scalar(
            "SELECT count(*) FROM tb_balance WHERE project_id = :pid AND year = 2025 AND NOT is_deleted", pid=pid)
        assert got > 0 and ((got < undeleted) if narrower else (got == undeleted)), (pid, got, undeleted)
