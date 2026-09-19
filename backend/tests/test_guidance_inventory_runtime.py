"""动态 guidance inventory 的运行时事实、membership 与 stale 契约。"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.guidance_inventory import (
    CANONICAL_SECTION_KEYS,
    GuidanceInventoryEntry,
    RuntimeGuidanceExemption,
    build_runtime_guidance_inventory,
    build_static_guidance_inventory,
    find_runtime_inventory_entry,
    infer_section_key,
    load_runtime_exemptions,
    normalize_runtime_custom_guidance,
    resolve_render_sheet_context,
)


def _render_sheet(
    code: str | None,
    name: str,
    *,
    component_type: str = "d-form-table",
    reason: str | None = None,
) -> dict:
    return {
        "sheet_code": code,
        "sheet_name": name,
        "sheet_code_reason": reason or ("explicit_code" if code else "no_canonical_code"),
        "whole_workbook": False,
        "componentType": component_type,
    }


def _static_entry(code: str, *, status: str = "exact", digest: str = "a" * 64) -> GuidanceInventoryEntry:
    return GuidanceInventoryEntry(
        wp_code=code,
        path=f"/guidance/{code}.json",
        parse_status="ok",
        source_digest=digest,
        exact_status=status,  # type: ignore[arg-type]
        missing_sections=() if status == "exact" else CANONICAL_SECTION_KEYS,
        reason="ok",
        source_ref_status="valid",
        source_ref_facts_digest="f" * 64,
    )


def _canonical_document(*, code: str, sheet_name: str) -> dict:
    return {
        "schema_version": 2,
        "wp_code": code,
        "sheet_code": code,
        "sheet_name": sheet_name,
        "status": "custom_confirmed",
        "version": "custom-v1",
        "sections": [
            {
                "key": key,
                "title": key,
                "content": f"{key} content",
                "source_refs": [{"kind": "custom", "path": f"confirmed/{code}/{key}"}],
            }
            for key in CANONICAL_SECTION_KEYS
        ],
    }


def _valid_exemption(
    *,
    target_code: str | None = None,
    kind: str = "inheritance",
    review_after: datetime,
) -> RuntimeGuidanceExemption:
    return RuntimeGuidanceExemption(
        kind=kind,  # type: ignore[arg-type]
        target_sheet_code=target_code,
        target_sheet_name=None,
        inherits_from="D0" if kind == "inheritance" else "D0",
        reason_code="shared_methodology",
        basis_refs=({"kind": "xlsx", "path": "D0.xlsx", "sheet": "D0"},),
        approved_by="methodology-admin",
        approved_at="2026-09-01T00:00:00+00:00",
        review_after=review_after.isoformat(),
    )


def test_inventory_digest_is_stable_while_run_metadata_changes():
    now = datetime(2026, 9, 7, tzinfo=UTC)
    kwargs = {
        "parent_wp_code": "D0",
        "render_sheets": [_render_sheet("D0-1", "函证汇总 D0-1")],
        "static_entries": [_static_entry("D0-1")],
        "include_whole_workbook_context": False,
        "now": now,
    }

    first = build_runtime_guidance_inventory(**kwargs, run_id="run-a")
    second = build_runtime_guidance_inventory(**kwargs, run_id="run-b")

    assert first.run_id != second.run_id
    assert first.facts_digest == second.facts_digest
    assert first.entries[0].entry_id == second.entries[0].entry_id
    assert first.entries[0].entry_digest == second.entries[0].entry_digest
    assert first.counters == {"exact": 1, "required": 1, "required_exact": 1}


def test_new_render_sheet_expands_required_denominator_without_static_authorization():
    base = build_runtime_guidance_inventory(
        parent_wp_code="D0",
        render_sheets=[_render_sheet("D0-1", "函证汇总 D0-1")],
        static_entries=[_static_entry("D0-1"), _static_entry("D0-9")],
        include_whole_workbook_context=False,
    )
    expanded = build_runtime_guidance_inventory(
        parent_wp_code="D0",
        render_sheets=[
            _render_sheet("D0-1", "函证汇总 D0-1"),
            _render_sheet("D0-2", "函证明细 D0-2"),
        ],
        static_entries=[_static_entry("D0-1"), _static_entry("D0-9")],
        include_whole_workbook_context=False,
    )

    assert base.counters["required"] == 1
    assert expanded.counters["required"] == 2
    orphan = next(entry for entry in expanded.entries if entry.sheet_code == "D0-9")
    assert orphan.context_kind == "guidance_only"
    assert orphan.required is False
    assert orphan.exact_status == "stale"

    with pytest.raises(ValueError, match="render-config 可达清册"):
        resolve_render_sheet_context(
            parent_wp_code="D0",
            render_sheets=[_render_sheet("D0-1", "函证汇总 D0-1")],
            requested_sheet_code="D0-9",
            requested_sheet_name=None,
        )


def test_render_membership_resolves_virtual_and_fails_closed_on_ambiguous_identity():
    render_sheets = [
        _render_sheet("D0-1", "HTML 虚拟页一 D0-1"),
        _render_sheet("D0-1", "HTML 虚拟页二 D0-1"),
    ]

    with pytest.raises(ValueError, match="identity 不唯一"):
        resolve_render_sheet_context(
            parent_wp_code="D0",
            render_sheets=render_sheets,
            requested_sheet_code="D0-1",
            requested_sheet_name=None,
        )

    code, reason, fact = resolve_render_sheet_context(
        parent_wp_code="D0",
        render_sheets=render_sheets,
        requested_sheet_code="D0-1",
        requested_sheet_name="HTML 虚拟页二 D0-1",
    )
    assert code == "D0-1"
    assert reason == "explicit_code"
    assert fact is not None and fact.sheet_name == "HTML 虚拟页二 D0-1"

    with pytest.raises(ValueError, match="不一致"):
        resolve_render_sheet_context(
            parent_wp_code="D0",
            render_sheets=render_sheets,
            requested_sheet_code="D0-2",
            requested_sheet_name="HTML 虚拟页二 D0-1",
        )


def test_confirmed_custom_document_is_observable_but_not_exact_without_authority():
    confirmed = _canonical_document(code="D0-2", sheet_name="函证明细 D0-2")
    confirmed_with_unmapped = {
        **confirmed,
        "sheet_code": "D0-4",
        "sheet_name": "存在未裁决段 D0-4",
        "unmapped_sections": [
            {"title": "专项补充", "content": "尚未裁决归属。", "source_refs": []}
        ],
    }
    raw_batch = {
        "wp-1:confirmed": {"document": confirmed},
        "wp-1:draft": {"document": {**confirmed, "status": "draft", "sheet_code": "D0-3"}},
        "wp-1:unmapped": {"document": confirmed_with_unmapped},
        "other:confirmed": {"document": confirmed},
    }
    custom = normalize_runtime_custom_guidance(raw_batch, wp_id="wp-1")
    assert len(custom) == 1

    inventory = build_runtime_guidance_inventory(
        parent_wp_code="D0",
        render_sheets=[_render_sheet("D0-2", "函证明细 D0-2")],
        static_entries=(),
        custom_entries=custom,
        include_whole_workbook_context=False,
    )
    entry = find_runtime_inventory_entry(
        inventory,
        sheet_code="D0-2",
        sheet_name="函证明细 D0-2",
    )
    assert entry is not None
    assert entry.exact_status == "invalid"
    assert "custom_source_authority_unavailable" in entry.exact_blockers
    assert any(fact.kind == "custom_runtime" for fact in entry.source_facts)


def test_static_unmapped_blocker_reaches_runtime_inventory_without_fake_missing_key():
    static = GuidanceInventoryEntry(
        wp_code="D0-2",
        path="/guidance/D0-2.json",
        parse_status="ok",
        source_digest="b" * 64,
        exact_status="missing",
        missing_sections=(),
        reason="incomplete:unmapped_sections",
        exact_blockers=("unmapped_sections",),
        source_ref_status="valid",
        source_ref_facts_digest="e" * 64,
    )
    inventory = build_runtime_guidance_inventory(
        parent_wp_code="D0",
        render_sheets=[_render_sheet("D0-2", "函证明细 D0-2")],
        static_entries=[static],
        include_whole_workbook_context=False,
    )

    entry = inventory.entries[0]
    assert entry.exact_status == "missing"
    assert entry.missing_sections == ()
    assert entry.exact_blockers == ("unmapped_sections",)
    assert entry.version_facts()["exact_blockers"] == ["unmapped_sections"]


def test_missing_or_expired_inheritance_cannot_shrink_required_denominator():
    now = datetime(2026, 9, 7, tzinfo=UTC)
    missing_source = _valid_exemption(
        target_code="D0-2",
        review_after=now + timedelta(days=30),
    )
    missing_source = RuntimeGuidanceExemption(
        **{**missing_source.__dict__, "inherits_from": None}
    )
    expired = _valid_exemption(
        target_code="D0-3",
        review_after=now - timedelta(seconds=1),
    )
    inventory = build_runtime_guidance_inventory(
        parent_wp_code="D0",
        render_sheets=[
            _render_sheet("D0-2", "函证明细 D0-2"),
            _render_sheet("D0-3", "替代程序 D0-3"),
        ],
        static_entries=(),
        exemptions=[missing_source, expired],
        include_whole_workbook_context=False,
        now=now,
    )

    by_code = {entry.sheet_code: entry for entry in inventory.entries if entry.context_kind == "sheet"}
    assert by_code["D0-2"].required is True
    assert by_code["D0-2"].exact_status == "stale"
    assert "exemption_missing_inherits_from" in by_code["D0-2"].stale_reasons
    assert by_code["D0-3"].required is True
    assert by_code["D0-3"].exact_status == "stale"
    assert "exemption_expired" in by_code["D0-3"].stale_reasons


def test_valid_inheritance_is_explicit_non_exact_and_versions_resolution_policy():
    now = datetime(2026, 9, 7, tzinfo=UTC)
    exemption = _valid_exemption(
        target_code="D0-2",
        review_after=now + timedelta(days=30),
    )
    inventory = build_runtime_guidance_inventory(
        parent_wp_code="D0",
        render_sheets=[_render_sheet("D0-2", "函证明细 D0-2")],
        static_entries=[_static_entry("D0")],
        exemptions=[exemption],
        include_whole_workbook_context=False,
        now=now,
    )
    entry = inventory.entries[0]
    assert entry.required is False
    assert entry.exact_status == "inherited"
    assert any(fact.kind == "resolution_policy" for fact in entry.source_facts)
    assert inventory.counters["required"] == 0
    assert inventory.counters["required_exact"] == 0


def test_whole_workbook_context_is_created_only_when_explicitly_requested():
    now = datetime(2026, 9, 7, tzinfo=UTC)
    ordinary = build_runtime_guidance_inventory(
        parent_wp_code="D0",
        render_sheets=[_render_sheet("D0-1", "函证汇总 D0-1")],
        static_entries=[_static_entry("D0-1")],
    )
    assert all(entry.context_kind != "whole_workbook" for entry in ordinary.entries)

    with_whole = build_runtime_guidance_inventory(
        parent_wp_code="D0",
        render_sheets=[_render_sheet("D0-1", "函证汇总 D0-1")],
        static_entries=[_static_entry("D0-1")],
        exemptions=[_valid_exemption(kind="whole_workbook", review_after=now + timedelta(days=30))],
        include_whole_workbook_context=True,
        now=now,
    )
    whole = find_runtime_inventory_entry(
        with_whole,
        sheet_code=None,
        sheet_name=None,
        whole_workbook=True,
    )
    assert whole is not None
    assert whole.context_kind == "whole_workbook"
    assert whole.exact_status == "inherited"


def test_prior_entry_digest_marks_render_source_change_stale_without_changing_entry_id():
    now = datetime(2026, 9, 7, tzinfo=UTC)
    first = build_runtime_guidance_inventory(
        parent_wp_code="D0",
        render_sheets=[_render_sheet("D0-1", "函证汇总 D0-1", component_type="d-form-table")],
        static_entries=[_static_entry("D0-1")],
        include_whole_workbook_context=False,
        now=now,
    )
    old = first.entries[0]
    changed = build_runtime_guidance_inventory(
        parent_wp_code="D0",
        render_sheets=[_render_sheet("D0-1", "函证汇总 D0-1", component_type="onlyoffice")],
        static_entries=[_static_entry("D0-1")],
        prior_entry_digests={old.entry_id: old.entry_digest},
        include_whole_workbook_context=False,
        now=now,
    )
    current = changed.entries[0]

    assert current.entry_id == old.entry_id
    assert current.entry_digest != old.entry_digest
    assert current.exact_status == "stale"
    assert current.stale_reasons == ("source_facts_changed",)


def test_malformed_schema_and_exemption_collection_are_controlled_invalid_inputs(tmp_path):
    guidance_dir = tmp_path / "guidance"
    guidance_dir.mkdir()
    (guidance_dir / "D0.json").write_text(
        '{"schema_version":"bad","wp_code":"D0","sections":[]}',
        encoding="utf-8",
    )
    entries = build_static_guidance_inventory(guidance_dir=guidance_dir)
    assert len(entries) == 1
    assert entries[0].exact_status == "invalid"
    assert entries[0].reason == "invalid_schema_version"

    (guidance_dir / "D0.json").write_text(
        '{"schema_version":2,"wp_code":"D0","sections":[],"resolution_policy":{"inheritance":42}}',
        encoding="utf-8",
    )
    assert load_runtime_exemptions("D0", guidance_dir=guidance_dir) == ()


def test_duplicate_custom_identity_fails_closed():
    first = _canonical_document(code="D0-2", sheet_name="函证明细 D0-2")
    second = {**first, "version": "custom-v2"}
    custom = normalize_runtime_custom_guidance(
        {
            "wp-1:first": {"document": first},
            "wp-1:second": {"document": second},
        },
        wp_id="wp-1",
    )

    with pytest.raises(ValueError, match="custom guidance identity 不唯一"):
        build_runtime_guidance_inventory(
            parent_wp_code="D0",
            render_sheets=[_render_sheet("D0-2", "函证明细 D0-2")],
            static_entries=(),
            custom_entries=custom,
            include_whole_workbook_context=False,
        )


def test_static_without_source_ref_validation_never_reaches_exact():
    """source_ref 未经验证的 static 必须保持 invalid，不能凭 shape 判 exact。

    这条守卫堵住 INV02 变异：把 invalid 分支里的 ``or`` 改成 ``and`` 会让
    ``exact_status=exact + source_ref_status=unvalidated`` 落到 else 分支，
    最终被判 exact —— 即 design §3 要求的「无 runtime contract 的 static
    同样不得据 shape 判 exact」。

    断言必须精确锁定 blocker 码：``_exemption_errors``/其它分支产生的
    ``source_refs_invalid`` 也会让粗粒度 ``exact_status == "invalid"`` 通过，
    从而制造假绿。用 ``exact_status="exact"`` 保证只有本分支能被命中，
    再用精确码钉住 unvalidated 的独立判定路径。
    """
    static = GuidanceInventoryEntry(
        wp_code="D0-1",
        path="/guidance/D0-1.json",
        parse_status="ok",
        source_digest="c" * 64,
        exact_status="exact",
        missing_sections=(),
        reason="ok",
        source_ref_status="unvalidated",
        source_ref_facts_digest="f" * 64,
    )
    inventory = build_runtime_guidance_inventory(
        parent_wp_code="D0",
        render_sheets=[_render_sheet("D0-1", "函证汇总 D0-1")],
        static_entries=[static],
        include_whole_workbook_context=False,
    )
    entry = inventory.entries[0]
    assert entry.exact_status == "invalid", (
        f"source_ref_status=unvalidated 不得判 exact，实际={entry.exact_status}"
    )
    assert entry.required is True
    # 必须精确断言 blocker 码：`validation_blocker` 字典的兜底默认值恰为
    # "source_refs_invalid"，因此若 invalid 分支的 source_ref 条件被整个删掉
    # （INV02 变异），断言只能靠「unvalidated 不是默认码」这一条区分出来。
    assert entry.exact_blockers == ("source_ref_context_missing",), (
        f"unvalidated 必须产出专属 blocker，实际={entry.exact_blockers}"
    )
    # 反向自检：默认兜底码必须不可作为判定依据，否则守卫退化为「只要进入
    # invalid 分支就通过」，无法检测 source_ref 条件的删除。
    assert entry.exact_blockers != ("source_refs_invalid",)


def test_run_id_and_generated_at_are_excluded_from_entry_digest():
    """run 元数据不得污染稳定 digest，否则会制造无内容变化的 artifact 冲突。"""
    now = datetime(2026, 9, 7, tzinfo=UTC)
    shared = {
        "parent_wp_code": "D0",
        "render_sheets": [_render_sheet("D0-1", "函证汇总 D0-1")],
        "static_entries": [_static_entry("D0-1")],
        "include_whole_workbook_context": False,
        "now": now,
    }
    first = build_runtime_guidance_inventory(run_id="run-a", **shared)
    second = build_runtime_guidance_inventory(run_id="run-b", **shared)

    assert first.run_id != second.run_id
    assert first.entries[0].entry_id == second.entries[0].entry_id
    assert first.entries[0].entry_digest == second.entries[0].entry_digest
    assert first.facts_digest == second.facts_digest
    assert "run-a" not in first.facts_digest


@pytest.mark.parametrize(
    ("title", "key"),
    [
        ("本表用途", "purpose"),
        ("与其他底稿的关联", "evidence"),
        ("二、测试方法与程序", "steps"),
        ("偏差率计算", "formulas"),
        ("常见波动原因分类", "judgments"),
        ("未知段落标题XYZ", None),
    ],
)
def test_infer_section_key_high_confidence_aliases(title: str, key: str | None):
    """T7 别名只认高置信标题；不得把任意中文映射进九段。"""
    assert infer_section_key(title) == key
