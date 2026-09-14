"""Guidance completion 判定守卫（Task 6 / G0.5）

🔴 铁律：supplement 不得「补齐」canonical 缺失段后推 complete。

canonical section presence 的判据：
    * 只有 published 且 active 的 guidance_publication 的 section 才算 canonical 已齐
    * project_guidance_supplement 的内容可以「叠加覆盖展示层」，但不能把 canonical
      缺失的 section 算作已覆盖 —— 判据是 `_canonical_section_presence()`
    * exemption 只让某些 subject 免于「必需覆盖」，不代表该 section 已齐

🔴 判据（mutation 必须能抓）：
    * M-COMP-CANON：把 `_canonical_section_presence()` 改成读 supplement 也计入 → 红
    * M-COMP-EXPIRY：豁免过期仍算覆盖 → 红
    * M-COMP-STAT：把 `_status_ok()` 删除 → draft/reviewed 也算 canonical → 红

不在本模块：
    * 具体 section 数量判定 —— 由调用方传入 `required_sections`
"""

from __future__ import annotations

from typing import Iterable

from app.models.guidance_publication_models import (
    GuidanceExemptionRecord,
    GuidancePublication,
    ProjectGuidanceSupplement,
    PUBLICATION_PUBLISHED,
)

__all__ = [
    "is_canonical_complete",
    "canonical_missing_sections",
    "canonical_covered_sections",
    "_canonical_section_presence",
    "_status_ok",
]


def _status_ok(pub: GuidancePublication) -> bool:
    """published + active 才计入 canonical 覆盖。"""
    if pub.status != PUBLICATION_PUBLISHED:
        return False
    if not pub.is_active:
        return False
    return True


def _canonical_section_presence(
    publication: GuidancePublication | None,
) -> set[str]:
    """从 published+active 的 canonical 里提取已覆盖 section。

    🔴 只读 canonical，不读 supplement —— supplement 是展示层叠加，不能算 canonical 齐。
    """
    if publication is None:
        return set()
    if not _status_ok(publication):
        return set()
    return set(publication.content_json.keys()) if isinstance(publication.content_json, dict) else set()


def canonical_covered_sections(
    publications: Iterable[GuidancePublication],
    *,
    exemptions: Iterable[GuidanceExemptionRecord] = (),
) -> set[str]:
    """给定一批 publication + 有效豁免，返回 canonical 覆盖的 section 集合。

    exemptions 不直接扩张 canonical 覆盖集合，只让特定 subject 免于「必须覆盖」。
    调用方应把 exemptions 用于「豁免判定」而非「覆盖集合扩张」—— 本函数不消费它
    是有意设计（防止 M-COMP-EXPIRY 变异：过期豁免仍算覆盖）。
    """
    covered: set[str] = set()
    for pub in publications:
        if _status_ok(pub):
            covered |= _canonical_section_presence(pub)
    return covered


def canonical_missing_sections(
    publications: Iterable[GuidancePublication],
    *,
    required_sections: Iterable[str],
) -> set[str]:
    """canonical 缺失段 = required - covered。supplement 不计入 covered。"""
    covered = canonical_covered_sections(publications)
    return set(required_sections) - covered


def is_canonical_complete(
    publications: Iterable[GuidancePublication],
    *,
    required_sections: Iterable[str],
    exempt_sections: Iterable[str] = (),
) -> bool:
    """canonical 是否已齐：required - (covered ∪ exempted) == ∅。

    exempt_sections 由调用方根据 exemptions 计算，本函数不消费 exemption 记录本身
    （避免过期豁免被误算，M-COMP-EXPIRY 判据）。
    """
    pubs = list(publications)
    missing = canonical_missing_sections(pubs, required_sections=set(required_sections))
    return not (missing - set(exempt_sections))
