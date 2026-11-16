# -*- coding: utf-8 -*-
"""M 循环明细表**存储单一来源**守卫（spec `m-cycle-key-naming-unification` 任务 4）。

## 背景（2026-11-16 现算）

M 循环明细表曾经有两条并行写入通路：

1. **逐行 JSON**：`M{n}-2-row-${index}-data` / `M1-M1-2-row-${i}-data`（每行一个 item_id）；
2. **整表 JSON**：`M{n}-2-full-data` / `M1-M1-2-full-data`（一次性写全部行）。

两条都写 ⇒ 刷新时读哪条取决于 `_restoreRows` 的实现，而 M1/M2/M10 原来**只读整表**
（M3/M7 有逐行降级）⇒ 一旦整表那条没写成功，刷新明细全丢。

现算事实（不是推测）：M 组真库 34 行**全是** `M{n}-1-tb-amount` 审定表取数，
**明细表整表 JSON 形态 0 行** ⇒ 删掉整表通路不需要迁移任何存量数据。

## 本守卫锁定什么

**逐行 JSON 是唯一来源**：5 个 composable（M1/M2/M3/M7/M10）不得再出现
`*-full-data` 的写入。M9 例外 —— 它写的是 `M9-2-detail-rows`（不是 `full-data`），
且那是它自己的唯一来源。

## 为什么需要这条守卫

删除是**行为变更**（读侧从整表切到逐行）。若有人后续「为了保险」把整表写入加回来，
两条通路又会出现，刷新读哪条重新变得不确定 —— 而这个缺陷不会让任何既有测试变红
（它只在「整表写失败 + 刷新」时表现为数据丢失）。守卫让它在加回来的当次就红。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
_COMPOSABLES = (
    _ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper" / "composables"
)

#: 必须是「逐行 JSON 单一来源」的 composable。
#: 🔴 M9 刻意不在列：它的 `_syncFullData` 写 `M9-2-detail-rows`（不是 full-data），
#:    且那是 M9TabDetail `_initDefaultRows` 的唯一读取来源。
_SINGLE_SOURCE_COMPOSABLES = (
    "useM1Detail.ts",
    "useM2Detail.ts",
    "useM3Detail.ts",
    "useM7Detail.ts",
    "useM10Detail.ts",
)

#: 逐行写入的 item_id 模板（每行一条）。守卫同时要求这些**确实存在**，
#: 否则「删了整表」+「逐行也没写」= 数据根本存不下来，比两条通路更糟。
_ROW_KEY_PATTERNS = {
    "useM1Detail.ts": r"M1-M1-2-row-\$\{",
    "useM2Detail.ts": r"M2-M2-2-(?:listed|unlisted)-row-\$\{",
    "useM3Detail.ts": r"M3-M3-2-row-\$\{",
    "useM7Detail.ts": r"M7-2-row-\$\{",
    "useM10Detail.ts": r"M10-2-row-\$\{",
}


def _read(name: str) -> str:
    path = _COMPOSABLES / name
    assert path.exists(), f"{name} 不存在 —— 改名后必须同步本守卫"
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", _SINGLE_SOURCE_COMPOSABLES)
def test_no_whole_table_full_data_write(name: str) -> None:
    """5 个 composable 不得再写整表 `*-full-data`（逐行 JSON 是唯一来源）。"""
    src = _read(name)
    # 只看「写入」：debouncedSave('<key containing full-data>'
    writes = re.findall(r"debouncedSave\(\s*['\"]([^'\"]*full-data[^'\"]*)['\"]", src)
    assert not writes, (
        f"{name} 又写了整表 full-data: {writes}。\n"
        "逐行 JSON 已是唯一来源（spec m-cycle-key-naming-unification 任务 4）；"
        "加回整表通路会让「刷新读哪条」重新变得不确定，且这个缺陷不会让既有测试变红 ——"
        "所以这里直接打红。若确有新需求，先写裁决再改本守卫。"
    )
    # 函数名残留也算（`_syncFullData` 定义但没人调，说明改造没做完）
    assert "_syncFullData" not in src, (
        f"{name} 仍残留 `_syncFullData` —— 改造应删函数本体，不是只删调用点"
    )


@pytest.mark.parametrize("name", _SINGLE_SOURCE_COMPOSABLES)
def test_row_level_write_still_present(name: str) -> None:
    """逐行 JSON 写入必须仍在（删了整表却没写逐行 = 数据存不下来）。"""
    src = _read(name)
    pat = _ROW_KEY_PATTERNS[name]
    hits = re.findall(pat, src)
    assert hits, (
        f"{name} 找不到逐行写入（期望匹配 /{pat}/）。\n"
        "整表通路已删 ⇒ 逐行是唯一来源，它必须真的存在，否则明细数据无处落库。"
    )


def test_m9_keeps_its_own_single_source() -> None:
    """反向断言：M9 的 `M9-2-detail-rows` 是它的唯一来源，**不得**被「统一」掉。

    这条防的是「照着 5 个文件的样子把 M9 也删了」——M9 的键名不同（不是 full-data），
    删了 M9 就真的没有明细存储了。
    """
    src = _read("useM9Detail.ts")
    assert "M9-2-detail-rows" in src, (
        "M9 的 `M9-2-detail-rows` 写入消失了 —— 它是 M9TabDetail._initDefaultRows 的"
        "唯一读取来源，删掉等于 M9 明细无处落库"
    )
    assert "full-data" not in src.replace("full-data（保证", ""), (
        "M9 出现了真正的 full-data 键 —— 它应该只用 M9-2-detail-rows"
    )
