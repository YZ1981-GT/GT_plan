# Feature: formula-management-library, Property 22: 勾选范围=执行范围=留痕范围一致 ——
# 对任意非空勾选子集（含"底稿:循环{X}"循环粒度项），全局一键刷新仅对被勾选范围执行生成、
# 未勾选域数据快照逐一不变，且审计留痕（draft_refresh_audit.detail.scopes）记录的 scope
# 集合恰等于勾选集合（去重后）——即 勾选 == 执行 == 留痕。
"""P22 属性测试：勾选范围=执行范围=留痕范围一致.

公式管理库（formula-management-library）Task 16.4 / 设计 §18（Req 21）。

**Property 22: 勾选范围=执行范围=留痕范围一致**

*对任意*非空勾选子集（含 ``workpaper:{cycle}`` 循环粒度项），经
``DraftRefreshOrchestrator.generate`` 全局一键刷新后：

1. **执行范围 == 勾选范围（去重后）**：仅被勾选的合法 scope 被分派到生成器
   （``_dispatch`` 调用集合 == 勾选去重集合），未勾选域完全不触碰。
2. **未勾选域快照逐一不变**：所有实际刷新的初稿单元（``RefreshResult.refreshed_units``
   与落库的 ``DraftMarker.unit_scope``）都归属于被勾选 scope 的命名空间；不存在任何
   落在未勾选域命名空间的单元（未勾选域零写入 → 快照不变，Req 21.3）。
3. **留痕范围 == 勾选范围（去重后）**：审计留痕 ``draft_refresh_audit.detail.scopes``
   记录的 scope 集合恰等于勾选去重集合（Req 21.6 / 19.4）。

即三者相等：``set(勾选) == set(执行) == set(留痕)``。

**model-based 策略**：Hypothesis 从合法范围池（固定顶层域 report/adjudication/note +
若干循环粒度项 workpaper:{cycle}）随机抽取**可含重复**的非空列表作为勾选；用受控
``_dispatch`` 桩为每个被勾选 scope 产出其命名空间内的初稿单元（未勾选 scope 从不被调用
→ 零单元），交治理层 ``refresh_with_presets`` 统一编排。断言上述三集合相等且未勾选域零写入。

复用 Task 16.1（``test_draft_refresh_orchestrator.py``）的内存 SQLite fixture + mock
``_dispatch`` 模式。勾选取自合法发现集：report/adjudication/note 为固定顶层域恒合法；
``workpaper:{cycle}`` 经 ``RefreshScopeDiscovery`` 由 ``CYCLE_NAMES`` + 种子 ``wp_index``
判为合法。full_resolve / ACNR 不涉及（编排层不解析引用）。
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import MetaData
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

# SQLite 测试方言：JSONB → JSON 编译；PG ARRAY → TEXT；UUID → 兼容。
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
    WpStatus,
)
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

# ── 合法范围池：固定顶层域 + 循环粒度项（均在 RefreshScopeDiscovery 发现集合内）──
# report/adjudication/note 为固定模块域恒合法；workpaper:{D,E,F,G} 经 CYCLE_NAMES +
# 种子 wp_index 合法（含"底稿:循环{X}"循环粒度项，满足 Property 22 量化范围）。
_SCOPE_POOL: list[str] = [
    "report",
    "adjudication",
    "note",
    "workpaper:D",
    "workpaper:E",
    "workpaper:F",
    "workpaper:G",
]

# 种子 wp_index：使 workpaper:{cycle} 在发现集合内（双保险，独立于 CYCLE_NAMES）。
_SEED_WP_CODES = ["D3", "D3-1", "E1", "F1", "G5"]


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


def _seed_wp_index():
    return [
        WpIndex(
            project_id=PROJECT_ID, wp_code=code, wp_name=f"底稿{code}",
            status=WpStatus.not_started, is_deleted=False,
        )
        for code in _SEED_WP_CODES
    ]


def _scope_unit(scope: str, i: int) -> str:
    """构造归属于某 scope 命名空间的初稿单元 unit_scope（可反解回 scope）。

    用 ``||`` 分隔（scope 键内含 ``:`` 但不含 ``||``），保证反解无歧义。
    """
    return f"{scope}||u{i}"


def _scope_of_unit(unit_scope: str) -> str:
    """从初稿单元 unit_scope 反解其归属 scope（执行/写入范围判定）。"""
    return unit_scope.split("||", 1)[0]


def _controlled_dispatch_factory(dispatched: list[str]):
    """受控 ``_dispatch`` 桩：记录被分派的 scope，为其产 2 个命名空间内单元（page_keys 空）。

    未勾选 scope 从不被 ``generate`` 调用 → 其命名空间零单元（未勾选域快照不变）。
    """

    async def _fake(scope, *, project_id, year):
        dispatched.append(scope)
        units = [RefreshUnit(unit_scope=_scope_unit(scope, i)) for i in range(2)]
        return units, []

    return _fake


@settings(
    max_examples=5,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    # 可含重复的非空勾选列表 → 覆盖"留痕集合恰等于勾选去重集合"；含循环粒度项。
    selected_raw=st.lists(st.sampled_from(_SCOPE_POOL), min_size=1, max_size=10),
)
def test_p22_selected_equals_executed_equals_audited(selected_raw: list[str]):
    """勾选 == 执行 == 留痕；未勾选域快照逐一不变。

    **Validates: Requirements 19.4, 21.3, 21.6**
    """

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                db.add_all(_seed_tb_rows())
                db.add_all(_seed_wp_index())
                await db.commit()

                selected_set = set(selected_raw)  # 勾选去重集合

                orch = DraftRefreshOrchestrator(db)
                dispatched: list[str] = []
                orch._dispatch = _controlled_dispatch_factory(dispatched)

                result, _app = await orch.generate(
                    project_id=PROJECT_ID,
                    year=YEAR,
                    operator=_Operator(),
                    scopes=selected_raw,
                )
                await db.commit()

                assert result.status == "success", result.blocking
                assert result.refresh_id is not None

                # ── ① 执行范围 == 勾选范围（去重后）──────────────────────────
                #    仅被勾选的合法 scope 被分派；未勾选 scope 从不进入 _dispatch。
                assert set(dispatched) == selected_set

                # ── ③ 留痕范围 == 勾选范围（去重后）──────────────────────────
                audit = (
                    await db.execute(
                        sa.select(DraftRefreshAudit).where(
                            DraftRefreshAudit.id == result.refresh_id
                        )
                    )
                ).scalar_one()
                audited_scopes = audit.detail.get("scopes")
                assert audited_scopes is not None
                assert set(audited_scopes) == selected_set

                # ── 执行范围（由实际生成单元反解）== 勾选范围 ──────────────────
                executed_from_units = {
                    _scope_of_unit(us) for us in result.refreshed_units
                }
                assert executed_from_units == selected_set

                # ── 三集合相等：勾选 == 执行 == 留痕 ──────────────────────────
                assert selected_set == set(dispatched) == set(audited_scopes)

                # ── ② 未勾选域快照逐一不变：无任何单元落未勾选 scope 命名空间 ──
                unselected = set(_SCOPE_POOL) - selected_set
                marker_scopes = (
                    (await db.execute(sa.select(DraftMarker.unit_scope)))
                    .scalars()
                    .all()
                )
                for us in marker_scopes:
                    assert _scope_of_unit(us) not in unselected, (
                        f"未勾选域 {_scope_of_unit(us)!r} 出现初稿单元 {us!r}，"
                        f"违反未勾选域快照不变（勾选={sorted(selected_set)}）"
                    )
                # 落库 Draft 标记的执行范围亦恰等于勾选集合。
                assert {_scope_of_unit(us) for us in marker_scopes} == selected_set

                # ── affected_count 真实：每被勾选 scope 产 2 单元 ─────────────
                assert result.affected_count == len(result.refreshed_units)
                assert result.affected_count == len(selected_set) * 2
        finally:
            await engine.dispose()

    _run(_scenario())
