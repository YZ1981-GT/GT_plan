# -*- coding: utf-8 -*-
"""raw SSE 事件降级清单（runtime-performance-and-reload-hardening-followup R3.2）。

`broadcast_raw` 写的是 `sse:project:*`，而 `/events/since` 只读 typed `audit:events`，因此 raw
事件不能冒充可重放。清单的约束：所有生产调用点的字面事件名必须登记；动态常量的已知值必须登记；
前端清单逐值相等；未知 raw event 仍 live 下发但必须 ERROR 提示维护者选择 typed 或登记降级。
"""
from __future__ import annotations

import ast
import asyncio
import logging
import re
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.services.event_bus import (
    RAW_EVENT_REPLAY_DEGRADED,
    RAW_EVENT_REPLAY_DEGRADED_PREFIXES,
    EventBus,
    raw_event_replay_is_degraded,
)

_ROOT = Path(__file__).resolve().parents[2]
_APP = _ROOT / "backend" / "app"
_FRONT = _ROOT / "audit-platform" / "frontend" / "src" / "services" / "sse" / "rawEventRecovery.ts"

_DYNAMIC_VALUES = {
    "consol.refresh.progress",
    "consol.refresh.completed",
    "consol.refresh.error",
    "formula.pushed",
    "procedure_task.event",
    "consol.pushed",
    "consol.push_failed",
    "consol.push_stale",
}


def _literal_broadcast_events() -> set[str]:
    result: set[str] = set()
    for path in _APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else (
                node.func.id if isinstance(node.func, ast.Name) else ""
            )
            if name != "broadcast_raw":
                continue
            arg = node.args[0] if node.args else next(
                (kw.value for kw in node.keywords if kw.arg == "event_type"), None
            )
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                result.add(arg.value)
    return result


def _frontend_exact_values() -> set[str]:
    text = _FRONT.read_text(encoding="utf-8")
    match = re.search(
        r"RAW_EVENT_REPLAY_DEGRADED\s*=\s*\[(.*?)\]\s*as const",
        text,
        re.DOTALL,
    )
    assert match, "前端 raw 降级清单不存在（判据不可空转）"
    return set(re.findall(r"^\s*['\"]([^'\"]+)['\"],?\s*$", match.group(1), re.MULTILINE))


def _frontend_prefix_values() -> tuple[str, ...]:
    text = _FRONT.read_text(encoding="utf-8")
    match = re.search(
        r"RAW_EVENT_REPLAY_DEGRADED_PREFIXES\s*=\s*\[(.*?)\]\s*as const",
        text,
        re.DOTALL,
    )
    assert match
    return tuple(re.findall(r"['\"]([^'\"]+)['\"]", match.group(1)))


def test_every_literal_raw_event_has_explicit_degradation():
    literals = _literal_broadcast_events()
    assert len(literals) >= 30, "扫描分母异常缩水（判据不可空转）"
    assert literals - RAW_EVENT_REPLAY_DEGRADED == set()


def test_dynamic_raw_event_values_are_registered():
    assert _DYNAMIC_VALUES <= RAW_EVENT_REPLAY_DEGRADED
    assert raw_event_replay_is_degraded("formula_runtime.result")
    assert not raw_event_replay_is_degraded("totally.new.raw.event")


def test_frontend_and_backend_inventory_are_identical():
    assert _frontend_exact_values() == set(RAW_EVENT_REPLAY_DEGRADED)
    assert _frontend_prefix_values() == RAW_EVENT_REPLAY_DEGRADED_PREFIXES


@pytest.mark.asyncio
async def test_unknown_raw_event_is_visible_but_not_blocked(caplog):
    bus = EventBus()
    queue = bus.create_sse_queue()
    bus._persist_raw_to_stream = AsyncMock(return_value=None)  # type: ignore[method-assign]
    with caplog.at_level(logging.ERROR):
        bus.broadcast_raw("totally.new.raw.event", {"project_id": "p1"})
        await asyncio.sleep(0)
    assert queue.get_nowait()["event_type"] == "totally.new.raw.event"
    assert "未登记 replay 降级策略" in caplog.text
    bus._persist_raw_to_stream.assert_awaited_once()  # type: ignore[attr-defined]
