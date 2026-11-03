"""合并附注明细映射：表内同名行的分组判别（spec note-chain-followup-optimizations R3 / ADR-4）。

同一张表里同名行很常见（2026-10-29 真库单体附注 366 张表、990 个重复行名）：固定资产「一、账面原值合计 / 二、累计折旧合计…」
下各有「房屋、建筑物」，应收股利「账龄一年以内 / 一年以上」下各有「其中：（1）」。只按第几次出现配对，来源少一组或组序不同
就会配到别的组的行（而且算「精确」匹配、可自动确认）。分组键给配对一个与位置无关的判据，来源表与明细模板用同一函数算：

1. 一级分组头：「一、」「（一）」开头的行、冒号结尾的非合计行（「合营企业：」）；其后到下一个分组头之前的行属于它；
2. 同一分组里同名行仍不止一行：再加最近一个「表内唯一」的行名细分（「其中：」开头的成员不算）；
3. 仍分不开的（同一处结构重复）按组内顺序编号 —— 这类只能按位置配对，建议须人工复核。

分组键只做判别，不进结构指纹（与同名出现序号一样；否则已确认的企业全部变成「结构已变化」）。
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from typing import Any

__all__ = ["group_label", "row_groups"]

_L1_RE = re.compile(r"^(?:[一二三四五六七八九十]+[、．.]|[（(][一二三四五六七八九十]+[）)])")
_MEMBER_RE = re.compile(r"^其中[:：]")
#: 细分键「上级›锚点」的分隔符（行名里不会出现）
_SEP = "›"


def _text(label: Any) -> str:
    return "".join(str(label or "").split())


def _is_head(label: Any, row_type: str) -> bool:
    text = _text(label)
    if not text or _MEMBER_RE.match(text):
        return False
    if _L1_RE.match(text):
        return True
    return row_type not in ("total", "subtotal") and text.endswith(("：", ":"))


def row_groups(labels: Sequence[Any], row_types: Sequence[Any] | None = None) -> list[tuple[str, int]]:
    """表内每行的 ``(分组键, 组内同名序号)``；分组键是行名比较键（``_label_key``），细分用「上级/锚点」。"""
    from app.services.consol_note_detail_suggest import _label_key

    types = [str(t or "data") for t in (row_types or [])]
    keys = [_label_key(label) for label in labels]
    unique = {k for k, n in Counter(k for k in keys if k).items() if n == 1}
    heads = [_is_head(label, types[i] if i < len(types) else "data") for i, label in enumerate(labels)]
    level1: list[str] = []
    current = ""
    for i, key in enumerate(keys):
        if heads[i]:
            current = key
            level1.append("")  # 分组头本身在顶层
        else:
            level1.append(current)
    crowded = {pair for pair, n in Counter((k, g) for k, g in zip(keys, level1) if k).items() if n > 1}
    groups: list[str] = []
    anchor = ""
    for i, key in enumerate(keys):
        if heads[i]:
            anchor = ""
            groups.append("")
            continue
        groups.append(f"{level1[i]}{_SEP}{anchor}" if (key, level1[i]) in crowded and anchor else level1[i])
        if key in unique and not _MEMBER_RE.match(_text(labels[i])):
            anchor = key
    seen: Counter[tuple[str, str]] = Counter()
    out: list[tuple[str, int]] = []
    for key, group in zip(keys, groups):
        out.append((group, seen[(key, group)]))
        seen[(key, group)] += 1
    return out


def group_label(group: Any) -> str:
    """分组键 → 给人看的写法：「一、账面原值合计」「二、将重分类进损益的其他综合收益 · 2、其他债权投资公允价值变动」。"""
    return " · ".join(part for part in str(group or "").split(_SEP) if part)
