"""Draft Refresh 幂等判定接线（spec formula-hub-integrity-closure 任务 20 第一段 A-2c-2；ADR-FHIC-08「幂等」）。

非 PG：SQLite 内存库，建表与种子照 ``tests/formula_management/test_draft_refresh_orchestrator.py``，建表后手工补迁移里有、
ORM 没声明的部分唯一索引 ``(project_id, year, idempotency_key) WHERE idempotency_key IS NOT NULL``。

- 编排器：经 ``DraftRefreshOrchestrator.generate`` 真跑，只把 ``_dispatch`` 换成受控生成器（勾选 note / adjudication /
  workpaper:D 这些 marker 路径范围），判定与取数都走生产代码：①同一请求两次 ⇒ 第二次命中（run_id / outcome / 计数 =
  首次，审计与 Draft 标记不增，预设套用回放首次存的），scopes 换序 / 重复也命中；②改覆盖确认 / 事务模式 ⇒ 执行；
  ③首次运行仍在执行 ⇒ ``RefreshInProgress``、什么都没写；④首次 partial ⇒ 重新执行，写入键 ≠ 有效键、不撞唯一索引，
  再来一次 partial 后写入键与已有各条都不同；⑤显式请求键两次 ⇒ 命中（计划不同也命中）；⑥``rolled_back`` ⇒ 执行；
  ⑦审计 ``detail`` 增写有效键与计划指纹；⑧``find_records`` 按列与按 ``detail.idempotency_base`` 两种来源都找得到。
- ``runtime_revisions``：与编排器原内联算法逐字一致（JSON 写法钉在字面串上）。
- ``report_basis``：另建 ``projects`` / ``trial_balance`` / ``financial_report`` / ``report_config``（``projects`` 是
  ``load_effective_formulas`` 经 ``resolve_applicable_standard`` 读项目准则所需）：改审定数 / 改报表公式 / 标过期 ⇒
  对应哈希或计数变，与行序无关，删除行 / 他年度行不计入。
- 路由：直调 ``one_click_draft_refresh``（照 ``tests/formula_management/test_draft_refresh_endpoint.py``）：``generate`` 抛
  ``RefreshInProgress`` ⇒ ``HTTPException`` 409、``detail == to_detail()``、未 commit；命中时预设套用是 dict 也进响应。
"""
from __future__ import annotations

import asyncio
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import MetaData
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

import sqlalchemy as sa  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

import app.routers.draft_refresh as endpoint  # noqa: E402
from app.models.audit_platform_models import (  # noqa: E402
    AccountCategory,
    TbAuxBalance,
    TbBalance,
    TbLedger,
    TrialBalance,
)
from app.models.core import Project  # noqa: E402
from app.models.dataset_models import LedgerDataset  # noqa: E402
from app.models.report_models import FinancialReport, FinancialReportType, ReportConfig  # noqa: E402
from app.models.workpaper_models import (  # noqa: E402
    DraftMarker,
    DraftRefreshAudit,
    DraftRefreshSnapshot,
    WpIndex,
)
from app.schemas.formula_runtime import DraftRefreshRequest  # noqa: E402
from app.services.draft_refresh_service import RefreshUnit  # noqa: E402
from app.services.formula_management.draft_refresh_orchestrator import DraftRefreshOrchestrator  # noqa: E402
from app.services.formula_management.refresh_idempotency import (  # noqa: E402
    DETAIL_BASE_KEY,
    DETAIL_FP_KEY,
    RefreshInProgress,
    hit_preset_application,
    hit_result,
    latest,
    rows_hash,
    runtime_revisions,
    write_key,
)
from app.services.formula_management.refresh_idempotency_store import (  # noqa: E402
    count_occupied,
    find_prior,
    find_records,
    report_basis,
)
from app.services.report_freshness import CALC_VERSION  # noqa: E402

