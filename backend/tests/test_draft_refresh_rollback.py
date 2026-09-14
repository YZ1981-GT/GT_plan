"""DraftRefreshService.rollback 回滚测试.

Task 5.4（formula-management-library）：验证 rollback 依据 draft_refresh_snapshot
恢复刷新前状态——
① 覆盖既有 draft/human_edited 单元后回滚 → marker 状态精确还原；
② 刷新新建的全新单元回滚 → marker 被删除（恢复"无标记"）；
③ confirm_overwrite 覆盖人工编辑单元回滚 → 依 editor_id 还原为 human_edited；
④ 审计记录标 result_status='rolled_back' 且回滚后同快照再刷新不再幂等短路；
⑤ not_found / already_rolled_back 守卫。
_Requirements: 4.5_
"""
from __future__ import annotations

import uuid
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
)
from app.services.draft_refresh_service import (
    DraftRefreshService,
    RefreshUnit,
    RollbackResult,
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
]


class _Operator:
    """最小 User 替身：refresh/rollback 只取 id / role。"""

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


def _seed_core():
    return [
        TbBalance(
            project_id=PROJECT_ID, year=YEAR, company_code="C1",
            account_code="1001", account_name="库存现金",
            closing_balance=Decimal("100"),
        ),
        TrialBalance(
            project_id=PROJECT_ID, year=YEAR, company_code="C1",
            standard_account_code="1001", account_name="库存现金",
            account_category=AccountCategory.asset, unadjusted_amount=Decimal("100"),
        ),
    ]


async def _count(db, model) -> int:
    return int((await db.execute(sa.select(sa.func.count()).select_from(model))).scalar() or 0)


async def _marker(db, unit_scope: str) -> DraftMarker | None:
    return (
        await db.execute(
            sa.select(DraftMarker).where(DraftMarker.unit_scope == unit_scope)
        )
    ).scalar_one_or_none()


# ── ① 覆盖既有 draft 单元后回滚 → marker 状态精确还原 ──────────────


@pytest.mark.asyncio
async def test_rollback_restores_overwritten_draft_marker(db_session: AsyncSession):
    db_session.add_all(_seed_core())
    db_session.add(
        DraftMarker(
            project_id=PROJECT_ID, year=YEAR,
            unit_scope="report:BS-1", state="draft",
        )
    )
    await db_session.commit()

    svc = DraftRefreshService()
    refreshed = await svc.refresh(
        db_session, project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
        scope="report", units=[RefreshUnit("report:BS-1")],
    )
    await db_session.commit()
    # 覆盖前写了快照（marker_state 元信息）
    assert refreshed.snapshotted_units == ["report:BS-1"]

    result = await svc.rollback(
        db_session, refresh_id=refreshed.refresh_id, operator=_Operator(),
    )
    await db_session.commit()

    assert isinstance(result, RollbackResult)
    assert result.status == "rolled_back"
    assert result.restored_markers == ["report:BS-1"]
    assert result.removed_markers == []
    assert result.restored_count == 1

    # marker 状态还原为刷新前的 draft，且脱离本次 refresh_id
    bs1 = await _marker(db_session, "report:BS-1")
    assert bs1 is not None
    assert bs1.state == "draft"
    assert bs1.refresh_id is None


# ── ② 刷新新建的全新单元回滚 → marker 被删除 ─────────────────────


@pytest.mark.asyncio
async def test_rollback_removes_new_unit_marker(db_session: AsyncSession):
    db_session.add_all(_seed_core())
    await db_session.commit()

    svc = DraftRefreshService()
    refreshed = await svc.refresh(
        db_session, project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
        scope="report", units=[RefreshUnit("report:BS-9")],
    )
    await db_session.commit()
    assert refreshed.snapshotted_units == []  # 全新单元无快照
    assert await _count(db_session, DraftMarker) == 1

    result = await svc.rollback(
        db_session, refresh_id=refreshed.refresh_id, operator=_Operator(),
    )
    await db_session.commit()

    assert result.status == "rolled_back"
    assert result.removed_markers == ["report:BS-9"]
    assert result.restored_markers == []
    # 新建单元的 marker 被删除，恢复"无标记"
    assert await _count(db_session, DraftMarker) == 0


# ── ③ confirm_overwrite 覆盖人工编辑单元回滚 → 还原 human_edited ──


