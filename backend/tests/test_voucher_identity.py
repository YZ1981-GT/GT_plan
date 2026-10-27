"""凭证身份单一实现（spec voucher-identity-writeback-and-audit-phase 任务 2，需求 1）。

- 跨语言样例 ``fixtures/voucher_identity_vectors.json``：后端与 ``utils/voucherIdentity.ts`` 读同一份，逐字相同。
- 真实凭证 ``fixtures/voucher_real_ledger_vectors.json``：同日同号不同凭证字是两张凭证；整张凭证内指纹不重复；
  摘要改动、输入顺序不改变指纹。
- SQLite 真 ORM 行：行值 IN / NOT IN 按凭证键取数；``resolve_line_fps`` 在账套重导（新数据集、新行 id、
  摘要改过）后解析到当前数据集的行，指定旧数据集时解析到旧行。
"""

from __future__ import annotations

import json
import random
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import TbLedger
from app.models.dataset_models import DatasetStatus, LedgerDataset
from app.services.voucher_identity import (
    SIDE_CREDIT,
    SIDE_DEBIT,
    SIDE_UNKNOWN,
    LineFingerprint,
    VoucherKey,
    amount_str,
    describe_line,
    fingerprint_lines,
    line_fingerprint,
    resolve_line_fps,
    side_of,
    signed_amount,
    voucher_key_sql,
    voucher_keys_in,
    voucher_keys_not_in,
)

FIXTURES = Path(__file__).parent / "fixtures"
VECTORS = json.loads((FIXTURES / "voucher_identity_vectors.json").read_text(encoding="utf-8"))
REAL: dict[str, list[dict]] = json.loads(
    (FIXTURES / "voucher_real_ledger_vectors.json").read_text(encoding="utf-8")
)["vouchers"]


# ─── 跨语言样例 ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("case", VECTORS["lines"], ids=lambda c: c["name"])
def test_line_vector(case):
    inp, exp = case["input"], case["expect"]
    vk = VoucherKey.from_row(inp)
    assert vk.to_str() == exp["vk"]
    assert side_of(inp["debit_amount"], inp["credit_amount"]) == exp["side"]
    vk2, acct, side, amount = describe_line(inp)
    assert (vk2, side, amount) == (vk, exp["side"], exp["amount"])
    assert line_fingerprint(vk, acct, side, amount, inp["occ"]) == exp["lfp"]
    assert VoucherKey.from_str(exp["vk"]) == vk
    assert LineFingerprint.parse(exp["lfp"]).to_str() == exp["lfp"]


@pytest.mark.parametrize("case", VECTORS["groups"], ids=lambda c: c["name"])
def test_group_vector(case):
    assert fingerprint_lines(case["lines"]) == case["expect"]


def test_vectors_cover_the_tricky_cases():
    """样例本身要覆盖三种借贷栏、空凭证字、红字、需要十进制四舍五入的金额。"""
    exp = [c["expect"] for c in VECTORS["lines"]]
    assert {e["side"] for e in exp} == {SIDE_DEBIT, SIDE_CREDIT, SIDE_UNKNOWN}
    assert any(json.loads(e["vk"])[3] == "" for e in exp)
    assert any(e["amount"].startswith("-") for e in exp)
    assert {"2.68", "-0.01"} <= {e["amount"] for e in exp}


# ─── 真实凭证 ───────────────────────────────────────────────────────────────────


def test_same_day_same_no_different_type_are_two_vouchers():
    fy = {VoucherKey.from_row(x) for x in REAL["fy0003_same_day_same_no"]}
    zz = {VoucherKey.from_row(x) for x in REAL["zz0003_same_day_same_no"]}
    assert len(fy) == len(zz) == 1
    assert fy != zz
    (k1,), (k2,) = fy, zz
    assert (k1.voucher_date, k1.voucher_no) == (k2.voucher_date, k2.voucher_no) == ("2025-01-07", "0003")
    merged = REAL["fy0003_same_day_same_no"] + REAL["zz0003_same_day_same_no"]
    fps = fingerprint_lines(merged)
    assert len(set(fps)) == len(merged)
    assert {LineFingerprint.parse(fp).vk for fp in fps} == {k1, k2}


