"""国企 ↔ 上市附注种子的章节配对：同名节按章类别配对（差异计算）+ 别名桥接按章类别选目标（转换）。

spec: disclosure-note-template-word-realignment Task 32（design §9）

为什么不能「每个标题只取第一个节」（原 ``note_template_diff._build_title_index``）
--------------------------------------------------------------------------------
两版种子里同名的节很多：会计政策章与报表项目注释章都有「固定资产」「存货」「长期股权投资」…，
报表项目注释章与母公司报表项目注释章都有「应收账款」「其他应收款」「投资收益」…，章行与它的章正文叶子同名。
只取第一个 ⇒ 第二个起**不进任何差异桶**（2026-10-17 实测国企 23 节、上市 28 节，含国企「八、22 固定资产」
上市「五、22 固定资产」这类科目注释节）⇒ 转换时这些节既不改写也不新建，留着源准则的编号；还会把
国企「十二、投资收益」（母公司）配到上市「五、69」（合并）、国企「四、应付债券」（会计政策）配到上市「五、46」。

配对规则（纯函数，结果确定）
----------------------------
每个节有一个配对组：章行 = ``chapter``；会计政策章 / 报表项目注释章 / 母公司报表项目注释章的节 = ``policy`` /
``items`` / ``parent``（按所在章的编号，见 :data:`CHAPTER_KINDS`）；其余章的节 = ``None``。同一标题下两侧的节按
亲和度从高到低、同分按文档顺序一一配对（:func:`affinity`）；章行只和章行配。配不上的进各自的独有桶，
别名桥接（转换侧）再按同一亲和度在独有桶里选目标并逐个占用，同一目标不会被两个源节占用。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

__all__ = [
    "CHAPTER_KINDS",
    "GROUP_CHAPTER",
    "affinity",
    "bridge_alias_pairs",
    "pair_template_sections",
    "section_groups",
]

#: 两版都有同名节的三类章（键 = 章编号；编号是标识，章名会按 Word 改，编号不变）
CHAPTER_KINDS: dict[str, dict[str, str]] = {
    "soe": {"四": "policy", "八": "items", "十二": "parent"},
    "listed": {"三": "policy", "五": "items", "十六": "parent"},
}

#: 章行（level 1 / 无父节点）的配对组
GROUP_CHAPTER = "chapter"


def section_groups(side: str, sections: Iterable[Any]) -> dict[str, str | None]:
    """``section_id`` → 配对组（章行 ``chapter`` / 三类章的节 / 其余 ``None``）。"""
    rows = [s for s in sections if isinstance(s, dict) and s.get("section_id")]
    by_id = {s["section_id"]: s for s in rows}
    kinds = CHAPTER_KINDS.get(side, {})
    out: dict[str, str | None] = {}
    for s in rows:
        parent = by_id.get(s.get("parent_section_id") or "")
        if parent is None:
            out[s["section_id"]] = GROUP_CHAPTER
            continue
        seen = {s["section_id"]}
        while parent.get("parent_section_id") in by_id and parent["section_id"] not in seen:
            seen.add(parent["section_id"])
            parent = by_id[parent["parent_section_id"]]
        out[s["section_id"]] = kinds.get(str(parent.get("section_number") or "").split("、")[0])
    return out


def affinity(a: str | None, b: str | None) -> float | None:
    """两个配对组的亲和度；``None`` = 不得配对。

    同组 3（两侧都在「其余章」2）；「其余章」与项目注释 / 母公司章 2、与会计政策章 1；项目注释 ↔ 母公司 1
    （国企「十二、现金流量表补充资料」↔ 上市「五、71」，已登记豁免）；会计政策 ↔ 项目注释 / 母公司 0.5，
    只在没有别的可配时才用（上市只在会计政策章有「债务重组」，国企在项目注释章）。章行只和章行配。
    """
    if (a == GROUP_CHAPTER) != (b == GROUP_CHAPTER):
        return None
    if a == b:
        return 2.0 if a is None else 3.0
    if a is None or b is None:
        return 1.0 if "policy" in (a, b) else 2.0
    if {a, b} == {"items", "parent"}:
        return 1.0
    return 0.5


def _greedy(scored: list[tuple[float, int, int]]) -> list[tuple[int, int]]:
    """亲和度高者先配、同分按（左序, 右序）；左右各只用一次。"""
    used_left: set[int] = set()
    used_right: set[int] = set()
    out: list[tuple[int, int]] = []
    for _neg, i, j in sorted((-score, i, j) for score, i, j in scored):
        if i in used_left or j in used_right:
            continue
        used_left.add(i)
        used_right.add(j)
        out.append((i, j))
    return sorted(out)


def pair_template_sections(
    soe_sections: list[dict[str, Any]],
    listed_sections: list[dict[str, Any]],
) -> tuple[list[tuple[str, dict, dict]], list[tuple[str, dict, str | None]], list[tuple[str, dict, str | None]]]:
    """按标题精确相同配对两版种子的节。

    Returns:
        ``(pairs, soe_only, listed_only)``：``pairs`` = ``[(标题, 国企节, 上市节)]``，按标题、再按国企节文档顺序；
        独有 = ``[(标题, 节, 配对组)]``，按标题、再按文档顺序。每个有标题的节恰好出现在其中一处。
    """
    groups = {"soe": section_groups("soe", soe_sections), "listed": section_groups("listed", listed_sections)}
    by_title: dict[str, dict[str, list[dict]]] = defaultdict(lambda: {"soe": [], "listed": []})
    for side, sections in (("soe", soe_sections), ("listed", listed_sections)):
        for s in sections:
            if isinstance(s, dict) and s.get("section_title"):
                by_title[s["section_title"]][side].append(s)

    def group(side: str, s: dict) -> str | None:
        return groups[side].get(s.get("section_id") or "")

    pairs: list[tuple[str, dict, dict]] = []
    soe_only: list[tuple[str, dict, str | None]] = []
    listed_only: list[tuple[str, dict, str | None]] = []
    for title in sorted(by_title):
        so, li = by_title[title]["soe"], by_title[title]["listed"]
        scored = [
            (score, i, j)
            for i, a in enumerate(so)
            for j, b in enumerate(li)
            if (score := affinity(group("soe", a), group("listed", b))) is not None
        ]
        matched = _greedy(scored)
        pairs += [(title, so[i], li[j]) for i, j in matched]
        used_so, used_li = {i for i, _ in matched}, {j for _, j in matched}
        soe_only += [(title, s, group("soe", s)) for i, s in enumerate(so) if i not in used_so]
        listed_only += [(title, s, group("listed", s)) for j, s in enumerate(li) if j not in used_li]
    return pairs, soe_only, listed_only


def bridge_alias_pairs(
    sources: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    source_side: str,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """别名桥接：源独有节 → 目标独有节（标题互为 ``SECTION_TITLE_ALIASES`` 别名，且过 ``match_section``）。

    条目形态同差异桶（``{section_id, title, pairing_group?}``）。同一别名在目标侧有多个节时（上市「营业收入和营业成本」
    在项目注释章与母公司章各一节）按 :func:`affinity` 选同类章的那个；每个目标只给一个源。
    """
    from app.services.note_section_matcher import (
        match_section,
        normalize_for_match,
        resolve_alias_counterparts,
    )

    target_side = "listed" if source_side == "soe" else "soe"
    scored: list[tuple[float, int, int]] = []
    for i, src in enumerate(sources):
        wanted = {normalize_for_match(t) for t in resolve_alias_counterparts(src.get("title"), target_side)}
        if not wanted or not src.get("section_id"):
            continue
        for j, tgt in enumerate(targets):
            if not tgt.get("section_id") or normalize_for_match(tgt.get("title")) not in wanted:
                continue
            soe_title, listed_title = (src, tgt) if source_side == "soe" else (tgt, src)
            if not match_section(soe_title.get("title"), listed_title.get("title")):
                continue  # 禁止对优先于一切
            score = affinity(src.get("pairing_group"), tgt.get("pairing_group"))
            # 别名是同一节的措辞差异：会计政策章 ↔ 项目注释 / 母公司章（0.5）不桥（国企「八、83 股份支付」
            # 不得经「股份支付 ↔ 股份支付及权益工具」桥到上市会计政策章）
            if score is not None and score >= 1.0:
                scored.append((score, i, j))
    pairs = [(sources[i], targets[j]) for i, j in _greedy(scored)]
    # 可追溯清单先列真正发生 sid 重键的桥接，再列 sid 本来同值、只改标题的桥接；转换语义不依赖顺序。
    return sorted(
        pairs,
        key=lambda pair: (
            pair[0].get("section_id") == pair[1].get("section_id"),
            str(pair[0].get("section_id") or ""),
            str(pair[1].get("section_id") or ""),
        ),
    )