@pytest.mark.asyncio
async def test_rollback_restores_human_edited_via_editor_id(db_session: AsyncSession):
    editor = uuid.uuid4()
    db_session.add_all(_seed_core())
    db_session.add(
        DraftMarker(
            project_id=PROJECT_ID, year=YEAR,
            unit_scope="report:BS-1", state="human_edited",
        )
    )
    await db_session.commit()

    svc = DraftRefreshService()
    refreshed = await svc.refresh(
        db_session, project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
        scope="report",
        units=[RefreshUnit("report:BS-1", before_value={"v": 1}, editor_id=editor)],
        confirm_overwrite=True,
    )
    await db_session.commit()
    assert refreshed.snapshotted_units == ["report:BS-1"]

    result = await svc.rollback(
        db_session, refresh_id=refreshed.refresh_id, operator=_Operator(),
    )
    await db_session.commit()

    assert result.status == "rolled_back"
    assert result.restored_markers == ["report:BS-1"]
    # 快照存业务数据 + editor_id → 还原为 human_edited
    bs1 = await _marker(db_session, "report:BS-1")
    assert bs1.state == "human_edited"

    # 恢复内容回给调用方（含 before_value + editor_id）
    assert len(result.restored_units) == 1
    ru = result.restored_units[0]
    assert ru.unit_scope == "report:BS-1"
    assert ru.before_value == {"v": 1}
    assert ru.editor_id == editor


# ── ④ 审计标 rolled_back + 回滚后同快照再刷新不再幂等 ────────────


@pytest.mark.asyncio
async def test_rollback_marks_audit_and_reenables_refresh(db_session: AsyncSession):
    db_session.add_all(_seed_core())
    await db_session.commit()

    svc = DraftRefreshService()
    refreshed = await svc.refresh(
        db_session, project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
        scope="report", units=[RefreshUnit("report:BS-9")],
    )
    await db_session.commit()

    op = _Operator()
    await svc.rollback(db_session, refresh_id=refreshed.refresh_id, operator=op)
    await db_session.commit()

    audit = (
        await db_session.execute(
            sa.select(DraftRefreshAudit).where(DraftRefreshAudit.id == refreshed.refresh_id)
        )
    ).scalar_one()
    assert audit.result_status == "rolled_back"
    assert audit.detail["rollback"]["operator_id"] == str(op.id)
    assert audit.detail["rollback"]["restored_count"] == 0
    # 原刷新明细保留
    assert audit.detail["refreshed_units"] == ["report:BS-9"]

    # 回滚后相同快照再次刷新 → 真正重新执行（不再幂等短路命中旧记录）
    again = await svc.refresh(
        db_session, project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
        scope="report", units=[RefreshUnit("report:BS-9")],
    )
    await db_session.commit()
    assert again.status == "success"
    assert again.idempotent is False
    assert again.refresh_id != refreshed.refresh_id
    assert await _count(db_session, DraftRefreshAudit) == 2


# ── ⑤ 守卫：not_found / already_rolled_back ─────────────────────


@pytest.mark.asyncio
async def test_rollback_not_found(db_session: AsyncSession):
    svc = DraftRefreshService()
    missing = uuid.uuid4()
    result = await svc.rollback(db_session, refresh_id=missing, operator=_Operator())
    await db_session.commit()

    assert result.status == "not_found"
    assert result.refresh_id == missing
    assert result.restored_count == 0


@pytest.mark.asyncio
async def test_rollback_already_rolled_back_is_noop(db_session: AsyncSession):
    db_session.add_all(_seed_core())
    await db_session.commit()

    svc = DraftRefreshService()
    refreshed = await svc.refresh(
        db_session, project_id=PROJECT_ID, year=YEAR, operator=_Operator(),
        scope="report", units=[RefreshUnit("report:BS-1")],
    )
    await db_session.commit()

    first = await svc.rollback(
        db_session, refresh_id=refreshed.refresh_id, operator=_Operator(),
    )
    await db_session.commit()
    assert first.status == "rolled_back"

    # 二次回滚 → 幂等空操作
    second = await svc.rollback(
        db_session, refresh_id=refreshed.refresh_id, operator=_Operator(),
    )
    await db_session.commit()
    assert second.status == "already_rolled_back"
    assert second.restored_count == 0
