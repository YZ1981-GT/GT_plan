"""F45 / Sprint 7.17-7.18 + 7.20: 事件广播失败 N 次后落入 DLQ。

覆盖 design D11.3 的核心不变量：
- ``replay_pending`` 对每条 pending/failed 事件都会尝试发布；
- 发布失败时 ``attempt_count += 1``；
- 当 ``attempt_count >= max_attempts`` 时，该事件 snapshot 进 ``event_outbox_dlq``；
- 原 ``import_event_outbox`` 行保留 ``status=failed``（审计痕迹，不删除）；
- DLQ 行保留 event_type/project_id/year/payload/failure_reason/attempt_count 完整信息；
- ``dlq_depth()`` 只统计未处理（``resolved_at IS NULL``）的 DLQ 行。

Fixture 模式：SQLite 内存库 + PG JSONB/UUID 降级（同 test_cross_project_isolation.py）。
``event_bus.publish_immediate`` 用 monkeypatch 替换为总是抛异常的假函数，
模拟下游 WebSocket / 消费者长期不可达的场景。
"""
from __future__ import annotations

import uuid

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
from app.models.audit_platform_schemas import EventType  # noqa: E402
from app.models.dataset_models import (  # noqa: E402
    EventOutboxDLQ,
    ImportEventOutbox,
    OutboxStatus,
)
from app.services.import_event_outbox_service import ImportEventOutboxService  # noqa: E402


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def always_fail_publish(monkeypatch):
    """把 event_bus.publish_immediate 打桩成总是抛异常的假函数。"""
    calls = {"count": 0, "last_event": None}

    async def _raise(*args, **kwargs):  # noqa: D401
        calls["count"] += 1
        if args:
            calls["last_event"] = args[0]
        raise RuntimeError("simulated downstream unavailable")

    monkeypatch.setattr(
        "app.services.import_event_outbox_service.event_bus.publish_immediate",
        _raise,
    )
    return calls


# ---------------------------------------------------------------------------
# 1) 3 次失败后事件落入 DLQ，原 outbox 行保留 failed 状态
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_exhausted_event_moved_to_dlq_after_three_failures(
    db_session: AsyncSession, always_fail_publish
):
    project_id = uuid.uuid4()
    payload = {"dataset_id": str(uuid.uuid4()), "project_id": str(project_id)}

    outbox = await ImportEventOutboxService.enqueue(
        db_session,
        event_type=EventType.LEDGER_DATASET_ACTIVATED,
        project_id=project_id,
        year=2025,
        payload=payload,
    )
    await db_session.commit()
    outbox_id = outbox.id

    # 跑 3 轮 replay，每轮 max_attempts=3 —— 第 3 轮 attempt_count 达到 3 时应触发 DLQ
    for _ in range(3):
        report = await ImportEventOutboxService.replay_pending(
            db_session, limit=10, max_attempts=3
        )
        await db_session.commit()

    # 第 3 轮的报告应该含 moved_to_dlq_count=1
    assert report["moved_to_dlq_count"] == 1, (
        f"第 3 轮失败应触发 DLQ 移动，实际 report={report}"
    )
    assert report["failed_count"] == 1

    # 原 outbox 行：保留 failed 状态 + attempt_count=3
    await db_session.refresh(outbox)
    assert outbox.status == OutboxStatus.failed, (
        f"原 outbox 行应保留 failed 状态，实际 {outbox.status}"
    )
    assert outbox.attempt_count == 3
    assert outbox.last_error is not None

    # DLQ 行验证
    dlq_rows = (
        await db_session.execute(sa.select(EventOutboxDLQ))
    ).scalars().all()
    assert len(dlq_rows) == 1, f"DLQ 应有 1 行，实际 {len(dlq_rows)} 行"
    dlq = dlq_rows[0]
    assert dlq.original_event_id == outbox_id
    assert dlq.event_type == EventType.LEDGER_DATASET_ACTIVATED.value
    assert dlq.project_id == project_id
    assert dlq.year == 2025
    assert dlq.payload == payload
    assert dlq.attempt_count == 3
    assert dlq.failure_reason is not None
    assert "simulated downstream unavailable" in dlq.failure_reason
    assert dlq.resolved_at is None
    assert dlq.resolved_by is None


