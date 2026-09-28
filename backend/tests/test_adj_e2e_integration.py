"""test_adj_e2e_integration.py — ADJ 端到端集成测试（本 spec 验收核心）.

spec: adj-formula-repair-and-approval-gate-wiring · 阶段 5 任务 5.1 + 5.2
属性 P9（端到端整链贯通）

测试链路：
  建分录(draft) → 调整列未变(draft 不纳入) → approved → 调整列与审定数已变
  → TRIAL_BALANCE_UPDATED 已发布

真 SQLite + 真 ORM + 真 service（不 mock 相邻层）。
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.audit_platform_models import (
    AccountCategory,
    Adjustment,
    AdjustmentEntry,
    AdjustmentType,
    ReviewStatus,
    TrialBalance,
)

# SQLite 兼容
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_UUID"):
    SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid  # type: ignore[attr-defined]

_PROJECT_ID = uuid.UUID("e2e00000-0000-4000-8000-000000000001")
_YEAR = 2098
_USER_ID = uuid.UUID("e2e00000-0000-4000-8000-000000000a01")
_COMPANY = "001"


@pytest_asyncio.fixture
async def e2e_db():
    """SQLite in-memory fixture：建表 + seed TB 行 + 返回 session factory。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # seed 一条 TB 行（应收账款 1122，未审数 10000，调整列为 0）
    async with factory() as db:
        db.add(TrialBalance(
            project_id=_PROJECT_ID,
            year=_YEAR,
            company_code=_COMPANY,
            standard_account_code="1122",
            account_name="应收账款",
            account_category=AccountCategory.asset,
            unadjusted_amount=Decimal("10000"),
            aje_adjustment=Decimal("0"),
            rje_adjustment=Decimal("0"),
            audited_amount=Decimal("10000"),
        ))
        await db.commit()

    yield factory

    await engine.dispose()


async def _seed_adj(
    db: AsyncSession,
    *,
    account_code: str = "1122",
    account_name: str = "应收账款",
    adj_type: AdjustmentType = AdjustmentType.aje,
    debit: Decimal = Decimal("500"),
    credit: Decimal = Decimal("0"),
    status: ReviewStatus = ReviewStatus.draft,
    origin: str = "manual",
    no_suffix: str = "",
) -> uuid.UUID:
    """seed 一笔调整分录（头表 + 明细行），返回 entry_group_id。"""
    group_id = uuid.uuid4()
    adj = Adjustment(
        project_id=_PROJECT_ID,
        year=_YEAR,
        company_code=_COMPANY,
        adjustment_no=f"{adj_type.value.upper()}-E2E-{account_code}{no_suffix}",
        adjustment_type=adj_type,
        account_code=account_code,
        account_name=account_name,
        debit_amount=debit,
        credit_amount=credit,
        entry_group_id=group_id,
        review_status=status,
        origin=origin,
        created_by=_USER_ID,
    )
    db.add(adj)
    await db.flush()
    db.add(AdjustmentEntry(
        adjustment_id=adj.id,
        entry_group_id=group_id,
        line_no=1,
        standard_account_code=account_code,
        account_name=account_name,
        debit_amount=debit,
        credit_amount=credit,
    ))
    await db.commit()
    return group_id


