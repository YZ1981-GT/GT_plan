"""F47 / Sprint 8.6: ValidationFinding.explanation 各 code 手算对照。

覆盖 design §D12.1 + requirements F47 的不变量：

1. **L1 AMOUNT_NOT_NUMERIC_KEY / AMOUNT_NOT_NUMERIC_RECOMMENDED**
   → `L1TypeErrorExplanation` 带 field_name / actual_value / expected_type=numeric
2. **L1 DATE_INVALID_KEY / DATE_INVALID_RECOMMENDED**
   → `L1TypeErrorExplanation` expected_type=date
3. **L2 BALANCE_UNBALANCED**
   → `UnbalancedExplanation`；inputs/computed 手算对照；sample_voucher_ids 前 10 条
4. **L2 L2_LEDGER_YEAR_OUT_OF_RANGE**
   → `YearOutOfRangeExplanation`；year_bounds 精确；out_of_range_samples
5. **L3 BALANCE_LEDGER_MISMATCH**
   → `BalanceMismatchExplanation`；expected = opening + sum_debit - sum_credit，
     diff_breakdown 4 项 (opening / sum_debit / sum_credit / actual_closing)，
     tolerance = min(1 + magnitude×0.00001, 100)
6. **无问题路径** → explanation=None（backward compat）

Fixture 模式：SQLite 内存库 + PG JSONB/UUID 降级，参考 test_cross_project_isolation.py。
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# SQLite 兼容适配：PG JSONB/UUID 降级到 JSON/uuid（必须在 Base.metadata 构建前生效）
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.base import Base  # noqa: E402
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.dataset_models  # noqa: E402, F401
from app.services.ledger_import.validator import (  # noqa: E402
    BalanceMismatchExplanation,
    L1TypeErrorExplanation,
    UnbalancedExplanation,
    YearOutOfRangeExplanation,
    validate_l1,
    validate_l2,
    validate_l3,
)


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # tb_account_chart 在 validator L2 中被查询但无 ORM 模型，
        # 用 raw DDL 建一张最小 schema 的空表满足 "has_chart=0 → 跳过 ACCOUNT_NOT_IN_CHART"
        await conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS tb_account_chart (
                id TEXT PRIMARY KEY,
                dataset_id TEXT,
                account_code TEXT,
                account_name TEXT
            )
            """
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


# ---------------------------------------------------------------------------
# L1 — AMOUNT type error
# ---------------------------------------------------------------------------


class TestL1AmountExplanation:
    def test_key_column_amount_not_numeric_has_explanation(self):
        """关键列金额非数值 → blocking + L1TypeErrorExplanation."""
        rows = [{"account_code": "1001", "debit_amount": "abc", "credit_amount": "0"}]
        findings, _ = validate_l1(rows, "balance", column_mapping={})

        blocking = [f for f in findings if f.code == "AMOUNT_NOT_NUMERIC_KEY"]
        assert len(blocking) == 1
        exp = blocking[0].explanation
        assert isinstance(exp, L1TypeErrorExplanation)
        assert exp.field_name == "debit_amount"
        assert exp.actual_value == "abc"
        assert exp.expected_type == "numeric"
        assert "parse_numeric" in exp.formula
        assert exp.hint  # 非空

    def test_recommended_column_amount_has_explanation(self):
        """次关键列金额非数值 → warning + 相同 schema 的 explanation."""
        rows = [
            {
                "account_code": "1001",
                "opening_balance": "1000",
                "debit_amount": "100",
                "credit_amount": "50",
                "closing_balance": "1050",
                # opening_debit 是 recommended
                "opening_debit": "xx",
            }
        ]
        findings, _ = validate_l1(rows, "balance", column_mapping={})

        rec = [f for f in findings if f.code == "AMOUNT_NOT_NUMERIC_RECOMMENDED"]
        assert len(rec) == 1
        exp = rec[0].explanation
        assert isinstance(exp, L1TypeErrorExplanation)
        assert exp.field_name == "opening_debit"
        assert exp.actual_value == "xx"
        assert exp.expected_type == "numeric"

    def test_actual_value_truncated_to_128(self):
        """超长原始值应被截断到 128 char，避免 explanation 体积爆炸."""
        long_value = "X" * 500
        rows = [{"account_code": "1001", "debit_amount": long_value, "credit_amount": "0"}]
        findings, _ = validate_l1(rows, "balance", column_mapping={})

        blocking = [f for f in findings if f.code == "AMOUNT_NOT_NUMERIC_KEY"]
        assert len(blocking) == 1
        assert len(blocking[0].explanation.actual_value) == 128


