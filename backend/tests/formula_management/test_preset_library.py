"""公式预设库结构 + Preset Inventory + 覆盖度测试（Task 14.1 / Req 22.1, 22.3, 22.5, 22.7）。

覆盖：
- 三处源收敛（prefill / check_presets / wide_table）到统一预设库口径
- 去重按 (page_key, target_cell)（Req 22.3）
- 预设条目字段/三类型/引用规范（Req 22.7：refs 为 addr_id/formula_ref，禁裸坐标串）
- Preset Inventory 逐页登记（Req 22.1）与物化 inventory.json 一致
- 覆盖度 presetted/pending 分布（Req 22.5）
- 幂等 seed 脚本（重复构建结果稳定）
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.formula_management import preset_library as pl

VALID_TYPES = {"auto_calc", "logic_check", "reasonability"}


# ── 收敛与去重 ────────────────────────────────────────────────────────────────
def test_build_preset_library_dedup_by_page_key_target_cell():
    """预设库按 (page_key, target_cell) 去重（Req 22.3）。"""
    entries, stats = pl.build_preset_library()
    keys = [e.dedup_key() for e in entries]
    assert len(keys) == len(set(keys)), "预设库存在重复的 (page_key, target_cell)"
    assert stats["inserted"] == len(entries)
    assert stats["inserted"] > 0


def test_converges_three_sources_caliber():
    """三处源收敛到统一口径：prefill + check_presets 至少各有条目。"""
    prefill = pl.convert_prefill_presets()
    checks = pl.convert_check_presets()
    assert len(prefill) > 0, "prefill_formula_mapping 未收敛出预设"
    assert len(checks) > 0, "check_presets 未收敛出预设"
    # 收敛来源标识齐全
    sources = {e.source for e in prefill} | {e.source for e in checks}
    assert "prefill_formula_mapping" in sources
    assert "check_presets" in sources


def test_all_formula_types_are_three_type():
    """所有预设 formula_type ∈ 三类型（auto_calc/logic_check/reasonability）。"""
    entries, _ = pl.build_preset_library()
    for e in entries:
        assert e.formula_type in VALID_TYPES, f"非法 formula_type: {e.formula_type} @ {e.page_key}"


def test_prefill_presets_are_auto_calc():
    """prefill（TB/TB_SUM/ADJ/PREV/WP）收敛为 auto_calc（计算回填）。"""
    for e in pl.convert_prefill_presets():
        assert e.formula_type == "auto_calc"


def test_refs_are_normalized_no_bare_coordinate(monkeypatch):
    """refs 每项为 dict（addr_id/formula_ref），无裸坐标字符串（Req 22.7 / Req 11.5）。"""
    entries, _ = pl.build_preset_library()
    for e in entries:
        for ref in e.refs:
            assert isinstance(ref, dict), f"引用非规范 dict: {ref!r} @ {e.page_key}"
            assert ("addr_id" in ref) or ("formula_ref" in ref), (
                f"引用缺 addr_id/formula_ref: {ref!r}"
            )


def test_page_key_scope_prefix():
    """page_key 形如 scope:key，scope ∈ {workpaper, report, note}。"""
    entries, _ = pl.build_preset_library()
    for e in entries:
        assert ":" in e.page_key
        scope = e.page_key.split(":", 1)[0]
        assert scope in {"workpaper", "report", "note"}, f"未知 scope: {scope}"


# ── Preset Inventory（Req 22.1） ─────────────────────────────────────────────
def test_inventory_pages_presetted():
    """出现在预设库的页面登记为 presetted，且 formula_count > 0。"""
    entries, _ = pl.build_preset_library()
    pages = pl.build_inventory(entries)
    assert len(pages) > 0
    for p in pages:
        assert p.preset_status == "presetted"
        assert p.formula_count >= 1
    # formula_count 之和 == 预设条目数
    assert sum(p.formula_count for p in pages) == len(entries)


def test_materialized_inventory_json_consistent():
    """物化的 inventory.json 与运行时构建一致（幂等物化）。"""
    assert pl.INVENTORY_PATH.exists(), "inventory.json 未生成（先运行 seed 脚本）"
    doc = json.loads(pl.INVENTORY_PATH.read_text(encoding="utf-8"))
    entries, _ = pl.build_preset_library()
    pages = pl.build_inventory(entries)
    assert doc["summary"]["total_pages"] == len(pages)
    assert doc["summary"]["total_formulas"] == len(entries)


# ── 覆盖度 presetted/pending（Req 22.5） ─────────────────────────────────────
def test_coverage_presetted_only_without_universe():
    """无 eligible 全集时仅报 presetted（pending=0）。"""
    cov = pl.compute_preset_coverage()
    assert cov["total_preset_pages"] > 0
    assert cov["by_status"]["pending"] == 0
    assert cov["by_status"]["presetted"] > 0


def test_coverage_pending_derived_from_eligible():
    """给定 workpaper 应承载公式全集时，pending = 全集 − 已预设。"""
    entries, _ = pl.build_preset_library()
    presetted_wp = {
        p.wp_code for p in pl.build_inventory(entries) if p.scope == "workpaper" and p.wp_code
    }
    # 构造一个含未预设编码的全集
    eligible = presetted_wp | {"ZZ_FAKE_PENDING"}
    cov = pl.compute_preset_coverage(eligible_workpaper_codes=eligible)
    wp_row = next(r for r in cov["by_scope"] if r["scope"] == "workpaper")
    assert wp_row["pending_pages"] >= 1
    assert wp_row["presetted_pages"] == len(presetted_wp)
    assert wp_row["total_pages"] == wp_row["presetted_pages"] + wp_row["pending_pages"]


# ── 幂等 seed 脚本 ────────────────────────────────────────────────────────────
def test_seed_script_build_is_stable():
    """重复构建 inventory 文档结果稳定（幂等，遵循 seed 去重模式）。"""
    from scripts.seed.seed_formula_presets import build_inventory_doc

    doc1, stats1 = build_inventory_doc()
    doc2, stats2 = build_inventory_doc()
    assert json.dumps(doc1, ensure_ascii=False, sort_keys=True) == json.dumps(
        doc2, ensure_ascii=False, sort_keys=True
    )
    assert stats1 == stats2


def test_seed_only_mode_excludes_sources():
    """--seed-only 仅用显式 seed，不收敛既有源。

    显式 seed 覆盖 Task 14.3 逐页预设试点（D 循环审定表 workpaper: / 报表勾稽
    report: / 附注核心页 note:），scope 限于三类；且始终 ⊊ 收敛全集。
    """
    seed_entries, _ = pl.build_preset_library(include_sources=False)
    full_entries, _ = pl.build_preset_library(include_sources=True)
    assert 0 < len(seed_entries) < len(full_entries)
    assert all(
        e.page_key.split(":", 1)[0] in {"report", "workpaper", "note"}
        for e in seed_entries
    )


def test_seed_pilot_refs_are_acnr_resolvable_grammar():
    """Task 14.3：逐页预设引用一律 ACNR addr_id/formula_ref，经 grammar_v1 可解析（Req 22.7）。

    显式 seed 试点条目的 formula_ref 引用应全部归一化为 ACNR canonical
    （migrated），无裸坐标/未映射函数残留。
    """
    from app.services.formula_management.preset_acnr_migration import normalize_ref

    seed_entries, _ = pl.build_preset_library(include_sources=False)
    assert seed_entries, "显式 seed 预设为空"
    for e in seed_entries:
        for ref in e.refs:
            expr = ref.get("formula_ref") or ref.get("addr_id")
            assert expr, f"引用缺 formula_ref/addr_id: {ref!r} @ {e.page_key}"
            nr = normalize_ref(expr)
            assert nr.migrated, (
                f"引用非 ACNR grammar_v1 可解析: {expr!r} "
                f"(status={nr.status}, reason={nr.reason}) @ {e.page_key}/{e.target_cell}"
            )


def test_seed_pilot_covers_d_cycle_report_note():
    """Task 14.3：试点覆盖 D 循环 + 报表 + 附注核心页面（Req 22.2, 22.6）。"""
    seed_entries, _ = pl.build_preset_library(include_sources=False)
    page_keys = {e.page_key for e in seed_entries}
    # D 循环审定表结构（试点 D1/D2/D4）
    assert {"workpaper:D1", "workpaper:D2", "workpaper:D4"} <= page_keys
    # 报表核心页勾稽
    assert "report:cross_check" in page_keys
    # 附注核心页
    assert {"note:五、4", "note:五、5"} <= page_keys
    # 三类型齐全（auto_calc / logic_check / reasonability）
    types = {e.formula_type for e in seed_entries}
    assert {"auto_calc", "logic_check", "reasonability"} <= types
