"""运行时 guidance 事实类型与加载器。

render-config sheets、模板文件摘要、豁免与 custom runtime guidance 的规范化都在
这里；:mod:`guidance_runtime_inventory` 只负责把这些事实折叠成 entry。所有加载器
在输入缺失/非法时返回结构化 reason，不做兜底补齐。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from app.services.guidance_inventory import (
    CANONICAL_SECTION_KEYS,
    GUIDANCE_DIR,
    GuidanceInventoryEntry,
    analyze_guidance_document,
    extract_sheet_code,
    load_guidance_document,
    normalize_source_refs,
    stable_digest,
)

RuntimeEntryStatus = Literal["exact", "missing", "stale", "inherited", "invalid"]
RuntimeContextKind = Literal[
    "sheet",
    "whole_workbook",
    "template_only",
    "guidance_only",
    "custom_runtime",
]


@dataclass(frozen=True)
class GuidanceSourceFact:
    """参与 inventory/version 的不可变来源事实。"""

    kind: Literal[
        "render_config",
        "template_index",
        "template_file",
        "static_guidance",
        "source_ref_validation",
        "custom_runtime",
        "resolution_policy",
    ]
    ref: str
    digest: str
    version: str | None = None
    origin: str | None = None


@dataclass(frozen=True)
class RenderSheetFact:
    """render-config 最终可见 sheet 的最小身份投影。"""

    fact_id: str
    parent_wp_code: str
    sheet_name: str
    sheet_code: str | None
    sheet_code_reason: str
    whole_workbook: bool
    component_type: str
    source_digest: str


@dataclass(frozen=True)
class RuntimeGuidanceExemption:
    """有依据、有期限的继承或整册豁免。"""

    kind: Literal["inheritance", "whole_workbook"]
    target_sheet_code: str | None
    target_sheet_name: str | None
    inherits_from: str | None
    reason_code: str
    basis_refs: tuple[dict[str, Any], ...]
    approved_by: str
    approved_at: str
    review_after: str


@dataclass(frozen=True)
class RuntimeCustomGuidance:
    """第三个 spec 可写入的已确认项目级说明接口契约。"""

    sheet_code: str | None
    sheet_name: str | None
    document: dict[str, Any]
    source_digest: str
    version: str | None


@dataclass(frozen=True)
class RuntimeGuidanceInventoryEntry:
    entry_id: str
    parent_wp_code: str
    sheet_code: str | None
    sheet_name: str
    context_kind: RuntimeContextKind
    required: bool
    source_facts: tuple[GuidanceSourceFact, ...]
    exact_status: RuntimeEntryStatus
    missing_sections: tuple[str, ...]
    exact_blockers: tuple[str, ...]
    stale_reasons: tuple[str, ...]
    exemption: RuntimeGuidanceExemption | None
    entry_digest: str

    def version_facts(self) -> dict[str, Any]:
        """供 GuidanceService 纳入响应版本；不含运行时间等非业务事实。"""
        return {
            "entry_id": self.entry_id,
            "entry_digest": self.entry_digest,
            "context_kind": self.context_kind,
            "required": self.required,
            "exact_status": self.exact_status,
            "source_facts": [asdict(fact) for fact in self.source_facts],
            "exact_blockers": list(self.exact_blockers),
            "stale_reasons": list(self.stale_reasons),
        }


@dataclass(frozen=True)
class RuntimeGuidanceInventory:
    schema_version: int
    run_id: str
    generated_at: str
    facts_digest: str
    entries: tuple[RuntimeGuidanceInventoryEntry, ...]
    counters: dict[str, int]


def _normalized_sheet_name(value: str | None) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def normalize_render_sheet_facts(
    parent_wp_code: str,
    sheets: Sequence[Mapping[str, Any]],
) -> tuple[RenderSheetFact, ...]:
    """只消费 render-config 最终 ``sheets``；不从模板/guidance 反向授权。"""
    facts: list[RenderSheetFact] = []
    seen_identities: set[tuple[str | None, str, bool]] = set()
    for raw in sheets:
        sheet_name = str(raw.get("sheet_name") or "").strip()
        if not sheet_name:
            raise ValueError("render-config sheet 缺少 sheet_name")
        raw_code = raw.get("sheet_code")
        sheet_code = str(raw_code).strip() if raw_code is not None else None
        sheet_code = sheet_code or None
        reason = str(raw.get("sheet_code_reason") or "").strip()
        if sheet_code is None and not reason:
            raise ValueError(f"render-config sheet {sheet_name!r} 缺少 sheet_code_reason")
        whole_workbook = bool(raw.get("whole_workbook", False))
        if whole_workbook and sheet_code is not None:
            raise ValueError("whole_workbook render fact 必须使用 sheet_code=null")
        component_type = str(raw.get("componentType") or "").strip()
        if not component_type:
            raise ValueError(f"render-config sheet {sheet_name!r} 缺少 componentType")
        normalized_name = _normalized_sheet_name(sheet_name)
        identity_key = (sheet_code, normalized_name, whole_workbook)
        if identity_key in seen_identities:
            raise ValueError(f"render-config 出现重复 sheet identity: {sheet_name}")
        seen_identities.add(identity_key)
        source_identity = {
            "parent_wp_code": parent_wp_code,
            "sheet_code": sheet_code,
            "sheet_name": normalized_name,
            "sheet_code_reason": reason,
            "whole_workbook": whole_workbook,
            "component_type": component_type,
        }
        source_digest = stable_digest(source_identity)
        facts.append(
            RenderSheetFact(
                fact_id=f"render:{source_digest[:24]}",
                parent_wp_code=parent_wp_code,
                sheet_name=sheet_name,
                sheet_code=sheet_code,
                sheet_code_reason=reason or "explicit_code",
                whole_workbook=whole_workbook,
                component_type=component_type,
                source_digest=source_digest,
            )
        )
    return tuple(facts)


def resolve_render_sheet_context(
    *,
    parent_wp_code: str,
    render_sheets: Sequence[Mapping[str, Any]],
    requested_sheet_code: str | None,
    requested_sheet_name: str | None,
    whole_workbook: bool = False,
) -> tuple[str | None, str, RenderSheetFact | None]:
    """以最终 render-config facts 做 membership；静态文件不能反向授权 sheet。"""
    code = str(requested_sheet_code or "").strip() or None
    name = str(requested_sheet_name or "").strip() or None
    if whole_workbook:
        if code is not None:
            raise ValueError("完整工作簿不得携带 sheet_code")
        return None, "whole_workbook", None
    if code is None and name is None:
        return None, "sheet_without_code", None

    by_name = extract_sheet_code(name)
    if code is not None and by_name is not None and code != by_name:
        raise ValueError("sheet_code 与 sheet_name 解析结果不一致")

    facts = normalize_render_sheet_facts(parent_wp_code, render_sheets)
    normalized_name = _normalized_sheet_name(name)
    matches = [
        fact
        for fact in facts
        if (code is None or fact.sheet_code == code)
        and (name is None or _normalized_sheet_name(fact.sheet_name) == normalized_name)
    ]
    if not matches and code is None and by_name is not None:
        matches = [
            fact
            for fact in facts
            if fact.sheet_code == by_name
            and (name is None or _normalized_sheet_name(fact.sheet_name) == normalized_name)
        ]
    if not matches:
        raise ValueError("sheet 未出现在当前底稿 render-config 可达清册")
    if len(matches) != 1:
        raise ValueError("sheet identity 不唯一，必须同时提供 canonical sheet_code 与 sheet_name")
    match = matches[0]
    return (
        match.sheet_code,
        "explicit_code" if code is not None else "derived_from_render_sheet",
        match,
    )


def _file_source_fact(
    *,
    kind: Literal["template_index", "template_file"],
    path: Path,
    version: str | None = None,
    origin: str | None = None,
) -> GuidanceSourceFact:
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        digest = stable_digest({"path": str(path), "missing": True})
    return GuidanceSourceFact(
        kind=kind,
        ref=str(path),
        digest=digest,
        version=version,
        origin=origin,
    )


def load_template_source_facts(
    parent_wp_code: str,
    *,
    template_path: Path | None = None,
    index_path: Path | None = None,
    template_version: str | None = None,
    template_origin: str | None = None,
) -> tuple[GuidanceSourceFact, ...]:
    """读取权威模板索引及当前实例/override 载体指纹。"""
    if index_path is None:
        index_path = Path(__file__).resolve().parent.parent.parent / "wp_templates" / "_index.json"
    facts: list[GuidanceSourceFact] = []
    indexed_paths: set[str] = set()
    if index_path.is_file():
        try:
            data = json.loads(index_path.read_text(encoding="utf-8"))
            index_origin = "canonical_index"
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            data = {}
            index_origin = "invalid_index"
        facts.append(
            _file_source_fact(
                kind="template_index",
                path=index_path,
                origin=index_origin,
            )
        )
        root = index_path.parent
        for item in data.get("files", []) if isinstance(data, dict) else []:
            if not isinstance(item, dict) or str(item.get("wp_code") or "") != parent_wp_code:
                continue
            relpath = str(item.get("relative_path") or "").strip()
            if not relpath:
                continue
            indexed_path = root / relpath
            facts.append(
                _file_source_fact(
                    kind="template_file",
                    path=indexed_path,
                    origin="canonical_index",
                )
            )
            indexed_paths.add(
                str(indexed_path.resolve()) if indexed_path.exists() else str(indexed_path)
            )
    if template_path is not None:
        key = str(template_path.resolve()) if template_path.exists() else str(template_path)
        if key not in indexed_paths or template_version or template_origin:
            facts.append(
                _file_source_fact(
                    kind="template_file",
                    path=template_path,
                    version=template_version,
                    origin=template_origin or "runtime_resolved",
                )
            )
    return tuple(sorted(facts, key=lambda fact: (fact.kind, fact.ref, fact.digest)))


def load_runtime_exemptions(
    parent_wp_code: str,
    *,
    guidance_dir: Path = GUIDANCE_DIR,
) -> tuple[RuntimeGuidanceExemption, ...]:
    """从父级 canonical guidance 的 ``resolution_policy`` 读取裁决。"""
    document = load_guidance_document(parent_wp_code, guidance_dir=guidance_dir) or {}
    policy = document.get("resolution_policy")
    if not isinstance(policy, dict):
        return ()

    raw_items: list[tuple[str, Any]] = []
    raw_inheritance = policy.get("inheritance")
    if isinstance(raw_inheritance, list):
        raw_items.extend(("inheritance", item) for item in raw_inheritance)
    raw_whole = policy.get("whole_workbook")
    if isinstance(raw_whole, dict):
        raw_items.append(("whole_workbook", raw_whole))

    exemptions: list[RuntimeGuidanceExemption] = []
    for kind, item in raw_items:
        if not isinstance(item, dict):
            continue
        exemptions.append(
            RuntimeGuidanceExemption(
                kind=kind,  # type: ignore[arg-type]
                target_sheet_code=str(item.get("target_sheet_code") or "").strip() or None,
                target_sheet_name=str(item.get("target_sheet_name") or "").strip() or None,
                inherits_from=str(item.get("inherits_from") or "").strip() or None,
                reason_code=str(item.get("reason_code") or "").strip(),
                basis_refs=normalize_source_refs(item.get("basis_refs")),
                approved_by=str(item.get("approved_by") or "").strip(),
                approved_at=str(item.get("approved_at") or "").strip(),
                review_after=str(item.get("review_after") or "").strip(),
            )
        )
    return tuple(exemptions)


def normalize_runtime_custom_guidance(
    raw_batch: Mapping[str, Mapping[str, Any]] | None,
    *,
    wp_id: str,
) -> tuple[RuntimeCustomGuidance, ...]:
    """只接受明确 ``custom_confirmed`` 的 field override。"""
    entries: list[RuntimeCustomGuidance] = []
    prefix = f"{wp_id}:"
    for item_key, fields in (raw_batch or {}).items():
        if not str(item_key).startswith(prefix) or not isinstance(fields, Mapping):
            continue
        document = fields.get("document")
        if not isinstance(document, dict) or document.get("status") != "custom_confirmed":
            continue
        try:
            analysis = analyze_guidance_document(document)
        except (TypeError, ValueError):
            continue
        # custom binary/source authority 尚未落地；这里只保留结构完整且已确认的
        # 条目供 runtime 清册显式打 invalid，绝不据 shape 直接授予 exact。
        if (
            analysis.present_sections != CANONICAL_SECTION_KEYS
            or analysis.missing_sections
            or analysis.duplicate_sections
            or analysis.unmapped_section_count
        ):
            continue
        entries.append(
            RuntimeCustomGuidance(
                sheet_code=str(document.get("sheet_code") or "").strip() or None,
                sheet_name=str(document.get("sheet_name") or "").strip() or None,
                document=document,
                source_digest=stable_digest(document),
                version=str(document.get("version") or "").strip() or None,
            )
        )
    return tuple(entries)


def _parse_instant(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _matching_exemption(
    fact: RenderSheetFact | None,
    exemptions: Sequence[RuntimeGuidanceExemption],
    *,
    kind: Literal["inheritance", "whole_workbook"],
) -> RuntimeGuidanceExemption | None:
    matches: list[RuntimeGuidanceExemption] = []
    for exemption in exemptions:
        if exemption.kind != kind:
            continue
        if kind == "whole_workbook":
            matches.append(exemption)
            continue
        if fact is None:
            continue
        if exemption.target_sheet_code and exemption.target_sheet_code != fact.sheet_code:
            continue
        if exemption.target_sheet_name and (
            _normalized_sheet_name(exemption.target_sheet_name)
            != _normalized_sheet_name(fact.sheet_name)
        ):
            continue
        if not exemption.target_sheet_code and not exemption.target_sheet_name:
            continue
        matches.append(exemption)
    if len(matches) > 1:
        raise ValueError(f"{kind} exemption 对同一 context 命中多条")
    return matches[0] if matches else None


def _exemption_errors(
    exemption: RuntimeGuidanceExemption | None,
    *,
    now: datetime,
) -> tuple[str, ...]:
    if exemption is None:
        return ()
    errors: list[str] = []
    if not exemption.inherits_from:
        errors.append("exemption_missing_inherits_from")
    if not exemption.reason_code:
        errors.append("exemption_missing_reason")
    if not exemption.basis_refs:
        errors.append("exemption_missing_basis")
    if not exemption.approved_by or not exemption.approved_at:
        errors.append("exemption_missing_approval")
    elif _parse_instant(exemption.approved_at) is None:
        errors.append("exemption_invalid_approved_at")
    review_after = _parse_instant(exemption.review_after)
    if review_after is None:
        errors.append("exemption_invalid_review_after")
    elif review_after <= now:
        errors.append("exemption_expired")
    return tuple(errors)


def _resolution_policy_fact(
    parent_wp_code: str,
    exemption: RuntimeGuidanceExemption,
) -> GuidanceSourceFact:
    target = exemption.target_sheet_code or _normalized_sheet_name(exemption.target_sheet_name)
    return GuidanceSourceFact(
        kind="resolution_policy",
        ref=f"{parent_wp_code}:resolution_policy:{exemption.kind}:{target or 'whole_workbook'}",
        digest=stable_digest(asdict(exemption)),
        origin=exemption.kind,
    )


def _stable_entry_identity(
    *,
    parent_wp_code: str,
    sheet_code: str | None,
    sheet_name: str,
    context_kind: RuntimeContextKind,
) -> dict[str, str]:
    if context_kind == "whole_workbook":
        coordinate = "whole_workbook"
    elif sheet_code:
        coordinate = f"code:{sheet_code}"
    else:
        coordinate = f"name:{_normalized_sheet_name(sheet_name)}"
    return {
        "parent_wp_code": parent_wp_code,
        "context_kind": context_kind,
        "coordinate": coordinate,
    }


def _static_source_facts(static: GuidanceInventoryEntry) -> tuple[GuidanceSourceFact, ...]:
    validation_digest = static.source_ref_facts_digest or stable_digest(
        {
            "wp_code": static.wp_code,
            "source_ref_status": static.source_ref_status,
            "issues": list(static.source_ref_issues),
        }
    )
    return (
        GuidanceSourceFact(
            kind="static_guidance",
            ref=static.path,
            digest=static.source_digest,
            origin=static.parse_status,
        ),
        GuidanceSourceFact(
            kind="source_ref_validation",
            ref=f"{static.path}#source_refs",
            digest=validation_digest,
            origin=static.source_ref_status,
        ),
    )
