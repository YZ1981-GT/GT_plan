"""编制说明全局 coverage 聚合。

本模块只聚合调用方提供的真实 runtime context；sheet 分母仍来自 render-config，
不会维护第二份 wp/sheet 业务清册。持久化输出仅是带输入 digest 的可重算 evidence。
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Mapping, Sequence
from uuid import uuid4

from app.services.guidance_inventory import (
    GuidanceInventoryEntry,
    GuidanceSourceFact,
    RuntimeCustomGuidance,
    RuntimeGuidanceExemption,
    RuntimeGuidanceInventoryEntry,
    RuntimeEntryStatus,
    build_runtime_guidance_inventory,
    build_static_guidance_inventory,
    revalidate_static_guidance_inventory,
    sheet_code_belongs_to_wp,
    stable_digest,
)
from app.services.guidance_source_refs import (
    TemplateAuthoritySnapshot,
    build_source_ref_contexts,
)


@dataclass(frozen=True)
class GuidanceCoverageContext:
    """一个真实 working-paper 实例的最终 render/input facts。"""

    context_id: str
    wp_id: str
    project_id: str
    parent_wp_code: str
    render_sheets: tuple[Mapping[str, Any], ...]
    template_facts: tuple[GuidanceSourceFact, ...] = ()
    custom_entries: tuple[RuntimeCustomGuidance, ...] = ()
    exemptions: tuple[RuntimeGuidanceExemption, ...] = ()
    template_authority_snapshot: TemplateAuthoritySnapshot | None = None
    include_whole_workbook_context: bool = False


@dataclass(frozen=True)
class GuidanceCoverageEntry:
    global_entry_id: str
    context_id: str
    wp_id: str
    project_id: str
    parent_wp_code: str
    runtime_entry_id: str
    sheet_code: str | None
    sheet_name: str
    context_kind: str
    required: bool
    exact_status: RuntimeEntryStatus
    missing_sections: tuple[str, ...]
    exact_blockers: tuple[str, ...]
    stale_reasons: tuple[str, ...]
    entry_digest: str
    source_facts: tuple[GuidanceSourceFact, ...]


@dataclass(frozen=True)
class GuidanceCoverageReport:
    schema_version: int
    run_id: str
    generated_at: str
    facts_digest: str
    contexts_digest: str
    entries: tuple[GuidanceCoverageEntry, ...]
    counters: dict[str, int]

    @property
    def closed(self) -> bool:
        return (
            self.counters.get("required", 0) == self.counters.get("required_exact", 0)
            and self.counters.get("required_non_exact", 0) == 0
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["closed"] = self.closed
        return payload


def _context_facts(context: GuidanceCoverageContext) -> dict[str, Any]:
    """只含稳定输入身份；run time/generated_at 不进入 context digest。"""
    return {
        "context_id": context.context_id,
        "wp_id": context.wp_id,
        "project_id": context.project_id,
        "parent_wp_code": context.parent_wp_code,
        "render_sheets": [dict(item) for item in context.render_sheets],
        "template_facts": [asdict(item) for item in context.template_facts],
        "custom_entries": [
            {
                "sheet_code": item.sheet_code,
                "sheet_name": item.sheet_name,
                "source_digest": item.source_digest,
                "version": item.version,
            }
            for item in context.custom_entries
        ],
        "exemptions": [asdict(item) for item in context.exemptions],
        "template_authority_snapshot": (
            context.template_authority_snapshot.version_facts()
            if context.template_authority_snapshot is not None
            else None
        ),
        "include_whole_workbook_context": context.include_whole_workbook_context,
    }


def _global_entry_id(context_id: str, entry: RuntimeGuidanceInventoryEntry) -> str:
    identity = {"context_id": context_id, "runtime_entry_id": entry.entry_id}
    return f"guidance-coverage:{stable_digest(identity)[:24]}"


def build_global_guidance_coverage(
    contexts: Sequence[GuidanceCoverageContext],
    *,
    static_entries: Sequence[GuidanceInventoryEntry] | None = None,
    prior_entry_digests: Mapping[str, str] | None = None,
    now: datetime | None = None,
    run_id: str | None = None,
) -> GuidanceCoverageReport:
    """聚合多个真实 context；新增 render sheet 必然扩大 required 分母。"""
    timestamp = (now or datetime.now(UTC)).astimezone(UTC)
    report_run_id = run_id or str(uuid4())
    static_entries = tuple(static_entries or build_static_guidance_inventory())
    prior_entry_digests = prior_entry_digests or {}

    ordered_contexts = sorted(contexts, key=lambda item: item.context_id)
    context_ids = [context.context_id for context in ordered_contexts]
    if len(context_ids) != len(set(context_ids)):
        raise ValueError("guidance coverage context_id 不唯一")

    entries: list[GuidanceCoverageEntry] = []
    for context in ordered_contexts:
        if not context.context_id or not context.wp_id or not context.project_id:
            raise ValueError("guidance coverage context identity 不完整")
        if not context.parent_wp_code:
            raise ValueError("guidance coverage parent_wp_code 为空")
        relevant_static = tuple(
            entry
            for entry in static_entries
            if entry.wp_code == context.parent_wp_code
            or sheet_code_belongs_to_wp(context.parent_wp_code, entry.wp_code)
        )
        if context.template_authority_snapshot is not None:
            source_ref_contexts = build_source_ref_contexts(
                context.template_authority_snapshot,
                context.render_sheets,
                additional_wp_codes=tuple(entry.wp_code for entry in relevant_static),
            )
        else:
            source_ref_contexts = {}
        # 每个 active template context 都重读并复验 static；禁止复用另一项目的 exact。
        context_static = revalidate_static_guidance_inventory(
            relevant_static,
            source_ref_contexts=source_ref_contexts,
        )
        inventory = build_runtime_guidance_inventory(
            parent_wp_code=context.parent_wp_code,
            render_sheets=context.render_sheets,
            template_facts=context.template_facts,
            static_entries=context_static,
            custom_entries=context.custom_entries,
            exemptions=context.exemptions,
            include_whole_workbook_context=context.include_whole_workbook_context,
            now=timestamp,
            run_id=f"{report_run_id}:{stable_digest(context.context_id)[:12]}",
        )
        for runtime_entry in inventory.entries:
            global_id = _global_entry_id(context.context_id, runtime_entry)
            stale_reasons = list(runtime_entry.stale_reasons)
            prior_digest = prior_entry_digests.get(global_id)
            if prior_digest is not None and prior_digest != runtime_entry.entry_digest:
                stale_reasons.append("source_facts_changed")
            normalized_stale = tuple(sorted(set(stale_reasons)))
            status: RuntimeEntryStatus = (
                "stale" if normalized_stale else runtime_entry.exact_status
            )
            entries.append(
                GuidanceCoverageEntry(
                    global_entry_id=global_id,
                    context_id=context.context_id,
                    wp_id=context.wp_id,
                    project_id=context.project_id,
                    parent_wp_code=context.parent_wp_code,
                    runtime_entry_id=runtime_entry.entry_id,
                    sheet_code=runtime_entry.sheet_code,
                    sheet_name=runtime_entry.sheet_name,
                    context_kind=runtime_entry.context_kind,
                    required=runtime_entry.required,
                    exact_status=status,
                    missing_sections=runtime_entry.missing_sections,
                    exact_blockers=runtime_entry.exact_blockers,
                    stale_reasons=normalized_stale,
                    entry_digest=runtime_entry.entry_digest,
                    source_facts=runtime_entry.source_facts,
                )
            )

    ordered_entries = tuple(
        sorted(
            entries,
            key=lambda item: (
                item.context_id,
                item.context_kind,
                item.sheet_code or "",
                item.sheet_name,
                item.global_entry_id,
            ),
        )
    )
    status_counts = Counter(item.exact_status for item in ordered_entries)
    required = sum(1 for item in ordered_entries if item.required)
    required_exact = sum(
        1 for item in ordered_entries if item.required and item.exact_status == "exact"
    )
    counters = dict(status_counts)
    counters.update(
        {
            "contexts": len(ordered_contexts),
            "entries": len(ordered_entries),
            "required": required,
            "required_exact": required_exact,
            "required_non_exact": required - required_exact,
            "whole_workbook_exemptions": sum(
                1
                for item in ordered_entries
                if item.context_kind == "whole_workbook"
                and item.exact_status == "inherited"
            ),
        }
    )
    contexts_digest = stable_digest([_context_facts(item) for item in ordered_contexts])
    facts_digest = stable_digest(
        [
            {
                "global_entry_id": item.global_entry_id,
                "entry_digest": item.entry_digest,
                "status": item.exact_status,
                "stale_reasons": list(item.stale_reasons),
            }
            for item in ordered_entries
        ]
    )
    return GuidanceCoverageReport(
        schema_version=1,
        run_id=report_run_id,
        generated_at=timestamp.isoformat(),
        facts_digest=facts_digest,
        contexts_digest=contexts_digest,
        entries=ordered_entries,
        counters=counters,
    )
