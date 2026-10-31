"""守卫：章号映射错配核查三态清单（Property 30）。

spec: soe-listed-note-conversion-correctness / Requirements 8.1, 8.2, 8.3, 8.4

------------------------------------------------------------------
背景（2026-08-05 核查 + 2026-08-06 用户裁决）
------------------------------------------------------------------

实时 ``compute_diff_from_templates()`` 的 ``common_sections`` = 107 条，其中两组
「章号不一致」的映射需逐条定性（Requirement 8.1）：

* ``soe ch08 → listed ch03`` = 10 条：section_title 两侧完全相同，soe 归「项目
  注释章」、listed 归「会计政策章」= **章节归属差异（NORMAL_MAPPING，正常映射）**，
  非 bug。
* ``soe ch12 → listed ch05`` = 1 条（现金流量表补充资料）：母公司章
  （``scope='consolidated_only'``）没有对应的 listed 母公司子节，故按同名落到 listed 合并章。
  **用户 2026-08-06 裁决 = EXEMPTED（已登记豁免）**。原第二条「投资收益」在
  disclosure-note-template-word-realignment Task 32 改为按章类别配对，现正确映射 ch12→ch16。

三态清单（模块级冻结常量）+ 连实时 ``compute_diff_from_templates()`` 断言：
- NORMAL_MAPPING（1 条）：正常映射，逐条列 section_title + 判定依据
- CORRECTED：A spec 已修正项及 Task 32 同名多节配对修正，
  与实时数据交叉锁死
- EXEMPTED（1 条）：已登记豁免 + 豁免依据（reason 非空且 ≥20 字）

**🔴 禁止写 `soe ch12→listed ch05 == 0` 断言**（仍有现金流量表补充资料 1 条）；
断言「实际恰为这 1 条，无第二条漏网」。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pytest

from app.services.note_template_diff import (
    compute_diff_from_templates,
    load_template_sections,
)

# ---------------------------------------------------------------------------
# 三态冻结清单（模块级常量）
# ---------------------------------------------------------------------------

_NORMAL_BASIS = "soe 项目注释章（八）/ listed 会计政策章（三）的章节归属差异，section_title 两侧相同，非错配"


@dataclass(frozen=True)
class NormalMapping:
    """soe ch08 → listed ch03 的正常映射条目（章节归属差异）。"""

    section_title: str
    basis: str


@dataclass(frozen=True)
class Corrected:
    """A spec 已修正项（如实登记的说明条目）。"""

    subject: str
    detail: str


@dataclass(frozen=True)
class Exempted:
    """已登记豁免条目 —— soe ch12（母公司章）→ listed ch05（合并章）。"""

    section_title: str
    reason: str


#: NORMAL_MAPPING = soe ch08 → listed ch03 现存条目（section_title 逐条锁死）。
#: 2026-10-16（spec disclosure-note-template-word-realignment）按四版 Word 把上市会计政策章里的 9 个利润表 /
#: 研发节改挂到项目附注章「五」与研发支出章「六」⇒ 原 10 条只剩「债务重组」：上市 Word 只在会计政策章有
#: 「债务重组」（国企在项目注释章），两边都与 Word 一致。改挂的 9 条见 CORRECTED。
NORMAL_MAPPING: tuple[NormalMapping, ...] = (
    NormalMapping("债务重组", _NORMAL_BASIS),
)
_REALIGNED_FROM_CH03 = (
    "信用减值损失", "公允价值变动收益", "开发支出", "所得税费用", "现金流量表项目注释",
    "营业外支出", "营业外收入", "资产减值损失", "资产处置收益",
)

#: A spec 已把 soe 第十二章 slug 前缀由旧值修正为新值（本清单如实登记，
#: 并与实时数据交叉锁死：live 里 soe ch12 子节 sid 必须已是新前缀、绝不含旧前缀）
_SOE_CH12_OLD_SLUG_PREFIX = "chapter-12-gu-fen-zhi-fu"
_SOE_CH12_NEW_SLUG_PREFIX = "chapter-12-mu-gong-si"

CORRECTED: tuple[Corrected, ...] = (
    Corrected(
        subject="soe 第十二章标题与 section_id slug",
        detail=(
            "A spec (parent-company-note-chapter-and-sourcing) 已将 soe 第十二章"
            "标题「股份支付」修正为「母公司财务报表的主要项目附注」，section_id slug"
            f" 前缀由 {_SOE_CH12_OLD_SLUG_PREFIX} 改为 {_SOE_CH12_NEW_SLUG_PREFIX}；"
            "其 6 个母公司子节前缀连带重键。本条为对该修复的如实登记。"
        ),
    ),
    Corrected(
        subject="上市会计政策章里的 9 个利润表 / 研发节",
        detail=(
            "disclosure-note-template-word-realignment（2026-10-16）按四版 Word 改挂："
            + "、".join(_REALIGNED_FROM_CH03)
            + " 由会计政策章「三」移到项目附注章「五」（开发支出到研发支出章「六」），编号换章号、"
            "旧编号登记为种子别名、section_id 不变 ⇒ 章号按父节点判（section_id 前缀不再代表所属章）。"
        ),
    ),
    Corrected(
        subject="同名多节按章类别一一配对",
        detail=(
            "disclosure-note-template-word-realignment Task 32（2026-10-17）删除每个标题只取第一节的缺陷；"
            "国企十二、投资收益现映射上市十六、投资收益，不再错配到五、69；两侧每个有标题的节恰进一个差异桶。"
        ),
    ),
)

#: EXEMPTED = soe ch12（母公司章）→ listed ch05（合并章）的 1 条，每条 reason ≥20 字
_EXEMPT_REASON = (
    "母公司披露与合并披露天然共用同名科目；消除需改母公司章结构，属 A spec "
    "(parent-company-note-chapter-and-sourcing) 范围，B spec 已裁决 out-of-scope（已裁决事项 3）。"
)

EXEMPTED: tuple[Exempted, ...] = (
    Exempted("现金流量表补充资料", "「现金流量表补充资料」" + _EXEMPT_REASON),
)

#: EXEMPTED reason 的最小长度闸（Requirement 8.3 理由质量）
_MIN_REASON_LEN = 20

# ---------------------------------------------------------------------------
# 实时数据（连实时 compute_diff_from_templates()，不读落盘 JSON）
# ---------------------------------------------------------------------------

_CH_RE = re.compile(r"^chapter-(\d+)-")


def _parent_ids() -> dict[str, str]:
    import json

    from app.services.note_section_catalog import template_json_path

    out: dict[str, str] = {}
    for tt in ("soe", "listed"):
        for s in json.loads(template_json_path(tt).read_text(encoding="utf-8"))["sections"]:
            if s.get("section_id"):
                out[s["section_id"]] = s.get("parent_section_id") or s["section_id"]
    return out


_PARENT_IDS = _parent_ids()


def _chapter_of(section_id: str) -> str:
    """节所属章号：取父节点（章）的 section_id 前缀（``chapter-08-xxx`` → ``08``）。

    section_id 在节改挂到别的章时保持不变（disclosure-note-template-word-realignment），其前缀是建 id 时的章；
    所属章以 ``parent_section_id`` 为准。
    """
    m = _CH_RE.match(_PARENT_IDS.get(section_id or "", section_id or "") or "")
    return m.group(1) if m else ""


@pytest.fixture(scope="module")
def live_diff() -> dict:
    """实时计算的差异数据（模板即真源，绕过 load_diff_data 的落盘缓存）。"""
    return compute_diff_from_templates(
        load_template_sections("soe"),
        load_template_sections("listed"),
    )


def _entries_for_pair(diff: dict, soe_ch: str, listed_ch: str) -> list[dict]:
    """取 common_sections 中章号为 (soe_ch, listed_ch) 的条目。"""
    return [
        e
        for e in diff["common_sections"]
        if _chapter_of(e.get("soe_section_id", "")) == soe_ch
        and _chapter_of(e.get("listed_section_id", "")) == listed_ch
    ]


def _titles(entries: list[dict]) -> set[str]:
    return {e.get("section_title", "") for e in entries}


# ---------------------------------------------------------------------------
# 三态清单自身完整性
# ---------------------------------------------------------------------------


def test_normal_mapping_registry_shape():
    """NORMAL_MAPPING = 1 条（改挂后只剩「债务重组」）、无重复 section_title、每条判定依据非空。"""
    assert len(NORMAL_MAPPING) == 1
    titles = [n.section_title for n in NORMAL_MAPPING]
    assert len(set(titles)) == 1, f"NORMAL_MAPPING 有重复 section_title: {titles}"
    assert not set(titles) & set(_REALIGNED_FROM_CH03), "已改挂的节不得再登记为正常映射"
    for n in NORMAL_MAPPING:
        assert n.section_title.strip(), "NORMAL_MAPPING section_title 不得为空"
        assert n.basis.strip(), f"{n.section_title} 缺判定依据"


def test_corrected_registry_shape():
    """CORRECTED 非空，且记录了 slug 修正（旧前缀 → 新前缀）。"""
    assert len(CORRECTED) >= 1, "CORRECTED 不得为空（A spec 已修正项须如实登记）"
    joined = " ".join(c.detail for c in CORRECTED)
    assert _SOE_CH12_OLD_SLUG_PREFIX in joined
    assert _SOE_CH12_NEW_SLUG_PREFIX in joined


def test_exempted_registry_non_empty_and_reasons():
    """反向自检：EXEMPTED 非空（防被当逃逸阀清空后守卫空转）；每条 reason ≥20 字。"""
    assert len(EXEMPTED) == 1, "EXEMPTED 必须恰有 1 条（现金流量表补充资料）"
    titles = [e.section_title for e in EXEMPTED]
    assert len(set(titles)) == 1, f"EXEMPTED 有重复 section_title: {titles}"
    for e in EXEMPTED:
        assert e.section_title.strip(), "EXEMPTED section_title 不得为空"
        assert e.reason.strip(), f"{e.section_title} 的豁免理由为空"
        assert len(e.reason) >= _MIN_REASON_LEN, (
            f"{e.section_title} 的豁免理由过短（{len(e.reason)} < {_MIN_REASON_LEN}）"
        )


def test_three_state_registries_disjoint():
    """三态清单无重复登记：NORMAL 与 EXEMPTED 的 section_title 集合不相交。"""
    normal = {n.section_title for n in NORMAL_MAPPING}
    exempt = {e.section_title for e in EXEMPTED}
    assert normal.isdisjoint(exempt), f"NORMAL 与 EXEMPTED 重复登记: {normal & exempt}"


# ---------------------------------------------------------------------------
# 连实时数据的断言
# ---------------------------------------------------------------------------


def test_ch08_ch03_entries_match_normal_mapping(live_diff):
    """soe ch08→listed ch03 实际条目 section_title 集合 == NORMAL_MAPPING（逐条锁死）。"""
    entries = _entries_for_pair(live_diff, "08", "03")
    actual = _titles(entries)
    expected = {n.section_title for n in NORMAL_MAPPING}
    assert actual == expected, (
        f"soe ch08→ch03 与 NORMAL_MAPPING 不一致\n"
        f"  仅实际有: {sorted(actual - expected)}\n"
        f"  仅清单有: {sorted(expected - actual)}"
    )


def test_ch08_ch05_main_mapping_count_stable(live_diff):
    """主映射 soe ch08→listed ch05 仍为多数（Requirement 8.4，≥45）。"""
    entries = _entries_for_pair(live_diff, "08", "05")
    assert len(entries) >= 45, (
        f"soe ch08→ch05 主映射计数 {len(entries)} < 45，主映射分布疑似变化"
    )


def test_ch04_ch03_mapping_count_stable(live_diff):
    """soe ch04→listed ch03 仍为多数（Requirement 8.4，≥20）。"""
    entries = _entries_for_pair(live_diff, "04", "03")
    assert len(entries) >= 20, (
        f"soe ch04→ch03 计数 {len(entries)} < 20，主映射分布疑似变化"
    )


def test_ch12_ch05_entries_are_exactly_exempted(live_diff):
    """soe ch12→listed ch05 实际条目 == EXEMPTED 登记的 1 条。

    「投资收益」已由同名多节配对修正到 listed ch16；这里只允许「现金流量表补充资料」，无第二条漏网。
    """
    entries = _entries_for_pair(live_diff, "12", "05")
    actual = _titles(entries)
    expected = {e.section_title for e in EXEMPTED}
    assert actual == expected, (
        f"soe ch12→ch05 实际条目与 EXEMPTED 不一致（新增未登记豁免项必红）\n"
        f"  实际: {sorted(actual)}\n"
        f"  登记: {sorted(expected)}"
    )


def test_ch12_investment_income_maps_to_listed_parent_ch16(live_diff):
    """同名多节修复：母公司「投资收益」必须 parent→parent，不得再落到 listed 五、69。"""
    entries = _entries_for_pair(live_diff, "12", "16")
    assert "投资收益" in _titles(entries), "soe 十二、投资收益未映射到 listed 十六母公司章"
    assert "投资收益" not in _titles(_entries_for_pair(live_diff, "12", "05"))


def test_corrected_slug_landed_in_live_data(live_diff):
    """CORRECTED 交叉锁死：live 中 soe ch12→ch05 条目的 soe_section_id 已是新前缀，绝不含旧前缀。"""
    entries = _entries_for_pair(live_diff, "12", "05")
    assert entries, "soe ch12→ch05 应有条目（EXEMPTED 的 1 条），实际为空"
    for e in entries:
        sid = e.get("soe_section_id", "")
        assert sid.startswith(_SOE_CH12_NEW_SLUG_PREFIX), (
            f"soe ch12 子节 sid 未采用修正后前缀: {sid}"
        )
        assert _SOE_CH12_OLD_SLUG_PREFIX not in sid, (
            f"soe ch12 子节 sid 仍含已修正的旧 slug: {sid}"
        )


def test_three_state_union_covers_all_anomalies(live_diff):
    """三态清单并集覆盖 ch08→ch03(1) + ch12→ch05(1) 全部条目，无遗漏无重复。"""
    ch08_03 = _titles(_entries_for_pair(live_diff, "08", "03"))
    ch12_05 = _titles(_entries_for_pair(live_diff, "12", "05"))
    all_anomalies = ch08_03 | ch12_05

    registered = {n.section_title for n in NORMAL_MAPPING} | {
        e.section_title for e in EXEMPTED
    }
    missing = all_anomalies - registered
    extra = registered - all_anomalies
    assert not missing, f"有异常条目未登记进三态清单（漏）: {sorted(missing)}"
    assert not extra, f"三态清单登记了实际不存在的条目（多）: {sorted(extra)}"


# ---------------------------------------------------------------------------
# 反向自检（防守卫空转 / 证明「新增未登记豁免项必红」）
# ---------------------------------------------------------------------------


def test_reverse_selfcheck_unregistered_ch12_entry_reddens(live_diff):
    """反向自检：若 ch12→ch05 出现未登记的第二条，集合相等断言必失败。

    注入一个虚构条目模拟「新增未登记豁免项」，确认守卫机制非空转。
    """
    entries = _entries_for_pair(live_diff, "12", "05")
    injected = entries + [
        {
            "section_title": "__虚构未登记科目__",
            "soe_section_id": "chapter-12-mu-gong-si-xxx",
            "listed_section_id": "chapter-05-he-bing-xxx",
        }
    ]
    actual = _titles(injected)
    expected = {e.section_title for e in EXEMPTED}
    assert actual != expected, (
        "反向自检失败：注入未登记条目后集合仍相等 —— 守卫无法拦住新增豁免项"
    )


def test_reverse_selfcheck_missing_normal_entry_reddens(live_diff):
    """反向自检：若 ch08→ch03 少一条，与 NORMAL_MAPPING 的相等断言必失败。"""
    entries = _entries_for_pair(live_diff, "08", "03")
    assert entries, "ch08→ch03 应有条目"
    dropped = _titles(entries[1:])  # 去掉一条
    expected = {n.section_title for n in NORMAL_MAPPING}
    assert dropped != expected, (
        "反向自检失败：去掉一条后仍相等 —— NORMAL_MAPPING 与实际未真正逐条锁死"
    )


def test_realigned_sections_sit_in_word_chapters(live_diff):
    """改挂的 9 个上市节按父节点已不在会计政策章「03」（防有人把它们挂回去，或章号又按 section_id 前缀判）。"""
    by_title = {e["section_title"]: _chapter_of(e["listed_section_id"]) for e in live_diff["common_sections"]}
    stuck = sorted(t for t in _REALIGNED_FROM_CH03 if by_title.get(t) == "03")
    assert not stuck, f"仍在会计政策章：{stuck}"
