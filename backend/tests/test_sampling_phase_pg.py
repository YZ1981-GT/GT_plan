"""年审抽样口径 × 真实账套（spec voucher-identity-writeback-and-audit-phase 任务 15，需求 7.1~7.4，pg_only）

在一个最后回滚的外层事务里调真实端点（会话以 create_savepoint 方式加入外层事务），真库不留痕。

辽宁卫生 2025 年「其他应付款」（2241）全年 6,135 条分录（上半年 2,510、下半年 3,625）。回滚事务里把项目设为
年审、预审截止日 2025-06-30，给一张底稿造预审工作：一条预审抽凭回填（2 月一笔 2241 分录的指纹）与两张预审手工
挂凭 —— 2025-01-03 ZZ-0004（2241 下 2 条；同日同号还有 ZJGJ-0004，凭证字不同不算）和 3 月一张跨科目凭证
（只扣它在 2241 下的分录）。

1. 缺口径 422 FINAL_POPULATION_MODE_REQUIRED；phase-context 报批次 1、挂凭 2、须选口径、缺省 b。
2. 口径 a：抽样框只含 2025-07-01 至 2025-12-31 的 3,625 条；所选期间全在截止日前 400。
3. 口径 b：抽样框 = 全年 − 预审回填分录 − 预审挂凭在 2241 下的分录；账套重导（新行 id）后仍扣除。
4. 项目没设截止日：口径 a 取预审批次期间上限（留痕注明来源）；批次也没期间信息 400。
5. 预审阶段不问口径、stats 不带 final_population。
6. 全年合并评价（任务 16）：年审批次回填随带评价、再保存评价，两条写入路径都写服务端现算的 combined（客户端传的
   不收）并投影到抽样记录结论；GET /phase-evaluation 与库里一致。

数据依赖缺失（项目 / 账套 / 底稿 / admin 用户）时跳过，不当作通过。
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.audit_platform_models import TbLedger, WorkpaperExtractionLog
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.models.workpaper_models import SampledVoucher
from app.services.dataset_service import DatasetService
from app.services.sampling_final_population import resolve_final_population
from app.services.voucher_identity import VoucherKey, fingerprint_lines
from app.services.voucher_sampling_exclusion import collect_exclusions

pytestmark = pytest.mark.pg_only

LIAONING = uuid.UUID("d9295a0c-f347-4aa5-a1d1-faf7847d379b")
YEAR = 2025
ACCT = "2241"
CUTOFF = date(2025, 6, 30)
TBL = TbLedger.__table__


@pytest.fixture
async def pg():
    if not str(settings.DATABASE_URL).startswith("postgresql"):
        pytest.skip("需要真实 PostgreSQL")
    engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    async with engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()
    await engine.dispose()


async def _counts(db: AsyncSession, ds: uuid.UUID) -> dict[str, int]:
    row = (await db.execute(sa.text(
        "SELECT count(*) AS total, count(*) FILTER (WHERE voucher_date > :c) AS h2 FROM tb_ledger "
        "WHERE dataset_id = :d AND is_deleted = false AND account_code LIKE :a"),
        {"d": ds, "a": f"{ACCT}%", "c": CUTOFF})).mappings().one()
    return dict(row)


async def _voucher_lines(db: AsyncSession, ds: uuid.UUID, vdate: date, vtype: str, no: str) -> list:
    return (await db.execute(
        sa.select(TBL).where(TBL.c.dataset_id == ds, TBL.c.voucher_date == vdate, TBL.c.voucher_type == vtype,
                             TBL.c.voucher_no == no, TBL.c.is_deleted == sa.false())
        .order_by(TBL.c.account_code, TBL.c.id)
    )).mappings().all()


@pytest.fixture
async def world(pg):
    """项目设年审 + 截止日；一张底稿上造预审回填一条（2 月 2241 分录）与预审手工挂凭一张（ZZ-0004）。"""
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers import cutoff_sampling, sampling_phase, voucher_sampling

    admin = (await pg.execute(sa.text("SELECT id FROM users WHERE username = 'admin'"))).scalar()
    proj = (await pg.execute(sa.text("SELECT is_deleted, status FROM projects WHERE id = :p"), {"p": LIAONING})).first()
    ds = await DatasetService.get_active_dataset_id(pg, LIAONING, YEAR)
    wp = (await pg.execute(sa.text(
        "SELECT id FROM working_paper WHERE project_id = :p AND is_deleted = false ORDER BY id LIMIT 1"),
        {"p": LIAONING})).scalar()
    if admin is None or proj is None or proj.is_deleted or str(proj.status) == "archived" or ds is None or wp is None:
        pytest.skip("辽宁卫生项目 / 2025 账套 / 底稿 / admin 用户不可用（数据依赖）")
    counts = await _counts(pg, ds)
    if counts != {"total": 6135, "h2": 3625}:
        pytest.skip(f"辽宁卫生 2241 分录数与快照不符（现 {counts}），数据已变")

    feb = (await pg.execute(sa.text(
        "SELECT voucher_date, voucher_type, voucher_no FROM tb_ledger WHERE dataset_id = :d AND is_deleted = false "
        "AND account_code LIKE :a AND voucher_date BETWEEN '2025-02-01' AND '2025-02-28' "
        "ORDER BY voucher_date, voucher_type, voucher_no LIMIT 1"), {"d": ds, "a": f"{ACCT}%"})).first()
    lines = await _voucher_lines(pg, ds, feb.voucher_date, feb.voucher_type, feb.voucher_no)
    fps = dict(zip((r["id"] for r in lines), fingerprint_lines(lines)))
    sampled = next(r for r in lines if r["account_code"].startswith(ACCT))
    await pg.execute(sa.text("UPDATE projects SET current_audit_phase = 'final', interim_cutoff_date = :c WHERE id = :p"),
                     {"c": CUTOFF, "p": LIAONING})
    prelim = WorkpaperExtractionLog(
        id=uuid.uuid4(), project_id=LIAONING, workpaper_id=wp, user_id=admin, extraction_type="voucher_sampling",
        extraction_criteria={"phase": "preliminary", "filled_line_fps": [fps[sampled["id"]]],
                             "filled_voucher_keys": [VoucherKey.from_row(sampled).to_str()],
                             "filters": {"account_codes": [ACCT], "period_range": [1, 2, 3, 4, 5, 6]}},
        total_matched=2510, filled_count=1, fill_mode="append",
    )
    pg.add(prelim)
    # 预审手工挂凭两张：ZZ-0004（同日同号还有一张 ZJGJ-0004，凭证字不同不算）与 3 月一张跨科目凭证
    # （只扣它落在 2241 下的分录，别的科目的分录不在本次科目范围内）
    zz = await _voucher_lines(pg, ds, date(2025, 1, 3), "ZZ", "0004")
    assert sorted(r["account_code"] for r in zz) == ["2241.12", "2241.98.06"]
    mar = (await pg.execute(sa.text(
        "SELECT voucher_date, voucher_type, voucher_no FROM tb_ledger WHERE dataset_id = :d AND is_deleted = false "
        "AND voucher_date BETWEEN '2025-03-01' AND '2025-03-31' GROUP BY voucher_date, voucher_type, voucher_no "
        "HAVING bool_or(account_code LIKE :a) AND bool_or(account_code NOT LIKE :a) "
        "ORDER BY voucher_date, voucher_type, voucher_no LIMIT 1"), {"d": ds, "a": f"{ACCT}%"})).first()
    mar_lines = await _voucher_lines(pg, ds, mar.voucher_date, mar.voucher_type, mar.voucher_no)
    for vk_row in (zz[0], mar_lines[0]):
        pg.add(SampledVoucher(
            id=uuid.uuid4(), project_id=LIAONING, year=YEAR, voucher_no=vk_row["voucher_no"],
            voucher_date=vk_row["voucher_date"], voucher_type=vk_row["voucher_type"],
            company_code=vk_row["company_code"], phase="preliminary", account_code=ACCT,
            working_paper_id=wp, batch_id=None,
        ))
    await pg.flush()
    attach_in_scope = sorted(str(r["id"]) for r in [*zz, *mar_lines] if r["account_code"].startswith(ACCT))
    assert 3 <= len(attach_in_scope) < 2 + len(mar_lines)

    class _Admin:
        id = admin

        class _Role:
            value = "admin"

        role = _Role()

    async def _db():
        yield pg

    async def _user():
        return _Admin()

    app = FastAPI()
    app.include_router(voucher_sampling.router)
    app.include_router(sampling_phase.router)
    app.include_router(cutoff_sampling.router)
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield {"client": client, "wp": wp, "ds": ds, "sampled": sampled, "admin": admin, "prelim_id": prelim.id,
               "attach_in_scope": attach_in_scope, "attach_vouchers": [zz[0], mar_lines[0]]}


def _extract_body(wp, *, mode=None, months=None) -> dict:
    body = {"sampling_method": "random", "sampling_params": {"sample_size": 3}, "random_seed": 7,
            "workpaper_id": str(wp), "year": YEAR,
            "filters": {"account_codes": [ACCT], "period_range": months or list(range(1, 13)), "exclude_extracted": True}}
    if mode:
        body["final_population_mode"] = mode
    return body


async def _extract(world, **kw):
    return await world["client"].post(f"/api/projects/{LIAONING}/sampling/voucher-extract", json=_extract_body(world["wp"], **kw))


async def test_phase_context_and_missing_mode_422(world):
    ctx = (await world["client"].get(f"/api/projects/{LIAONING}/sampling/phase-context",
                                     params={"wp_id": str(world["wp"])})).json()
    assert ctx["current_audit_phase"] == "final" and ctx["interim_cutoff_date"] == "2025-06-30"
    assert (ctx["interim_batch_count"], ctx["interim_sample_count"], ctx["interim_line_count"], ctx["interim_attach_count"]) == (1, 1, 1, 2)
    assert ctx["requires_final_population_mode"] is True and ctx["default_final_population_mode"] == "full_minus_interim"
    assert ctx["effective_cutoff_date"] == "2025-06-30" and ctx["cutoff_source"] == "project"
    resp = await _extract(world)
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["error_code"] == "FINAL_POPULATION_MODE_REQUIRED"


async def test_mode_a_frame_is_remaining_period_only(world):
    resp = await _extract(world, mode="remaining")
    assert resp.status_code == 200, resp.text
    stats = resp.json()["stats"]
    assert stats["population_count"] == 3625
    fp = stats["final_population"]
    assert (fp["mode"], fp["date_start"], fp["date_end"], fp["interim_cutoff_source"]) == (
        "remaining", "2025-07-01", "2025-12-31", "project")
    assert all(it["voucher_date"] > "2025-06-30" for it in resp.json()["items"])
    early = await _extract(world, mode="remaining", months=[1, 2, 3])
    assert early.status_code == 400 and early.json()["detail"]["error_code"] == "REMAINING_PERIOD_EMPTY"


async def test_mode_b_excludes_interim_batch_and_attach_lines_even_after_reimport(world, pg):
    n_attach = len(world["attach_in_scope"])
    resp = await _extract(world, mode="full_minus_interim")
    assert resp.status_code == 200, resp.text
    stats = resp.json()["stats"]
    assert stats["population_count"] == 6135 - 1 - n_attach
    fp = stats["final_population"]
    assert (fp["mode"], fp["interim_batch_line_fps"], fp["interim_attach_count"], fp["excluded_attach_lines"],
            fp["unresolved_attach_count"]) == ("full_minus_interim", 1, 2, n_attach, 0)
    final = await resolve_final_population(
        pg, project_id=LIAONING, workpaper_id=world["wp"], year=YEAR, phase="final", mode="full_minus_interim",
        date_start=date(2025, 1, 1), date_end=date(2025, 12, 31), account_codes=[ACCT])
    assert sorted(final.attach_line_ids) == world["attach_in_scope"]

    # 重导：2241 分录复制到新数据集（新行 id），旧数据集 superseded、新数据集 active
    old_ds = world["ds"]
    new_ds = (await DatasetService.create_staged(pg, LIAONING, YEAR, source_type="import")).id
    cols = [c.name for c in TBL.columns]
    src = TBL.alias("src")
    exprs = [sa.func.gen_random_uuid() if n == "id" else sa.literal(new_ds, type_=TBL.c.dataset_id.type)
             if n == "dataset_id" else src.c[n] for n in cols]
    await pg.execute(sa.insert(TBL).from_select(cols, sa.select(*exprs).where(
        src.c.dataset_id == old_ds, src.c.is_deleted == sa.false(), src.c.account_code.like(f"{ACCT}%"))))
    lds = LedgerDataset.__table__
    await pg.execute(sa.update(lds).where(lds.c.id == old_ds).values(status=DatasetStatus.superseded))
    await pg.execute(sa.update(lds).where(lds.c.id == new_ds).values(status=DatasetStatus.active, activated_at=sa.func.now()))
    assert await DatasetService.get_active_dataset_id(pg, LIAONING, YEAR) == new_ds

    again = await _extract(world, mode="full_minus_interim")
    assert again.status_code == 200, again.text
    assert again.json()["stats"]["population_count"] == 6135 - 1 - n_attach
    assert again.json()["stats"]["dataset_id"] == str(new_ds)

    # 扣除的是新账套的行：批次分录经指纹、挂凭经凭证键重新定位
    final = await resolve_final_population(
        pg, project_id=LIAONING, workpaper_id=world["wp"], year=YEAR, phase="final", mode="full_minus_interim",
        date_start=date(2025, 1, 1), date_end=date(2025, 12, 31), account_codes=[ACCT])
    new_lines = [r for v in world["attach_vouchers"]
                 for r in await _voucher_lines(pg, new_ds, v["voucher_date"], v["voucher_type"], v["voucher_no"])]
    assert sorted(final.attach_line_ids) == sorted(str(r["id"]) for r in new_lines)  # 新账套只复制了 2241 分录
    assert len(final.attach_line_ids) == n_attach and not set(final.attach_line_ids) & set(world["attach_in_scope"])
    ex = await collect_exclusions(pg, project_id=LIAONING, year=YEAR, workpaper_id=world["wp"],
                                  extraction_type="voucher_sampling", sampling_unit="ledger_line",
                                  exclude_extracted=True, phase="final")
    s = world["sampled"]
    new_sampled = (await pg.execute(sa.select(TBL.c.id).where(
        TBL.c.dataset_id == new_ds, TBL.c.voucher_date == s["voucher_date"], TBL.c.voucher_type == s["voucher_type"],
        TBL.c.voucher_no == s["voucher_no"], TBL.c.account_code == s["account_code"],
        TBL.c.debit_amount == s["debit_amount"], TBL.c.credit_amount == s["credit_amount"]))).scalars().all()
    assert len(ex.line_ids) == 1 and ex.line_ids[0] in {str(i) for i in new_sampled} and ex.unresolved_line_fps == 0


async def test_cutoff_falls_back_to_interim_batch_period_then_400(world, pg):
    await pg.execute(sa.text("UPDATE projects SET interim_cutoff_date = NULL WHERE id = :p"), {"p": LIAONING})
    ctx = (await world["client"].get(f"/api/projects/{LIAONING}/sampling/phase-context",
                                     params={"wp_id": str(world["wp"])})).json()
    assert (ctx["interim_cutoff_date"], ctx["effective_cutoff_date"], ctx["cutoff_source"]) == (
        None, "2025-06-30", "interim_batches")
    resp = await _extract(world, mode="remaining")
    assert resp.status_code == 200, resp.text
    fp = resp.json()["stats"]["final_population"]
    assert (fp["interim_cutoff_date"], fp["interim_cutoff_source"], fp["date_start"]) == (
        "2025-06-30", "interim_batches", "2025-07-01")
    assert resp.json()["stats"]["population_count"] == 3625

    # 预审批次没有期间信息、项目也没设截止日：口径 a 无从确定 → 400；口径 b 不受影响
    log = WorkpaperExtractionLog.__table__
    await pg.execute(sa.update(log).where(log.c.workpaper_id == world["wp"]).values(
        extraction_criteria={"phase": "preliminary", "filled_line_fps": []}))
    no_cutoff = await _extract(world, mode="remaining")
    assert no_cutoff.status_code == 400 and no_cutoff.json()["detail"]["error_code"] == "INTERIM_CUTOFF_REQUIRED"
    assert (await _extract(world, mode="full_minus_interim")).status_code == 200


async def test_last_mode_and_preliminary_phase_not_asked(world, pg):
    pg.add(WorkpaperExtractionLog(
        id=uuid.uuid4(), project_id=LIAONING, workpaper_id=world["wp"], user_id=world["admin"],
        extraction_type="voucher_sampling", extraction_criteria={"phase": "final", "final_population_mode": "remaining"},
        total_matched=1, filled_count=1, fill_mode="append",
    ))
    await pg.flush()
    ctx = (await world["client"].get(f"/api/projects/{LIAONING}/sampling/phase-context",
                                     params={"wp_id": str(world["wp"])})).json()
    assert ctx["last_final_population_mode"] == "remaining" and ctx["default_final_population_mode"] == "remaining"

    await pg.execute(sa.text("UPDATE projects SET current_audit_phase = 'preliminary' WHERE id = :p"), {"p": LIAONING})
    ctx = (await world["client"].get(f"/api/projects/{LIAONING}/sampling/phase-context",
                                     params={"wp_id": str(world["wp"])})).json()
    assert ctx["requires_final_population_mode"] is False
    resp = await _extract(world, mode="remaining")  # 预审带了口径也不适用、不记
    assert resp.status_code == 200, resp.text
    assert "final_population" not in resp.json()["stats"]
    assert resp.json()["stats"]["population_count"] == 6135 - 1  # 预审：exclude_extracted 排本底稿已回填的那条


async def test_combined_written_on_fill_and_on_evaluation_save(world, pg):
    """口径 b：全年推断错报 = 预审样本实际错报 80 + 年审推断错报；错报上限 = 80 + 年审错报上限。"""
    from datetime import datetime
    from unittest.mock import AsyncMock, patch

    from app.models.workpaper_models import SamplingRecord

    log = WorkpaperExtractionLog.__table__
    crit = (await pg.execute(sa.select(log.c.extraction_criteria).where(log.c.id == world["prelim_id"]))).scalar_one()
    # 同一外层事务里 now() 恒等：把预审批次的时间挪早，合并评价只算年审批次之前的预审批次。
    # 用 ORM 更新（同步会话里那个对象）：合并评价按 ORM 读日志，Core 更新会让它读到会话里的旧值
    await pg.execute(sa.update(WorkpaperExtractionLog).where(WorkpaperExtractionLog.id == world["prelim_id"]).values(
        extraction_criteria={**crit, "evaluation": {"projected": "300.00", "upper_limit": "900.00",
                                                   "sample_error_total": "80.00"}},
        created_at=datetime(2025, 7, 15, 10, 0, 0)))
    h2 = (await pg.execute(sa.text(
        "SELECT voucher_date, voucher_type, voucher_no FROM tb_ledger WHERE dataset_id = :d AND is_deleted = false "
        "AND account_code LIKE :a AND voucher_date > :c ORDER BY voucher_date, voucher_type, voucher_no LIMIT 1"),
        {"d": world["ds"], "a": f"{ACCT}%", "c": CUTOFF})).first()
    lines = await _voucher_lines(pg, world["ds"], h2.voucher_date, h2.voucher_type, h2.voucher_no)
    line = next(r for r in lines if r["account_code"].startswith(ACCT))
    fp = dict(zip((r["id"] for r in lines), fingerprint_lines(lines)))[line["id"]]
    forged = {"projected": "1.00", "upper_limit": "1.00", "conclusion_message": "伪造"}
    body = {
        "workpaper_id": str(world["wp"]), "extraction_type": "voucher_sampling",
        "extraction_criteria": {
            "phase": "final", "final_population_mode": "full_minus_interim", "filled_line_fps": [fp],
            "filled_voucher_keys": [VoucherKey.from_row(line).to_str()],
            "filters": {"account_codes": [ACCT], "period_range": list(range(1, 13))},
            "evaluation": {"projected": "1000", "upper_limit": "2500", "tolerable_misstatement": "5000",
                           "conclusion_message": "年审结论", "combined": forged},
        },
        "total_matched": 6000, "filled_count": 1, "fill_mode": "append",
    }
    with patch("app.routers.cutoff_sampling.VersionTrailService.create_snapshot_fire_and_forget",
               new=AsyncMock(return_value=None)):
        resp = await world["client"].post(f"/api/projects/{LIAONING}/sampling/cutoff-fill", json=body)
    assert resp.status_code == 200, resp.text
    final_id, batch_id = uuid.UUID(resp.json()["id"]), uuid.UUID(resp.json()["batch_id"])

    async def stored() -> tuple[dict, str | None]:
        ev = (await pg.execute(sa.select(log.c.extraction_criteria).where(log.c.id == final_id))).scalar_one()["evaluation"]
        rec = (await pg.execute(sa.select(SamplingRecord.conclusion).where(SamplingRecord.batch_id == batch_id))).scalar_one()
        return ev, rec

    ev, conclusion = await stored()
    c = ev["combined"]
    assert (c["projected"], c["upper_limit"], c["conclusion_code"]) == ("1080.00", "2580.00", "acceptable")
    assert c["notes"] == ["另有预审手工挂凭 2 张：其核对结果不在抽样评价里，未计入合并"] and c["scope_consistent"] is True
    assert conclusion.startswith("年审结论\n【全年合并评价】全年合并（口径 b 全年扣除预审已检样本）") and "伪造" not in conclusion

    resp = await world["client"].post(f"/api/projects/{LIAONING}/sampling/voucher-evaluation", json={
        "workpaper_id": str(world["wp"]), "log_id": str(final_id),
        "evaluation": {"projected": "1500", "upper_limit": "3000", "tolerable_misstatement": "3000",
                       "conclusion_message": "年审结论（复核后）", "combined": forged}})
    assert resp.status_code == 200, resp.text
    ev, conclusion = await stored()
    c = ev["combined"]
    assert (c["projected"], c["upper_limit"], c["conclusion_code"]) == ("1580.00", "3080.00", "not_acceptable")
    assert "3080.00" in conclusion and "不可接受" in conclusion and conclusion.startswith("年审结论（复核后）\n")

    view = (await world["client"].get(f"/api/projects/{LIAONING}/sampling/phase-evaluation",
                                      params={"wp_id": str(world["wp"]), "log_id": str(final_id)})).json()
    assert view["available"] and view["combined"] == c and view["interim"][0]["log_id"] == str(world["prelim_id"])
