"""运行时 guidance inventory 折叠。

事实类型与加载器见 :mod:`guidance_runtime_facts`；本模块只把一次 render context
的事实折叠成不可变 entry 与集合核算，运行元数据不参与稳定 digest。
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any, Mapping, Sequence
from uuid import uuid4

from app.services.guidance_inventory import (
    CANONICAL_SECTION_KEYS,
    GuidanceInventoryEntry,
    build_static_guidance_inventory,
    sheet_code_belongs_to_wp,
    stable_digest,
)
from app.services.guidance_runtime_facts import (
    GuidanceSourceFact,
    RuntimeContextKind,
    RuntimeCustomGuidance,
    RuntimeEntryStatus,
    RuntimeGuidanceExemption,
    RuntimeGuidanceInventory,
    RuntimeGuidanceInventoryEntry,
    _exemption_errors,
    _matching_exemption,
    _normalized_sheet_name,
    _resolution_policy_fact,
    _stable_entry_identity,
    _static_source_facts,
    normalize_render_sheet_facts,
)

__all__ = [
    "build_runtime_guidance_inventory",
    "find_runtime_inventory_entry",
]


def __getattr__(name: str) -> Any:
    """事实类型/加载器已迁至 ``guidance_runtime_facts``；保留既有导入路径。"""
    from app.services import guidance_runtime_facts

    try:
        return getattr(guidance_runtime_facts, name)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None


def build_runtime_guidance_inventory(
    *,
    parent_wp_code: str,
    render_sheets: Sequence[Mapping[str, Any]],
    template_facts: Sequence[GuidanceSourceFact] = (),
    static_entries: Sequence[GuidanceInventoryEntry] | None = None,
    custom_entries: Sequence[RuntimeCustomGuidance] = (),
    exemptions: Sequence[RuntimeGuidanceExemption] = (),
    prior_entry_digests: Mapping[str, str] | None = None,
    include_whole_workbook_context: bool = False,
    now: datetime | None = None,
    run_id: str | None = None,
) -> RuntimeGuidanceInventory:
    """合并 render/template/static/custom facts；运行元数据不参与稳定 digest。"""
    timestamp = (now or datetime.now(UTC)).astimezone(UTC)
    static_entries = tuple(static_entries or build_static_guidance_inventory())
    static_by_code: dict[str, GuidanceInventoryEntry] = {}
    for static in static_entries:
        if static.wp_code in static_by_code:
            raise ValueError(f"static guidance wp_code 不唯一: {static.wp_code}")
        static_by_code[static.wp_code] = static
    render_facts = normalize_render_sheet_facts(parent_wp_code, render_sheets)
    prior_entry_digests = prior_entry_digests or {}
    entries: list[RuntimeGuidanceInventoryEntry] = []
    represented_codes: set[str] = set()
    represented_custom_ids: set[int] = set()

    def make_entry(
        *,
        sheet_code: str | None,
        sheet_name: str,
        context_kind: RuntimeContextKind,
        required: bool,
        source_facts: Sequence[GuidanceSourceFact],
        status: RuntimeEntryStatus,
        missing_sections: Sequence[str],
        stale_reasons: Sequence[str],
        exemption: RuntimeGuidanceExemption | None,
        exact_blockers: Sequence[str] = (),
    ) -> RuntimeGuidanceInventoryEntry:
        identity = _stable_entry_identity(
            parent_wp_code=parent_wp_code,
            sheet_code=sheet_code,
            sheet_name=sheet_name,
            context_kind=context_kind,
        )
        entry_id = f"guidance:{stable_digest(identity)[:24]}"
        ordered_facts = tuple(
            sorted(source_facts, key=lambda item: (item.kind, item.ref, item.digest))
        )
        normalized_blockers = tuple(dict.fromkeys(exact_blockers))
        base_facts = {
            **identity,
            "sheet_name": _normalized_sheet_name(sheet_name),
            "required": required,
            "source_facts": [asdict(item) for item in ordered_facts],
            "missing_sections": list(missing_sections),
            "exact_blockers": list(normalized_blockers),
            "exemption": asdict(exemption) if exemption else None,
        }
        entry_digest = stable_digest(base_facts)
        stale = list(stale_reasons)
        prior = prior_entry_digests.get(entry_id)
        if prior is not None and prior != entry_digest:
            stale.append("source_facts_changed")
        effective_status: RuntimeEntryStatus = "stale" if stale else status
        return RuntimeGuidanceInventoryEntry(
            entry_id=entry_id,
            parent_wp_code=parent_wp_code,
            sheet_code=sheet_code,
            sheet_name=sheet_name,
            context_kind=context_kind,
            required=required,
            source_facts=ordered_facts,
            exact_status=effective_status,
            missing_sections=tuple(missing_sections),
            exact_blockers=normalized_blockers,
            stale_reasons=tuple(sorted(set(stale))),
            exemption=exemption,
            entry_digest=entry_digest,
        )

    for fact in render_facts:
        target_code = fact.sheet_code or parent_wp_code
        represented_codes.add(target_code)
        static = static_by_code.get(target_code)
        matching_custom = [
            (index, item)
            for index, item in enumerate(custom_entries)
            if (item.sheet_code and item.sheet_code == fact.sheet_code)
            or (
                item.sheet_name
                and _normalized_sheet_name(item.sheet_name)
                == _normalized_sheet_name(fact.sheet_name)
            )
        ]
        if len(matching_custom) > 1:
            raise ValueError(f"custom guidance identity 不唯一: {fact.sheet_name}")
        custom = matching_custom[0][1] if matching_custom else None
        if matching_custom:
            represented_custom_ids.add(matching_custom[0][0])

        inheritance = _matching_exemption(fact, exemptions, kind="inheritance")
        exemption_errors = _exemption_errors(inheritance, now=timestamp)
        valid_inheritance = inheritance is not None and not exemption_errors
        source_facts: list[GuidanceSourceFact] = [
            GuidanceSourceFact(
                kind="render_config",
                ref=fact.fact_id,
                digest=fact.source_digest,
                origin=fact.component_type,
            ),
            *template_facts,
        ]
        if static is not None:
            source_facts.extend(_static_source_facts(static))
        if custom is not None:
            source_facts.append(
                GuidanceSourceFact(
                    kind="custom_runtime",
                    ref=f"{fact.fact_id}:custom_confirmed",
                    digest=custom.source_digest,
                    version=custom.version,
                    origin="custom_confirmed",
                )
            )
        if inheritance is not None:
            source_facts.append(_resolution_policy_fact(parent_wp_code, inheritance))

        stale_reasons = list(exemption_errors)
        if exemption_errors:
            status: RuntimeEntryStatus = "stale"
            missing = static.missing_sections if static else CANONICAL_SECTION_KEYS
            blockers = static.exact_blockers if static else ("canonical_sections",)
        elif valid_inheritance:
            status = "inherited"
            missing = ()
            blockers = ()
        elif (
            static is not None
            and static.exact_status == "exact"
            and static.source_ref_status == "valid"
        ):
            status = "exact"
            missing = ()
            blockers = ()
        elif static is not None and (
            static.exact_status == "stale" or static.source_ref_status == "stale"
        ):
            status = "stale"
            missing = static.missing_sections
            blockers = static.exact_blockers or ("source_refs_stale",)
            stale_reasons.append("static_source_refs_stale")
        elif static is not None and (
            static.exact_status == "invalid"
            or static.source_ref_status in {"invalid", "cross_template", "unvalidated"}
            or static.exact_status == "exact"
        ):
            status = "invalid"
            missing = static.missing_sections
            validation_blocker = {
                "cross_template": "source_refs_cross_template",
                "unvalidated": "source_ref_context_missing",
            }.get(static.source_ref_status, "source_refs_invalid")
            blockers = tuple(dict.fromkeys((*static.exact_blockers, validation_blocker)))
        elif custom is not None:
            status = "invalid"
            missing = static.missing_sections if static else CANONICAL_SECTION_KEYS
            blockers = tuple(
                dict.fromkeys(
                    (*((static.exact_blockers) if static else ()), "custom_source_authority_unavailable")
                )
            )
        else:
            status = "missing"
            missing = static.missing_sections if static else CANONICAL_SECTION_KEYS
            blockers = static.exact_blockers if static else ("canonical_sections",)

        entries.append(
            make_entry(
                sheet_code=fact.sheet_code,
                sheet_name=fact.sheet_name,
                context_kind="sheet",
                required=not valid_inheritance,
                source_facts=source_facts,
                status=status,
                missing_sections=missing,
                stale_reasons=stale_reasons,
                exemption=inheritance,
                exact_blockers=blockers,
            )
        )

    if not render_facts:
        # 真实 WP context 本身也必须进入分母。模板/static 存在但 render manifest 为空
        # 时生成可观察 blocker，禁止空清册把 required 分母静默缩成 0。
        parent_static = static_by_code.get(parent_wp_code)
        context_facts: list[GuidanceSourceFact] = list(template_facts)
        if parent_static is not None:
            context_facts.extend(_static_source_facts(parent_static))
        entries.append(
            make_entry(
                sheet_code=None,
                sheet_name=parent_wp_code,
                context_kind="template_only",
                required=True,
                source_facts=context_facts,
                status="invalid",
                missing_sections=(
                    parent_static.missing_sections
                    if parent_static is not None
                    else CANONICAL_SECTION_KEYS
                ),
                stale_reasons=(),
                exemption=None,
                exact_blockers=(
                    "render_config_missing",
                    *(parent_static.exact_blockers if parent_static is not None else ()),
                ),
            )
        )

    # guidance/custom orphan 保持可观察，但绝不能反向授权为 render 可达 sheet。
    for static in static_entries:
        if static.wp_code in represented_codes or static.wp_code == parent_wp_code:
            continue
        if not sheet_code_belongs_to_wp(parent_wp_code, static.wp_code):
            continue
        entries.append(
            make_entry(
                sheet_code=static.wp_code,
                sheet_name=static.wp_code,
                context_kind="guidance_only",
                required=False,
                source_facts=_static_source_facts(static),
                status="invalid",
                missing_sections=static.missing_sections,
                stale_reasons=("guidance_source_not_render_reachable",),
                exemption=None,
                exact_blockers=static.exact_blockers,
            )
        )

    for index, custom in enumerate(custom_entries):
        if index in represented_custom_ids:
            continue
        custom_identity = custom.sheet_code or custom.sheet_name or f"custom-{index + 1}"
        entries.append(
            make_entry(
                sheet_code=custom.sheet_code,
                sheet_name=custom.sheet_name or custom_identity,
                context_kind="custom_runtime",
                required=False,
                source_facts=(
                    GuidanceSourceFact(
                        kind="custom_runtime",
                        ref=f"unmatched:{custom_identity}",
                        digest=custom.source_digest,
                        version=custom.version,
                        origin="custom_confirmed",
                    ),
                ),
                status="invalid",
                missing_sections=CANONICAL_SECTION_KEYS,
                stale_reasons=("custom_source_not_render_reachable",),
                exemption=None,
                exact_blockers=("custom_source_authority_unavailable",),
            )
        )

    if include_whole_workbook_context:
        whole_exemption = _matching_exemption(None, exemptions, kind="whole_workbook")
        whole_errors = _exemption_errors(whole_exemption, now=timestamp)
        whole_facts: list[GuidanceSourceFact] = list(template_facts)
        if whole_exemption is not None:
            whole_facts.append(_resolution_policy_fact(parent_wp_code, whole_exemption))
        entries.append(
            make_entry(
                sheet_code=None,
                sheet_name="",
                context_kind="whole_workbook",
                required=False,
                source_facts=whole_facts,
                status="inherited" if whole_exemption is not None and not whole_errors else "invalid",
                missing_sections=(),
                stale_reasons=whole_errors
                or (() if whole_exemption else ("whole_workbook_exemption_missing",)),
                exemption=whole_exemption,
            )
        )

    ordered = tuple(
        sorted(
            entries,
            key=lambda item: (
                item.context_kind,
                item.sheet_code or "",
                _normalized_sheet_name(item.sheet_name),
                item.entry_id,
            ),
        )
    )
    facts_digest = stable_digest(
        [
            {
                "entry_id": item.entry_id,
                "entry_digest": item.entry_digest,
                "status": item.exact_status,
                "stale_reasons": list(item.stale_reasons),
            }
            for item in ordered
        ]
    )
    counters = dict(Counter(item.exact_status for item in ordered))
    counters["required"] = sum(1 for item in ordered if item.required)
    counters["required_exact"] = sum(
        1 for item in ordered if item.required and item.exact_status == "exact"
    )
    return RuntimeGuidanceInventory(
        schema_version=1,
        run_id=run_id or str(uuid4()),
        generated_at=timestamp.isoformat(),
        facts_digest=facts_digest,
        entries=ordered,
        counters=counters,
    )


def find_runtime_inventory_entry(
    inventory: RuntimeGuidanceInventory,
    *,
    sheet_code: str | None,
    sheet_name: str | None,
    whole_workbook: bool = False,
) -> RuntimeGuidanceInventoryEntry | None:
    normalized_name = _normalized_sheet_name(sheet_name)
    if whole_workbook:
        matches = [
            entry for entry in inventory.entries if entry.context_kind == "whole_workbook"
        ]
    elif sheet_code is None and not normalized_name:
        # parent/no-sheet 请求也必须命中一个已验证的 runtime contract，不能用 None
        # 退回 service 的 shape-only 判定。优先 parent canonical sheet，其次空 manifest blocker。
        parent_matches = [
            entry
            for entry in inventory.entries
            if entry.context_kind == "sheet" and entry.sheet_code == entry.parent_wp_code
        ]
        matches = parent_matches or [
            entry for entry in inventory.entries if entry.context_kind == "template_only"
        ]
    else:
        matches = [
            entry
            for entry in inventory.entries
            if entry.context_kind == "sheet"
            and (sheet_code is None or entry.sheet_code == sheet_code)
            and (
                not normalized_name
                or _normalized_sheet_name(entry.sheet_name) == normalized_name
            )
        ]
    if len(matches) > 1:
        raise ValueError("runtime guidance inventory identity 不唯一")
    return matches[0] if matches else None
