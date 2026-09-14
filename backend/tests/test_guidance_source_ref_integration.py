"""source_ref 四态贯穿 canonical、child resolution、runtime 与 coverage。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.services.guidance_coverage_service import (
    GuidanceCoverageContext,
    build_global_guidance_coverage,
)
from app.services.guidance_extractor import GuidanceExtractor
from app.services.guidance_inventory import (
    CANONICAL_SECTION_KEYS,
    analyze_guidance_document,
    build_runtime_guidance_inventory,
    build_static_guidance_inventory,
)
from app.services.guidance_source_refs import (
    build_source_ref_contexts,
    build_template_authority_snapshot,
    file_sha256,
)
from app.services.wp_guidance_service import GuidanceService


def _xlsx(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "说明"
    worksheet["A1"] = value
    workbook.save(path)
    workbook.close()


def _render() -> dict:
    return {
        "sheet_code": "D0-1",
        "sheet_name": "函证汇总 D0-1",
        "sheet_code_reason": "explicit_code",
        "whole_workbook": False,
        "componentType": "d-form-table",
    }


def _prepare_case(tmp_path: Path, state: str):
    repo = tmp_path
    template_root = repo / "backend" / "wp_templates"
    canonical = template_root / "D" / "D0.xlsx"
    other = template_root / "E" / "E0.xlsx"
    _xlsx(canonical, "D0 权威来源")
    _xlsx(other, "E0 其他模板")
    (template_root / "_index.json").write_text(
        json.dumps(
            {
                "files": [
                    {
                        "wp_code": "D0",
                        "filename": canonical.name,
                        "relative_path": "D/D0.xlsx",
                        "format": "xlsx",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    base_ref = {
        "kind": "xlsx",
        "path": canonical.relative_to(repo).as_posix(),
        "digest": file_sha256(canonical),
        "sheet": "说明",
        "range": "A1",
    }
    if state == "empty":
        refs = []
    elif state == "cross_template":
        refs = [
            {
                **base_ref,
                "path": other.relative_to(repo).as_posix(),
                "digest": file_sha256(other),
            }
        ]
    elif state == "stale":
        refs = [{**base_ref, "digest": "0" * 64}]
    else:
        refs = [base_ref]
    document = {
        "schema_version": 2,
        "wp_code": "D0-1",
        "title": "函证汇总",
        "sections": [
            {
                "key": key,
                "title": key,
                "content": f"{key} content",
                "source_refs": refs,
            }
            for key in CANONICAL_SECTION_KEYS
        ],
    }
    guidance_dir = repo / "guidance"
    guidance_dir.mkdir()
    (guidance_dir / "D0-1.json").write_text(
        json.dumps(document, ensure_ascii=False),
        encoding="utf-8",
    )
    render = (_render(),)
    snapshot = build_template_authority_snapshot(
        parent_wp_code="D0",
        render_sheets=render,
        active_template_path=canonical,
        index_path=template_root / "_index.json",
        repo_root=repo,
        template_root=template_root,
    )
    contexts = build_source_ref_contexts(snapshot, render)
    return document, guidance_dir, render, snapshot, contexts


@pytest.mark.parametrize(
    ("state", "analysis_status", "runtime_status"),
    [
        ("valid", "exact", "exact"),
        ("empty", "missing", "missing"),
        ("cross_template", "invalid", "invalid"),
        ("stale", "stale", "stale"),
    ],
)
@pytest.mark.asyncio
async def test_source_ref_four_states_reach_every_exact_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    state: str,
    analysis_status: str,
    runtime_status: str,
):
    document, guidance_dir, render, snapshot, contexts = _prepare_case(tmp_path, state)
    analysis = analyze_guidance_document(
        document,
        fallback_wp_code="D0-1",
        source_ref_context=contexts["D0-1"],
    )
    assert analysis.status == analysis_status
    assert analysis.source_ref_status == ("missing" if state == "empty" else state)

    static_entries = build_static_guidance_inventory(
        guidance_dir=guidance_dir,
        source_ref_contexts=contexts,
    )
    static = static_entries[0]
    assert static.exact_status == analysis_status
    runtime = build_runtime_guidance_inventory(
        parent_wp_code="D0",
        render_sheets=render,
        static_entries=static_entries,
    )
    runtime_entry = next(entry for entry in runtime.entries if entry.context_kind == "sheet")
    assert runtime_entry.exact_status == runtime_status

    import app.services.guidance_extractor as extractor_module

    monkeypatch.setattr(extractor_module, "GUIDANCE_DIR", guidance_dir)
    child = await GuidanceExtractor().extract_exact_static(
        "D0-1",
        validated_entry=runtime_entry,
    )
    assert (child is not None) is (state == "valid")

    response = await GuidanceService().resolve_guidance(
        parent_wp_code="D0",
        requested_sheet_code="D0-1",
        runtime_entry=runtime_entry,
        inventory_facts_digest=runtime.facts_digest,
        inventory_run_id="four-state",
    )
    assert response["resolution_status"] == runtime_status
    assert (response["resolved_wp_code"] == "D0-1") is (state == "valid")

    unvalidated_static = build_static_guidance_inventory(guidance_dir=guidance_dir)
    coverage = build_global_guidance_coverage(
        [
            GuidanceCoverageContext(
                context_id=f"context-{state}",
                wp_id="wp-1",
                project_id="project-1",
                parent_wp_code="D0",
                render_sheets=render,
                template_authority_snapshot=snapshot,
            )
        ],
        static_entries=unvalidated_static,
    )
    coverage_entry = next(entry for entry in coverage.entries if entry.required)
    assert coverage_entry.exact_status == runtime_status
    assert coverage.counters["required_exact"] == (1 if state == "valid" else 0)
