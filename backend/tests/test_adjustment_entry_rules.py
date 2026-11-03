"""调整分录录入规则、编号与科目下拉（spec adjustment-hall-entry-review-closure 任务 1、2）。"""
from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import (
    AccountCategory,
    AccountChart,
    AccountDirection,
    AccountSource,
    AdjustmentType,
    ReportLineMapping,
    ReportLineMappingType,
    ReportType,
    TrialBalance,
)
from app.models.audit_platform_schemas import AdjustmentCreate, AdjustmentLineItem, AdjustmentUpdate
from app.models.base import Base
from app.models.core import Project, ProjectStatus, ProjectType
from app.services.adjustment_entry_rules import (
    entry_rule_errors,
    next_free_number,
    normalize_adjustment_no,
    to_cents,
)
from app.services.adjustment_service import AdjustmentService

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
USER_ID = uuid.uuid4()


def _li(code="1001", d="0", c="0"):
    return SimpleNamespace(standard_account_code=code, debit_amount=Decimal(d), credit_amount=Decimal(c))


# ── 纯规则 ────────────────────────────────────────────────────────────────


def test_valid_entry_has_no_errors():
    assert entry_rule_errors([_li("1001", d="100"), _li("6001", c="100")]) == []


@pytest.mark.parametrize("lines, expected", [
    ([_li("1001", d="-100"), _li("6001", c="-100")], "金额不能为负数"),
    ([_li("1001", d="100", c="100"), _li("6001", c="0")], "借方和贷方不能同时填写"),
    ([_li("1001", d="100"), _li("6001"), _li("1002", c="100")], "第 2 行借贷金额均为 0"),
    ([_li("", d="100"), _li("6001", c="100")], "第 1 行未选择科目"),
    ([_li("1001", d="100"), _li("6001", c="60")], "借贷不平衡"),
    ([_li("1001"), _li("6001")], "借贷金额均为 0"),
    ([], "至少需要一行明细"),
])
def test_rule_violations_are_reported_in_chinese(lines, expected):
    errors = entry_rule_errors(lines)
    assert any(expected in e for e in errors), errors


def test_zero_total_is_rejected_even_when_balanced():
    errors = entry_rule_errors([_li("1001"), _li("6001")])
    assert "借贷合计为 0，没有需要调整的金额" in errors


def test_amounts_compare_after_rounding_to_cents():
    # 0.1 + 0.2 的浮点尾差不再导致「不平衡」
    lines = [_li("1001", d=str(0.1 + 0.2)), _li("6001", c="0.30")]
    assert entry_rule_errors(lines) == []
    assert to_cents("1,234.565".replace(",", "")) == Decimal("1234.57")
    with pytest.raises(ValueError, match="金额无法识别"):
        to_cents("十元")


def test_custom_row_labels_are_used():
    errors = entry_rule_errors([_li("", d="10"), _li("6001", c="10")], row_labels=["第 7 行", "第 8 行"])
    assert errors == ["第 7 行未选择科目"]


def test_adjustment_no_normalization_and_next_free_number():
    assert normalize_adjustment_no("  AJE-内部-01 ") == "AJE-内部-01"
    assert normalize_adjustment_no("   ") is None
    with pytest.raises(ValueError, match="超过"):
        normalize_adjustment_no("X" * 31)
    assert next_free_number("AJE", 3, {"AJE-003", "AJE-004"}) == "AJE-005"
    assert next_free_number("RJE", 0, set()) == "RJE-001"


# ── 服务层（SQLite）────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)() as session:
        yield session


