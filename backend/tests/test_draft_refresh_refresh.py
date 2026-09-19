"""DraftRefreshService.refresh 幂等编排 + Draft 标记 + 审计留痕测试.

Task 5.3（formula-management-library）：验证 refresh 的五步编排——
① tb_snapshot_hash 幂等短路；② 未确认覆盖仅刷新非人工编辑单元；
③ 覆盖前写回滚快照；④ 生成初稿打 draft_marker state='draft'；
⑤ 写不可篡改 draft_refresh_audit。并验证 mark_human_edited（Req 3.4）。
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy import MetaData
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.audit_platform_models import (
    AccountCategory,
    TbAuxBalance,
    TbBalance,
    TbLedger,
    TrialBalance,
)
from app.models.dataset_models import LedgerDataset
from app.models.workpaper_models import (
    DraftMarker,
    DraftRefreshAudit,
    DraftRefreshSnapshot,
    WorkingPaper,
    WpFileStatus,
    WpSourceType,
)
from app.services.draft_refresh_service import (
    DraftRefreshService,
    RefreshResult,
    RefreshUnit,
)

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
if not hasattr(SQLiteTypeCompiler, "visit_ARRAY"):
    SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "TEXT"

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)

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
    WorkingPaper.__table__,
]


class _Operator:
    """最小 User 替身：refresh 只取 id / role。"""

    def __init__(self, role: str = "partner"):
        self.id = uuid.uuid4()
        self.role = role


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with test_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: MetaData().create_all(sync_conn, tables=_TEST_TABLES)
        )
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: MetaData().drop_all(sync_conn, tables=_TEST_TABLES)
        )


# ── 四表库最小种子（使 precheck 通过：tb_balance + trial_balance 有非零未审数）──


def _seed_core(**tb_kw):
    return [
        TbBalance(
            project_id=PROJECT_ID, year=YEAR, company_code="C1",
            account_code="1001", account_name="库存现金",
            closing_balance=Decimal("100"), **tb_kw,
        ),
        TrialBalance(
            project_id=PROJECT_ID, year=YEAR, company_code="C1",
            standard_account_code="1001", account_name="库存现金",
            account_category=AccountCategory.asset, unadjusted_amount=Decimal("100"),
        ),
    ]


async def _count(db, model) -> int:
    return int((await db.execute(sa.select(sa.func.count()).select_from(model))).scalar() or 0)


# ── ⑤ + ④ 基础：生成初稿打 Draft 标记 + 写审计 ─────────────────────


@pytest.mark.asyncio
async def test_refresh_creates_draft_markers_and_audit(db_session: AsyncSession):
    db_session.add_all(_seed_core())
    await db_session.commit()

    svc = DraftRefreshService()
    result = await svc.refresh(
        db_session,
        project_id=PROJECT_ID,
        year=YEAR,
        operator=_Operator(),
        scope="report",
        units=[RefreshUnit("report:BS-1"), RefreshUnit("report:BS-2")],
    )
    await db_session.commit()

    assert isinstance(result, RefreshResult)
    assert result.status == "success"
    assert result.idempotent is False
    assert result.affected_count == 2
    assert set(result.refreshed_units) == {"report:BS-1", "report:BS-2"}

    markers = (await db_session.execute(sa.select(DraftMarker))).scalars().all()
    assert {m.unit_scope for m in markers} == {"report:BS-1", "report:BS-2"}
    assert all(m.state == "draft" for m in markers)
    assert all(m.refresh_id == result.refresh_id for m in markers)

    audit = (await db_session.execute(sa.select(DraftRefreshAudit))).scalar_one()
    assert audit.id == result.refresh_id
    assert audit.project_id == PROJECT_ID
    assert audit.year == YEAR
    assert audit.scope == "report"
    assert audit.affected_count == 2
    assert audit.result_status == "success"
    assert audit.tb_snapshot_hash  # 非空指纹
    assert audit.detail["refreshed_units"] == ["report:BS-1", "report:BS-2"]


# ── ① 幂等短路 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_idempotent_same_snapshot(db_session: AsyncSession):
    db_session.add_all(_seed_core())
    await db_session.commit()

    svc = DraftRefreshService()
    first = await svc.refresh(
        db_session, project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
        scope="report", units=[RefreshUnit("report:BS-1")],
    )
    await db_session.commit()

    second = await svc.refresh(
        db_session, project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
        scope="report", units=[RefreshUnit("report:BS-1")],
    )
    await db_session.commit()

    assert second.status == "idempotent_hit"
    assert second.idempotent is True
    assert second.refresh_id == first.refresh_id
    # 幂等短路不重复写审计
    assert await _count(db_session, DraftRefreshAudit) == 1


@pytest.mark.asyncio
async def test_refresh_not_idempotent_when_data_changes(db_session: AsyncSession):
    db_session.add_all(_seed_core())
    await db_session.commit()

    svc = DraftRefreshService()
    await svc.refresh(
        db_session, project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
        scope="report", units=[RefreshUnit("report:BS-1")],
    )
    await db_session.commit()

    # 改动四表库 → 指纹变化 → 不再幂等
    tb = (await db_session.execute(sa.select(TrialBalance))).scalar_one()
    tb.unadjusted_amount = Decimal("999")
    await db_session.commit()

    second = await svc.refresh(
        db_session, project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
        scope="report", units=[RefreshUnit("report:BS-1")],
    )
    await db_session.commit()

    assert second.status == "success"
    assert second.idempotent is False
    assert await _count(db_session, DraftRefreshAudit) == 2


@pytest.mark.asyncio
async def test_scope_key_order_independent_idempotency(db_session: AsyncSession):
    """多值 scope 的顺序不影响幂等匹配。"""
    db_session.add_all(_seed_core())
    await db_session.commit()

    svc = DraftRefreshService()
    first = await svc.refresh(
        db_session, project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
        scope=["report", "note"], units=[RefreshUnit("report:BS-1")],
    )
    await db_session.commit()

    second = await svc.refresh(
        db_session, project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
        scope=["note", "report"], units=[RefreshUnit("report:BS-1")],
    )
    await db_session.commit()

    assert second.status == "idempotent_hit"
    assert second.refresh_id == first.refresh_id
    assert first.scope == "note,report"  # 归一化排序


# ── ② 覆盖排除 human_edited ──────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_skips_human_edited_when_not_confirmed(db_session: AsyncSession):
    db_session.add_all(_seed_core())
    db_session.add(
        DraftMarker(
            project_id=PROJECT_ID, year=YEAR,
            unit_scope="report:BS-1", state="human_edited",
        )
    )
    await db_session.commit()

    svc = DraftRefreshService()
    result = await svc.refresh(
        db_session, project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
        scope="report",
        units=[RefreshUnit("report:BS-1"), RefreshUnit("report:BS-2")],
        confirm_overwrite=False,
    )
    await db_session.commit()

    assert result.skipped_human_edited == ["report:BS-1"]
    assert result.refreshed_units == ["report:BS-2"]
    assert result.affected_count == 1

    # 人工编辑单元保持 human_edited 不被覆盖为 draft
    bs1 = (
        await db_session.execute(
            sa.select(DraftMarker).where(DraftMarker.unit_scope == "report:BS-1")
        )
    ).scalar_one()
    assert bs1.state == "human_edited"


@pytest.mark.asyncio
async def test_refresh_overwrites_human_edited_when_confirmed(db_session: AsyncSession):
    db_session.add_all(_seed_core())
    db_session.add(
        DraftMarker(
            project_id=PROJECT_ID, year=YEAR,
            unit_scope="report:BS-1", state="human_edited",
        )
    )
    await db_session.commit()

    svc = DraftRefreshService()
    result = await svc.refresh(
        db_session, project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
        scope="report",
        units=[RefreshUnit("report:BS-1", before_value={"v": 1})],
        confirm_overwrite=True,
    )
    await db_session.commit()

    assert result.skipped_human_edited == []
    assert result.refreshed_units == ["report:BS-1"]
    # ③ 覆盖前写回滚快照
    assert result.snapshotted_units == ["report:BS-1"]

    bs1 = (
        await db_session.execute(
            sa.select(DraftMarker).where(DraftMarker.unit_scope == "report:BS-1")
        )
    ).scalar_one()
    assert bs1.state == "draft"

    snap = (await db_session.execute(sa.select(DraftRefreshSnapshot))).scalar_one()
    assert snap.unit_scope == "report:BS-1"
    assert snap.before_value == {"v": 1}
    assert snap.refresh_id == result.refresh_id


# ── ③ 覆盖既有 draft 单元也写快照 ────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_snapshots_existing_draft_overwrite(db_session: AsyncSession):
    db_session.add_all(_seed_core())
    db_session.add(
        DraftMarker(
            project_id=PROJECT_ID, year=YEAR,
            unit_scope="report:BS-1", state="draft",
        )
    )
    await db_session.commit()

    svc = DraftRefreshService()
    # 改数据避免与不存在的历史审计冲突（本例首次刷新，无需）
    result = await svc.refresh(
        db_session, project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
        scope="report", units=[RefreshUnit("report:BS-1")],
    )
    await db_session.commit()

    assert result.snapshotted_units == ["report:BS-1"]
    snap = (await db_session.execute(sa.select(DraftRefreshSnapshot))).scalar_one()
    assert snap.before_value["marker_state"] == "draft"


@pytest.mark.asyncio
async def test_refresh_new_unit_no_snapshot(db_session: AsyncSession):
    """全新单元（无既有 marker、无 before_value）不写快照。"""
    db_session.add_all(_seed_core())
    await db_session.commit()

    svc = DraftRefreshService()
    result = await svc.refresh(
        db_session, project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
        scope="report", units=[RefreshUnit("report:BS-9")],
    )
    await db_session.commit()

    assert result.snapshotted_units == []
    assert await _count(db_session, DraftRefreshSnapshot) == 0


# ── 前置校验阻断 → 不写任何数据 ──────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_blocked_when_core_data_missing(db_session: AsyncSession):
    """空四表库（核心表缺失）→ status='blocked'，不写 marker/audit/snapshot。"""
    svc = DraftRefreshService()
    result = await svc.refresh(
        db_session, project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
        scope="report", units=[RefreshUnit("report:BS-1")],
    )
    await db_session.commit()

    assert result.status == "blocked"
    assert result.refresh_id is None
    assert result.blocking  # 缺失清单非空
    assert await _count(db_session, DraftMarker) == 0
    assert await _count(db_session, DraftRefreshAudit) == 0
    assert await _count(db_session, DraftRefreshSnapshot) == 0


# ── mark_human_edited（Req 3.4）──────────────────────────────────


@pytest.mark.asyncio
async def test_mark_human_edited_updates_existing_draft(db_session: AsyncSession):
    db_session.add(
        DraftMarker(
            project_id=PROJECT_ID, year=YEAR,
            unit_scope="report:BS-1", state="draft",
        )
    )
    await db_session.commit()

    svc = DraftRefreshService()
    marker = await svc.mark_human_edited(
        db_session, project_id=PROJECT_ID, year=YEAR, unit_scope="report:BS-1",
    )
    await db_session.commit()

    assert marker.state == "human_edited"
    assert await _count(db_session, DraftMarker) == 1


@pytest.mark.asyncio
async def test_mark_human_edited_creates_when_absent(db_session: AsyncSession):
    svc = DraftRefreshService()
    marker = await svc.mark_human_edited(
        db_session, project_id=PROJECT_ID, year=YEAR, unit_scope="report:NEW",
    )
    await db_session.commit()

    assert marker.state == "human_edited"
    assert marker.unit_scope == "report:NEW"
    assert await _count(db_session, DraftMarker) == 1


@pytest.mark.asyncio
async def test_marked_human_edited_then_refresh_skips_it(db_session: AsyncSession):
    """mark_human_edited 后，未确认覆盖的 refresh 会跳过该单元（Req 3.4 → 4.4 闭环）。"""
    db_session.add_all(_seed_core())
    await db_session.commit()

    svc = DraftRefreshService()
    await svc.mark_human_edited(
        db_session, project_id=PROJECT_ID, year=YEAR, unit_scope="report:BS-1",
    )
    await db_session.commit()

    result = await svc.refresh(
        db_session, project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
        scope="report", units=[RefreshUnit("report:BS-1")],
        confirm_overwrite=False,
    )
    await db_session.commit()

    assert result.skipped_human_edited == ["report:BS-1"]
    assert result.affected_count == 0


# ── Req 25.5：一键刷新生成初稿后触发受影响单元过时刷新（复用 prefill_stale）──


def _seed_working_paper(*, prefill_stale: bool = False) -> WorkingPaper:
    """最小 WorkingPaper 行（sqlite 不强制 FK；仅供 trigger_recalc 的 mark_stale 命中）。

    带 ``parsed_data.html_data``：mark_stale 只标记「持有已落库派生值」的底稿，
    从未编辑过的底稿渲染时实时取数、不存在过期状态，不再被无条件标脏。
    """
    return WorkingPaper(
        project_id=PROJECT_ID,
        wp_index_id=uuid.uuid4(),
        file_path="/tmp/wp.xlsx",
        source_type=WpSourceType.manual,
        status=WpFileStatus.draft,
        prefill_stale=prefill_stale,
        parsed_data={"html_data": {"rows": []}},
    )


@pytest.mark.asyncio
async def test_refresh_triggers_stale_recalc_after_draft(db_session: AsyncSession):
    """一键刷新生成初稿后经既有 prefill_stale 机制标下游底稿过时（Req 25.5）。

    复用 prefill_engine.mark_stale（不自建）：refresh 成功生成初稿单元后，
    项目内底稿被标 prefill_stale=True，供既有 /trial-balance/recalc 通道重算对齐。
    """
    db_session.add_all(_seed_core())
    db_session.add(_seed_working_paper(prefill_stale=False))
    await db_session.commit()

    svc = DraftRefreshService()
    result = await svc.refresh(
        db_session, project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
        scope="report", units=[RefreshUnit("report:BS-1")],
    )
    await db_session.commit()

    assert result.status == "success"
    # 至少 1 张底稿被标过时
    assert result.stale_marked_count >= 1
    wp = (await db_session.execute(sa.select(WorkingPaper))).scalar_one()
    assert wp.prefill_stale is True


@pytest.mark.asyncio
async def test_blocked_refresh_does_not_trigger_stale(db_session: AsyncSession):
    """前置校验阻断（核心表缺失）时不生成初稿，也不触发过时刷新（stale_marked_count=0）。"""
    db_session.add(_seed_working_paper(prefill_stale=False))
    await db_session.commit()

    svc = DraftRefreshService()
    result = await svc.refresh(
        db_session, project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
        scope="report", units=[RefreshUnit("report:BS-1")],
    )
    await db_session.commit()

    assert result.status == "blocked"
    assert result.stale_marked_count == 0
    wp = (await db_session.execute(sa.select(WorkingPaper))).scalar_one()
    assert wp.prefill_stale is False
