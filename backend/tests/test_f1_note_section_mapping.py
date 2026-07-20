"""F1 附注章节映射与 variant matrix 一致性."""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = REPO_ROOT / "backend" / "data"


def _load_json(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _matrix_listed_code(account_key: str) -> str | None:
    matrix = _load_json("note_template_variant_matrix.json")
    for acct in matrix["accounts"]:
        if acct["account_key"] == account_key:
            return acct["variants"].get("listed_standalone")
    return None


def _wp_note_section(wp_code: str) -> str | None:
    mapping = _load_json("wp_account_mapping.json")
    for pkg in mapping["mappings"]:
        if pkg.get("wp_code") == wp_code:
            return pkg.get("note_section")
    return None


def _rule_section_for_account(account_code: str, wp_code: str) -> str | None:
    rules = _load_json("note_wp_mapping_rules.json")
    for item in rules["mappings"]:
        codes = item.get("account_codes") or []
        wp_codes = item.get("wp_codes") or []
        if account_code in codes and wp_code in wp_codes:
            return item.get("note_section")
    return None


def test_f1_prepayment_note_section_aligned_with_matrix():
    """F1 预付款项附注章节应与 variant matrix 上市口径一致（五、7）."""
    expected = _matrix_listed_code("yu_fu_kuan_xiang")
    assert expected == "五、7"
    assert _wp_note_section("F1") == expected
    assert _rule_section_for_account("1123", "F1-1") == expected


def test_f2_inventory_note_section_aligned_with_matrix():
    """F2 存货附注章节应与 variant matrix 上市口径一致（五、9）."""
    expected = _matrix_listed_code("cun_huo")
    assert expected == "五、9"
    assert _wp_note_section("F2") == expected
    assert _rule_section_for_account("1401", "F2-1") == expected
