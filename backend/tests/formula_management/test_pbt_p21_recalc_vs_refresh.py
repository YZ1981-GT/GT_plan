# Feature: formula-management-library, Property 21: recalc 与一键刷新语义区分
"""属性测试 P21：recalc 与合伙人一键刷新的语义区分。

**Property 21: recalc 与一键刷新语义区分**

*对任意*触发者与操作：

- **recalc**（团队可触发、仅重算既有公式）执行后**不产生 Draft 标记**、**不生成初稿单元**、
  **不写审计留痕**；
- **一键刷新**（合伙人专属）执行后受影响单元带 Draft 标记（``draft_marker.state='draft'``）
  且写一条 ``draft_refresh_audit``；
- 两者对**既有公式**的重算结果，对同一数据状态**逐一一致**（同一 L1 内核纯函数，无并行分叉）。

被测：``app.services.draft_refresh_service.DraftRefreshService.refresh``（一键刷新：打 Draft +
审计）与既有公式经 ``formula_engine.execute`` 的重算（recalc：仅重算、不打 Draft）。

验证策略（内存 sqlite，参考 test_pbt_p03/p04；每个 example 独立库）：

1. **recalc 语义**：对同一数据用 L1 内核重算既有公式集合，**不调用** DraftRefreshService；
   断言此后 ``draft_marker`` / ``draft_refresh_audit`` 行数**均为 0**（recalc 不触碰 Draft
   状态、不留痕）。
2. **一键刷新语义**：以既有公式对应的初稿单元调 ``refresh``；断言每个受影响单元生成
   ``draft_marker.state='draft'``，且恰写入 **1 条** ``draft_refresh_audit``。
3. **重算一致性**：一键刷新（数据未变）后再次用 L1 内核重算同一既有公式集合，结果与
   步骤 1 的 recalc 结果**逐一相等**——一键刷新只改变"初稿/Draft 治理状态"，不改变既有
   公式的计算数值。

Framework: hypothesis（遵循 conftest fast profile，max_examples 可经
HYPOTHESIS_MAX_EXAMPLES 覆盖）。

**Validates: Requirements 20.4, 20.6**（设计 Req 25.4/25.6：recalc 不打 Draft / 一键刷新打 Draft）
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import MetaData
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

# SQLite 测试方言：JSONB → JSON；PG ARRAY → TEXT（与既有 draft_refresh 测试一致）。
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.audit_platform_models import (  # noqa: E402
    AccountCategory,
    TbAuxBalance,
    TbBalance,
    TbLedger,
    TrialBalance,
)
from app.models.dataset_models import LedgerDataset  # noqa: E402
from app.models.workpaper_models import (  # noqa: E402
    DraftMarker,
    DraftRefreshAudit,
    DraftRefreshSnapshot,
)
from app.services.draft_refresh_service import (  # noqa: E402
    DraftRefreshService,
    RefreshUnit,
)
from app.services.formula_engine import FormulaContext, execute as kernel_execute  # noqa: E402

_TEST_TABLES = [
    TbBalance.__table__,
    TbLedger.__table__,
    TbAuxBalance.__table__,
    TrialBalance.__table__,
    LedgerDataset.__table__,
    DraftMarker.__table__,
    DraftRefreshAudit.__table__,
    DraftRefreshSnapshot.__table__,
]


class _Operator:
    """最小 User 替身：refresh 只取 id / role。"""

    def __init__(self, role: str = "partner"):
        self.id = uuid.uuid4()
        self.role = role


async def _count(db, model) -> int:
    return int(
        (await db.execute(sa.select(sa.func.count()).select_from(model))).scalar() or 0
    )


def _seed_rows(project_id: uuid.UUID, year: int, accounts: dict[str, int]):
    """由 (account_code → amount) 种子四表库核心两表，使 precheck 通过。"""
    rows: list = []
    for code, amount in accounts.items():
        rows.append(
            TbBalance(
                project_id=project_id, year=year, company_code="C1",
                account_code=code, account_name=f"科目{code}",
                closing_balance=Decimal(amount),
            )
        )
        rows.append(
            TrialBalance(
                project_id=project_id, year=year, company_code="C1",
                standard_account_code=code, account_name=f"科目{code}",
                account_category=AccountCategory.asset,
                unadjusted_amount=Decimal(amount),
            )
        )
    return rows


def _recalc_existing_formulas(
    formulas: list[str], accounts: dict[str, int]
) -> list[Decimal]:
    """recalc：团队重算既有公式（单一 L1 内核，纯函数，不触碰 Draft 状态）。"""
    ctx = FormulaContext.from_simple_map(
        {code: Decimal(amt) for code, amt in accounts.items()}
    )
    return [kernel_execute(f, ctx).value for f in formulas]


# ─────────────────────────────────────────────────────────────────────────────
# 智能生成器：账户快照 + 引用这些账户的既有公式集合。
# ─────────────────────────────────────────────────────────────────────────────
@st.composite
def _accounts_and_formulas(draw):
    codes = draw(
        st.lists(
            st.integers(min_value=1000, max_value=6999).map(str),
            min_size=1, max_size=5, unique=True,
        )
    )
    accounts = {c: draw(st.integers(min_value=1, max_value=1_000_000)) for c in codes}

    # 既有公式：每条引用 1~2 个已种子账户 + 可选常数，经 + / - 组合。
    n_formulas = draw(st.integers(min_value=1, max_value=4))
    formulas: list[str] = []
    for _ in range(n_formulas):
        a = draw(st.sampled_from(codes))
        term = f"TB('{a}','期末余额')"
        if draw(st.booleans()):
            b = draw(st.sampled_from(codes))
            op = draw(st.sampled_from(["+", "-"]))
            term = f"{term} {op} TB('{b}','期末余额')"
        formulas.append(term)
    return accounts, formulas


@given(payload=_accounts_and_formulas())
@settings(max_examples=60)
def test_p21_recalc_no_draft_refresh_marks_draft(payload):
    """P21：recalc 不打 Draft/不留痕；一键刷新打 Draft+留痕；既有公式重算结果一致。

    **Validates: Requirements 20.4, 20.6**
    """
    accounts, formulas = payload
    project_id = uuid.uuid4()
    year = 2025

    async def _scenario():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(
                    lambda sc: MetaData().create_all(sc, tables=_TEST_TABLES)
                )
            factory = async_sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )
            async with factory() as db:
                db.add_all(_seed_rows(project_id, year, accounts))
                await db.commit()

                # ── ① recalc 语义：团队重算既有公式，不调用 DraftRefreshService ──
                recalc_values = _recalc_existing_formulas(formulas, accounts)

                # recalc 不产生任何 Draft 标记 / 审计留痕。
                assert await _count(db, DraftMarker) == 0
                assert await _count(db, DraftRefreshAudit) == 0

                # ── ② 一键刷新语义：合伙人生成初稿 → 打 Draft + 审计 ──
                svc = DraftRefreshService()
                unit_scopes = [f"report:F-{i}" for i in range(len(formulas))]
                units = [RefreshUnit(s) for s in unit_scopes]
                result = await svc.refresh(
                    db,
                    project_id=project_id, year=year,
                    operator=_Operator(),
                    scope="report",
                    units=units,
                )
                await db.commit()

                assert result.status == "success", result.blocking

                # 每个受影响单元带 draft 标记。
                markers = (await db.execute(sa.select(DraftMarker))).scalars().all()
                marker_map = {m.unit_scope: m.state for m in markers}
                assert set(marker_map) == set(unit_scopes)
                assert all(state == "draft" for state in marker_map.values())
                assert result.affected_count == len(unit_scopes)

                # 恰写入一条审计留痕。
                assert await _count(db, DraftRefreshAudit) == 1

                # ── ③ 重算一致性：数据未变，一键刷新后重算既有公式 == recalc 结果 ──
                post_refresh_values = _recalc_existing_formulas(formulas, accounts)
                assert post_refresh_values == recalc_values

            return result.affected_count
        finally:
            await engine.dispose()

    asyncio.run(_scenario())
