"""核对表保存发出的 WORKPAPER_SAVED 带上保存人（spec writeback-followup-issue-closure R7.2）。

附注刷新等下游按 `extra.user_id` 记 `updated_by`；事件不带它时只能记成系统重算（修前更糟：
builder 拿全零 UUID 当用户，撞 `disclosure_notes_updated_by_fkey`，真库判据见
`test_note_refresh_after_save_pg.py`）。
"""
from __future__ import annotations

import ast
import uuid
from pathlib import Path

import pytest

from app.routers import checklist_responses as R

_ROUTER = Path(R.__file__)


@pytest.mark.asyncio
async def test_event_carries_the_saver(monkeypatch):
    from app.services.event_bus import event_bus

    captured: list = []

    async def _publish(payload):
        captured.append(payload)

    monkeypatch.setattr(event_bus, "publish", _publish)
    saver = uuid.uuid4()
    await R._publish_checklist_saved(
        project_id=uuid.uuid4(), wp_id=uuid.uuid4(), wp_code="D3", year=2025, item_ids=["D3-x"], user_id=saver,
    )
    assert captured[0].extra["user_id"] == str(saver)


@pytest.mark.asyncio
async def test_event_without_saver_has_no_placeholder(monkeypatch):
    from app.services.event_bus import event_bus

    captured: list = []

    async def _publish(payload):
        captured.append(payload)

    monkeypatch.setattr(event_bus, "publish", _publish)
    await R._publish_checklist_saved(project_id=uuid.uuid4(), wp_id=uuid.uuid4(), wp_code="D3", year=2025, item_ids=[])
    assert "user_id" not in captured[0].extra, "没有保存人就不带，不编占位身份"


def test_every_save_path_passes_the_current_user():
    """调用点漏传 user_id 时函数照样能调通，只能靠结构判据钉住（每个调用点都显式传了）。"""
    tree = ast.parse(_ROUTER.read_text(encoding="utf-8"))
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_publish_checklist_saved"
    ]
    assert calls, "保存路径必须发 WORKPAPER_SAVED"
    for call in calls:
        assert any(kw.arg == "user_id" for kw in call.keywords), f"第 {call.lineno} 行没有传 user_id"