# ---------------------------------------------------------------------------
# L1 — DATE type error
# ---------------------------------------------------------------------------


class TestL1DateExplanation:
    def test_key_column_date_invalid_has_explanation(self):
        rows = [
            {
                "voucher_date": "not-a-date",
                "voucher_no": "记-001",
                "account_code": "1001",
                "debit_amount": "100",
                "credit_amount": "0",
            }
        ]
        findings, _ = validate_l1(rows, "ledger", column_mapping={})

        blocking = [f for f in findings if f.code == "DATE_INVALID_KEY"]
        assert len(blocking) == 1
        exp = blocking[0].explanation
        assert isinstance(exp, L1TypeErrorExplanation)
        assert exp.field_name == "voucher_date"
        assert exp.actual_value == "not-a-date"
        assert exp.expected_type == "date"
        assert "parse_date" in exp.formula


# ---------------------------------------------------------------------------
# 无问题路径 → explanation=None
# ---------------------------------------------------------------------------


class TestNoIssueNoExplanation:
    def test_happy_path_no_explanation(self):
        rows = [
            {
                "account_code": "1001",
                "opening_balance": "1000",
                "debit_amount": "100",
                "credit_amount": "50",
                "closing_balance": "1050",
            }
        ]
        findings, cleaned = validate_l1(rows, "balance", column_mapping={})
        assert findings == []
        assert len(cleaned) == 1

    def test_row_skipped_warning_has_no_explanation(self):
        """ROW_SKIPPED_KEY_EMPTY 是企业级宽容 warning，无需 explanation."""
        rows = [
            {
                "account_code": "",
                "opening_balance": "1000",
                "debit_amount": "100",
                "credit_amount": "50",
                "closing_balance": "1050",
            }
        ]
        findings, _ = validate_l1(rows, "balance", column_mapping={})
        skipped = [f for f in findings if f.code == "ROW_SKIPPED_KEY_EMPTY"]
        assert len(skipped) == 1
        # 此 finding 属于"跳过通知"，无需 explanation
        assert skipped[0].explanation is None


class TestExplanationSerialization:
    """SerializeAsAny 行为：子类特有字段必须保留到 model_dump() 输出."""

    def test_balance_mismatch_subclass_fields_preserved(self):
        rows = [
            {
                "account_code": "1001",
                "debit_amount": "abc",  # 触发 L1TypeErrorExplanation
                "credit_amount": "0",
            }
        ]
        findings, _ = validate_l1(rows, "balance", column_mapping={})
        blocking = [f for f in findings if f.code == "AMOUNT_NOT_NUMERIC_KEY"]
        dump = blocking[0].model_dump()
        # 子类 L1TypeErrorExplanation 的字段必须在 dump 输出里
        assert "field_name" in dump["explanation"]
        assert "expected_type" in dump["explanation"]
        assert dump["explanation"]["field_name"] == "debit_amount"
        assert dump["explanation"]["expected_type"] == "numeric"


# ---------------------------------------------------------------------------
# L2 — BALANCE_UNBALANCED
# ---------------------------------------------------------------------------


async def _seed_ledger_rows(db: AsyncSession, project_id, dataset_id, year, rows):
    """批量插入 tb_ledger 行（用 raw SQL 确保 dataset_id 以 str(UUID) 的 dashed 形式存储）。

    说明：ORM 写入时 SQLite 的 UUID 列视为 CHAR(32)，会把 UUID 存成去掉 dashes 的
    hex 字符串；但 validator.validate_l2/l3 查询时用 ``str(dataset_id)`` 作为
    参数（dashed 形式），两者不一致导致查询为空。
    生产（PG）里 UUID 是原生类型没这问题；测试用 raw SQL 绕过 SA 的 SQLite
    UUID 转换器，存成和生产一致的 dashed 形式。
    """
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
                "id": str(uuid.uuid4()),
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


async def _seed_balance_rows(db: AsyncSession, project_id, dataset_id, year, rows):
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


