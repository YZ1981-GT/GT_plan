"""Draft Refresh 服务层两条路径的计数口径、重算门槛与幂等开关（spec formula-hub-integrity-closure 任务 20 第一段 A-2a；
需求 3.3 / 3.4；ADR-FHIC-08）。全部非 PG：

- ``refresh()``（marker 路径）走 SQLite 内存库，夹具照 ``tests/test_draft_refresh_refresh.py``：只打 Draft 标记 ⇒
  ``draft_marked_count`` = 单元数、``affected_count`` = 0，不触发过时刷新（``working_paper.prefill_stale`` 计数不变），审计
  ``detail`` 记 outcome 与四个计数；零单元调用也写审计；``idempotency_checked`` / ``idempotency_key``；
- ``execute_refresh`` 的会话照 ``tests/formula_runtime/test_refresh_transaction.py`` 用 ``AsyncMock``（``pg_advisory_xact_lock``、
  outbox 的方言分支都离不开 PG），另记 ``add`` 的对象，并让幂等查询（按 ``revision_fingerprint`` 查审计）从已 ``add`` 的审计里
  取 —— 同一会话里第二次调用能看到第一次写的审计；
- ``trigger_recalc`` 用子类记录调用、再照常执行原实现（不替换）。
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy import MetaData
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import AccountCategory, TbAuxBalance, TbBalance, TbLedger, TrialBalance
from app.models.dataset_models import LedgerDataset
from app.models.workpaper_models import (
    DraftMarker,
    DraftRefreshAudit,
    DraftRefreshSnapshot,
    WorkingPaper,
    WpFileStatus,
    WpSourceType,
)
from app.services.draft_refresh_service import DraftRefreshService, RefreshUnit
from app.services.formula_runtime.contracts import AppliedMutation, CanonicalFormulaTarget, FormulaMutation

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
PROJECT_ID = uuid.UUID(int=2001)
YEAR = 2025
_TABLES = [
    TbBalance.__table__, TbLedger.__table__, TbAuxBalance.__table__, TrialBalance.__table__, LedgerDataset.__table__,
    DraftMarker.__table__, DraftRefreshAudit.__table__, DraftRefreshSnapshot.__table__, WorkingPaper.__table__,
]
#: 审计 detail 里供幂等重放的 outcome 与四个计数
OUTCOME_KEYS = ("outcome", "affected_count", "applied_count", "recomputed_count", "draft_marked_count")
#: 假会话里 UPDATE 的 rowcount：trigger_recalc → mark_stale 真执行时 stale_marked_count 取到它
FAKE_ROWCOUNT = 3


class _Operator:
    def __init__(self) -> None:
        self.id = uuid.uuid4()
        self.role = "partner"


class _RecalcSpy(DraftRefreshService):
    """记录 :meth:`trigger_recalc` 的调用，再照常执行原实现（不替换）。"""

    def __init__(self) -> None:
        self.recalc_calls: list[uuid.UUID] = []

    async def trigger_recalc(self, db, *, project_id, account_codes=None):
        self.recalc_calls.append(project_id)
        return await super().trigger_recalc(db, project_id=project_id, account_codes=account_codes)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: MetaData().create_all(sync_conn, tables=_TABLES))
    async with async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: MetaData().drop_all(sync_conn, tables=_TABLES))


async def _seed(db: AsyncSession) -> None:
    """四表库最小种子（precheck 通过）+ 一张持有已落库派生值的底稿（mark_stale 真执行时会被标过时）。"""
    db.add_all([
        TbBalance(project_id=PROJECT_ID, year=YEAR, company_code="C1", account_code="1001", account_name="库存现金",
                  closing_balance=Decimal("100")),
        TrialBalance(project_id=PROJECT_ID, year=YEAR, company_code="C1", standard_account_code="1001",
                     account_name="库存现金", account_category=AccountCategory.asset, unadjusted_amount=Decimal("100")),
        WorkingPaper(project_id=PROJECT_ID, wp_index_id=uuid.uuid4(), file_path="/tmp/wp.xlsx",
                     source_type=WpSourceType.manual, status=WpFileStatus.draft, prefill_stale=False,
                     parsed_data={"html_data": {"rows": []}}),
    ])
    await db.commit()


async def _stale_count(db: AsyncSession) -> int:
    stmt = sa.select(sa.func.count()).select_from(WorkingPaper).where(WorkingPaper.prefill_stale.is_(True))
    return int((await db.execute(stmt)).scalar() or 0)


async def _audits(db: AsyncSession) -> list[DraftRefreshAudit]:
    return list((await db.execute(sa.select(DraftRefreshAudit).order_by(DraftRefreshAudit.operated_at))).scalars())


def _refresh_kwargs(units, **extra):
    return dict(project_id=PROJECT_ID, year=YEAR, operator=_Operator(), scope="report", units=units, **extra)


# ── refresh()：marker 路径 ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_marker_only_refresh_counts_and_no_recalc(db_session: AsyncSession):
    """需求 3.3 / 3.4：只打 Draft 标记 ⇒ draft_marked = 单元数、affected = 0，不调 trigger_recalc、prefill_stale 计数不变。"""
    await _seed(db_session)
    svc = _RecalcSpy()
    result = await svc.refresh(db_session, **_refresh_kwargs([RefreshUnit("report:BS-1"), RefreshUnit("report:BS-2")]))
    await db_session.commit()

    assert (result.status, result.outcome) == ("success", "draft_marked")
    assert (result.draft_marked_count, result.applied_count, result.recomputed_count) == (2, 0, 0)
    assert result.affected_count == 0 and result.to_dict()["affected_count"] == 0
    assert result.stale_marked_count == 0 and svc.recalc_calls == []
    assert await _stale_count(db_session) == 0
    [audit] = await _audits(db_session)
    assert audit.affected_count == 0 and audit.result_status == "success"
    assert {key: audit.detail[key] for key in OUTCOME_KEYS} == {
        "outcome": "draft_marked", "affected_count": 0, "applied_count": 0, "recomputed_count": 0,
        "draft_marked_count": 2,
    }
    assert audit.detail["stale_marked_count"] == 0
    # 观测通道有效：真调一次 trigger_recalc，同一张底稿确实会被标过时（上面的「不变」不是空断言）
    assert await svc.trigger_recalc(db_session, project_id=PROJECT_ID) == 1
    assert await _stale_count(db_session) == 1


@pytest.mark.asyncio
async def test_zero_unit_refresh_writes_one_audit_no_effect(db_session: AsyncSession):
    """仅报表范围时编排器以零单元调用 refresh()：照样写一条审计，outcome = no_effect、计数全 0。"""
    await _seed(db_session)
    svc = _RecalcSpy()
    result = await svc.refresh(db_session, **_refresh_kwargs([]))
    await db_session.commit()

    assert (result.status, result.outcome, result.affected_count, result.draft_marked_count) == ("success", "no_effect", 0, 0)
    [audit] = await _audits(db_session)
    assert audit.id == result.refresh_id
    assert audit.detail["outcome"] == "no_effect" and audit.detail["draft_marked_count"] == 0
    assert svc.recalc_calls == []


@pytest.mark.asyncio
async def test_refresh_idempotency_checked_skips_short_circuit(db_session: AsyncSession):
    """默认照旧命中并回放首次的 outcome 与计数；idempotency_checked=True 时同输入照样执行、写第二条审计与 idempotency_key。"""
    await _seed(db_session)
    svc = DraftRefreshService()
    units = [RefreshUnit("report:BS-1")]
    first = await svc.refresh(db_session, **_refresh_kwargs(units))
    await db_session.commit()
    hit = await svc.refresh(db_session, **_refresh_kwargs(units))
    await db_session.commit()
    assert (hit.status, hit.idempotent, hit.refresh_id) == ("idempotent_hit", True, first.refresh_id)
    assert (hit.outcome, hit.draft_marked_count, hit.affected_count) == ("draft_marked", 1, 0)
    assert first.to_dict()["idempotent"] is False and len(await _audits(db_session)) == 1

    key = "f" * 64
    again = await svc.refresh(db_session, **_refresh_kwargs(units, idempotency_checked=True, idempotency_key=key))
    await db_session.commit()
    assert (again.status, again.idempotent, again.outcome) == ("success", False, "draft_marked")
    audits = await _audits(db_session)
    assert len(audits) == 2 and again.refresh_id == audits[-1].id != first.refresh_id
    assert (audits[0].idempotency_key, audits[-1].idempotency_key) == (None, key)


@pytest.mark.asyncio
async def test_refresh_with_presets_passes_idempotency_arguments(db_session: AsyncSession):
    await _seed(db_session)
    svc = DraftRefreshService()
    kwargs = dict(project_id=PROJECT_ID, year=YEAR, operator=_Operator(), scope="report", page_keys=[],
                  preset_index={}, extra_units=[RefreshUnit("report:BS-1")], idempotency_checked=True,
                  idempotency_key="k" * 64)
    for _ in range(2):
        result, _application = await svc.refresh_with_presets(db_session, **kwargs)
        await db_session.commit()
        assert (result.status, result.outcome) == ("success", "draft_marked")
    audits = await _audits(db_session)
    assert len(audits) == 2 and {a.idempotency_key for a in audits} == {"k" * 64}
    assert all("preset_application" in a.detail for a in audits)


def test_replay_falls_back_to_legacy_counts_when_keys_missing():
    """改造前的审计没有 outcome / 计数键：affected_count 列按旧口径归位，其余取 0、outcome 取 None。"""
    legacy = DraftRefreshAudit(affected_count=3, detail={"refreshed_units": ["a", "b", "c"]})
    zeros = {"applied_count": 0, "recomputed_count": 0, "draft_marked_count": 0}
    assert DraftRefreshService._replayed_outcome(legacy, legacy_field="draft_marked_count") == (
        None, {**zeros, "draft_marked_count": 3})
    assert DraftRefreshService._replayed_outcome(legacy, legacy_field="applied_count") == (
        None, {**zeros, "applied_count": 3})
    fresh = DraftRefreshAudit(affected_count=5, detail={"outcome": "applied", "applied_count": 4, "recomputed_count": 1,
                                                        "draft_marked_count": 2})
    assert DraftRefreshService._replayed_outcome(fresh, legacy_field="applied_count") == (
        "applied", {"applied_count": 4, "recomputed_count": 1, "draft_marked_count": 2})


# ── execute_refresh ────────────────────────────────────────────────────


class _Savepoint:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False  # 不吞异常：失败照常抛给调用方的 except


def _runtime_session() -> AsyncMock:
    """照 test_refresh_transaction.py 的 AsyncMock 会话；另记 add 的对象，幂等查询从已 add 的审计里按指纹取最近一条。"""
    session = AsyncMock()
    session.added = []
    session.add = session.added.append
    session.flush = AsyncMock()
    session.begin_nested = lambda: _Savepoint()

    async def execute(stmt, params=None):
        fingerprint = None
        if isinstance(stmt, sa.Select) and any(d.get("entity") is DraftRefreshAudit for d in stmt.column_descriptions):
            bound = stmt.compile().params
            fingerprint = next((v for k, v in bound.items() if k.startswith("revision_fingerprint")), None)
        hits = [o for o in session.added if isinstance(o, DraftRefreshAudit)
                and fingerprint is not None and o.revision_fingerprint == fingerprint]
        result = MagicMock()
        result.scalars.return_value.first.return_value = hits[-1] if hits else None
        result.scalars.return_value.all.return_value = []
        result.scalar_one_or_none.return_value = None
        result.rowcount = FAKE_ROWCOUNT
        return result

    session.execute = execute
    return session


def _audits_added(session) -> list[DraftRefreshAudit]:
    return [o for o in session.added if isinstance(o, DraftRefreshAudit)]


def _mutation(addr_id: str, domain: str = "workpaper") -> FormulaMutation:
    target = CanonicalFormulaTarget(domain=domain, project_id=PROJECT_ID, year=YEAR, addr_id=addr_id,
                                    locator={"wp_id": str(uuid.UUID(int=7)), "cell": "A1"})
    return FormulaMutation(target=target, before_value=100, after_value=200, expected_version="v1")


class _Adapter:
    """照 test_refresh_transaction.MockAdapter：逐条回 AppliedMutation；``fail=True`` 时 apply_many 抛错。"""

    def __init__(self, domain: str, *, fail: bool = False) -> None:
        self.domain, self.fail, self.applied = domain, fail, []

    async def prepare_many(self, targets, values):
        return []

    async def apply_many(self, mutations):
        if self.fail:
            raise RuntimeError("模拟写入失败")
        self.applied.extend(mutations)
        return [AppliedMutation(target=m.target, applied_version=f"v{i + 2}", applied_at="2025-01-01T00:00:00Z")
                for i, m in enumerate(mutations)]

    async def restore_many(self, snapshots):
        return []

    async def read_versions(self, targets):
        return {}


async def _execute(svc, session, mutations, adapters, **extra):
    return await svc.execute_refresh(session, project_id=PROJECT_ID, year=YEAR, scopes=sorted(adapters) or ["report"],
                                     mutations=mutations, adapters=adapters, **extra)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["all_or_nothing", "partial_success"])
async def test_execute_applied_counts_and_recalc_once(mode):
    """需求 3.3：affected = applied + recomputed（recomputed 由调用方传入）；需求 3.4：金额变化 > 0 ⇒ trigger_recalc 恰一次。"""
    svc, session = _RecalcSpy(), _runtime_session()
    result = await _execute(svc, session, [_mutation("c1"), _mutation("c2")], {"workpaper": _Adapter("workpaper")},
                            transaction_mode=mode, recomputed_count=3)

    assert (result.status, result.outcome) == ("success", "applied")
    assert (result.applied_count, result.recomputed_count, result.draft_marked_count) == (2, 3, 0)
    assert result.to_dict()["affected_count"] == 5
    assert svc.recalc_calls == [PROJECT_ID]
    [audit] = _audits_added(session)
    assert (audit.result_status, audit.affected_count) == ("success", 5)
    assert {key: audit.detail[key] for key in OUTCOME_KEYS} == {
        "outcome": "applied", "affected_count": 5, "applied_count": 2, "recomputed_count": 3, "draft_marked_count": 0,
    }
    assert audit.detail["stale_marked_count"] == FAKE_ROWCOUNT


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["all_or_nothing", "partial_success"])
async def test_execute_preset_markers_only_is_draft_marked_without_recalc(mode):
    """无 runtime mutation、只有预设 Draft 标记：outcome = draft_marked，不触发过时刷新（改造前按 marker_scopes 触发）。"""
    svc, session = _RecalcSpy(), _runtime_session()
    result = await _execute(svc, session, [], {}, transaction_mode=mode,
                            draft_units=[RefreshUnit("workpaper:D1:B2"), RefreshUnit("workpaper:D1:B3")])

    assert (result.status, result.outcome, result.draft_marked_count) == ("draft_marked", "draft_marked", 2)
    assert result.to_dict()["affected_count"] == 0 and svc.recalc_calls == []
    [audit] = _audits_added(session)
    assert (audit.result_status, audit.affected_count, audit.detail["stale_marked_count"]) == ("success", 0, 0)
    assert audit.detail["outcome"] == "draft_marked" and audit.detail["draft_marked_count"] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(("recomputed", "outcome"), [(4, "recomputed"), (0, "no_effect")])
async def test_execute_without_writable_mutation(recomputed, outcome):
    """无可写 mutation：调用方剔除的仅重算 > 0 ⇒ recomputed，三者都为 0 才 no_effect；都不调 trigger_recalc。"""
    svc, session = _RecalcSpy(), _runtime_session()
    result = await _execute(svc, session, [], {}, recomputed_count=recomputed)

    assert (result.status, result.outcome) == (outcome, outcome)
    assert (result.applied_count, result.recomputed_count, result.to_dict()["affected_count"]) == (0, recomputed, recomputed)
    assert svc.recalc_calls == []
    [audit] = _audits_added(session)
    assert (audit.result_status, audit.affected_count, audit.detail["outcome"]) == ("success", recomputed, outcome)
    assert audit.detail["recomputed_count"] == recomputed


@pytest.mark.asyncio
@pytest.mark.parametrize(("good", "recomputed", "applied", "recalc"), [(True, 0, 1, 1), (False, 2, 0, 0)])
async def test_execute_partial_with_failure_and_effective(good, recomputed, applied, recalc):
    """partial_success：有失败且有效 > 0 ⇒ partial（有效可只来自仅重算）；重算门槛按金额变化，不按是否有成功项。"""
    svc, session = _RecalcSpy(), _runtime_session()
    adapters = {"workpaper": _Adapter("workpaper", fail=True), "report": _Adapter("report", fail=not good)}
    result = await _execute(svc, session, [_mutation("w1"), _mutation("r1", "report")], adapters,
                            transaction_mode="partial_success", recomputed_count=recomputed)

    assert (result.status, result.outcome) == ("partial_success", "partial")
    assert (result.applied_count, result.recomputed_count, result.failed_count) == (applied, recomputed, 2 - applied)
    assert result.to_dict()["affected_count"] == applied + recomputed
    assert len(svc.recalc_calls) == recalc
    [audit] = _audits_added(session)
    assert (audit.result_status, audit.detail["outcome"], audit.affected_count) == ("partial_success", "partial",
                                                                                  applied + recomputed)


@pytest.mark.asyncio
async def test_execute_all_or_nothing_failure_counts_zero():
    """all_or_nothing 任一失败 ⇒ failed、整批回滚：三个计数都记 0（传入的 recomputed 不计入），不调 trigger_recalc。"""
    svc, session = _RecalcSpy(), _runtime_session()
    result = await _execute(svc, session, [_mutation("c1")], {"workpaper": _Adapter("workpaper", fail=True)},
                            recomputed_count=2)

    assert (result.status, result.outcome, result.to_dict()["affected_count"]) == ("failed", "failed", 0)
    assert (result.applied_count, result.recomputed_count, result.draft_marked_count) == (0, 0, 0)
    assert svc.recalc_calls == []
    [audit] = _audits_added(session)
    assert (audit.result_status, audit.affected_count, audit.detail["outcome"]) == ("failed", 0, "failed")


@pytest.mark.asyncio
async def test_execute_idempotency_checked_skips_check():
    """默认照旧命中并回放首次的 outcome 与计数（不再写审计）；idempotency_checked=True 时同输入照样执行、写第二条审计。"""
    svc, session = _RecalcSpy(), _runtime_session()
    adapters = {"workpaper": _Adapter("workpaper")}
    first = await _execute(svc, session, [_mutation("c1")], adapters, recomputed_count=1)
    hit = await _execute(svc, session, [_mutation("c1")], adapters, recomputed_count=1)
    assert (hit.status, hit.run_id, hit.outcome) == ("idempotent_hit", first.run_id, "applied")
    assert (hit.applied_count, hit.recomputed_count, hit.to_dict()["affected_count"]) == (1, 1, 2)
    assert len(_audits_added(session)) == 1 and len(adapters["workpaper"].applied) == 1

    again = await _execute(svc, session, [_mutation("c1")], adapters, recomputed_count=1, idempotency_checked=True)
    assert (again.status, again.outcome) == ("success", "applied") and again.run_id != first.run_id
    assert len(_audits_added(session)) == 2 and len(adapters["workpaper"].applied) == 2
    assert len(svc.recalc_calls) == 2
