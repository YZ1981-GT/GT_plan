"""Contract tests for L/M/N formula preset entries (Property 7 + 8).

Verifies all 41 lmn_four_table_extraction entries in formula_presets_seed.json:
- Property 7: page_key format, expression only TB/SUM_TB, category=auto_calc, refs non-empty
- Property 8: shared codes (4002 M3/M4, 4104 M6/M8) don't create target_cell conflicts
"""

import json
import re
from pathlib import Path

import pytest

SEED_FILE = Path(__file__).parent.parent / "data" / "formula_presets" / "formula_presets_seed.json"


def _load_lmn_presets():
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    return [p for p in data["presets"] if p.get("source") == "lmn_four_table_extraction"]


class TestLmnPresetFormat:
    """Property 7: format validity."""

    def test_entries_exist(self):
        presets = _load_lmn_presets()
        assert len(presets) >= 36, f"Expected >=36 LMN presets, got {len(presets)}"

    @pytest.mark.parametrize("preset", _load_lmn_presets(), ids=lambda p: p["target_cell"])
    def test_page_key_format(self, preset):
        assert re.match(r"^workpaper:[LMN]\d+-1$", preset["page_key"]), f"Bad page_key: {preset['page_key']}"

    @pytest.mark.parametrize("preset", _load_lmn_presets(), ids=lambda p: p["target_cell"])
    def test_expression_only_tb_functions(self, preset):
        expr = preset["expression"]
        # Remove TB(...) and SUM_TB(...) calls, remaining should have no unknown function calls
        cleaned = re.sub(r"(SUM_)?TB\([^)]+\)", "", expr)
        # Only operators and whitespace should remain
        assert not re.search(r"[A-Z_]+\(", cleaned), f"Unsupported function in: {expr}"

    @pytest.mark.parametrize("preset", _load_lmn_presets(), ids=lambda p: p["target_cell"])
    def test_formula_type_auto_calc(self, preset):
        assert preset["formula_type"] == "auto_calc"

    @pytest.mark.parametrize("preset", _load_lmn_presets(), ids=lambda p: p["target_cell"])
    def test_refs_non_empty(self, preset):
        assert len(preset["refs"]) > 0


class TestLmnSharedCodeNoConflict:
    """Property 8: shared codes (4002/4104) don't create target_cell conflicts."""

    def test_m3_m4_different_targets(self):
        presets = _load_lmn_presets()
        m3_targets = {p["target_cell"] for p in presets if p["page_key"] == "workpaper:M3-1"}
        m4_targets = {p["target_cell"] for p in presets if p["page_key"] == "workpaper:M4-1"}
        assert m3_targets.isdisjoint(m4_targets), f"M3/M4 conflict: {m3_targets & m4_targets}"

    def test_m6_m8_different_targets(self):
        presets = _load_lmn_presets()
        m6_targets = {p["target_cell"] for p in presets if p["page_key"] == "workpaper:M6-1"}
        m8_targets = {p["target_cell"] for p in presets if p["page_key"] == "workpaper:M8-1"}
        assert m6_targets.isdisjoint(m8_targets), f"M6/M8 conflict: {m6_targets & m8_targets}"
