"""预审样本存续核对 × 真 PostgreSQL（任务 17，需求 8，pg_only）。

只在【测试】凭证身份走查项目 ``ca8da212`` 的回滚事务里造一版临时 active 账套与四条元数据：

- U-OLD：当前账套保留同一指纹 → 未变；
- M-OLD：凭证键仍在、金额由 200 改 201 → 分录已改；
- R-OLD：原凭证键不在，同日期 / 科目 / 借贷栏 / 金额改号为 R-NEW → 疑似重编号；
- D-OLD：前三步都不命中 → 凭证已删除。

真端点 POST → GET status → PATCH 确认 → GET voucher-coverage；路由内部 commit 只提交到外层事务的 SAVEPOINT，
fixture 最后整体 rollback，不在共享库留下账套、分录或核对汇总。
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.audit_platform_models import TbLedger
from app.models.core import Project
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.services.dataset_service import DatasetService
from app.services.voucher_identity import VoucherKey, line_fingerprint

pytestmark = pytest.mark.pg_only

PROJECT = uuid.UUID("ca8da212-8a0f-48b6-bd82-06660bd94380")
YEAR = 2025
COMPANY = "T17-PG"


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


def _vk(no: str, day: int) -> VoucherKey:
    return VoucherKey.of(year=YEAR, company_code=COMPANY, voucher_date=date(YEAR, 12, day), voucher_type="SV", voucher_no=no)


def _input(no: str, day: int, account: str, side: str, amount: str) -> dict:
    fp = line_fingerprint(_vk(no, day), account, side, amount, 0)
    return {"row_key": fp, "lfp": fp, "vk": _vk(no, day).to_str(), "account_code": account, "side": side, "amount": amount}


def _line(dataset_id, no: str, day: int, account: str, side: str, amount: str) -> dict:
    return {
        "id": uuid.uuid4(), "project_id": PROJECT, "year": YEAR, "company_code": COMPANY,
        "voucher_date": date(YEAR, 12, day), "voucher_type": "SV", "voucher_no": no,
        "account_code": account, "account_name": f"任务17 {account}",
        "debit_amount": amount if side == "D" else None, "credit_amount": amount if side == "C" else None,
        "summary": f"任务17 {no}", "dataset_id": dataset_id, "is_deleted": False,
    }


@pytest.fixture
async def world(pg):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from app.core.database import get_db
    from app.deps import get_current_user
    from app.routers import sampling_phase, voucher_sampling

    project = (await pg.execute(sa.text("SELECT is_deleted FROM projects WHERE id=:p"), {"p": PROJECT})).first()
    admin = (await pg.execute(sa.text("SELECT id FROM users WHERE username='admin'"))).scalar()
    wp = (await pg.execute(sa.text(
        "SELECT wp.id FROM working_paper wp JOIN wp_index wi ON wi.id=wp.wp_index_id "
        "WHERE wp.project_id=:p AND wp.is_deleted=false AND wi.wp_code='J1' LIMIT 1"), {"p": PROJECT})).scalar()
    old_dataset = await DatasetService.get_active_dataset_id(pg, PROJECT, YEAR)
    if project is None or project.is_deleted or admin is None or wp is None or old_dataset is None:
        pytest.skip("【测试】凭证身份走查项目 / J1 底稿 / admin / active 账套不可用")

    new_dataset = uuid.uuid4()
    pg.add(LedgerDataset(
        id=new_dataset, project_id=PROJECT, year=YEAR, status=DatasetStatus.staged,
        source_type="import", previous_dataset_id=old_dataset,
        source_summary={"test": "interim-survival-pg"},
    ))
    await pg.flush()
    await pg.execute(sa.update(LedgerDataset).where(LedgerDataset.id == old_dataset).values(status=DatasetStatus.superseded))
    await pg.execute(sa.update(LedgerDataset).where(LedgerDataset.id == new_dataset).values(
        status=DatasetStatus.active, activated_at=sa.func.now()))
    await pg.execute(sa.update(Project).where(Project.id == PROJECT).values(current_audit_phase="final"))
    await pg.execute(sa.insert(TbLedger.__table__).values([
        _line(new_dataset, "U-OLD", 20, "T1701", "D", "100.00"),
        _line(new_dataset, "M-OLD", 21, "T1702", "C", "201.00"),
        _line(new_dataset, "M-CAND", 21, "T1702", "C", "200.00"),
        _line(new_dataset, "R-NEW", 22, "T1703", "D", "300.00"),
        _line(new_dataset, "R-WRONG-SIDE", 22, "T1703", "C", "300.00"),
        _line(new_dataset, "R-WRONG-AMOUNT", 22, "T1703", "D", "301.00"),
    ]))
    await pg.flush()
    assert await DatasetService.get_active_dataset_id(pg, PROJECT, YEAR) == new_dataset

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
    app.include_router(sampling_phase.router)
    app.include_router(voucher_sampling.router)
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_current_user] = _user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield {"client": client, "wp": wp, "dataset": new_dataset, "admin": admin}


async def test_four_statuses_summary_ack_and_project_coverage(world, pg):
    rows = [
        _input("U-OLD", 20, "T1701", "D", "100.00"),
        _input("M-OLD", 21, "T1702", "C", "200.00"),
        _input("R-OLD", 22, "T1703", "D", "300.00"),
        _input("D-OLD", 23, "T1704", "C", "400.00"),
    ]
    client, wp, dataset = world["client"], world["wp"], world["dataset"]
    resp = await client.post(f"/api/projects/{PROJECT}/sampling/interim-survival", json={
        "wp_id": str(wp), "year": YEAR, "rows": rows,
    })
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert [r["status"] for r in out["results"]] == ["unchanged", "modified", "renumbered", "deleted"]
    assert (out["total"], out["unchanged"], out["modified"], out["renumbered"], out["deleted"], out["unacked"]) == (4, 1, 1, 1, 1, 3)
    assert out["dataset_id"] == str(dataset)
    assert out["results"][1]["current_voucher"]["lines"][0]["amount"] == "201.00"
    assert [c["voucher_no"] for c in out["results"][2]["candidates"]] == ["R-NEW"]

    # 三层一致 + 真 upsert：V212 表列、约束、ORM 写入都实际经过。
    row = (await pg.execute(sa.text(
        "SELECT total, unchanged, changed, renumbered, deleted, unacked FROM interim_survival_checks WHERE id=:i"),
        {"i": uuid.UUID(out["check_id"])})).one()
    assert tuple(row) == (4, 1, 1, 1, 1, 3)

    status = await client.get(f"/api/projects/{PROJECT}/sampling/interim-survival/status",
                              params={"wp_id": str(wp), "year": YEAR})
    assert status.status_code == 200 and status.json()["check"]["unacked"] == 3
    ack = await client.patch(f"/api/projects/{PROJECT}/sampling/interim-survival/{out['check_id']}", json={
        "wp_id": str(wp), "dataset_id": str(dataset), "unacked": 2,
    })
    assert ack.status_code == 200 and ack.json()["unacked"] == 2 and ack.json()["ack_by"] == str(world["admin"])

    coverage = await client.get(f"/api/projects/{PROJECT}/sampling/voucher-coverage", params={"year": YEAR})
    assert coverage.status_code == 200, coverage.text
    item = next(x for x in coverage.json()["by_workpaper"] if x["working_paper_id"] == str(wp))
    assert item["wp_code"] == "J1" and item["interim_survival_unacked"] == 2
    assert item["interim_survival_counts"] == {"total": 4, "unchanged": 1, "modified": 1, "renumbered": 1, "deleted": 1}

    # 重跑同版且把 modified 标为已确认：同一汇总 id upsert，不新增第二行；其余两条仍未确认。
    rows[1].update({"previous_dataset_id": str(dataset), "previous_status": "modified", "acknowledged": True})
    again = await client.post(f"/api/projects/{PROJECT}/sampling/interim-survival", json={
        "wp_id": str(wp), "year": YEAR, "rows": rows,
    })
    assert again.status_code == 200 and again.json()["check_id"] == out["check_id"] and again.json()["unacked"] == 2
    assert (await pg.execute(sa.text(
        "SELECT count(*) FROM interim_survival_checks WHERE working_paper_id=:w AND dataset_id=:d"),
        {"w": wp, "d": dataset})).scalar_one() == 1