# 固定且带字母：SQLite 的 UUID 列是 NUMERIC 亲和，全数字的十六进制串会被存成数值（夹具假象）
PROJECT_ID = uuid.UUID("a2c2a2c2-0000-4000-8000-000000000001")
YEAR = 2025
PENDING_PAGE = "note:__fh_idem_pending__"
UNITS = {
    "note": ["note:N1!0:1", "note:N1!0:2", "note:N2!1:1"],
    "adjudication": ["audit_sheet:X:1", "audit_sheet:X:2"],
    "workpaper:D": ["workpaper:D:u0"],
}
DEFAULT_SCOPES = ["note", "adjudication"]
_TABLES = [
    TbBalance.__table__, TbLedger.__table__, TbAuxBalance.__table__, TrialBalance.__table__, LedgerDataset.__table__,
    DraftMarker.__table__, DraftRefreshAudit.__table__, DraftRefreshSnapshot.__table__, WpIndex.__table__,
]
#: 迁移建、ORM 未声明的部分唯一索引（快照库现读，logs/task20a2c_index_probe.log）
_UNIQUE_KEY_INDEX = (
    "CREATE UNIQUE INDEX uq_audit_project_year_idempotency ON draft_refresh_audit "
    "(project_id, year, idempotency_key) WHERE idempotency_key IS NOT NULL"
)
OPERATOR = SimpleNamespace(id=uuid.UUID("a2c2a2c2-0000-4000-8000-000000000002"), role="partner")


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _session(tables, *extra_ddl: str):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: MetaData().create_all(sync_conn, tables=tables))
        for ddl in extra_ddl:
            await conn.execute(sa.text(ddl))
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False), engine


def _scenario(body):
    """建编排器夹具（四表核心两表过 precheck + 唯一索引）后跑 ``body(db)``。"""
    async def _main():
        factory, engine = await _session(_TABLES, _UNIQUE_KEY_INDEX)
        try:
            async with factory() as db:
                for code, amount in (("1001", 1000), ("2001", 500)):
                    db.add(TbBalance(project_id=PROJECT_ID, year=YEAR, company_code="C1", account_code=code,
                                     account_name=f"科目{code}", closing_balance=Decimal(amount)))
                    db.add(TrialBalance(project_id=PROJECT_ID, year=YEAR, company_code="C1",
                                        standard_account_code=code, account_name=f"科目{code}",
                                        account_category=AccountCategory.asset, unadjusted_amount=Decimal(amount)))
                await db.commit()
                await body(db)
        finally:
            await engine.dispose()
    _run(_main())


async def _fake_dispatch(scope, *, project_id, year):
    """受控生成器：按 ``UNITS`` 产 Draft 单元；note 另给一个没有预设的页面（预设套用里记为 pending）。"""
    return [RefreshUnit(unit_scope=us) for us in UNITS.get(scope, [])], ([PENDING_PAGE] if scope == "note" else [])


async def _generate(db, *, scopes=DEFAULT_SCOPES, **kwargs):
    orchestrator = DraftRefreshOrchestrator(db)
    orchestrator._dispatch = _fake_dispatch
    result, application = await orchestrator.generate(
        project_id=PROJECT_ID, year=YEAR, operator=OPERATOR, scopes=list(scopes), **kwargs)
    await db.commit()  # 路由在 outcome != failed 时 commit
    return result, application


def _audit_row(key, *, status="success", detail=None, at=None, year=YEAR):
    return DraftRefreshAudit(
        project_id=PROJECT_ID, year=year, operator_id=OPERATOR.id, operator_role="partner",
        operated_at=at or datetime.now(timezone.utc) - timedelta(hours=1), scope="adjudication,note",
        tb_snapshot_hash="0" * 64, affected_count=0, result_status=status,
        detail={} if detail is None else detail, transaction_mode="all_or_nothing", idempotency_key=key,
    )


async def _count(db, model) -> int:
    return int((await db.execute(sa.select(sa.func.count()).select_from(model))).scalar_one())


async def _audit(db, audit_id) -> DraftRefreshAudit:
    return (await db.execute(sa.select(DraftRefreshAudit).where(DraftRefreshAudit.id == audit_id))).scalar_one()


async def _marker_runs(db) -> set:
    return set((await db.execute(sa.select(DraftMarker.refresh_id))).scalars().all())


