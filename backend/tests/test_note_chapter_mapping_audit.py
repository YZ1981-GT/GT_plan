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
* ``soe ch12 → listed ch05`` = 2 条（投资收益 / 现金流量表补充资料）：母公司章
  （``scope='consolidated_only'``）子节与 listed 合并章子节同名。Requirement 8.2
  原预期这 2 条在 A spec 修好 soe 第十二章标题后**消失**，但 A 只改章标题不改
  子节名，故仍配对。**用户 2026-08-06 裁决 = EXEMPTED（已登记豁免）**，在本 spec
  内以豁免状态收口，不改母公司章结构、不路由回 A spec。

三态清单（模块级冻结常量）+ 连实时 ``compute_diff_from_templates()`` 断言：
- NORMAL_MAPPING（10 条）：正常映射，逐条列 section_title + 判定依据
- CORRECTED：A spec 已修正项（soe 第十二章 slug gu-fen-zhi-fu → mu-gong-si-…），
  与实时数据交叉锁死（soe ch12 子节 sid 必须已是新前缀）
- EXEMPTED（2 条）：已登记豁免 + 豁免依据（每条 reason 非空且 ≥20 字）

**🔴 禁止写 `soe ch12→listed ch05 == 0` 断言**（那会在仍有 2 条时打红 = 假绿风险，
且与 EXEMPTED 语义矛盾）。断言的是「实际 2 条恰好都在豁免清单里、无第三条漏网」。
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


#: NORMAL_MAPPING = soe ch08 → listed ch03 的 10 条（section_title 逐条锁死）
NORMAL_MAPPING: tuple[NormalMapping, ...] = (
    NormalMapping("信用减值损失", _NORMAL_BASIS),
    NormalMapping("债务重组", _NORMAL_BASIS),
    NormalMapping("公允价值变动收益", _NORMAL_BASIS),
    NormalMapping("开发支出", _NORMAL_BASIS),
    NormalMapping("所得税费用", _NORMAL_BASIS),
    NormalMapping("现金流量表项目注释", _NORMAL_BASIS),
    NormalMapping("营业外支出", _NORMAL_BASIS),
    NormalMapping("营业外收入", _NORMAL_BASIS),
    NormalMapping("资产减值损失", _NORMAL_BASIS),
    NormalMapping("资产处置收益", _NORMAL_BASIS),
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
)

#: EXEMPTED = soe ch12（母公司章）→ listed ch05（合并章）的 2 条，每条 reason ≥20 字
_EXEMPT_REASON = (
    "母公司披露与合并披露天然共用同名科目；消除需改母公司章结构，属 A spec "
    "(parent-company-note-chapter-and-sourcing) 范围，B spec 已裁决 out-of-scope（已裁决事项 3）。"
)

EXEMPTED: tuple[Exempted, ...] = (
    Exempted("投资收益", "「投资收益」" + _EXEMPT_REASON),
    Exempted("现金流量表补充资料", "「现金流量表补充资料」" + _EXEMPT_REASON),
)

#: EXEMPTED reason 的最小长度闸（Requirement 8.3 理由质量）
_MIN_REASON_LEN = 20

# ---------------------------------------------------------------------------
# 实时数据（连实时 compute_diff_from_templates()，不读落盘 JSON）
# ---------------------------------------------------------------------------

_CH_RE = re.compile(r"^chapter-(\d+)-")


def _chapter_of(section_id: str) -> str:
    """从 section_id 前缀解析章号（``chapter-08-xxx`` → ``08``）。"""
    m = _CH_RE.match(section_id or "")
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
    """NORMAL_MAPPING = 10 条、无重复 section_title、每条判定依据非空。"""
    assert len(NORMAL_MAPPING) == 10
    titles = [n.section_title for n in NORMAL_MAPPING]
    assert len(set(titles)) == 10, f"NORMAL_MAPPING 有重复 section_title: {titles}"
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
    assert len(EXEMPTED) == 2, "EXEMPTED 必须恰有 2 条（投资收益 / 现金流量表补充资料）"
    titles = [e.section_title for e in EXEMPTED]
    assert len(set(titles)) == 2, f"EXEMPTED 有重复 section_title: {titles}"
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
    """soe ch12→listed ch05 实际条目 == EXEMPTED 登记的 2 条。

    🔴 断言的是「恰好这 2 条且都在豁免清单里、无第三条漏网」，
    而非 `== 0`（== 0 在仍有 2 条时会打红 = 假绿风险）。
    """
    entries = _entries_for_pair(live_diff, "12", "05")
    actual = _titles(entries)
    expected = {e.section_title for e in EXEMPTED}
    assert actual == expected, (
        f"soe ch12→ch05 实际条目与 EXEMPTED 不一致（新增未登记豁免项必红）\n"
        f"  实际: {sorted(actual)}\n"
        f"  登记: {sorted(expected)}"
    )


def test_corrected_slug_landed_in_live_data(live_diff):
    """CORRECTED 交叉锁死：live 中 soe ch12→ch05 条目的 soe_section_id 已是新前缀，绝不含旧前缀。"""
    entries = _entries_for_pair(live_diff, "12", "05")
    assert entries, "soe ch12→ch05 应有条目（EXEMPTED 的 2 条），实际为空"
    for e in entries:
        sid = e.get("soe_section_id", "")
        assert sid.startswith(_SOE_CH12_NEW_SLUG_PREFIX), (
            f"soe ch12 子节 sid 未采用修正后前缀: {sid}"
        )
        assert _SOE_CH12_OLD_SLUG_PREFIX not in sid, (
            f"soe ch12 子节 sid 仍含已修正的旧 slug: {sid}"
        )


def test_three_state_union_covers_all_anomalies(live_diff):
    """三态清单并集覆盖 ch08→ch03(10) + ch12→ch05(2) 全部条目，无遗漏无重复。"""
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
    """反向自检：若 ch12→ch05 出现未登记的第三条，集合相等断言必失败。

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
