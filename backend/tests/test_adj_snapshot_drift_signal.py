"""需求 3.3：调整额「持久化快照」与「实时汇总」不一致的可观测信号。

spec: tb-adjustment-column-formula-closure Phase 1 Task 1.11

## 背景

两个口径长期并存且**差异完全静默**：
- 快照 = `trial_balance.aje_adjustment`（`recalc_adjustments` 落列，报表域
  `TB(code,'AJE调整')` 读它）
- 实时 = `adj_net_batch`（按当前 approved 分录现算，`ADJ(code,'aje_net')` 读它）

真库现状是持久化列全 0 而实时值非 0 —— 界面显示 0，公式按非 0 算，
没有任何地方报告二者不等。

## 本轮实现

接进既有 `ConsistencyCheckService.check_full_chain` 的第 6 项检查
（功能收敛期不新建页面/端点），**不做自动 recalc**（需求 3.3 明确不承诺）。

## 判据设计

🔴 **双向**：
- 有漂移 → 必须 `passed=False` 且 `failed_items` 指名科目
- 无漂移 → 必须 `passed=True`（否则每个项目都告警 = 等于没有信号）

🔴 **真库现状形态必须被覆盖**：快照全 0 + 实时非 0 是最重要的一个 case，
单独一条测试钉住。

Validates: Requirements 3.3
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base

_PID = uuid.UUID("aaaa1111-0000-4000-8000-000000000311")
_UID = uuid.UUID("aaaa2222-0000-4000-8000-000000000312")
_YEAR = 2097
_CO = "001"
_CODE = "1122"
_NAME = "应收账款"
_AMT = Decimal("10000")

_CHECK_NAME = "调整额快照→实时"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def _seed(
    db: AsyncSession,
    *,
    snapshot_aje: Decimal,
    with_entry: bool = True,
    review_status: str = "approved",
) -> None:
    """落一行 trial_balance（快照值由参数给）+ 可选一笔 AJE 分录（实时值来源）。

    `snapshot_aje` 与分录金额的关系决定是否漂移：
    - 相等 → 无漂移
    - 不等（尤其快照 0 / 实时非 0）→ 有漂移，真库现状形态
    """
    from app.models.audit_platform_models import (
        AccountCategory,
        Adjustment,
        AdjustmentEntry,
        AdjustmentType,
        TrialBalance,
    )

    db.add(TrialBalance(
        project_id=_PID, year=_YEAR, company_code=_CO,
        standard_account_code=_CODE, account_name=_NAME,
        account_category=AccountCategory.asset,
        unadjusted_amount=Decimal("100000"),
        audited_amount=Decimal("100000") + snapshot_aje,
        aje_adjustment=snapshot_aje,
        rje_adjustment=Decimal("0"),
        opening_balance=Decimal("0"),
        is_deleted=False,
    ))

    if with_entry:
        adj_id, grp = uuid.uuid4(), uuid.uuid4()
        db.add(Adjustment(
            id=adj_id, project_id=_PID, year=_YEAR, company_code=_CO,
            adjustment_no="AJE-DRIFT-1", adjustment_type=AdjustmentType.aje,
            account_code=_CODE, account_name=_NAME,
            debit_amount=_AMT, credit_amount=Decimal("0"),
            entry_group_id=grp, review_status=review_status, origin="manual",
            is_deleted=False, created_by=_UID,
        ))
        db.add(AdjustmentEntry(
            id=uuid.uuid4(), adjustment_id=adj_id, entry_group_id=grp, line_no=1,
            standard_account_code=_CODE, account_name=_NAME,
            debit_amount=_AMT, credit_amount=Decimal("0"), is_deleted=False,
        ))
    await db.flush()


async def _run_check(db: AsyncSession) -> dict:
    """跑第 6 项检查并返回它那一段结果。"""
    from app.services.consistency_check_service import ConsistencyCheckService

    svc = ConsistencyCheckService(db)
    result = await svc._check_adjustment_snapshot_vs_realtime(_PID, _YEAR)
    assert result["check_name"] == _CHECK_NAME
    return result


# ─── 有漂移必须被发现 ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_real_world_shape_snapshot_zero_realtime_nonzero(db_session):
    """🔴 真库现状形态：快照 **0** 而实时 **非 0** ⇒ 必须报不一致。

    这是需求 3.3 明确要求「必须能被发现」的那个 case。
    """
    await _seed(db_session, snapshot_aje=Decimal("0"))
    r = await _run_check(db_session)

    assert r["passed"] is False, "快照 0 / 实时 10000 未被判为不一致"
    assert r["failed_items"], "无 failed_items ⇒ 信号不可定位"
    item = r["failed_items"][0]
    assert item["entity_id"] == _CODE, f"未指名出问题的科目：{item}"
    assert "10000" in item["message"], f"消息未给出实时值：{item['message']}"
    assert "不一致" in item["message"]


@pytest.mark.asyncio
async def test_snapshot_stale_after_new_approved_entry(db_session):
    """快照是旧值（3000）而新分录使实时变成 10000 ⇒ 报不一致。"""
    await _seed(db_session, snapshot_aje=Decimal("3000"))
    r = await _run_check(db_session)
    assert r["passed"] is False
    assert any("3000" in i["message"] for i in r["failed_items"])


@pytest.mark.asyncio
async def test_drift_message_does_not_promise_auto_recalc(db_session):
    """🔴 消息措辞不得暗示自动重算（需求 3.3 明确不承诺）。"""
    await _seed(db_session, snapshot_aje=Decimal("0"))
    r = await _run_check(db_session)
    msg = r["failed_items"][0]["message"]
    assert "不自动重算" in msg, (
        f"消息应明示本检查不自动重算，实为：{msg}"
    )


# ─── 无漂移必须不误报 ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_drift_when_snapshot_matches_realtime(db_session):
    """🔴 快照与实时一致 ⇒ `passed=True`。

    没有这条，检查项可能对每个项目都告警 —— 那等于没有信号。
    """
    await _seed(db_session, snapshot_aje=_AMT)
    r = await _run_check(db_session)
    assert r["passed"] is True, f"无漂移却报不一致：{r['failed_items']}"
    assert r["failed_items"] == []
    assert r["total_items"] > 0, "分母为 0 ⇒ 本测试退化成空转"


@pytest.mark.asyncio
async def test_no_drift_when_both_zero(db_session):
    """两边都 0（无任何调整分录）⇒ 一致，不告警。"""
    await _seed(db_session, snapshot_aje=Decimal("0"), with_entry=False)
    r = await _run_check(db_session)
    assert r["passed"] is True, f"两边都 0 却报不一致：{r['failed_items']}"


@pytest.mark.asyncio
async def test_draft_entry_does_not_count_as_drift(db_session):
    """draft 分录不进实时口径 ⇒ 快照 0 + draft 分录 = 一致，不告警。

    口径必须与试算平衡表调整列一致（仅 approved）。若这里漏了 review_status
    过滤，每个有草稿分录的项目都会被误报漂移。
    """
    await _seed(
        db_session, snapshot_aje=Decimal("0"),
        with_entry=True, review_status="draft",
    )
    r = await _run_check(db_session)
    assert r["passed"] is True, (
        f"draft 分录被算进实时口径 ⇒ 误报漂移：{r['failed_items']}"
    )


@pytest.mark.asyncio
async def test_no_tb_rows_returns_empty_denominator(db_session):
    """无 trial_balance 数据 ⇒ 空分母、passed=True、不报错。"""
    r = await _run_check(db_session)
    assert r["passed"] is True
    assert r["total_items"] == 0


# ─── 接入 check_full_chain ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_is_wired_into_full_chain(db_session):
    """🔴 必须真的挂进 `check_full_chain`，否则是死代码。

    memory 记录过同源事故：`disclosure-payload` 轮的前端组件"写了但没人 import"
    ⇒ 需求实质未达成。本条防同型。
    """
    from app.services.consistency_check_service import ConsistencyCheckService

    await _seed(db_session, snapshot_aje=Decimal("0"))
    full = await ConsistencyCheckService(db_session).check_full_chain(_PID, _YEAR)

    names = [c["check_name"] for c in full["checks"]]
    assert _CHECK_NAME in names, f"第 6 项检查未挂进 check_full_chain：{names}"

    mine = next(c for c in full["checks"] if c["check_name"] == _CHECK_NAME)
    assert mine["passed"] is False, "挂进去了但结果没反映漂移"
    assert full["all_consistent"] is False, (
        "漂移未影响 all_consistent ⇒ 调用方看不到信号"
    )


@pytest.mark.asyncio
async def test_full_chain_still_has_all_six_checks(db_session):
    """既有 5 项检查不得被挤掉（只增不改）。"""
    from app.services.consistency_check_service import ConsistencyCheckService

    full = await ConsistencyCheckService(db_session).check_full_chain(_PID, _YEAR)
    names = {c["check_name"] for c in full["checks"]}
    for expected in ("四表→试算表", "附注→底稿"):
        assert expected in names, f"既有检查项 {expected} 丢失：{names}"
    assert len(full["checks"]) == 6, f"检查项数应为 6，实得 {len(full['checks'])}"


@pytest.mark.asyncio
async def test_check_result_shape_matches_siblings(db_session):
    """返回结构与其余 5 项一致（调用方按统一形状消费）。"""
    await _seed(db_session, snapshot_aje=Decimal("0"))
    r = await _run_check(db_session)
    for key in ("check_name", "passed", "total_items", "passed_items", "failed_items"):
        assert key in r, f"缺字段 {key}"
    assert isinstance(r["failed_items"], list)
    assert r["passed_items"] == r["total_items"] - len(r["failed_items"])
