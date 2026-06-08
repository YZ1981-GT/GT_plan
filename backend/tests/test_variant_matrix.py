"""note_template_variant_matrix.json ↔ section_code_index.json 一致性校验.

Spec:   .kiro/specs/audit-report-template-integration/ task 0.6.2.1 / 0.6.2.2
Source: scripts/build_variant_matrix.py / scripts/normalize_note_bindings.py

断言：
- 矩阵每个账户每个变体的 code 必存在于 section_code_index 对应变体的「项目注释」章。
- legacy_aliases 与 index 一致。
- 关键账户（货币资金 / 固定资产）码与 index 对齐（防 POC 错码 五、12 回潮）。
- bindings 国企 八、N 已标注 legacy_aliases，且 loader 仍能用 五、N 别名解析。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = REPO_ROOT / "backend" / "data"
INDEX_PATH = DATA / "audit_report_templates" / "section_code_index.json"
MATRIX_PATH = DATA / "note_template_variant_matrix.json"

VARIANTS = ("soe_standalone", "soe_consolidated", "listed_standalone", "listed_consolidated")
PROJECT_CHAPTER = {
    "soe_standalone": "八",
    "soe_consolidated": "八",
    "listed_standalone": "五",
    "listed_consolidated": "五",
}


def _chapter(code: str) -> str:
    return code.split("、")[0] if "、" in code else code


@pytest.fixture(scope="module")
def index() -> dict:
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def matrix() -> dict:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def index_project_codes(index: dict) -> dict[str, set[str]]:
    """每变体「项目注释」章内的 section_code 集合."""
    out: dict[str, set[str]] = {}
    for vk in VARIANTS:
        chap = PROJECT_CHAPTER[vk]
        codes = {
            s["section_code"]
            for s in index["variants"][vk]["sections"]
            if _chapter(s["section_code"]) == chap
        }
        out[vk] = codes
    return out


@pytest.fixture(scope="module")
def index_alias_by_code(index: dict) -> dict[str, dict[str, list[str]]]:
    """每变体 section_code → legacy_aliases."""
    out: dict[str, dict[str, list[str]]] = {}
    for vk in VARIANTS:
        out[vk] = {
            s["section_code"]: (s.get("legacy_aliases") or [])
            for s in index["variants"][vk]["sections"]
        }
    return out


def test_matrix_non_empty(matrix: dict) -> None:
    assert matrix.get("accounts"), "matrix accounts empty"


def test_every_matrix_code_exists_in_index(
    matrix: dict, index_project_codes: dict[str, set[str]]
) -> None:
    """每个矩阵变体 code 必存在于 index 对应变体的项目注释章."""
    bad: list[tuple] = []
    for acct in matrix["accounts"]:
        for vk in VARIANTS:
            code = acct["variants"].get(vk)
            if code is None:
                continue
            if code not in index_project_codes[vk]:
                bad.append((acct["account_key"], vk, code))
    assert not bad, f"matrix codes not in index project-note chapter: {bad[:10]}"


def test_account_keys_unique(matrix: dict) -> None:
    keys = [a["account_key"] for a in matrix["accounts"]]
    assert len(keys) == len(set(keys)), "duplicate account_key in matrix"


def test_legacy_aliases_match_index(
    matrix: dict, index_alias_by_code: dict[str, dict[str, list[str]]]
) -> None:
    """矩阵 legacy_aliases 必与 index 对应节一致."""
    bad: list[tuple] = []
    for acct in matrix["accounts"]:
        for vk, aliases in acct.get("legacy_aliases", {}).items():
            code = acct["variants"].get(vk)
            idx_aliases = index_alias_by_code[vk].get(code, [])
            if sorted(aliases) != sorted(idx_aliases):
                bad.append((acct["account_key"], vk, aliases, idx_aliases))
    assert not bad, f"legacy_aliases mismatch with index: {bad[:10]}"


def test_monetary_funds_codes(matrix: dict) -> None:
    """货币资金：soe 八、1 / listed 五、1 / soe legacy 五、1."""
    acct = next(a for a in matrix["accounts"] if a["section_title"] == "货币资金")
    assert acct["variants"]["soe_standalone"] == "八、1"
    assert acct["variants"]["listed_standalone"] == "五、1"
    assert acct["legacy_aliases"].get("soe_standalone") == ["五、1"]


def test_fixed_assets_codes_match_index_not_poc(matrix: dict) -> None:
    """固定资产：必为 index 真实码 八、22 / 五、22（非 POC 错码 五、12）."""
    acct = next(a for a in matrix["accounts"] if a["section_title"] == "固定资产")
    assert acct["variants"]["soe_standalone"] == "八、22"
    assert acct["variants"]["listed_standalone"] == "五、22"
    assert acct["variants"]["soe_standalone"] != "八、12"
    assert acct["variants"]["listed_standalone"] != "五、12"


def test_bindings_soe_legacy_alias_annotated() -> None:
    """bindings: 国企 canonical 八、1/八、2 已追加 legacy_aliases（镜像 index）."""
    try:
        from app.services import note_template_bindings_loader as loader
    except ModuleNotFoundError:
        from backend.app.services import note_template_bindings_loader as loader

    loader.reload()
    b1 = loader.get_binding_for_section("八、1")
    assert b1 is not None, "八、1 binding missing"
    assert b1.get("legacy_aliases") == ["五、1"], b1.get("legacy_aliases")

    b2 = loader.get_binding_for_section("八、2")
    assert b2 is not None, "八、2 binding missing"
    assert b2.get("legacy_aliases") == ["五、2"], b2.get("legacy_aliases")


def test_catalog_resolves_soe_legacy_to_canonical() -> None:
    """catalog: 国企历史 五、N 归一到 八、N（loader 查表时所依赖的规则）."""
    try:
        from app.services.note_section_catalog import resolve_binding_key
    except ModuleNotFoundError:
        from backend.app.services.note_section_catalog import resolve_binding_key

    # 八、3 衍生金融资产 不在 bindings，但归一规则本身必须把 五、3 → 八、3
    assert resolve_binding_key("五、3", template_type="soe") == "八、3"
    assert resolve_binding_key("五、1", template_type="soe") == "八、1"
