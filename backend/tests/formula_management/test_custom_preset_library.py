"""自定义预设收敛源与隔离存储测试（template-library-formula-preset-custom Wave 1）。

覆盖 Property 2/4/7：
- P2 自定义不写入通用基线（``upsert_custom_presets`` 后 seed 逐字节不变）
- P4 自定义同键覆盖通用（custom 置于 seed 之前，去重首个赢）
- P7 零回归（custom 为空时 ``build_preset_library`` 口径不变）
- ``upsert_custom_presets`` 幂等（重复写同键仅 update 不追加）

隔离：所有写测试用 ``monkeypatch`` 把 ``CUSTOM_PATH`` 指向 tmp_path，绝不碰真实数据文件。

Requirements: 3.2, 5.1, 6.1
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.formula_management import preset_library as pl
from app.services.formula_management.preset_library import PresetEntry


@pytest.fixture
def tmp_custom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把 CUSTOM_PATH 重定向到临时文件（隔离，不碰真实自定义文件）。"""
    p = tmp_path / "formula_custom_presets.json"
    p.write_text(
        json.dumps(
            {"description": "test", "version": "t", "presets": []},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(pl, "CUSTOM_PATH", p)
    return p


def _entry(page_key: str, target_cell: str, expr: str = "=TB('1001')") -> PresetEntry:
    return PresetEntry(
        page_key=page_key,
        target_cell=target_cell,
        expression=expr,
        formula_type="auto_calc",
        refs=[],
        source="custom",
        description="test custom",
    )


# ── P2: 自定义不写入通用基线 ──────────────────────────────────────────────────
def test_upsert_custom_does_not_touch_seed(tmp_custom: Path):
    seed_before = pl.SEED_PATH.read_bytes()
    pl.upsert_custom_presets([_entry("note:测试章节", "R1C1")])
    seed_after = pl.SEED_PATH.read_bytes()
    assert seed_before == seed_after, "upsert_custom_presets 不得改动 formula_presets_seed.json"


def test_upsert_custom_writes_only_custom_file(tmp_custom: Path):
    pl.upsert_custom_presets([_entry("workpaper:ZZ99", "A1")])
    saved = json.loads(tmp_custom.read_text(encoding="utf-8"))
    assert len(saved["presets"]) == 1
    assert saved["presets"][0]["source"] == "custom"
    assert saved["presets"][0]["page_key"] == "workpaper:ZZ99"


# ── upsert 幂等 ───────────────────────────────────────────────────────────────
def test_upsert_custom_idempotent(tmp_custom: Path):
    s1 = pl.upsert_custom_presets([_entry("note:X", "R2C2", "=TB('1002')")])
    assert s1 == {"inserted": 1, "updated": 0, "total": 1}
    s2 = pl.upsert_custom_presets([_entry("note:X", "R2C2", "=TB('9999')")])
    assert s2["updated"] == 1 and s2["inserted"] == 0 and s2["total"] == 1
    saved = json.loads(tmp_custom.read_text(encoding="utf-8"))
    assert saved["presets"][0]["expression"] == "=TB('9999')", "同键应覆盖表达式"


def test_upsert_custom_forces_source_custom(tmp_custom: Path):
    """即便传入 source 非 custom，落库也强制标 custom（隔离来源）。"""
    e = _entry("note:Y", "R1C1")
    e.source = "seed"  # 恶意/误传
    pl.upsert_custom_presets([e])
    saved = json.loads(tmp_custom.read_text(encoding="utf-8"))
    assert saved["presets"][0]["source"] == "custom"


# ── P7: 零回归（custom 为空口径不变） ─────────────────────────────────────────
def test_empty_custom_preserves_baseline(tmp_custom: Path):
    """空 custom 时 build_preset_library 结果与无 custom 源逐字节一致。"""
    entries, stats = pl.build_preset_library()
    keys = [e.dedup_key() for e in entries]
    assert len(keys) == len(set(keys))
    assert stats["inserted"] == len(entries) > 0
    # 空 custom → 无 custom 条目
    assert all(e.source != "custom" for e in entries)
    # include_sources=False 仍仅显式源
    seed_only, _ = pl.build_preset_library(include_sources=False)
    assert all(e.source != "custom" for e in seed_only)
    assert 0 < len(seed_only) < len(entries)


# ── P4: 自定义同键覆盖通用 ────────────────────────────────────────────────────
def test_custom_overrides_seed_on_same_key(tmp_custom: Path):
    """custom 与 seed 同 (page_key, target_cell) 时结果取 custom（置最前，首个赢）。"""
    # 取一条真实 seed 条目的键
    seed = pl.load_seed_presets()
    assert seed, "需要非空 seed 作对照"
    target = seed[0]
    # 写一条同键 custom（表达式区分）
    override_expr = "=CUSTOM_OVERRIDE_MARKER()"
    pl.upsert_custom_presets(
        [
            PresetEntry(
                page_key=target.page_key,
                target_cell=target.target_cell,
                expression=override_expr,
                formula_type="auto_calc",
                refs=[],
                source="custom",
                description="override",
            )
        ]
    )
    entries, _ = pl.build_preset_library()
    matched = [
        e
        for e in entries
        if e.page_key == target.page_key and e.target_cell == target.target_cell
    ]
    assert len(matched) == 1, "去重后同键仅一条"
    assert matched[0].source == "custom", "同键应为 custom（覆盖通用）"
    assert matched[0].expression == override_expr


def test_custom_only_key_appears_in_library(tmp_custom: Path):
    """custom 独有键出现在预设库且 source=custom。"""
    pl.upsert_custom_presets([_entry("note:自定义独有节", "R7C7")])
    entries, stats = pl.build_preset_library()
    matched = [e for e in entries if e.page_key == "note:自定义独有节"]
    assert len(matched) == 1 and matched[0].source == "custom"
    assert stats.get("source:custom", 0) >= 1
