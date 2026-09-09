"""legacy guidance → canonical v2 无损迁移契约。"""
from __future__ import annotations

import json
from copy import deepcopy

from app.services.guidance_inventory import GUIDANCE_DIR
from backend.scripts.fix.migrate_guidance_canonical_schema import (
    migrate_document,
    validate_canonical_structure,
    validate_lossless,
)


def _load(code: str) -> dict:
    return json.loads((GUIDANCE_DIR / f"{code}.json").read_text(encoding="utf-8"))


def _legacy_document(code: str, sections: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "wp_code": code,
        "title": f"{code} 编制说明",
        "sections": sections,
    }


def _migration_fixture() -> dict:
    return _legacy_document(
        "T-MIGRATION",
        [
            {"title": "一、编制步骤", "content": "先核对范围，再执行程序。"},
            {"title": "WACC 公式（加权平均资本成本）", "content": "WACC = Ke × E/V"},
            {"title": "Ke 公式（CAPM 资本资产定价模型）", "content": "Ke = Rf + β × Rm"},
            {"title": "专项复核提示", "content": "保留无法稳定分类的专家正文。"},
        ],
    )


def test_duplicate_formula_sections_are_merged_without_losing_wacc_or_capm():
    before = _migration_fixture()
    after = migrate_document(before, filename_code="T-MIGRATION")

    assert validate_lossless(before, after) == []
    assert validate_canonical_structure(after, filename_code="T-MIGRATION") == []
    formulas = next(section for section in after["sections"] if section["key"] == "formulas")
    assert formulas["legacy_titles"] == [
        "WACC 公式（加权平均资本成本）",
        "Ke 公式（CAPM 资本资产定价模型）",
    ]
    assert "WACC =" in formulas["content"]
    assert "Ke =" in formulas["content"]
    assert after["migration"]["version"] == 2
    assert len(after["migration"]["canonical_body_digest"]) == 64


def test_duplicate_judgment_sections_keep_all_three_topics():
    before = _legacy_document(
        "T-JUDGMENT",
        [
            {"title": "二、三级重要性计算逻辑", "content": "PM 应低于整体重要性。"},
            {"title": "三、特定类别重要性（如适用）", "content": "识别特定类别重要性。"},
            {"title": "四、审计过程中修订重要性", "content": "变化时修订重要性。"},
        ],
    )
    after = migrate_document(before, filename_code="T-JUDGMENT")

    assert validate_lossless(before, after) == []
    judgments = next(section for section in after["sections"] if section["key"] == "judgments")
    assert judgments["legacy_titles"] == [
        "二、三级重要性计算逻辑",
        "三、特定类别重要性（如适用）",
        "四、审计过程中修订重要性",
    ]
    assert "PM" in judgments["content"]
    assert "特定类别重要性" in judgments["content"]
    assert "修订重要性" in judgments["content"]


def test_unrecognized_sections_are_preserved_as_lineage_leaves():
    before = _migration_fixture()
    after = migrate_document(before, filename_code="T-MIGRATION")

    assert validate_lossless(before, after) == []
    assert after["unmapped_sections"] == [
        {
            "title": "专项复核提示",
            "content": "保留无法稳定分类的专家正文。",
            "source_refs": [],
            "source_index": 3,
            "classification": "unmapped",
        }
    ]
    assert after["migration"]["legacy_section_count"] == 4
    assert after["migration"]["unmapped_section_count"] == 1


def test_v2_metadata_upgrade_is_idempotent_and_does_not_rewrite_business_body():
    canonical = migrate_document(_migration_fixture(), filename_code="T-MIGRATION")
    version_one = deepcopy(canonical)
    version_one["migration"]["version"] = 1
    version_one["migration"].pop("canonical_body_digest")
    business_body = {key: value for key, value in version_one.items() if key != "migration"}

    upgraded = migrate_document(version_one, filename_code="T-MIGRATION")

    assert {key: value for key, value in upgraded.items() if key != "migration"} == business_body
    assert validate_lossless(version_one, upgraded) == []
    assert upgraded["migration"]["version"] == 2
    assert migrate_document(upgraded, filename_code="T-MIGRATION") == upgraded


def test_v2_fingerprint_rejects_body_lineage_and_digest_mutations():
    canonical = migrate_document(_migration_fixture(), filename_code="T-MIGRATION")
    formulas_index = next(
        index for index, section in enumerate(canonical["sections"])
        if section["key"] == "formulas"
    )
    steps_index = next(
        index for index, section in enumerate(canonical["sections"])
        if section["key"] == "steps"
    )

    mutations: list[tuple[str, dict]] = []
    singleton = deepcopy(canonical)
    singleton["sections"][steps_index]["content"] += "（被改写）"
    mutations.append(("singleton", singleton))

    merged = deepcopy(canonical)
    merged["sections"][formulas_index]["content"] += "（被改写）"
    mutations.append(("merged", merged))

    lineage = deepcopy(canonical)
    lineage["sections"][formulas_index]["legacy_subsections"][0]["content"] += "（被改写）"
    mutations.append(("lineage", lineage))

    unmapped = deepcopy(canonical)
    unmapped["unmapped_sections"][0]["content"] += "（被改写）"
    mutations.append(("unmapped", unmapped))

    digest = deepcopy(canonical)
    digest["migration"]["canonical_body_digest"] = "0" * 64
    mutations.append(("digest", digest))

    for label, mutated in mutations:
        after = migrate_document(mutated, filename_code="T-MIGRATION")
        errors = validate_lossless(mutated, after)
        assert "canonical_body_digest 不一致" in errors, (label, errors)


def test_every_business_document_has_a_lossless_canonical_projection():
    failures: list[str] = []
    count = 0
    for path in sorted(GUIDANCE_DIR.glob("*.json")):
        if path.stem.startswith("_"):
            continue
        count += 1
        before = json.loads(path.read_text(encoding="utf-8"))
        try:
            after = migrate_document(before, filename_code=path.stem)
            errors = validate_lossless(before, after)
            errors.extend(validate_canonical_structure(after, filename_code=path.stem))
            failures.extend(f"{path.name}: {error}" for error in errors)
        except Exception as exc:  # noqa: BLE001 — 报出完整失败文件
            failures.append(f"{path.name}: {exc}")

    assert count > 0
    assert failures == []


def test_invalid_recommended_questions_are_rejected():
    after = migrate_document(_load("K1"), filename_code="K1")
    after["recommended_questions"] = ["", 42]
    errors = validate_canonical_structure(after, filename_code="K1")
    assert "recommended_questions 必须是非空字符串数组" in errors
