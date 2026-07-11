"""DraftRefreshOrchestrator（全局刷新生成编排层）单元测试.

公式管理库（formula-management-library）Task 16.1 / 设计 §18（Req 21.1-21.5）。

验证四条核心行为：

1. **按勾选 scope 分派产 units**（可 mock 各生成器）：``generate`` 仅对被勾选的合法
   scope 调 ``_dispatch`` 归集 units，交治理层 ``refresh_with_presets`` 打 Draft 标记。
2. **未勾选域零 units**：未被勾选的域不分派、不生成、不写入（Req 21.3）。
3. **affected_count == len(refreshed_units)**：治理层据真实喂入 units 得出，不再恒为 0
   （Req 21.4）。
4. **未知 scope 忽略**：不在 ``RefreshScopeDiscovery.discover`` 发现集合内的 scope 被
   忽略（warning，不静默丢弃、不分派）。

外加**真实 ``_dispatch`` 路由**测试（不 mock，仅桩注入各生成器入口）：report →
``report:{row_code}``；note → ``note:{section}!{r}:{c}``；workpaper/adjudication →
从 ``wp_index`` 派生 ``workpaper:{wp_code}`` page_keys；未识别 scope → ``([], [])``。

用内存 SQLite（``:memory:`` + ``aiosqlite``），每个测试独立引擎隔离；参考
``test_pbt_p03_idempotent.py`` 的 fixture / 种子模式。
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

import pytest
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
from app.models.report_models import FinancialReportType  # noqa: E402
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


def _seed_wp_index(codes: list[str]):
    return [
        WpIndex(
            project_id=PROJECT_ID, wp_code=code, wp_name=f"底稿{code}",
            status=WpStatus.not_started, is_deleted=False,
        )
        for code in codes
    ]


async def _count(db, model) -> int:
    return int(
        (await db.execute(sa.select(sa.func.count()).select_from(model))).scalar() or 0
    )


# ═══════════════════════════════════════════════════════════════════════════
# ① / ② / ③ / ④  —— generate 分派/隔离/计数/未知忽略（mock 各生成器）
# ═══════════════════════════════════════════════════════════════════════════
def _fake_dispatch_factory(dispatched: list[str], mapping: dict[str, list[str]]):
    """构造受控 _dispatch：记录被分派的 scope，按映射产出 unit_scope（page_keys 空）。"""

    async def _fake(scope, *, project_id, year):
        dispatched.append(scope)
        return [RefreshUnit(unit_scope=us) for us in mapping.get(scope, [])], []

    return _fake


def test_generate_dispatches_only_selected_scopes():
    """① 按勾选 scope 分派产 units；② 未勾选域零 units；③ affected_count 一致。

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
                # report→2 units, note→3 units, adjudication→若被分派会产 units（但不勾选）
                orch._dispatch = _fake_dispatch_factory(
                    dispatched,
                    {
                        "report": ["report:BS-1", "report:BS-2"],
                        "note": ["note:N1!0:1", "note:N1!0:2", "note:N2!1:1"],
                        "adjudication": ["audit_sheet:X:1"],
                    },
                )

                result, _app = await orch.generate(
                    project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
                    scopes=["report", "note"],
                )
                await db.commit()

                # ① 仅勾选的 report / note 被分派（② adjudication 未勾选 → 未分派）
                assert set(dispatched) == {"report", "note"}
                assert "adjudication" not in dispatched

                # ③ affected_count == len(refreshed_units) == 2 + 3
                assert result.status == "success", result.blocking
                assert result.affected_count == 5
                assert result.affected_count == len(result.refreshed_units)

                # ② 未勾选域（adjudication）零单元：refreshed 全落 report:/note: 前缀
                assert all(
                    us.startswith(("report:", "note:")) for us in result.refreshed_units
                )
                assert not any(
                    us.startswith("audit_sheet:") for us in result.refreshed_units
                )

                # 治理层已为 5 个单元打 Draft 标记
                assert await _count(db, DraftMarker) == 5
        finally:
            await engine.dispose()

    _run(_scenario())


def test_generate_unselected_domain_zero_writes():
    """② 只勾选 note 时，report 域完全不触碰（零 report: 单元 / 零标记）。

    **Validates: Requirements 21.3**
    """

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                db.add_all(_seed_tb_rows())
                await db.commit()

                orch = DraftRefreshOrchestrator(db)
                dispatched: list[str] = []
                orch._dispatch = _fake_dispatch_factory(
                    dispatched,
                    {
                        "report": ["report:BS-1"],
                        "note": ["note:N1!0:1"],
                    },
                )

                result, _ = await orch.generate(
                    project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
                    scopes=["note"],
                )
                await db.commit()

                assert dispatched == ["note"]
                assert result.refreshed_units == ["note:N1!0:1"]
                # report 域未被触碰
                markers = (
                    await db.execute(sa.select(DraftMarker.unit_scope))
                ).scalars().all()
                assert not any(m.startswith("report:") for m in markers)
        finally:
            await engine.dispose()

    _run(_scenario())


