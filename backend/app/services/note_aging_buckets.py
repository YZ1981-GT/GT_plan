"""账龄 / 期限区间行名 → 区间，判「来源区间落在模板哪一档」（spec note-table-structure-formula-pull-closure R6.3）。

合并附注模板的账龄档常比单体粗：国企合并「1年以内（含1年）/ 1至2年 / 2至3年 / 3年以上」，单体分到「3至4年 / 4至5年 /
5年以上」。原先单体多出的档要么被当成模板没有的行另起一行，要么按字面相似度模糊配到「3年以上」（须人工确认）。区间
包含是确定的：来源档整段落在模板唯一一档里 ⇒ 并到那一档（多档相加），可自动确认。

只认数字写法（「1年以内」「1至2年」「1-2年」「3年以上」「0-6个月」「90天以内」），中文数字与「其中：」「小计」行不认。
"""
from __future__ import annotations

import math
import re
from collections.abc import Sequence
from typing import Any

__all__ = ["bucket_interval", "containing_bucket"]

_WS = str.maketrans("", "", " \t\r\n\u3000")
_UNIT_DAYS = {"年": 365.0, "个月": 30.0, "月": 30.0, "天": 1.0, "日": 1.0}
_UNIT = r"(年|个月|月|天|日)"
#: 「（含1年）」「(不含3年)」这类括注不改变区间
_NOTE = r"(?:[（(][^）)]*[）)])?"
_WITHIN_RE = re.compile(rf"^(\d+(?:\.\d+)?){_UNIT}以内{_NOTE}$")
_RANGE_RE = re.compile(rf"^(\d+(?:\.\d+)?)[-－—–~～至到](\d+(?:\.\d+)?){_UNIT}{_NOTE}$")
_ABOVE_RE = re.compile(rf"^(\d+(?:\.\d+)?){_UNIT}以上{_NOTE}$")


def bucket_interval(label: Any) -> tuple[float, float] | None:
    """行名 → 左开右闭区间（天）；认不出 ⇒ None。「1年以内」=(0, 365]，「1至2年」=(365, 730]，「3年以上」=(1095, ∞)。"""
    text = str(label or "").translate(_WS).rstrip(":：")
    if m := _WITHIN_RE.fullmatch(text):
        return 0.0, float(m.group(1)) * _UNIT_DAYS[m.group(2)]
    if m := _RANGE_RE.fullmatch(text):
        lo, hi = float(m.group(1)) * _UNIT_DAYS[m.group(3)], float(m.group(2)) * _UNIT_DAYS[m.group(3)]
        return (lo, hi) if lo < hi else None
    if m := _ABOVE_RE.fullmatch(text):
        return float(m.group(1)) * _UNIT_DAYS[m.group(2)], math.inf
    return None


def containing_bucket(label: Any, candidates: Sequence[Any]) -> int | None:
    """``label`` 的区间整段落在哪个候选行里（候选行号）；落在几档里取最窄的一档（同宽取下限高的），
    分不出 / 一档都不含 ⇒ None。区间相同（「1年以内」与「1年以内（含1年）」）也算落在里面。"""
    own = bucket_interval(label)
    if own is None:
        return None
    best: tuple[tuple[float, float], int] | None = None
    tie = False
    for i, cand in enumerate(candidates):
        span = bucket_interval(cand)
        if span is None or not (span[0] <= own[0] and own[1] <= span[1]):
            continue
        narrow = (span[1] - span[0], -span[0])  # 「3年以上」与「5年以上」都含「6年以上」：取下限高的
        if best is None or narrow < best[0]:
            best, tie = (narrow, i), False
        elif narrow == best[0]:
            tie = True
    return None if best is None or tie else best[1]
