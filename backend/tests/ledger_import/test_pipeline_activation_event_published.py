"""v2 入库管线激活后必须内联发布 LEDGER_DATASET_ACTIVATED（断点 1 防御测试）。

🔴 缺陷（2026-09-29 复现）：``ledger_import.pipeline.execute_pipeline`` 在
``activate_dataset`` 之后只 ``commit``，从不调 ``DatasetService.publish_dataset_activated``。
outbox 行一直 ``pending``，下游整条链（auto_match 建科目映射 → 试算表未审数 → 报表 →
附注/底稿 stale）全靠 ``outbox_replay_worker`` 轮询补发：最坏 30s 延迟；
``LEDGER_IMPORT_OUTBOX_REPLAY_ENABLED=False`` 时整条链静默不触发。
真库 ``import_event_outbox`` 的 17 条激活事件 ``attempt_count`` 全为 1（=由 worker
重放置位，无一次内联发布）即此缺陷的生产证据。

判据（都在真 pipeline 上跑，不 mock 管线本身）：
1. 管线返回时，事件已派发给订阅者（不等 worker）
2. outbox 行已是 ``published`` 且 ``attempt_count == 0``（内联路径不递增）
3. 投递失败时 outbox 行转 ``failed``（保留给 worker 重放），导入本身仍成功
4. 同一数据集重复激活（resume 场景）不会二次派发
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
SQLiteTypeCompiler.visit_UUID = SQLiteTypeCompiler.visit_uuid

from app.models.base import Base
import app.models.core  # noqa: F401
import app.models.audit_platform_models  # noqa: F401
import app.models.dataset_models  # noqa: F401
from app.models.audit_platform_schemas import EventPayload, EventType
from app.models.dataset_models import (
    DatasetStatus,
    ImportEventOutbox,
    LedgerDataset,
    OutboxStatus,
)
from app.services.event_bus import event_bus

_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "ledger_samples"
sys.path.insert(0, str(_FIXTURE_DIR))
from minimal_balance_ledger import create_minimal_sample  # type: ignore  # noqa: E402


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.fixture
def captured_activation_events():
    """把 LEDGER_DATASET_ACTIVATED 的全部生产订阅者换成一个记录器。

    只替换订阅表、不替换派发机制：``publish_one → _deliver → event_bus.publish_immediate
    → _dispatch`` 全部走真实代码。测试结束恢复原订阅者，避免污染其他用例。
    """
    received: list[EventPayload] = []

    async def _recorder(payload: EventPayload) -> None:
        received.append(payload)

    et = EventType.LEDGER_DATASET_ACTIVATED
    original = list(event_bus._handlers.get(et, []))
    event_bus._handlers[et] = [_recorder]
    try:
        yield received
    finally:
        event_bus._handlers[et] = original


async def _run_pipeline(session_factory, tmp_path: Path, project_id: uuid.UUID):
    """在 SQLite 上真跑一遍 v2 管线（小样本走 INSERT 分支，不触及 COPY）。"""
    from app.services.ledger_import.pipeline import execute_pipeline

    sample = create_minimal_sample(tmp_path / "minimal.xlsx")
    # pipeline 与 publish_dataset_activated 都在函数体内 import async_session，
    # 必须 patch 源头 app.core.database.async_session 才能让两处都落到测试库。
    # calamine 是可选依赖 → 用管线自己的内存降级开关强制走 openpyxl（不改管线代码路径）。
    # rebuild_aux_balance_summary 是裸 SQL（gen_random_uuid() + 无 ORM 模型的
    # tb_aux_balance_summary 表），SQLite 跑不了且与事件发布无关 → 替换为 no-op。
    async def _noop_rebuild(*_a, **_kw) -> int:
        return 0

    with patch("app.core.database.async_session", session_factory), \
         patch("app.services.ledger_import.pipeline._detect_memory_pressure",
               return_value=True), \
         patch("app.services.smart_import_engine.rebuild_aux_balance_summary",
               _noop_rebuild):
        return await execute_pipeline(
            job_id=uuid.uuid4(),
            project_id=project_id,
            year=2025,
            custom_mapping=None,
            created_by=None,
            file_sources=[(sample.name, sample)],
            force_activate=True,
        )


async def _outbox_rows(session_factory, project_id: uuid.UUID) -> list[ImportEventOutbox]:
    async with session_factory() as db:
        result = await db.execute(
            sa.select(ImportEventOutbox).where(
                ImportEventOutbox.project_id == project_id,
                ImportEventOutbox.event_type == EventType.LEDGER_DATASET_ACTIVATED.value,
            )
        )
        return list(result.scalars().all())


@pytest.mark.asyncio
async def test_pipeline_publishes_activation_inline(
    session_factory, tmp_path, captured_activation_events,
):
    """判据 1 + 2：管线返回时事件已派发，outbox 行已 published 且未经 worker。"""
    project_id = uuid.uuid4()
    result = await _run_pipeline(session_factory, tmp_path, project_id)

    assert result.success and result.dataset_id is not None
    assert result.balance_rows > 0, "样本应写入余额行，否则本测试没有真跑管线"

    # 判据 1：订阅者已收到，且 payload 能定位到本次数据集
    assert len(captured_activation_events) == 1, (
        "v2 管线激活后必须内联派发 LEDGER_DATASET_ACTIVATED，"
        f"实际收到 {len(captured_activation_events)} 次（0 = 仍依赖 outbox worker 补发）"
    )
    payload = captured_activation_events[0]
    assert payload.project_id == project_id
    assert payload.year == 2025
    assert (payload.extra or {}).get("dataset_id") == str(result.dataset_id)

    # 判据 2：outbox 行已 published；attempt_count==0 证明走的是内联路径
    rows = await _outbox_rows(session_factory, project_id)
    assert len(rows) == 1
    assert rows[0].status == OutboxStatus.published
    assert rows[0].published_at is not None
    assert rows[0].attempt_count == 0, (
        "attempt_count>0 说明是 worker 重放置位的，而不是管线内联发布"
    )

    async with session_factory() as db:
        ds = await db.get(LedgerDataset, result.dataset_id)
        assert ds.status == DatasetStatus.active


@pytest.mark.asyncio
async def test_delivery_failure_keeps_outbox_for_worker_and_import_succeeds(
    session_factory, tmp_path,
):
    """判据 3：订阅者抛错 → outbox 行转 failed（worker 可重放），导入仍返回成功。"""

    async def _boom(_payload: EventPayload) -> None:
        raise RuntimeError("simulated downstream failure")

    et = EventType.LEDGER_DATASET_ACTIVATED
    original = list(event_bus._handlers.get(et, []))
    event_bus._handlers[et] = [_boom]
    # _dispatch 会吞 handler 异常并发 SYNC_FAILED；这里要验证的是「投递链自身失败」，
    # 故让 publish_immediate 直接抛，模拟派发口故障（与 publish_one 的 except 分支对齐）。
    original_publish = event_bus.publish_immediate

    async def _failing_publish(payload: EventPayload) -> None:
        if payload.event_type == et:
            raise RuntimeError("simulated dispatch failure")
        await original_publish(payload)

    project_id = uuid.uuid4()
    try:
        with patch.object(event_bus, "publish_immediate", _failing_publish):
            result = await _run_pipeline(session_factory, tmp_path, project_id)
    finally:
        event_bus._handlers[et] = original

    assert result.success, "事件投递失败不得让已激活的导入变成失败"
    rows = await _outbox_rows(session_factory, project_id)
    assert len(rows) == 1
    assert rows[0].status == OutboxStatus.failed, "投递失败必须留给 worker 重放"
    assert "simulated dispatch failure" in (rows[0].last_error or "")


@pytest.mark.asyncio
async def test_republish_same_dataset_does_not_dispatch_twice(
    session_factory, tmp_path, captured_activation_events,
):
    """判据 4：resume 场景重复调用 publish 不会二次派发（published 行直接跳过）。"""
    from app.services.dataset_service import DatasetService

    project_id = uuid.uuid4()
    result = await _run_pipeline(session_factory, tmp_path, project_id)
    assert len(captured_activation_events) == 1

    rows = await _outbox_rows(session_factory, project_id)
    ds_stub = LedgerDataset(id=result.dataset_id, project_id=project_id, year=2025)
    setattr(ds_stub, "_activation_outbox_id", rows[0].id)
    with patch("app.core.database.async_session", session_factory):
        await DatasetService.publish_dataset_activated(ds_stub)

    assert len(captured_activation_events) == 1, "已 published 的 outbox 行不得再次派发"