def test_generate_ignores_unknown_scope():
    """④ 未知 scope 被忽略（不分派、不生成）；合法 scope 正常处理。

    **Validates: Requirements 21.1, 21.3**
    """

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                db.add_all(_seed_tb_rows())
                await db.commit()

                orch = DraftRefreshOrchestrator(db)
                dispatched: list[str] = []
                orch._dispatch = _fake_dispatch_factory(
                    dispatched, {"report": ["report:BS-1"]}
                )

                result, _ = await orch.generate(
                    project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
                    scopes=["report", "totally-unknown-scope", "another_bogus"],
                )
                await db.commit()

                # 未知 scope 从未进入分派
                assert dispatched == ["report"]
                assert "totally-unknown-scope" not in dispatched
                assert "another_bogus" not in dispatched
                assert result.affected_count == 1
                assert result.refreshed_units == ["report:BS-1"]

                # 审计 detail.scopes 只记录实际执行的合法范围（Req 21.6）
                audit = (
                    await db.execute(
                        sa.select(DraftRefreshAudit).where(
                            DraftRefreshAudit.id == result.refresh_id
                        )
                    )
                ).scalar_one()
                assert audit.detail.get("scopes") == ["report"]
        finally:
            await engine.dispose()

    _run(_scenario())


# ═══════════════════════════════════════════════════════════════════════════
# 真实 _dispatch 路由（桩注入各生成器入口，验证 scope → 生成器映射）
# ═══════════════════════════════════════════════════════════════════════════
def test_dispatch_report_routes_to_report_engine(monkeypatch):
    """report scope → ReportEngine.generate_unadjusted_report，产 report:{row_code} 单元。

    **Validates: Requirements 21.1**
    """

    async def _scenario():
        factory, engine = await _make_session()
        try:
            import app.services.report_engine as report_engine_mod

            async def _fake_gen(self, project_id, year, report_type):
                return [{"row_code": f"{report_type.value}-1", "row_name": "x"}]

            monkeypatch.setattr(
                report_engine_mod.ReportEngine,
                "generate_unadjusted_report",
                _fake_gen,
            )

            async with factory() as db:
                orch = DraftRefreshOrchestrator(db)
                units, page_keys = await orch._dispatch(
                    "report", project_id=PROJECT_ID, year=YEAR
                )
                # 四张主表各产一行 → 4 个单元，全部 report: 前缀
                assert len(units) == len(_orch_report_types())
                assert all(u.unit_scope.startswith("report:") for u in units)
                assert page_keys == ["report:*"]
        finally:
            await engine.dispose()

    _run(_scenario())


def _orch_report_types():
    return [
        FinancialReportType.balance_sheet,
        FinancialReportType.income_statement,
        FinancialReportType.cash_flow_statement,
        FinancialReportType.equity_statement,
    ]


def test_dispatch_note_routes_to_execute_note_formulas(monkeypatch):
    """note scope → execute_note_formulas，仅 status=ok 单元产 note:{section}!{r}:{c}。

    **Validates: Requirements 21.1**
    """

    async def _scenario():
        factory, engine = await _make_session()
        try:
            import app.services.note_formula_generator as note_mod

            async def _fake_exec(db, project_id, year, note_section, **kw):
                return {
                    "results": [
                        {"cell": "2:3", "status": "ok"},
                        {"cell": "4:5", "status": "skipped"},
                    ]
                }

            monkeypatch.setattr(note_mod, "execute_note_formulas", _fake_exec)

            async with factory() as db:
                orch = DraftRefreshOrchestrator(db)

                async def _fake_sections(*, project_id, year):
                    return ["五、1"]

                orch._note_sections = _fake_sections

                units, page_keys = await orch._dispatch(
                    "note", project_id=PROJECT_ID, year=YEAR
                )
                # 仅 status=ok 的单元入选
                assert [u.unit_scope for u in units] == ["note:五、1!2:3"]
                assert page_keys == ["note:五、1"]
        finally:
            await engine.dispose()

    _run(_scenario())


def test_dispatch_workpaper_derives_page_keys_from_wp_index():
    """workpaper:{cycle} / adjudication → 从 wp_index 派生 workpaper:{wp_code} page_keys。

    **Validates: Requirements 21.1, 21.2**
    """

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                db.add_all(_seed_wp_index(["D3", "D3-1", "E1", "E1-1"]))
                await db.commit()

                orch = DraftRefreshOrchestrator(db)

                # 循环 D → 仅 D 前缀底稿
                units_d, pages_d = await orch._dispatch(
                    "workpaper:D", project_id=PROJECT_ID, year=YEAR
                )
                assert units_d == []  # 审定表 writeback 接口不匹配 → 经预设库 page_keys 生成
                assert set(pages_d) == {"workpaper:D3", "workpaper:D3-1"}

                # adjudication → 仅审定表页面（-1 结尾）
                units_a, pages_a = await orch._dispatch(
                    "adjudication", project_id=PROJECT_ID, year=YEAR
                )
                assert units_a == []
                assert set(pages_a) == {"workpaper:D3-1", "workpaper:E1-1"}
        finally:
            await engine.dispose()

    _run(_scenario())


def test_dispatch_unknown_scope_returns_empty():
    """未识别 scope → ([], [])（不分派、不生成、不写入，Req 21.3）。

    **Validates: Requirements 21.3**
    """

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                orch = DraftRefreshOrchestrator(db)
                units, page_keys = await orch._dispatch(
                    "nonsense-domain", project_id=PROJECT_ID, year=YEAR
                )
                assert units == []
                assert page_keys == []
        finally:
            await engine.dispose()

    _run(_scenario())
