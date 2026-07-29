"""Characterization 安全网（template-library-formula-preset-custom Task 1.1）。

锁定改动前的既有口径，作为后续「自定义预设隔离」零回归对照（Property 7）：
- ``build_preset_library`` 去重/stats 口径（无 custom 源时的基线）
- 当前预设库**不含** ``source='custom'`` 条目（custom 尚未成为源）
- ``formula_presets_seed.json`` 可加载且非空（基线内容存在）
- ``build_inventory`` / ``find_presets_for_page`` 条目带 ``source`` 字段（GET /presets/inventory、
  GET /presets/page 响应形状的服务层来源，路由仅薄封装）

引入 custom 源（Task 2.1）后，custom 文件初始为空 → 这些断言应仍全绿
（空 custom 使 ``[custom=[], seed, ...]`` 去重结果与改前 ``[seed, ...]`` 逐字节一致）。

Requirements: 5.1, 5.2
"""

from __future__ import annotations

from app.services.formula_management import preset_library as pl

VALID_TYPES = {"auto_calc", "logic_check", "reasonability"}


# ── build_preset_library 基线口径 ─────────────────────────────────────────────
def test_baseline_dedup_and_stats_consistent():
    """去重后条目数 == stats.inserted，且 (page_key, target_cell) 唯一。"""
    entries, stats = pl.build_preset_library()
    keys = [e.dedup_key() for e in entries]
    assert len(keys) == len(set(keys)), "预设库存在重复 (page_key, target_cell)"
    assert stats["inserted"] == len(entries)
    assert stats["inserted"] > 0
    assert stats.get("skipped", 0) >= 0


def test_baseline_has_no_custom_source():
    """改动前预设库不含 source='custom' 条目（custom 尚未成为源）。

    Task 2.1 引入空 custom 文件后此断言仍应成立（空 custom 无条目）。
    """
    entries, _ = pl.build_preset_library()
    custom = [e for e in entries if e.source == "custom"]
    assert custom == [], f"改动前不应有 custom 条目，实得 {len(custom)} 条"


def test_baseline_include_sources_false_is_seed_only():
    """include_sources=False 仅含显式预设（当前 = seed）。

    引入 custom（空）后仍应等价：custom 与 include_sources 正交、恒前置，
    但空 custom 不增条目。
    """
    seed_entries, _ = pl.build_preset_library(include_sources=False)
    full_entries, _ = pl.build_preset_library(include_sources=True)
    assert 0 < len(seed_entries) < len(full_entries)
    # seed-only 结果同样无 custom（改动前）
    assert all(e.source != "custom" for e in seed_entries)


def test_baseline_all_formula_types_valid():
    entries, _ = pl.build_preset_library()
    for e in entries:
        assert e.formula_type in VALID_TYPES, f"非法 formula_type: {e.formula_type} @ {e.page_key}"


# ── seed 文件基线（存在且非空） ───────────────────────────────────────────────
def test_baseline_seed_presets_loadable_nonempty():
    """formula_presets_seed.json 可加载且非空（基线内容存在，供 P2 未被写守卫对照）。"""
    seed = pl.load_seed_presets()
    assert len(seed) > 0, "显式 seed 预设为空（先运行 seed 脚本）"
    assert all(e.source != "custom" for e in seed), "seed 条目不应标 custom"


# ── inventory / page 响应形状（服务层，路由薄封装） ──────────────────────────
def test_baseline_inventory_pages_have_source_bearing_entries():
    """build_inventory 逐页登记 + 条目带 source（GET /presets/inventory 来源）。"""
    entries, _ = pl.build_preset_library()
    pages = pl.build_inventory(entries)
    assert len(pages) > 0
    for p in pages:
        assert p.preset_status == "presetted"
        assert p.formula_count > 0
    # 每条预设条目均带 source（前端据此判通用/自定义）
    for e in entries:
        assert isinstance(e.source, str) and e.source, f"条目缺 source @ {e.page_key}"


def test_baseline_find_presets_for_page_entries_have_source():
    """find_presets_for_page（GET /presets/page 来源）返回条目带 source。"""
    entries, _ = pl.build_preset_library()
    assert entries
    sample_page = entries[0].page_key
    found = pl.find_presets_for_page(sample_page, entries=entries)
    assert found, f"页面 {sample_page} 应有预设"
    for e in found:
        assert hasattr(e, "source") and e.source
