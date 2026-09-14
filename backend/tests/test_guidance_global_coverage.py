"""跨 working-paper context 的动态 guidance coverage 契约。"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from openpyxl import Workbook

from app.services.guidance_coverage_service import (
    GuidanceCoverageContext,
    build_global_guidance_coverage,
)
from app.services.guidance_inventory import (
    CANONICAL_SECTION_KEYS,
    RuntimeCustomGuidance,
    build_static_guidance_inventory,
    stable_digest,
)
from app.services.guidance_source_refs import (
    TemplateAuthoritySnapshot,
    build_template_authority_snapshot,
    file_sha256,
)


def _render(code: str, *, component_type: str = "d-form-table") -> dict:
    return {
        "sheet_code": code,
        "sheet_name": f"测试页 {code}",
        "sheet_code_reason": "explicit_code",
        "whole_workbook": False,
        "componentType": component_type,
    }


def _xlsx(path: Path, value: str = "权威编制说明") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "说明"
    worksheet["A1"] = value
    workbook.save(path)
    workbook.close()


def _fixture(
    tmp_path: Path,
    *codes: str,
    missing_codes: tuple[str, ...] = (),
):
    repo = tmp_path
    template_root = repo / "backend" / "wp_templates"
    source = template_root / "D" / "D0.xlsx"
    _xlsx(source)
    (template_root / "_index.json").write_text(
        json.dumps(
            {
                "files": [
                    {
                        "wp_code": "D0",
                        "filename": source.name,
                        "relative_path": "D/D0.xlsx",
                        "format": "xlsx",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    guidance_dir = repo / "guidance"
    guidance_dir.mkdir()
    ref = {
        "kind": "xlsx",
        "path": source.relative_to(repo).as_posix(),
        "digest": file_sha256(source),
        "sheet": "说明",
        "range": "A1",
    }
    for code in codes:
        sections = [
            {
                "key": key,
                "title": key,
                "content": f"{key} content",
                "source_refs": [] if code in missing_codes else [ref],
            }
            for key in CANONICAL_SECTION_KEYS
        ]
        (guidance_dir / f"{code}.json").write_text(
            json.dumps(
                {
                    "schema_version": 2,
                    "wp_code": code,
                    "title": code,
                    "sections": sections,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    return repo, template_root, source, build_static_guidance_inventory(guidance_dir=guidance_dir)


def _snapshot(
    repo: Path,
    template_root: Path,
    render_sheets: tuple[dict, ...],
    *,
    active_path: Path | None = None,
) -> TemplateAuthoritySnapshot:
    return build_template_authority_snapshot(
        parent_wp_code="D0",
        render_sheets=render_sheets,
        active_template_path=active_path,
        template_version="v1",
        template_origin="test",
        index_path=template_root / "_index.json",
        repo_root=repo,
        template_root=template_root,
    )


def _context(
    context_id: str,
    snapshot: TemplateAuthoritySnapshot,
    *codes: str,
    component_type: str = "d-form-table",
    custom_entries: tuple[RuntimeCustomGuidance, ...] = (),
    include_whole_workbook_context: bool = False,
) -> GuidanceCoverageContext:
    return GuidanceCoverageContext(
        context_id=context_id,
        wp_id=f"wp-{context_id}",
        project_id=f"project-{context_id}",
        parent_wp_code="D0",
        render_sheets=tuple(_render(code, component_type=component_type) for code in codes),
        custom_entries=custom_entries,
        template_authority_snapshot=snapshot,
        include_whole_workbook_context=include_whole_workbook_context,
    )


def test_global_coverage_uses_runtime_contexts_and_keeps_run_id_out_of_stable_digest(tmp_path: Path):
    now = datetime(2026, 9, 7, tzinfo=UTC)
    repo, root, _source, static = _fixture(tmp_path, "D0-1", "D0-2")
    render_a = (_render("D0-1"),)
    render_b = (_render("D0-1"), _render("D0-2"))
    contexts = [
        _context("a", _snapshot(repo, root, render_a), "D0-1"),
        _context("b", _snapshot(repo, root, render_b), "D0-1", "D0-2"),
    ]

    first = build_global_guidance_coverage(
        contexts, static_entries=static, now=now, run_id="run-a"
    )
    second = build_global_guidance_coverage(
        list(reversed(contexts)), static_entries=static, now=now, run_id="run-b"
    )

    assert first.run_id != second.run_id
    assert first.contexts_digest == second.contexts_digest
    assert first.facts_digest == second.facts_digest
    # 两个 digest 都必须是真正计算出的稳定摘要，而非常量或降级值。
    # 仅断言「两次相等」没有判别力：把 digest 改成字面量后两次仍相等，
    # 变异检验 C01 因此误判为 GREEN（守卫盲区，不是代码无问题）。
    assert len(first.contexts_digest) == 64 and len(first.facts_digest) == 64, (
        "digests must be full-length stable digests, not truncated or constant"
    )
    assert first.contexts_digest != first.facts_digest, (
        "contexts digest and facts digest must be independently computed"
    )
    assert first.counters["contexts"] == 2
    assert first.counters["required"] == 3
    assert first.counters["required_exact"] == 3
    assert first.counters["required_non_exact"] == 0
    assert first.closed is True


def test_new_render_sheet_expands_global_required_denominator(tmp_path: Path):
    now = datetime(2026, 9, 7, tzinfo=UTC)
    repo, root, _source, static = _fixture(tmp_path, "D0-1", "D0-2")
    base_render = (_render("D0-1"),)
    expanded_render = (_render("D0-1"), _render("D0-2"))
    base = build_global_guidance_coverage(
        [_context("a", _snapshot(repo, root, base_render), "D0-1")],
        static_entries=static,
        now=now,
    )
    expanded = build_global_guidance_coverage(
        [_context("a", _snapshot(repo, root, expanded_render), "D0-1", "D0-2")],
        static_entries=static,
        now=now,
    )

    assert base.counters["required"] == 1
    assert expanded.counters["required"] == 2
    assert expanded.counters["required_exact"] == 2
    assert base.facts_digest != expanded.facts_digest


def test_prior_global_entry_digest_marks_changed_source_facts_stale(tmp_path: Path):
    now = datetime(2026, 9, 7, tzinfo=UTC)
    repo, root, _source, static = _fixture(tmp_path, "D0-1")
    render = (_render("D0-1"),)
    snapshot = _snapshot(repo, root, render)
    first = build_global_guidance_coverage(
        [_context("a", snapshot, "D0-1")], static_entries=static, now=now
    )
    prior = {entry.global_entry_id: entry.entry_digest for entry in first.entries}
    changed = build_global_guidance_coverage(
        [_context("a", snapshot, "D0-1", component_type="onlyoffice-sheet")],
        static_entries=static,
        prior_entry_digests=prior,
        now=now,
    )

    required = next(entry for entry in changed.entries if entry.required)
    assert required.exact_status == "stale"
    assert required.stale_reasons == ("source_facts_changed",)
    assert changed.counters["required_exact"] == 0
    assert changed.counters["required_non_exact"] == 1
    assert changed.closed is False


def test_context_without_render_manifest_remains_a_required_observable_blocker(tmp_path: Path):
    repo, root, _source, static = _fixture(tmp_path, "D0")
    snapshot = _snapshot(repo, root, ())
    report = build_global_guidance_coverage(
        [_context("empty", snapshot)], static_entries=static
    )

    assert report.counters["required"] == 1
    assert report.counters["required_exact"] == 0
    entry = next(entry for entry in report.entries if entry.required)
    assert entry.context_kind == "template_only"
    assert entry.exact_status == "invalid"
    assert "render_config_missing" in entry.exact_blockers


def test_confirmed_custom_without_binary_authority_is_not_exact(tmp_path: Path):
    repo, root, _source, static = _fixture(
        tmp_path,
        "D0-2",
        missing_codes=("D0-2",),
    )
    render = (_render("D0-2"),)
    custom_document = {
        "status": "custom_confirmed",
        "sheet_code": "D0-2",
        "sheet_name": "测试页 D0-2",
    }
    custom = RuntimeCustomGuidance(
        sheet_code="D0-2",
        sheet_name="测试页 D0-2",
        document=custom_document,
        source_digest=stable_digest(custom_document),
        version="custom-v1",
    )
    report = build_global_guidance_coverage(
        [_context("custom", _snapshot(repo, root, render), "D0-2", custom_entries=(custom,))],
        static_entries=static,
    )

    entry = next(item for item in report.entries if item.required)
    assert entry.exact_status == "invalid"
    assert "custom_source_authority_unavailable" in entry.exact_blockers
    assert any(fact.kind == "custom_runtime" for fact in entry.source_facts)
    assert report.counters["required_exact"] == 0


def test_static_is_revalidated_per_active_template_context(tmp_path: Path):
    repo, root, canonical, static = _fixture(tmp_path, "D0-1")
    render = (_render("D0-1"),)
    changed_active = repo / "runtime" / "D0-active.xlsx"
    _xlsx(changed_active, value="已变化的活动模板")
    valid_snapshot = _snapshot(repo, root, render, active_path=canonical)
    stale_snapshot = _snapshot(repo, root, render, active_path=changed_active)

    report = build_global_guidance_coverage(
        [
            _context("valid", valid_snapshot, "D0-1"),
            _context("stale", stale_snapshot, "D0-1"),
        ],
        static_entries=static,
    )

    by_context = {
        entry.context_id: entry
        for entry in report.entries
        if entry.required and entry.context_kind == "sheet"
    }
    assert by_context["valid"].exact_status == "exact"
    assert by_context["stale"].exact_status == "stale"
    assert "static_source_refs_stale" in by_context["stale"].stale_reasons
    assert report.counters["required"] == 2
    assert report.counters["required_exact"] == 1
