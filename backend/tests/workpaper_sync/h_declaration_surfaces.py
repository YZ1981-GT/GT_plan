# -*- coding: utf-8 -*-
"""**声明清单**面（不是运行时载体）—— 键命中统计要把它排除在「生产命中」之外。

spec: `h3-h5-h7-variant-axis-and-dynamic-column-paradigm`

═══ 为什么需要排除面 ═══════════════════════════════════════════════════════════

`sync/hManagedSheets.ts` 是受管 sheet 的单一声明点：它列出每张受管表的 `storeItemId`，
专供后端 `test_h_frontend_managed_sheet_parity` 逐字比对。它**不读写 store**（文件里零
`api.put` / `http.put` / `getString(` / `persist(`，只有 `readonly` 数据与纯函数），
所以出现在这里的键**不构成第二个运行时来源**。

不排除它会连锁打红三条本来正确的判据：

  · H5 的「`H5-2-rows` 字面量零命中」（HC-4 拼接解析）—— 声明清单登记的是**解析后**的
    真键，正是它该在的地方；
  · `test_dropping_the_concat_branch_would_false_red` 的变异分母；
  · H7 两键的「生产命中恰 1 家」（HC-6 第 4 条区分 BP-5 的判据）。

🔴 **这不是放宽**：排除面被钉死成**这一个文件**，且 `assert_declaration_only_surface`
   现场核验它确实不含任何读写形态 —— 谁把读写逻辑塞进声明清单，排除立刻失效。

═══ 为什么单独一个模块 ═══════════════════════════════════════════════════════════

`h_cycle_facts.py` 已到行数门禁上限（800）。拆伴生模块而非上调 whitelist 基线 ——
上调是「打磨让文件变大」，与门禁意图相反。
"""
from __future__ import annotations

import re
from typing import Final

#: 声明清单文件（相对前端 `src/` 的路径尾段，与 `h_cycle_facts.FrontendFile.rel` 同口径）。
DECLARATION_ONLY_SURFACES: Final[tuple[str, ...]] = (
    "components/workpaper/sync/hManagedSheets.ts",
)

#: 声明清单里**不得**出现的读写形态（出现即说明它变成了运行时载体）。
_CARRIER_WRITE_RE: Final[re.Pattern[str]] = re.compile(
    r"\b(?:api|http)\.(?:put|post|patch)\s*\(|\bpersist\s*\(|\bonSave\s*\?\.\s*\(|"
    r"\bgetString\s*\(|\bgetNum\s*\(|\ballResponses\b"
)


def assert_declaration_only_surface() -> None:
    """现场核验 `DECLARATION_ONLY_SURFACES` 里的文件确实只是声明、不读写 store。

    排除面的**前提**，判据侧应在用到排除前先调它（否则排除就成了无条件豁免）。

    🔴 `frontend_files` 走函数内延迟 import：`h_cycle_facts` 在模块顶部 import 本模块
    以取得排除面常量，顶层反向 import 会成环。
    """
    from tests.workpaper_sync.h_cycle_facts import frontend_files

    for rel in DECLARATION_ONLY_SURFACES:
        matches = [f for f in frontend_files() if f.rel == rel]
        assert matches, f"声明清单 {rel} 不存在 —— 排除面指向了一个不存在的文件"
        body = matches[0].text
        hit = _CARRIER_WRITE_RE.search(body)
        assert hit is None, (
            f"{rel} 出现了运行时载体形态 {hit.group(0)!r} —— 它不再是纯声明清单，"
            "键命中统计不能再把它排除"
        )
