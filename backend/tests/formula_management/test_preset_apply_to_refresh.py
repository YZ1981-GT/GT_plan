"""预设套用到一键刷新/底稿生成测试（Task 14.2 / Req 22.4, 22.6）。

覆盖：
- ``DraftRefreshService.build_preset_draft_units`` 按 page_key 查预设库：
  已预设页面（presetted）套用预设公式为初稿单元（来源标 preset）；
  未预设页面（pending）跳过保留现状（无回归）。
- ``refresh_with_presets`` 把预设初稿单元 + 上游 extra_units 合并编排刷新，
  刷新审计明细追加预设套用统计；pending 页不生成单元。
- 预设库不可用时按页跳过、不阻断刷新（fail-open，无回归）。
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

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
    PresetApplication,
    RefreshUnit,
)
from app.services.formula_management.preset_library import PresetEntry  # noqa: E402

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


def _seed_rows():
    """种子四表库核心两表，保证 precheck 通过（tb_balance 有行 + 非零未审数）。"""
    rows: list = []
    for code, amount in [("1001", 100), ("1002", 200)]:
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


# 桩预设索引：D3-1 已预设两条，report:BS 已预设一条；其余页面 pending。
def _stub_index() -> dict[str, list[PresetEntry]]:
    return {
        "workpaper:D3-1": [
            PresetEntry(
                page_key="workpaper:D3-1",
                target_cell="B5",
                expression="=TB('1001')",
                formula_type="auto_calc",
                refs=[{"formula_ref": "TB('1001')"}],
                source="prefill_formula_mapping",
            ),
            PresetEntry(
                page_key="workpaper:D3-1",
                target_cell="B6",
                expression="=TB('1002')",
                formula_type="auto_calc",
                refs=[{"formula_ref": "TB('1002')"}],
                source="prefill_formula_mapping",
            ),
        ],
        "report:BS": [
            PresetEntry(
                page_key="report:BS",
                target_cell="ASSET_TOTAL",
                expression="=ROW('BS-1')+ROW('BS-2')",
                formula_type="logic_check",
                refs=[{"formula_ref": "ROW('BS-1')"}],
                source="seed",
            ),
        ],
    }


# ── build_preset_draft_units：presetted 套用 / pending 跳过（Req 22.4, 22.6） ──
def test_presetted_pages_produce_draft_units_pending_skipped():
    svc = DraftRefreshService()
    app = svc.build_preset_draft_units(
        ["workpaper:D3-1", "report:BS", "workpaper:D9-2"],  # 最后一页 pending
        preset_index=_stub_index(),
    )
    assert isinstance(app, PresetApplication)
    # 已预设两页共 3 条预设 → 3 个初稿单元
    assert app.preset_count == 3
    assert set(app.presetted_pages) == {"workpaper:D3-1", "report:BS"}
    # 未预设页跳过保留现状（无回归）
    assert app.pending_pages == ["workpaper:D9-2"]

    scopes = {u.unit_scope for u in app.units}
    assert scopes == {
        "workpaper:D3-1:B5",
        "workpaper:D3-1:B6",
        "report:BS:ASSET_TOTAL",
    }
    # 初稿单元 after_value 承载预设来源与三类型
    for u in app.units:
        assert u.after_value["source"] == "preset"
        assert u.after_value["formula_type"] in {
            "auto_calc",
            "logic_check",
            "reasonability",
        }
        assert u.before_value is None


def test_build_preset_draft_units_dedups_page_keys():
    """重复 page_key 只处理一次（保序去重）。"""
    svc = DraftRefreshService()
    app = svc.build_preset_draft_units(
        ["workpaper:D3-1", "workpaper:D3-1"], preset_index=_stub_index()
    )
    assert app.presetted_pages == ["workpaper:D3-1"]
    assert app.preset_count == 2  # 该页两条预设，不因重复 page_key 翻倍


def test_all_pending_no_units_no_regression():
    """全部未预设页面 → 不产出任何单元，保留现状（无回归）。"""
    svc = DraftRefreshService()
    app = svc.build_preset_draft_units(
        ["workpaper:ZZ-1", "note:zz"], preset_index=_stub_index()
    )
    assert app.preset_count == 0
    assert app.presetted_pages == []
    assert set(app.pending_pages) == {"workpaper:ZZ-1", "note:zz"}


def test_preset_index_failure_fail_open(monkeypatch):
    """预设库构建失败时按页跳过、不抛异常（fail-open，无回归）。"""
    import app.services.formula_management.preset_library as pl

    def _boom():
        raise RuntimeError("preset library unavailable")

    monkeypatch.setattr(pl, "build_preset_index", _boom)
    svc = DraftRefreshService()
    # 不传 preset_index → 触发内部构建失败 → 全部页面 pending，无单元
    app = svc.build_preset_draft_units(["workpaper:D3-1", "report:BS"])
    assert app.preset_count == 0
    assert set(app.pending_pages) == {"workpaper:D3-1", "report:BS"}


# ── refresh_with_presets：套用 + 编排 + 审计明细统计 ─────────────────────────
def test_refresh_with_presets_applies_and_records():
    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                db.add_all(_seed_rows())
                await db.commit()

                svc = DraftRefreshService()
                extra = [RefreshUnit("note:N1")]  # 上游引擎产出的非预设初稿单元
                result, app = await svc.refresh_with_presets(
                    db,
                    project_id=PROJECT_ID,
                    year=YEAR,
                    operator=_Operator(),
                    scope="report",
                    page_keys=["workpaper:D3-1", "report:BS", "workpaper:PENDING-1"],
                    extra_units=extra,
                    preset_index=_stub_index(),
                )
                await db.commit()

                assert result.status == "success", result.blocking
                # 预设 3 条 + 上游 1 条 = 4 个刷新单元
                assert result.affected_count == 4
                assert app.preset_count == 3
                assert app.pending_pages == ["workpaper:PENDING-1"]

                # Draft 标记写入 4 个单元
                marker_count = int(
                    (
                        await db.execute(
                            sa.select(sa.func.count()).select_from(DraftMarker)
                        )
                    ).scalar()
                    or 0
                )
                assert marker_count == 4

                # 审计明细追加预设套用统计
                audit = (
                    await db.execute(
                        sa.select(DraftRefreshAudit).where(
                            DraftRefreshAudit.id == result.refresh_id
                        )
                    )
                ).scalar_one()
                pa = audit.detail.get("preset_application")
                assert pa is not None
                assert pa["preset_count"] == 3
                assert pa["pending_pages"] == ["workpaper:PENDING-1"]
                assert set(pa["presetted_pages"]) == {"workpaper:D3-1", "report:BS"}
        finally:
            await engine.dispose()

    _run(_scenario())


def test_refresh_with_presets_all_pending_only_extra_units():
    """全部页面 pending 时仅编排上游 extra_units（预设不产单元，无回归）。"""

    async def _scenario():
        factory, engine = await _make_session()
        try:
            async with factory() as db:
                db.add_all(_seed_rows())
                await db.commit()

                svc = DraftRefreshService()
                result, app = await svc.refresh_with_presets(
                    db,
                    project_id=PROJECT_ID,
                    year=YEAR,
                    operator=_Operator(),
                    scope="note",
                    page_keys=["workpaper:PENDING-1", "note:pending"],
                    extra_units=[RefreshUnit("note:N1")],
                    preset_index=_stub_index(),
                )
                await db.commit()

                assert result.status == "success", result.blocking
                assert app.preset_count == 0
                assert result.affected_count == 1  # 仅上游单元
                assert set(app.pending_pages) == {"workpaper:PENDING-1", "note:pending"}
        finally:
            await engine.dispose()

    _run(_scenario())
