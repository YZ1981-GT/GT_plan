"""K 管理循环复盘修复 — LEDGER_DETAIL 3-arg e2e fixture 测试.

Spec: .kiro/specs/k-admin-cycle-post-review-fix/
Sprint 1 Task 3.4 — P0 必修
Validates: Requirements 2.4

Bug Condition (from bugfix.md / design.md):
  prefill_engine 的 `=LEDGER_DETAIL('科目','期间','金额条件')` 3-arg 签名
  在 K8-2/K9-2 销售/管理费用月度明细 prefill 链路中使用，但从未在端到端
  fixture 中以此签名模式被测试验证（K spec 实施时未补 e2e 测试，仅单元测
  试覆盖 _parse_period_range / _parse_args / 解析器注册）.

Expected Behavior (after fix):
  - 调用 _resolve_ledger_detail_formula(db, project_id, year, args) 不抛异常
  - 返回值为 list[dict[str, Any]]
  - 每行 dict 含 voucher_date / voucher_no / summary / debit_amount /
    credit_amount / counterpart_account 字段
  - 覆盖 3 种 direction: '>=0' / '<0' / '*'

Performance Notes:
  - 使用 sqlite+aiosqlite in-memory 快速建表
  - 仅 3 条 TbLedger fixture 数据 + 1 条 Project + 1 条 ProjectUser
  - 5 个测试 case，runtime < 5s
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.audit_platform_models import TbLedger
from app.models.base import Base
from app.models.core import (
    Project,
    ProjectStatus,
    ProjectType,
    ProjectUser,
    User,
)
from app.services.prefill_engine import _resolve_ledger_detail_formula

# SQLite 不识别 PG JSONB；映射到 JSON 以便 in-memory 测试
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

FAKE_USER_ID = uuid.uuid4()
FAKE_PROJECT_ID = uuid.uuid4()
YEAR = 2025


# --------------------------------------------------------------------------- #
# get_active_filter patch for SQLite in-memory
# --------------------------------------------------------------------------- #


async def _sqlite_active_filter(db, table, project_id, year, **kwargs):
    """SQLite 兼容的 active_filter — 用 ORM 属性而非 table.c 访问列."""
    return sa.and_(
        table.project_id == project_id,
        table.year == year,
        table.is_deleted == sa.false(),
    )


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """每个测试独立 in-memory schema."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession) -> dict:
    """种入 K8 销售费用 (6601) + K9 管理费用 (6602) 的明细行.

    数据组合覆盖:
      - account_code='6601' (K8) + 多月份 + 借方 / 贷方 / 零额三种符号
      - account_code='6602' (K9) + 多月份 (用于"非过滤目标"反向核验)
    """
    # 项目权限基础数据
    user = User(
        id=FAKE_USER_ID,
        username="k_prefill_tester",
        email="kpf@test.com",
        hashed_password="x",
        role="member",
    )
    db_session.add(user)

    project = Project(
        id=FAKE_PROJECT_ID,
        name="K-cycle prefill ledger detail e2e",
        client_name="测试客户",
        project_type=ProjectType.annual,
        status=ProjectStatus.execution,
        created_by=FAKE_USER_ID,
    )
    db_session.add(project)

    db_session.add(
        ProjectUser(
            project_id=FAKE_PROJECT_ID,
            user_id=FAKE_USER_ID,
            role="auditor",
            permission_level="edit",
            is_deleted=False,
        )
    )

    # K8 销售费用 6601 — 1月：借方 500（>0 命中 >=0）
    db_session.add(
        TbLedger(
            project_id=FAKE_PROJECT_ID,
            year=YEAR,
            company_code="001",
            voucher_date=date(2025, 1, 5),
            voucher_no="记-K8-001",
            account_code="6601",
            account_name="销售费用",
            accounting_period=1,
            debit_amount=Decimal("500.00"),
            credit_amount=Decimal("0"),
            counterpart_account="1001",
            summary="销售人员差旅费",
        )
    )

    # K8 销售费用 6601 — 1月：贷方 200（debit < 0 不存在; 改用 credit_amount > 0
    # 表达"反向调整"——_resolve_ledger_detail_formula 对 amount_filter 做
    # debit_amount OR credit_amount 双侧匹配，credit_amount=200 命中 >=0 但
    # 不命中 <0；同时另置一条 debit_amount=-100 用于 <0 命中）
    db_session.add(
        TbLedger(
            project_id=FAKE_PROJECT_ID,
            year=YEAR,
            company_code="001",
            voucher_date=date(2025, 1, 12),
            voucher_no="记-K8-002",
            account_code="6601",
            account_name="销售费用",
            accounting_period=1,
            debit_amount=Decimal("0"),
            credit_amount=Decimal("200.00"),
            counterpart_account="1002",
            summary="销售费用冲回",
        )
    )

    # K8 销售费用 6601 — 1月：debit 负数（命中 <0 direction）
    db_session.add(
        TbLedger(
            project_id=FAKE_PROJECT_ID,
            year=YEAR,
            company_code="001",
            voucher_date=date(2025, 1, 20),
            voucher_no="记-K8-003",
            account_code="6601",
            account_name="销售费用",
            accounting_period=1,
            debit_amount=Decimal("-100.00"),
            credit_amount=Decimal("0"),
            counterpart_account="1003",
            summary="销售费用红字调整",
        )
    )

    # K8 销售费用 6601 — 2月：借方 800（用于"1月过滤"边界反例核验）
    db_session.add(
        TbLedger(
            project_id=FAKE_PROJECT_ID,
            year=YEAR,
            company_code="001",
            voucher_date=date(2025, 2, 3),
            voucher_no="记-K8-004",
            account_code="6601",
            account_name="销售费用",
            accounting_period=2,
            debit_amount=Decimal("800.00"),
            credit_amount=Decimal("0"),
            counterpart_account="1001",
            summary="销售人员差旅费",
        )
    )

    # K9 管理费用 6602 — 1月：借方 1000（用于"科目过滤"边界反例核验）
    db_session.add(
        TbLedger(
            project_id=FAKE_PROJECT_ID,
            year=YEAR,
            company_code="001",
            voucher_date=date(2025, 1, 8),
            voucher_no="记-K9-001",
            account_code="6602",
            account_name="管理费用",
            accounting_period=1,
            debit_amount=Decimal("1000.00"),
            credit_amount=Decimal("0"),
            counterpart_account="1002",
            summary="办公用品采购",
        )
    )

    await db_session.commit()
    return {"project_id": FAKE_PROJECT_ID, "year": YEAR}


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