@pytest.mark.parametrize("name", sorted(REAL))
def test_fingerprints_unique_within_voucher(name):
    lines = REAL[name]
    fps = fingerprint_lines(lines)
    assert len(set(fps)) == len(fps)
    vk = VoucherKey.from_row(lines[0])
    assert all(LineFingerprint.parse(fp).vk == vk for fp in fps)


@pytest.mark.parametrize("name", sorted(REAL))
def test_summary_change_keeps_fingerprints(name):
    """客户改摘要不改变分录身份：指纹集合不变；同组只有一条的分录指纹逐条不变。"""
    lines = REAL[name]
    before = fingerprint_lines(lines)
    changed = [{**x, "summary": f"客户改过的摘要{len(lines) - i}"} for i, x in enumerate(lines)]
    after = fingerprint_lines(changed)
    assert sorted(after) == sorted(before)
    singles = {g for g in (describe_line(x) for x in lines) if sum(describe_line(y) == g for y in lines) == 1}
    for x, b, a in zip(lines, before, after):
        if describe_line(x) in singles:
            assert a == b


def test_summary_change_keeps_fingerprints_many_to_many():
    lines = REAL["fy0012_many_to_many"]
    changed = [{**x, "summary": "付工资"} for x in lines]
    assert fingerprint_lines(changed) == fingerprint_lines(lines)


@pytest.mark.parametrize("name", sorted(REAL))
def test_input_order_does_not_matter(name):
    lines = REAL[name]
    expected = dict(zip((x["id"] for x in lines), fingerprint_lines(lines)))
    shuffled = list(lines)
    random.Random(7).shuffle(shuffled)
    assert dict(zip((x["id"] for x in shuffled), fingerprint_lines(shuffled))) == expected


def test_red_debit_stays_debit_and_double_filled_is_unknown():
    red = [x for x in REAL["red_blue_mixed"] if x["debit_amount"] and Decimal(x["debit_amount"]) < 0]
    assert red
    for x in red:
        _, _, side, amount = describe_line(x)
        assert side == SIDE_DEBIT and amount.startswith("-")
    for x in REAL["both_sides_filled"]:
        _, _, side, amount = describe_line(x)
        assert side == SIDE_UNKNOWN
        assert amount == amount_str(x["debit_amount"])


# ─── 解析与金额 ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, "0.00"), ("", "0.00"), ("-0.004", "0.00"), ("1e3", "1000.00"), (Decimal("2.675"), "2.68"),
     (2.675, "2.68"), ("-2.675", "-2.68"), (0, "0.00")],
)
def test_amount_str(value, expected):
    assert amount_str(value) == expected


def test_amount_str_rejects_garbage():
    with pytest.raises(ValueError, match="金额无法解析"):
        amount_str("abc")


def test_signed_amount_uses_the_side_column():
    assert signed_amount("100", None) == Decimal("100")
    assert signed_amount(None, "-5") == Decimal("-5")
    assert signed_amount("3", "3") == Decimal("3")
    assert signed_amount("0", "7", SIDE_UNKNOWN) == Decimal("7")


@pytest.mark.parametrize("text", ["bad", "[]", '["2025","001","2025-01-07","ZZ"]', '["2025","001","2025-01-07","ZZ",3]', "null"])
def test_voucher_key_from_str_rejects(text):
    with pytest.raises(ValueError, match="凭证键格式错误"):
        VoucherKey.from_str(text)


@pytest.mark.parametrize(
    "text",
    ["bad", '["2025","001","2025-01-07","ZZ","0003","1002","Z","1.00",0]',
     '["2025","001","2025-01-07","ZZ","0003","1002","D","1.00","0"]', '["2025","001","2025-01-07","ZZ","0003"]'],
)
def test_line_fingerprint_parse_rejects(text):
    with pytest.raises(ValueError, match="分录指纹格式错误"):
        LineFingerprint.parse(text)


def test_key_normalisation():
    a = VoucherKey.of(year=2025, company_code="001", voucher_date=date(2025, 1, 7), voucher_type=None, voucher_no="3")
    b = VoucherKey.of(year="2025", company_code=" 001", voucher_date=datetime(2025, 1, 7, 8, 30), voucher_type="", voucher_no="3 ")
    assert a == b and a.to_str() == '["2025","001","2025-01-07","","3"]'
    row = {"company_code": "001", "voucher_date": "2025-01-07", "voucher_type": None, "voucher_no": "3"}
    assert VoucherKey.from_row(row, year=2025) == a
    assert a.date_value == date(2025, 1, 7)
    assert a.sql_values() == ("001", date(2025, 1, 7), "", "3")