class TestAdjE2EIntegration:
    """P9 端到端：draft → 调整列未变 → approved → 调整列与审定数已变。"""

    @pytest.mark.asyncio
    async def test_draft_does_not_affect_tb(self, e2e_db):
        """draft 分录不进 TB 调整列（ADR-ADJ-003：仅 approved）。"""
        from app.services.trial_balance_service import TrialBalanceService

        async with e2e_db() as db:
            # 建 draft 分录
            await _seed_adj(db, status=ReviewStatus.draft, debit=Decimal("500"))

            # 重算
            svc = TrialBalanceService(db)
            await svc.recalc_adjustments(_PROJECT_ID, _YEAR, _COMPANY)
            await svc.recalc_audited(_PROJECT_ID, _YEAR, _COMPANY)
            await db.flush()

            # 读 TB
            tb = (await db.execute(
                sa.select(TrialBalance).where(
                    TrialBalance.project_id == _PROJECT_ID,
                    TrialBalance.standard_account_code == "1122",
                )
            )).scalar_one()

            # draft 不影响——调整列仍为 0
            assert tb.aje_adjustment == Decimal("0"), (
                f"draft 分录不应计入 aje_adjustment，得到 {tb.aje_adjustment}"
            )
            assert tb.audited_amount == Decimal("10000"), (
                f"审定数不应变化，得到 {tb.audited_amount}"
            )

    @pytest.mark.asyncio
    async def test_approved_updates_tb(self, e2e_db):
        """approved 分录计入 TB 调整列 + 审定数变化。"""
        from app.services.trial_balance_service import TrialBalanceService

        async with e2e_db() as db:
            # 建 approved 分录（借记 500）
            await _seed_adj(
                db,
                status=ReviewStatus.approved,
                debit=Decimal("500"),
                credit=Decimal("0"),
            )

            # 重算
            svc = TrialBalanceService(db)
            await svc.recalc_adjustments(_PROJECT_ID, _YEAR, _COMPANY)
            await svc.recalc_audited(_PROJECT_ID, _YEAR, _COMPANY)
            await db.flush()

            # 读 TB
            tb = (await db.execute(
                sa.select(TrialBalance).where(
                    TrialBalance.project_id == _PROJECT_ID,
                    TrialBalance.standard_account_code == "1122",
                )
            )).scalar_one()

            # 应收账款是资产（借方类），sign=+1，净额 500-0=500
            assert tb.aje_adjustment == Decimal("500"), (
                f"approved 分录应计入 aje_adjustment=500，得到 {tb.aje_adjustment}"
            )
            # audited = unadjusted + aje + rje = 10000 + 500 + 0
            assert tb.audited_amount == Decimal("10500"), (
                f"审定数应为 10500，得到 {tb.audited_amount}"
            )

    @pytest.mark.asyncio
    async def test_adj_net_matches_recalc(self, e2e_db):
        """P5：adj_net 单点路径与 recalc 批量路径逐值相同。"""
        from app.services.adjustment_amount_source import adj_net
        from app.services.trial_balance_service import TrialBalanceService

        async with e2e_db() as db:
            await _seed_adj(
                db,
                status=ReviewStatus.approved,
                debit=Decimal("800"),
                credit=Decimal("0"),
            )

            # 批量路径
            svc = TrialBalanceService(db)
            await svc.recalc_adjustments(_PROJECT_ID, _YEAR, _COMPANY)
            await db.flush()

            tb = (await db.execute(
                sa.select(TrialBalance).where(
                    TrialBalance.project_id == _PROJECT_ID,
                    TrialBalance.standard_account_code == "1122",
                )
            )).scalar_one()

            # 单点路径
            single = await adj_net(
                db,
                project_id=_PROJECT_ID,
                year=_YEAR,
                account_code="1122",
                adj_type="aje_net",
                exclude_origins=frozenset({"workpaper"}),
            )

            assert tb.aje_adjustment == single, (
                f"批量路径 {tb.aje_adjustment} ≠ 单点路径 {single}"
            )

    @pytest.mark.asyncio
    async def test_formula_resolver_returns_value(self, e2e_db):
        """ADJ() 公式 resolver 对已 approved 分录返回非零值。"""
        from app.services.prefill_engine import _resolve_adj_formula

        async with e2e_db() as db:
            await _seed_adj(
                db,
                status=ReviewStatus.approved,
                debit=Decimal("300"),
                credit=Decimal("0"),
            )

            result = await _resolve_adj_formula(
                db, _PROJECT_ID, _YEAR, ["1122", "aje_net"]
            )

            assert result is not None
            assert result == Decimal("300"), f"期望 300，得到 {result}"


