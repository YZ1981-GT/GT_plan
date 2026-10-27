"""凭证身份 × 真实账套（spec voucher-identity-writeback-and-audit-phase 任务 2，pg_only）。

只读 6 套真实账（2025 年度 active 数据集）；写入只在回滚事务里做。

1. SQL 凭证键（``voucher_key_sql``）与 Python 凭证键（``VoucherKey``）计数逐套相等，且每个凭证键各自借贷平衡
   （键不会把一张凭证拆开）；混凭证字的三套账按 (日期, 号) 计数少于按凭证键 —— 只按日期和号会把不同凭证并成一张。
2. 四川物流 2025-01-07「0003」是 FY 与 ZZ 两张各自平衡的凭证。
3. 账套重导：回滚事务里新建数据集、把 FY-0012 复制过去（新行 id、改过摘要）并激活，``resolve_line_fps``
   解析到新行；指定旧数据集时解析到旧行。

项目缺失或没有 active 数据集时跳过（数据依赖），不当作通过。
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.audit_platform_models import TbLedger
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.services.dataset_query import get_active_filter
from app.services.dataset_service import DatasetService
from app.services.voucher_identity import (
    VoucherKey,
    fingerprint_lines,
    resolve_line_fps,
    to_decimal,
    voucher_key_sql,
)

pytestmark = pytest.mark.pg_only

YEAR = 2025
PROJECTS = {
    "四川物流": "f4b778ad-23b3-49ab-b3c8-ee62a5f82226",
    "辽宁卫生": "37814426-a29e-4fc2-9313-a59d229bf7b0",
    "医疗器械": "5e193c68-f53c-4e95-8d03-5d9c996c402d",
    "华氏": "005a6f2d-cecd-4e30-bcbd-9fb01236c194",
    "和平药房": "5942c12e-65fb-4187-ace3-79d45a90cb53",
    "宜宾临港": "05ef8dd7-9c34-4ae4-b96b-5ba485be2e17",
}
#: 同日同号混了多种凭证字的账套（requirements F1）
MIXED_TYPES = {"四川物流", "辽宁卫生", "宜宾临港"}
TBL = TbLedger.__table__


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


async def _active(db: AsyncSession, name: str):
    pid = uuid.UUID(PROJECTS[name])
    ds = await DatasetService.get_active_dataset_id(db, pid, YEAR)
    if ds is None:
        pytest.skip(f"{name} 没有 {YEAR} 年 active 数据集")
    return pid, ds, await get_active_filter(db, TBL, pid, YEAR, strict=True)


async def _count_distinct(db: AsyncSession, cols, where) -> int:
    sub = sa.select(*cols).where(where).distinct().subquery()
    return (await db.execute(sa.select(sa.func.count()).select_from(sub))).scalar_one()


@pytest.mark.parametrize("name", sorted(PROJECTS))
async def test_sql_key_matches_python_key(pg, name):
    _, _, active = await _active(pg, name)
    n_key = await _count_distinct(pg, voucher_key_sql(TBL), active)
    raw = (await pg.execute(
        sa.select(TBL.c.company_code, TBL.c.voucher_date, TBL.c.voucher_type, TBL.c.voucher_no).where(active).distinct()
    )).all()
    keys = {VoucherKey.of(year=YEAR, company_code=c, voucher_date=d, voucher_type=t, voucher_no=n) for c, d, t, n in raw}
    assert n_key == len(keys) > 0

    unbalanced = (await pg.execute(
        sa.select(sa.func.count()).select_from(
            sa.select(*voucher_key_sql(TBL))
            .where(active)
            .group_by(*voucher_key_sql(TBL))
            .having(sa.func.sum(sa.func.coalesce(TBL.c.debit_amount, 0))
                    != sa.func.sum(sa.func.coalesce(TBL.c.credit_amount, 0)))
            .subquery()
        )
    )).scalar_one()
    assert unbalanced == 0, f"{name} 有 {unbalanced} 个凭证键借贷不平"

    n_date_no = await _count_distinct(pg, (TBL.c.company_code, TBL.c.voucher_date, TBL.c.voucher_no), active)
    n_no = await _count_distinct(pg, (TBL.c.voucher_no,), active)
    assert n_key >= n_date_no >= n_no
    if name in MIXED_TYPES:
        assert n_key > n_date_no, f"{name}：按 (日期, 号) 应少于按凭证键"


async def test_fy_zz_0003_are_two_balanced_vouchers(pg):
    _, _, active = await _active(pg, "四川物流")
    rows = (await pg.execute(
        sa.select(TBL).where(active, TBL.c.voucher_date == date(2025, 1, 7), TBL.c.voucher_no == "0003")
    )).mappings().all()
    groups: dict[VoucherKey, list] = defaultdict(list)
    for r in rows:
        groups[VoucherKey.from_row(r)].append(r)
    assert sorted(k.voucher_type for k in groups) == ["FY", "ZZ"]
    for key, lines in groups.items():
        debit = sum((to_decimal(x["debit_amount"]) for x in lines), Decimal("0"))
        credit = sum((to_decimal(x["credit_amount"]) for x in lines), Decimal("0"))
        assert debit == credit != 0, key
    fps = fingerprint_lines(rows)
    assert len(set(fps)) == len(rows)


async def test_resolve_line_fps_survives_reimport(pg):
    pid, old_ds, active = await _active(pg, "四川物流")
    rows = (await pg.execute(
        sa.select(TBL).where(
            active, TBL.c.voucher_date == date(2025, 1, 20), TBL.c.voucher_type == "FY", TBL.c.voucher_no == "0012"
        )
    )).mappings().all()
    assert len(rows) == 5
    fps = fingerprint_lines(rows)
    assert await resolve_line_fps(pg, project_id=pid, year=YEAR, fps=fps) == {fp: r["id"] for fp, r in zip(fps, rows)}

    new_ds = (await DatasetService.create_staged(pg, pid, YEAR, source_type="import")).id
    copies: dict[uuid.UUID, uuid.UUID] = {}
    payload = []
    for r in reversed(rows):
        copies[r["id"]] = new_id = uuid.uuid4()
        keep = {k: r[k] for k in r.keys() if k not in ("id", "dataset_id", "summary", "created_at", "updated_at")}
        payload.append({**keep, "id": new_id, "dataset_id": new_ds, "summary": "重导后客户改过的摘要"})
    await pg.execute(sa.insert(TBL), payload)
    lds = LedgerDataset.__table__
    await pg.execute(sa.update(lds).where(lds.c.id == old_ds).values(status=DatasetStatus.superseded))
    await pg.execute(
        sa.update(lds).where(lds.c.id == new_ds).values(status=DatasetStatus.active, activated_at=sa.func.now())
    )
    assert await DatasetService.get_active_dataset_id(pg, pid, YEAR) == new_ds

    got = await resolve_line_fps(pg, project_id=pid, year=YEAR, fps=fps)
    assert got == {fp: copies[r["id"]] for fp, r in zip(fps, rows)}
    pinned = await resolve_line_fps(pg, project_id=pid, year=YEAR, fps=fps, force_dataset_id=old_ds)
    assert pinned == {fp: r["id"] for fp, r in zip(fps, rows)}
