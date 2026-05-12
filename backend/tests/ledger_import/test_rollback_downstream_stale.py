"""F46 / Sprint 7.21-7.23: rollback 事件联动下游 is_stale 标记。

覆盖 design D11.4 不变量：
1. ``DatasetService.rollback`` 在事务内写入 ``import_event_outbox``，
   event_type=``LEDGER_DATASET_ROLLED_BACK``；
2. payload 同时保留历史键（rolled_back_dataset_id/restored_dataset_id）
   和 F46 新增键（old_dataset_id/new_active_dataset_id/project_id/year），
   确保下游 handler 能按 design 文档消费；
3. 事件派发后 ``event_handlers._mark_downstream_stale_on_rollback``
   把匹配 project+year 的 AuditReport / DisclosureNote 标 is_stale=True；
4. Workpaper 的 stale 走既有 ``_mark_workpapers_stale_all``（prefill_stale=True），
   本测试不重复验证（已在 phase 9 覆盖），只保证 rollback 订阅链路没断。

Fixture 模式：SQLite 内存库 + PG JSONB/UUID 降级，同 test_cross_project_isolation.py。
事件派发用 ``event_bus.publish_immediate`` 同步触发，避免 debounce 异步等待。
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# SQLite 兼容适配：PG JSONB/UUID 降级到 JSON/uuid（必须在 Base.metadata 构建前生效）
SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.base import Base  # noqa: E402
import app.models.core  # noqa: E402, F401
import app.models.audit_platform_models  # noqa: E402, F401
import app.models.dataset_models  # noqa: E402, F401
import app.models.workpaper_models  # noqa: E402, F401
import app.models.report_models  # noqa: E402, F401
from app.models.audit_platform_schemas import EventPayload, EventType  # noqa: E402
from app.models.dataset_models import (  # noqa: E402
    DatasetStatus,
    ImportEventOutbox,
    LedgerDataset,
    OutboxStatus,
)
from app.models.report_models import (  # noqa: E402
    AuditReport,
    CompanyType,
    DisclosureNote,
    NoteStatus,
    OpinionType,
    ReportStatus,
)
from app.services.dataset_service import DatasetService  # noqa: E402
from app.services.import_event_outbox_service import ImportEventOutboxService  # noqa: E402


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncSession:
    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


@pytest.fixture
def test_session_factory(monkeypatch, db_engine):
    """把 event_handlers 使用的 async_session_factory 替换为指向同一内存库。

    设计 D11.4 的 handler 内部用 ``async_session_factory()`` 打开新会话，
    默认指向生产配置的 DATABASE_URL。测试里把它 patch 成指向 ``db_engine``
    所在的内存库的 session factory，才能让 handler 看到刚建好的下游行。
    """
    session_factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(
        "app.services.event_handlers.async_session_factory",
        session_factory,
    )
    return session_factory


# ---------------------------------------------------------------------------
# 辅助：建立 active + previous + 下游 AuditReport/DisclosureNote
# ---------------------------------------------------------------------------
async def _seed_active_with_previous(
    db: AsyncSession, project_id: uuid.UUID, year: int
) -> tuple[LedgerDataset, LedgerDataset]:
    """创建 previous dataset (superseded) + current active dataset。

    previous_dataset_id FK 连接两者，模拟"上一次导入已 superseded，
    本次导入 active"场景，满足 rollback 的前置条件（current.previous_dataset_id
    非空且目标 previous 存在）。
    """
    prev = LedgerDataset(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        status=DatasetStatus.superseded,
        source_type="import",
    )
    db.add(prev)
    await db.flush()

    current = LedgerDataset(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        status=DatasetStatus.active,
        source_type="import",
        previous_dataset_id=prev.id,
    )
    db.add(current)
    await db.flush()
    return current, prev


async def _seed_downstream(
    db: AsyncSession, project_id: uuid.UUID, year: int
) -> tuple[AuditReport, DisclosureNote]:
    ar = AuditReport(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        opinion_type=OpinionType.unqualified,
        company_type=CompanyType.non_listed,
        report_date=date(year, 12, 31),
        status=ReportStatus.draft,
        is_stale=False,
    )
    note = DisclosureNote(
        id=uuid.uuid4(),
        project_id=project_id,
        year=year,
        note_section="3.1",
        section_title="货币资金",
        status=NoteStatus.draft,
        is_stale=False,
    )
    db.add_all([ar, note])
    await db.flush()
    return ar, note


# ===========================================================================
# 1) rollback 在事务内写入 outbox，payload 含 F46 新旧两套键
# ===========================================================================
@pytest.mark.asyncio
async def test_rollback_enqueues_outbox_event_with_both_payload_keys(
    db_session: AsyncSession,
):
    project_id = uuid.uuid4()
    year = 2024

    current, previous = await _seed_active_with_previous(db_session, project_id, year)
    await db_session.commit()

    result = await DatasetService.rollback(
        db_session,
        project_id=project_id,
        year=year,
        performed_by=uuid.uuid4(),
        reason="测试",
    )
    await db_session.commit()

    assert result is not None
    assert result.id == previous.id
    assert result.status == DatasetStatus.active

    outbox_rows = (
        await db_session.execute(
            sa.select(ImportEventOutbox).where(
                ImportEventOutbox.event_type
                == EventType.LEDGER_DATASET_ROLLED_BACK.value
            )
        )
    ).scalars().all()
    assert len(outbox_rows) == 1, "rollback 必须写入 outbox 事件行"

    payload = outbox_rows[0].payload or {}
    # 历史键（向后兼容）
    assert payload.get("rolled_back_dataset_id") == str(current.id)
    assert payload.get("restored_dataset_id") == str(previous.id)
    # F46 新增键（供 event_handlers 消费）
    assert payload.get("project_id") == str(project_id)
    assert payload.get("year") == year
    assert payload.get("old_dataset_id") == str(current.id)
    assert payload.get("new_active_dataset_id") == str(previous.id)


# ===========================================================================
# 2) event handler 订阅 LEDGER_DATASET_ROLLED_BACK →
#    AuditReport.is_stale / DisclosureNote.is_stale 被置 True
# ===========================================================================
@pytest.mark.asyncio
async def test_rollback_event_marks_audit_report_and_note_stale(
    db_session: AsyncSession, test_session_factory
):
    # 注册 event_handlers（清空 event_bus 订阅表避免跨测试干扰）
    from app.services.event_bus import event_bus

    event_bus._handlers.clear()
    from app.services import event_handlers as _eh

    _eh.register_event_handlers()

    project_id = uuid.uuid4()
    year = 2024

    ar, note = await _seed_downstream(db_session, project_id, year)
    await db_session.commit()
    assert ar.is_stale is False
    assert note.is_stale is False

    # 派发 rollback 事件（payload 与 DatasetService.rollback 实际写入的载荷一致）
    await event_bus.publish_immediate(
        EventPayload(
            event_type=EventType.LEDGER_DATASET_ROLLED_BACK,
            project_id=project_id,
            year=year,
            extra={
                "project_id": str(project_id),
                "year": year,
                "old_dataset_id": str(uuid.uuid4()),
                "new_active_dataset_id": str(uuid.uuid4()),
            },
        )
    )

    # handler 在独立 session 中修改，refresh 获取 DB 最新值
    await db_session.refresh(ar)
    await db_session.refresh(note)

    assert ar.is_stale is True, "AuditReport.is_stale 应被事件 handler 置 True"
    assert note.is_stale is True, "DisclosureNote.is_stale 应被事件 handler 置 True"


# ===========================================================================
# 3) 跨 project/跨 year 的下游对象不应被误标
# ===========================================================================
@pytest.mark.asyncio
async def test_rollback_event_does_not_mark_unrelated_downstream(
    db_session: AsyncSession, test_session_factory
):
    from app.services.event_bus import event_bus

    event_bus._handlers.clear()
    from app.services import event_handlers as _eh

    _eh.register_event_handlers()

    project_a = uuid.uuid4()
    project_b = uuid.uuid4()
    target_year = 2024
    other_year = 2025

    # 目标：project_a + 2024
    ar_target, note_target = await _seed_downstream(db_session, project_a, target_year)
    # 其他项目 / 其他年度不应受影响
    ar_other_project, note_other_project = await _seed_downstream(
        db_session, project_b, target_year
    )
    ar_other_year, note_other_year = await _seed_downstream(
        db_session, project_a, other_year
    )
    await db_session.commit()

    await event_bus.publish_immediate(
        EventPayload(
            event_type=EventType.LEDGER_DATASET_ROLLED_BACK,
            project_id=project_a,
            year=target_year,
            extra={
                "project_id": str(project_a),
                "year": target_year,
                "old_dataset_id": str(uuid.uuid4()),
                "new_active_dataset_id": str(uuid.uuid4()),
            },
        )
    )

    for obj in (
        ar_target,
        note_target,
        ar_other_project,
        note_other_project,
        ar_other_year,
        note_other_year,
    ):
        await db_session.refresh(obj)

    # 目标对象被标 stale
    assert ar_target.is_stale is True
    assert note_target.is_stale is True
    # 其他项目 / 其他年度完全不受影响
    assert ar_other_project.is_stale is False
    assert note_other_project.is_stale is False
    assert ar_other_year.is_stale is False
    assert note_other_year.is_stale is False


# ===========================================================================
# 4) 端到端：rollback → 发布 outbox → handler 同步执行 → is_stale 传播
# ===========================================================================
@pytest.mark.asyncio
async def test_rollback_full_flow_marks_downstream(
    db_session: AsyncSession, test_session_factory
):
    from app.services.event_bus import event_bus

    event_bus._handlers.clear()
    from app.services import event_handlers as _eh

    _eh.register_event_handlers()

    project_id = uuid.uuid4()
    year = 2024

    current, previous = await _seed_active_with_previous(db_session, project_id, year)
    ar, note = await _seed_downstream(db_session, project_id, year)
    await db_session.commit()

    # 1) rollback 写入 outbox
    restored = await DatasetService.rollback(
        db_session,
        project_id=project_id,
        year=year,
        performed_by=uuid.uuid4(),
        reason="端到端测试",
    )
    await db_session.commit()

    outbox_id = getattr(restored, "_rollback_outbox_id", None)
    assert outbox_id is not None

    # 2) 发布该 outbox 事件（publish_one 会通过 event_bus.publish_immediate 同步派发）
    published = await ImportEventOutboxService.publish_one(db_session, outbox_id)
    await db_session.commit()
    assert published is True

    # 验证 outbox 状态迁移
    outbox = await ImportEventOutboxService.get(db_session, outbox_id)
    assert outbox is not None
    assert outbox.status == OutboxStatus.published

    # 3) handler 已同步执行 —— 下游对象 is_stale = True
    await db_session.refresh(ar)
    await db_session.refresh(note)
    assert ar.is_stale is True
    assert note.is_stale is True
