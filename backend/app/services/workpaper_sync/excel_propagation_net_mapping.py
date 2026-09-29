# -*- coding: utf-8 -*-
"""多趟传播声明 → **净映射** 的合成（`excel_workbook_row_change` 的伴生模块）。

spec: d1-sync-row-table-engine-and-d1-coverage · Tasks 25~29 的整册门

═══ 为什么单独一个模块 ═══

「把多趟的累积效果合成一处引用的净位移」是一个**独立概念**，与
`excel_workbook_row_change` 里的「声明 / 应用 / 逆归一化」三段流程正交：
逆归一化要用它，将来 apply 侧若也需要合成视图同样要用它。
抽出来同时让宿主模块回落到行数门基线之下（门的首选处置是抽伴生模块）。

真源在本模块，`excel_workbook_row_change.net_propagation_pairs` 是薄转发。
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - 仅类型
    from app.services.workpaper_sync.excel_workbook_row_change import (
        WorkbookRowChangePlan,
    )

__all__ = ["net_propagation_pairs"]


def _shape(ref: str) -> str:
    """把引用文本里的数字串统一掩码，得到「形状」。

    同一条链的各步只有行号在变 ⇒ 形状恒等；不同 sheet 的同名 defined name
    形状不同（sheet 名与列标都不同）。
    """
    return re.sub(r"\d+", "#", ref)


def net_propagation_pairs(
    plan: "WorkbookRowChangePlan | Any", *, part: str
) -> dict[tuple[str, str], int]:
    """把一个 part 的传播声明合成**净映射** `{(ref_after, ref_before): 引用处数}`。

    ═══ 为什么需要「合成」这一步 ═══

    合并多趟 materialize 的声明（`merge_workbook_row_change_propagations`）之后，
    **同一处**引用被多趟各改一次就会留下一条链：

        locator `B12#0`：`D1-4!B23` → `B24`（第一趟）， `B24` → `B25`（第二趟）

    净效果是 `B23 ⇒ B25`。而链里的中间态 `B24` 同时可能是**另一处**引用（locator
    `B13#0`）的起点 —— 纯按文本看两者无法区分，这正是串行逆替换会串台的根因：

        ① `B26→B25` ⇒ B13 变 B25，此刻 **B12 与 B13 都是 B25**（信息已丢）
        ② `B25→B24` ⇒ 两个一起变 B24
        ③ `B24→B23` ⇒ 两个一起变 B23 ⇒ B13 错成 B23（应为 B24）

    ═══ 分组键是两维，各自补对方的盲区（实测逼出来的，不是设计洁癖）═══

    * 只用 `locator` 不够：workbook-scope defined name 的 locator 对**所有 sheet**
      的同名条目是同一个（实测 `_xlnm.Print_Area#0` 一个 locator 底下 13 条，分属
      D1-3 / D1-4 / D1-9 / D1-10 / D1-15 / D1-16 各自的打印区）⇒ 串不成单链。
    * 只用「形状」不够：`审定表D1-1` 的 B12 与 B13 都引用 `D1-4!B{行}`，形状完全
      相同，但它们是两处**独立**引用（各有自己的链）⇒ 会被错并成一条 4 步链。

    ═══ fail-closed，不猜 ═══

    一个分组内若串不成单链（链头不唯一 / 有环 / 有断点），抛
    `PropagationDriftError` 而不是挑一条用 —— 声明不自洽时猜一个等于让被检查
    对象自己声明自己合法（design.md 明确拒绝的方案）。

    Returns:
        `{(净 ref_after, 净 ref_before): 该净映射覆盖的引用处数}`。处数用于与逆替换的
        实际出现次数对账（见 `assert_propagation_declared_exactly`）：
        单趟时每个分组一步 ⇒ 处数 == 条目数，与本函数引入前逐字节等价。
    """
    from app.services.workpaper_sync.excel_workbook_row_change import (
        PropagationDriftError,
    )

    entries = [e for e in plan.propagations if e.part == part]
    if not entries:
        return {}

    by_group: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for entry in entries:
        by_group.setdefault((entry.locator, _shape(entry.ref_before)), []).append(
            (entry.ref_before, entry.ref_after)
        )

    pairs: dict[tuple[str, str], int] = {}
    for group, steps in by_group.items():
        if len(steps) == 1:
            net_before, net_after = steps[0]
        else:
            forward: dict[str, str] = {}
            for before, after in steps:
                if before in forward and forward[before] != after:
                    raise PropagationDriftError(
                        f"{part} 分组={group!r}：同一改前文本 {before!r} 被声明位移到"
                        f"两个不同目标（{forward[before]!r} 与 {after!r}）—— 声明不自洽"
                    )
                forward[before] = after
            afters = set(forward.values())
            heads = [b for b in forward if b not in afters]
            if len(heads) != 1:
                raise PropagationDriftError(
                    f"{part} 分组={group!r}：{len(steps)} 条声明串不成单链"
                    f"（链头候选 {heads!r}）—— 同一处引用的多趟位移必须首尾相接，"
                    "不自洽时不得挑一条用"
                )
            cursor = heads[0]
            net_before = cursor
            seen = {cursor}
            while cursor in forward:
                cursor = forward[cursor]
                if cursor in seen:
                    raise PropagationDriftError(
                        f"{part} 分组={group!r}：位移声明成环（{cursor!r}）"
                    )
                seen.add(cursor)
            net_after = cursor
        if net_before == net_after:
            raise PropagationDriftError(
                f"{part} 分组={group!r}：合成后的净位移改前改后逐字相同"
                f"（{net_before!r}）—— 多趟位移互相抵消不应进入传播清单"
            )
        key = (net_after, net_before)
        pairs[key] = pairs.get(key, 0) + 1
    return pairs
