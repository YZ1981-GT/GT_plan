"""Phase 8 派生生成器：截断 marker 稳定回连、投资收益 canonical account 合并。"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_section_index_recovers_truncated_marker_by_stable_section_id(tmp_path, monkeypatch):
    mod = _load("_phase8_section_index", "scripts/build_section_code_index.py")
    data = tmp_path / "data"
    notes = data / "audit_report_templates" / "disclosure_notes"
    notes.mkdir(parents=True)
    (notes / "soe_standalone.docx").write_bytes(b"stub")
    seed = {
        "sections": [{
            "section_number": "八、投资收益完整标题", "section_id": "stable-investment-income",
            "section_title": "投资收益", "content_type": "mixed",
        }]
    }
    (data / "seed.json").write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")
    out = data / "audit_report_templates" / "section_code_index.json"
    out.write_text(json.dumps({"variants": {"soe_standalone": {"sections": [{
        "section_code": "八、投资收益截断", "section_id": "stable-investment-income",
        "section_title": "投资收益【旧提示】",
    }]}}}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(mod, "DATA", data)
    monkeypatch.setattr(mod, "NOTES_DIR", notes)
    monkeypatch.setattr(mod, "OUT_PATH", out)
    monkeypatch.setattr(mod, "VARIANT_SEED", {"soe_standalone": ("seed.json", "soe")})
    monkeypatch.setattr(mod, "scan_section_markers", lambda _path: ["八、投资收益截断"])

    payload = mod.build_variant_index("soe_standalone")
    assert payload["_meta"]["missing_seed"] == []
    assert payload["_meta"]["recovered_by_section_id"] == ["八、投资收益截断"]
    row = payload["sections"][0]
    assert row["section_code"] == "八、投资收益截断"
    assert row["section_id"] == "stable-investment-income"
    assert row["section_title"] == "投资收益"


def _investment_index() -> dict:
    variants = {}
    for variant, code, sid in (
        ("soe_standalone", "八、70", "long-tou-zi-shou-yi-xia-biao-zhong-bu-shi-yong-d"),
        ("soe_consolidated", "八、70", "long-tou-zi-shou-yi-xia-biao-zhong-bu-shi-yong-d"),
        ("listed_standalone", "五、69", "short-tou-zi-shou-yi"),
        ("listed_consolidated", "五、69", "short-tou-zi-shou-yi"),
    ):
        variants[variant] = {"sections": [{
            "section_code": code,
            "section_id": f"chapter-x-xiang-mu-zhu-shi-{sid.split('-', 1)[1]}",
            "section_title": "投资收益",
            "legacy_aliases": [],
        }]}
    return {"variants": variants}


def test_matrix_merges_old_prompt_slug_into_stable_investment_key():
    mod = _load("_phase8_variant_matrix", "scripts/build_variant_matrix.py")
    old = {"accounts": [
        {"account_key": "tou_zi_shou_yi_xia_biao_zhong_bu_shi_yong_d", "variants": {}, "legacy_aliases": {}},
        {"account_key": "tou_zi_shou_yi", "variants": {}, "legacy_aliases": {},
         "parent_company_sections": {"listed": "十六、投资收益（注：以", "soe": "十二、投资收益"}},
    ]}
    fresh = mod.build_matrix(_investment_index())
    fresh = mod.carry_over_existing_variants(fresh, old)
    result = mod.carry_over_additive_fields(fresh, old)
    mod.validate_matrix(result)
    assert len(result["accounts"]) == 1
    row = result["accounts"][0]
    assert row["account_key"] == "tou_zi_shou_yi"
    assert row["variants"] == {
        "soe_standalone": "八、70", "soe_consolidated": "八、70",
        "listed_standalone": "五、69", "listed_consolidated": "五、69",
    }
    assert row["parent_company_sections"] == old["accounts"][1]["parent_company_sections"]


def test_matrix_refuses_conflicting_additive_fields_after_canonicalization():
    mod = _load("_phase8_variant_matrix_conflict", "scripts/build_variant_matrix.py")
    fresh = mod.build_matrix(_investment_index())
    old = {"accounts": [
        {"account_key": "tou_zi_shou_yi", "parent_company_sections": {"listed": "A"}},
        {"account_key": "tou_zi_shou_yi_xia_biao_zhong_bu_shi_yong_d",
         "parent_company_sections": {"listed": "B"}},
    ]}
    with pytest.raises(ValueError, match="additive"):
        mod.carry_over_additive_fields(fresh, old)


def test_section_index_prefix_fallback_requires_unique_match():
    mod = _load("_phase8_section_prefix", "scripts/build_section_code_index.py")
    one = {"十二、现金流量表补充资料": {"section_id": "new"}}
    assert mod.resolve_marker_seed("十二、现金流量表补充资", one, {}, {}) == (one[next(iter(one))], True)
    ambiguous = {**one, "十二、现金流量表补充资料续": {"section_id": "other"}}
    assert mod.resolve_marker_seed("十二、现金流量表补充资", ambiguous, {}, {}) == (None, False)


def test_matrix_preserves_valid_non_null_slot_missing_from_poc_index():
    mod = _load("_phase8_variant_carry", "scripts/build_variant_matrix.py")
    fresh = {"accounts": [{
        "account_key": "suo_de_shui_fei_yong", "section_title": "所得税费用",
        "variants": {v: ("八、78" if v.startswith("soe") else None) for v in mod.VARIANT_ORDER},
        "legacy_aliases": {},
    }]}
    old = {"accounts": [{
        "account_key": "suo_de_shui_fei_yong",
        "variants": {
            "soe_standalone": "八、78", "soe_consolidated": "八、78",
            "listed_standalone": "五、81", "listed_consolidated": "五、81",
        },
    }]}
    out = mod.carry_over_existing_variants(fresh, old)
    assert out["accounts"][0]["variants"]["listed_standalone"] == "五、81"


def test_matrix_refuses_conflicting_existing_and_generated_variant():
    mod = _load("_phase8_variant_value_conflict", "scripts/build_variant_matrix.py")
    fresh = {"accounts": [{
        "account_key": "x", "variants": {v: ("新码" if v == "soe_standalone" else None) for v in mod.VARIANT_ORDER},
    }]}
    old = {"accounts": [{"account_key": "x", "variants": {"soe_standalone": "旧码"}}]}
    with pytest.raises(ValueError, match="新旧值冲突"):
        mod.carry_over_existing_variants(fresh, old)


def test_committed_section_index_is_exact_generator_output():
    """Word marker 仍用旧截断码时，落盘 index 必须由 stable section_id/唯一前缀回连当前种子。"""
    mod = _load("_phase8_section_index_committed", "scripts/build_section_code_index.py")
    committed = json.loads((ROOT / "data" / "audit_report_templates" / "section_code_index.json").read_text(encoding="utf-8"))
    recovered = 0
    for variant in mod.VARIANT_SEED:
        payload = mod.build_variant_index(variant)
        meta = payload.pop("_meta")
        assert meta["missing_seed"] == [], (variant, meta["missing_seed"])
        recovered += len(meta["recovered_by_section_id"])
        assert payload == committed["variants"][variant]
    assert recovered > 0, "测试样本不再经过旧 marker→当前种子回连，稳定身份回退会空转"


def test_committed_matrix_is_exact_canonical_generator_output():
    mod = _load("_phase8_variant_matrix_committed", "scripts/build_variant_matrix.py")
    committed = json.loads((ROOT / "data" / "note_template_variant_matrix.json").read_text(encoding="utf-8"))
    generated = mod.build_matrix(mod.load_index())
    generated = mod.carry_over_existing_variants(generated, committed)
    generated = mod.carry_over_additive_fields(generated, committed)
    mod.validate_matrix(generated)
    assert generated == committed
