"""反向联动 handler 回归测试（公式管理联动缺口修复）。

覆盖 event_handlers 中两个反向联动 handler：
- _stale_engine_on_formula_config_changed
- _stale_engine_on_prefill_mapping_changed

验证修复点（2026-06-12）：
1. 报表公式/预填映射变更 → 失效 FormulaReverseIndex 单例
   （否则 /formula-usage、/cell-detail 面板显示过时引用关系直到进程重启）。
2. on_change 返回 affected=0 且非降级时 → 记录 degraded（暴露漏标，不静默）。

这两个 handler 此前零测试覆盖，正是 staleness 缺口长期未被发现的原因。
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.models.audit_platform_schemas import EventPayload, EventType


def _get_handler(event_type: EventType, name_fragment: str):
    """注册全部 handler 后，从 event_bus 取出匹配名字片段的 handler。"""
    from app.services.event_bus import event_bus
    from app.services.event_handlers import register_event_handlers

    register_event_handlers()
    handlers = event_bus._handlers.get(event_type, [])
    for h in handlers:
        if name_fragment in getattr(h, "__qualname__", repr(h)):
            return h
    raise AssertionError(
        f"handler with fragment {name_fragment!r} not found for {event_type}"
    )


@pytest.mark.asyncio
async def test_formula_config_changed_invalidates_reverse_index():
    """报表公式变更 → 失效反向索引单例。"""
    handler = _get_handler(
        EventType.FORMULA_CONFIG_CHANGED, "_stale_engine_on_formula_config_changed"
    )

    project_id = uuid.uuid4()
    payload = EventPayload(
        event_type=EventType.FORMULA_CONFIG_CHANGED,
        project_id=project_id,
        year=2025,
        extra={"row_code": "BS-1"},
    )

    with patch(
        "app.services.formula_reverse_index.invalidate_reverse_index"
    ) as mock_invalidate, patch(
        "app.services.stale_propagation_engine.stale_engine.on_change",
        new=AsyncMock(return_value={"affected": ["WP:D2::"], "total": 1, "degraded": False}),
    ):
        await handler(payload)

    mock_invalidate.assert_called_once()


@pytest.mark.asyncio
async def test_formula_config_changed_affected_zero_logs_degraded():
    """on_change affected=0 且非降级 → 记录 degraded（暴露漏标）。"""
    handler = _get_handler(
        EventType.FORMULA_CONFIG_CHANGED, "_stale_engine_on_formula_config_changed"
    )

    project_id = uuid.uuid4()
    payload = EventPayload(
        event_type=EventType.FORMULA_CONFIG_CHANGED,
        project_id=project_id,
        year=2025,
        extra={"row_code": "BS-99"},
    )

    with patch(
        "app.services.formula_reverse_index.invalidate_reverse_index"
    ), patch(
        "app.services.stale_propagation_engine.stale_engine.on_change",
        new=AsyncMock(return_value={"affected": [], "total": 0, "degraded": False}),
    ), patch(
        "app.services.stale_degraded_logger.log_stale_degraded"
    ) as mock_log:
        await handler(payload)

    mock_log.assert_called_once()
    _, kwargs = mock_log.call_args
    assert "formula_config_changed" in kwargs["source"]


@pytest.mark.asyncio
async def test_formula_config_changed_degraded_not_logged_when_engine_degraded():
    """on_change 返回 degraded=True（图加载失败已 fallback）→ 不重复记 degraded。"""
    handler = _get_handler(
        EventType.FORMULA_CONFIG_CHANGED, "_stale_engine_on_formula_config_changed"
    )

    payload = EventPayload(
        event_type=EventType.FORMULA_CONFIG_CHANGED,
        project_id=uuid.uuid4(),
        year=2025,
        extra={"row_code": "BS-1"},
    )

    with patch(
        "app.services.formula_reverse_index.invalidate_reverse_index"
    ), patch(
        "app.services.stale_propagation_engine.stale_engine.on_change",
        new=AsyncMock(return_value={"affected": [], "total": 0, "degraded": True}),
    ), patch(
        "app.services.stale_degraded_logger.log_stale_degraded"
    ) as mock_log:
        await handler(payload)

    mock_log.assert_not_called()


@pytest.mark.asyncio
async def test_prefill_mapping_changed_invalidates_reverse_index():
    """预填映射变更 → 失效反向索引单例。"""
    handler = _get_handler(
        EventType.PREFILL_MAPPING_CHANGED, "_stale_engine_on_prefill_mapping_changed"
    )

    payload = EventPayload(
        event_type=EventType.PREFILL_MAPPING_CHANGED,
        project_id=uuid.uuid4(),
        year=2025,
        extra={"changed_wp_codes": ["D2", "D2-2"]},
    )

    with patch(
        "app.services.formula_reverse_index.invalidate_reverse_index"
    ) as mock_invalidate, patch(
        "app.services.stale_propagation_engine.stale_engine.on_change",
        new=AsyncMock(return_value={"affected": [], "total": 0, "degraded": False}),
    ):
        await handler(payload)

    mock_invalidate.assert_called_once()
