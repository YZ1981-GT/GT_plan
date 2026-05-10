"""F49 / Sprint 8.15: L3 ValidationFinding.location.drill_down 集成断言。

覆盖 design §D12.3 + requirements F49 的不变量：

1. L3 ``BALANCE_LEDGER_MISMATCH`` finding.location 带 drill_down
   - target == "tb_ledger"
   - filter.dataset_id == str(dataset_id)
   - filter.account_code == 差异最大的那个 account_code
   - sample_ids ≤ 3 条、元素是该 dataset 内该科目的 tb_ledger.id
   - expected_count == 该科目 tb_ledger 总行数
2. L3 ``AUX_ACCOUNT_MISMATCH`` finding.location 也带 drill_down
   - target ∈ {"tb_aux_ledger", "tb_aux_balance"}（优先 ledger）
   - 对只在 aux_balance 缺失的场景，target=="tb_aux_balance"
3. 无不一致时（happy path）不产生 L3 findings，因此也不产生 drill_down

SQLite 内存库 + PG JSONB/UUID 降级，沿用 test_finding_explanation.py 模板。
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# SQLite 兼容适配：PG JSONB/UUID 降级到 JSON/uuid
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.base import Base  # noqa: E402
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.dataset_models  # noqa: E402, F401
from app.services.ledger_import.validator import validate_l3  # noqa: E402

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


# ---------------------------------------------------------------------------
# 种子数据（与 test_finding_explanation.py 相同的 raw SQL 写法，
# 避开 SQLite UUID dashes/hex 差异）
# ---------------------------------------------------------------------------


async def _seed_ledger(db, project_id, dataset_id, year, rows):
    from sqlalchemy import text

    for r in rows:
        await db.execute(
            text(
                """
                INSERT INTO tb_ledger (
                    id, tenant_id, project_id, year, company_code,
                    voucher_date, voucher_no, account_code,
                    debit_amount, credit_amount,
                    dataset_id, is_deleted
                ) VALUES (
                    :id, 'default', :pid, :yr, '001',
                    :vdate, :vno, :acode,
                    :debit, :credit,
                    :did, 0
                )
                """
            ),
            {
                "id": r.get("id") or str(uuid.uuid4()),
                "pid": str(project_id),
                "yr": year,
                "vdate": (r.get("voucher_date") or date(year, 6, 1)).isoformat(),
                "vno": r["voucher_no"],
                "acode": r["account_code"],
                "debit": r.get("debit_amount"),
                "credit": r.get("credit_amount"),
                "did": str(dataset_id),
            },
        )
    await db.flush()


async def _seed_balance(db, project_id, dataset_id, year, rows):
    from sqlalchemy import text

    for r in rows:
        await db.execute(
            text(
                """
                INSERT INTO tb_balance (
                    id, tenant_id, project_id, year, company_code,
                    account_code,
                    opening_balance, debit_amount, credit_amount, closing_balance,
                    dataset_id, is_deleted
                ) VALUES (
                    :id, 'default', :pid, :yr, '001',
                    :acode,
                    :opening, :debit, :credit, :closing,
                    :did, 0
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "pid": str(project_id),
                "yr": year,
                "acode": r["account_code"],
                "opening": r.get("opening_balance"),
                "debit": r.get("debit_amount"),
                "credit": r.get("credit_amount"),
                "closing": r.get("closing_balance"),
                "did": str(dataset_id),
            },
        )
    await db.flush()


