"""Phase 1 测试：附注从披露表刷新服务。

覆盖：
- refresh_note_section（只读）：已同步 → synced / 未同步 → not_synced（不标待更新）/ 不存在 → not_found
- handle_workpaper_saved：只读诊断，参数缺失按原因返回
- 事件注册：**不再**订阅 WORKPAPER_SAVED（spec note-pull-header-formula-closure R1；判据见
  ``test_disclosure_builders_not_wired.py``）
- 路由注册：refresh-from-disclosure 端点存在

spec: note-data-from-disclosure-table Phase 1 Task 5（2026-10-26 改为只读状态）
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
    """已从披露表同步（有 sub_table_data + 底稿来源）→ synced，只读：不改 stale、不改表格。"""
    from app.services.note_disclosure_refresh_service import refresh_note_section

    note = _make_fake_note(has_sub_data=True)
    before = dict(note.table_data)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=note)))
    db.flush = AsyncMock()

    result = await refresh_note_section(
        db, PID, YEAR, wp_code="D2", section_id="八、5",
    )

    assert result.status == "synced"
    assert result.rows_count == 3
    assert note.is_stale is True and note.stale_source == "test", "只读：不清 stale"
    assert note.table_data == before, "只读：不改表格"
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_section_no_data():
    """从未由底稿同步（数据来自模板取数 / 公式推送）→ not_synced，不标「披露表数据为空」待更新。"""
    from app.services.note_disclosure_refresh_service import refresh_note_section

    note = _make_fake_note(has_sub_data=False)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=note)))
    db.flush = AsyncMock()

    result = await refresh_note_section(
        db, PID, YEAR, wp_code="D2", section_id="八、5",
    )

    assert result.status == "not_synced"
    assert "D2" in result.message and "披露页保存一次" in result.message
    assert note.stale_source == "test", "不写 disclosure_refresh_no_data"
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_refresh_section_template_rows_without_fingerprint_is_not_synced():
    """有 sub_table_data 但既无同步指纹、来源也不是底稿（旧模板数据）→ not_synced。"""
    from app.services.note_disclosure_refresh_service import refresh_note_section

    note = _make_fake_note(has_sub_data=True)
    note.table_data["_source"] = "template"
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=note)))

    result = await refresh_note_section(db, PID, YEAR, wp_code="D2", section_id="八、5")
    assert result.status == "not_synced"


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


def test_handler_not_subscribed_to_workpaper_saved():
    """底稿保存不再订阅附注刷新 handler（它曾先跑后端 builder 写错数、再清 / 标 stale）。AST 判据，注释不算。"""
    import ast
    import inspect
    import textwrap

    from app.services import event_handlers_cycle_linkage as linkage

    tree = ast.parse(textwrap.dedent(inspect.getsource(linkage.register_cycle_linkage_handlers)))
    modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert "app.services.note_disclosure_refresh_service" not in modules


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
