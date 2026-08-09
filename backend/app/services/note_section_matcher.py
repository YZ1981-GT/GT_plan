"""附注章节标题匹配器 —— 国企↔上市转换的章节配对判据。

spec: soe-listed-note-conversion-correctness / Requirements 5.1~5.5

------------------------------------------------------------------------------
🔴 本模块禁止引入相似度/模糊匹配（Requirement 5.1，守卫源码级断言）
------------------------------------------------------------------------------

实证（2026-08-05）：``财务报表主要项目注释``（soe 合并章）与
``母公司财务报表主要项目注释`` 的 ``SequenceMatcher`` 相似度 **0.87**，而真正需要
救回的 5 对措辞差异中最低的 ``研究开发支出`` ↔ ``研发支出`` 只有 **0.80**
⇒ 任何阈值都无法既救回 5 对又拦住这一对：

- 阈值 ≤ 0.80 → 合并章错配到母公司章（丢整章数据）
- 阈值 > 0.87 → 5 对措辞差异仍被判「各自独有」（源侧归档 + 目标侧新建空章 ⇒ 丢数据）

故只能**穷举配对**（:data:`SECTION_TITLE_ALIASES`）+ **禁止对清单**
（:data:`FORBIDDEN_MATCH_PAIRS`）。本模块**不提供**相似度接口。

------------------------------------------------------------------------------
归一化只去空白（Requirement 5.1）
------------------------------------------------------------------------------

虚词差异（的/和/与/、/或）**不做泛化替换**，全部由 ALIASES 逐条承载。理由：
泛化替换等价于一种隐式模糊匹配 —— 「所有权**和**使用权受限」与「所有权**或**使用权受限」
去掉虚词后相同是巧合，而「营业收入**、**营业成本」与「营业收入**和**营业成本」若按
「去掉全部标点与连词」归一，会连带把别的章节也归一到一起（如 soe
``递延所得税资产和递延所得税负债`` 与假想的 ``递延所得税资产`` 独立章）。

------------------------------------------------------------------------------
判据真源 = ``docs/模版/`` 两份源 docx（2026-08-06 按 Heading 样式逐条读取）
------------------------------------------------------------------------------

- listed: ``docs/模版/1.上市公司年审报表及附注-2026.01/1.上市公司年审报表及附注-2026.01/
  3.2025年度上市公司财务报表附注模板-2026.01.15.docx``
- soe: ``docs/模版/1、2025年度财务决算审计报告-2026.01.06/1、2025年度财务决算审计报告-国企/
  1.1-2025国企财务报表附注20260119.docx``

docx 章号是 Word 自动编号，段落文本**不含**「十二、」⇒ 定位章节必须按
``paragraph.style.name == 'Heading N'``，用章号正则会 0 命中。

🔴 **listed 母公司章标题实测为「公司财务报表主要项目注释」（无「母」字）**，
而 ``note_template_listed.json`` 写的是「母公司财务报表主要项目注释」
（spec ``parent-company-note-chapter-and-sourcing`` 已裁决保留 JSON 现值）
⇒ 禁止对必须**同时登记两种写法**，否则改一侧另一侧漏防。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

__all__ = [
    "AliasPair",
    "SECTION_TITLE_ALIASES",
    "FORBIDDEN_MATCH_PAIRS",
    "normalize_for_match",
    "match_section",
    "resolve_alias_counterpart",
]

_WHITESPACE = " \t\r\n\u3000\u00a0\u2002\u2003\u2009"


@dataclass(frozen=True)
class AliasPair:
    """一对语义相同但措辞不同的章节标题。

    Attributes:
        soe_title: 国企源 docx 中的标题原文
        listed_title: 上市源 docx 中的标题原文
        evidence: 源 docx 依据（两侧标题原文 + 差异说明）
    """

    soe_title: str
    listed_title: str
    evidence: str


#: 穷举配对清单（Requirement 5.2）。每条 evidence 为源 docx 两侧标题原文。
#:
#: 🔴 新增条目必须先在源 docx 里逐字核对两侧标题，禁止凭「看起来是同一个意思」添加。
SECTION_TITLE_ALIASES: Final[tuple[AliasPair, ...]] = (
    AliasPair(
        soe_title="财务报表编制基础",
        listed_title="财务报表的编制基础",
        evidence=(
            "源 docx Heading 1：soe「财务报表编制基础」/ listed「财务报表的编制基础」"
            "；差异 = 多一个结构助词「的」"
        ),
    ),
    AliasPair(
        soe_title="递延所得税资产和递延所得税负债",
        listed_title="递延所得税资产与递延所得税负债",
        evidence=(
            "源 docx：soe Heading 3「递延所得税资产和递延所得税负债」/ "
            "listed Heading 2「递延所得税资产与递延所得税负债」；差异 = 和/与"
        ),
    ),
    AliasPair(
        soe_title="所有权和使用权受到限制的资产",
        listed_title="所有权或使用权受到限制的资产",
        evidence=(
            "源 docx：soe Heading 3「所有权和使用权受到限制的资产」/ "
            "listed Heading 2「所有权或使用权受到限制的资产」；差异 = 和/或"
        ),
    ),
    AliasPair(
        soe_title="营业收入、营业成本",
        listed_title="营业收入和营业成本",
        evidence=(
            "源 docx：soe Heading 3「营业收入、营业成本」/ "
            "listed Heading 2「营业收入和营业成本」；差异 = 顿号/和"
        ),
    ),
    AliasPair(
        soe_title="研究开发支出",
        listed_title="研发支出",
        evidence=(
            "源 docx：soe Heading 3「研究开发支出」（会计政策章）/ "
            "listed Heading 2「研发支出」；差异 = 全称/简称，"
            "两侧措辞差异大于禁止匹配对的标题差异，任何阈值法都无法既救回本对又拦住禁止对"
        ),
    ),
)


#: 禁止匹配对（Requirement 5.3）—— 相似度高但语义不同，必须人工钉死。
#:
#: 元素为 ``(soe_title, listed_title, reason)``。匹配方向无关：任一侧出现在对里即拒绝。
FORBIDDEN_MATCH_PAIRS: Final[tuple[tuple[str, str, str], ...]] = (
    (
        "财务报表主要项目注释",
        "公司财务报表主要项目注释",
        "soe 第五章是**合并**口径章节（93 子节）；listed 第十六章是**母公司**口径"
        "（源 docx Heading 1 原文「公司财务报表主要项目注释」，无「母」字，57 表）。"
        "标题差异仅一个限定词，比需要救回的措辞差异对更相似，故阈值法结构性不可行"
        "，故阈值法必然二者取一。配错会把整章合并数据落到母公司章。",
    ),
    (
        "财务报表主要项目注释",
        "母公司财务报表主要项目注释",
        "同上一条，但用 note_template_listed.json 里的现值写法（带「母」字）。"
        "spec parent-company-note-chapter-and-sourcing 已裁决保留 JSON 现值 ⇒ "
        "两种写法都要登记，否则改一侧另一侧漏防。",
    ),
)


def normalize_for_match(title: str | None) -> str:
    """归一化章节标题 —— **仅去除空白字符**（Requirement 5.1）。

    不做虚词替换、不做全半角转换、不做大小写折叠：虚词差异由
    :data:`SECTION_TITLE_ALIASES` 逐条承载。

    ``None`` / 非字符串 → 空串。
    """
    if not isinstance(title, str):
        return ""
    return title.strip().translate({ord(c): None for c in _WHITESPACE})


def _forbidden_key_pairs() -> frozenset[tuple[str, str]]:
    """禁止对的归一化键集合（双向）。"""
    out: set[tuple[str, str]] = set()
    for soe, listed, _reason in FORBIDDEN_MATCH_PAIRS:
        a, b = normalize_for_match(soe), normalize_for_match(listed)
        out.add((a, b))
        out.add((b, a))
    return frozenset(out)


def _alias_key_pairs() -> frozenset[tuple[str, str]]:
    """别名对的归一化键集合（双向）。"""
    out: set[tuple[str, str]] = set()
    for pair in SECTION_TITLE_ALIASES:
        a = normalize_for_match(pair.soe_title)
        b = normalize_for_match(pair.listed_title)
        out.add((a, b))
        out.add((b, a))
    return frozenset(out)


_FORBIDDEN_KEYS: Final = _forbidden_key_pairs()
_ALIAS_KEYS: Final = _alias_key_pairs()


def match_section(soe_title: str | None, listed_title: str | None) -> bool:
    """判定两个章节标题是否指同一章节。

    判定顺序（**禁止对优先于一切**）：

    1. 命中 :data:`FORBIDDEN_MATCH_PAIRS` → ``False``
    2. 归一化后精确相等 → ``True``
    3. 命中 :data:`SECTION_TITLE_ALIASES` → ``True``
    4. 其余 → ``False``

    空标题一律 ``False``（不把两个空标题当同一章）。
    """
    a = normalize_for_match(soe_title)
    b = normalize_for_match(listed_title)
    if not a or not b:
        return False
    if (a, b) in _FORBIDDEN_KEYS:
        return False
    if a == b:
        return True
    return (a, b) in _ALIAS_KEYS


def resolve_alias_counterpart(title: str | None, target_side: str) -> str | None:
    """取某标题在对侧的别名写法。

    Args:
        title: 源侧标题
        target_side: ``"soe"`` 或 ``"listed"``

    Returns:
        对侧标题原文；无别名（含精确同名情形）返回 ``None``。
    """
    if target_side not in ("soe", "listed"):
        return None
    key = normalize_for_match(title)
    if not key:
        return None
    for pair in SECTION_TITLE_ALIASES:
        soe_k = normalize_for_match(pair.soe_title)
        listed_k = normalize_for_match(pair.listed_title)
        if target_side == "listed" and key == soe_k:
            return pair.listed_title
        if target_side == "soe" and key == listed_k:
            return pair.soe_title
    return None
