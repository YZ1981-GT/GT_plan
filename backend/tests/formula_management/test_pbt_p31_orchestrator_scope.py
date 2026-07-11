# Feature: formula-management-library, Property 31: 全局刷新按勾选范围生成初稿且范围隔离、affected_count 真实
"""属性测试 P31：全局刷新按勾选范围生成初稿且范围隔离、affected_count 真实。

*对任意*非空勾选子集（从 ``RefreshScopeDiscovery`` 合法 scope 集抽样，含
``workpaper:{cycle}`` 循环粒度项），经 ``DraftRefreshOrchestrator.generate`` 分派生成后：

- **(a) 范围内落域**：产出的所有 Draft_Unit 的 ``unit_scope`` 均落在**被勾选** scope
  对应域/循环的前缀内（``report:`` / ``adjudication:`` / ``note:`` /
  ``workpaper:{cycle}:``）。
- **(b) 范围隔离（未勾选域零写入）**：对任一**未被勾选**的合法 scope，刷新后无任何
  ``draft_marker`` 落在其域/循环前缀内（数据快照逐一不变）——``draft_marker`` 是本层
  唯一可观测的写入（各生成器经 ``_dispatch`` mock 隔离）。
- **(c) affected_count 真实**：``affected_count == len(refreshed_units)``（≥0），且被勾选
  域产出内容时 ``> 0``（不再恒为 0）。

**model-based**：Hypothesis 随机非空勾选子集；mock ``_dispatch`` 让各 scope 产出带该
scope 专属前缀的 units（page_keys 空 → 不经预设库另生单元）；断言 (a) refreshed_units
全落被勾选域前缀、(b) 未勾选域无单元、(c) ``affected_count == len(refreshed_units)``。

被测：``app.services.formula_management.draft_refresh_orchestrator.DraftRefreshOrchestrator``
（``generate`` → ``refresh_with_presets`` → ``refresh`` 治理链）。

- 用内存 SQLite（``:memory:`` + ``aiosqlite``）+ 方言 patch + 种子四表库两表保证
  ``precheck`` 通过（参考 ``test_draft_refresh_orchestrator.py`` / ``test_pbt_p03_idempotent.py``
  的 fixture / 种子模式）。
- 合法 scope 集与 ``RefreshScopeDiscovery.discover`` 共用口径：固定顶层域
  ``report`` / ``adjudication`` / ``note`` + ``dashboard_aggregator_service.CYCLE_NAMES``
  循环常量派生的 ``workpaper:{cycle}`` 项（后端单一真源）。

Framework: hypothesis（遵循 conftest fast profile；本测试显式 ``max_examples=5``）。

**Validates: Requirements 21.1, 21.3, 21.4**
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
    WpIndex,
)
from app.services.dashboard_aggregator_service import CYCLE_NAMES  # noqa: E402
from app.services.draft_refresh_service import RefreshUnit  # noqa: E402
from app.services.formula_management.draft_refresh_orchestrator import (  # noqa: E402
    DraftRefreshOrchestrator,
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
    WpIndex.__table__,
]


class _Operator:
    """最小 User 替身：refresh 只取 id / role。"""

    def __init__(self, role: str = "partner"):
        self.id = uuid.uuid4()
        self.role = role


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


def _seed_tb_rows():
    """种子四表库核心两表，保证 precheck 通过（非空 + 非零未审数）。"""
    rows: list = []
    for code, amount in [("1001", 1000), ("2001", 500)]:
        rows.append(
            TbBalance(
                project_id=PROJECT_ID, year=YEAR, company_code="C1",
                account_code=code, account_name=f"科目{code}",
                closing_balance=Decimal(amount),
            )
        )
        rows.append(
            TrialBalance(
                project_id=PROJECT_ID, year=YEAR, company_code="C1",
                standard_account_code=code, account_name=f"科目{code}",
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
# 合法 scope 集（与 RefreshScopeDiscovery.discover 共用口径）+ 每 scope 专属前缀。
# ─────────────────────────────────────────────────────────────────────────────
_CYCLE_KEYS = sorted({c.upper() for c in CYCLE_NAMES if c})
# 固定顶层域 + 循环粒度项：generate 会校验 scopes ⊆ discover 集合，这些键全部合法。
_CANDIDATE_SCOPES: list[str] = ["report", "adjudication", "note"] + [
    f"workpaper:{c}" for c in _CYCLE_KEYS
]


def _prefix_for(scope: str) -> str:
    """一个 scope 对应域/循环的 unit_scope 专属前缀（用于范围落域/隔离判定）。

    各前缀两两互不为对方前缀（顶层域 vs ``workpaper:{cycle}:`` vs 不同循环），
    从而 (a) 落域 与 (b) 范围隔离 可精确判定，且体现循环粒度隔离。
    """
    if scope.startswith("workpaper:"):
        cycle = scope.split(":", 1)[1]
        return f"workpaper:{cycle}:"
    return f"{scope}:"


def _fake_dispatch_factory(dispatched: list[str]):
    """受控 _dispatch：记录被分派 scope，按 scope 专属前缀产 2 个 unit（page_keys 空）。

    page_keys 返回空 → ``refresh_with_presets`` 不经预设库另生单元，refreshed_units
    即等于本 mock 产出的 units（便于精确断言范围与计数）。
    """

    async def _fake(scope, *, project_id, year):
        dispatched.append(scope)
        prefix = _prefix_for(scope)
        units = [RefreshUnit(unit_scope=f"{prefix}u{i}") for i in range(2)]
        return units, []

    return _fake


# 非空勾选子集：从合法 scope 集抽样，去重、保序无关（generate 内部保序去重）。
_SELECTED = st.lists(
    st.sampled_from(_CANDIDATE_SCOPES),
    min_size=1,
    max_size=min(6, len(_CANDIDATE_SCOPES)),
    unique=True,
)


@given(selected=_SELECTED)
@settings(max_examples=5)
def test_global_refresh_scope_isolation_and_affected_count(selected):
    """P31：全局刷新按勾选范围生成初稿、范围隔离、affected_count 真实。

    **Validates: Requirements 21.1, 21.3, 21.4**
    """

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                db.add_all(_seed_tb_rows())
                await db.commit()

                orch = DraftRefreshOrchestrator(db)
                dispatched: list[str] = []
                orch._dispatch = _fake_dispatch_factory(dispatched)

                result, _app = await orch.generate(
                    project_id=PROJECT_ID,
                    year=YEAR,
                    operator=_Operator(),
                    scopes=selected,
                )
                await db.commit()

                assert result.status == "success", result.blocking

                selected_set = set(selected)
                selected_prefixes = tuple(_prefix_for(s) for s in selected_set)

                # 仅被勾选的合法 scope 被分派（Req 21.1）。
                assert set(dispatched) == selected_set

                # ── (a) 范围内落域：每个 refreshed unit 落某个被勾选域/循环前缀 ──
                for us in result.refreshed_units:
                    assert us.startswith(selected_prefixes), (
                        f"unit {us!r} 未落在被勾选范围 {sorted(selected_set)} 内"
                    )

                # ── (b) 范围隔离：任一未勾选合法 scope 的前缀下零单元（数据快照不变）──
                markers = (
                    (await db.execute(sa.select(DraftMarker.unit_scope)))
                    .scalars()
                    .all()
                )
                for scope in _CANDIDATE_SCOPES:
                    if scope in selected_set:
                        continue
                    unsel_prefix = _prefix_for(scope)
                    assert not any(us.startswith(unsel_prefix) for us in markers), (
                        f"未勾选 scope {scope!r} 的域被写入了 draft_marker"
                    )
                    assert not any(
                        us.startswith(unsel_prefix) for us in result.refreshed_units
                    )

                # ── (c) affected_count == len(refreshed_units)，勾选域有内容 → > 0 ──
                assert result.affected_count == len(result.refreshed_units)
                assert result.affected_count == 2 * len(selected_set)
                assert result.affected_count > 0

                # 治理层为每个刷新单元打了 Draft 标记（写入=刷新单元数）。
                assert await _count(db, DraftMarker) == result.affected_count
        finally:
            await engine.dispose()

    _run(_scenario())