# ─── SQLite 真 ORM 行 ──────────────────────────────────────────────────────────

_PID = uuid.uuid4()
_YEAR = 2025


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda c: TbLedger.metadata.create_all(c, tables=[TbLedger.__table__, LedgerDataset.__table__])
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _amount(v):
    return Decimal(v) if v not in (None, "") else None


def _ledger_rows(lines, dataset_id, **override):
    out = []
    for x in lines:
        out.append(TbLedger(
            id=uuid.uuid4(), project_id=_PID, year=_YEAR, company_code=x["company_code"],
            voucher_date=date.fromisoformat(x["voucher_date"]), voucher_type=x["voucher_type"],
            voucher_no=x["voucher_no"], account_code=x["account_code"], account_name=x.get("account_name"),
            debit_amount=_amount(x["debit_amount"]), credit_amount=_amount(x["credit_amount"]),
            summary=x.get("summary"), dataset_id=dataset_id, **override,
        ))
    return out


def _synthetic(date_s, vtype, no, pairs):
    return [
        {"company_code": "001", "voucher_date": date_s, "voucher_type": vtype, "voucher_no": no,
         "account_code": acct, "debit_amount": d, "credit_amount": c, "summary": "S"}
        for acct, d, c in pairs
    ]


OTHER_MONTH = _synthetic("2025-02-07", "ZZ", "0003", [("1122", "50.00", None), ("6001", None, "50.00")])
NO_TYPE = _synthetic("2025-06-23", None, "0046", [("1002", "8.00", None), ("1122", None, "8.00")])


async def _seed(db, dataset_id):
    db.add(LedgerDataset(id=dataset_id, project_id=_PID, year=_YEAR, status=DatasetStatus.active,
                         source_type="import", activated_at=datetime(2026, 1, 1)))
    fy, zz = REAL["fy0003_same_day_same_no"], REAL["zz0003_same_day_same_no"]
    db.add_all(_ledger_rows(fy + zz, dataset_id) + _ledger_rows(OTHER_MONTH + NO_TYPE, dataset_id))
    await db.flush()


async def _fetch(db, *where):
    tbl = TbLedger.__table__
    stmt = sa.select(tbl).where(tbl.c.project_id == _PID, *where).order_by(tbl.c.voucher_date, tbl.c.account_code)
    return (await db.execute(stmt)).mappings().all()


def _key_of(name):
    return VoucherKey.from_row(REAL[name][0])


def test_voucher_key_sql_has_no_bind_params_for_pg_group_by():
    """SELECT 与 GROUP BY 各调一次时，PG 要求两处表达式逐字相同：凭证字的空串须是字面量。"""
    from sqlalchemy.dialects import postgresql

    tbl = TbLedger.__table__
    stmt = sa.select(*voucher_key_sql(tbl), sa.func.count()).group_by(*voucher_key_sql(tbl))
    compiled = stmt.compile(dialect=postgresql.asyncpg.dialect())
    assert compiled.params == {}
    assert str(compiled).count("coalesce(tb_ledger.voucher_type, '')") == 2


async def test_group_by_voucher_key_separates_voucher_types(db):
    await _seed(db, uuid.uuid4())
    tbl = TbLedger.__table__
    n_key = (await db.execute(sa.select(sa.func.count()).select_from(
        sa.select(*voucher_key_sql(tbl)).distinct().subquery()))).scalar_one()
    n_date_no = (await db.execute(sa.select(sa.func.count()).select_from(
        sa.select(tbl.c.voucher_date, tbl.c.voucher_no).distinct().subquery()))).scalar_one()
    assert (n_key, n_date_no) == (4, 3)


async def test_keys_in_selects_only_that_voucher(db):
    await _seed(db, uuid.uuid4())
    tbl = TbLedger.__table__
    fy = _key_of("fy0003_same_day_same_no")
    rows = await _fetch(db, voucher_keys_in(tbl, [fy]))
    assert len(rows) == len(REAL["fy0003_same_day_same_no"])
    assert {r["voucher_type"] for r in rows} == {"FY"}
    rest = await _fetch(db, voucher_keys_not_in(tbl, [fy]))
    assert len(rest) == len(REAL["zz0003_same_day_same_no"]) + len(OTHER_MONTH) + len(NO_TYPE)
    assert all(r["voucher_type"] != "FY" for r in rest)
    other_month = VoucherKey.from_row(OTHER_MONTH[0], year=_YEAR)
    assert {r["voucher_date"] for r in await _fetch(db, voucher_keys_in(tbl, [other_month]))} == {date(2025, 2, 7)}


