"""附注正文批量导入 service — 章节读取、统一匹配、手工映射校验与 preview。

spec: disclosure-note-doc-upload-and-batch-fill Phase 4 Task 21~25
（第二轮复盘 R-07 / R-08 / R-16 / R-25 / R-26 修订）

匹配裁定（design §4.2 / AC-3.1~3.9）：
- 上传 / 知识库按章节树逐级定位（第 23 组，``note_section_tree_locator``）：先定位一级章，再只在已定位章内
  定位其下小标题；定位不上一律交给用户手工对应，不到别处按标题找。标题定位只产生 candidate（AC-3.3）；
- 内容模板：「手工映射 / 同模板同编号同标题 / variant matrix / soe↔listed 显式别名」产生 confirmed；
  同模板编号对不上时只在同一章内按标题找；
- 多个来源指向同一目标 ⇒ 全部 manual_required，不先到先得（AC-3.4）；
- 禁止对（``FORBIDDEN_MATCH_PAIRS``）永不产生候选。
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import lru_cache
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
)
from app.services.note_section_tree_locator import (
    ALIAS_TITLES,
    ManualMappingError,
    MatchResult,
    build_target_tree,
    is_forbidden,
    locate_by_tree,
    validate_tree_mappings,
)
from app.services.note_variable_replacer import apply_replacement_plan, build_replacement_plan

logger = logging.getLogger(__name__)

__all__ = [
    "ManualMappingError",
    "MatchResult",
    "SourceContext",
    "build_preview",
    "load_target_sections",
    "locate_sources",
    "match_sections",
    "sha256_text",
    "validate_manual_mappings",
    "validate_mappings",
    "writable_for",
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


_ALIAS_TITLES = ALIAS_TITLES
_is_forbidden = is_forbidden


def writable_for(kind: str) -> Callable[[Mapping[str, Any]], bool]:
    """本次可写范围：上传 / 知识库只填叙述性章节（AC-2.3），内容模板全套（叙述 + 科目注释）。"""
    kinds = ("narrative", "account_explanation") if kind == "content_template" else ("narrative",)
    return lambda target: target.get("section_kind") in kinds


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
    """内容模板来源：来源存在、目标在本次可写范围（本项目且 scope 内）、一对一、非禁止对；否则抛错。

    上传 / 知识库按章节树校验（锚点 / 章首正文），见 :func:`validate_mappings`。
    """
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


def validate_mappings(
    sources: list[ParsedSection],
    targets: list[dict[str, Any]],
    manual_mappings: dict[str, UUID],
    *,
    source_context: SourceContext | None = None,
) -> None:
    """按来源类型校验手工映射：模板见 :func:`validate_manual_mappings`，上传 / 知识库按章节树（锚点可选章）。"""
    ctx = source_context or SourceContext()
    if ctx.kind == "content_template":
        validate_manual_mappings(sources, targets, manual_mappings)
    else:
        validate_tree_mappings(sources, targets, manual_mappings, writable=writable_for(ctx.kind))


def locate_sources(
    sources: list[ParsedSection],
    targets: list[dict[str, Any]],
    *,
    manual_mappings: dict[str, UUID] | None = None,
    source_context: SourceContext | None = None,
    target_template_type: str | None = None,
) -> tuple[list[ParsedSection], list[MatchResult], frozenset[str]]:
    """统一入口：(预览用来源, 逐来源结论, 有子标题的来源 ID)。

    上传 / 知识库按章节树逐级定位（叶子目标并入后代、章首正文单列）；模板来源按编号匹配，来源原样。
    ``targets`` 须是 ``scope="all"`` 的全部章节（定位要走容器节点），``manual_mappings`` 须先经
    :func:`validate_mappings`。
    """
    ctx = source_context or SourceContext()
    if ctx.kind == "content_template":
        matches = match_sections(sources, targets, manual_mappings=manual_mappings, source_context=ctx,
                                 target_template_type=target_template_type)
        return sources, matches, frozenset()
    result = locate_by_tree(sources, targets, manual_mappings=manual_mappings, writable=writable_for(ctx.kind))
    return result.sources, result.matches, result.structural


def tree_warnings(targets: list[dict[str, Any]]) -> list[str]:
    """目标章节树缺失 / 部分行不在树上时提示（这些行不参与自动定位，只能手工指定）。"""
    tree = build_target_tree(targets)
    if not tree.roots:
        return ["本项目章节树未建立（章节缺少层级信息），无法按章节树定位；请联系管理员补齐章节树，或逐个手工指定目标章节"]
    if tree.off_tree:
        return [f"本项目有 {len(tree.off_tree)} 个章节不在章节树上（缺少层级信息或上级章节），不参与自动定位，可在下拉里手工指定"]
    return []


def _source_is_account(src: ParsedSection) -> bool | None:
    """模板来源是否属报表科目注释：用快照里的 ``section_kind``；无法判断返回 None（不门控）。"""
    meta_kind = (src.metadata or {}).get("section_kind")
    if meta_kind in ("narrative", "account_explanation"):
        return meta_kind == "account_explanation"
    return None


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


def _propose_by_title(src: ParsedSection, available: list[dict], ctx: SourceContext,
                      target_tt: str) -> tuple[dict | None, str, str, str]:
    """模板来源编号对不上时按标题找：同模板只在来源编号所属的章内找（第 23 组）；跨模板只认显式别名 / 标题。"""
    key = canonical_title(src.title)
    if not key:
        return None, "unmatched", "来源标题为空", "manual_required"
    exact = [t for t in available if canonical_title(t.get("section_title")) == key]
    alias = [t for t in available if t not in exact
             and (key, canonical_title(t.get("section_title"))) in _ALIAS_TITLES]
    hits = [t for t in exact + alias if not _is_forbidden(src.title, t.get("section_title"))]
    if normalize_template_type(ctx.template_type) == target_tt:
        chapter = chapter_title_for_code((src.metadata or {}).get("note_section"), ctx.template_type)
        hits = [t for t in hits if chapter and canonical_title(t.get("chapter_title")) == canonical_title(chapter)]
        if not hits:
            return (None, "unmatched", f"在「{chapter}」章内找不到「{src.title}」" if chapter
                    else f"来源编号无所属章，按标题找不到「{src.title}」的章内位置", "manual_required")
    if not hits:
        return None, "unmatched", "未找到匹配的目标章节", "manual_required"
    if len(hits) > 1:
        return None, "ambiguous", f"存在 {len(hits)} 个同名目标章节，需人工选择", "manual_required"
    hit = hits[0]
    if hit in alias:
        return hit, "alias", f"显式别名「{src.title}」↔「{hit.get('section_title')}」", "confirmed"
    return hit, "title_exact", f"标题规范化一致「{src.title}」", "candidate"


def match_sections(
    sources: list[ParsedSection],
    targets: list[dict[str, Any]],
    *,
    manual_mappings: dict[str, UUID] | None = None,
    source_context: SourceContext | None = None,
    target_template_type: str | None = None,
) -> list[MatchResult]:
    """内容模板来源的章节匹配（规则见模块说明）；``manual_mappings`` 须先经 :func:`validate_manual_mappings`。

    上传 / 知识库来源按章节树逐级定位，用 :func:`locate_sources`（本函数对它们直接报错，防止走回按标题全局找）。
    """
    ctx = source_context or SourceContext()
    if ctx.kind != "content_template":
        raise ValueError("上传 / 知识库来源按章节树逐级定位：请用 locate_sources")
    target_tt = normalize_template_type(target_template_type)
    manual = manual_mappings or {}
    tgt_by_id = {t["id"]: t for t in targets}
    reserved = {tid for tid in manual.values() if tid in tgt_by_id}
    available = [t for t in targets if t["id"] not in reserved]

    proposals: dict[str, tuple[dict | None, str, str, str]] = {}
    for src in sources:
        if src.source_id in manual:
            continue
        source_account = _source_is_account(src)
        eligible = [t for t in available if _kind_compatible(t, source_account)]
        proposals[src.source_id] = (
            _propose_by_code(src, eligible, ctx, target_tt)
            or _propose_by_title(src, eligible, ctx, target_tt)
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


# ════════════════════════════════════════════════════════════════════════════
# Task 24~25：Preview
# ════════════════════════════════════════════════════════════════════════════

#: design §8.2 quality_warning：源章 draft/stale/占位文本/疑似来源实体、日期、金额 ⇒ 需复核
_HIGH_RISK_REVIEW_FLAGS = frozenset({
    QualityFlag.DRAFT, QualityFlag.STALE, QualityFlag.PLACEHOLDER, QualityFlag.SOURCE_ENTITY,
    QualityFlag.DATE, QualityFlag.AMOUNT,
})



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
    structural_ids: frozenset[str] | set[str] | None = None,
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

    structural = set(structural_ids or ())
    skipped = {"folded": 0, "out_of_scope": 0, "anchor": 0}
    # 左栏逐来源显示跳过原因（AC-2.2）：只给计数时分不清「被跳过」与「没匹配上」；只供展示，不进 digest
    skipped_sources: list[dict[str, str]] = []
    for m in matches:
        src = src_map.get(m.source_id)
        if src is None:
            continue
        if m.match_kind in skipped:
            # 已并入上级 / 不在本次可填范围 / 有子标题的来源已定位到章（只作其下定位的锚点）：不进预览
            skipped[m.match_kind] += 1
            skipped_sources.append({"source_id": m.source_id, "match_kind": m.match_kind, "evidence": m.evidence})
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
            # 不可用原因直接用定位结论（在哪个章下找不到 / 上级未定位 / 同名多个…），用户据此手工对应
            category = "unavailable"
            reason = m.evidence or "未找到匹配的目标章节"
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
            # 有子标题的来源：未定位时下拉可选目标章作锚点（第 23 组）；只供展示，不进 digest
            "structural": m.source_id in structural,
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
