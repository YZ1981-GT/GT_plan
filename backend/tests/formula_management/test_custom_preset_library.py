"""自定义预设收敛口径测试（template-library-formula-preset-custom Wave 1；formula-global-settings-sync R14.3 改存数据库）。

覆盖 Property 4/7 + 迁库口径：
- P4 自定义同键覆盖通用（数据库自定义 > 旧文件 > seed > 收敛源，去重首个赢）
- P7 零回归（自定义为空时 ``build_preset_library`` 口径不变）
- 旧文件 ``formula_custom_presets.json`` 只读兼容；预设库读不写文件
- 读时补刷钩子：读预设库会触发缓存补刷（失败不影响读取）

隔离：``CUSTOM_PATH`` 指向 tmp_path；数据库自定义预设走进程内缓存，用例结束清空。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.formula_management import preset_library as pl
from app.services.formula_management.preset_library import PresetEntry


@pytest.fixture(autouse=True)
def clean_db_cache():
    pl.set_db_custom_entries([])
    pl.set_db_custom_refresher(None)
    yield
    pl.set_db_custom_entries([])
    pl.set_db_custom_refresher(None)


@pytest.fixture
def tmp_custom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把 CUSTOM_PATH 重定向到临时文件（隔离，不碰真实自定义文件）。"""
    p = tmp_path / "formula_custom_presets.json"
    p.write_text(json.dumps({"description": "test", "version": "t", "presets": []}, ensure_ascii=False),
                 encoding="utf-8")
    monkeypatch.setattr(pl, "CUSTOM_PATH", p)
    return p


def _entry(page_key: str, target_cell: str, expr: str = "=TB('1001')") -> PresetEntry:
    return PresetEntry(page_key=page_key, target_cell=target_cell, expression=expr, formula_type="auto_calc",
                       refs=[], source="custom", description="test custom")


def test_upsert_writer_removed_and_library_never_writes(tmp_custom: Path):
    """R14.3：不再有写仓库 JSON 的函数；建库只读。"""
    assert not hasattr(pl, "upsert_custom_presets")
    before = tmp_custom.read_bytes()
    pl.set_db_custom_entries([_entry("note:测试章节", "R1C1")])
    pl.build_preset_library()
    assert tmp_custom.read_bytes() == before


# ── P7: 零回归（自定义为空口径不变） ─────────────────────────────────────────
def test_empty_custom_preserves_baseline(tmp_custom: Path):
    entries, stats = pl.build_preset_library()
    keys = [e.dedup_key() for e in entries]
    assert len(keys) == len(set(keys))
    assert stats["inserted"] == len(entries) > 0
    assert all(e.source != "custom" for e in entries)
    seed_only, _ = pl.build_preset_library(include_sources=False)
    assert all(e.source != "custom" for e in seed_only)
    assert 0 < len(seed_only) < len(entries)


# ── P4: 自定义同键覆盖通用；数据库 > 旧文件 ──────────────────────────────────
def test_db_custom_overrides_file_and_seed_on_same_key(tmp_custom: Path):
    seed = pl.load_seed_presets()
    assert seed, "需要非空 seed 作对照"
    target = seed[0]
    tmp_custom.write_text(json.dumps({"presets": [
        {"page_key": target.page_key, "target_cell": target.target_cell, "expression": "=FILE_MARKER()",
         "formula_type": "auto_calc"},
        {"page_key": "note:旧文件独有", "target_cell": "R1C1", "expression": "=TB('1')", "formula_type": "auto_calc"},
    ]}, ensure_ascii=False), encoding="utf-8")
    entries, _ = pl.build_preset_library()
    hit = [e for e in entries if e.dedup_key() == target.dedup_key()]
    assert [(e.source, e.expression) for e in hit] == [("custom", "=FILE_MARKER()")], "旧文件只读兼容仍生效"
    pl.set_db_custom_entries([_entry(target.page_key, target.target_cell, "=DB_MARKER()")])
    entries, stats = pl.build_preset_library()
    hit = [e for e in entries if e.dedup_key() == target.dedup_key()]
    assert [(e.source, e.expression) for e in hit] == [("custom", "=DB_MARKER()")], "数据库自定义优先"
    assert any(e.page_key == "note:旧文件独有" for e in entries)
    assert stats.get("source:custom", 0) >= 2


def test_explicit_custom_entries_argument_wins_over_cache(tmp_custom: Path):
    pl.set_db_custom_entries([_entry("note:缓存", "R1C1")])
    entries, _ = pl.build_preset_library(custom_entries=[_entry("note:显式", "R1C1")])
    pages = {e.page_key for e in entries if e.source == "custom"}
    assert "note:显式" in pages and "note:缓存" not in pages


def test_reading_library_triggers_refresher_and_survives_its_failure(tmp_custom: Path):
    calls: list[int] = []

    def refresher():
        calls.append(1)
        raise RuntimeError("连不上库")

    pl.set_db_custom_refresher(refresher)
    pl.set_db_custom_entries([_entry("note:仍可读", "R2C2")])
    entries, _ = pl.build_preset_library()
    assert calls and any(e.page_key == "note:仍可读" for e in entries), "补刷失败沿用当前缓存"


# ── 草稿刷新读取口径回归（R14.3：自定义优先于基线，改存数据库后不变） ──────────
def test_draft_refresh_applies_db_custom_over_seed(tmp_custom: Path):
    from app.services.draft_refresh_service import DraftRefreshService

    seed = pl.load_seed_presets()
    target = seed[0]
    baseline = DraftRefreshService().build_preset_draft_units([target.page_key])
    unit = next(u for u in baseline.units if u.after_value["target_cell"] == target.target_cell)
    assert unit.after_value["expression"] == target.expression
    pl.set_db_custom_entries([_entry(target.page_key, target.target_cell, "=DB_CUSTOM_MARKER()"),
                              _entry("note:仅自定义页", "R1C1")])
    app = DraftRefreshService().build_preset_draft_units([target.page_key, "note:仅自定义页"])
    unit = next(u for u in app.units if u.after_value["target_cell"] == target.target_cell)
    assert unit.after_value["expression"] == "=DB_CUSTOM_MARKER()", "数据库自定义优先于基线"
    assert "note:仅自定义页" in app.presetted_pages