# ---------------------------------------------------------------------------
# 2) 重试次数未达上限时，事件不应进 DLQ（仅 attempt_count 递增）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_event_not_moved_to_dlq_before_max_attempts(
    db_session: AsyncSession, always_fail_publish
):
    project_id = uuid.uuid4()

    await ImportEventOutboxService.enqueue(
        db_session,
        event_type=EventType.LEDGER_DATASET_ACTIVATED,
        project_id=project_id,
        year=2025,
        payload={"dataset_id": str(uuid.uuid4())},
    )
    await db_session.commit()

    # 只跑 2 轮（max_attempts=3）
    for _ in range(2):
        report = await ImportEventOutboxService.replay_pending(
            db_session, limit=10, max_attempts=3
        )
        await db_session.commit()
        assert report["moved_to_dlq_count"] == 0, (
            "未达 max_attempts 前不应触发 DLQ 移动"
        )

    # DLQ 表应为空
    dlq_count = (
        await db_session.execute(sa.select(sa.func.count()).select_from(EventOutboxDLQ))
    ).scalar_one()
    assert dlq_count == 0


# ---------------------------------------------------------------------------
# 3) max_attempts=None 时不触发 DLQ（无限重试策略）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_dlq_when_max_attempts_disabled(
    db_session: AsyncSession, always_fail_publish
):
    project_id = uuid.uuid4()
    await ImportEventOutboxService.enqueue(
        db_session,
        event_type=EventType.LEDGER_DATASET_ACTIVATED,
        project_id=project_id,
        year=2025,
        payload={"dataset_id": str(uuid.uuid4())},
    )
    await db_session.commit()

    # 跑 5 轮无 max_attempts
    for _ in range(5):
        report = await ImportEventOutboxService.replay_pending(db_session, limit=10)
        await db_session.commit()

    assert report.get("moved_to_dlq_count", 0) == 0

    dlq_count = (
        await db_session.execute(sa.select(sa.func.count()).select_from(EventOutboxDLQ))
    ).scalar_one()
    assert dlq_count == 0


# ---------------------------------------------------------------------------
# 4) dlq_depth() 只统计未处理的 DLQ 行
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dlq_depth_counts_unresolved_only(
    db_session: AsyncSession, always_fail_publish
):
    from datetime import datetime, timezone

    project_id = uuid.uuid4()

    # 初始化 3 条 DLQ：手动创建避免依赖 replay 流程
    unresolved_a = EventOutboxDLQ(
        event_type="x.dummy",
        project_id=project_id,
        year=2025,
        payload={},
        attempt_count=3,
    )
    unresolved_b = EventOutboxDLQ(
        event_type="x.dummy",
        project_id=project_id,
        year=2025,
        payload={},
        attempt_count=3,
    )
    resolved = EventOutboxDLQ(
        event_type="x.dummy",
        project_id=project_id,
        year=2025,
        payload={},
        attempt_count=3,
        resolved_at=datetime.now(timezone.utc),
        resolved_by=uuid.uuid4(),
    )
    db_session.add_all([unresolved_a, unresolved_b, resolved])
    await db_session.commit()

    depth = await ImportEventOutboxService.dlq_depth(db_session)
    assert depth == 2, (
        f"dlq_depth 应只统计 resolved_at IS NULL 的行，实际 {depth}"
    )


# ---------------------------------------------------------------------------
# 5) 进入 DLQ 后原 outbox 行 attempt_count >= max_attempts，
#    后续 replay 会跳过该行（不再重复进 DLQ）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dlq_entry_not_duplicated_on_subsequent_replays(
    db_session: AsyncSession, always_fail_publish
):
    project_id = uuid.uuid4()
    await ImportEventOutboxService.enqueue(
        db_session,
        event_type=EventType.LEDGER_DATASET_ACTIVATED,
        project_id=project_id,
        year=2025,
        payload={"dataset_id": str(uuid.uuid4())},
    )
    await db_session.commit()

    # 3 轮后进入 DLQ
    for _ in range(3):
        await ImportEventOutboxService.replay_pending(
            db_session, limit=10, max_attempts=3
        )
        await db_session.commit()

    depth_after_first = await ImportEventOutboxService.dlq_depth(db_session)
    assert depth_after_first == 1

    # 再跑 3 轮 —— 原 outbox 已 attempt_count=3 >= max_attempts，
    # replay_pending 的 WHERE 子句会排除它
    for _ in range(3):
        report = await ImportEventOutboxService.replay_pending(
            db_session, limit=10, max_attempts=3
        )
        await db_session.commit()
        assert report["read_count"] == 0
        assert report["moved_to_dlq_count"] == 0

    depth_after_second = await ImportEventOutboxService.dlq_depth(db_session)
    assert depth_after_second == 1, "同一事件不应被多次移入 DLQ"