async def _seed_aux_balance(db, project_id, dataset_id, year, rows):
    from sqlalchemy import text

    for r in rows:
        await db.execute(
            text(
                """
                INSERT INTO tb_aux_balance (
                    id, tenant_id, project_id, year, company_code,
                    account_code, aux_type, aux_code,
                    opening_balance, closing_balance,
                    dataset_id, is_deleted
                ) VALUES (
                    :id, 'default', :pid, :yr, '001',
                    :acode, :atype, :acode2,
                    :opening, :closing,
                    :did, 0
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "pid": str(project_id),
                "yr": year,
                "acode": r["account_code"],
                "atype": r.get("aux_type") or "客户",
                "acode2": r.get("aux_code") or "C001",
                "opening": r.get("opening_balance") or 0,
                "closing": r.get("closing_balance") or 0,
                "did": str(dataset_id),
            },
        )
    await db.flush()


async def _seed_aux_ledger(db, project_id, dataset_id, year, rows):
    from sqlalchemy import text

    for r in rows:
        await db.execute(
            text(
                """
                INSERT INTO tb_aux_ledger (
                    id, tenant_id, project_id, year, company_code,
                    voucher_date, voucher_no, account_code,
                    aux_type, aux_code,
                    debit_amount, credit_amount,
                    dataset_id, is_deleted
                ) VALUES (
                    :id, 'default', :pid, :yr, '001',
                    :vdate, :vno, :acode,
                    :atype, :acode2,
                    :debit, :credit,
                    :did, 0
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "pid": str(project_id),
                "yr": year,
                "vdate": (r.get("voucher_date") or date(year, 6, 1)).isoformat(),
                "vno": r["voucher_no"],
                "acode": r["account_code"],
                "atype": r.get("aux_type") or "客户",
                "acode2": r.get("aux_code") or "C001",
                "debit": r.get("debit_amount") or 0,
                "credit": r.get("credit_amount") or 0,
                "did": str(dataset_id),
            },
        )
    await db.flush()


# ---------------------------------------------------------------------------
# L3 BALANCE_LEDGER_MISMATCH drill_down
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_balance_ledger_mismatch_drill_down_populated(db_session):
    """差异最大的科目 1001 期末应为 120，实际为 130，diff=10 → blocking + drill_down。"""
    project_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    year = 2025

    # 科目 1001：2 条 ledger 行，sum_debit=50, sum_credit=30
    await _seed_ledger(
        db_session, project_id, dataset_id, year,
        rows=[
            {"voucher_no": "L-001", "account_code": "1001",
             "debit_amount": 50, "credit_amount": 0},
            {"voucher_no": "L-002", "account_code": "1001",
             "debit_amount": 0, "credit_amount": 30},
        ],
    )
    # 余额表故意错录 closing=130 而不是正确的 120
    await _seed_balance(
        db_session, project_id, dataset_id, year,
        rows=[
            {"account_code": "1001",
             "opening_balance": 100, "debit_amount": 50,
             "credit_amount": 30, "closing_balance": 130},
        ],
    )

    findings = await validate_l3(
        db_session, dataset_id=dataset_id, project_id=project_id
    )

    mismatch = [f for f in findings if f.code == "BALANCE_LEDGER_MISMATCH"]
    assert len(mismatch) == 1
    loc = mismatch[0].location
    assert "drill_down" in loc, "L3 BALANCE_LEDGER_MISMATCH 必须带 drill_down"
    dd = loc["drill_down"]
    assert dd is not None
    assert dd["target"] == "tb_ledger"
    assert dd["filter"]["dataset_id"] == str(dataset_id)
    assert dd["filter"]["account_code"] == "1001"
    assert isinstance(dd["sample_ids"], list)
    assert 0 < len(dd["sample_ids"]) <= 3
    # 该科目 2 条 ledger 行 → expected_count=2
    assert dd["expected_count"] == 2


@pytest.mark.asyncio
async def test_drill_down_picks_largest_diff_account(db_session):
    """多个科目都不一致时，drill_down 应锁定差异最大的那个（sample_mismatch 逻辑）。"""
    project_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    year = 2025

    # 科目 1001：差异 10；科目 2001：差异 100（更大）
    await _seed_ledger(
        db_session, project_id, dataset_id, year,
        rows=[
            {"voucher_no": "L-001", "account_code": "1001",
             "debit_amount": 50, "credit_amount": 0},
            {"voucher_no": "L-002", "account_code": "2001",
             "debit_amount": 200, "credit_amount": 0},
        ],
    )
    await _seed_balance(
        db_session, project_id, dataset_id, year,
        rows=[
            # 1001: expected 150 (100+50-0)，实际 160 → diff 10
            {"account_code": "1001",
             "opening_balance": 100, "debit_amount": 50, "credit_amount": 0,
             "closing_balance": 160},
            # 2001: expected 200 (0+200-0)，实际 300 → diff 100 (最大)
            {"account_code": "2001",
             "opening_balance": 0, "debit_amount": 200, "credit_amount": 0,
             "closing_balance": 300},
        ],
    )

    findings = await validate_l3(
        db_session, dataset_id=dataset_id, project_id=project_id
    )

    mismatch = [f for f in findings if f.code == "BALANCE_LEDGER_MISMATCH"]
    assert len(mismatch) == 1
    dd = mismatch[0].location["drill_down"]
    # 差异最大的是 2001
    assert dd["filter"]["account_code"] == "2001"
    assert dd["expected_count"] == 1  # 该科目 1 条 ledger 行


@pytest.mark.asyncio
async def test_no_mismatch_no_finding_no_drill_down(db_session):
    """happy path：余额 = 序时累计，不产生 finding，也没有 drill_down。"""
    project_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    year = 2025

    await _seed_ledger(
        db_session, project_id, dataset_id, year,
        rows=[
            {"voucher_no": "L-001", "account_code": "1001",
             "debit_amount": 50, "credit_amount": 0},
        ],
    )
    await _seed_balance(
        db_session, project_id, dataset_id, year,
        rows=[
            {"account_code": "1001",
             "opening_balance": 100, "debit_amount": 50, "credit_amount": 0,
             "closing_balance": 150},  # 正确
        ],
    )

    findings = await validate_l3(
        db_session, dataset_id=dataset_id, project_id=project_id
    )
    assert [f for f in findings if f.code == "BALANCE_LEDGER_MISMATCH"] == []


# ---------------------------------------------------------------------------
# L3 AUX_ACCOUNT_MISMATCH drill_down
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aux_ledger_mismatch_drill_down_targets_aux_ledger(db_session):
    """aux_ledger 里 account_code='9999' 不在 tb_ledger → target=tb_aux_ledger."""
    project_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    year = 2025

    # tb_ledger 只有 1001
    await _seed_ledger(
        db_session, project_id, dataset_id, year,
        rows=[
            {"voucher_no": "V-001", "account_code": "1001",
             "debit_amount": 50, "credit_amount": 50},
        ],
    )
    # tb_balance 需要和 tb_ledger 一致（避免触发 BALANCE_LEDGER_MISMATCH 先跑）
    await _seed_balance(
        db_session, project_id, dataset_id, year,
        rows=[
            {"account_code": "1001",
             "opening_balance": 0, "debit_amount": 50, "credit_amount": 50,
             "closing_balance": 0},
        ],
    )
    # tb_aux_ledger 有 9999（不在 tb_ledger）
    await _seed_aux_ledger(
        db_session, project_id, dataset_id, year,
        rows=[
            {"voucher_no": "AV-001", "account_code": "9999",
             "debit_amount": 10, "credit_amount": 0,
             "aux_type": "客户", "aux_code": "C001"},
            {"voucher_no": "AV-002", "account_code": "9999",
             "debit_amount": 0, "credit_amount": 10,
             "aux_type": "客户", "aux_code": "C001"},
        ],
    )

    findings = await validate_l3(
        db_session, dataset_id=dataset_id, project_id=project_id
    )

    aux = [f for f in findings if f.code == "AUX_ACCOUNT_MISMATCH"]
    assert len(aux) == 1
    dd = aux[0].location["drill_down"]
    assert dd is not None
    assert dd["target"] == "tb_aux_ledger"
    assert dd["filter"]["account_code"] == "9999"
    assert dd["filter"]["dataset_id"] == str(dataset_id)
    assert dd["expected_count"] == 2
    assert 0 < len(dd["sample_ids"]) <= 3


@pytest.mark.asyncio
async def test_aux_balance_only_mismatch_targets_aux_balance(db_session):
    """missing 只在 aux_balance（不在 aux_ledger）→ target=tb_aux_balance."""
    project_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    year = 2025

    # tb_ledger + tb_balance: 1001 一致
    await _seed_ledger(
        db_session, project_id, dataset_id, year,
        rows=[
            {"voucher_no": "V-001", "account_code": "1001",
             "debit_amount": 0, "credit_amount": 0},
        ],
    )
    await _seed_balance(
        db_session, project_id, dataset_id, year,
        rows=[
            {"account_code": "1001",
             "opening_balance": 0, "debit_amount": 0, "credit_amount": 0,
             "closing_balance": 0},
        ],
    )
    # tb_aux_balance 里有 8888 (不在 tb_balance)；tb_aux_ledger 无 8888
    await _seed_aux_balance(
        db_session, project_id, dataset_id, year,
        rows=[
            {"account_code": "8888", "aux_type": "项目",
             "aux_code": "P001", "opening_balance": 100, "closing_balance": 100},
        ],
    )

    findings = await validate_l3(
        db_session, dataset_id=dataset_id, project_id=project_id
    )

    aux = [f for f in findings if f.code == "AUX_ACCOUNT_MISMATCH"]
    assert len(aux) == 1
    dd = aux[0].location["drill_down"]
    assert dd is not None
    assert dd["target"] == "tb_aux_balance"
    assert dd["filter"]["account_code"] == "8888"
    assert dd["expected_count"] == 1
