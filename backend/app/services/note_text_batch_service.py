"""附注正文批量导入 service — 章节读取、统一匹配、手工映射校验与 preview。

spec: disclosure-note-doc-upload-and-batch-fill Phase 4 Task 21~25
（第二轮复盘 R-07 / R-08 / R-16 / R-25 / R-26 修订）

匹配裁定（design §4.2 / AC-3.1~3.5）：
- 只有「手工映射 / 同模板同编号同标题 / variant matrix / soe↔listed 显式别名（模板来源）」产生 confirmed；
- 外部来源（上传 / 知识库）的标题规范化精确匹配**只产生 candidate**（AC-3.3），需人工确认；
- 同名目标不唯一时按「章路径」消歧，仍不唯一 ⇒ manual_required；
- 多个来源指向同一目标 ⇒ 全部 manual_required，不先到先得（AC-3.4）；
- 禁止对（``FORBIDDEN_MATCH_PAIRS``）永不产生候选。
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from html import escape
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.core import Project
from app.models.report_models import DisclosureNote
from app.services.note_document_parser import ParsedSection
from app.services.note_html_sanitizer import (
    append_note_html,
    has_visible_text,
    note_text_to_html,
    sanitize_note_html,
)
from app.services.note_quality_scanner import QualityFlag, scan_section_quality
from app.services.note_section_catalog import (
    DATA_DIR,
    normalize_report_scope,
    normalize_section_code,
    normalize_template_type,
    section_allowed_for_project,
)
from app.services.note_section_kind import (
    canonical_title,
    chapter_title_for_code,
    classify_note_section,
    is_account_chapter_title,
    normalize_title,
)
from app.services.note_section_matcher import FORBIDDEN_MATCH_PAIRS, SECTION_TITLE_ALIASES
from app.services.note_variable_replacer import apply_replacement_plan, build_replacement_plan

logger = logging.getLogger(__name__)

__all__ = [
    "ManualMappingError",
    "MatchResult",
    "SourceContext",
    "build_preview",
    "fold_unmatched_descendants",
    "load_target_sections",
    "match_sections",
    "sha256_text",
    "validate_manual_mappings",
]


def sha256_text(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


@dataclass(frozen=True)
class SourceContext:
    """来源上下文：模板来源需带其标准/口径，供同模板编号与 variant matrix 匹配。"""

    kind: str = "upload"  # upload | knowledge | content_template
    template_type: str | None = None
    report_scope: str | None = None


# ════════════════════════════════════════════════════════════════════════════
# Task 21：章节读取（R-16：类型按 Word 权威判定；content_hash 恒基于真实正文）
# ════════════════════════════════════════════════════════════════════════════


def _table_payload_expr(dialect_name: str) -> sa.ColumnElement[bool]:
    """SQL 侧「承载表格」= ``table_data`` 是非空 JSON 对象；与 :func:`has_table_payload` 同口径（守卫逐值对拍）。

    🔴 首版写 ``table_data IS NOT NULL``：JSON ``null`` 也算「有表」⇒ 真库每行 has_body 恒真、container 永不成立；
    SQLite 夹具从不写该列（SQL NULL）⇒ 假绿（第 17 组真实写入验收发现）。只取类型判定，不把表格内容拉回 Python。
    """
    column = DisclosureNote.table_data
    type_of = sa.func.jsonb_typeof(column) if dialect_name == "postgresql" else sa.func.json_type(column)
    return sa.and_(type_of == "object", sa.cast(column, sa.Text) != "{}")


async def load_target_sections(
    db: AsyncSession,
    project_id: UUID,
    year: int,
    *,
    scope: str = "narrative",
    include_content: bool = False,
) -> list[dict[str, Any]]:
    """加载目标项目附注章节。

    - ``scope="narrative"``：只返回叙述性叶子章节；``"all"``：三类全返回；
    - 正文**总是**参与 ``content_hash`` / ``has_content`` 计算，``include_content=False`` 仅不下发正文；
    - 口径不适用（``section_allowed_for_project``）与软删除章节排除。
    """
    project = await db.get(Project, project_id)
    raw_tt = getattr(project, "template_type", None)
    raw_rs = getattr(project, "report_scope", None)
    rows = (await db.execute(
        sa.select(
            DisclosureNote.id, DisclosureNote.section_id, DisclosureNote.note_section,
            DisclosureNote.section_title, DisclosureNote.level, DisclosureNote.parent_section_id,
            DisclosureNote.sort_index, DisclosureNote.content_type, DisclosureNote.status,
            DisclosureNote.is_stale, DisclosureNote.updated_at, DisclosureNote.text_content,
            _table_payload_expr(db.get_bind().dialect.name).label("has_table"),
        )
        .where(
            DisclosureNote.project_id == project_id,
            DisclosureNote.year == year,
            DisclosureNote.is_deleted == sa.false(),
        )
        # 全文顺序 = sort_order（生成链 / 导出 / 编辑器同口径）；sort_index 是 V019「同层级内序号」，只作并列时的次序
        .order_by(DisclosureNote.sort_order.asc().nulls_last(), DisclosureNote.sort_index, DisclosureNote.note_section)
    )).all()

    parents = {r.parent_section_id for r in rows if r.parent_section_id}
    sections: list[dict[str, Any]] = []
    for r in rows:
        if not section_allowed_for_project(r.note_section, raw_tt, raw_rs):
            continue
        text = r.text_content or ""
        has_content = has_visible_text(text)
        kind = classify_note_section(
            r.note_section, raw_tt, raw_rs,
            section_title=r.section_title,
            has_children=bool(r.section_id) and r.section_id in parents,
            has_body=has_content or bool(r.has_table),
        )
        if scope == "narrative" and kind != "narrative":
            continue
        item = {
            "id": r.id, "section_id": r.section_id, "note_section": r.note_section,
            "section_title": r.section_title, "level": r.level,
            "parent_section_id": r.parent_section_id, "sort_index": r.sort_index,
            "content_type": _enum_value(r.content_type), "status": _enum_value(r.status),
            "is_stale": bool(r.is_stale), "updated_at": r.updated_at,
            "content_hash": sha256_text(text), "has_content": has_content,
            "section_kind": kind, "chapter_title": chapter_title_for_code(r.note_section, raw_tt),
        }
        if include_content:
            item["text_content"] = text
        sections.append(item)
    return sections


async def resolve_target_context(db: AsyncSession, project_id: UUID) -> tuple[str, str]:
    """目标项目 (template_type, report_scope)，均已归一。"""
    project = await db.get(Project, project_id)
    return (
        normalize_template_type(getattr(project, "template_type", None)),
        normalize_report_scope(getattr(project, "report_scope", None)),
    )


# ════════════════════════════════════════════════════════════════════════════
# Task 22~23：统一匹配器 + 手工映射校验
# ════════════════════════════════════════════════════════════════════════════


class MatchResult:
    __slots__ = ("source_id", "target_note_id", "match_kind", "evidence", "confidence")

    def __init__(self, source_id: str, target_note_id: UUID | None, match_kind: str,
                 evidence: str, confidence: str):
        self.source_id = source_id
        self.target_note_id = target_note_id
        self.match_kind = match_kind
        self.evidence = evidence
        self.confidence = confidence


class ManualMappingError(ValueError):
    """手工映射非法（端点转 422）。"""


def _pairs(raw: list[tuple[str, str]]) -> frozenset[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for a, b in raw:
        ka, kb = normalize_title(a), normalize_title(b)
        out.update({(ka, kb), (kb, ka)})
    return frozenset(out)


_FORBIDDEN_TITLES = _pairs([(a, b) for a, b, _reason in FORBIDDEN_MATCH_PAIRS])
_ALIAS_TITLES = _pairs([(p.soe_title, p.listed_title) for p in SECTION_TITLE_ALIASES])


def _is_forbidden(a: str | None, b: str | None) -> bool:
    return (normalize_title(a), normalize_title(b)) in _FORBIDDEN_TITLES


def _index_variant_matrix(
    matrix: dict[str, Any],
) -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], frozenset[str]]]:
    """((template_type, 章节号) → account_key, (account_key, template_type) → 章节号集合)。"""
    by_code: dict[tuple[str, str], str] = {}
    codes: dict[tuple[str, str], set[str]] = {}
    for account in matrix.get("accounts") or []:
        key = account.get("account_key")
        if not key:
            continue
        # 逐对展开：同一变体可有多个旧码（建成 {变体: 码} 字典会只剩最后一个）
        pairs = list((account.get("variants") or {}).items()) + [
            (variant, code) for variant, olds in (account.get("legacy_aliases") or {}).items() for code in olds
        ]
        for variant, code in pairs:
            if isinstance(code, str) and code.strip():
                tt = variant.split("_", 1)[0]
                by_code.setdefault((tt, code.strip()), key)
                codes.setdefault((key, tt), set()).add(code.strip())
    return by_code, {k: frozenset(v) for k, v in codes.items()}


@lru_cache(maxsize=1)
def _matrix_index() -> tuple[dict[tuple[str, str], str], dict[tuple[str, str], frozenset[str]]]:
    return _index_variant_matrix(
        json.loads((DATA_DIR / "note_template_variant_matrix.json").read_text(encoding="utf-8")))


def validate_manual_mappings(
    sources: list[ParsedSection],
    targets: list[dict[str, Any]],
    manual_mappings: dict[str, UUID],
) -> None:
    """来源存在、目标在本次可写范围（本项目且 scope 内）、一对一、非禁止对；否则抛错。"""
    src_by_id = {s.source_id: s for s in sources}
    tgt_by_id = {t["id"]: t for t in targets}
    seen: dict[UUID, str] = {}
    for source_id, target_id in manual_mappings.items():
        src = src_by_id.get(source_id)
        if src is None:
            raise ManualMappingError(f"来源章节不存在：{source_id}")
        tgt = tgt_by_id.get(target_id)
        if tgt is None:
            raise ManualMappingError("目标章节不在可写范围（非本项目、已删除或不属于本次可填章节类型）")
        if target_id in seen:
            raise ManualMappingError(f"同一目标章节只能接受一个来源：{tgt['note_section']}")
        if _is_forbidden(src.title, tgt.get("section_title")):
            raise ManualMappingError(f"禁止匹配对不可强行映射：「{src.title}」↔「{tgt.get('section_title')}」")
        seen[target_id] = source_id


def _source_chapters(sources: list[ParsedSection]) -> dict[str, str | None]:
    """每个来源章节所在的顶层章标题（祖先链顶端）；顶层来源无祖先 ⇒ None。"""
    out: dict[str, str | None] = {}
    stack: list[ParsedSection] = []
    doc = _NO_DOC
    for src in sources:
        if _doc_of(src) != doc:  # 知识库多篇文档拼接：层级栈不得跨文档
            stack, doc = [], _doc_of(src)
        while stack and stack[-1].level >= src.level:
            stack.pop()
        out[src.source_id] = stack[0].title if stack else None
        stack.append(src)
    return out


_NO_DOC = object()


def _doc_of(src: ParsedSection) -> Any:
    return (src.metadata or {}).get("doc_id")


def _source_is_account(src: ParsedSection, chapter: str | None) -> bool | None:
    """来源是否属报表科目注释；无法判断返回 None（不门控）。

    - 模板来源：用快照里的 ``section_kind``；
    - 有祖先：看所在顶层章标题是否为「项目注释 / 项目附注」；
    - 顶层来源：自身就是科目注释章标题 ⇒ True，否则未知（扁平文档的顶层标题也可能是节）。
    """
    meta_kind = (src.metadata or {}).get("section_kind")
    if meta_kind in ("narrative", "account_explanation"):
        return meta_kind == "account_explanation"
    if chapter is not None:
        return is_account_chapter_title(chapter)
    return True if is_account_chapter_title(src.title) else None


def _kind_compatible(target: dict, source_account: bool | None) -> bool:
    return source_account is None or (target.get("section_kind") == "account_explanation") == source_account


def _propose_by_code(src: ParsedSection, available: list[dict], ctx: SourceContext,
                     target_tt: str) -> tuple[dict, str, str, str] | None:
    """模板来源：同模板同编号 / 跨模板 variant matrix。"""
    raw_code = (src.metadata or {}).get("note_section")
    if ctx.kind != "content_template" or not raw_code:
        return None
    src_tt = normalize_template_type(ctx.template_type)
    src_code = normalize_section_code(raw_code, template_type=src_tt)
    if src_tt == target_tt:
        hits = [t for t in available
                if normalize_section_code(t["note_section"], template_type=target_tt) == src_code]
        if len(hits) != 1:
            return None
        same = canonical_title(hits[0].get("section_title")) == canonical_title(src.title)
        return (hits[0], "same_template_code", f"同模板章节编号「{src_code}」"
                + ("且标题一致" if same else "一致但标题不同"), "confirmed" if same else "candidate")
    by_code, codes = _matrix_index()
    account = by_code.get((src_tt, src_code)) or by_code.get((src_tt, raw_code.strip()))
    if not account:
        return None
    wanted = codes.get((account, target_tt), frozenset())
    hits = [t for t in available if t["note_section"] in wanted
            or normalize_section_code(t["note_section"], template_type=target_tt) in wanted]
    if len(hits) != 1:
        return None
    return (hits[0], "variant_matrix", f"科目映射矩阵「{account}」：{src_code}→{hits[0]['note_section']}", "confirmed")


def _propose_by_title(src: ParsedSection, available: list[dict], chapter: str | None,
                      ctx: SourceContext) -> tuple[dict | None, str, str, str]:
    key = canonical_title(src.title)
    if not key:
        return None, "unmatched", "来源标题为空", "manual_required"
    exact = [t for t in available if canonical_title(t.get("section_title")) == key]
    alias = [t for t in available if t not in exact
             and (key, canonical_title(t.get("section_title"))) in _ALIAS_TITLES]
    hits = [t for t in exact + alias if not _is_forbidden(src.title, t.get("section_title"))]
    if not hits:
        return None, "unmatched", "未找到匹配的目标章节", "manual_required"
    if len(hits) > 1 and chapter:
        path_hits = [t for t in hits if canonical_title(t.get("chapter_title")) == canonical_title(chapter)]
        if len(path_hits) == 1:
            return path_hits[0], "title_path", f"章路径「{chapter} / {src.title}」唯一命中", "candidate"
    if len(hits) > 1:
        return None, "ambiguous", f"存在 {len(hits)} 个同名目标章节，需人工选择", "manual_required"
    hit = hits[0]
    if hit in alias:
        confidence = "confirmed" if ctx.kind == "content_template" else "candidate"
        return hit, "alias", f"显式别名「{src.title}」↔「{hit.get('section_title')}」", confidence
    return hit, "title_exact", f"标题规范化一致「{src.title}」", "candidate"


def match_sections(
    sources: list[ParsedSection],
    targets: list[dict[str, Any]],
    *,
    manual_mappings: dict[str, UUID] | None = None,
    source_context: SourceContext | None = None,
    target_template_type: str | None = None,
) -> list[MatchResult]:
    """统一章节匹配（规则见模块说明）；``manual_mappings`` 须先经 :func:`validate_manual_mappings`。"""
    ctx = source_context or SourceContext()
    target_tt = normalize_template_type(target_template_type)
    manual = manual_mappings or {}
    tgt_by_id = {t["id"]: t for t in targets}
    reserved = {tid for tid in manual.values() if tid in tgt_by_id}
    available = [t for t in targets if t["id"] not in reserved]
    chapters = _source_chapters(sources)

    proposals: dict[str, tuple[dict | None, str, str, str]] = {}
    for src in sources:
        if src.source_id in manual:
            continue
        chapter = chapters.get(src.source_id)
        source_account = _source_is_account(src, chapter)
        # 章类型门控：Word 中「存货」等同时出现在会计政策章与项目注释章，不门控则两者争抢同一叙述目标
        if targets and not any(_kind_compatible(t, source_account) for t in targets):
            proposals[src.source_id] = (
                None, "out_of_scope",
                "来源属报表科目注释章节，本次只填叙述性章节" if source_account
                else "来源属叙述性章节，本次目标仅含报表科目注释", "manual_required",
            )
            continue
        eligible = [t for t in available if _kind_compatible(t, source_account)]
        proposals[src.source_id] = (
            _propose_by_code(src, eligible, ctx, target_tt)
            or _propose_by_title(src, eligible, chapter, ctx)
        )

    claims: dict[UUID, list[str]] = {}
    for source_id, (tgt, *_rest) in proposals.items():
        if tgt is not None:
            claims.setdefault(tgt["id"], []).append(source_id)

    results: list[MatchResult] = []
    for src in sources:
        tid = manual.get(src.source_id)
        if src.source_id in manual:
            ok = tid in tgt_by_id
            results.append(MatchResult(src.source_id, tid if ok else None, "manual" if ok else "unmatched",
                                       "用户手工映射" if ok else "手工映射目标不可用", "confirmed" if ok else "manual_required"))
            continue
        tgt, kind, evidence, confidence = proposals[src.source_id]
        if tgt is not None and len(claims[tgt["id"]]) > 1:
            results.append(MatchResult(src.source_id, None, "conflict",
                                       f"{len(claims[tgt['id']])} 个来源章节指向同一目标「{tgt['note_section']}」，需人工确认",
                                       "manual_required"))
            continue
        results.append(MatchResult(src.source_id, tgt["id"] if tgt else None, kind, evidence, confidence))
    return results


def fold_unmatched_descendants(
    sources: list[ParsedSection],
    matches: list[MatchResult],
) -> tuple[list[ParsedSection], list[MatchResult]]:
    """R-25：未匹配（``unmatched``）的后代标题并入最近的已匹配祖先，标题转加粗段落。

    国企 Word 的节是 H3、上市是 H2（其 H3 为节内小标题）；按标题切节时子标题会成为孤立来源，
    不并入则其正文丢失。``conflict`` / ``ambiguous`` 不并入（需用户人工选择）。
    """
    by_id = {m.source_id: m for m in matches}
    html: dict[str, str] = {s.source_id: s.html for s in sources}
    folded: dict[str, str] = {}
    stack: list[tuple[int, str | None]] = []  # (level, 内容归属的来源 ID)
    doc = _NO_DOC
    for src in sources:
        if _doc_of(src) != doc:  # 不把下一篇文档的开头并进上一篇的末节
            stack, doc = [], _doc_of(src)
        while stack and stack[-1][0] >= src.level:
            stack.pop()
        match = by_id.get(src.source_id)
        owner: str | None = None
        if match is not None and match.target_note_id is not None:
            owner = src.source_id
        elif match is not None and match.match_kind == "unmatched" and stack and stack[-1][1]:
            owner = stack[-1][1]
            html[owner] += f"<p><strong>{escape(src.title)}</strong></p>{src.html}"
            folded[src.source_id] = owner
        stack.append((src.level, owner))
    title_of = {s.source_id: s.title for s in sources}
    new_sources = [dataclasses.replace(s, html=html[s.source_id]) if html[s.source_id] != s.html else s
                   for s in sources]
    new_matches = [
        MatchResult(m.source_id, None, "folded", f"已并入上级「{title_of[folded[m.source_id]]}」", "manual_required")
        if m.source_id in folded else m
        for m in matches
    ]
    return new_sources, new_matches


# ════════════════════════════════════════════════════════════════════════════
# Task 24~25：Preview
# ════════════════════════════════════════════════════════════════════════════

#: design §8.2 quality_warning：源章 draft/stale/占位文本/疑似来源实体、日期、金额 ⇒ 需复核
_HIGH_RISK_REVIEW_FLAGS = frozenset({
    QualityFlag.DRAFT, QualityFlag.STALE, QualityFlag.PLACEHOLDER, QualityFlag.SOURCE_ENTITY,
    QualityFlag.DATE, QualityFlag.AMOUNT,
})
_UNAVAILABLE_REASONS = {
    "conflict": None,  # 用 evidence 原文
    "ambiguous": None,
    "unmatched": "未找到匹配的目标章节",
}


def build_preview(
    sources: list[ParsedSection],
    targets: list[dict[str, Any]],
    matches: list[MatchResult],
    *,
    target_vars: dict[str, Any] | None = None,
    source_entity_name: str | None = None,
    revoked_replacement_ids: set[str] | frozenset[str] | None = None,
    source_context: SourceContext | None = None,
    target_template_type: str | None = None,
    target_report_scope: str | None = None,
    source_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """预览：消毒 → 确定性变量替换（可撤销）→ 再消毒 → 追加结果预演 → 质量/风险分级 → digest。

    ``targets`` 必须带 ``text_content``（``load_target_sections(include_content=True)``）。
    digest 绑定：来源身份 + 逐章 (source_id, target_note_id, proposed_hash)；目标现状由 apply 逐章复核。
    """
    ctx = source_context or SourceContext()
    revoked = set(revoked_replacement_ids or ())
    cross_standard = ctx.kind == "content_template" and (
        normalize_template_type(ctx.template_type), normalize_report_scope(ctx.report_scope)
    ) != (normalize_template_type(target_template_type), normalize_report_scope(target_report_scope))
    src_map = {s.source_id: s for s in sources}
    tgt_map = {t["id"]: t for t in targets}
    items: list[dict[str, Any]] = []

    skipped = {"folded": 0, "out_of_scope": 0}
    # 左栏逐来源显示跳过原因（AC-2.2）：只给计数时分不清「被跳过」与「没匹配上」；只供展示，不进 digest
    skipped_sources: list[dict[str, str]] = []
    for m in matches:
        src = src_map.get(m.source_id)
        if src is None:
            continue
        if m.match_kind in skipped:
            skipped[m.match_kind] += 1  # 已并入上级 / 不在本次可填范围：不进预览
            skipped_sources.append({"source_id": m.source_id, "match_kind": m.match_kind})
            continue
        meta = src.metadata or {}
        # 纯文字来源（模板快照里多数章节是生成链写入的纯文字）按编辑器口径转 HTML：否则写入后分段并成一段（第 19 组）
        sanitized = note_text_to_html(src.html)
        plan = build_replacement_plan(sanitized, target_vars=target_vars or {},
                                      source_entity_name=source_entity_name, scope=src.source_id)
        proposed = sanitize_note_html(apply_replacement_plan(sanitized, plan, revoked_ids=revoked))
        tgt = tgt_map.get(m.target_note_id) if m.target_note_id else None
        before = (tgt.get("text_content") or "") if tgt else ""
        before_hash = sha256_text(before) if tgt and "text_content" in tgt else (
            tgt.get("content_hash") if tgt else sha256_text(""))
        has_before = has_visible_text(before)
        append_html = append_note_html(before, proposed) if tgt and has_before else None

        quality = scan_section_quality(
            text_content=proposed, status=meta.get("status"), is_stale=bool(meta.get("is_stale")),
            section_kind=(tgt or {}).get("section_kind") or meta.get("section_kind"),
            section_title=src.title, source_entity_name=source_entity_name,
        )
        flags = list(quality.flags) + (["cross_standard"] if cross_standard and tgt else [])
        if tgt is None:
            category = "unavailable"
            reason = _UNAVAILABLE_REASONS.get(m.match_kind) or m.evidence
        elif not has_visible_text(proposed):
            category, reason = "unavailable", "来源正文为空"
        elif (m.confidence != "confirmed" or has_before or quality.is_high_risk or cross_standard
              or _HIGH_RISK_REVIEW_FLAGS & set(quality.flags)):
            category, reason = "review", None
        else:
            category, reason = "recommended", None
        items.append({
            "source_id": m.source_id, "source_title": src.title,
            "target_note_id": str(m.target_note_id) if tgt else None,
            "target_note_section": (tgt or {}).get("note_section"),
            "target_section_title": (tgt or {}).get("section_title"),
            # 右栏按目标所属一级章分组（AC-2.3）；只供展示，不进 digest
            "target_chapter_title": (tgt or {}).get("chapter_title"),
            "match_kind": m.match_kind, "evidence": m.evidence, "confidence": m.confidence,
            "category": category, "default_selected": category == "recommended",
            "unavailable_reason": reason,
            # 差异预览「现有内容」按编辑器口径显示（纯文字原样塞进 v-html 会并成一段）；复核仍按原文 hash
            "before_html": note_text_to_html(before), "before_hash": before_hash,
            "proposed_html": proposed, "proposed_hash": sha256_text(proposed),
            "append_html": append_html, "append_hash": sha256_text(append_html) if append_html is not None else None,
            "expected_updated_at": str(tgt["updated_at"]) if tgt and tgt.get("updated_at") else None,
            "default_mode": "replace", "quality_flags": flags,
            "replacements": [
                {"replacement_id": r.replacement_id, "variable": r.variable, "old_value": r.old_value,
                 "new_value": r.new_value, "reversible": r.reversible, "revoked": r.replacement_id in revoked}
                for r in plan.items
            ],
        })

    summary = {
        "total": len(items),
        "recommended": sum(i["category"] == "recommended" for i in items),
        "review": sum(i["category"] == "review" for i in items),
        "unavailable": sum(i["category"] == "unavailable" for i in items),
        "new": sum(i["category"] != "unavailable" and i["append_html"] is None for i in items),
        "replace": sum(i["category"] != "unavailable" and i["append_html"] is not None for i in items),
        "high_risk": sum(bool(set(i["quality_flags"]) & {"source_entity", "entity_specific",
                                                          "account_explanation", "cross_standard"}) for i in items),
        **skipped,
    }
    # digest 只绑「预览输入」：来源身份 + 映射 + 拟写入内容。目标现状不进 digest ——
    # 所选目标由 apply 逐章 before_hash 复核（409 并列出冲突章节，设计 §7.2-4 / §7.3），
    # 未勾选目标被他人修改不应让整批报「摘要不一致」。append 结果依赖现状，由 append_hash 单独复核。
    canonical = json.dumps({
        "source": source_identity or {},
        "items": [[i["source_id"], i["target_note_id"], i["proposed_hash"]] for i in items],
    }, sort_keys=True, ensure_ascii=False, default=str)
    return {"preview_digest": sha256_text(canonical), "items": items, "skipped_sources": skipped_sources,
            "summary": summary, "warnings": []}
