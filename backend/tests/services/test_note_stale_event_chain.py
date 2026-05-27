"""集成测试 — Sprint 2 Task 2.5 EventBus 联动 3 新事件 + ROLLED_BACK 兼容.

Spec:   .kiro/specs/disclosure-note-full-revamp/ Sprint 2 Task 2.5
Design: D6 联动机制 EventBus 订阅表
Reqs:   R2.1 验收标准（DisclosureNote.is_stale 联动）

测试对象（实际订阅事件 — spec 设计名 ↔ 实际命中事件名）：
  ① on_event_ledger_activated      ↔ LEDGER_DATASET_ACTIVATED   ✅ 名称一致
  ② on_event_workpaper_reviewed    ↔ WORKPAPER_REVIEW_PASSED    （spec 设计 WORKPAPER_REVIEWED 不存在）
  ③ on_event_adjustment_approved   ↔ ADJUSTMENT_BATCH_COMMITTED  （spec 设计 ADJUSTMENT_APPROVED 不存在）

≥ 8 用例（3 新事件 × 2 路径 + ROLLED_BACK 兼容性 × 2）：
  T1  LEDGER_DATASET_ACTIVATED 事件订阅存在 + handler 触发 update SQL
  T2  LEDGER_DATASET_ACTIVATED handler 限制 project+year 维度
  T3  WORKPAPER_REVIEW_PASSED 事件订阅存在 + handler 触发 update SQL
  T4  WORKPAPER_REVIEW_PASSED handler 限制 project+year 维度
  T5  ADJUSTMENT_BATCH_COMMITTED 事件订阅存在 + handler 触发 update SQL
  T6  ADJUSTMENT_BATCH_COMMITTED handler 限制 project+year 维度
  T7  LEDGER_DATASET_ROLLED_BACK 兼容性 — 既有 _mark_downstream_stale_on_rollback
        handler 仍在订阅表（本 spec 不动该 handler）
  T8  3 个新 handler 与现有 rollback handler 共存 — 订阅表清单完整

测试策略：
- 不依赖真实 PG / SQLite（项目历史 ARRAY 字段在 SQLite 上无法 create_all）
- 用 ``MagicMock`` 替换 ``async_session_factory``，捕获 handler 提交的
  ``session.execute(update)`` 调用 — 断言 update 语句的 WHERE 子句字段
  + project_id + year 命中正确
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy as sa

from app.models.audit_platform_schemas import EventPayload, EventType


# ---------------------------------------------------------------------------
# Fixture：Mock session_factory + 重新注册 handlers
# ---------------------------------------------------------------------------


class _CapturingSession:
    """模拟 AsyncSession — 捕获每次 .execute() 调用的 update 对象."""

    def __init__(self, captured: list):
        self.captured = captured
        self.committed = False
        self.rolled_back = False

    async def execute(self, stmt, *args, **kwargs):
        self.captured.append(stmt)
        result = MagicMock()
        result.rowcount = 1
        return result

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def flush(self):
        pass


@pytest.fixture
def captured_executes():
    return []


@pytest.fixture
def fresh_event_bus(monkeypatch, captured_executes):
    """清空 event_bus + 重 register_event_handlers + patch session_factory."""
    from app.services.event_bus import event_bus

    event_bus._handlers.clear()
    event_bus._pending.clear()

    @asynccontextmanager
    async def _fake_session_factory(*args, **kwargs):
        sess = _CapturingSession(captured_executes)
        try:
            yield sess
        finally:
            pass

    # 让所有 handler 共享同一 session_factory mock — 注意 handler 调用形式是
    # ``async with async_session_factory() as session:`` ，所以 patch 的是
    # 一个**返回 async context manager 的可调用**。
    monkeypatch.setattr(
        "app.services.event_handlers.async_session_factory",
        _fake_session_factory,
    )

    from app.services import event_handlers as _eh
    _eh.register_event_handlers()
    return event_bus


# ---------------------------------------------------------------------------
# helper：在捕获列表中寻找 update DisclosureNote 的语句
# ---------------------------------------------------------------------------


def _find_disclosure_note_update(captured: list) -> sa.sql.Update | None:
    """从捕获语句列表中找第一个 update DisclosureNote 表的 statement."""
    from app.models.report_models import DisclosureNote
    for stmt in captured:
        # SQLAlchemy 2.0：sa.update(Model) 返回 Update 对象
        if isinstance(stmt, sa.sql.Update):
            tables = stmt.entity_description if hasattr(stmt, "entity_description") else None
            # 简单方式：编译看 table 名
            try:
                table_name = stmt.table.name
            except Exception:
                # update().table is set when bound to a table mapper; via __mapper__
                table_name = getattr(stmt, "table", None)
                table_name = getattr(table_name, "name", "")
            if table_name == DisclosureNote.__tablename__:
                return stmt
    return None


def _find_audit_report_update(captured: list) -> sa.sql.Update | None:
    from app.models.report_models import AuditReport
    for stmt in captured:
        if isinstance(stmt, sa.sql.Update):
            try:
                table_name = stmt.table.name
            except Exception:
                table_name = getattr(getattr(stmt, "table", None), "name", "")
            if table_name == AuditReport.__tablename__:
                return stmt
    return None


def _stmt_compiled_str(stmt) -> str:
    """返回带绑定参数渲染的 SQL 字符串（用于 WHERE 字段断言）."""
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


# ===========================================================================
# T1  LEDGER_DATASET_ACTIVATED 订阅 + handler 触发 update SQL
# ===========================================================================


@pytest.mark.asyncio
async def test_ledger_activated_handler_updates_disclosure_notes(
    fresh_event_bus, captured_executes,
):
    project_id = uuid.uuid4()
    year = 2025

    # 订阅断言：LEDGER_DATASET_ACTIVATED 必须有至少 1 个 handler
    handlers = fresh_event_bus._handlers.get(EventType.LEDGER_DATASET_ACTIVATED, [])
    assert len(handlers) >= 1
    handler_names = [
        getattr(h, "__qualname__", h.__name__) for h in handlers
    ]
    assert any(
        "on_event_ledger_activated" in n for n in handler_names
    ), f"on_event_ledger_activated 未注册，实际 handlers={handler_names}"

    await fresh_event_bus.publish_immediate(
        EventPayload(
            event_type=EventType.LEDGER_DATASET_ACTIVATED,
            project_id=project_id,
            year=year,
        )
    )

    # 至少有 1 条 update DisclosureNote 语句被提交
    upd = _find_disclosure_note_update(captured_executes)
    assert upd is not None, "未捕获到 update DisclosureNote 语句"
    sql = _stmt_compiled_str(upd)
    assert "is_stale" in sql.lower()
    # UUID 在 literal_binds 中无 dash 渲染
    assert (str(project_id) in sql or str(project_id).replace("-", "") in sql)
    assert str(year) in sql


# ===========================================================================
# T2  LEDGER_DATASET_ACTIVATED handler 限制 project+year 维度（WHERE 子句）
# ===========================================================================


@pytest.mark.asyncio
async def test_ledger_activated_handler_scopes_by_project_and_year(
    fresh_event_bus, captured_executes,
):
    """断言 update statement 的 WHERE 含 project_id + year 字段过滤."""
    project_id = uuid.uuid4()
    year = 2025

    await fresh_event_bus.publish_immediate(
        EventPayload(
            event_type=EventType.LEDGER_DATASET_ACTIVATED,
            project_id=project_id,
            year=year,
        )
    )

    upd = _find_disclosure_note_update(captured_executes)
    assert upd is not None
    sql = _stmt_compiled_str(upd).lower()
    assert "project_id" in sql
    assert "year" in sql
    assert "is_deleted" in sql, "WHERE 必须含 is_deleted = false 过滤"


# ===========================================================================
# T3 / T4  WORKPAPER_REVIEW_PASSED
# ===========================================================================


@pytest.mark.asyncio
async def test_workpaper_review_passed_handler_updates_disclosure_notes(
    fresh_event_bus, captured_executes,
):
    project_id = uuid.uuid4()
    year = 2025

    handlers = fresh_event_bus._handlers.get(EventType.WORKPAPER_REVIEW_PASSED, [])
    handler_names = [
        getattr(h, "__qualname__", h.__name__) for h in handlers
    ]
    assert any(
        "on_event_workpaper_reviewed" in n for n in handler_names
    ), f"on_event_workpaper_reviewed 未注册，实际 handlers={handler_names}"

    await fresh_event_bus.publish_immediate(
        EventPayload(
            event_type=EventType.WORKPAPER_REVIEW_PASSED,
            project_id=project_id,
            year=year,
        )
    )

    upd = _find_disclosure_note_update(captured_executes)
    assert upd is not None
    sql = _stmt_compiled_str(upd)
    assert "is_stale" in sql.lower()
    assert (str(project_id) in sql or str(project_id).replace("-", "") in sql)
    assert str(year) in sql


@pytest.mark.asyncio
async def test_workpaper_review_passed_handler_scopes_by_project_and_year(
    fresh_event_bus, captured_executes,
):
    project_id = uuid.uuid4()
    year = 2025

    await fresh_event_bus.publish_immediate(
        EventPayload(
            event_type=EventType.WORKPAPER_REVIEW_PASSED,
            project_id=project_id,
            year=year,
        )
    )

    upd = _find_disclosure_note_update(captured_executes)
    assert upd is not None
    sql = _stmt_compiled_str(upd).lower()
    assert "project_id" in sql
    assert "year" in sql
    assert "is_deleted" in sql


# ===========================================================================
# T5 / T6  ADJUSTMENT_BATCH_COMMITTED
# ===========================================================================


@pytest.mark.asyncio
async def test_adjustment_batch_committed_handler_updates_disclosure_notes(
    fresh_event_bus, captured_executes,
):
    project_id = uuid.uuid4()
    year = 2025

    handlers = fresh_event_bus._handlers.get(EventType.ADJUSTMENT_BATCH_COMMITTED, [])
    handler_names = [
        getattr(h, "__qualname__", h.__name__) for h in handlers
    ]
    assert any(
        "on_event_adjustment_approved" in n for n in handler_names
    ), f"on_event_adjustment_approved 未注册，实际 handlers={handler_names}"

    await fresh_event_bus.publish_immediate(
        EventPayload(
            event_type=EventType.ADJUSTMENT_BATCH_COMMITTED,
            project_id=project_id,
            year=year,
        )
    )

    upd = _find_disclosure_note_update(captured_executes)
    assert upd is not None
    sql = _stmt_compiled_str(upd)
    assert "is_stale" in sql.lower()
    assert (str(project_id) in sql or str(project_id).replace("-", "") in sql)
    assert str(year) in sql


@pytest.mark.asyncio
async def test_adjustment_batch_committed_handler_scopes_by_project_and_year(
    fresh_event_bus, captured_executes,
):
    project_id = uuid.uuid4()
    year = 2025

    await fresh_event_bus.publish_immediate(
        EventPayload(
            event_type=EventType.ADJUSTMENT_BATCH_COMMITTED,
            project_id=project_id,
            year=year,
        )
    )

    upd = _find_disclosure_note_update(captured_executes)
    assert upd is not None
    sql = _stmt_compiled_str(upd).lower()
    assert "project_id" in sql
    assert "year" in sql
    assert "is_deleted" in sql


# ===========================================================================
# T7  LEDGER_DATASET_ROLLED_BACK 兼容性 — F46 既有 handler 仍触发
# ===========================================================================


@pytest.mark.asyncio
async def test_rolled_back_compat_existing_handler_fires(
    fresh_event_bus, captured_executes,
):
    """T7：F46 既有 _mark_downstream_stale_on_rollback handler 仍订阅 + 触发.

    本 spec 不动该 handler，但补 3 新订阅后不能误删既有订阅。
    既有 handler 同时 update DisclosureNote 和 AuditReport 两表（参考 F46/Sprint 7.22）。
    """
    handlers = fresh_event_bus._handlers.get(EventType.LEDGER_DATASET_ROLLED_BACK, [])
    handler_names = [
        getattr(h, "__qualname__", h.__name__) for h in handlers
    ]
    assert any(
        "_mark_downstream_stale_on_rollback" in n for n in handler_names
    ), f"F46 既有 rollback handler 必须仍订阅，实际 handlers={handler_names}"

    project_id = uuid.uuid4()
    year = 2025
    await fresh_event_bus.publish_immediate(
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

    # F46 handler 同时 update AuditReport + DisclosureNote
    note_upd = _find_disclosure_note_update(captured_executes)
    ar_upd = _find_audit_report_update(captured_executes)
    assert note_upd is not None, "rollback 必须 update DisclosureNote (F46 既有)"
    assert ar_upd is not None, "rollback 必须 update AuditReport (F46 既有)"


# ===========================================================================
# T8  共存 — 3 新 handler 与现有 rollback handler 不冲突
# ===========================================================================


@pytest.mark.asyncio
async def test_new_handlers_coexist_with_rollback_handler(
    fresh_event_bus, captured_executes,
):
    """T8：4 个事件订阅清单完整，互不挤占。"""
    eb = fresh_event_bus
    expected = {
        EventType.LEDGER_DATASET_ACTIVATED: "on_event_ledger_activated",
        EventType.WORKPAPER_REVIEW_PASSED: "on_event_workpaper_reviewed",
        EventType.ADJUSTMENT_BATCH_COMMITTED: "on_event_adjustment_approved",
        EventType.LEDGER_DATASET_ROLLED_BACK: "_mark_downstream_stale_on_rollback",
    }
    for evt_type, expected_name in expected.items():
        names = [
            getattr(h, "__qualname__", h.__name__)
            for h in eb._handlers.get(evt_type, [])
        ]
        assert any(expected_name in n for n in names), (
            f"{evt_type.value} 期望 handler {expected_name} 缺失，"
            f"实际 = {names}"
        )

    # 新事件不应触发 AR update（仅 ROLLED_BACK 才标 AR）
    captured_executes.clear()
    project_id = uuid.uuid4()
    year = 2025
    await eb.publish_immediate(
        EventPayload(
            event_type=EventType.LEDGER_DATASET_ACTIVATED,
            project_id=project_id,
            year=year,
        )
    )
    note_upd = _find_disclosure_note_update(captured_executes)
    ar_upd = _find_audit_report_update(captured_executes)
    assert note_upd is not None, "ACTIVATED 必须 update DisclosureNote"
    assert ar_upd is None, "ACTIVATED 不应 update AuditReport（仅 ROLLED_BACK 才标 AR）"
