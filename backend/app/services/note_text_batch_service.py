"""附注正文批量导入 service — 章节读取、统一匹配与 preview。

spec: disclosure-note-doc-upload-and-batch-fill Phase 4 Task 21~25
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_models import DisclosureNote
from app.services.note_document_parser import ParsedSection
from app.services.note_html_sanitizer import sanitize_note_html
from app.services.note_quality_scanner import QualityFlag, scan_section_quality
from app.services.note_section_catalog import (
    build_variant_key,
    normalize_report_scope,
    normalize_template_type,
)
from app.services.note_section_matcher import match_section as alias_match
from app.services.note_variable_replacer import (
    ReplacementPlan,
    apply_replacement_plan,
    build_replacement_plan,
)

logger = logging.getLogger(__name__)

__all__ = [
    "load_target_sections",
    "match_sections",
    "build_preview",
    "MatchResult",
]

# ── 容量限制 ──────────────────────────────────────────────────────────────

_MAX_BATCH_SECTIONS = 500
_SECTION_BYTE_LIMIT = 512 * 1024


# ════════════════════════════════════════════════════════════════════════════
# Task 21：章节读取
# ════════════════════════════════════════════════════════════════════════════


async def load_target_sections(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    scope: str = "narrative",
    include_content: bool = False,
) -> list[dict[str, Any]]:
    """加载目标项目附注章节列表。

    scope:
      - "narrative": 只返回叙述性章节（排除 account_explanation 和 container）。
      - "all": 返回全部活动章节。

    include_content=False 时不返回 text_content（列表轻量化）。
    """
    cols = [
        DisclosureNote.id,
        DisclosureNote.section_id,
        DisclosureNote.note_section,
        DisclosureNote.section_title,
        DisclosureNote.level,
        DisclosureNote.parent_section_id,
        DisclosureNote.sort_index,
        DisclosureNote.content_type,
        DisclosureNote.status,
        DisclosureNote.is_stale,
        DisclosureNote.updated_at,
    ]
    if include_content:
        cols.append(DisclosureNote.text_content)

    stmt = (
        sa.select(*cols)
        .where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.is_deleted == sa.false(),
        )
        .order_by(DisclosureNote.sort_index)
    )

    result = await db.execute(stmt)
    rows = result.all()

    sections = []
    for row in rows:
        d = dict(row._mapping)
        # 计算 content_hash
        text = d.get("text_content") or ""
        d["content_hash"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if not include_content:
            d.pop("text_content", None)
        # TODO Task 9: section_kind 分类（目前简化）
        d["section_kind"] = _classify_section_kind(d)
        sections.append(d)

    if scope == "narrative":
        sections = [s for s in sections if s["section_kind"] == "narrative"]

    return sections


def _classify_section_kind(section: dict[str, Any]) -> str:
    """简化的章节类型分类。Task 9 会扩展为完整的 variant matrix 查询。"""
    # account_name 非空通常是报表科目解释
    if section.get("account_name"):
        return "account_explanation"
    # 有子节点且无正文的纯容器（简化判断：level=1 且无 text_content）
    # 完整实现需要查询子节点数量
    return "narrative"


# ════════════════════════════════════════════════════════════════════════════
# Task 22~23：统一匹配器
# ════════════════════════════════════════════════════════════════════════════


class MatchResult:
    __slots__ = ("source_id", "target_note_id", "match_kind", "evidence", "confidence")

    def __init__(
        self,
        source_id: str,
        target_note_id: UUID | None,
        match_kind: str,
        evidence: str,
        confidence: str,
    ):
        self.source_id = source_id
        self.target_note_id = target_note_id
        self.match_kind = match_kind
        self.evidence = evidence
        self.confidence = confidence


def match_sections(
    sources: list[ParsedSection],
    targets: list[dict[str, Any]],
    *,
    manual_mappings: dict[str, UUID] | None = None,
) -> list[MatchResult]:
    """统一章节匹配。

    优先级（design §4.2）：
    1. 手动映射（用户已确认）→ confirmed
    2. 同变体规范 note_section 精确匹配 → confirmed
    3. 显式 alias（note_section_matcher）→ confirmed
    4. 去空白后标题精确匹配 → candidate
    5. 其余 → manual_required
    """
    manual = manual_mappings or {}
    results: list[MatchResult] = []

    # 索引目标
    by_section: dict[str, dict] = {}
    by_title: dict[str, dict] = {}
    by_id: dict[UUID, dict] = {}
    for t in targets:
        ns = (t.get("note_section") or "").strip()
        if ns:
            by_section[ns] = t
        title = (t.get("section_title") or "").strip()
        if title:
            by_title.setdefault(_norm_title(title), t)
        by_id[t["id"]] = t

    used_targets: set[UUID] = set()

    for src in sources:
        # 1. 手动映射
        if src.source_id in manual:
            tid = manual[src.source_id]
            tgt = by_id.get(tid)
            if tgt and tid not in used_targets:
                used_targets.add(tid)
                results.append(MatchResult(
                    src.source_id, tid, "manual", "用户手动映射", "confirmed",
                ))
                continue

        # 2. 规范 note_section 精确
        src_title = (src.title or "").strip()
        tgt = by_section.get(src_title)
        if tgt and tgt["id"] not in used_targets:
            used_targets.add(tgt["id"])
            results.append(MatchResult(
                src.source_id, tgt["id"], "exact_section", f"note_section 精确匹配「{src_title}」", "confirmed",
            ))
            continue

        # 3. 显式 alias
        found_alias = False
        for t in targets:
            if t["id"] in used_targets:
                continue
            t_title = (t.get("section_title") or "").strip()
            if alias_match(src_title, t_title):
                used_targets.add(t["id"])
                results.append(MatchResult(
                    src.source_id, t["id"], "alias", f"显式别名匹配「{src_title}」↔「{t_title}」", "confirmed",
                ))
                found_alias = True
                break
        if found_alias:
            continue

        # 4. 标题精确（去空白后）
        norm = _norm_title(src_title)
        tgt = by_title.get(norm)
        if tgt and tgt["id"] not in used_targets:
            used_targets.add(tgt["id"])
            results.append(MatchResult(
                src.source_id, tgt["id"], "title_exact", f"标题精确匹配「{src_title}」", "candidate",
            ))
            continue

        # 5. 未匹配
        results.append(MatchResult(
            src.source_id, None, "unmatched", "未能自动匹配，需人工选择", "manual_required",
        ))

    return results


def _norm_title(title: str) -> str:
    """标题归一化（仅去空白，与 note_section_matcher 一致）。"""
    import unicodedata
    return "".join(c for c in title if not unicodedata.category(c).startswith("Z") and c not in " \t\r\n")


# ════════════════════════════════════════════════════════════════════════════
# Task 24~25：Preview service
# ════════════════════════════════════════════════════════════════════════════


class PreviewItem:
    __slots__ = (
        "source_id", "target_note_id", "target_note_section",
        "match_kind", "evidence", "confidence", "category",
        "unavailable_reason", "before_html", "proposed_html",
        "before_hash", "proposed_hash", "expected_updated_at",
        "default_mode", "quality_flags", "replacements",
    )

    def __init__(self, **kw: Any):
        for k, v in kw.items():
            setattr(self, k, v)


def build_preview(
    sources: list[ParsedSection],
    targets: list[dict[str, Any]],
    matches: list[MatchResult],
    *,
    target_vars: dict[str, Any] | None = None,
    source_entity_name: str | None = None,
) -> dict[str, Any]:
    """构建预览结果：消毒 + 变量替换 + 风险分类 + digest。"""
    target_vars = target_vars or {}
    items: list[dict[str, Any]] = []

    src_map = {s.source_id: s for s in sources}
    tgt_map = {str(t["id"]): t for t in targets}

    for m in matches:
        src = src_map.get(m.source_id)
        if not src:
            continue

        # 消毒来源 HTML
        sanitized_html = sanitize_note_html(src.html)

        # 变量替换
        plan = build_replacement_plan(
            sanitized_html,
            target_vars=target_vars,
            source_entity_name=source_entity_name,
        )
        proposed = apply_replacement_plan(sanitized_html, plan)

        # 目标现有内容
        before_html = ""
        before_hash = hashlib.sha256(b"").hexdigest()
        expected_updated_at = None
        target_section = None

        if m.target_note_id:
            tgt = tgt_map.get(str(m.target_note_id))
            if tgt:
                before_html = tgt.get("text_content") or ""
                before_hash = tgt.get("content_hash") or hashlib.sha256(before_html.encode()).hexdigest()
                expected_updated_at = tgt.get("updated_at")
                target_section = tgt.get("note_section")

        proposed_hash = hashlib.sha256(proposed.encode("utf-8")).hexdigest()

        # 质量扫描
        quality = scan_section_quality(
            text_content=proposed,
            section_kind=tgt.get("section_kind") if m.target_note_id and tgt else None,
            section_title=src.title,
            source_entity_name=source_entity_name,
        )

        # 风险分类
        category = _classify_preview_category(
            m, before_html, quality.flags, quality.is_high_risk,
        )

        # 默认模式
        default_mode = "replace"
        if before_html and category != "unavailable":
            default_mode = "replace"  # 已有内容默认替换

        replacements = [
            {
                "replacement_id": r.replacement_id,
                "variable": r.variable,
                "old_value": r.old_value,
                "new_value": r.new_value,
                "reversible": r.reversible,
            }
            for r in plan.items
        ]

        items.append({
            "source_id": m.source_id,
            "target_note_id": str(m.target_note_id) if m.target_note_id else None,
            "target_note_section": target_section,
            "match_kind": m.match_kind,
            "evidence": m.evidence,
            "confidence": m.confidence,
            "category": category,
            "unavailable_reason": _unavailable_reason(m, quality.flags),
            "before_html": before_html,
            "proposed_html": proposed,
            "before_hash": before_hash,
            "proposed_hash": proposed_hash,
            "expected_updated_at": str(expected_updated_at) if expected_updated_at else None,
            "default_mode": default_mode,
            "quality_flags": quality.flags,
            "replacements": replacements,
        })

    # 统计
    summary = {
        "total": len(items),
        "recommended": sum(1 for i in items if i["category"] == "recommended"),
        "review": sum(1 for i in items if i["category"] == "review"),
        "unavailable": sum(1 for i in items if i["category"] == "unavailable"),
        "new": sum(1 for i in items if not i["before_html"] and i["category"] == "recommended"),
        "replace": sum(1 for i in items if i["before_html"] and i["category"] in ("recommended", "review")),
    }

    # Digest
    canonical = json.dumps(
        [{"sid": i["source_id"], "tid": i["target_note_id"], "ph": i["proposed_hash"]} for i in items],
        sort_keys=True,
    )
    preview_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    return {
        "preview_digest": preview_digest,
        "items": items,
        "summary": summary,
        "warnings": [],
    }


def _classify_preview_category(
    match: MatchResult,
    before_html: str,
    quality_flags: list[str],
    is_high_risk: bool,
) -> str:
    """按 design §8.2 风险分级。"""
    if match.confidence == "manual_required" or match.target_note_id is None:
        return "unavailable"

    if is_high_risk:
        return "review"
    if before_html:
        return "review"
    if QualityFlag.DRAFT in quality_flags or QualityFlag.STALE in quality_flags:
        return "review"

    return "recommended"


def _unavailable_reason(match: MatchResult, quality_flags: list[str]) -> str | None:
    if match.target_note_id is None:
        return "未找到匹配的目标章节"
    if match.confidence == "manual_required":
        return "需手动选择目标章节"
    if QualityFlag.EMPTY in quality_flags:
        return "来源正文为空"
    return None
