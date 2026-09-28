"""adj_net_batch 守卫 — 批量调整取数的口径与等价性.

spec: tb-adjustment-column-formula-closure · Phase 0 Task 0.4 + 0.5

守卫内容：
- **P3** draft 分录不计入（`review_status` 过滤生效）+ **双向变异**
  （同一条改 approved 后必须计入 —— 只做正向的话，函数返回恒空也能通过）
- **P4** `origin='workpaper'` 不计入试算平衡表口径 + **双向变异**
  （`exclude_origins` 传空集后 workpaper 必须计入）
- **0.5** 批量路径与逐条 `adj_net` **逐值相等**（防两条路径漂移；
  consol 封板曾抓到同型 bug：批量与单点结果不一致）
- 返回值结构契约：6 键齐全、`*_dr`/`*_cr` 恒非负、`*_net` 已按科目方向归一
- 空输入短路（不发查询）

真 SQLite + 真 ORM 行，不 mock DB 层。

Validates: Requirements 1.2, 1.3 · Properties P3, P4
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

_PROJECT_ID = uuid.UUID("bbbbbbbb-0000-4000-8000-00000000ba01")
_USER_ID = uuid.UUID("cccccccc-0000-4000-8000-00000000ba02")
_YEAR = 2099
_COMPANY = "001"
_ACCT_DEBIT = "1001"    # 资产类（借方正常） — 库存现金
_ACCT_CREDIT = "2202"   # 负债类（贷方正常） — 应付账款
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
        await _seed_fk_parents(session)
        yield session
    await engine.dispose()


async def _seed_fk_parents(db: AsyncSession) -> None:
    from app.models.core import Project, User

    db.add(User(id=_USER_ID, username="test_adj_batch", email="adjbatch@test.local",
                hashed_password="x", role="admin"))
    db.add(Project(id=_PROJECT_ID, name="adj_batch_test", client_name="测试客户",
                   status="active", created_by=_USER_ID))
    await db.flush()


async def _seed_adj(
    db: AsyncSession,
    *,
    adj_type: str,
    account_code: str,
    debit: Decimal,
    credit: Decimal,
    review_status: str = "approved",
    origin: str = "manual",
    account_name: str = "",
) -> None:
    """插入 Adjustment 主表 + AdjustmentEntry 明细行（ADR-ADJ-001 口径）。"""
    from app.models.audit_platform_models import Adjustment, AdjustmentEntry, AdjustmentType

    adj_id = uuid.uuid4()
    grp = uuid.uuid4()
    db.add(Adjustment(
        id=adj_id, project_id=_PROJECT_ID, year=_YEAR, company_code=_COMPANY,
        adjustment_no=f"ADJ-{adj_id.hex[:8]}", adjustment_type=AdjustmentType(adj_type),
        account_code=account_code, account_name=account_name, entry_group_id=grp,
        review_status=review_status, origin=origin, is_deleted=False, created_by=_USER_ID,
    ))
    db.add(AdjustmentEntry(
        id=uuid.uuid4(), adjustment_id=adj_id, entry_group_id=grp, line_no=1,
        standard_account_code=account_code, account_name=account_name,
        debit_amount=debit, credit_amount=credit, is_deleted=False,
    ))
    await db.flush()


async def _batch(db, codes, *, statuses=_TB_STATUSES, origins=_TB_ORIGINS):
    from app.services.adjustment_amount_source import adj_net_batch

    return await adj_net_batch(
        db, project_id=_PROJECT_ID, year=_YEAR, account_codes=codes,
        include_statuses=statuses, exclude_origins=origins,
    )


# ───────────────────────────────────────────────────────────────────────────
# P3 — review_status 过滤（含双向变异）
# ───────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_p3_draft_not_counted(db_session: AsyncSession):
    """draft 分录不得计入（B1 的防回归）。"""
    await _seed_adj(db_session, adj_type="aje", account_code=_ACCT_DEBIT,
                    debit=Decimal("500"), credit=Decimal("0"),
                    review_status="draft", account_name="库存现金")

    got = await _batch(db_session, [_ACCT_DEBIT])
    assert got == {}, f"draft 分录不应出现在结果中，实得 {got}"


@pytest.mark.asyncio
async def test_p3_mutation_approved_is_counted(db_session: AsyncSession):
    """**双向变异**：同一条改 approved 后必须计入。

    没有这一半，`adj_net_batch` 返回恒空也能让上一个测试通过。
    """
    await _seed_adj(db_session, adj_type="aje", account_code=_ACCT_DEBIT,
                    debit=Decimal("500"), credit=Decimal("0"),
                    review_status="approved", account_name="库存现金")

    got = await _batch(db_session, [_ACCT_DEBIT])
    assert _ACCT_DEBIT in got, f"approved 分录必须计入，实得 {got}"
    assert got[_ACCT_DEBIT]["aje_net"] == Decimal("500")
    assert got[_ACCT_DEBIT]["aje_dr"] == Decimal("500")
    assert got[_ACCT_DEBIT]["aje_cr"] == Decimal("0")


@pytest.mark.asyncio
async def test_p3_draft_and_approved_mixed(db_session: AsyncSession):
    """混合集：只取 approved 的那部分金额。"""
    await _seed_adj(db_session, adj_type="aje", account_code=_ACCT_DEBIT,
                    debit=Decimal("500"), credit=Decimal("0"),
                    review_status="approved", account_name="库存现金")
    await _seed_adj(db_session, adj_type="aje", account_code=_ACCT_DEBIT,
                    debit=Decimal("999"), credit=Decimal("0"),
                    review_status="draft", account_name="库存现金")

    got = await _batch(db_session, [_ACCT_DEBIT])
    assert got[_ACCT_DEBIT]["aje_net"] == Decimal("500"), (
        f"应只含 approved 的 500，实得 {got[_ACCT_DEBIT]['aje_net']}"
        "（含 999 ⇒ review_status 过滤失效）"
    )


@pytest.mark.asyncio
async def test_p3_mutation_empty_statuses_includes_draft(db_session: AsyncSession):
    """**双向变异**：include_statuses 传空集 ⇒ 不过滤 ⇒ draft 也计入。"""
    await _seed_adj(db_session, adj_type="aje", account_code=_ACCT_DEBIT,
                    debit=Decimal("500"), credit=Decimal("0"),
                    review_status="approved", account_name="库存现金")
    await _seed_adj(db_session, adj_type="aje", account_code=_ACCT_DEBIT,
                    debit=Decimal("999"), credit=Decimal("0"),
                    review_status="draft", account_name="库存现金")

    got = await _batch(db_session, [_ACCT_DEBIT], statuses=frozenset())
    assert got[_ACCT_DEBIT]["aje_net"] == Decimal("1499"), (
        "空 statuses 应纳入全部状态（500+999=1499）"
    )


# ───────────────────────────────────────────────────────────────────────────
# P4 — origin 过滤（含双向变异）
# ───────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_p4_workpaper_origin_excluded(db_session: AsyncSession):
    """origin=workpaper 不得计入试算平衡表口径（B2 的防回归 / V124 防双计）。"""
    await _seed_adj(db_session, adj_type="aje", account_code=_ACCT_DEBIT,
                    debit=Decimal("700"), credit=Decimal("0"),
                    review_status="approved", origin="workpaper",
                    account_name="库存现金")

    got = await _batch(db_session, [_ACCT_DEBIT])
    assert got == {}, f"workpaper 来源应被排除，实得 {got}"


@pytest.mark.asyncio
async def test_p4_mutation_empty_origins_includes_workpaper(db_session: AsyncSession):
    """**双向变异**：exclude_origins 传空集 ⇒ workpaper 必须计入。"""
    await _seed_adj(db_session, adj_type="aje", account_code=_ACCT_DEBIT,
                    debit=Decimal("700"), credit=Decimal("0"),
                    review_status="approved", origin="workpaper",
                    account_name="库存现金")

    got = await _batch(db_session, [_ACCT_DEBIT], origins=frozenset())
    assert got[_ACCT_DEBIT]["aje_net"] == Decimal("700"), (
        "空 exclude_origins 应纳入 workpaper 来源（ADJ() 底稿呈现口径）"
    )


@pytest.mark.asyncio
async def test_p4_manual_and_workpaper_mixed(db_session: AsyncSession):
    """混合来源：只取非 workpaper 的部分。"""
    await _seed_adj(db_session, adj_type="aje", account_code=_ACCT_DEBIT,
                    debit=Decimal("300"), credit=Decimal("0"),
                    review_status="approved", origin="manual", account_name="库存现金")
    await _seed_adj(db_session, adj_type="aje", account_code=_ACCT_DEBIT,
                    debit=Decimal("700"), credit=Decimal("0"),
                    review_status="approved", origin="workpaper", account_name="库存现金")

    got = await _batch(db_session, [_ACCT_DEBIT])
    assert got[_ACCT_DEBIT]["aje_net"] == Decimal("300"), (
        f"应只含 manual 的 300，实得 {got[_ACCT_DEBIT]['aje_net']}"
        "（含 700 ⇒ origin 排除失效，与审定表 writeback 双计）"
    )


@pytest.mark.asyncio
async def test_p4_null_origin_is_kept(db_session: AsyncSession):
    """origin 为 NULL 的分录不得被 exclude_origins 误排除。"""
    await _seed_adj(db_session, adj_type="aje", account_code=_ACCT_DEBIT,
                    debit=Decimal("123"), credit=Decimal("0"),
                    review_status="approved", origin=None, account_name="库存现金")

    got = await _batch(db_session, [_ACCT_DEBIT])
    assert got[_ACCT_DEBIT]["aje_net"] == Decimal("123"), "origin IS NULL 应保留"


# ───────────────────────────────────────────────────────────────────────────
# Task 0.5 — 批量与逐条 adj_net 等价性
# ───────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_batch_equals_single_point(db_session: AsyncSession):
    """批量路径与逐条 adj_net **逐值相等**（防两条路径漂移）。

    覆盖借方类与贷方类两种科目 + aje/rje 两种类型 —— 贷方类是符号归一的关键，
    只测借方类的话符号 bug 不会暴露。
    """
    from app.services.adjustment_amount_source import adj_net

    await _seed_adj(db_session, adj_type="aje", account_code=_ACCT_DEBIT,
                    debit=Decimal("500"), credit=Decimal("0"),
                    account_name="库存现金")
    await _seed_adj(db_session, adj_type="rje", account_code=_ACCT_DEBIT,
                    debit=Decimal("0"), credit=Decimal("120"),
                    account_name="库存现金")
    await _seed_adj(db_session, adj_type="aje", account_code=_ACCT_CREDIT,
                    debit=Decimal("0"), credit=Decimal("800"),
                    account_name="应付账款")
    await _seed_adj(db_session, adj_type="rje", account_code=_ACCT_CREDIT,
                    debit=Decimal("60"), credit=Decimal("0"),
                    account_name="应付账款")

    codes = [_ACCT_DEBIT, _ACCT_CREDIT]
    batch = await _batch(db_session, codes)

    for code in codes:
        for t in ("aje", "rje"):
            single = await adj_net(
                db_session, project_id=_PROJECT_ID, year=_YEAR,
                account_code=code, adj_type=f"{t}_net",
                include_statuses=_TB_STATUSES, exclude_origins=_TB_ORIGINS,
            )
            batched = batch.get(code, {}).get(f"{t}_net", Decimal("0"))
            assert batched == single, (
                f"{code} {t}: 批量 {batched} ≠ 单点 {single}"
            )


@pytest.mark.asyncio
async def test_batch_equals_single_point_when_no_data(db_session: AsyncSession):
    """无数据科目：批量缺键 与 单点返 0 语义等价（含 -0 归零）。"""
    from app.services.adjustment_amount_source import adj_net

    batch = await _batch(db_session, [_ACCT_CREDIT])
    single = await adj_net(
        db_session, project_id=_PROJECT_ID, year=_YEAR,
        account_code=_ACCT_CREDIT, adj_type="aje_net",
        include_statuses=_TB_STATUSES, exclude_origins=_TB_ORIGINS,
    )
    assert single == Decimal("0")
    assert str(single) == "0", f"贷方类无数据不得返回 -0，实得 {single!r}"
    assert batch.get(_ACCT_CREDIT, {}).get("aje_net", Decimal("0")) == single


# ───────────────────────────────────────────────────────────────────────────
# 返回值结构契约
# ───────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_return_shape_has_six_keys(db_session: AsyncSession):
    """有数据的科目必须 6 键齐全（调用方可无条件取用，无需 .get 兜底每个键）。"""
    await _seed_adj(db_session, adj_type="aje", account_code=_ACCT_DEBIT,
                    debit=Decimal("10"), credit=Decimal("0"), account_name="库存现金")

    got = await _batch(db_session, [_ACCT_DEBIT])
    assert set(got[_ACCT_DEBIT]) == {
        "aje_net", "aje_dr", "aje_cr", "rje_net", "rje_dr", "rje_cr",
    }


@pytest.mark.asyncio
async def test_dr_cr_are_raw_nonnegative(db_session: AsyncSession):
    """`*_dr`/`*_cr` 是**原始**借贷合计（未归一）⇒ 恒非负；`*_net` 才归一。

    贷方类科目：贷记 800 ⇒ 原始 cr=800、dr=0，归一 net=+800（负债增加）。
    若 dr/cr 也被归一，展示列会出现负数，审计师无法对上分录。
    """
    await _seed_adj(db_session, adj_type="aje", account_code=_ACCT_CREDIT,
                    debit=Decimal("0"), credit=Decimal("800"),
                    account_name="应付账款")

    b = (await _batch(db_session, [_ACCT_CREDIT]))[_ACCT_CREDIT]
    assert b["aje_dr"] == Decimal("0")
    assert b["aje_cr"] == Decimal("800"), "原始贷方合计应恒非负"
    assert b["aje_net"] == Decimal("800"), (
        "贷方类贷记增加 ⇒ 归一净额为正（与 trial_balance.aje_adjustment 同口径）"
    )


@pytest.mark.asyncio
async def test_credit_account_sign_normalization(db_session: AsyncSession):
    """贷方类借记减少 ⇒ 归一净额为负。"""
    await _seed_adj(db_session, adj_type="aje", account_code=_ACCT_CREDIT,
                    debit=Decimal("300"), credit=Decimal("0"),
                    account_name="应付账款")

    b = (await _batch(db_session, [_ACCT_CREDIT]))[_ACCT_CREDIT]
    assert b["aje_dr"] == Decimal("300")
    assert b["aje_net"] == Decimal("-300"), "贷方类借记 ⇒ 负债减少 ⇒ 净额为负"


@pytest.mark.asyncio
async def test_multiple_entries_same_account_aggregate(db_session: AsyncSession):
    """同科目多笔分录按类型分别累加。"""
    await _seed_adj(db_session, adj_type="aje", account_code=_ACCT_DEBIT,
                    debit=Decimal("100"), credit=Decimal("0"), account_name="库存现金")
    await _seed_adj(db_session, adj_type="aje", account_code=_ACCT_DEBIT,
                    debit=Decimal("0"), credit=Decimal("30"), account_name="库存现金")
    await _seed_adj(db_session, adj_type="rje", account_code=_ACCT_DEBIT,
                    debit=Decimal("7"), credit=Decimal("0"), account_name="库存现金")

    b = (await _batch(db_session, [_ACCT_DEBIT]))[_ACCT_DEBIT]
    assert b["aje_dr"] == Decimal("100")
    assert b["aje_cr"] == Decimal("30")
    assert b["aje_net"] == Decimal("70")
    assert b["rje_net"] == Decimal("7")


# ───────────────────────────────────────────────────────────────────────────
# 边界
# ───────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_codes_short_circuits(db_session: AsyncSession):
    """空科目集直接返回 {}（与调用点 `if all_account_codes:` 守卫语义一致）。"""
    assert await _batch(db_session, []) == {}
    assert await _batch(db_session, None) == {}
    assert await _batch(db_session, ["", None]) == {}


@pytest.mark.asyncio
async def test_soft_deleted_adjustment_excluded(db_session: AsyncSession):
    """is_deleted=true 的分录不得计入（真库 34 条全是此状态，必须守住）。"""
    from app.models.audit_platform_models import Adjustment, AdjustmentEntry, AdjustmentType

    adj_id = uuid.uuid4()
    grp = uuid.uuid4()
    db_session.add(Adjustment(
        id=adj_id, project_id=_PROJECT_ID, year=_YEAR, company_code=_COMPANY,
        adjustment_no="ADJ-DEL", adjustment_type=AdjustmentType("aje"),
        account_code=_ACCT_DEBIT, account_name="库存现金", entry_group_id=grp,
        review_status="approved", origin="manual", is_deleted=True, created_by=_USER_ID,
    ))
    db_session.add(AdjustmentEntry(
        id=uuid.uuid4(), adjustment_id=adj_id, entry_group_id=grp, line_no=1,
        standard_account_code=_ACCT_DEBIT, account_name="库存现金",
        debit_amount=Decimal("555"), credit_amount=Decimal("0"), is_deleted=False,
    ))
    await db_session.flush()

    assert await _batch(db_session, [_ACCT_DEBIT]) == {}


@pytest.mark.asyncio
async def test_unrequested_account_not_returned(db_session: AsyncSession):
    """只返回请求的科目（account_codes 过滤生效）。"""
    await _seed_adj(db_session, adj_type="aje", account_code=_ACCT_DEBIT,
                    debit=Decimal("10"), credit=Decimal("0"), account_name="库存现金")
    await _seed_adj(db_session, adj_type="aje", account_code=_ACCT_CREDIT,
                    debit=Decimal("0"), credit=Decimal("20"), account_name="应付账款")

    got = await _batch(db_session, [_ACCT_DEBIT])
    assert set(got) == {_ACCT_DEBIT}, f"不应返回未请求的科目，实得 {set(got)}"
