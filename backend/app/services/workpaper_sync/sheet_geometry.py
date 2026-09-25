# -*- coding: utf-8 -*-
"""行表型受管 sheet 的几何纯函数 —— 框架层单一实现（收敛四份复制）。

spec: d1-sync-row-table-engine-and-d1-coverage · Task 5 · Requirements 1.4 / 4.2

═══ 为什么收敛这两个 ═══

`_snake`（camelCase → snake_case）与 `_col_index`（A1 列标 → 1-based 列序号）在 D2/D3/D6/D7
四家 provider 里**逐字节等价**（变量名有 char/ch、index/idx 之别，行为完全相同）。它们是纯
函数、无副作用、可穷举验证，是引擎抽取里风险最低、可先行收敛的一块（Task 5 排在阶段 1 首位
的理由）。四家改为从本模块 import，四份复制删除。

🔴 框架层纪律（需求 7.1 由 CI 卡点守）：本模块不感知任何具体 wp_code / adapter_id。它只做
两件纯几何的事，被 sheet 层与循环层调用，不反向依赖它们。

收敛后行为必须逐字节等价 —— golden digest 门（Task 1 的 23 个 digest）零变化即证。
"""
from __future__ import annotations

__all__ = ["snake", "col_index"]


def snake(camel: str) -> str:
    """camelCase → snake_case（`priorAudited` → `prior_audited`；`agingPrior` → `aging_prior`）。

    与四家 provider 原 `_snake` 逐字节等价：每遇大写字母插一个下划线并降为小写，其余原样。
    首字母若大写会产生前导下划线（`Foo` → `_foo`）—— 与原实现一致，调用方从不给首字母大写的键。
    """
    out: list[str] = []
    for ch in camel:
        if ch.isupper():
            out.append("_")
            out.append(ch.lower())
        else:
            out.append(ch)
    return "".join(out)


def col_index(letters: str) -> int:
    """A1 列标 → 1-based 列序号（`A` → 1，`Z` → 26，`AA` → 27，`AM` → 39）。

    与四家 provider 原 `_col_index` 逐字节等价（26 进制，`ord(ch) - 64`）。
    """
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch) - 64)
    return idx