@pytest_asyncio.fixture
async def pid(db: AsyncSession):
    project = Project(
        id=uuid.uuid4(), name="录入规则测试_2025", client_name="录入规则测试",
        project_type=ProjectType.annual, status=ProjectStatus.planning, created_by=USER_ID,
    )
    db.add(project)
    await db.flush()
    for code, name, cat in [("1001", "库存现金", AccountCategory.asset), ("6001", "主营业务收入", AccountCategory.revenue),
                            ("1231", "坏账准备", AccountCategory.asset)]:
        db.add(AccountChart(project_id=project.id, account_code=code, account_name=name, direction=AccountDirection.debit,
                            level=1, category=cat, source=AccountSource.standard))
    # 只有 1001 有已确认映射；1231 / 6001 没有 —— 原下拉只会返回 1001
    db.add(ReportLineMapping(project_id=project.id, standard_account_code="1001", report_type=ReportType.balance_sheet,
                             report_line_code="BS-001", report_line_name="货币资金", report_line_level=1,
                             mapping_type=ReportLineMappingType.manual, is_confirmed=True))
    db.add(TrialBalance(project_id=project.id, year=2025, company_code="001", standard_account_code="1001",
                        account_name="库存现金", account_category=AccountCategory.asset,
                        unadjusted_amount=Decimal("100"), audited_amount=Decimal("120.50")))
    await db.commit()
    return project.id


def _create(no=None, amount="100"):
    return AdjustmentCreate(
        adjustment_type=AdjustmentType.aje, year=2025, description="测试", adjustment_no=no,
        line_items=[AdjustmentLineItem(standard_account_code="1001", debit_amount=Decimal(amount)),
                    AdjustmentLineItem(standard_account_code="6001", credit_amount=Decimal(amount))],
    )


@pytest.mark.asyncio
async def test_custom_number_is_used_and_duplicates_rejected(db, pid):
    svc = AdjustmentService(db)
    first = await svc.create_entry(pid, _create(no=" 内部-01 "), USER_ID)
    assert first.adjustment_no == "内部-01"
    with pytest.raises(ValueError, match="已被本年度其他调整分录使用"):
        await svc.create_entry(pid, _create(no="内部-01"), USER_ID)


@pytest.mark.asyncio
async def test_auto_number_skips_numbers_taken_by_custom_entries(db, pid):
    svc = AdjustmentService(db)
    await svc.create_entry(pid, _create(no="AJE-002"), USER_ID)   # 计数 1，下一自动号 AJE-002 已被占
    auto = await svc.create_entry(pid, _create(), USER_ID)
    assert auto.adjustment_no == "AJE-003"


@pytest.mark.asyncio
async def test_create_and_update_reject_rule_violations(db, pid):
    svc = AdjustmentService(db)
    bad = _create()
    bad.line_items[0].debit_amount = Decimal("-100")
    bad.line_items[1].credit_amount = Decimal("-100")
    with pytest.raises(ValueError, match="金额不能为负数"):
        await svc.create_entry(pid, bad, USER_ID)
    ok = await svc.create_entry(pid, _create(), USER_ID)
    with pytest.raises(ValueError, match="借方和贷方不能同时填写"):
        await svc.update_entry(pid, ok.entry_group_id, AdjustmentUpdate(line_items=[
            AdjustmentLineItem(standard_account_code="1001", debit_amount=Decimal("50"), credit_amount=Decimal("50")),
            AdjustmentLineItem(standard_account_code="6001", credit_amount=Decimal("0")),
        ]), USER_ID)


@pytest.mark.asyncio
async def test_account_dropdown_lists_all_standard_accounts_with_balance(db, pid):
    svc = AdjustmentService(db)
    options = await svc.get_account_dropdown(pid, year=2025)
    by_code = {o.code: o for o in options}
    assert set(by_code) == {"1001", "1231", "6001"}, "未确认映射的标准科目也要能选"
    assert [o.code for o in options] == sorted(by_code), "按编码排序"
    assert by_code["1001"].report_line == "货币资金" and by_code["1231"].report_line is None
    assert by_code["1001"].balance == Decimal("120.50") and by_code["6001"].balance is None
    # 不传年度不带余额；按行次仍只返回该行次已确认映射的科目
    assert all(o.balance is None for o in await svc.get_account_dropdown(pid))
    assert [o.code for o in await svc.get_account_dropdown(pid, "BS-001")] == ["1001"]
