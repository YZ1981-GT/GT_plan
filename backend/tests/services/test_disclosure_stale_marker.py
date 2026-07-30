"""披露过期标记兜底 handler 单测。

Spec: .kiro/specs/disclosure-note-follow-actual-content/ R1.4 / R5.1 / Task 4.6
Properties: Property 3（失败不影响底稿保存）/ Property 5（不改 table_data）/
            Property 10（开关关闭即无行为变化）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.services import disclosure_stale_marker as mod


@dataclass
class _Payload:
    project_id: UUID | None = None
    year: int | None = None
    extra: Any = None


PID = uuid4()


@pytest.fixture(autouse=True)
def _clear_registry_cache():
    mod._registry.cache_clear()
    yield
    mod._registry.cache_clear()


@pytest.fixture
def enabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DISCLOSURE_AUTO_SYNC_ENABLED", "true")
    yield


@pytest.fixture
def disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DISCLOSURE_AUTO_SYNC_ENABLED", raising=False)
    yield


# ════════════════════════════════════════════════════════════════════
# 灰度开关（Property 10）
# ════════════════════════════════════════════════════════════════════


def test_disabled_by_default(disabled):
    assert mod.is_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on", " true "])
def test_enabled_values(monkeypatch: pytest.MonkeyPatch, val: str):
    monkeypatch.setenv("DISCLOSURE_AUTO_SYNC_ENABLED", val)
    assert mod.is_enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "", "maybe"])
def test_disabled_values(monkeypatch: pytest.MonkeyPatch, val: str):
    monkeypatch.setenv("DISCLOSURE_AUTO_SYNC_ENABLED", val)
    assert mod.is_enabled() is False


@pytest.mark.asyncio
async def test_handler_returns_disabled_when_off(disabled):
    r = await mod.handle_workpaper_saved_for_disclosure(
        _Payload(project_id=PID, extra={"wp_code": "F2"})
    )
    assert r["status"] == "disabled"
    assert r["marked"] == 0


# ════════════════════════════════════════════════════════════════════
# registry 映射
# ════════════════════════════════════════════════════════════════════


def test_registry_loads_real_file():
    reg = mod._registry()
    assert reg, "note_workpaper_sync_registry.json 未能加载"
    assert "F2" in reg, "registry 缺 F2 映射"


def test_sections_for_f2_covers_both_variants():
    secs = mod.sections_for_wp_code("F2")
    assert "五、9" in secs
    assert "八、10" in secs


def test_sections_for_unknown_wp_code_is_empty():
    assert mod.sections_for_wp_code("ZZ99") == []


@pytest.mark.parametrize("bad", [None, "", "   "])
def test_sections_for_blank_wp_code(bad):
    assert mod.sections_for_wp_code(bad) == []


def test_registry_unavailable_degrades_to_empty(monkeypatch: pytest.MonkeyPatch, tmp_path):
    monkeypatch.setattr(mod, "_REGISTRY_PATH", tmp_path / "nope.json")
    mod._registry.cache_clear()
    assert mod._registry() == {}


# ════════════════════════════════════════════════════════════════════
# wp_code 提取
# ════════════════════════════════════════════════════════════════════


def test_wp_code_from_explicit_field():
    assert mod.wp_code_from_payload({"wp_code": "F2"}) == "F2"


def test_wp_code_trims_whitespace():
    assert mod.wp_code_from_payload({"wp_code": "  K1 "}) == "K1"


@pytest.mark.parametrize(
    "item_id,expected",
    [
        ("F2-note-listed-s2-overrides", "F2"),
        ("F2-note-soe-s5-data-resource", "F2"),
        ("K1-disclosure-listed-rows", "K1"),
        ("D2-1-note-listed-x", "D2-1"),
    ],
)
def test_wp_code_inferred_from_disclosure_item_id(item_id: str, expected: str):
    """extra 缺 wp_code 时按披露 item_id 前缀反推。"""
    assert mod.wp_code_from_payload({"item_ids": [item_id]}) == expected


def test_wp_code_none_for_non_disclosure_items():
    assert mod.wp_code_from_payload({"item_ids": ["F2-1-gross-raw-materials-opening"]}) is None


@pytest.mark.parametrize("extra", [None, {}, "oops", 42, {"item_ids": "not a list"}])
def test_wp_code_tolerates_bad_extra(extra):
    assert mod.wp_code_from_payload(extra) is None


def test_wp_code_explicit_wins_over_items():
    got = mod.wp_code_from_payload(
        {"wp_code": "F2", "item_ids": ["K1-note-listed-x"]}
    )
    assert got == "F2"


# ════════════════════════════════════════════════════════════════════
# handler 四条路径
# ════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_no_project(enabled):
    r = await mod.handle_workpaper_saved_for_disclosure(_Payload(extra={"wp_code": "F2"}))
    assert r["status"] == "no_project"


@pytest.mark.asyncio
async def test_no_wp_code(enabled):
    r = await mod.handle_workpaper_saved_for_disclosure(_Payload(project_id=PID, extra={}))
    assert r["status"] == "no_wp_code"


@pytest.mark.asyncio
async def test_no_mapping_for_non_disclosure_workpaper(enabled):
    """绝大多数 WORKPAPER_SAVED 是非披露底稿 → no_mapping，不得记 error。"""
    r = await mod.handle_workpaper_saved_for_disclosure(
        _Payload(project_id=PID, extra={"wp_code": "ZZ99"})
    )
    assert r["status"] == "no_mapping"
    assert r["marked"] == 0


@pytest.mark.asyncio
async def test_marked_path(enabled, monkeypatch: pytest.MonkeyPatch):
    calls: list[dict[str, Any]] = []

    class _FakeDb:
        async def commit(self) -> None:
            calls.append({"commit": True})

        async def rollback(self) -> None:  # pragma: no cover
            calls.append({"rollback": True})

    class _Ctx:
        async def __aenter__(self):
            return _FakeDb()

        async def __aexit__(self, *a):
            return False

    async def _fake_mark(db, project_id, sections, *, year=None, source=mod.STALE_SOURCE):
        calls.append(
            {"project_id": project_id, "sections": sections, "year": year, "source": source}
        )
        return len(sections)

    monkeypatch.setattr("app.core.database.async_session", lambda: _Ctx())
    monkeypatch.setattr(mod, "mark_sections_stale", _fake_mark)

    r = await mod.handle_workpaper_saved_for_disclosure(
        _Payload(project_id=PID, year=2025, extra={"wp_code": "F2"})
    )
    assert r["status"] == "marked"
    assert r["marked"] == len(r["sections"])
    assert "五、9" in r["sections"]
    marked_call = next(c for c in calls if "sections" in c)
    assert marked_call["year"] == 2025
    assert marked_call["source"] == mod.STALE_SOURCE
    assert any(c.get("commit") for c in calls)


@pytest.mark.asyncio
async def test_failed_path_is_fail_soft(enabled, monkeypatch: pytest.MonkeyPatch):
    """Property 3：标记失败绝不冒泡（底稿保存已提交，不能反向破坏）。"""
    rolled_back: list[bool] = []

    class _FakeDb:
        async def commit(self) -> None:  # pragma: no cover
            pass

        async def rollback(self) -> None:
            rolled_back.append(True)

    class _Ctx:
        async def __aenter__(self):
            return _FakeDb()

        async def __aexit__(self, *a):
            return False

    async def _boom(*a, **kw):
        raise RuntimeError("db down")

    monkeypatch.setattr("app.core.database.async_session", lambda: _Ctx())
    monkeypatch.setattr(mod, "mark_sections_stale", _boom)

    r = await mod.handle_workpaper_saved_for_disclosure(
        _Payload(project_id=PID, extra={"wp_code": "F2"})
    )
    assert r["status"] == "failed"
    assert r["marked"] == 0
    assert rolled_back == [True]


@pytest.mark.asyncio
async def test_mark_sections_stale_noop_on_empty_list():
    assert await mod.mark_sections_stale(None, PID, []) == 0  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_mark_sections_stale_sql_only_touches_stale_columns(monkeypatch: pytest.MonkeyPatch):
    """Property 5：只改 is_stale / stale_source，绝不动 table_data。"""
    captured: dict[str, Any] = {}

    class _Res:
        rowcount = 2

    class _Db:
        async def execute(self, stmt, params=None):
            captured["sql"] = str(stmt)
            captured["params"] = params
            return _Res()

    n = await mod.mark_sections_stale(_Db(), PID, ["五、9", "八、10"], year=2025)  # type: ignore[arg-type]
    assert n == 2
    sql = captured["sql"]
    assert "is_stale = true" in sql
    assert "stale_source" in sql
    assert "table_data" not in sql, "兜底标记不得触碰 table_data"
    assert "year = :year" in sql
    assert captured["params"]["secs"] == ["五、9", "八、10"]


@pytest.mark.asyncio
async def test_mark_sections_stale_without_year_omits_clause(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    class _Res:
        rowcount = 1

    class _Db:
        async def execute(self, stmt, params=None):
            captured["sql"] = str(stmt)
            captured["params"] = params
            return _Res()

    await mod.mark_sections_stale(_Db(), PID, ["五、9"])  # type: ignore[arg-type]
    assert "year = :year" not in captured["sql"]
    assert "year" not in captured["params"]


# ════════════════════════════════════════════════════════════════════
# 注册
# ════════════════════════════════════════════════════════════════════


def test_handler_is_registered_to_event_bus():
    """确认 handler 已挂到 WORKPAPER_SAVED（否则兜底永不触发）。"""
    import inspect

    from app.services import event_handlers_cycle_linkage as linkage

    src = inspect.getsource(linkage.register_cycle_linkage_handlers)
    assert "handle_workpaper_saved_for_disclosure" in src
    assert "WORKPAPER_SAVED" in src
