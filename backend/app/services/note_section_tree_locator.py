"""附注批量写入：按章节树逐级定位（spec disclosure-note-doc-upload-and-batch-fill 第 23 组；AC-1.6 / AC-3.6~3.8）。

用户拍板（2026-10-15）：「先找到大标题章节，之后再匹配其下面的小标题，按树形层级来」「如果匹配不上可以提前用户
手动处理对应，你不要自行处理」「识别上传文档时，也需要按章节树形来」。首版先按小标题在全部目标里找、同名多个才用
一级章消歧：章下没有这一节时配到别的章的同名节（国企 Word「重要会计政策 / 递延所得税资产及递延所得税负债」→
「六、税项」下同名节），章节点与同名正文节同时命中报「同名多个」。

- 来源树：标题按出现顺序建树，上级 = 前面最近的、层级更高的标题；知识库多篇文档各自成树；解析器生成的
  「（无标题）」「（表格）」占位章不当上级。树由 (顺序, 层级) 在服务端重算，不信客户端回传的上级。
- 目标树：``section_id / parent_section_id``；不在树上的行（无 section_id、上级不存在）不参与定位，只能手工指定。
- 逐级定位：来源顶层标题只在目标根节点里找，已定位节点的子标题只在其目标的子节点里找，唯一命中才算定位；
  找不到 / 同名多个 / 上级未定位 ⇒ 需人工对应，不到别处找、不就近并入、不按编号推测。
- 目标是叶子 ⇒ 来源该节的全部后代按原顺序并入该节正文（小标题转加粗段落）。目标有子节点 ⇒ 来源自身正文落到
  与目标同名的唯一子节点（「一 公司基本情况」→「一、1 公司基本情况」）；来源同时有子标题时，自身正文另列为
  ``{source_id}#body``（章首正文），找不到同名正文节需人工对应。
- 章即正文：目标章下**只有**一个同名正文节且它没有下级（上市「十 公允价值」→「十、1 公允价值」）⇒ 按叶子处理，
  来源章内的小标题（Word「（1）以公允价值计量的项目和金额」…「（5）…」）是这段正文的组成部分，一并并入。
- 手工对应：值为有子节点的目标 ⇒ 锚点（其下小标题在该目标内定位，自身正文按章首正文规则）；否则为写入目标，
  来源的后代并入。
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from html import escape
from typing import Any
from uuid import UUID

from app.services.note_document_parser import ParsedSection
from app.services.note_html_sanitizer import has_visible_text
from app.services.note_section_kind import canonical_title, normalize_title
from app.services.note_section_matcher import FORBIDDEN_MATCH_PAIRS, SECTION_TITLE_ALIASES

__all__ = [
    "ALIAS_TITLES",
    "BODY_SUFFIX",
    "PSEUDO_TITLES",
    "LocateResult",
    "ManualMappingError",
    "MatchResult",
    "TargetTree",
    "build_source_tree",
    "build_target_tree",
    "doc_of",
    "is_forbidden",
    "locate_by_tree",
    "source_parent_ids",
    "validate_tree_mappings",
]

#: 解析器给「文档开头无标题的段落 / 表格」起的占位标题：不当上级、不参与定位
PSEUDO_TITLES = frozenset({"（无标题）", "（表格）"})
#: 章首正文项：来源节点有子标题且自身有正文时，正文单列为 ``{source_id}#body``
BODY_SUFFIX = "#body"


class ManualMappingError(ValueError):
    """手工映射非法（端点转 422）。"""


class MatchResult:
    __slots__ = ("source_id", "target_note_id", "match_kind", "evidence", "confidence")

    def __init__(self, source_id: str, target_note_id: UUID | None, match_kind: str,
                 evidence: str, confidence: str):
        self.source_id = source_id
        self.target_note_id = target_note_id
        self.match_kind = match_kind
        self.evidence = evidence
        self.confidence = confidence


def _pairs(raw: list[tuple[str, str]]) -> frozenset[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for a, b in raw:
        ka, kb = normalize_title(a), normalize_title(b)
        out.update({(ka, kb), (kb, ka)})
    return frozenset(out)


_FORBIDDEN_TITLES = _pairs([(a, b) for a, b, _reason in FORBIDDEN_MATCH_PAIRS])
ALIAS_TITLES = _pairs([(p.soe_title, p.listed_title) for p in SECTION_TITLE_ALIASES])


def is_forbidden(a: str | None, b: str | None) -> bool:
    return (normalize_title(a), normalize_title(b)) in _FORBIDDEN_TITLES


# ── 来源树 ────────────────────────────────────────────────────────────────────

_NO_DOC = object()


def doc_of(section: ParsedSection) -> Any:
    return (section.metadata or {}).get("doc_id")


@dataclass(eq=False)
class SourceNode:
    section: ParsedSection
    parent: SourceNode | None = None
    children: list[SourceNode] = field(default_factory=list)

    @property
    def sid(self) -> str:
        return self.section.source_id

    def descendants(self) -> list[SourceNode]:
        out: list[SourceNode] = []
        for child in self.children:
            out.append(child)
            out.extend(child.descendants())
        return out


def build_source_tree(sections: list[ParsedSection]) -> list[SourceNode]:
    """全部节点（文档顺序）；``parent`` = 前面最近的、层级更高的标题，跨文档不连。"""
    nodes: list[SourceNode] = []
    stack: list[SourceNode] = []
    doc = _NO_DOC
    for section in sections:
        node = SourceNode(section)
        nodes.append(node)
        if doc_of(section) != doc:
            stack, doc = [], doc_of(section)
        if section.title in PSEUDO_TITLES:
            continue
        while stack and stack[-1].section.level >= section.level:
            stack.pop()
        if stack:
            node.parent = stack[-1]
            stack[-1].children.append(node)
        stack.append(node)
    return nodes


def source_parent_ids(sections: list[ParsedSection]) -> dict[str, str | None]:
    """解析结果下发给前端的上级（只供显示；定位时由服务端按顺序与层级重算）。"""
    return {n.sid: (n.parent.sid if n.parent else None) for n in build_source_tree(sections)}


# ── 目标树 ────────────────────────────────────────────────────────────────────


@dataclass
class TargetTree:
    roots: list[dict[str, Any]]
    children: dict[Any, list[dict[str, Any]]]
    off_tree: list[dict[str, Any]]

    def kids(self, target: Mapping[str, Any]) -> list[dict[str, Any]]:
        return self.children.get(target["id"], [])


def build_target_tree(targets: list[dict[str, Any]]) -> TargetTree:
    by_sid = {t["section_id"]: t for t in targets if t.get("section_id")}
    children: dict[Any, list[dict[str, Any]]] = {}
    roots: list[dict[str, Any]] = []
    off: list[dict[str, Any]] = []
    for t in targets:
        sid, parent_sid = t.get("section_id"), t.get("parent_section_id")
        if not sid:
            off.append(t)
        elif not parent_sid:
            roots.append(t)
        elif parent_sid in by_sid and parent_sid != sid:
            children.setdefault(by_sid[parent_sid]["id"], []).append(t)
        else:
            off.append(t)
    return TargetTree(roots=roots, children=children, off_tree=off)


# ── 逐级定位 ──────────────────────────────────────────────────────────────────


def _label(target: Mapping[str, Any]) -> str:
    return f"{target.get('note_section') or ''} {target.get('section_title') or ''}".strip()


def _sole_body_leaf(tree: TargetTree, target: Mapping[str, Any]) -> dict[str, Any] | None:
    """章下只有一个与章同名、自身无下级的正文节 ⇒ 返回它（章即正文）；否则 None。"""
    kids = tree.kids(target)
    if len(kids) != 1 or tree.kids(kids[0]):
        return None
    key = canonical_title(target.get("section_title"))
    return kids[0] if key and canonical_title(kids[0].get("section_title")) == key else None


def _find(pool: list[dict[str, Any]], title: str) -> list[dict[str, Any]]:
    key = canonical_title(title)
    if not key:
        return []
    exact = [t for t in pool if canonical_title(t.get("section_title")) == key]
    alias = [t for t in pool if t not in exact and (key, canonical_title(t.get("section_title"))) in ALIAS_TITLES]
    return [t for t in exact + alias if not is_forbidden(title, t.get("section_title"))]


@dataclass
class LocateResult:
    #: 预览用来源：叶子目标的来源已并入后代正文；章首正文项为 ``{source_id}#body``
    sources: list[ParsedSection]
    #: 每个来源恰好一条结论（文档顺序；章首正文项紧跟其节点）
    matches: list[MatchResult]
    #: 有子标题的来源节点：未定位时前端下拉要能选目标章（锚点）
    structural: frozenset[str] = frozenset()


def validate_tree_mappings(
    sections: list[ParsedSection],
    targets: list[dict[str, Any]],
    manual_mappings: Mapping[str, UUID],
    *,
    writable: Callable[[Mapping[str, Any]], bool],
) -> None:
    """来源存在（章首正文项须对应有子标题且有正文的节点）、目标属本项目、一对一、非禁止对；
    有子节点的目标是锚点（章首正文项不能指向锚点），其余目标须在本次可写范围。"""
    nodes = {n.sid: n for n in build_source_tree(sections)}
    tree = build_target_tree(targets)
    by_id = {t["id"]: t for t in targets}
    seen: dict[UUID, str] = {}
    for key, target_id in manual_mappings.items():
        is_body = key.endswith(BODY_SUFFIX)
        node = nodes.get(key[: -len(BODY_SUFFIX)] if is_body else key)
        if node is None or (is_body and not (node.children and has_visible_text(node.section.html))):
            raise ManualMappingError(f"来源章节不存在：{key}")
        target = by_id.get(target_id)
        if target is None:
            raise ManualMappingError("目标章节不在本项目（已删除或口径不适用）")
        anchor = bool(tree.kids(target))
        if anchor and is_body:
            raise ManualMappingError(f"章首正文要指定到可写入的章节，「{_label(target)}」下还有子章节")
        if not anchor and not writable(target):
            raise ManualMappingError(f"目标章节「{_label(target)}」不在本次可填范围（上传 / 知识库只填叙述性章节）")
        if target_id in seen:
            raise ManualMappingError(f"同一目标章节只能接受一个来源：{_label(target)}")
        if is_forbidden(node.section.title, target.get("section_title")):
            raise ManualMappingError(f"禁止匹配对不可强行映射：「{node.section.title}」↔「{target.get('section_title')}」")
        seen[target_id] = key


Proposal = tuple[dict[str, Any] | None, str, str, str]


def locate_by_tree(
    sections: list[ParsedSection],
    targets: list[dict[str, Any]],
    *,
    manual_mappings: Mapping[str, UUID] | None = None,
    writable: Callable[[Mapping[str, Any]], bool],
) -> LocateResult:
    """上传 / 知识库来源按章节树逐级定位（规则见模块说明）。``manual_mappings`` 须先经校验。"""
    manual = dict(manual_mappings or {})
    nodes = build_source_tree(sections)
    tree = build_target_tree(targets)
    by_id = {t["id"]: t for t in targets}
    out_sections: dict[str, ParsedSection] = {n.sid: n.section for n in nodes}
    proposals: dict[str, Proposal] = {}
    skipped: dict[str, tuple[str, str]] = {}
    body_items: dict[str, str] = {}  # 节点 sid → 章首正文项 id

    def body_target(item_id: str, target: dict[str, Any], node_confidence: str) -> Proposal:
        if item_id in manual and item_id.endswith(BODY_SUFFIX):
            return by_id[manual[item_id]], "manual", "用户手工对应", "confirmed"
        key = canonical_title(target.get("section_title"))
        same = [k for k in tree.kids(target) if canonical_title(k.get("section_title")) == key]
        if len(same) == 1:
            return same[0], "chapter_body", f"正文落到「{_label(target)}」下的同名正文节「{_label(same[0])}」", node_confidence
        return (None, "chapter_body_unmatched",
                f"「{_label(target)}」下没有与之同名的正文节，章首正文需人工指定目标节", "manual_required")

    def visit(node: SourceNode, pool: list[dict[str, Any]] | None, scope: str) -> None:
        title = node.section.title
        if node.sid in manual:
            proposal: Proposal = (by_id[manual[node.sid]], "manual", "用户手工对应", "confirmed")
        elif title in PSEUDO_TITLES:
            proposal = (None, "unmatched", "文档开头无标题的段落，需人工指定目标章节", "manual_required")
        elif pool is None:
            proposal = (None, "parent_unmatched", f"上级「{scope}」未定位：先对应上级标题，或逐个手工指定", "manual_required")
        else:
            hits = _find(pool, title)
            if len(hits) == 1:
                proposal = (hits[0], "tree_path", f"章节树「{scope} / {title}」" if scope else f"章节树「{title}」",
                            "candidate")
            elif hits:
                proposal = (None, "tree_ambiguous", f"「{scope or '一级章'}」下有 {len(hits)} 个「{title}」，需人工选择",
                            "manual_required")
            else:
                proposal = (None, "tree_unmatched",
                            f"在「{scope}」下找不到「{title}」" if scope else f"一级章里找不到「{title}」", "manual_required")
        target, _kind, _evidence, confidence = proposal
        if target is None:
            proposals[node.sid] = proposal
            for child in node.children:
                visit(child, None, title)
            return
        sole = _sole_body_leaf(tree, target) if _kind != "manual" else None
        if sole is not None:  # 章即正文：整章（含章内小标题）落到同名正文节
            proposal = (sole, "chapter_body", f"正文落到「{_label(target)}」下的同名正文节「{_label(sole)}」", confidence)
            target = sole
        kids = tree.kids(target)
        if not kids:  # 目标是叶子：后代全部并入该节正文（用户另行手工指定的后代除外，连同其下级单独处理）
            parts: list[str] = [node.section.html]

            def fold(parent: SourceNode) -> None:
                for child in parent.children:
                    if child.sid in manual:
                        visit(child, None, title)
                        continue
                    parts.append(f"<p><strong>{escape(child.section.title)}</strong></p>{child.section.html}")
                    skipped[child.sid] = ("folded", f"已并入「{title}」")
                    fold(child)

            fold(node)
            if len(parts) > 1:
                out_sections[node.sid] = dataclasses.replace(node.section, html="".join(parts))
            proposals[node.sid] = proposal
            return
        if not node.children:  # 无子标题的来源定位到有子节点的目标：正文按章首正文规则
            proposals[node.sid] = body_target(node.sid, target, confidence)
            return
        skipped[node.sid] = ("anchor", f"已定位到「{_label(target)}」，其下小标题在该章内定位")
        if has_visible_text(node.section.html):
            body_id = node.sid + BODY_SUFFIX
            body_items[node.sid] = body_id
            out_sections[body_id] = dataclasses.replace(node.section, source_id=body_id, title=f"{title}（章首正文）")
            proposals[body_id] = body_target(body_id, target, confidence)
        for child in node.children:
            visit(child, kids, _label(target))

    for node in nodes:
        if node.parent is None:
            visit(node, tree.roots, "")

    # 可写范围：定位到不可写的目标（如上传来源定位到科目注释节）不进预览，其并入的后代随之跳过
    for item_id, (target, kind, evidence, confidence) in list(proposals.items()):
        if target is not None and not writable(target) and not tree.kids(target):
            proposals[item_id] = (None, "out_of_scope", f"「{_label(target)}」不在本次可填范围", "manual_required")
    owners_out = {sid for sid, (_t, kind, *_r) in proposals.items() if kind == "out_of_scope"}
    for node in nodes:
        if node.sid in owners_out:
            for d in node.descendants():
                if skipped.get(d.sid, ("",))[0] == "folded":
                    skipped[d.sid] = ("out_of_scope", f"随「{node.section.title}」不在本次可填范围")

    # 多个来源指向同一写入目标 ⇒ 全部人工确认（AC-3.4）
    claims: dict[Any, list[str]] = {}
    for item_id, (target, kind, *_rest) in proposals.items():
        if target is not None and kind != "out_of_scope":
            claims.setdefault(target["id"], []).append(item_id)
    for target_id, item_ids in claims.items():
        if len(item_ids) > 1:
            for item_id in item_ids:
                if proposals[item_id][1] != "manual":
                    proposals[item_id] = (None, "conflict", f"{len(item_ids)} 个来源章节指向同一目标"
                                          f"「{_label(by_id[target_id])}」，需人工确认", "manual_required")

    matches: list[MatchResult] = []
    for node in nodes:
        for item_id in (node.sid, body_items.get(node.sid)):
            if item_id is None:
                continue
            if item_id in skipped:
                kind, evidence = skipped[item_id]
                matches.append(MatchResult(item_id, None, kind, evidence, "manual_required"))
            elif item_id in proposals:
                target, kind, evidence, confidence = proposals[item_id]
                if kind == "out_of_scope":
                    matches.append(MatchResult(item_id, None, kind, evidence, confidence))
                else:
                    matches.append(MatchResult(item_id, target["id"] if target else None, kind, evidence, confidence))
    ordered = [out_sections[m.source_id] for m in matches]
    return LocateResult(sources=ordered, matches=matches,
                        structural=frozenset(n.sid for n in nodes if n.children))
