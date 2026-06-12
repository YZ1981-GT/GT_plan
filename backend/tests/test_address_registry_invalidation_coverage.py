"""地址坐标库失效域覆盖回归测试（联动缺口修复 2026-06-12）。

验证 event_handlers 注册的地址库失效 handler 覆盖全部 5 个域的触发源：

| 域 | 触发事件 |
|----|---------|
| tb | ADJUSTMENT_*, TRIAL_BALANCE_UPDATED, DATA_IMPORTED, DATASET_ACTIVATED/ROLLED_BACK |
| report | REPORTS_UPDATED, DATA_IMPORTED, ... |
| note | NOTE_SECTION_SAVED（修复点：此前仅全量导入才刷新）|
| wp | WORKPAPER_SAVED（修复点：此前仅全量导入才刷新）|
| 全部 | DATA_IMPORTED, LEDGER_DATASET_ACTIVATED, LEDGER_DATASET_ROLLED_BACK（修复点：rollback 此前漏订阅）|

缺口后果：附注章节保存 / 底稿保存后，NOTE(...) / WP(...) 地址坐标缓存陈旧，
跨模块穿透跳转可能定位到旧坐标，直到下次全量导入才刷新。
"""
from __future__ import annotations

import uuid

import pytest

from app.models.audit_platform_schemas import EventPayload, EventType


def _handler_names(event_type: EventType) -> list[str]:
    from app.services.event_bus import event_bus
    from app.services.event_handlers import register_event_handlers

    register_event_handlers()
    return [
        getattr(h, "__qualname__", repr(h))
        for h in event_bus._handlers.get(event_type, [])
    ]


def test_note_section_saved_invalidates_note_domain():
    """NOTE_SECTION_SAVED 必须挂接 _invalidate_addr_note。"""
    names = _handler_names(EventType.NOTE_SECTION_SAVED)
    assert any("_invalidate_addr_note" in n for n in names), (
        f"NOTE_SECTION_SAVED 缺少地址库 note 域失效 handler，实际: {names}"
    )


def test_workpaper_saved_invalidates_wp_domain():
    """WORKPAPER_SAVED 必须挂接 _invalidate_addr_wp。"""
    names = _handler_names(EventType.WORKPAPER_SAVED)
    assert any("_invalidate_addr_wp" in n for n in names), (
        f"WORKPAPER_SAVED 缺少地址库 wp 域失效 handler，实际: {names}"
    )


def test_dataset_rolled_back_invalidates_all_domains():
    """LEDGER_DATASET_ROLLED_BACK 必须挂接 _invalidate_addr_all。"""
    names = _handler_names(EventType.LEDGER_DATASET_ROLLED_BACK)
    assert any("_invalidate_addr_all" in n for n in names), (
        f"LEDGER_DATASET_ROLLED_BACK 缺少地址库全量失效 handler，实际: {names}"
    )


@pytest.mark.asyncio
async def test_note_handler_calls_invalidate_with_note_domain(monkeypatch):
    """_invalidate_addr_note 实际以 domain='note' 调用 invalidate_async。"""
    from app.services.event_bus import event_bus
    from app.services.event_handlers import register_event_handlers

    register_event_handlers()
    handler = next(
        h for h in event_bus._handlers[EventType.NOTE_SECTION_SAVED]
        if "_invalidate_addr_note" in getattr(h, "__qualname__", "")
    )

    captured: dict = {}

    async def fake_invalidate_async(project_id, year=0, domain="", template_type=""):
        captured["project_id"] = project_id
        captured["domain"] = domain

    from app.services import address_registry as addr_mod
    monkeypatch.setattr(
        addr_mod.address_registry, "invalidate_async", fake_invalidate_async
    )

    pid = uuid.uuid4()
    await handler(EventPayload(
        event_type=EventType.NOTE_SECTION_SAVED,
        project_id=pid,
        year=2025,
        extra={"section_code": "八、1"},
    ))

    assert captured.get("domain") == "note"
    assert captured.get("project_id") == pid
