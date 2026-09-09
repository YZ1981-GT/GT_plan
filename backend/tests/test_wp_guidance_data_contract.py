"""编制说明静态数据与动态清册契约。"""
from __future__ import annotations

import json
from pathlib import Path

from app.services.guidance_inventory import (
    CANONICAL_SECTION_KEYS,
    GUIDANCE_DIR,
    analyze_guidance_document,
    build_static_guidance_inventory,
    inventory_digest,
    normalize_source_refs,
    section_content,
)


def _exact_sections() -> list[dict]:
    return [
        {
            "key": key,
            "title": key,
            "content": f"{key} content",
            "source_refs": [{"kind": "xlsx", "path": "backend/wp_templates/A/test.xlsx"}],
        }
        for key in CANONICAL_SECTION_KEYS
    ]


def test_every_guidance_document_has_canonical_structure_and_observable_gaps():
    failures: list[str] = []
    count = 0
    for path in sorted(GUIDANCE_DIR.glob("*.json"), key=lambda item: item.name.lower()):
        if path.stem.startswith("_"):
            continue
        count += 1
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            assert isinstance(document, dict)
            assert document.get("schema_version") == 2
            assert document.get("wp_code") == path.stem
            assert str(document.get("title") or "").strip()

            sections = document.get("sections")
            assert isinstance(sections, list)
            keys: list[str] = []
            for section in sections:
                assert isinstance(section, dict)
                key = str(section.get("key") or "")
                assert key in CANONICAL_SECTION_KEYS
                assert key not in keys
                keys.append(key)
                assert str(section.get("title") or "").strip()
                assert section_content(section)
                assert isinstance(section.get("source_refs"), list)

            questions = document.get("recommended_questions", [])
            assert isinstance(questions, list)
            assert all(isinstance(item, str) and item.strip() for item in questions)

            unmapped = document.get("unmapped_sections", [])
            assert isinstance(unmapped, list)
            for section in unmapped:
                assert isinstance(section, dict)
                assert str(section.get("title") or "").strip()
                assert section_content(section)
                assert isinstance(section.get("source_refs"), list)
                assert isinstance(section.get("source_index"), int)

            analysis = analyze_guidance_document(document, fallback_wp_code=path.stem)
            if analysis.status == "exact":
                assert analysis.missing_sections == ()
                assert analysis.exact_blockers == ()
                assert analysis.unmapped_section_count == 0
                assert all(normalize_source_refs(section.get("source_refs")) for section in sections)
            else:
                assert analysis.exact_blockers
                assert set(analysis.missing_sections).issubset(set(CANONICAL_SECTION_KEYS))
        except (AssertionError, TypeError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"{path.name}: {exc}")

    assert count > 0
    assert failures == []


def test_guidance_directory_is_parseable_canonical_and_bundle_free():
    entries = build_static_guidance_inventory()
    assert entries, "guidance 清册不能为空"
    failures = [entry for entry in entries if entry.parse_status != "ok"]
    assert failures == []
    assert all(entry.reason != "second_schema_bundle" for entry in entries)
    assert not (GUIDANCE_DIR / "cash_flow_support.json").exists()
    assert not (GUIDANCE_DIR / "goodwill_impairment.json").exists()
    assert not (GUIDANCE_DIR / "segment_reporting.json").exists()


def test_inventory_digest_is_stable_and_all_non_exact_states_have_blockers():
    first = build_static_guidance_inventory()
    second = build_static_guidance_inventory()
    assert inventory_digest(first) == inventory_digest(second)
    assert all(entry.exact_status in {"exact", "missing"} for entry in first)
    for entry in first:
        if entry.exact_status == "exact":
            assert entry.missing_sections == ()
            assert entry.exact_blockers == ()
            assert entry.reason == "ok"
        else:
            assert entry.exact_blockers
            assert entry.reason.startswith("incomplete:")
            assert set(entry.missing_sections).issubset(set(CANONICAL_SECTION_KEYS))


def test_unmapped_is_an_observable_inventory_blocker_even_when_nine_sections_exist(
    tmp_path: Path,
):
    code = "T-UNMAPPED"
    document = {
        "schema_version": 2,
        "wp_code": code,
        "title": "未裁决段清册契约",
        "sections": _exact_sections(),
        "unmapped_sections": [
            {
                "title": "专项补充",
                "content": "尚未裁决归属。",
                "source_refs": [],
                "source_index": 9,
            }
        ],
    }
    (tmp_path / f"{code}.json").write_text(
        json.dumps(document, ensure_ascii=False), encoding="utf-8"
    )

    analysis = analyze_guidance_document(document)
    assert analysis.status == "invalid"
    assert analysis.missing_sections == ()
    assert analysis.unmapped_section_count == 1
    assert analysis.source_ref_status == "unvalidated"
    assert analysis.exact_blockers == (
        "unmapped_sections",
        "source_ref_context_missing",
    )

    entries = build_static_guidance_inventory(guidance_dir=tmp_path)
    assert len(entries) == 1
    assert entries[0].exact_status == "invalid"
    assert entries[0].missing_sections == ()
    assert entries[0].exact_blockers == (
        "unmapped_sections",
        "source_ref_context_missing",
    )
    assert entries[0].reason == "invalid:unmapped_sections,source_ref_context_missing"


def test_d0_5_is_valid_json_and_a3_8_has_explainable_status():
    d0_5 = json.loads((GUIDANCE_DIR / "D0-5.json").read_text(encoding="utf-8"))
    assert d0_5["wp_code"] == "D0-5"

    a3_8 = json.loads((GUIDANCE_DIR / "A3-8.json").read_text(encoding="utf-8"))
    assert a3_8["wp_code"] == "A3-8"
    assert "wp_codes" not in a3_8
    analysis = analyze_guidance_document(a3_8, fallback_wp_code="A3-8")
    assert analysis.wp_code == "A3-8"
    assert (analysis.status == "exact") == (not analysis.exact_blockers)


def test_normalize_source_refs_preserves_nested_docx_anchor_object():
    raw = [{
        "kind": "docx",
        "path": "backend/wp_templates/A/A1.docx",
        "anchor": {
            "type": "paragraph_text",
            "text": "编制说明",
            "match": "normalized",
        },
    }]

    normalized = normalize_source_refs(raw)

    assert normalized == tuple(raw)
    assert isinstance(normalized[0]["anchor"], dict)
