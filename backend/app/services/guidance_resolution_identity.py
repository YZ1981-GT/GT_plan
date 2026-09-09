"""Guidance authoritative resolution 的 identity / provenance / verdict 契约。

Task 8 的核心是把 resolution 从「散落在 _build_response 的字符串字段」提升为
显式 dataclass，前端不再靠文案猜状态。

对齐 spec design.md §7：
    GuidanceResponse {
      contractVersion, schemaVersion,
      subject, requestedIdentity, resolvedIdentity,
      inherited, provenance, resolutionStatus, completionStatus,
      resolutionReasons, sections, missingSections,
      version, sourceDigest, inventoryDigest, generatedAt
    }

🔴 判据：
    * membership fail-closed：requested.identity wp/sheet 不匹配 authority 时
      抛 GuidanceMembershipError，route 层映射 403，不泄漏内容
    * legacy static candidate 不判 exact：source="static_json" 但 publication
      缺失时 resolutionStatus="review_candidate"，不是 "exact"
    * resolutionReasons 是 list[str]，不是单字符串；前端可迭代渲染
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# 契约版本：wire 层主版本号，minor 兼容由 minor 字段承载
GUIDANCE_CONTRACT_VERSION = "1.0"

# Schema 版本：Resolution Response 的 schema 版本（不随内容变）
GUIDANCE_RESOLUTION_SCHEMA_VERSION = "guidance-resolution-v1"

ResolutionStatus = Literal[
    "exact",           # child exact（active publication 或 durable custom-confirmed ACK）
    "review_candidate",  # legacy static JSON 尚未 publication；只作候选，不判 exact
    "parent_inherited",  # 走 parent chain（整册或 child miss→parent）
    "typed_fallback",    # parent chain 命中 typed fallback
    "generic_fallback",  # parent chain 命中 generic fallback
    "missing",           # 缺九段但已发布
    "invalid",           # runtime contract invalid（source_ref 校验失败）
    "stale",             # runtime contract stale
]

CompletionStatus = Literal["complete", "partial", "blocked"]


@dataclass(frozen=True)
class ResolutionIdentity:
    """请求/解析出的 identity 三元组。"""

    wp_code: str
    sheet_code: str | None = None
    sheet_uid: str | None = None
    lineage_id: str | None = None
    template_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "wp_code": self.wp_code,
            "sheet_code": self.sheet_code,
            "sheet_uid": self.sheet_uid,
            "lineage_id": self.lineage_id,
            "template_version": self.template_version,
        }


@dataclass(frozen=True)
class ProvenanceSource:
    """单个来源的信息：primary / overlay / extraction。"""

    kind: Literal["primary", "overlay", "extraction"]
    source: str  # GuidanceResult.source：static_json / template_sheet / typed_fallback / fallback
    path: str | None = None
    digest: str | None = None


@dataclass(frozen=True)
class ResolutionProvenance:
    """来源集合：primary 是最终展示的主源，overlays 是叠加层，extraction 是 raw 抽取。"""

    primary: ProvenanceSource
    overlays: list[ProvenanceSource] = field(default_factory=list)
    extraction: list[ProvenanceSource] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        def _d(p: ProvenanceSource) -> dict[str, Any]:
            return {"kind": p.kind, "source": p.source, "path": p.path, "digest": p.digest}
        return {
            "primary": _d(self.primary),
            "overlays": [_d(x) for x in self.overlays],
            "extraction": [_d(x) for x in self.extraction],
        }


class GuidanceMembershipError(Exception):
    """跨 wp/sheet membership fail-closed。

    服务端判定 requested identity 不属于当前 authority 时抛出；route 映射 403。
    本异常**不得**在 message 里带任何 authority 内容（避免泄漏）。
    """


@dataclass
class ResolutionVerdict:
    """解析裁决：status + reasons（列表，非单串）。"""

    status: ResolutionStatus
    reasons: list[str] = field(default_factory=list)
    completion: CompletionStatus = "partial"
    blockers: list[str] = field(default_factory=list)
    missing_sections: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "resolution_status": self.status,
            "resolution_reasons": list(self.reasons),
            "completion_status": self.completion,
            "exact_blockers": list(self.blockers),
            "missing_sections": list(self.missing_sections),
        }
