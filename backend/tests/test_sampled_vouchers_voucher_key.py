"""挂凭登记表按凭证键去重（spec voucher-identity-writeback-and-audit-phase 任务 3，V210，发现 N3）。

- 静态：V210 / R210 的列、约束、两条唯一索引；ORM 三层一致。
- 单元：``register_sampled_vouchers`` 新格式（凭证键）按键成行、旧格式（只有号）按号去重、阶段取日志。
- pg_only（回滚事务）：同一批次两张同号不同日 / 同日同号不同凭证字的凭证都能登记（N3）；重复登记不增行；
  旧格式日志重复登记不增行（索引里日期为空折叠成哨兵值）；手工侧同日同号不同凭证字可分别挂；阶段约束。
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.workpaper_models import SampledVoucher
from app.services import sampling_registry_service as reg
from app.services.voucher_identity import VoucherKey

_MIG = Path(__file__).resolve().parents[1] / "migrations"
V210 = (_MIG / "V210__voucher_identity_sampled_vouchers.sql").read_text(encoding="utf-8")
R210 = (_MIG / "R210__rollback_voucher_identity_sampled_vouchers.sql").read_text(encoding="utf-8")
#: 四川物流（真实项目，只在回滚事务里写；sampled_vouchers.project_id 有外键）
PROJECT = uuid.UUID("f4b778ad-23b3-49ab-b3c8-ee62a5f82226")
COMPANY = "重庆医药集团四川物流有限公司"


def _create_index_sql(text: str, name: str) -> str:
    start = text.index(f"CREATE UNIQUE INDEX IF NOT EXISTS {name}")
    return text[start : text.index(";", start)]


def _vk(vdate: str, vtype: str, no: str) -> str:
    return VoucherKey.of(year=2025, company_code=COMPANY, voucher_date=vdate, voucher_type=vtype, voucher_no=no).to_str()


def _log(**criteria):
    return SimpleNamespace(
        project_id=PROJECT, workpaper_id=uuid.uuid4(), batch_id=uuid.uuid4(), user_id=None,
        extraction_criteria={"phase": "preliminary", "filters": {"account_codes": ["1221"]}, **criteria},
    )


# ─── 静态：迁移与 ORM ───────────────────────────────────────────────────────────


class TestMigrationText:
    def test_columns_and_constraint_idempotent(self):
        for col in ("company_code varchar", "voucher_type varchar(20)", "phase varchar(16)"):
            assert f"ADD COLUMN IF NOT EXISTS {col}" in V210
        assert "ck_sampled_vouchers_phase" in V210
        assert "CHECK (phase IS NULL OR phase IN ('preliminary', 'final'))" in V210
        for m in re.finditer(r"CREATE (UNIQUE )?INDEX", V210):
            assert V210[m.start() : m.start() + 60].count("IF NOT EXISTS") == 1

    def test_manual_index_keys_on_voucher_key_and_wp(self):
        idx = _create_index_sql(V210, "uq_sampled_voucher_manual_project_year_no")
        for expr in ("voucher_no", "(COALESCE(voucher_date, DATE '1900-01-01'))", "(COALESCE(company_code, ''))",
                     "(COALESCE(voucher_type, ''))", "COALESCE(working_paper_id"):
            assert expr in idx
        assert idx.rstrip().endswith("WHERE is_deleted = false AND batch_id IS NULL")

    def test_batch_index_keys_on_voucher_key(self):
        idx = _create_index_sql(V210, "uq_sampled_vouchers_batch")
        for expr in ("(COALESCE(voucher_date, DATE '1900-01-01'))", "(COALESCE(company_code, ''))",
                     "(COALESCE(voucher_type, ''))", "working_paper_id", "batch_id"):
            assert expr in idx
        # 谓词必须与 register_sampled_vouchers 的 index_where 相同，不能多出 batch_id 条件
        assert idx.rstrip().endswith("WHERE is_deleted = false")

    def test_rebuild_only_when_definition_lacks_voucher_type(self):
        assert V210.count("indexdef NOT LIKE '%voucher_type%'") == 2

    def test_rollback_restores_old_indexes_and_refuses_on_conflict(self):
        assert "RAISE EXCEPTION" in R210
        assert "ON sampled_vouchers (project_id, year, voucher_no, working_paper_id, batch_id)" in R210
        for col in ("phase", "voucher_type", "company_code"):
            assert f"DROP COLUMN IF EXISTS {col}" in R210
        # 先恢复索引再删列：删列会级联删掉表达式索引
        assert R210.index("CREATE UNIQUE INDEX uq_sampled_vouchers_batch") < R210.index("DROP COLUMN")


class TestOrmContract:
    @pytest.mark.parametrize(("name", "length"), [("company_code", None), ("voucher_type", 20), ("phase", 16)])
    def test_new_columns(self, name, length):
        col = SampledVoucher.__table__.c[name]
        assert isinstance(col.type, sa.String) and col.type.length == length
        assert col.nullable is True


# ─── 单元：登记行的构造 ─────────────────────────────────────────────────────────


class _CaptureDB:
    def __init__(self):
        self.stmts = []

    async def execute(self, stmt):
        self.stmts.append(stmt)
        return SimpleNamespace(rowcount=len(stmt._multi_values[0]) if stmt._multi_values else 1)

    async def flush(self):
        return None


def _rows_of(log) -> list[dict]:
    db = _CaptureDB()
    asyncio.run(reg.register_sampled_vouchers(db, log=log, year=2025))
    if not db.stmts:
        return []
    return [dict(r) for r in db.stmts[0]._multi_values[0]]


def _col(row: dict, name: str):
    for k, v in row.items():
        if getattr(k, "name", k) == name:
            return v
    raise KeyError(name)


def test_new_format_rows_carry_voucher_key_and_phase():
    log = _log(filled_voucher_keys=[_vk("2025-01-07", "FY", "0003"), _vk("2025-01-07", "ZZ", "0003"),
                                    _vk("2025-02-07", "FY", "0003"), _vk("2025-01-07", "FY", "0003")],
               filled_voucher_nos=["0003"])
    rows = _rows_of(log)
    got = [(_col(r, "voucher_date"), _col(r, "voucher_type"), _col(r, "voucher_no")) for r in rows]
    assert got == [(date(2025, 1, 7), "FY", "0003"), (date(2025, 1, 7), "ZZ", "0003"), (date(2025, 2, 7), "FY", "0003")]
    assert {_col(r, "company_code") for r in rows} == {COMPANY}
    assert {_col(r, "phase") for r in rows} == {"preliminary"}


def test_legacy_format_rows_dedupe_by_number():
    rows = _rows_of(_log(filled_voucher_nos=["0003", " 0003 ", "0004", ""], phase="interim"))
    assert [(_col(r, "voucher_no"), _col(r, "voucher_date"), _col(r, "voucher_type")) for r in rows] == [
        ("0003", None, None), ("0004", None, None)]
    assert {_col(r, "phase") for r in rows} == {None}


def test_bad_keys_fall_back_to_legacy_numbers():
    rows = _rows_of(_log(filled_voucher_keys=["bad", '["2025","001","","FY","1"]'], filled_voucher_nos=["9"]))
    assert [_col(r, "voucher_no") for r in rows] == ["9"]


def test_conflict_target_compiles_to_expression_index():
    log = _log(filled_voucher_keys=[_vk("2025-01-07", "FY", "0003")])
    db = _CaptureDB()
    asyncio.run(reg.register_sampled_vouchers(db, log=log, year=2025))
    sql = str(db.stmts[0].compile(dialect=postgresql.asyncpg.dialect()))
    assert ("ON CONFLICT (project_id, year, voucher_no, (COALESCE(voucher_date, DATE '1900-01-01')), "
            "(COALESCE(company_code, '')), (COALESCE(voucher_type, '')), working_paper_id, batch_id) "
            "WHERE is_deleted = false DO NOTHING") in sql


# ─── pg_only：真实索引语义（回滚事务）──────────────────────────────────────────


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


async def _count(db, log) -> int:
    tbl = SampledVoucher.__table__
    return (await db.execute(sa.select(sa.func.count()).where(tbl.c.batch_id == log.batch_id))).scalar_one()


@pytest.mark.pg_only
async def test_pg_same_batch_same_no_other_date_and_type_all_registered(pg):
    log = _log(filled_voucher_keys=[_vk("2025-01-07", "FY", "0003"), _vk("2025-01-07", "ZZ", "0003"),
                                    _vk("2025-02-07", "FY", "0003")])
    assert await reg.register_sampled_vouchers(pg, log=log, year=2025) == 3
    assert await reg.register_sampled_vouchers(pg, log=log, year=2025) == 0
    assert await _count(pg, log) == 3
    again = SimpleNamespace(**{**vars(log), "batch_id": uuid.uuid4()})
    assert await reg.register_sampled_vouchers(pg, log=again, year=2025) == 3


@pytest.mark.pg_only
async def test_pg_legacy_log_registers_once(pg):
    log = _log(filled_voucher_nos=["0003", "0004"])
    assert await reg.register_sampled_vouchers(pg, log=log, year=2025) == 2
    assert await reg.register_sampled_vouchers(pg, log=log, year=2025) == 0
    assert await _count(pg, log) == 2


@pytest.mark.pg_only
async def test_pg_manual_rows_split_by_voucher_type(pg):
    tbl = SampledVoucher.__table__
    wp = uuid.uuid4()
    base = {"project_id": PROJECT, "year": 2025, "voucher_no": "0003", "voucher_date": date(2025, 1, 7),
            "company_code": COMPANY, "working_paper_id": wp}
    await pg.execute(sa.insert(tbl).values(**base, voucher_type="FY"))
    await pg.execute(sa.insert(tbl).values(**base, voucher_type="ZZ"))
    with pytest.raises(sa.exc.IntegrityError, match="uq_sampled_voucher_manual_project_year_no"):
        async with pg.begin_nested():
            await pg.execute(sa.insert(tbl).values(**base, voucher_type="FY"))
    # 空凭证字与 NULL 按同一张参与去重
    await pg.execute(sa.insert(tbl).values(**{**base, "voucher_no": "0046"}, voucher_type=None))
    with pytest.raises(sa.exc.IntegrityError, match="uq_sampled_voucher_manual_project_year_no"):
        async with pg.begin_nested():
            await pg.execute(sa.insert(tbl).values(**{**base, "voucher_no": "0046"}, voucher_type=""))


@pytest.mark.pg_only
async def test_pg_phase_constraint(pg):
    tbl = SampledVoucher.__table__
    with pytest.raises(sa.exc.IntegrityError, match="ck_sampled_vouchers_phase"):
        async with pg.begin_nested():
            await pg.execute(sa.insert(tbl).values(project_id=PROJECT, year=2025, voucher_no="1", phase="interim"))
    await pg.execute(sa.insert(tbl).values(project_id=PROJECT, year=2025, voucher_no="1", phase="final"))


@pytest.mark.pg_only
async def test_pg_live_indexes_match_v210(pg):
    rows = dict((await pg.execute(sa.text(
        "SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'sampled_vouchers'"
    ))).all())
    for name in ("uq_sampled_voucher_manual_project_year_no", "uq_sampled_vouchers_batch"):
        for col in ("voucher_date", "company_code", "voucher_type"):
            assert col in rows[name], f"{name} 缺 {col}：本地库未应用 V210"
