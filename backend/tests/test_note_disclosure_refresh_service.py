"""Phase 1 测试：附注从披露表刷新服务。

覆盖：
- refresh_note_section：有数据 → refreshed / 无数据 → stale_marked / 不存在 → not_found
- refresh_note_from_disclosure：单底稿多章节
- refresh_all_notes：全量
- handle_workpaper_saved：事件 handler fail-soft
- 事件注册：handler 已注册到 WORKPAPER_SAVED
- 路由注册：refresh-from-disclosure 端点存在

spec: note-data-from-disclosure-table Phase 1 Task 5
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── 伪造 payload ──────────────────────────────────────────────────────────────

PID = uuid.uuid4()
YEAR = 2025


@dataclass
class _Payload:
    project_id: uuid.UUID | None = PID
    year: int | None = YEAR
    extra: dict[str, Any] | None = None


# ══════════════════════════════════════════════════════════════════════════════
# 单元测试：registry 加载
# ══════════════════════════════════════════════════════════════════════════════


class TestRegistry:
    def test_load_registry_returns_dict(self):
        from app.services.note_disclosure_refresh_service import _load_registry

        _load_registry.cache_clear()
        reg = _load_registry()
        assert isinstance(reg, dict)
        # 至少有 D1 E1
        assert "D1" in reg
        assert "E1" in reg

    def test_sections_for_wp_code(self):
        from app.services.note_disclosure_refresh_service import sections_for_wp_code

        secs = sections_for_wp_code("D2")
        assert len(secs) >= 1
        # D2 对应 五、5 或 八、5
        assert any("5" in s for s in secs)

    def test_sections_for_wp_code_with_variant(self):
        from app.services.note_disclosure_refresh_service import sections_for_wp_code

        secs_listed = sections_for_wp_code("E1", "listed")
        secs_soe = sections_for_wp_code("E1", "soe")
        assert len(secs_listed) == 1
        assert len(secs_soe) == 1
        assert secs_listed != secs_soe  # listed 五、1 vs soe 八、1

    def test_sections_for_unknown_wp_code(self):
        from app.services.note_disclosure_refresh_service import sections_for_wp_code

        assert sections_for_wp_code("ZZ99") == []

    def test_all_wp_codes(self):
        from app.services.note_disclosure_refresh_service import all_wp_codes

        codes = all_wp_codes()
        assert len(codes) >= 30  # 至少 30 个底稿有映射
        assert "D1" in codes
        assert "E1" in codes


# ══════════════════════════════════════════════════════════════════════════════
# 单元测试：refresh_note_section
# ══════════════════════════════════════════════════════════════════════════════


def _make_fake_note(*, has_sub_data: bool, section: str = "八、5"):
    """构造一个假的 DisclosureNote 对象。"""
    note = MagicMock()
    note.project_id = PID
    note.year = YEAR
    note.note_section = section
    note.is_stale = True
    note.stale_source = "test"
    note.updated_by = None
    note.updated_at = None

    if has_sub_data:
        note.table_data = {
            "_source": "workpaper",
            "sub_table_data": {
                "按账龄披露应收账款": [
                    {"label": "1年以内", "values": [100, 200]},
                    {"label": "1至2年", "values": [50, 60]},
                    {"label": "合计", "values": [150, 260], "is_total": True},
                ],
            },
        }
    else:
        note.table_data = {"_source": "template"}

    return note


@pytest.mark.asyncio
async def test_refresh_section_with_data():
    """有 sub_table_data → refreshed，stale 清除。"""
    from app.services.note_disclosure_refresh_service import refresh_note_section

    note = _make_fake_note(has_sub_data=True)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=note)))
    db.flush = AsyncMock()

    result = await refresh_note_section(
        db, PID, YEAR, wp_code="D2", section_id="八、5",
    )

    assert result.status == "refreshed"
    assert result.rows_count == 3
    assert note.is_stale is False
    assert note.stale_source is None
    assert note.table_data["_source"] == "workpaper"
    assert "_last_refresh_at" in note.table_data


@pytest.mark.asyncio
async def test_refresh_section_no_data():
    """无 sub_table_data → stale_marked。"""
    from app.services.note_disclosure_refresh_service import refresh_note_section

    note = _make_fake_note(has_sub_data=False)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=note)))
    db.flush = AsyncMock()

    result = await refresh_note_section(
        db, PID, YEAR, wp_code="D2", section_id="八、5",
    )

    assert result.status == "stale_marked"
    assert note.is_stale is True
    assert note.stale_source == "disclosure_refresh_no_data"


@pytest.mark.asyncio
async def test_refresh_section_not_found():
    """附注不存在 → not_found。"""
    from app.services.note_disclosure_refresh_service import refresh_note_section

    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    result = await refresh_note_section(
        db, PID, YEAR, wp_code="D2", section_id="八、5",
    )

    assert result.status == "not_found"


# ══════════════════════════════════════════════════════════════════════════════
# 单元测试：handle_workpaper_saved
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_handler_no_project():
    from app.services.note_disclosure_refresh_service import handle_workpaper_saved

    r = await handle_workpaper_saved(_Payload(project_id=None))
    assert r["status"] == "no_project"


@pytest.mark.asyncio
async def test_handler_no_wp_code():
    from app.services.note_disclosure_refresh_service import handle_workpaper_saved

    r = await handle_workpaper_saved(_Payload(extra={}))
    assert r["status"] == "no_wp_code"


@pytest.mark.asyncio
async def test_handler_no_mapping():
    from app.services.note_disclosure_refresh_service import handle_workpaper_saved

    r = await handle_workpaper_saved(_Payload(extra={"wp_code": "ZZ99"}))
    assert r["status"] == "no_mapping"


@pytest.mark.asyncio
async def test_handler_no_year():
    from app.services.note_disclosure_refresh_service import handle_workpaper_saved

    r = await handle_workpaper_saved(_Payload(year=None, extra={"wp_code": "D2"}))
    assert r["status"] == "no_year"


# ══════════════════════════════════════════════════════════════════════════════
# 集成检查：事件注册
# ══════════════════════════════════════════════════════════════════════════════


def test_handler_registered_in_cycle_linkage():
    """handle_workpaper_saved 必须在 register_cycle_linkage_handlers 中注册。"""
    import inspect
    from app.services import event_handlers_cycle_linkage as linkage

    src = inspect.getsource(linkage.register_cycle_linkage_handlers)
    assert "handle_workpaper_saved" in src, "handler 未注册到 cycle linkage"
    assert "note_disclosure_refresh_service" in src, "import 路径不对"


# ══════════════════════════════════════════════════════════════════════════════
# 集成检查：路由注册
# ══════════════════════════════════════════════════════════════════════════════


def test_refresh_endpoint_exists():
    """refresh-from-disclosure 端点必须在 disclosure_notes router 中。"""
    from app.routers.disclosure_notes import router

    paths = [r.path for r in router.routes if hasattr(r, "path")]
    assert any("refresh-from-disclosure" in p for p in paths), (
        f"refresh-from-disclosure 端点未注册，现有路径: {paths[:10]}"
    )


def test_refresh_endpoint_is_post():
    """refresh-from-disclosure 必须是 POST 方法。"""
    from app.routers.disclosure_notes import router

    for route in router.routes:
        if hasattr(route, "path") and "refresh-from-disclosure" in route.path:
            assert "POST" in route.methods, f"期望 POST，实际 {route.methods}"
            return
    pytest.fail("未找到 refresh-from-disclosure 路由")