# ── ① ⑦ 同一请求两次 ⇒ 命中 ───────────────────────────────────────────────────────────────────────────
def test_same_request_twice_hits_first_run_without_writing():
    async def body(db):
        first, first_app = await _generate(db)
        assert (first.status, first.outcome, first.draft_marked_count) == ("draft_marked", "draft_marked", 5)
        second, second_app = await _generate(db)

        assert second.status == "idempotent_hit" and second.to_dict()["idempotent"] is True
        assert second.run_id == first.refresh_id
        assert (second.outcome, second.applied_count, second.recomputed_count, second.draft_marked_count) == (
            first.outcome, first.applied_count, first.recomputed_count, first.draft_marked_count)
        assert (second.failures, second.post_commit_events, second.rollback_available) == ([], [], True)
        # 没有写入：审计仍 1 条；Draft 标记仍 5 个且都还挂在首次运行上（再执行会改挂到新运行）
        assert (await _count(db, DraftRefreshAudit), await _count(db, DraftMarker)) == (1, 5)
        assert await _marker_runs(db) == {first.refresh_id}
        # 预设套用回放首次运行存的（判据不空转：确有 pending 页面）
        assert second_app == first_app.to_dict() and second_app["pending_pages"] == [PENDING_PAGE]
        # ⑦ detail 增写有效键与计划指纹；无请求键 ⇒ 有效键 = plan_fp = 列值（首次 occupied = 0）
        audit = await _audit(db, first.refresh_id)
        assert audit.detail[DETAIL_BASE_KEY] == audit.detail[DETAIL_FP_KEY] == audit.idempotency_key
        assert len(audit.idempotency_key) == 64 and audit.detail["outcome"] == "draft_marked"

    _scenario(body)


@settings(max_examples=5, deadline=None)
@given(
    chosen=st.lists(st.sampled_from(sorted(UNITS)), min_size=1, max_size=3, unique=True),
    data=st.data(),
    confirm_overwrite=st.booleans(),
    transaction_mode=st.sampled_from(["all_or_nothing", "partial_success"]),
)
def test_same_plan_hits_whatever_scope_order(chosen, data, confirm_overwrite, transaction_mode):
    """计划指纹按排序去重的 scopes 算：第二次请求把 scopes 换序、加重复项，仍命中首次运行。"""
    again = data.draw(st.permutations(chosen)) + data.draw(st.lists(st.sampled_from(chosen), max_size=2))
    mode = {"confirm_overwrite": confirm_overwrite, "transaction_mode": transaction_mode}

    async def body(db):
        first, _ = await _generate(db, scopes=chosen, **mode)
        second, _ = await _generate(db, scopes=again, **mode)
        assert first.status == "draft_marked", first
        assert (second.status, second.run_id) == ("idempotent_hit", first.refresh_id)
        assert await _count(db, DraftRefreshAudit) == 1

    _scenario(body)


# ── ② 改覆盖确认 / 事务模式 ⇒ 执行 ─────────────────────────────────────────────────────────────────────
def test_changed_overwrite_or_transaction_mode_executes():
    async def body(db):
        first, _ = await _generate(db)
        by_overwrite, _ = await _generate(db, confirm_overwrite=True)
        by_mode, _ = await _generate(db, transaction_mode="partial_success")
        runs = [first.refresh_id, by_overwrite.refresh_id, by_mode.refresh_id]
        assert [r.status for r in (first, by_overwrite, by_mode)] == ["draft_marked"] * 3
        assert len(set(runs)) == 3 and await _count(db, DraftRefreshAudit) == 3
        keys = [(await _audit(db, run)).idempotency_key for run in runs]
        assert len(set(keys)) == 3  # 三个不同的计划指纹，各自首次占用 ⇒ 写入键 = 有效键

    _scenario(body)


# ── ③ 首次运行仍在执行 ⇒ RefreshInProgress ─────────────────────────────────────────────────────────────
def test_first_run_still_executing_raises_in_progress():
    async def body(db):
        busy = _audit_row("k-busy", status="executing")
        db.add(busy)
        await db.commit()
        busy_id = busy.id  # rollback 会让实例过期，之后再读属性要走 IO
        with pytest.raises(RefreshInProgress) as raised:
            await _generate(db, idempotency_key="k-busy")
        await db.rollback()
        assert raised.value.run_id == str(busy_id)
        assert raised.value.to_detail()["error_code"] == "DRAFT_REFRESH_IN_PROGRESS"
        assert (await _count(db, DraftRefreshAudit), await _count(db, DraftMarker)) == (1, 0)

    _scenario(body)


