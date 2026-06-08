"""L3 BALANCE_LEDGER_MISMATCH 在 v2 符号约定下的方向归一回归测试。

复盘补漏（ledger-sign-convention-unify）：Task 2 把 converter 改为 v2
（category_natural_positive）后，tb_balance 的 closing/opening_balance 对贷方类
（负债/权益/收入）存自然正数，而 tb_ledger 发生额仍是借正贷负原始口径。
validate_l3 的恒等式 closing = opening + 发生额 必须把发生额归一到科目自然方向
（贷方类用 credit-debit），否则贷方类全部误报 BALANCE_LEDGER_MISMATCH。

本测试守护：
1. v2 贷方类（负债）账套平衡时不误报（核心修复）。
2. v2 贷方类真不平衡时仍能报出。
3. v1 旧数据（借正贷负）保持原 debit-credit 公式，行为不变。

Validates: ledger-sign-convention-unify 需求 5、6（连带 L3 校验口径）
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base
import app.models.audit_platform_models  # noqa: F401  注册 ORM
import app.models.dataset_models  # noqa: F401
from app.services.ledger_import.validator import validate_l3

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


async def _seed_ledger(db, project_id, dataset_id, year, rows):
    for r in rows:
        await db.execute(
            text("""
                INSERT INTO tb_ledger (
                    id, tenant_id, project_id, year, company_code,
                    voucher_date, voucher_no, account_code,
                    debit_amount, credit_amount, dataset_id, is_deleted
                ) VALUES (
                    :id, 'default', :pid, :yr, '001',
                    :vdate, :vno, :acode, :debit, :credit, :did, 0
                )
            """),
            {
                "id": str(uuid.uuid4()),
                "pid": str(project_id),
                "yr": year,
                "vdate": (r.get("voucher_date") or date(year, 6, 1)).isoformat(),
                "vno": r["voucher_no"],
                "acode": r["account_code"],
                "debit": r.get("debit_amount") or 0,
                "credit": r.get("credit_amount") or 0,
                "did": str(dataset_id),
            },
        )
    await db.flush()


async def _seed_balance(db, project_id, dataset_id, year, rows):
    for r in rows:
        await db.execute(
            text("""
                INSERT INTO tb_balance (
                    id, tenant_id, project_id, year, company_code, account_code,
                    opening_balance, debit_amount, credit_amount, closing_balance,
                    closing_direction, sign_convention_version,
                    dataset_id, is_deleted
                ) VALUES (
                    :id, 'default', :pid, :yr, '001', :acode,
                    :opening, :debit, :credit, :closing,
                    :cdir, :scv, :did, 0
                )
            """),
            {
                "id": str(uuid.uuid4()),
                "pid": str(project_id),
                "yr": year,
                "acode": r["account_code"],
                "opening": r.get("opening_balance") or 0,
                "debit": r.get("debit_amount") or 0,
                "credit": r.get("credit_amount") or 0,
                "closing": r.get("closing_balance") or 0,
                "cdir": r.get("closing_direction"),
                "scv": r.get("sign_convention_version"),
                "did": str(dataset_id),
            },
        )
    await db.flush()


def _mismatches(findings):
    return [f for f in findings if f.code == "BALANCE_LEDGER_MISMATCH"]


@pytest.mark.asyncio
async def test_v2_credit_class_balanced_no_false_positive(db_session: AsyncSession):
    """v2 负债类平衡账套：期初 100000(+) 本期贷记增加 20000 → 期末 120000(+)。

    自然方向净额 = credit(20000) - debit(0) = +20000；
    expected = 100000 + 20000 = 120000 == closing → 不报 mismatch。
    旧（错误）公式会算 100000 + (0-20000) = 80000，误报差 40000。
    """
    pid, did, year = uuid.uuid4(), uuid.uuid4(), 2025
    await _seed_balance(db_session, pid, did, year, [{
        "account_code": "2202",
        "opening_balance": 100000,
        "closing_balance": 120000,
        "closing_direction": "credit",
        "sign_convention_version": "v2_category_natural_positive",
    }])
    await _seed_ledger(db_session, pid, did, year, [
        {"voucher_no": "V1", "account_code": "2202", "credit_amount": 20000},
    ])

    findings = await validate_l3(db_session, dataset_id=did, project_id=pid)
    assert _mismatches(findings) == []


@pytest.mark.asyncio
async def test_v2_credit_class_truly_unbalanced_still_flags(db_session: AsyncSession):
    """v2 负债类真不平衡：期末 120000 但发生额仅贷记 5000 → expected 105000，差 15000 → 报。"""
    pid, did, year = uuid.uuid4(), uuid.uuid4(), 2025
    await _seed_balance(db_session, pid, did, year, [{
        "account_code": "2202",
        "opening_balance": 100000,
        "closing_balance": 120000,
        "closing_direction": "credit",
        "sign_convention_version": "v2_category_natural_positive",
    }])
    await _seed_ledger(db_session, pid, did, year, [
        {"voucher_no": "V1", "account_code": "2202", "credit_amount": 5000},
    ])

    findings = await validate_l3(db_session, dataset_id=did, project_id=pid)
    mm = _mismatches(findings)
    assert len(mm) == 1


@pytest.mark.asyncio
async def test_v2_debit_class_balanced_no_false_positive(db_session: AsyncSession):
    """v2 资产类（借方）平衡：期初 80000 借记 20000 → 期末 100000，正常公式不变。"""
    pid, did, year = uuid.uuid4(), uuid.uuid4(), 2025
    await _seed_balance(db_session, pid, did, year, [{
        "account_code": "1001",
        "opening_balance": 80000,
        "closing_balance": 100000,
        "closing_direction": "debit",
        "sign_convention_version": "v2_category_natural_positive",
    }])
    await _seed_ledger(db_session, pid, did, year, [
        {"voucher_no": "V1", "account_code": "1001", "debit_amount": 20000},
    ])

    findings = await validate_l3(db_session, dataset_id=did, project_id=pid)
    assert _mismatches(findings) == []


@pytest.mark.asyncio
async def test_v1_legacy_keeps_debit_minus_credit(db_session: AsyncSession):
    """v1 旧数据（无 version / 借正贷负）：负债贷方余额存负数，保持原 debit-credit 公式。

    期初 -100000，本期贷记 20000 → expected = -100000 + (0 - 20000) = -120000 == closing。
    """
    pid, did, year = uuid.uuid4(), uuid.uuid4(), 2025
    await _seed_balance(db_session, pid, did, year, [{
        "account_code": "2202",
        "opening_balance": -100000,
        "closing_balance": -120000,
        "closing_direction": None,
        "sign_convention_version": None,
    }])
    await _seed_ledger(db_session, pid, did, year, [
        {"voucher_no": "V1", "account_code": "2202", "credit_amount": 20000},
    ])

    findings = await validate_l3(db_session, dataset_id=did, project_id=pid)
    assert _mismatches(findings) == []