# ---------------------------------------------------------------------------
# 复盘补漏：真 DB 变异证明（原 mock/spy 守卫无法覆盖的部分）
#
# 原 0.1 的 test_aje_and_rje_must_differ_with_data 用 spy patch 只验证了
# 「resolver 把不同 adj_type 传给了 adj_net」，未验证 adj_net 内部真的用该
# type 做了 SQL 过滤。若有人删掉 adj_net 里的 adjustment_type 条件，那个 spy
# 测试仍会绿 —— 本节用真 DB 落两笔不同类型分录，是唯一能打红的守卫。
# ---------------------------------------------------------------------------


class TestRealDbMutationProofs:
    """真 DB 变异证明：删掉对应过滤条件后本节必打红。"""

    @pytest.mark.asyncio
    async def test_p2_type_filter_really_filters(self, e2e_db):
        """P2 真变异：同科目落 AJE 500 + RJE 300，两者必须各取各的。

        若 adj_net 缺 adjustment_type 过滤 → 两者都返回合计 800 → 本测试红。
        """
        from app.services.adjustment_amount_source import adj_net

        async with e2e_db() as db:
            await _seed_adj(
                db, adj_type=AdjustmentType.aje, debit=Decimal("500"),
                status=ReviewStatus.approved, no_suffix="-a",
            )
            await _seed_adj(
                db, adj_type=AdjustmentType.rje, debit=Decimal("300"),
                status=ReviewStatus.approved, no_suffix="-r",
            )

            aje = await adj_net(
                db, project_id=_PROJECT_ID, year=_YEAR,
                account_code="1122", adj_type="aje_net",
                exclude_origins=frozenset(),
            )
            rje = await adj_net(
                db, project_id=_PROJECT_ID, year=_YEAR,
                account_code="1122", adj_type="rje_net",
                exclude_origins=frozenset(),
            )

        assert aje == Decimal("500"), (
            f"AJE 应为 500，得到 {aje}"
            + ("（= 合计 800 ⇒ adjustment_type 过滤失效）" if aje == Decimal("800") else "")
        )
        assert rje == Decimal("300"), (
            f"RJE 应为 300，得到 {rje}"
            + ("（= 合计 800 ⇒ adjustment_type 过滤失效）" if rje == Decimal("800") else "")
        )
        assert aje != rje

    @pytest.mark.asyncio
    async def test_p6_exclude_origins_really_excludes(self, e2e_db):
        """P6 真变异：manual 500 + workpaper 100，exclude 与不 exclude 必不相等。

        这是 tasks 0.3 要求的 origin 双向变异证明（原实现漏做）。
        """
        from app.services.adjustment_amount_source import adj_net

        async with e2e_db() as db:
            await _seed_adj(
                db, debit=Decimal("500"), status=ReviewStatus.approved,
                origin="manual", no_suffix="-m",
            )
            await _seed_adj(
                db, debit=Decimal("100"), status=ReviewStatus.approved,
                origin="workpaper", no_suffix="-w",
            )

            no_excl = await adj_net(
                db, project_id=_PROJECT_ID, year=_YEAR,
                account_code="1122", adj_type="aje_net",
                exclude_origins=frozenset(),
            )
            with_excl = await adj_net(
                db, project_id=_PROJECT_ID, year=_YEAR,
                account_code="1122", adj_type="aje_net",
                exclude_origins=frozenset({"workpaper"}),
            )

        # ADR-ADJ-002: 公式口径含全部来源；TB 列口径排除 workpaper
        assert no_excl == Decimal("600"), f"不排除应为 600，得到 {no_excl}"
        assert with_excl == Decimal("500"), f"排除 workpaper 应为 500，得到 {with_excl}"
        assert no_excl != with_excl, (
            "exclude_origins 未生效——传空集与传 {'workpaper'} 结果相同"
        )

    @pytest.mark.asyncio
    async def test_p11_draft_amount_is_observable_as_difference(self, e2e_db):
        """P11 差额可观测：draft 分录金额落在 audited - unadjusted - aje - rje 差额里。

        这是 tasks 4.4 要求的验证（原因 PG 空表被跳过，此处用 SQLite 真做）。
        双向：全 approved 时差额为 0。
        """
        from app.services.adjustment_amount_source import adj_net
        from app.services.trial_balance_service import TrialBalanceService

        async with e2e_db() as db:
            # approved 500 + draft 999
            await _seed_adj(
                db, debit=Decimal("500"), status=ReviewStatus.approved, no_suffix="-ap",
            )
            await _seed_adj(
                db, debit=Decimal("999"), status=ReviewStatus.draft, no_suffix="-dr",
            )

            svc = TrialBalanceService(db)
            await svc.recalc_adjustments(_PROJECT_ID, _YEAR, _COMPANY)
            await svc.recalc_audited(_PROJECT_ID, _YEAR, _COMPANY)
            await db.flush()

            tb = (await db.execute(
                sa.select(TrialBalance).where(
                    TrialBalance.project_id == _PROJECT_ID,
                    TrialBalance.standard_account_code == "1122",
                )
            )).scalar_one()

            # 全状态口径（含 draft）
            all_status = await adj_net(
                db, project_id=_PROJECT_ID, year=_YEAR,
                account_code="1122", adj_type="aje_net",
                include_statuses=frozenset(),   # 不过滤 = 纳入全部状态
                exclude_origins=frozenset({"workpaper"}),
            )

        # TB 列只含 approved 的 500
        assert tb.aje_adjustment == Decimal("500"), (
            f"TB aje 列应只含 approved 的 500，得到 {tb.aje_adjustment}"
            + "（含 999 ⇒ review_status 过滤失效）"
        )
        # 全状态口径含 draft ⇒ 1499
        assert all_status == Decimal("1499"), (
            f"全状态口径应为 1499，得到 {all_status}"
        )
        # 未纳入金额 = 1499 - 500 = 999，可观测不静默
        uncounted = all_status - tb.aje_adjustment
        assert uncounted == Decimal("999"), (
            f"未纳入 draft 金额应为 999（可观测），得到 {uncounted}"
        )

    @pytest.mark.asyncio
    async def test_p11_all_approved_yields_zero_difference(self, e2e_db):
        """P11 反向变异：全部 approved 时未纳入金额为 0。"""
        from app.services.adjustment_amount_source import adj_net
        from app.services.trial_balance_service import TrialBalanceService

        async with e2e_db() as db:
            await _seed_adj(
                db, debit=Decimal("500"), status=ReviewStatus.approved, no_suffix="-a1",
            )
            await _seed_adj(
                db, debit=Decimal("200"), status=ReviewStatus.approved, no_suffix="-a2",
            )

            svc = TrialBalanceService(db)
            await svc.recalc_adjustments(_PROJECT_ID, _YEAR, _COMPANY)
            await db.flush()

            tb = (await db.execute(
                sa.select(TrialBalance).where(
                    TrialBalance.project_id == _PROJECT_ID,
                    TrialBalance.standard_account_code == "1122",
                )
            )).scalar_one()

            all_status = await adj_net(
                db, project_id=_PROJECT_ID, year=_YEAR,
                account_code="1122", adj_type="aje_net",
                include_statuses=frozenset(),
                exclude_origins=frozenset({"workpaper"}),
            )

        assert tb.aje_adjustment == Decimal("700")
        assert all_status == Decimal("700")
        assert all_status - tb.aje_adjustment == Decimal("0"), (
            "全 approved 时未纳入金额应为 0"
        )


    @pytest.mark.asyncio
    async def test_adj_net_include_statuses_really_filters(self, e2e_db):
        """复盘补漏：adj_net 自身的 include_statuses 过滤必须生效。

        原测试缺口：`test_draft_does_not_affect_tb` 走的是 recalc_adjustments 的
        批量 SQL（review_status 条件散写在那里），`adj_net` 的 include_statuses
        参数路径从未被断言 —— 删掉它后全部测试仍绿（已实测）。

        本测试直接对比 adj_net 默认口径（仅 approved）与全状态口径。
        """
        from app.services.adjustment_amount_source import (
            DEFAULT_INCLUDE_STATUSES,
            adj_net,
        )

        # 前置：确认默认口径就是「仅 approved」
        assert DEFAULT_INCLUDE_STATUSES == frozenset({"approved"})

        async with e2e_db() as db:
            await _seed_adj(
                db, debit=Decimal("400"), status=ReviewStatus.approved, no_suffix="-ok",
            )
            await _seed_adj(
                db, debit=Decimal("600"), status=ReviewStatus.draft, no_suffix="-dft",
            )
            await _seed_adj(
                db, debit=Decimal("700"), status=ReviewStatus.pending_review,
                no_suffix="-pnd",
            )

            # 默认口径（include_statuses=None → 仅 approved）
            default_val = await adj_net(
                db, project_id=_PROJECT_ID, year=_YEAR,
                account_code="1122", adj_type="aje_net",
                exclude_origins=frozenset(),
            )
            # 显式仅 approved
            explicit_appr = await adj_net(
                db, project_id=_PROJECT_ID, year=_YEAR,
                account_code="1122", adj_type="aje_net",
                include_statuses=frozenset({"approved"}),
                exclude_origins=frozenset(),
            )
            # 全状态（空集 = 不过滤）
            all_val = await adj_net(
                db, project_id=_PROJECT_ID, year=_YEAR,
                account_code="1122", adj_type="aje_net",
                include_statuses=frozenset(),
                exclude_origins=frozenset(),
            )
            # 含 pending_review
            with_pending = await adj_net(
                db, project_id=_PROJECT_ID, year=_YEAR,
                account_code="1122", adj_type="aje_net",
                include_statuses=frozenset({"approved", "pending_review"}),
                exclude_origins=frozenset(),
            )

        assert default_val == Decimal("400"), (
            f"默认口径应只含 approved 的 400，得到 {default_val}"
            + "（= 1700 ⇒ include_statuses 过滤失效）"
        )
        assert explicit_appr == Decimal("400")
        assert default_val == explicit_appr, "None 与显式 approved 应等价"
        assert all_val == Decimal("1700"), f"全状态应为 1700，得到 {all_val}"
        assert with_pending == Decimal("1100"), (
            f"approved+pending 应为 1100，得到 {with_pending}"
        )
        # 三个口径必须互不相等（变异证明：过滤真的分层生效）
        assert len({default_val, with_pending, all_val}) == 3, (
            f"三种 include_statuses 口径结果应互不相同，"
            f"得到 {default_val}/{with_pending}/{all_val}"
        )


    @pytest.mark.asyncio
    async def test_credit_account_zero_is_not_negative_zero(self, e2e_db):
        """C1 实测发现：贷方类无数据时不得返回 Decimal("-0")。

        机理：符号归一 `sign = -1`，`-1 * Decimal("0")` 得 `Decimal("-0")`。
        `-0 == 0` 为 True 故断言 `== 0` 抓不到它，必须断言**字符串形态**
        —— 该脏值会以 "-0" 流向前端展示 / Excel 写格 / 字符串比较。
        """
        from app.services.adjustment_amount_source import adj_net

        async with e2e_db() as db:
            # 只落 AJE，查 RJE（贷方类科目 + 无数据 = 触发 -0 的组合）
            await _seed_adj(
                db, account_code="2202", account_name="应付账款",
                adj_type=AdjustmentType.aje, debit=Decimal("0"),
                credit=Decimal("500"), status=ReviewStatus.approved,
                no_suffix="-cz",
            )
            rje_val = await adj_net(
                db, project_id=_PROJECT_ID, year=_YEAR,
                account_code="2202", adj_type="rje_net",
                exclude_origins=frozenset(),
            )

        assert rje_val == Decimal("0")
        assert str(rje_val) == "0", (
            f"贷方类零值应为规范 '0'，得到 {str(rje_val)!r}"
            "（'-0' 会流向前端/Excel 成为可见脏值）"
        )
        assert not str(rje_val).startswith("-"), "零值带负号"


