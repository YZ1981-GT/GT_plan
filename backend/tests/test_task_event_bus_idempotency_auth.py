"""TaskEventBus 幂等、procedure outbox 隔离与 /task-events 授权。

Validates: Requirements 9.1, 9.2, 9.6 / Properties 17, 18
"""
from __future__ import annotations

import ast
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core.events.envelope import compute_durable_idempotency_key
from app.models.phase15_enums import TaskEventStatus
from app.routers.task_events import EventReplayRequest, list_events, replay_event
from app.services.procedure_task_transition_service import AGGREGATE_PROCEDURE_ROW_TASK
from app.services.task_event_bus import TaskEventBus, is_procedure_delivery_outbox

ROOT = Path(__file__).resolve().parents[2]
TASK_EVENT_BUS_PATH = ROOT / "backend" / "app" / "services" / "task_event_bus.py"
TASK_EVENTS_ROUTER_PATH = ROOT / "backend" / "app" / "routers" / "task_events.py"


def test_publish_source_writes_and_queries_idempotency_key_equality() -> None:
    """publish 源码必须等值查/写 idempotency_key，禁止 trace_id LIKE。"""
    src = TASK_EVENT_BUS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    publish = next(
        n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "publish"
    )
    body = ast.get_source_segment(src, publish) or ""
    assert "idempotency_key=" in body
    assert "idempotency_key ==" in body or "TaskEvent.idempotency_key ==" in body
    assert ".like(" not in body


@pytest.mark.asyncio
async def test_publish_persists_idempotency_key_and_dedups_by_equality() -> None:
    bus = TaskEventBus()
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.add = MagicMock()
    mock_db.flush = AsyncMock()

    project_id = uuid.uuid4()
    payload = {"ref_id": "proc_001", "version": "1"}
    await bus.publish(mock_db, project_id, "trim_applied", None, payload)

    stmt = mock_db.execute.await_args.args[0]
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": False})).lower()
    assert "idempotency_key" in compiled
    assert "like" not in compiled

    added = mock_db.add.call_args[0][0]
    expected = compute_durable_idempotency_key(project_id, "trim_applied", payload)
    assert added.idempotency_key == expected

    existing = MagicMock()
    existing.id = uuid.uuid4()
    mock_result.scalar_one_or_none.return_value = existing
    mock_db.add.reset_mock()
    hit = await bus.publish(mock_db, project_id, "trim_applied", None, payload)
    assert hit == existing.id
    mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_replay_excludes_procedure_delivery_outbox() -> None:
    bus = TaskEventBus()
    mock_db = AsyncMock()
    event = MagicMock()
    event.id = uuid.uuid4()
    event.status = TaskEventStatus.dead_letter
    event.retry_count = 3
    event.project_id = uuid.uuid4()
    event.trace_id = "trc_outbox"
    event.aggregate_type = AGGREGATE_PROCEDURE_ROW_TASK
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = event
    mock_db.execute = AsyncMock(return_value=mock_result)

    assert is_procedure_delivery_outbox(event) is True
    with pytest.raises(HTTPException) as exc:
        await bus.replay(mock_db, event.id, uuid.uuid4(), "manual_retry")
    assert exc.value.status_code == 409
    assert "PROCEDURE_DELIVERY_OUTBOX_NOT_REPLAYABLE" in str(exc.value.detail)
    assert event.status == TaskEventStatus.dead_letter
    assert event.retry_count == 3


@pytest.mark.asyncio
async def test_consume_skips_procedure_delivery_outbox() -> None:
    bus = TaskEventBus()
    handler = AsyncMock()
    bus.register_handler("procedure_task.assigned", handler)
    mock_db = AsyncMock()
    event = MagicMock()
    event.id = uuid.uuid4()
    event.event_type = "procedure_task.assigned"
    event.status = TaskEventStatus.queued
    event.aggregate_type = AGGREGATE_PROCEDURE_ROW_TASK
    event.payload = {}
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = event
    mock_db.execute = AsyncMock(return_value=mock_result)

    ok = await bus.consume(mock_db, event.id)
    assert ok is False
    handler.assert_not_awaited()
    assert event.status == TaskEventStatus.queued


