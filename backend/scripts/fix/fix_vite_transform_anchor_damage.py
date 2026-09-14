"""修复批量插入脚本造成的 22 个 Vite transform 崩溃（锚点定位缺陷遗留损坏）。

四类损坏，均由「用字符/正则找插入锚点、未做括号配对」的批量脚本造成：

  A) 11 个 GtK{3..13}*.vue —— `:tb-source-codes="tbSourceCodes"` 被插入到
     `@navigate-sheet="(s: string) => emit('navigate-sheet', s)"` 的箭头函数内部。
     缺陷成因：脚本把 arrow function `=>` 里的 `>` 误当成标签闭合符。
     症状：`Error parsing JavaScript expression: Did not expect a type annotation here. (1:3)`

  B) 6 个 k{8..13}/core/K*TabAdjudication.vue —— `tbSourceCodes?: Record<string, any> | null`
     被插入到 `prefill?: Array<{ ... }>` 的**内层对象**里，把闭合 `}>` 挤到下一行。
     缺陷成因：从后往前找 `}` 配 defineProps 的 `}>()`，命中了内层 `Array<{}>` 的 `}`。
     症状：`[vue/compiler-sfc] Unexpected token, expected ","`

  C) 4 个 h{1,2}/core/H*TabDisclosure*.vue —— `import WpAmountInput from '...'`
     被插入到一条**多行 import 语句**的中间（紧跟 `import {` 之后）。
     缺陷成因：用「最后一个 `^import ` 行」当锚点，命中了多行 import 的开头行。
     症状：`[vue/compiler-sfc] Unexpected keyword 'import'.`

  D) 1 个 GtF4AccountsPayable.vue —— `?? … ?? … || ''` 混用未加括号。
     症状：`Nullish coalescing operator(??) requires parens when mixing with logical operators.`

用法：
    python backend/scripts/fix/fix_vite_transform_anchor_damage.py --check   # 只报告
    python backend/scripts/fix/fix_vite_transform_anchor_damage.py           # 实际修复

幂等：已修复的文件再次运行报「无待修」。修完做反向自检（破损形态必须消失、目标形态必须存在）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_WP = _ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
assert _WP.is_dir(), f"workpaper dir missing: {_WP}"

# ─────────────────────────── 组 A ───────────────────────────
GROUP_A_FILES = [
    "GtK3OtherPayables.vue",
    "GtK4OtherCurrentLiabilities.vue",
    "GtK5Provisions.vue",
    "GtK6HeldForSale.vue",
    "GtK7DeferredIncome.vue",
    "GtK8SellingExpenses.vue",
    "GtK9AdminExpenses.vue",
    "GtK10OtherIncome.vue",
    "GtK11AssetImpairmentLoss.vue",
    "GtK12NonOperatingIncome.vue",
    "GtK13NonOperatingExpense.vue",
]
A_BROKEN = (
    '          @navigate-sheet="(s: string) =          :tb-source-codes="tbSourceCodes"\n'
    "        > emit('navigate-sheet', s)\"\n"
)
A_FIXED = (
    "          @navigate-sheet=\"(s: string) => emit('navigate-sheet', s)\"\n"
    '          :tb-source-codes="tbSourceCodes"\n'
)

# ─────────────────────────── 组 B ───────────────────────────
GROUP_B_FILES = [f"k{n}/core/K{n}TabAdjudication.vue" for n in (8, 9, 10, 11, 12, 13)]
B_BROKEN = "   tbSourceCodes?: Record<string, any> | null\n}>\n"
B_FIXED = " }>\n  tbSourceCodes?: Record<string, any> | null\n"

# ─────────────────────────── 组 C ───────────────────────────
GROUP_C_FILES = [
    "h1/core/H1TabDisclosureListed.vue",
    "h1/core/H1TabDisclosureSoe.vue",
    "h2/core/H2TabDisclosureListed.vue",
    "h2/core/H2TabDisclosureSoe.vue",
]
C_IMPORT = "import WpAmountInput from '../../shared/WpAmountInput.vue'\n"
C_BROKEN = "import {\n" + C_IMPORT
C_FIXED = C_IMPORT + "import {\n"

# ─────────────────────────── 组 D ───────────────────────────
GROUP_D_FILE = "GtF4AccountsPayable.vue"
D_BROKEN = """  () => props.htmlData?.project_context?.bs_date
    ?? props.htmlData?.projectContext?.bs_date
    ?? formData.projectContext.value?.bs_date
    || '',
"""
D_FIXED = """  () => (props.htmlData?.project_context?.bs_date
    ?? props.htmlData?.projectContext?.bs_date
    ?? formData.projectContext.value?.bs_date)
    || '',
"""

PLAN: list[tuple[str, list[str], str, str]] = [
    ("A", GROUP_A_FILES, A_BROKEN, A_FIXED),
    ("B", GROUP_B_FILES, B_BROKEN, B_FIXED),
    ("C", GROUP_C_FILES, C_BROKEN, C_FIXED),
    ("D", [GROUP_D_FILE], D_BROKEN, D_FIXED),
]


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只报告，不写文件")
    args = ap.parse_args()

    fixed_total = 0
    already_total = 0
    problems: list[str] = []

    for group, files, broken, fixed in PLAN:
        print(f"\n===== 组 {group} ({len(files)} 个文件) =====")
        for rel in files:
            p = _WP / rel
            if not p.is_file():
                problems.append(f"[组{group}] 文件不存在: {rel}")
                print(f"  MISSING  {rel}")
                continue
            text = _read(p)
            n_broken = text.count(broken)
            n_fixed = text.count(fixed)

            if n_broken == 0 and n_fixed >= 1:
                already_total += 1
                print(f"  OK(已修)  {rel}")
                continue
            if n_broken == 0 and n_fixed == 0:
                problems.append(f"[组{group}] 既无破损形态也无目标形态（形态已变）: {rel}")
                print(f"  UNKNOWN  {rel}  ← 需人工确认")
                continue
            if n_broken != 1:
                problems.append(f"[组{group}] 破损形态命中 {n_broken} 次（期望 1）: {rel}")
                print(f"  AMBIG    {rel}  hits={n_broken}")
                continue

            if args.check:
                print(f"  待修      {rel}")
                fixed_total += 1
                continue

            new_text = text.replace(broken, fixed, 1)
            p.write_text(new_text, encoding="utf-8")

            # 反向自检：破损形态必须消失、目标形态必须出现
            verify = _read(p)
            if broken in verify:
                problems.append(f"[组{group}] 写入后破损形态仍在: {rel}")
            if fixed not in verify:
                problems.append(f"[组{group}] 写入后目标形态缺失: {rel}")
            fixed_total += 1
            print(f"  FIXED     {rel}")

    print("\n===== 汇总 =====")
    verb = "待修" if args.check else "已修"
    print(f"{verb}: {fixed_total} 个   本来就正确: {already_total} 个")
    if problems:
        print(f"\n异常 {len(problems)} 条：")
        for x in problems:
            print(f"  - {x}")
        return 1
    if fixed_total == 0:
        print("无待修文件（幂等）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
