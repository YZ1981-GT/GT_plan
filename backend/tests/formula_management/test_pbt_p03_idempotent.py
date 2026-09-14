# Feature: formula-management-library, Property 3: 一键刷新幂等
"""属性测试 P3：一键刷新幂等。

*对任意* 四表库快照 + 刷新范围（scope）+ 初稿单元集合（units），当四表库数据与
scope 均不变时，重复调用 ``DraftRefreshService.refresh`` 是幂等的：

- 第一次 refresh → ``status='success'``，写入一条 ``draft_refresh_audit``；
- 第二次（相同快照 + 相同 scope）refresh → ``status='idempotent_hit'``、
  ``idempotent is True``、``refresh_id`` 与第一次相同、且**不重复写审计**
  （``draft_refresh_audit`` 行数保持 1）；
- 一旦四表库数据发生变更（``tb_snapshot_hash`` 改变）→ 不再幂等：再次 refresh
  ``status='success'``、``idempotent is False``、审计行数增至 2。

被测：``app.services.draft_refresh_service.DraftRefreshService.refresh``
（幂等键 = ``tb_snapshot_hash`` + 归一化 ``scope``；见 service 文档）。

- 用内存 SQLite（``:memory:`` + ``aiosqlite``）建四表库
  （trial_balance / tb_balance / tb_ledger / tb_aux_balance）+ ``ledger_datasets``
  + ``draft_marker`` / ``draft_refresh_audit`` / ``draft_refresh_snapshot`` 三表，
  参考 ``backend/tests/test_draft_refresh_refresh.py`` 的 fixture / 种子模式。
- Hypothesis 随机生成四表库快照（账户 code + 非零金额，确保 precheck 通过）、
  scope（单值 / 多值）与 units（初稿单元集合）。

Framework: hypothesis（遵循 conftest fast profile，max_examples 可经
HYPOTHESIS_MAX_EXAMPLES 覆盖）。

**Validates: Requirements 3.1**
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import MetaData
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

# SQLite 测试方言：JSONB → JSON 编译；PG ARRAY → TEXT 兜底（建表所需）。
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

PROJECT_ID = uuid.uuid4()
YEAR = 2025

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


# ─────────────────────────────────────────────────────────────────────────────
# 事件循环辅助：refresh 为协程；每个 example 用独立内存引擎隔离。
# ─────────────────────────────────────────────────────────────────────────────
def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _make_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: MetaData().create_all(sync_conn, tables=_TEST_TABLES)
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return factory, engine


def _seed_rows(accounts: list[tuple[str, int]]):
    """由 (account_code, amount) 列表种子四表库核心两表。

    - tb_balance：closing_balance = amount（precheck 需 tb_balance 有行）。
    - trial_balance：unadjusted_amount = amount（precheck 需存在非零未审数）。

    amount 恒为正整数（生成器约束），保证 precheck 通过（不被 blocked）。
    """
    rows: list = []
    for code, amount in accounts:
        rows.append(
            TbBalance(
                project_id=PROJECT_ID,
                year=YEAR,
                company_code="C1",
                account_code=code,
                account_name=f"科目{code}",
                closing_balance=Decimal(amount),
            )
        )
        rows.append(
            TrialBalance(
                project_id=PROJECT_ID,
                year=YEAR,
                company_code="C1",
                standard_account_code=code,
                account_name=f"科目{code}",
                account_category=AccountCategory.asset,
                unadjusted_amount=Decimal(amount),
            )
        )
    return rows


async def _count(db, model) -> int:
    return int(
        (await db.execute(sa.select(sa.func.count()).select_from(model))).scalar() or 0
    )


# ─────────────────────────────────────────────────────────────────────────────
# 智能生成器：约束到 refresh 的输入空间（非零金额快照 + scope + units）。
# ─────────────────────────────────────────────────────────────────────────────

# 账户快照：唯一 code + 正整数金额（保证 precheck 通过、hash 确定）。
_SNAPSHOT = st.lists(
    st.tuples(
        st.integers(min_value=1000, max_value=9999).map(str),
        st.integers(min_value=1, max_value=1_000_000),
    ),
    min_size=1,
    max_size=5,
    unique_by=lambda t: t[0],
)

# scope：单值 或 多值序列（多值验证归一化排序后仍幂等）。
_SCOPE = st.sampled_from(
    [
        "report",
        "note",
        "audit_sheet",
        ("report", "note"),
        ("note", "report"),
    ]
)

# units：初稿单元集合（unit_scope 唯一，至少 1 个）。
_UNITS = st.lists(
    st.builds(lambda i: f"report:R-{i}", st.integers(min_value=0, max_value=50)),
    min_size=1,
    max_size=5,
    unique=True,
)


@given(accounts=_SNAPSHOT, scope=_SCOPE, unit_scopes=_UNITS)
@settings(max_examples=100)
def test_one_click_refresh_is_idempotent(accounts, scope, unit_scopes):
    """P3：相同快照 + scope 重复 refresh 幂等；数据变更后非幂等。

    **Validates: Requirements 3.1**
    """

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                db.add_all(_seed_rows(accounts))
                await db.commit()

                svc = DraftRefreshService()
                units = [RefreshUnit(s) for s in unit_scopes]

                # ── 第一次刷新：成功，写入一条审计 ──
                first = await svc.refresh(
                    db,
                    project_id=PROJECT_ID,
                    year=YEAR,
                    operator=_Operator(),
                    scope=scope,
                    units=units,
                )
                await db.commit()

                assert first.status == "success", first.blocking
                assert first.idempotent is False
                assert first.refresh_id is not None
                assert await _count(db, DraftRefreshAudit) == 1

                # ── 第二次刷新（相同快照 + 相同 scope）：幂等短路 ──
                second = await svc.refresh(
                    db,
                    project_id=PROJECT_ID,
                    year=YEAR,
                    operator=_Operator(),
                    scope=scope,
                    units=units,
                )
                await db.commit()

                # 幂等命中：status/idempotent/refresh_id 一致，且不重复写审计。
                assert second.status == "idempotent_hit"
                assert second.idempotent is True
                assert second.refresh_id == first.refresh_id
                assert second.tb_snapshot_hash == first.tb_snapshot_hash
                assert await _count(db, DraftRefreshAudit) == 1  # 未重复写审计

                # ── 数据变更 → 指纹改变 → 不再幂等 ──
                tb = (
                    await db.execute(sa.select(TrialBalance).limit(1))
                ).scalars().first()
                # 改为不同的正值（+1 保证既变更又非零）。
                tb.unadjusted_amount = (tb.unadjusted_amount or Decimal(0)) + Decimal(1)
                await db.commit()

                third = await svc.refresh(
                    db,
                    project_id=PROJECT_ID,
                    year=YEAR,
                    operator=_Operator(),
                    scope=scope,
                    units=units,
                )
                await db.commit()

                assert third.status == "success"
                assert third.idempotent is False
                assert third.tb_snapshot_hash != first.tb_snapshot_hash
                assert third.refresh_id != first.refresh_id
                assert await _count(db, DraftRefreshAudit) == 2  # 新增一条审计
        finally:
            await engine.dispose()

    _run(_scenario())
