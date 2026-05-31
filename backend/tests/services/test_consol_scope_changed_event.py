"""CONSOL_SCOPE_CHANGED 事件发射单测（consol-phase3-frontend-drilldown / 需求 5.2 / T4）.

覆盖：
- _emit_scope_changed 调 event_bus.broadcast_raw("consol.scope_changed", {project_id, year})
- event_bus 不可用 / 抛错时静默回退（不阻断业务，EH4 由前端"刷新树"兜底）
- EventType.CONSOL_SCOPE_CHANGED 枚举存在且值正确

Validates: Requirements 5.2; Property T4 (scope 变更触发树重建的事件侧).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.services.consol_scope_service import _emit_scope_changed


def test_emit_scope_changed_broadcasts_raw():
    """_emit_scope_changed 以正确事件名 + payload 调 broadcast_raw."""
    pid = uuid4()
    mock_bus = MagicMock()
    with patch("app.services.event_bus.event_bus", mock_bus):
        _emit_scope_changed(pid, 2025)

    mock_bus.broadcast_raw.assert_called_once()
    args, _ = mock_bus.broadcast_raw.call_args
    assert args[0] == "consol.scope_changed"
    assert args[1] == {"project_id": str(pid), "year": 2025}


def test_emit_scope_changed_year_none_ok():
    """year 缺失（None）时仍广播，payload.year=None."""
    pid = uuid4()
    mock_bus = MagicMock()
    with patch("app.services.event_bus.event_bus", mock_bus):
        _emit_scope_changed(pid, None)

    args, _ = mock_bus.broadcast_raw.call_args
    assert args[1]["year"] is None
    assert args[1]["project_id"] == str(pid)


def test_emit_scope_changed_swallows_errors():
    """broadcast_raw 抛错时静默回退，不向上抛（不阻断业务）."""
    pid = uuid4()
    mock_bus = MagicMock()
    mock_bus.broadcast_raw.side_effect = RuntimeError("no event loop")
    with patch("app.services.event_bus.event_bus", mock_bus):
        # 不抛异常即通过
        _emit_scope_changed(pid, 2025)


def test_event_type_enum_present():
    """EventType.CONSOL_SCOPE_CHANGED 枚举存在且值为 consol.scope_changed."""
    from app.models.audit_platform_schemas import EventType

    assert EventType.CONSOL_SCOPE_CHANGED.value == "consol.scope_changed"