def test_outbox_isolation_uses_aggregate_type_not_trace_guess() -> None:
    src = TASK_EVENT_BUS_PATH.read_text(encoding="utf-8")
    assert "AGGREGATE_PROCEDURE_ROW_TASK" in src
    assert "is_procedure_delivery_outbox" in src
    tree = ast.parse(src)
    predicate = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "is_procedure_delivery_outbox"
    )
    body_nodes = list(predicate.body)
    if (
        body_nodes
        and isinstance(body_nodes[0], ast.Expr)
        and isinstance(body_nodes[0].value, ast.Constant)
        and isinstance(body_nodes[0].value.value, str)
    ):
        body_nodes = body_nodes[1:]
    body_mod = ast.Module(body=body_nodes, type_ignores=[])
    string_lits = {
        node.value
        for node in ast.walk(body_mod)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    attrs = {
        node.attr for node in ast.walk(body_mod) if isinstance(node, ast.Attribute)
    }
    names = {node.id for node in ast.walk(body_mod) if isinstance(node, ast.Name)}
    assert "aggregate_type" in string_lits or "aggregate_type" in attrs
    assert "AGGREGATE_PROCEDURE_ROW_TASK" in names
    assert "trace_id" not in attrs
    assert "trace_id" not in string_lits
    body_src = "\n".join(ast.get_source_segment(src, n) or "" for n in body_nodes)
    assert ".like(" not in body_src


@pytest.mark.asyncio
async def test_list_events_requires_project_visibility() -> None:
    db = AsyncMock()
    user = MagicMock()
    project_id = uuid.uuid4()
    with patch(
        "app.routers.task_events.assert_project_permission",
        AsyncMock(side_effect=HTTPException(status_code=403, detail="NO_ACCESS")),
    ) as perm:
        with pytest.raises(HTTPException) as exc:
            await list_events(
                project_id=project_id,
                status=None,
                pagination=MagicMock(offset=0, limit=20, page=1, page_size=20),
                db=db,
                current_user=user,
            )
        assert exc.value.status_code == 403
    perm.assert_awaited_once()
    assert perm.await_args.args[2] == project_id
    assert perm.await_args.args[3] == "readonly"


@pytest.mark.asyncio
async def test_replay_actor_comes_from_current_user_not_request_body() -> None:
    db = AsyncMock()
    event = MagicMock()
    event.id = uuid.uuid4()
    event.project_id = uuid.uuid4()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = event
    db.execute = AsyncMock(return_value=mock_result)

    current_user = MagicMock()
    current_user.id = uuid.uuid4()
    body_operator = uuid.uuid4()
    assert body_operator != current_user.id

    req = EventReplayRequest(
        event_id=event.id,
        operator_id=body_operator,
        reason_code="manual_retry",
    )
    with patch(
        "app.routers.task_events.assert_project_permission",
        AsyncMock(return_value=current_user),
    ) as perm:
        with patch(
            "app.routers.task_events.task_event_bus.replay",
            AsyncMock(return_value={"event_id": str(event.id), "status": "queued"}),
        ) as replay:
            await replay_event(req, db, current_user)

    perm.assert_awaited_once()
    assert perm.await_args.args[2] == event.project_id
    assert perm.await_args.args[3] == "edit"
    replay.assert_awaited_once()
    assert replay.await_args.args[2] == current_user.id
    assert replay.await_args.args[2] != body_operator


def test_router_does_not_pass_request_body_operator_to_replay() -> None:
    src = TASK_EVENTS_ROUTER_PATH.read_text(encoding="utf-8")
    assert "req.operator_id" not in src
    assert "current_user.id" in src
    assert "assert_project_permission" in src