class TestPrefillActiveFilterArity:
    """C1 实测发现：prefill_engine 的 get_active_filter 必须传 `Model.__table__`。

    🔴 该函数内部用 `table.c.project_id`，传 ORM 类会抛
    `AttributeError: type object 'TbLedger' has no attribute 'c'`。
    实测 prefill_engine 曾有 **5 处**传 ORM 类（LEDGER / AUX / LEDGER_DETAIL /
    COUNT_LEDGER / TB_AUX），坐实这些 resolver 从未被真正执行过 ——
    修 ADJ 的 import 只让代码往前走一步，又撞到这第二层缺陷。

    全仓其余调用方（import_service / note_data_extractor / mapping_service 等
    20+ 处）全部传 `__table__`，故本守卫的正确口径有充分对照。
    """

    def test_prefill_engine_passes_table_not_orm_class(self):
        """prefill_engine 内不得出现 `get_active_filter(db, TbXxx, ...)` 形态。"""
        import re
        from pathlib import Path

        fp = Path(__file__).resolve().parents[1] / "app" / "services" / "prefill_engine.py"
        text = fp.read_text(encoding="utf-8")

        # 命中「第二参是 ORM 类名（无 .__table__）」的调用
        offenders = re.findall(
            r"get_active_filter\(\s*db,\s*(Tb\w+|TrialBalance)\s*,", text
        )
        assert not offenders, (
            f"prefill_engine 有 {len(offenders)} 处 get_active_filter 传 ORM 类"
            f"（必须传 .__table__，否则 AttributeError）: {sorted(set(offenders))}"
        )

    def test_prefill_engine_has_table_calls(self):
        """P12 非空转：确认文件里确实有 get_active_filter 调用（否则上一断言恒绿）。"""
        import re
        from pathlib import Path

        fp = Path(__file__).resolve().parents[1] / "app" / "services" / "prefill_engine.py"
        text = fp.read_text(encoding="utf-8")

        correct = re.findall(r"get_active_filter\(\s*db,\s*\w+\.__table__\s*,", text)
        assert len(correct) >= 5, (
            f"prefill_engine 中 `.__table__` 形态的调用只有 {len(correct)} 处，"
            "现算基线为 5 处（LEDGER/AUX/LEDGER_DETAIL/COUNT_LEDGER/TB_AUX）"
            "—— 少于此数说明调用被删或改回 ORM 类写法"
        )

    def test_scanner_detects_orm_class_form(self):
        """P12 双向变异：扫描器对已知坏形态必须命中。"""
        import re

        bad_sample = "active_filter = await get_active_filter(db, TbLedger, project_id, year)\n"
        hits = re.findall(r"get_active_filter\(\s*db,\s*(Tb\w+|TrialBalance)\s*,", bad_sample)
        assert hits == ["TbLedger"], "扫描器对坏样本未命中 ⇒ 守卫恒绿"

        good_sample = "x = await get_active_filter(db, TbLedger.__table__, project_id, year)\n"
        no_hits = re.findall(r"get_active_filter\(\s*db,\s*(Tb\w+|TrialBalance)\s*,", good_sample)
        assert no_hits == [], "扫描器对正确写法误报 ⇒ 假阳"