async def test_empty_voucher_type_matches_null(db):
    await _seed(db, uuid.uuid4())
    tbl = TbLedger.__table__
    key = VoucherKey.from_row(NO_TYPE[0], year=_YEAR)
    assert key.voucher_type == ""
    rows = await _fetch(db, voucher_keys_in(tbl, [key]))
    assert len(rows) == len(NO_TYPE) and all(r["voucher_type"] is None for r in rows)


async def test_empty_key_lists(db):
    await _seed(db, uuid.uuid4())
    tbl = TbLedger.__table__
    assert await _fetch(db, voucher_keys_in(tbl, [])) == []
    assert len(await _fetch(db, voucher_keys_not_in(tbl, []))) == 9


async def test_resolve_line_fps_maps_to_current_rows(db):
    ds = uuid.uuid4()
    await _seed(db, ds)
    rows = await _fetch(db)
    fps = fingerprint_lines(rows)
    got = await resolve_line_fps(db, project_id=_PID, year=_YEAR, fps=fps)
    assert got == {fp: r["id"] for fp, r in zip(fps, rows)}


async def test_resolve_line_fps_after_reimport(db):
    """重导：新数据集、新行 id、客户改了摘要、行顺序不同 —— 指纹仍解析到新行；指定旧数据集解析到旧行。"""
    old_ds, new_ds = uuid.uuid4(), uuid.uuid4()
    await _seed(db, old_ds)
    old_rows = await _fetch(db)
    fps = fingerprint_lines(old_rows)
    copies = {}
    for r in reversed(old_rows):
        new = TbLedger(**{**{k: r[k] for k in r.keys() if k not in ("id", "dataset_id", "summary",
                                                                   "created_at", "updated_at")},
                          "id": uuid.uuid4(), "dataset_id": new_ds, "summary": f"重导后改的摘要 {r['account_code']}"})
        copies[r["id"]] = new.id
        db.add(new)
    await db.execute(sa.update(LedgerDataset).where(LedgerDataset.id == old_ds).values(status=DatasetStatus.superseded))
    db.add(LedgerDataset(id=new_ds, project_id=_PID, year=_YEAR, status=DatasetStatus.active,
                         source_type="import", activated_at=datetime(2026, 2, 1)))
    await db.flush()

    got = await resolve_line_fps(db, project_id=_PID, year=_YEAR, fps=fps)
    assert got == {fp: copies[r["id"]] for fp, r in zip(fps, old_rows)}
    pinned = await resolve_line_fps(db, project_id=_PID, year=_YEAR, fps=fps, force_dataset_id=old_ds)
    assert pinned == {fp: r["id"] for fp, r in zip(fps, old_rows)}


async def test_resolve_line_fps_skips_bad_and_missing(db):
    await _seed(db, uuid.uuid4())
    rows = await _fetch(db)
    fp = fingerprint_lines(rows)[0]
    missing = LineFingerprint.parse(fp)
    missing = LineFingerprint(missing.vk, missing.account_code, missing.side, "999999.99", 0).to_str()
    got = await resolve_line_fps(db, project_id=_PID, year=_YEAR, fps=[fp, "not-json", missing])
    assert set(got) == {fp}
    assert await resolve_line_fps(db, project_id=_PID, year=_YEAR, fps=[]) == {}


async def test_resolve_line_fps_identical_lines_get_distinct_rows(db):
    ds = uuid.uuid4()
    db.add(LedgerDataset(id=ds, project_id=_PID, year=_YEAR, status=DatasetStatus.active, source_type="import"))
    same = _synthetic("2025-03-01", "记", "9", [("1002", "10.00", None), ("1002", "10.00", None), ("6001", None, "20.00")])
    db.add_all(_ledger_rows(same, ds))
    await db.flush()
    rows = await _fetch(db)
    fps = fingerprint_lines(rows)
    assert len(set(fps)) == 3
    got = await resolve_line_fps(db, project_id=_PID, year=_YEAR, fps=fps)
    assert sorted(map(str, got.values())) == sorted(str(r["id"]) for r in rows)