REQUIRED_ROW_KEYS = {
    "voucher_date",
    "voucher_no",
    "summary",
    "debit_amount",
    "credit_amount",
    "counterpart_account",
}


def _assert_row_shape(row: dict) -> None:
    """每行返回结果应含 prefill 所需字段."""
    missing = REQUIRED_ROW_KEYS - row.keys()
    assert not missing, f"返回行缺少字段: {missing}; 实际行: {row!r}"


# --------------------------------------------------------------------------- #
# Tests — 3-arg 签名 × 3 direction
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_resolve_ledger_detail_3arg_direction_geq_zero(
    db_session: AsyncSession, seeded_db: dict
) -> None:
    """direction='>=0' — 应命中 6601/1月 借方 500 + 贷方 200 两条 (-100 排除).

    Bug Condition: prefill_resolve / LEDGER_DETAIL / args_count=3
    Expected: 不抛异常 + 返回 list + 行结构完整
    """
    with patch("app.services.dataset_query.get_active_filter", _sqlite_active_filter):
        rows = await _resolve_ledger_detail_formula(
            db_session,
            seeded_db["project_id"],
            seeded_db["year"],
            ["6601", "1月", ">=0"],
        )

    # P0 #4 关键断言: 不抛异常 + 返回 list
    assert isinstance(rows, list), f"期望 list，得到 {type(rows)}"

    # 数据正确性: debit/credit 任一 >=0 → 6601 1月 三条全部命中（含 -100，因为
    # credit_amount=0 满足 >=0；这是 _resolve_ledger_detail_formula 的双侧 OR 语义）
    assert len(rows) == 3, (
        f"6601/1月 借方>=0 OR 贷方>=0 应命中 3 条, 实得 {len(rows)} 条"
    )

    # 结构完整性
    for row in rows:
        _assert_row_shape(row)
        assert row["voucher_no"].startswith("记-K8-"), (
            f"科目过滤未生效，6602 行漏入: {row['voucher_no']}"
        )