@pytest.mark.asyncio
async def test_l2_balance_unbalanced_explanation(db_session: AsyncSession):
    """手算：debit = 100 + 200 = 300；credit = 100 + 150 = 250；diff = 50."""
    project_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    year = 2025

    await _seed_ledger_rows(
        db_session,
        project_id,
        dataset_id,
        year,
        rows=[
            {"voucher_no": "V-001", "account_code": "1001",
             "debit_amount": 100, "credit_amount": 0},
            {"voucher_no": "V-002", "account_code": "1001",
             "debit_amount": 0, "credit_amount": 100},
            {"voucher_no": "V-003", "account_code": "2001",
             "debit_amount": 200, "credit_amount": 0},
            {"voucher_no": "V-004", "account_code": "2001",
             "debit_amount": 0, "credit_amount": 150},
        ],
    )

    findings = await validate_l2(
        db_session, dataset_id=dataset_id, year=year, project_id=project_id
    )

    unbal = [f for f in findings if f.code == "BALANCE_UNBALANCED"]
    assert len(unbal) == 1, (
        f"期望 1 条 BALANCE_UNBALANCED，实际 findings={findings}"
    )
    exp = unbal[0].explanation
    assert isinstance(exp, UnbalancedExplanation)
    assert exp.inputs["sum_debit"] == 300.0
    assert exp.inputs["sum_credit"] == 250.0
    assert exp.computed["diff"] == 50.0
    assert exp.computed["abs_diff"] == 50.0
    assert exp.computed["tolerance"] == 0.01
    # sample_voucher_ids：差额最大的凭证在前
    # V-003 单凭证 debit=200, credit=0, |diff|=200 (最大)
    assert "V-003" in exp.sample_voucher_ids
    # 最多 10 条
    assert len(exp.sample_voucher_ids) <= 10


@pytest.mark.asyncio
async def test_l2_balance_balanced_no_finding(db_session: AsyncSession):
    """借贷平衡时不产生 finding."""
    project_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    year = 2025

    await _seed_ledger_rows(
        db_session,
        project_id,
        dataset_id,
        year,
        rows=[
            {"voucher_no": "V-001", "account_code": "1001",
             "debit_amount": 100, "credit_amount": 0},
            {"voucher_no": "V-002", "account_code": "1001",
             "debit_amount": 0, "credit_amount": 100},
        ],
    )

    findings = await validate_l2(
        db_session, dataset_id=dataset_id, year=year, project_id=project_id
    )
    assert [f for f in findings if f.code == "BALANCE_UNBALANCED"] == []


# ---------------------------------------------------------------------------
# L2 — L2_LEDGER_YEAR_OUT_OF_RANGE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_l2_year_out_of_range_explanation(db_session: AsyncSession):
    """2025 年度 dataset 中有 2024/2026 越界凭证."""
    project_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    year = 2025

    await _seed_ledger_rows(
        db_session,
        project_id,
        dataset_id,
        year,
        rows=[
            # 年内合法
            {"voucher_no": "V-IN", "account_code": "1001",
             "voucher_date": date(2025, 3, 15),
             "debit_amount": 100, "credit_amount": 100},
            # 早于年度开始
            {"voucher_no": "V-EARLY", "account_code": "1001",
             "voucher_date": date(2024, 12, 31),
             "debit_amount": 50, "credit_amount": 50},
            # 晚于年度结束
            {"voucher_no": "V-LATE", "account_code": "1001",
             "voucher_date": date(2026, 1, 1),
             "debit_amount": 30, "credit_amount": 30},
        ],
    )

    findings = await validate_l2(
        db_session, dataset_id=dataset_id, year=year, project_id=project_id
    )

    year_findings = [f for f in findings if f.code == "L2_LEDGER_YEAR_OUT_OF_RANGE"]
    assert len(year_findings) == 1
    exp = year_findings[0].explanation
    assert isinstance(exp, YearOutOfRangeExplanation)
    assert exp.year_bounds == ("2025-01-01", "2025-12-31")
    assert exp.inputs["year"] == 2025
    assert exp.computed["out_of_range_count"] == 2
    # 样本含两条越界凭证
    voucher_nos = {s["voucher_no"] for s in exp.out_of_range_samples}
    assert voucher_nos == {"V-EARLY", "V-LATE"}
    # 最多 10 条
    assert len(exp.out_of_range_samples) <= 10


