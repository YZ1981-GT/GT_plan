"""多项目数据集谓词 ``dataset_query.active_rows_predicate``（advanced-query-linkage-closure 任务 3；R1.2；design §3.4、§10.2）。

口径与平台单项目入口 ``get_active_filter`` 逐 (项目, 年度) 相同：有 active 数据集的组合只取按
``activated_at DESC NULLS LAST, created_at DESC`` 最新的一个，没有的组合只按未删。

- SQLite：编译执行不报错；两个 active 数据集取最新、superseded 与软删行不出现、无数据集的项目按未删；
- 真 PG：四表 × 每个活项目年度，两种谓词的行集合逐行相等（同一次扫描里计「只在一边成立」的行数 = 0），
  且多项目一次调用 = 各项目单独口径之和；另把两条分支各钉一个样本 —— 「有非生效数据集 ⇒ 更窄」用真实
  项目（按能力解析），「完全没有数据集 ⇒ 等于只按未删」在回滚事务里自建。

🔴 **2026-11-01 阶段 0 改造**：原先两条分支分别写死 `YB`（宜宾临港店）/ `WL`（和平物流）两个 UUID，
两者现算在 `projects` 里都已查不到行；且共享库现在**没有任何活项目**的审计年度满足「没有 active 数据集」
⇒ 后者改为自建（详见 `closure.md` §16.7）。
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


async def _predicate_count(session, pick) -> int:
    t = TbBalance.__table__
    where = await active_rows_predicate(session, t, project_ids=[pick.id], year=pick.audit_year)
    return (await session.execute(
        sa.select(sa.func.count()).select_from(t)
        .where(t.c.project_id == pick.id, t.c.year == pick.audit_year, where)
    )).scalar_one()


@pytest.mark.pg_only
async def test_pg_narrower_than_undeleted_when_non_active_datasets_exist(pg_rollback_session, gold, picks) -> None:
    """真实项目：该年度有 active 数据集且还有非生效数据集的行 ⇒ 多项目谓词比只按未删更窄。"""
    pick = await picks.resolve("balance_with_narrowing_active_dataset")
    got = await _predicate_count(pg_rollback_session, pick)
    undeleted = await gold.scalar(
        "SELECT count(*) FROM tb_balance WHERE project_id = :pid AND year = :year AND NOT is_deleted",
        pid=pick.id, year=pick.audit_year)
    assert got > 0 and got < undeleted, (pick, got, undeleted)


@pytest.mark.pg_only
async def test_pg_falls_back_to_undeleted_without_any_dataset(pg_rollback_session, no_active_dataset_project) -> None:
    """自建项目：该年度没有任何数据集行 ⇒ 多项目谓词 = 只按未删。

    为什么自建而不从真库里挑：现算共享库里**没有任何活项目**的审计年度是「没有 active 数据集」的
    （见 `closure.md` §16.7）。挑一个「口径恰好相等」的真实项目也能让断言变绿，但走的是
    「所有行都属于生效数据集」那条路，**这条分支会静默失去覆盖**。
    金标准在同一会话上读 —— 自建行还没提交，换连接读到的是 0，断言会以"两边都空"的方式假绿。
    """
    pick = no_active_dataset_project
    got = await _predicate_count(pg_rollback_session, pick)
    undeleted = (await pg_rollback_session.execute(sa.text(
        "SELECT count(*) FROM tb_balance WHERE project_id = :pid AND year = :year AND NOT is_deleted"),
        {"pid": pick.id, "year": pick.audit_year})).scalar_one()
    total = (await pg_rollback_session.execute(sa.text(
        "SELECT count(*) FROM tb_balance WHERE project_id = :pid AND year = :year"),
        {"pid": pick.id, "year": pick.audit_year})).scalar_one()
    assert got == undeleted > 0, (pick, got, undeleted)
    assert undeleted < total, f"自建项目应含软删行（现 {undeleted}/{total}）—— 否则「只按未删」这一半没被走到"