# ── ④ 首次 partial ⇒ 重新执行；写入键不撞唯一索引、连续重做各不相同 ────────────────────────────────────────
def test_partial_prior_reexecutes_with_fresh_write_keys():
    async def body(db):
        key = "k-partial"
        db.add(_audit_row(key, detail={"outcome": "partial"}))
        await db.commit()
        second, _ = await _generate(db, idempotency_key=key)
        assert second.status == "draft_marked"
        rerun = await _audit(db, second.refresh_id)
        assert rerun.idempotency_key == write_key(key, 1) != key and rerun.detail[DETAIL_BASE_KEY] == key
        # 再来一条更晚的 partial（列值 = 第 2 次占用的写入键）⇒ 第三次执行：已占用 3 条（列 1 + detail 2）
        db.add(_audit_row(write_key(key, 2), detail={"outcome": "partial", DETAIL_BASE_KEY: key},
                          at=rerun.operated_at + timedelta(seconds=1)))
        await db.commit()
        third, _ = await _generate(db, idempotency_key=key)
        assert third.status == "draft_marked"
        keys = [row.idempotency_key for row in await find_records(db, PROJECT_ID, YEAR, key)]
        assert (await _audit(db, third.refresh_id)).idempotency_key == write_key(key, 3)
        assert len(keys) == len(set(keys)) == 4 and key in keys
        # 判据不空转：唯一索引确实生效（同一写入键再插一条即违反）
        db.add(_audit_row(write_key(key, 3)))
        with pytest.raises(IntegrityError):
            await db.flush()
        await db.rollback()

    _scenario(body)


# ── ⑤ 显式请求键 ⇒ 同键命中（计划不同也命中） ⑦ ────────────────────────────────────────────────────────────
def test_explicit_request_key_hits_even_if_plan_differs():
    async def body(db):
        first, _ = await _generate(db, idempotency_key="k-explicit")
        second, _ = await _generate(db, idempotency_key="  k-explicit  ", confirm_overwrite=True)
        assert (second.status, second.run_id) == ("idempotent_hit", first.refresh_id)
        audit = await _audit(db, first.refresh_id)
        assert audit.idempotency_key == audit.detail[DETAIL_BASE_KEY] == "k-explicit"
        assert len(audit.detail[DETAIL_FP_KEY]) == 64 and await _count(db, DraftRefreshAudit) == 1

    _scenario(body)


# ── ⑥ rolled_back ⇒ 执行 ────────────────────────────────────────────────────────────────────────────
def test_rolled_back_prior_executes():
    async def body(db):
        db.add(_audit_row("k-rb", status="rolled_back", detail={"outcome": "draft_marked"}))
        await db.commit()
        result, _ = await _generate(db, idempotency_key="k-rb")
        assert result.status == "draft_marked" and await _count(db, DraftRefreshAudit) == 2
        assert (await _audit(db, result.refresh_id)).idempotency_key == write_key("k-rb", 1)

    _scenario(body)


# ── ⑧ 查找：按列与按 detail.idempotency_base 两种来源 ────────────────────────────────────────────────────
def test_find_records_matches_column_and_detail_base():
    async def body(db):
        t0 = datetime(2026, 10, 28, 8, 0, tzinfo=timezone.utc)
        by_column = _audit_row("k8", at=t0)
        by_detail = _audit_row(None, detail={DETAIL_BASE_KEY: "k8"}, at=t0 + timedelta(minutes=1))
        db.add_all([by_column, by_detail,
                     _audit_row("k8-x", detail={DETAIL_BASE_KEY: "other"}, at=t0 + timedelta(minutes=2)),
                     _audit_row("k8", year=YEAR - 1, at=t0 + timedelta(minutes=3))])
        await db.commit()
        found = await find_records(db, PROJECT_ID, YEAR, "k8")
        assert [row.id for row in found] == [by_detail.id, by_column.id]  # 最近的在前
        prior = await find_prior(db, PROJECT_ID, YEAR, "k8")
        assert prior.id == by_detail.id == latest(found).id
        assert await count_occupied(db, PROJECT_ID, YEAR, "k8") == 2
        assert await find_prior(db, PROJECT_ID, YEAR, "k-none") is None

    _scenario(body)


