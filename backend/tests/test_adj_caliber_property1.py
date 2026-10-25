"""Property 1 裁决记录 — 「净额归一」与「原始借贷相减」两种口径的等价性边界.

spec: tb-adjustment-column-formula-closure · Phase 0 Task 0.7

## 待验命题

P1：`audited = unadj + aje_net`（归一净额）**是否等价于**
    `audited = unadj + aje_dr - aje_cr`（原始借贷相减，现有 `get_summary_with_adjustments` 口径）

## 实测结论（本文件即证据）

**不等价，且差异有明确边界**：

| 科目方向 | 原始 dr-cr 口径 | 归一 net 口径 | 是否等价 |
|---|---|---|---|
| 借方正常（资产/费用） | `unadj + (dr-cr)` | `unadj + (dr-cr)` | ✅ 等价 |
| 贷方正常（负债/权益/收入） | `unadj + (dr-cr)` | `unadj - (dr-cr)` | ❌ **符号相反** |

⇒ P1 **不成立**。tasks 0.7 要求「若不等价则停下来报告差异，不得擅自改口径」，
本文件即该报告的可执行形态。

## 哪个口径正确

**归一口径正确**，依据是平台既有的 v2 约定与同文件内的参照实现：

1. `trial_balance.unadjusted_amount` 按 `category_natural_positive` 存**自然正数**
   （收入类贷方余额存为正数，不是负数）
2. `trial_balance_service.recalc_adjustments` L405-416 的注释明确写道：
   > 对贷方正常类（负债/权益/收入），一笔贷记增加应使审定数增大，若直接相加
   > "借正贷负"净额会方向反掉
   并据此实现 `row.aje_adjustment = sign * vals["aje"]`
3. 业务语义：应付账款贷记 800 = 负债**增加** 800 ⇒ 审定数应比未审数**大** 800

而 `get_summary_with_adjustments` 用的正是该注释警告的未修形态 —— 它是
`recalc_adjustments` 的**孪生体但未随之修复**。本文件把该缺陷记为 **B4**。

Validates: Property P1（结论为「不成立」，并钉住正确口径）
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

_PROJECT_ID = uuid.UUID("bbbbbbbb-0000-4000-8000-00000000c101")
_USER_ID = uuid.UUID("cccccccc-0000-4000-8000-00000000c102")
_YEAR = 2099
_COMPANY = "001"

# 借方正常方向（资产）
_ACCT_DEBIT = "1001"
_NAME_DEBIT = "库存现金"
# 贷方正常方向（负债）
_ACCT_CREDIT = "2202"
_NAME_CREDIT = "应付账款"
# 贷方正常方向（收入）—— 截图缺陷现场就是收入类
_ACCT_REVENUE = "6001"
_NAME_REVENUE = "主营业务收入"

_TB_STATUSES = frozenset({"approved"})
_TB_ORIGINS = frozenset({"workpaper"})


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        from app.models.core import Project, User

        session.add(User(id=_USER_ID, username="test_p1", email="p1@test.local",
                         hashed_password="x", role="admin"))
        session.add(Project(id=_PROJECT_ID, name="p1_test", client_name="测试客户",
                            status="active", created_by=_USER_ID))
        await session.flush()
        yield session
    await engine.dispose()


async def _seed(db, *, code, name, debit, credit, adj_type="aje"):
    from app.models.audit_platform_models import Adjustment, AdjustmentEntry, AdjustmentType

    adj_id, grp = uuid.uuid4(), uuid.uuid4()
    db.add(Adjustment(
        id=adj_id, project_id=_PROJECT_ID, year=_YEAR, company_code=_COMPANY,
        adjustment_no=f"ADJ-{adj_id.hex[:8]}", adjustment_type=AdjustmentType(adj_type),
        account_code=code, account_name=name, entry_group_id=grp,
        review_status="approved", origin="manual", is_deleted=False, created_by=_USER_ID,
    ))
    db.add(AdjustmentEntry(
        id=uuid.uuid4(), adjustment_id=adj_id, entry_group_id=grp, line_no=1,
        standard_account_code=code, account_name=name,
        debit_amount=Decimal(str(debit)), credit_amount=Decimal(str(credit)),
        is_deleted=False,
    ))
    await db.flush()


async def _fetch(db, codes):
    from app.services.adjustment_amount_source import adj_net_batch

    return await adj_net_batch(
        db, project_id=_PROJECT_ID, year=_YEAR, account_codes=codes,
        include_statuses=_TB_STATUSES, exclude_origins=_TB_ORIGINS,
    )


# ───────────────────────────────────────────────────────────────────────────
# P1 在借方类科目上成立
# ───────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_p1_holds_for_debit_direction_account(db_session: AsyncSession):
    """借方正常方向科目：两种口径**等价**。"""
    await _seed(db_session, code=_ACCT_DEBIT, name=_NAME_DEBIT, debit=500, credit=0)

    b = (await _fetch(db_session, [_ACCT_DEBIT]))[_ACCT_DEBIT]

    raw_caliber = b["aje_dr"] - b["aje_cr"]      # 现有 get_summary_with_adjustments
    net_caliber = b["aje_net"]                    # adj_net / TB 持久化列

    assert raw_caliber == Decimal("500")
    assert net_caliber == Decimal("500")
    assert raw_caliber == net_caliber, "借方类两口径应等价"


@pytest.mark.asyncio
async def test_p1_holds_for_debit_direction_credit_entry(db_session: AsyncSession):
    """借方类被贷记（资产减少）：仍等价（符号同为负）。"""
    await _seed(db_session, code=_ACCT_DEBIT, name=_NAME_DEBIT, debit=0, credit=120)

    b = (await _fetch(db_session, [_ACCT_DEBIT]))[_ACCT_DEBIT]
    assert b["aje_dr"] - b["aje_cr"] == Decimal("-120")
    assert b["aje_net"] == Decimal("-120")


# ───────────────────────────────────────────────────────────────────────────
# 🔴 P1 在贷方类科目上不成立 —— 这就是 B4
# ───────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_p1_fails_for_credit_direction_liability(db_session: AsyncSession):
    """🔴 贷方正常方向（负债）：两口径**符号相反**，差额 = 2×金额。

    业务语义：应付账款贷记 800 = 负债增加 800 ⇒ 审定数应 **+800**。
    现有 `dr - cr` 口径得 **−800**（方向反掉），归一口径得 **+800**（正确）。
    """
    await _seed(db_session, code=_ACCT_CREDIT, name=_NAME_CREDIT, debit=0, credit=800)

    b = (await _fetch(db_session, [_ACCT_CREDIT]))[_ACCT_CREDIT]

    raw_caliber = b["aje_dr"] - b["aje_cr"]
    net_caliber = b["aje_net"]

    assert raw_caliber == Decimal("-800"), "现有口径：借正贷负 ⇒ 贷记得负数"
    assert net_caliber == Decimal("800"), "归一口径：负债增加 ⇒ 正数"
    assert raw_caliber != net_caliber, "P1 在贷方类不成立（若相等说明归一失效）"
    assert net_caliber - raw_caliber == Decimal("1600"), "差额恒为 2×原始净额绝对值"


@pytest.mark.asyncio
async def test_p1_fails_for_credit_direction_revenue(db_session: AsyncSession):
    """🔴 收入类（截图缺陷现场的科目类别）：同样符号相反。

    截图现象 = `IS-001 营业收入` 审计调整**贷方** 10,000、审定数 **−10,000**。
    该审定数正是 `unadj + dr - cr = 0 + 0 - 10000` 的产物；
    按归一口径应为 `0 + 10000 = +10000`（收入增加）。
    """
    await _seed(db_session, code=_ACCT_REVENUE, name=_NAME_REVENUE,
                debit=0, credit=10000)

    b = (await _fetch(db_session, [_ACCT_REVENUE]))[_ACCT_REVENUE]

    raw_caliber = b["aje_dr"] - b["aje_cr"]
    net_caliber = b["aje_net"]

    assert raw_caliber == Decimal("-10000")
    assert net_caliber == Decimal("10000"), "收入贷记增加 ⇒ 归一净额为正"
    # 复现截图那个 -10,000：unadj=0 时现有口径的审定数
    assert Decimal("0") + raw_caliber == Decimal("-10000"), (
        "复现截图的 audited=-10,000（现有口径产物）"
    )
    assert Decimal("0") + net_caliber == Decimal("10000"), (
        "修正后应为 +10,000（收入增加）"
    )


@pytest.mark.asyncio
async def test_p1_fails_for_credit_direction_debit_entry(db_session: AsyncSession):
    """贷方类被借记（负债减少）：同样相反。"""
    await _seed(db_session, code=_ACCT_CREDIT, name=_NAME_CREDIT, debit=300, credit=0)

    b = (await _fetch(db_session, [_ACCT_CREDIT]))[_ACCT_CREDIT]
    assert b["aje_dr"] - b["aje_cr"] == Decimal("300")
    assert b["aje_net"] == Decimal("-300"), "贷方类借记 ⇒ 负债减少 ⇒ 净额为负"


# ───────────────────────────────────────────────────────────────────────────
# 等价性边界的精确刻画（供后续实现引用）
# ───────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_p1_boundary_is_exactly_account_direction(db_session: AsyncSession):
    """等价性边界**恰好**是科目方向，与金额大小/借贷方向无关。

    这条把结论钉成可判定形式：实现方不需要逐科目试，只看 direction 即可。
    """
    from app.services.ledger_import.direction_resolver import resolve_account_direction

    cases = [
        (_ACCT_DEBIT, _NAME_DEBIT, 500, 0),
        (_ACCT_DEBIT, _NAME_DEBIT, 0, 120),
        (_ACCT_CREDIT, _NAME_CREDIT, 0, 800),
        (_ACCT_CREDIT, _NAME_CREDIT, 300, 0),
        (_ACCT_REVENUE, _NAME_REVENUE, 0, 10000),
    ]
    for code, name, dr, cr in cases:
        await _seed(db_session, code=code, name=name, debit=dr, credit=cr)

    got = await _fetch(db_session, [_ACCT_DEBIT, _ACCT_CREDIT, _ACCT_REVENUE])

    for code in (_ACCT_DEBIT, _ACCT_CREDIT, _ACCT_REVENUE):
        b = got[code]
        raw = b["aje_dr"] - b["aje_cr"]
        net = b["aje_net"]
        direction, _ = resolve_account_direction(code, "")
        if direction == "credit":
            assert net == -raw, f"{code} 贷方类：net 应 = -raw（实得 net={net} raw={raw}）"
        else:
            assert net == raw, f"{code} 借方类：net 应 = raw（实得 net={net} raw={raw}）"


@pytest.mark.asyncio
async def test_display_columns_stay_raw_regardless_of_direction(db_session: AsyncSession):
    """展示用借贷列**不受**方向影响，恒为原始非负值（ADR-ADJ-005）。

    这是「显示列用 raw、审定数用 net」这一裁决可行的前提：
    审计师在借/贷列看到的数字与分录逐字一致，可直接对账。
    """
    await _seed(db_session, code=_ACCT_REVENUE, name=_NAME_REVENUE, debit=0, credit=10000)

    b = (await _fetch(db_session, [_ACCT_REVENUE]))[_ACCT_REVENUE]
    assert b["aje_dr"] == Decimal("0")
    assert b["aje_cr"] == Decimal("10000"), (
        "贷方列应显示分录原始贷方金额 10000（与凭证逐字一致），不因归一而变号"
    )
    assert b["aje_cr"] >= 0 and b["aje_dr"] >= 0, "展示列恒非负"