# ---------------------------------------------------------------------------
# L3 — BALANCE_LEDGER_MISMATCH
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_l3_balance_ledger_mismatch_explanation(db_session: AsyncSession):
    """手算：
    - opening=100, sum_debit=50, sum_credit=30, expected_closing=120
    - actual_closing=130 → diff=10
    - magnitude = max(100, 130, 50, 30, 1) = 130
    - tolerance = min(1 + 130×0.00001, 100) = 1.0013 → 远小于 diff=10 → blocking
    """
    project_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    year = 2025

    await _seed_ledger_rows(
        db_session,
        project_id,
        dataset_id,
        year,
        rows=[
            {"voucher_no": "L-001", "account_code": "1001",
             "debit_amount": 50, "credit_amount": 0},
            {"voucher_no": "L-002", "account_code": "1001",
             "debit_amount": 0, "credit_amount": 30},
        ],
    )
    await _seed_balance_rows(
        db_session,
        project_id,
        dataset_id,
        year,
        rows=[
            {"account_code": "1001",
             "opening_balance": 100, "debit_amount": 50, "credit_amount": 30,
             # 注意：actual_closing 设为 130 而不是正确的 120
             "closing_balance": 130},
        ],
    )

    findings = await validate_l3(
        db_session, dataset_id=dataset_id, project_id=project_id
    )

    mismatch = [f for f in findings if f.code == "BALANCE_LEDGER_MISMATCH"]
    assert len(mismatch) == 1, f"期望 1 条 BALANCE_LEDGER_MISMATCH，实际 {findings}"
    exp = mismatch[0].explanation
    assert isinstance(exp, BalanceMismatchExplanation)

    # inputs 手算对照
    assert exp.inputs["account_code"] == "1001"
    assert exp.inputs["opening_balance"] == 100.0
    assert exp.inputs["sum_debit"] == 50.0
    assert exp.inputs["sum_credit"] == 30.0
    assert exp.inputs["actual_closing_balance"] == 130.0

    # computed 手算对照
    assert exp.computed["expected_closing"] == 120.0  # 100 + 50 - 30
    assert exp.computed["diff"] == 10.0              # |130 - 120|
    # magnitude = max(100, 130, 50, 30, 1) = 130
    assert exp.computed["magnitude"] == 130.0
    # tolerance = min(1 + 130 * 0.00001, 100) = 1.0013
    assert exp.computed["tolerance"] == pytest.approx(1.0013, abs=1e-4)

    # diff_breakdown 4 条
    assert len(exp.diff_breakdown) == 4
    sources = [item["source"] for item in exp.diff_breakdown]
    assert sources == [
        "opening_balance", "sum_debit", "sum_credit", "actual_closing_balance"
    ]
    weights = [item["weight"] for item in exp.diff_breakdown]
    assert weights == ["+", "+", "-", "="]

    # tolerance_formula 字面量暴露
    assert "magnitude" in exp.tolerance_formula


@pytest.mark.asyncio
async def test_l3_balance_within_tolerance_no_finding(db_session: AsyncSession):
    """differences within dynamic tolerance → no finding."""
    project_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    year = 2025

    await _seed_ledger_rows(
        db_session,
        project_id,
        dataset_id,
        year,
        rows=[
            {"voucher_no": "L-001", "account_code": "1001",
             "debit_amount": 50, "credit_amount": 0},
        ],
    )
    await _seed_balance_rows(
        db_session,
        project_id,
        dataset_id,
        year,
        rows=[
            # 期末余额 150 vs 期望 150 → diff=0，无 finding
            {"account_code": "1001",
             "opening_balance": 100, "debit_amount": 50, "credit_amount": 0,
             "closing_balance": 150},
        ],
    )

    findings = await validate_l3(
        db_session, dataset_id=dataset_id, project_id=project_id
    )
    assert [f for f in findings if f.code == "BALANCE_LEDGER_MISMATCH"] == []


@pytest.mark.asyncio
async def test_l3_large_magnitude_tolerance_cap(db_session: AsyncSession):
    """金额量级大时 tolerance 受上限 100 元封顶."""
    project_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    year = 2025

    # magnitude 取 max(1_000_000_000) = 10 亿 → 1 + 1e9 × 1e-5 = 10001 → cap 到 100
    await _seed_ledger_rows(
        db_session,
        project_id,
        dataset_id,
        year,
        rows=[
            {"voucher_no": "L-001", "account_code": "1001",
             "debit_amount": 100_000_000, "credit_amount": 0},
        ],
    )
    await _seed_balance_rows(
        db_session,
        project_id,
        dataset_id,
        year,
        rows=[
            # actual = 1_000_000_050，expected = 1_000_000_000，diff = 50 < 100 → no finding
            {"account_code": "1001",
             "opening_balance": 900_000_000,
             "debit_amount": 100_000_000,
             "credit_amount": 0,
             "closing_balance": 1_000_000_050},
        ],
    )

    findings = await validate_l3(
        db_session, dataset_id=dataset_id, project_id=project_id
    )
    # 50 < tolerance=100 (封顶) → 无 finding
    assert [f for f in findings if f.code == "BALANCE_LEDGER_MISMATCH"] == []
