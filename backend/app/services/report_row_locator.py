"""报表关键行按行名定位（spec citar-report-analysis §2.1）。

报表行编码随模板而变：国企单体「流动资产合计」是 BS-027、上市单体是 BS-018；
IS-017 在国企是「▲赔付支出净额」、在上市是「资产减值损失」。写死编码取数会静默取错行
（财务比率曾把「其中：原材料」当流动资产、跨表核对曾把「▲保单红利支出」当净利润）。

行名在两版模板里稳定，故按规范化后的行名定位。财务比率、变动分析、跨表核对共用本模块。
"""

from __future__ import annotations

import re
from typing import Any, Iterable

# 开头序号：一、 （一） 1. 1、 四、 等；以及「减：」「加：」「其中：」等前缀
_LEADING_NO = re.compile(r"^(?:[一二三四五六七八九十]+、|[（(][一二三四五六七八九十]+[）)]|\d+[.、．])")
_PREFIX = re.compile(r"^(?:减|加|其中)[:：]")
# 括号说明：(亏损以“-”号填列) （净亏损以“－”号填列）
_PAREN = re.compile(r"[（(][^（()）]*[）)]")
_MARKS = re.compile(r"[△▲#☆★*]")


def normalize_row_name(name: str | None) -> str:
    """去空白、标记、开头序号、减/加/其中前缀与括号说明。"""
    text = re.sub(r"\s+", "", str(name or ""))
    text = _MARKS.sub("", text)
    # 序号与前缀可能叠加（「减：」后跟序号的写法少见，循环两次足够）
    for _ in range(2):
        text = _LEADING_NO.sub("", text)
        text = _PREFIX.sub("", text)
    return _PAREN.sub("", text)


#: 语义键 → (精确名集合, 前缀集合, 是否要求顶层行 indent_level == 0)
_RULES: dict[str, tuple[frozenset[str], tuple[str, ...], bool]] = {
    "cash": (frozenset({"货币资金"}), (), False),
    "accounts_receivable": (frozenset({"应收账款"}), (), False),
    "inventory": (frozenset({"存货"}), (), False),
    "current_assets": (frozenset({"流动资产合计"}), (), False),
    "total_assets": (frozenset({"资产总计", "资产合计"}), (), False),
    "current_liabilities": (frozenset({"流动负债合计"}), (), False),
    "total_liabilities": (frozenset({"负债合计"}), (), False),
    "total_equity": (
        # 「股东（或所有者）权益合计」去括号说明后即「股东权益合计」
        frozenset({"所有者权益合计", "股东权益合计"}),
        (),
        False,
    ),
    "revenue": (frozenset({"营业收入"}), (), False),
    "cost_of_sales": (frozenset({"营业成本"}), (), False),
    "profit_before_tax": (frozenset(), ("利润总额",), True),
    "income_tax": (frozenset({"所得税费用", "所得税"}), (), False),
    "net_profit": (frozenset(), ("净利润",), True),
    "equity_ending": (frozenset({"本年年末余额", "期末余额"}), (), True),
}

#: 语义键 → 中文名（溯源 / 原因提示用）
SEMANTIC_LABELS: dict[str, str] = {
    "cash": "货币资金",
    "accounts_receivable": "应收账款",
    "inventory": "存货",
    "current_assets": "流动资产合计",
    "total_assets": "资产总计",
    "current_liabilities": "流动负债合计",
    "total_liabilities": "负债合计",
    "total_equity": "所有者权益合计",
    "revenue": "营业收入",
    "cost_of_sales": "营业成本",
    "profit_before_tax": "利润总额",
    "income_tax": "所得税费用",
    "net_profit": "净利润",
    "equity_ending": "本年年末余额",
}


def _get(row: Any, attr: str) -> Any:
    if isinstance(row, dict):
        return row.get(attr)
    return getattr(row, attr, None)


def locate(rows: Iterable[Any], key: str) -> Any | None:
    """按语义键在报表行里找唯一行；多个命中取缩进最小者中的第一行，找不到返回 None。"""
    names, prefixes, top_only = _RULES[key]
    hits: list[tuple[int, int, Any]] = []
    for idx, row in enumerate(rows):
        indent = int(_get(row, "indent_level") or 0)
        if top_only and indent != 0:
            continue
        norm = normalize_row_name(_get(row, "row_name"))
        if not norm:
            continue
        if norm in names or any(norm.startswith(p) for p in prefixes):
            hits.append((indent, idx, row))
    if not hits:
        return None
    hits.sort(key=lambda h: (h[0], h[1]))
    return hits[0][2]
