"""已抽排除按凭证键与分录指纹（spec voucher-identity-writeback-and-audit-phase 任务 5，需求 2.4 / 2.6 / 2.7）

SQLite 真 ORM 行，走生产路径：回填日志写进 workpaper_extraction_log → collect_exclusions →
LedgerSamplingService.build_ledger_query（排除字段经 SamplingExclusions.filter_kwargs，与两个路由同一映射）
→ 执行，断言剩下哪些分录；登记表三个查询按凭证键。

- 同号别月、同日同号别凭证字的凭证不被排除（旧口径按凭证号会整张连带）；
- 分录行单位按指纹：账套重导（新数据集、新行 id、摘要改过）后仍排除同一笔分录；旧日志的行 id 重导后失效；
- 整张凭证单位按凭证键；年审排除预审回填；撤销的回填不排除；项目级排除取登记表凭证键；
- 旧日志（只有凭证号）按旧口径并标 legacy_exclusion；
- 跨底稿重复 / 项目级概览按凭证键，旧登记行（无日期）按号兼容并标 legacy。
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import TbLedger, WorkpaperExtractionLog
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.models.workpaper_models import SampledVoucher, SamplingRecord, WorkingPaper, WpIndex
from app.services.ledger_sampling_service import LedgerQueryFilters, LedgerSamplingService
from app.services.sampled_voucher_queries import (
    cross_workpaper_duplicate_vouchers,
    project_level_extracted_vouchers,
    project_sampling_coverage,
)
from app.services.voucher_identity import VoucherKey, fingerprint_lines
from app.services.voucher_sampling_exclusion import collect_exclusions

_PID = uuid.uuid4()
_WP = uuid.uuid4()
_YEAR = 2025
_C = "001"


def _line(vdate, vtype, no, acct, d, c):
    return {"voucher_date": vdate, "voucher_type": vtype, "voucher_no": no, "account_code": acct,
            "debit_amount": d, "credit_amount": c}


#: 同日同号两种凭证字 + 同号别月 + 空凭证字；抽样科目 1122 每张一笔
VOUCHERS = {
    "FY-0003": [_line("2025-01-07", "FY", "0003", "1122", "100.00", None),
                _line("2025-01-07", "FY", "0003", "6001", None, "100.00")],
    "ZZ-0003": [_line("2025-01-07", "ZZ", "0003", "1122", "200.00", None),
                _line("2025-01-07", "ZZ", "0003", "6001", None, "200.00")],
    "ZZ-0003-feb": [_line("2025-02-07", "ZZ", "0003", "1122", "50.00", None),
                    _line("2025-02-07", "ZZ", "0003", "6001", None, "50.00")],
    "0046": [_line("2025-06-23", None, "0046", "1122", "8.00", None),
             _line("2025-06-23", None, "0046", "1002", None, "8.00")],
}
ALL_1122 = {"FY-0003", "ZZ-0003", "ZZ-0003-feb", "0046"}


def _vk(name: str) -> VoucherKey:
    return VoucherKey.from_row({**VOUCHERS[name][0], "company_code": _C}, year=_YEAR)


def _name_of(row) -> str:
    for name, lines in VOUCHERS.items():
        if VoucherKey.from_row(row, year=_YEAR) == _vk(name):
            return name
    raise AssertionError(f"未知凭证 {row}")


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [TbLedger.__table__, LedgerDataset.__table__, WorkpaperExtractionLog.__table__,
              SampledVoucher.__table__, SamplingRecord.__table__, WorkingPaper.__table__, WpIndex.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: TbLedger.metadata.create_all(c, tables=tables))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed(db, ds: uuid.UUID, *, summary: str = "原摘要", activated: datetime = datetime(2026, 1, 1)) -> None:
    db.add(LedgerDataset(id=ds, project_id=_PID, year=_YEAR, status=DatasetStatus.active,
                         source_type="import", activated_at=activated))
    for lines in VOUCHERS.values():
        for x in lines:
            db.add(TbLedger(
                id=uuid.uuid4(), project_id=_PID, year=_YEAR, company_code=_C,
                voucher_date=date.fromisoformat(x["voucher_date"]), voucher_type=x["voucher_type"],
                voucher_no=x["voucher_no"], account_code=x["account_code"],
                debit_amount=Decimal(x["debit_amount"]) if x["debit_amount"] else None,
                credit_amount=Decimal(x["credit_amount"]) if x["credit_amount"] else None,
                summary=f"{summary} {x['account_code']}", dataset_id=ds,
            ))
    await db.flush()


async def _reimport(db, old_ds: uuid.UUID) -> uuid.UUID:
    """重导：旧数据集 superseded，新数据集全部新行 id、客户改了摘要。"""
    await db.execute(sa.update(LedgerDataset).where(LedgerDataset.id == old_ds)
                     .values(status=DatasetStatus.superseded))
    new_ds = uuid.uuid4()
    await _seed(db, new_ds, summary="重导后改的摘要", activated=datetime(2026, 2, 1))
    return new_ds


async def _rows(db, ds: uuid.UUID | None = None) -> list[dict]:
    tbl = TbLedger.__table__
    stmt = sa.select(tbl).where(tbl.c.project_id == _PID)
    if ds is not None:
        stmt = stmt.where(tbl.c.dataset_id == ds)
    return (await db.execute(stmt.order_by(tbl.c.voucher_date, tbl.c.voucher_no, tbl.c.account_code))).mappings().all()


async def _sample_line(db, name: str, account: str = "1122", ds: uuid.UUID | None = None) -> tuple[str, str]:
    """某张凭证在科目 account 上那笔分录的 (分录指纹, 行 id)，指纹按整张凭证编（与 enrich_voucher_context 同）。"""
    lines = [r for r in await _rows(db, ds) if _name_of(r) == name]
    fps = fingerprint_lines(lines, year=_YEAR)
    for row, fp in zip(lines, fps):
        if row["account_code"] == account:
            return fp, str(row["id"])
    raise AssertionError(f"{name} 没有科目 {account}")


async def _log(db, criteria: dict, *, wp: uuid.UUID = _WP, undone: bool = False,
               extraction_type: str = "voucher_sampling") -> None:
    db.add(WorkpaperExtractionLog(
        id=uuid.uuid4(), project_id=_PID, workpaper_id=wp, user_id=uuid.uuid4(),
        extraction_type=extraction_type, extraction_criteria=criteria, total_matched=1, filled_count=1,
        fill_mode="append", is_undone=undone,
    ))
    await db.flush()


async def _new_log(db, names: list[str], **kw) -> None:
    """新格式回填日志：分录指纹 + 凭证键（+ 旧前端兼容的凭证号）。"""
    fps = [(await _sample_line(db, n))[0] for n in names]
    criteria = {
        "filled_line_fps": fps,
        "filled_voucher_keys": [_vk(n).to_str() for n in names],
        "filled_voucher_nos": sorted({VOUCHERS[n][0]["voucher_no"] for n in names}),
    }
    if "phase" in kw:
        criteria["phase"] = kw.pop("phase")
    await _log(db, criteria, **kw)


async def _remaining(db, *, unit: str = "ledger_line", exclude_extracted: bool = True, phase: str | None = None,
                     scope: str = "workpaper", extraction_type: str = "voucher_sampling"):
    ex = await collect_exclusions(
        db, project_id=_PID, year=_YEAR, workpaper_id=_WP, extraction_type=extraction_type,
        sampling_unit=unit, exclude_extracted=exclude_extracted, phase=phase, exclude_scope=scope,
    )
    filters = LedgerQueryFilters(date_start=date(2025, 1, 1), date_end=date(2025, 12, 31),
                                 account_codes=["1122"], **ex.filter_kwargs())
    query = await LedgerSamplingService.build_ledger_query(db, _PID, _YEAR, filters)
    rows = (await db.execute(query)).scalars().all()
    return ex, {_name_of(r) for r in rows}


class TestLineUnit:
    async def test_new_log_excludes_only_that_line(self, db):
        await _seed(db, uuid.uuid4())
        await _new_log(db, ["FY-0003"])
        ex, left = await _remaining(db)
        # 同日同号别凭证字、同号别月都还在（旧口径按「0003」会三张一起排除）
        assert left == ALL_1122 - {"FY-0003"}
        assert ex.legacy is False and len(ex.line_ids) == 1 and ex.voucher_nos == []

    async def test_still_excluded_after_reimport(self, db):
        old_ds = uuid.uuid4()
        await _seed(db, old_ds)
        await _new_log(db, ["FY-0003", "0046"])
        new_ds = await _reimport(db, old_ds)
        ex, left = await _remaining(db)
        assert left == ALL_1122 - {"FY-0003", "0046"}
        _, new_id = await _sample_line(db, "FY-0003", ds=new_ds)
        assert new_id in ex.line_ids and ex.unresolved_line_fps == 0

    async def test_legacy_line_ids_no_longer_match_after_reimport(self, db):
        """旧日志只记行 id：重导后行 id 全换，排除失效 —— 结果如实标 legacy，供界面提示。"""
        old_ds = uuid.uuid4()
        await _seed(db, old_ds)
        _, old_id = await _sample_line(db, "FY-0003")
        await _log(db, {"filled_voucher_nos": ["0003"], "filled_unit_ids": [old_id]})
        _, left_before = await _remaining(db)
        assert left_before == ALL_1122 - {"FY-0003"}
        await _reimport(db, old_ds)
        ex, left = await _remaining(db)
        assert left == ALL_1122 and ex.legacy is True and ex.legacy_line_ids == [old_id]

    async def test_legacy_number_only_log_keeps_old_behaviour_and_says_so(self, db):
        await _seed(db, uuid.uuid4())
        await _log(db, {"filled_voucher_nos": ["0003"]})
        ex, left = await _remaining(db)
        assert left == {"0046"}  # 旧口径：凭证号整张排除，连带同号别日、别凭证字
        assert ex.legacy is True and ex.to_stats()["legacy_exclusion"] is True

    async def test_undone_log_is_not_excluded(self, db):
        await _seed(db, uuid.uuid4())
        await _new_log(db, ["FY-0003"], undone=True)
        _, left = await _remaining(db)
        assert left == ALL_1122

    async def test_other_workpaper_and_other_type_not_excluded(self, db):
        await _seed(db, uuid.uuid4())
        await _new_log(db, ["FY-0003"], wp=uuid.uuid4())
        await _new_log(db, ["ZZ-0003"], extraction_type="cutoff")
        _, left = await _remaining(db)
        assert left == ALL_1122


class TestVoucherUnitAndPhase:
    async def test_voucher_unit_excludes_whole_voucher_by_key(self, db):
        await _seed(db, uuid.uuid4())
        await _new_log(db, ["ZZ-0003"])
        ex, left = await _remaining(db, unit="voucher")
        assert left == ALL_1122 - {"ZZ-0003"}
        assert ex.voucher_keys == [_vk("ZZ-0003").to_str()] and ex.line_ids == []

    async def test_cutoff_excludes_by_key(self, db):
        await _seed(db, uuid.uuid4())
        await _log(db, {"filled_voucher_keys": [_vk("ZZ-0003-feb").to_str()], "filled_voucher_nos": ["0003"]},
                   extraction_type="cutoff")
        _, left = await _remaining(db, unit="voucher", extraction_type="cutoff")
        assert left == ALL_1122 - {"ZZ-0003-feb"}

    async def test_final_excludes_preliminary_even_when_exclude_extracted_off(self, db):
        await _seed(db, uuid.uuid4())
        await _new_log(db, ["FY-0003"], phase="preliminary")
        await _new_log(db, ["ZZ-0003"], phase="final")
        _, left = await _remaining(db, exclude_extracted=False, phase="final")
        assert left == ALL_1122 - {"FY-0003"}
        _, left_all = await _remaining(db, phase="final")
        assert left_all == ALL_1122 - {"FY-0003", "ZZ-0003"}
        _, left_prelim = await _remaining(db, exclude_extracted=False, phase="preliminary")
        assert left_prelim == ALL_1122


def _registered(name: str | None, *, wp: uuid.UUID | None, no: str | None = None, batch: bool = True,
                deleted: bool = False) -> SampledVoucher:
    """登记行：name 给出时按凭证键（V210 起的写法）；name=None 时是只有凭证号的旧行（日期等为空）。"""
    if name is None:
        return SampledVoucher(id=uuid.uuid4(), project_id=_PID, year=_YEAR, voucher_no=no,
                              working_paper_id=wp, batch_id=uuid.uuid4() if batch else None, is_deleted=deleted)
    vk = _vk(name)
    return SampledVoucher(
        id=uuid.uuid4(), project_id=_PID, year=_YEAR, voucher_no=vk.voucher_no, voucher_date=vk.date_value,
        company_code=vk.company_code, voucher_type=vk.voucher_type, working_paper_id=wp,
        batch_id=uuid.uuid4() if batch else None, is_deleted=deleted,
    )


class TestRegistryByVoucherKey:
    async def test_project_scope_excludes_registered_vouchers_only(self, db):
        await _seed(db, uuid.uuid4())
        other_wp = uuid.uuid4()
        db.add_all([
            _registered("ZZ-0003", wp=other_wp),
            _registered("ZZ-0003-feb", wp=other_wp, batch=False),  # 穿透页手工标记：不算已执行抽凭
            _registered("0046", wp=other_wp, deleted=True),  # 撤销（软删）
        ])
        await db.flush()
        ex, left = await _remaining(db, scope="project")
        assert left == ALL_1122 - {"ZZ-0003"}
        assert ex.voucher_keys == [_vk("ZZ-0003").to_str()] and ex.legacy is False
        _, left_wp_scope = await _remaining(db)
        assert left_wp_scope == ALL_1122

    async def test_legacy_registry_rows_exclude_by_number(self, db):
        await _seed(db, uuid.uuid4())
        db.add(_registered(None, wp=uuid.uuid4(), no="0046"))
        await db.flush()
        assert await project_level_extracted_vouchers(db, _PID, _YEAR) == ([], ["0046"])
        ex, left = await _remaining(db, scope="project")
        assert left == ALL_1122 - {"0046"} and ex.legacy is True

    async def test_cross_workpaper_duplicates_by_key(self, db):
        other_wp = uuid.uuid4()
        db.add_all([_registered("ZZ-0003-feb", wp=other_wp), _registered("FY-0003", wp=_WP)])
        await db.flush()
        # 本次样本是 1 月的 ZZ-0003：别的底稿抽的是 2 月那张同号凭证，不是重复（旧口径按号会误报）
        assert await cross_workpaper_duplicate_vouchers(
            db, project_id=_PID, year=_YEAR, voucher_keys=[_vk("ZZ-0003")], exclude_workpaper_id=_WP) == []
        got = await cross_workpaper_duplicate_vouchers(
            db, project_id=_PID, year=_YEAR, voucher_keys=[_vk("ZZ-0003-feb"), _vk("FY-0003")],
            exclude_workpaper_id=_WP)
        assert [(d["voucher_key"], d["legacy"], d["batch_count"]) for d in got] == [
            (_vk("ZZ-0003-feb").to_str(), False, 1)]  # 本底稿自己登记的 FY-0003 不算
        assert got[0]["voucher_date"] == "2025-02-07" and got[0]["voucher_type"] == "ZZ"

    async def test_cross_workpaper_legacy_row_matches_by_number_and_is_flagged(self, db):
        db.add(_registered(None, wp=uuid.uuid4(), no="0003"))
        await db.flush()
        got = await cross_workpaper_duplicate_vouchers(
            db, project_id=_PID, year=_YEAR, voucher_keys=[_vk("FY-0003"), _vk("0046")], exclude_workpaper_id=_WP)
        assert [(d["voucher_key"], d["legacy"]) for d in got] == [(_vk("FY-0003").to_str(), True)]

    async def test_coverage_duplicated_by_key(self, db):
        wp1, wp2, wp3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        db.add_all([
            _registered("FY-0003", wp=wp1), _registered("FY-0003", wp=wp2),
            _registered("ZZ-0003", wp=wp3), _registered("ZZ-0003-feb", wp=wp2),
        ])
        await db.flush()
        dup = (await project_sampling_coverage(db, _PID, _YEAR))["duplicated"]
        # 按号会把三张「0003」算成被 3 个底稿抽过；按凭证键只有 FY-0003 被两个底稿抽过
        assert [(d["voucher_key"], d["workpaper_count"], d["legacy"]) for d in dup] == [
            (_vk("FY-0003").to_str(), 2, False)]


# ─── 幂等键：按分录指纹 / 凭证键，旧日志与改造前逐字相同 ─────────────────────────


class _KeyCapture:
    """只记下 record_extraction_log 派生的幂等键；查重一律「没有既有记录」。"""

    def __init__(self):
        self.keys: list[str | None] = []

    async def execute(self, stmt):
        from types import SimpleNamespace

        return SimpleNamespace(scalar_one_or_none=lambda: None)

    def add(self, record):
        self.keys.append(record.idempotency_key)
        self._record = record

    async def flush(self):
        self._record.id = uuid.uuid4()
        self._record.created_at = datetime(2026, 10, 27)


async def _key_for(criteria: dict, *, wp: uuid.UUID = _WP, extraction_type: str = "voucher_sampling") -> str | None:
    from app.services.ledger_sampling_service import ExtractionLogCreate

    db = _KeyCapture()
    await LedgerSamplingService.record_extraction_log(db, ExtractionLogCreate(
        project_id=_PID, workpaper_id=wp, user_id=uuid.uuid4(), extraction_type=extraction_type,
        extraction_criteria=criteria, total_matched=1, filled_count=1, fill_mode="append",
    ))
    return db.keys[0]


class TestIdempotencyKey:
    async def test_legacy_log_key_is_byte_identical_to_before(self):
        import hashlib
        import json

        body = {"wp": str(_WP), "type": "voucher_sampling", "mode": "append", "vouchers": ["0003", "0046"]}
        old = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        assert await _key_for({"filled_voucher_nos": ["0046", "0003"], "phase": "final"}) == old

    async def test_same_number_different_voucher_is_a_different_batch(self):
        """截止测试只回填凭证键：FY-0003 与 ZZ-0003 号相同，按号派生会把第二批当成重复丢掉。"""
        fy = await _key_for({"filled_voucher_keys": [_vk("FY-0003").to_str()], "filled_voucher_nos": ["0003"]},
                            extraction_type="cutoff")
        zz = await _key_for({"filled_voucher_keys": [_vk("ZZ-0003").to_str()], "filled_voucher_nos": ["0003"]},
                            extraction_type="cutoff")
        assert fy and zz and fy != zz

    async def test_fps_key_ignores_numbers_and_order_but_not_phase(self):
        a = '["2025","001","2025-01-07","FY","0003","1122","D","100.00",0]'
        b = '["2025","001","2025-01-07","ZZ","0003","1122","D","200.00",0]'
        k1 = await _key_for({"filled_line_fps": [a, b], "filled_voucher_nos": ["0003"], "phase": "preliminary"})
        k2 = await _key_for({"filled_line_fps": [b, a], "filled_voucher_nos": ["X"], "phase": "preliminary"})
        k3 = await _key_for({"filled_line_fps": [a, b], "phase": "final"})
        k4 = await _key_for({"filled_line_fps": [a, b], "phase": "final", "final_population_mode": "remaining_period"})
        assert k1 == k2 and len({k1, k3, k4}) == 3

    async def test_no_identity_no_key(self):
        assert await _key_for({"phase": "final"}) is None


# ─── 两个路由把收集器结果原样交给 LedgerQueryFilters ───────────────────────────


def _full_exclusions():
    from app.services.voucher_sampling_exclusion import SamplingExclusions

    return SamplingExclusions(
        voucher_keys=[_vk("FY-0003").to_str()], line_ids=[str(uuid.uuid4())], voucher_nos=["0009"],
        legacy_line_ids=[str(uuid.uuid4())], legacy=True, unresolved_line_fps=2,
    )


def _assert_filters_carry(filters, ex):
    assert filters.exclude_voucher_keys == ex.voucher_keys
    assert filters.exclude_line_ids == ex.line_ids
    assert filters.exclude_voucher_nos == ex.voucher_nos
    assert filters.exclude_unit_ids == ex.legacy_line_ids


class TestRoutersHandExclusionsToFilters:
    async def test_voucher_extract(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        from httpx import ASGITransport, AsyncClient

        from app.services.sampling_population_reconcile import PopulationReconcileFacts
        from tests.test_voucher_sampling_integration import (
            _make_app, _make_extract_request, _make_ledger_rows, _make_stats,
        )

        ex = _full_exclusions()
        app, _ = _make_app()
        population = _make_ledger_rows(5)
        with patch("app.routers.voucher_sampling._authorize_and_validate_extract", new=AsyncMock(return_value=None)), \
                patch("app.routers.voucher_sampling.resolve_population_reconcile",
                      new=AsyncMock(return_value=PopulationReconcileFacts(available=False))), \
                patch("app.routers.voucher_sampling.resolve_final_population", new=AsyncMock(return_value=None)), \
                patch("app.routers.voucher_sampling.collect_exclusions", new=AsyncMock(return_value=ex)) as collect, \
                patch("app.routers.voucher_sampling.LedgerSamplingService") as svc:
            svc.build_ledger_query = AsyncMock(return_value=MagicMock())
            svc.execute_with_stats = AsyncMock(return_value=(population, _make_stats(population)))
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(f"/api/projects/{_PID}/sampling/voucher-extract",
                                         json=_make_extract_request(phase="final"))
        assert resp.status_code == 200, resp.text
        _assert_filters_carry(svc.build_ledger_query.call_args[0][3], ex)
        assert collect.await_args.kwargs["phase"] == "final"
        stats = resp.json()["stats"]
        assert (stats["legacy_exclusion"], stats["excluded_voucher_count"], stats["unresolved_excluded_lines"]) == (
            True, 1, 2)

    async def test_cutoff_extract(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        from httpx import ASGITransport, AsyncClient

        from app.services.ledger_sampling_service import StatsResult
        from tests.test_cutoff_sampling_integration import _make_app, _make_extract_request

        ex = _full_exclusions()
        app, _ = _make_app()
        stats = StatsResult(total_count=0, debit_total=Decimal("0"), credit_total=Decimal("0"),
                            by_voucher_type={}, truncated=False)
        with patch("app.routers.cutoff_sampling.collect_exclusions", new=AsyncMock(return_value=ex)) as collect, \
                patch("app.routers.cutoff_sampling.LedgerSamplingService") as svc:
            svc.build_ledger_query = AsyncMock(return_value=MagicMock())
            svc.execute_with_stats = AsyncMock(return_value=([], stats))
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(f"/api/projects/{_PID}/sampling/cutoff-extract", json=_make_extract_request())
        assert resp.status_code == 200, resp.text
        _assert_filters_carry(svc.build_ledger_query.call_args[0][3], ex)
        assert collect.await_args.kwargs["sampling_unit"] == "voucher"
        assert resp.json()["stats"]["legacy_exclusion"] is True

    async def test_cutoff_fill_records_voucher_identity(self):
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient

        from tests.test_cutoff_sampling_integration import _make_app, _make_fill_request

        app, mock_db = _make_app()
        mock_db.commit = AsyncMock()
        req = {**_make_fill_request(), "filled_voucher_keys": [_vk("FY-0003").to_str()], "filled_line_fps": ["fp-1"]}
        with patch("app.routers.cutoff_sampling.LedgerSamplingService") as svc:
            svc.record_extraction_log = AsyncMock(return_value={"id": str(uuid.uuid4()), "created_at": "2025-12-31"})
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(f"/api/projects/{_PID}/sampling/cutoff-fill", json=req)
        assert resp.status_code == 200, resp.text
        crit = svc.record_extraction_log.await_args.args[1].extraction_criteria
        assert crit["filled_voucher_keys"] == [_vk("FY-0003").to_str()] and crit["filled_line_fps"] == ["fp-1"]
        assert crit["filled_voucher_nos"] == req["filled_voucher_nos"]  # 旧前端兼容字段照记

    async def test_in_memory_voucher_unit_is_keyed_by_voucher_key(self):
        """整张凭证单位（总体未超内存上限）：同号别日的两张凭证是两个单位，抽中一张只带出它自己的分录。"""
        from unittest.mock import AsyncMock, MagicMock, patch

        from httpx import ASGITransport, AsyncClient

        from app.services.sampling_population_reconcile import PopulationReconcileFacts
        from app.services.voucher_sampling_exclusion import SamplingExclusions
        from tests.test_voucher_sampling_integration import _make_app, _make_extract_request, _make_stats

        def row(vdate, vtype, acct, d, c):
            return {"id": str(uuid.uuid4()), "voucher_date": vdate, "voucher_no": "0003", "voucher_type": vtype,
                    "account_code": acct, "debit_amount": d, "credit_amount": c, "company_code": _C}

        population = [row("2025-01-07", "FY", "1122", "1000.00", None), row("2025-01-07", "FY", "1122", None, "1000.00"),
                      row("2025-02-07", "ZZ", "1122", "50.00", None), row("2025-02-07", "ZZ", "1122", None, "50.00")]
        req = _make_extract_request(method="specific_item", sampling_params={"materiality_threshold": "500"})
        req["filters"]["sampling_unit"] = "voucher"
        app, _ = _make_app()
        with patch("app.routers.voucher_sampling._authorize_and_validate_extract", new=AsyncMock(return_value=None)), \
                patch("app.routers.voucher_sampling.resolve_population_reconcile",
                      new=AsyncMock(return_value=PopulationReconcileFacts(available=False))), \
                patch("app.routers.voucher_sampling.collect_exclusions",
                      new=AsyncMock(return_value=SamplingExclusions())), \
                patch("app.routers.voucher_sampling.LedgerSamplingService") as svc:
            svc.build_ledger_query = AsyncMock(return_value=MagicMock())
            svc.execute_with_stats = AsyncMock(return_value=(population, _make_stats(population)))
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(f"/api/projects/{_PID}/sampling/voucher-extract", json=req)
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        # 按号聚合会把两张「0003」并成一个 2,100 元的单位，抽中后带出 4 行
        assert [(it["voucher_type"], it["voucher_date"]) for it in items] == [("FY", "2025-01-07")] * 2