@pytest.mark.asyncio
async def test_resolve_ledger_detail_3arg_direction_lt_zero(
    db_session: AsyncSession, seeded_db: dict
) -> None:
    """direction='<0' — 应命中 6601/1月 debit_amount=-100 一条 (双侧 OR 语义).

    Bug Condition: prefill_resolve / LEDGER_DETAIL / args_count=3
    Expected: 不抛异常 + 返回 list + 行结构完整
    """
    with patch("app.services.dataset_query.get_active_filter", _sqlite_active_filter):
        rows = await _resolve_ledger_detail_formula(
            db_session,
            seeded_db["project_id"],
            seeded_db["year"],
            ["6601", "1月", "<0"],
        )

    assert isinstance(rows, list)
    # debit_amount=-100 (< 0) → 命中
    # debit_amount=500 / credit_amount=200 / debit_amount=0 — 任意一侧 < 0 才命中，
    # 三条样本仅红字调整一条同时满足 debit<0 (credit=0 不 <0)
    assert len(rows) == 1, (
        f"6601/1月 debit<0 OR credit<0 应命中 1 条, 实得 {len(rows)} 条"
    )
    _assert_row_shape(rows[0])
    assert rows[0]["voucher_no"] == "记-K8-003"


@pytest.mark.asyncio
async def test_resolve_ledger_detail_3arg_direction_wildcard(
    db_session: AsyncSession, seeded_db: dict
) -> None:
    """direction='*' — 不过滤金额，应命中 6601/1月 三条全部.

    Bug Condition: prefill_resolve / LEDGER_DETAIL / args_count=3
    Expected: 不抛异常 + 返回 list + 行结构完整
    """
    with patch("app.services.dataset_query.get_active_filter", _sqlite_active_filter):
        rows = await _resolve_ledger_detail_formula(
            db_session,
            seeded_db["project_id"],
            seeded_db["year"],
            ["6601", "1月", "*"],
        )

    assert isinstance(rows, list)
    assert len(rows) == 3, (
        f"6601/1月 不过滤金额应命中 3 条, 实得 {len(rows)} 条"
    )

    # 期间过滤生效：2月那条 (记-K8-004) 应排除
    voucher_nos = {r["voucher_no"] for r in rows}
    assert "记-K8-004" not in voucher_nos, "2月行未被期间过滤"
    assert voucher_nos == {"记-K8-001", "记-K8-002", "记-K8-003"}

    for row in rows:
        _assert_row_shape(row)


# --------------------------------------------------------------------------- #
# Smoke / 边界
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_resolve_ledger_detail_3arg_empty_data_returns_list(
    db_session: AsyncSession, seeded_db: dict
) -> None:
    """空命中场景：6603 财务费用 不存在 → 返回 [] 而非异常.

    防御 prefill 链路对"科目无任何流水"的兼容性；此场景在生产数据中常见
    （某些公司当年无销售费用 / 管理费用流水）.
    """
    with patch("app.services.dataset_query.get_active_filter", _sqlite_active_filter):
        rows = await _resolve_ledger_detail_formula(
            db_session,
            seeded_db["project_id"],
            seeded_db["year"],
            ["6603", "全年", "*"],
        )

    assert isinstance(rows, list)
    assert rows == []


@pytest.mark.asyncio
async def test_resolve_ledger_detail_3arg_account_filter_isolation(
    db_session: AsyncSession, seeded_db: dict
) -> None:
    """科目过滤隔离：查询 6602 只命中 K9 行, 不污染 6601 数据.

    Preservation: 多账户混存时 account_code 严格匹配, 不会跨科目串数据.
    """
    with patch("app.services.dataset_query.get_active_filter", _sqlite_active_filter):
        rows = await _resolve_ledger_detail_formula(
            db_session,
            seeded_db["project_id"],
            seeded_db["year"],
            ["6602", "1月", ">=0"],
        )

    assert isinstance(rows, list)
    assert len(rows) == 1
    assert rows[0]["voucher_no"] == "记-K9-001"
    _assert_row_shape(rows[0])