# ── runtime_revisions：与原内联算法逐字一致 ─────────────────────────────────────────────────────────────
def test_runtime_revisions_match_former_inline_json():
    def sha(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    mutation = SimpleNamespace(source_formula_id=None, target=SimpleNamespace(addr_id="wp/审定表/B5"),
                               after_value=Decimal("1.50"), expected_version=3)
    unit = RefreshUnit(unit_scope="note:货币资金!0:1", after_value={"source": "preset", "v": Decimal("2.0")})
    assert runtime_revisions([], []) == (sha("[]"), sha("[]"))
    assert runtime_revisions([mutation], [unit]) == (
        sha('[{"after": "1.50", "source_formula_id": "", "target": "wp/审定表/B5", "version": 3}]'),
        sha('[{"after": {"source": "preset", "v": "2.0"}, "unit_scope": "note:货币资金!0:1"}]'),
    )


# ── report_basis ─────────────────────────────────────────────────────────────────────────────────────
_REPORT_TABLES = [Project.__table__, TrialBalance.__table__, FinancialReport.__table__, ReportConfig.__table__]
BS = FinancialReportType.balance_sheet


def _tb(code, audited, unadjusted, opening, *, year=YEAR, deleted=False):
    return TrialBalance(project_id=PROJECT_ID, year=year, company_code="C1", standard_account_code=code,
                        account_name=code, account_category=AccountCategory.asset, audited_amount=audited,
                        unadjusted_amount=unadjusted, opening_balance=opening, is_deleted=deleted)


def _fr(code, *, year=YEAR, deleted=False, stale=False):
    return FinancialReport(project_id=PROJECT_ID, year=year, report_type=BS, row_code=code, row_name=code,
                           calc_version=CALC_VERSION, is_stale=stale, is_deleted=deleted)


def test_report_basis_tracks_each_input_and_ignores_row_order():
    async def main():
        factory, engine = await _session(_REPORT_TABLES)
        try:
            async with factory() as db:
                db.add(Project(id=PROJECT_ID, name="幂等取数_2025", client_name="幂等取数", template_type="soe",
                               report_scope="standalone"))
                db.add_all([_tb("1001", Decimal("100"), Decimal("90"), Decimal("80")),
                            _tb("2001", Decimal("50"), Decimal("50"), None),
                            _tb("9999", Decimal("7"), None, None, deleted=True),
                            _tb("1001", Decimal("1"), None, None, year=YEAR - 1)])
                db.add_all([ReportConfig(report_type=BS, row_number=n, row_code=code, row_name=code, formula=text,
                                         applicable_standard="soe_standalone")
                            for n, (code, text) in enumerate((("BS-001", "TB('1001','期末余额')"),
                                                              ("BS-002", "ROW('BS-001')")), 1)])
                db.add_all([_fr("BS-001"), _fr("BS-002"), _fr("BS-003", deleted=True, stale=True),
                            _fr("BS-001", year=YEAR - 1, stale=True)])
                await db.commit()

                async def basis():
                    return await report_basis(db, PROJECT_ID, YEAR)

                base = await basis()
                # 组成与行序无关：按种子逆序独立算的行哈希相同；删除行、他年度行不计入
                assert base.tb_rows_hash == rows_hash(reversed(
                    [("1001", Decimal("100"), Decimal("90"), Decimal("80")), ("2001", Decimal("50"), Decimal("50"), None)]))
                assert base.definitions_hash == rows_hash(reversed(
                    [("balance_sheet", "BS-001", "TB('1001','期末余额')"), ("balance_sheet", "BS-002", "ROW('BS-001')")]))
                assert (base.calc_version, base.stale_count) == (CALC_VERSION, 0)

                async def change(stmt):
                    await db.execute(stmt)
                    await db.commit()
                    db.expire_all()
                    return await basis()

                tb, rc, fr = TrialBalance, ReportConfig, FinancialReport
                assert await change(sa.update(tb).where(tb.year == YEAR - 1).values(audited_amount=Decimal("2"))) == base
                assert await change(sa.update(tb).where(tb.is_deleted.is_(True)).values(audited_amount=Decimal("8"))) == base
                audited = await change(sa.update(tb).where(tb.standard_account_code == "2001", tb.year == YEAR)
                                       .values(audited_amount=Decimal("51")))
                assert audited.tb_rows_hash != base.tb_rows_hash
                assert (audited.definitions_hash, audited.stale_count) == (base.definitions_hash, 0)
                padded = await change(sa.update(rc).where(rc.row_code == "BS-002").values(formula="  ROW('BS-001')  "))
                assert padded.definitions_hash == base.definitions_hash  # 规范化（去首尾空白）后同一公式
                edited = await change(sa.update(rc).where(rc.row_code == "BS-002").values(formula="ROW('BS-001')*2"))
                assert edited.definitions_hash != base.definitions_hash and edited.tb_rows_hash == audited.tb_rows_hash
                marked = await change(sa.update(fr).where(fr.row_code == "BS-002", fr.year == YEAR).values(is_stale=True))
                assert (marked.stale_count, marked.definitions_hash) == (1, edited.definitions_hash)
                versionless = await change(sa.update(fr).where(fr.row_code == "BS-001", fr.year == YEAR)
                                           .values(calc_version=None))
                assert versionless.stale_count == 2  # 计算版本为空 ⇒ 过期（D13-A）
        finally:
            await engine.dispose()

    _run(main())


# ── 路由：409 与命中时的预设套用 dict ──────────────────────────────────────────────────────────────────
class _FakeDb:
    def __init__(self):
        self.committed = self.rolled_back = False

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


class _PassingPrecheck:
    async def precheck(self, db, *, project_id, year):
        return SimpleNamespace(can_refresh=True, to_dict=lambda: {"can_refresh": True})


def _call_router(monkeypatch, generate):
    async def _allow(_db, user, _project_id, _level):
        return user

    class _Orchestrator:
        def __init__(self, db):
            self.db = db

        async def generate(self, **kwargs):
            return await generate()

    monkeypatch.setattr(endpoint, "assert_project_permission", _allow)
    monkeypatch.setattr(endpoint, "DraftRefreshService", _PassingPrecheck)
    monkeypatch.setattr(endpoint, "DraftRefreshOrchestrator", _Orchestrator)
    db = _FakeDb()
    body = DraftRefreshRequest(project_id=PROJECT_ID, year=YEAR, scopes=["note"])
    return db, lambda: _run(endpoint.one_click_draft_refresh(body=body, db=db, _user=object()))


def test_router_maps_in_progress_to_409_without_commit(monkeypatch):
    busy = RefreshInProgress(uuid.uuid4())

    async def generate():
        raise busy

    db, call = _call_router(monkeypatch, generate)
    with pytest.raises(HTTPException) as raised:
        call()
    assert (raised.value.status_code, raised.value.detail) == (409, busy.to_detail())
    assert raised.value.detail["error_code"] == "DRAFT_REFRESH_IN_PROGRESS"
    assert (db.committed, db.rolled_back) == (False, False)  # 照 RuntimeFrozen：不 commit，会话随请求结束


def test_router_accepts_hit_preset_application_dict(monkeypatch):
    stored = {"preset_count": 2, "presetted_pages": ["note:a"], "pending_pages": ["note:b"]}
    prior = SimpleNamespace(id=uuid.uuid4(), operated_at=None, result_status="success",
                            detail={"outcome": "draft_marked", "draft_marked_count": 5, "preset_application": stored})

    async def generate():
        return hit_result(prior), hit_preset_application(prior)

    db, call = _call_router(monkeypatch, generate)
    resp = call()
    assert (resp.status, resp.idempotent, resp.run_id, resp.outcome) == ("idempotent_hit", True, prior.id, "draft_marked")
    assert (resp.draft_marked_count, resp.affected_count) == (5, 0)
    assert resp.preset_application.model_dump() == stored
    assert (db.committed, db.rolled_back) == (True, False)  # 命中照常 commit（没有写入），不发事件
