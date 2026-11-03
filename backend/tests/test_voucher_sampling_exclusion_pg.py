"""已抽排除与凭证上下文 × 真实账套（spec voucher-identity-writeback-and-audit-phase 任务 5，pg_only）

只读真实账；写入（回填日志、重导数据集、登记行）只在回滚事务里做。

1. 医疗器械银行存款（1002）整张凭证抽样单位 8,592 个（按凭证键；只按号是 692 个）；按单位取回的是整张凭证在
   过滤范围内的分录。
2. 预审批次按分录指纹排除：回滚事务里写一条预审回填日志（四川物流 FY-0012 的一笔银行存款分录），年审抽样不勾
   「排除已抽」也排除它；把整套账复制到新数据集并激活（新行 id、改过摘要）后仍排除新行。
3. 同号别月凭证不被排除：四川物流全年「0003」有几十张凭证，按凭证键只排 2025-01-07 FY-0003；旧日志只有凭证号时
   按号整张排除全部「0003」并标 legacy。
4. 凭证上下文：FY-0012 的样本行带整张凭证分录（5 行）与分录指纹；辅助明细账补全、登记表三个查询在真库上不报错。

项目或底稿缺失时跳过（数据依赖），不当作通过。
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.audit_platform_models import TbLedger, WorkpaperExtractionLog
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.models.workpaper_models import SampledVoucher
from app.services.dataset_service import DatasetService
from app.services.ledger_sampling_service import (
    LedgerQueryFilters,
    LedgerSamplingService,
    enrich_items_with_aux_party,
    enrich_voucher_context,
)
from app.services.sampled_voucher_queries import (
    cross_workpaper_duplicate_vouchers,
    project_level_extracted_vouchers,
    project_sampling_coverage,
)
from app.services.voucher_identity import VoucherKey, fingerprint_lines
from app.services.voucher_sampling_exclusion import collect_exclusions

pytestmark = pytest.mark.pg_only

YEAR = 2025
SICHUAN = uuid.UUID("f4b778ad-23b3-49ab-b3c8-ee62a5f82226")
MEDICAL = uuid.UUID("5e193c68-f53c-4e95-8d03-5d9c996c402d")
TBL = TbLedger.__table__
SNAPSHOT = json.loads(
    (Path(__file__).parent / "fixtures" / "voucher_real_ledger_vectors.json").read_text(encoding="utf-8")
)["counts_snapshot"]


@pytest.fixture
async def pg():
    if not str(settings.DATABASE_URL).startswith("postgresql"):
        pytest.skip("需要真实 PostgreSQL")
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
    await engine.dispose()


async def _active_ds(db: AsyncSession, pid: uuid.UUID) -> uuid.UUID:
    ds = await DatasetService.get_active_dataset_id(db, pid, YEAR)
    if ds is None:
        pytest.skip(f"{pid} 没有 {YEAR} 年 active 数据集")
    return ds


async def _a_workpaper(db: AsyncSession, pid: uuid.UUID) -> uuid.UUID:
    wp = (await db.execute(sa.text("SELECT id FROM working_paper WHERE project_id = :p LIMIT 1"), {"p": pid})).scalar()
    if wp is None:
        pytest.skip(f"{pid} 没有底稿，回填日志无处挂")
    return wp


async def _voucher_rows(db: AsyncSession, ds: uuid.UUID, vdate: date, vtype: str, no: str) -> list:
    return (await db.execute(
        sa.select(TBL).where(TBL.c.dataset_id == ds, TBL.c.voucher_date == vdate, TBL.c.voucher_type == vtype,
                             TBL.c.voucher_no == no, TBL.c.is_deleted == sa.false())
        .order_by(TBL.c.account_code, TBL.c.id)
    )).mappings().all()


async def _log(db: AsyncSession, pid: uuid.UUID, wp: uuid.UUID, criteria: dict) -> uuid.UUID:
    user = (await db.execute(sa.text("SELECT id FROM users ORDER BY created_at LIMIT 1"))).scalar()
    if user is None:
        pytest.skip("库里没有用户，回填日志的 user_id 外键无处指")
    log_id = uuid.uuid4()
    db.add(WorkpaperExtractionLog(
        id=log_id, project_id=pid, workpaper_id=wp, user_id=user, extraction_type="voucher_sampling",
        extraction_criteria=criteria, total_matched=1, filled_count=1, fill_mode="append",
    ))
    await db.flush()
    return log_id


async def _query(db, pid, *, start: date, end: date, accounts: list[str], ex=None):
    filters = LedgerQueryFilters(date_start=start, date_end=end, account_codes=accounts,
                                 **(ex.filter_kwargs() if ex else {}))
    return await LedgerSamplingService.build_ledger_query(db, pid, YEAR, filters)


async def _ids(db, query) -> set[uuid.UUID]:
    sub = query.subquery()
    return set((await db.execute(sa.select(sub.c.id))).scalars().all())


async def test_medical_bank_whole_voucher_units_by_key(pg):
    await _active_ds(pg, MEDICAL)
    query = await _query(pg, MEDICAL, start=date(2025, 1, 1), end=date(2025, 12, 31), accounts=["1002"])
    units = await LedgerSamplingService.locate_sampling_units(pg, query, unit="voucher")
    snap = SNAPSHOT["医疗器械_1002"]
    assert len(units) == len({u["unit_id"] for u in units}) == snap["n_key"] == 8592
    assert len({u["voucher_no"] for u in units}) == snap["n_no"]  # 只按号会并成 692 张
    # 取回一个单位 = 该凭证在过滤范围（1002）内的全部分录，且都属于这一张凭证
    unit = units[len(units) // 2]
    lines = await LedgerSamplingService.fetch_by_unit_ids(pg, query, "voucher", [unit["unit_id"]])
    vk = VoucherKey.from_str(unit["unit_id"])
    assert lines and all(VoucherKey.from_row(x, year=YEAR) == vk for x in lines)
    assert all(x["account_code"].startswith("1002") for x in lines)


async def test_preliminary_excluded_by_fingerprint_even_after_reimport(pg):
    old_ds = await _active_ds(pg, SICHUAN)
    wp = await _a_workpaper(pg, SICHUAN)
    rows = await _voucher_rows(pg, old_ds, date(2025, 1, 20), "FY", "0012")
    assert len(rows) == 5
    fps = dict(zip((r["id"] for r in rows), fingerprint_lines(rows)))
    bank = [r for r in rows if r["account_code"] == "1002"]
    sampled, other = sorted(bank, key=lambda r: r["credit_amount"])[::-1]  # 抽了贷 2,000 那笔，1,680 没抽
    await _log(pg, SICHUAN, wp, {"phase": "preliminary", "filled_line_fps": [fps[sampled["id"]]],
                                 "filled_voucher_keys": [VoucherKey.from_row(sampled).to_str()]})

    async def remaining() -> tuple[set[uuid.UUID], object]:
        ex = await collect_exclusions(pg, project_id=SICHUAN, year=YEAR, workpaper_id=wp,
                                      extraction_type="voucher_sampling", sampling_unit="ledger_line",
                                      exclude_extracted=False, phase="final")
        query = await _query(pg, SICHUAN, start=date(2025, 1, 1), end=date(2025, 1, 31), accounts=["1002"], ex=ex)
        return await _ids(pg, query), ex

    left, ex = await remaining()
    assert sampled["id"] not in left and other["id"] in left and ex.legacy is False

    # 重导：整套账复制到新数据集（新行 id、摘要改过），旧数据集 superseded、新数据集 active
    new_ds = (await DatasetService.create_staged(pg, SICHUAN, YEAR, source_type="import")).id
    cols = [c.name for c in TBL.columns]
    src = TBL.alias("src")
    exprs = [
        sa.func.gen_random_uuid() if n == "id"
        else sa.literal(new_ds, type_=TBL.c.dataset_id.type) if n == "dataset_id"
        else sa.func.concat(src.c.summary, "（重导后改过）") if n == "summary"
        else src.c[n]
        for n in cols
    ]
    await pg.execute(sa.insert(TBL).from_select(
        cols, sa.select(*exprs).where(src.c.dataset_id == old_ds, src.c.is_deleted == sa.false())))
    lds = LedgerDataset.__table__
    await pg.execute(sa.update(lds).where(lds.c.id == old_ds).values(status=DatasetStatus.superseded))
    await pg.execute(sa.update(lds).where(lds.c.id == new_ds).values(status=DatasetStatus.active,
                                                                    activated_at=sa.func.now()))
    assert await DatasetService.get_active_dataset_id(pg, SICHUAN, YEAR) == new_ds

    new_rows = await _voucher_rows(pg, new_ds, date(2025, 1, 20), "FY", "0012")
    new_sampled = next(r for r in new_rows if r["account_code"] == "1002" and r["credit_amount"] == sampled["credit_amount"])
    left, ex = await remaining()
    assert ex.line_ids == [str(new_sampled["id"])] and ex.unresolved_line_fps == 0
    new_bank = {r["id"] for r in new_rows if r["account_code"] == "1002"}
    assert new_sampled["id"] not in left and (new_bank - {new_sampled["id"]}) <= left
    assert not ({r["id"] for r in rows} & left)  # 旧数据集的行不再在抽样框里


async def test_same_number_other_vouchers_are_not_excluded(pg):
    ds = await _active_ds(pg, SICHUAN)
    wp = await _a_workpaper(pg, SICHUAN)
    fy = await _voucher_rows(pg, ds, date(2025, 1, 7), "FY", "0003")
    assert len(fy) == 2
    all_0003 = set((await pg.execute(sa.select(TBL.c.id).where(
        TBL.c.dataset_id == ds, TBL.c.voucher_no == "0003", TBL.c.is_deleted == sa.false()))).scalars().all())
    assert len(all_0003) > 10  # 全年几十张「0003」

    async def left_0003(criteria: dict):
        log_id = await _log(pg, SICHUAN, wp, criteria)
        ex = await collect_exclusions(pg, project_id=SICHUAN, year=YEAR, workpaper_id=wp,
                                      extraction_type="voucher_sampling", sampling_unit="voucher",
                                      exclude_extracted=True)
        query = await _query(pg, SICHUAN, start=date(2025, 1, 1), end=date(2025, 12, 31), accounts=[], ex=ex)
        left = (await _ids(pg, query)) & all_0003
        await pg.execute(sa.delete(WorkpaperExtractionLog).where(WorkpaperExtractionLog.id == log_id))
        return left, ex

    left, ex = await left_0003({"filled_voucher_keys": [VoucherKey.from_row(fy[0]).to_str()]})
    assert left == all_0003 - {r["id"] for r in fy} and ex.legacy is False
    left, ex = await left_0003({"filled_voucher_nos": ["0003"]})
    assert left == set() and ex.legacy is True  # 旧口径：凭证号整张排除，连带全年同号凭证


async def test_voucher_context_and_aux_party_on_real_ledger(pg, caplog):
    ds = await _active_ds(pg, SICHUAN)
    rows = await _voucher_rows(pg, ds, date(2025, 1, 20), "FY", "0012")
    query = await _query(pg, SICHUAN, start=date(2025, 1, 20), end=date(2025, 1, 20), accounts=["1002"])
    items, _ = await LedgerSamplingService.execute_with_stats(pg, query, page=1, page_size=500)
    items = [it for it in items if it["voucher_no"] == "0012" and it["voucher_type"] == "FY"]
    assert len(items) == 2
    with caplog.at_level(logging.WARNING):
        await enrich_items_with_aux_party(pg, SICHUAN, YEAR, items)
        await enrich_voucher_context(pg, SICHUAN, YEAR, items)
    assert not [r for r in caplog.records if "补全失败" in r.getMessage()], "补全在真库上报错（被 fail-open 吞成 WARNING）"
    fps = dict(zip((str(r["id"]) for r in rows), fingerprint_lines(rows)))
    vk = VoucherKey.from_row(rows[0]).to_str()
    for it in items:
        assert it["voucher_key"] == vk and it["side"] == "C" and it["line_fp"] == fps[it["id"]]
        assert sorted(e["line_fp"] for e in it["voucher_entries"]) == sorted(fps.values())  # 只有这一张的 5 行
        assert "party_name" in it and "party_ambiguous" in it


async def test_registry_queries_by_key_on_real_db(pg):
    ds = await _active_ds(pg, SICHUAN)
    wp = await _a_workpaper(pg, SICHUAN)
    fy = VoucherKey.from_row((await _voucher_rows(pg, ds, date(2025, 1, 7), "FY", "0003"))[0])
    zz = VoucherKey.from_row((await _voucher_rows(pg, ds, date(2025, 1, 7), "ZZ", "0003"))[0])
    feb = VoucherKey.from_row((await _voucher_rows(pg, ds, date(2025, 2, 5), "ZZ", "0003"))[0])

    def reg(vk: VoucherKey, wp_id) -> SampledVoucher:
        return SampledVoucher(id=uuid.uuid4(), project_id=SICHUAN, year=YEAR, voucher_no=vk.voucher_no,
                              voucher_date=vk.date_value, company_code=vk.company_code, voucher_type=vk.voucher_type,
                              working_paper_id=wp_id, batch_id=uuid.uuid4(), phase="preliminary")

    pg.add_all([reg(fy, wp), reg(fy, None), reg(feb, None),
                SampledVoucher(id=uuid.uuid4(), project_id=SICHUAN, year=YEAR, voucher_no="0046",
                               working_paper_id=None, batch_id=uuid.uuid4())])  # 旧行：只有号
    await pg.flush()
    keys, legacy_nos = await project_level_extracted_vouchers(pg, SICHUAN, YEAR)
    assert {fy, feb} <= set(keys) and zz not in keys and "0046" in legacy_nos
    dups = await cross_workpaper_duplicate_vouchers(pg, project_id=SICHUAN, year=YEAR, voucher_keys=[fy, zz],
                                                    exclude_workpaper_id=wp)
    # 同日同号的 ZZ-0003 没被别处抽过；FY-0003 被「未挂底稿」的引擎登记抽过（本底稿自己的不算）
    assert [(d["voucher_key"], d["legacy"], d["batch_count"]) for d in dups] == [(fy.to_str(), False, 1)]
    dup_cov = (await project_sampling_coverage(pg, SICHUAN, YEAR))["duplicated"]
    assert all(d["voucher_key"] != zz.to_str() for d in dup_cov)
