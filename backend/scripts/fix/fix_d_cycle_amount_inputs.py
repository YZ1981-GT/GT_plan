"""D 循环披露组件金额控件收敛为 `WpAmountInput`（幂等）—— spec Task 25。

用法::

    python backend/scripts/fix/fix_d_cycle_amount_inputs.py            # dry-run
    python backend/scripts/fix/fix_d_cycle_amount_inputs.py --check    # 欠账即非零退出
    python backend/scripts/fix/fix_d_cycle_amount_inputs.py --apply

🔴 **为什么必须换掉 `el-input-number`**（2026-07-29 平台双证，memory 铁律）

EP **2.13.6** 的 `node_modules/element-plus/es/components/input-number/**` 全文
**没有** `formatter` / `parser` prop —— 该 prop 不存在；浏览器实测输 1234567.5
显示 `1234567.50`（**无千分符**），换 `el-input` 才显示 `1,234,567.50`。

故平台单一真源 = `components/workpaper/shared/WpAmountInput.vue`（基于 `el-input`：
失焦千分符 / 聚焦原始值便于编辑 / 粘贴带逗号可解析 / 非法输入回退不写 NaN）。

🔴 **反向边界：非金额数值列不得套用** —— 比例 / 占比 / 率 / 账龄天数 / 年度 /
笔数 / 数量。本轮 63 处逐个核过邻近列头，**全部是金额列**（账面余额 / 坏账准备 /
计提 / 转回 / 核销 / 已质押金额 / 终止确认金额 / 变动金额 …），无一命中反向边界；
若将来有新增非金额列，守卫 `dCycleAmountControl.spec.ts` 会打红。

🔴 **`:precision="2"` 是 EP 真 prop 可保留**，`WpAmountInput` 亦支持同名 prop。

改造面（改造前计数）::

    d2/D2DisclosureNoteBody.vue   43
    d5/D5TabDisclosure.vue        14
    d7/D7TabDisclosure.vue         4
    d6/D6TabDisclosure.vue         2   （该文件已有 8 处 WpAmountInput，属部分迁移）
                                  ──
                                  63

spec: .kiro/specs/d-cycle-four-table-extraction-and-disclosure-completion/
      Requirements 9.1, 9.2, 9.3, 9.5 / Task 25
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
ROOT = BACKEND.parent
WP_DIR = ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"

TARGETS: tuple[str, ...] = (
    "d2/D2DisclosureNoteBody.vue",
    "d5/D5TabDisclosure.vue",
    "d7/D7TabDisclosure.vue",
    "d6/D6TabDisclosure.vue",
)

IMPORT_LINE = "import WpAmountInput from '@/components/workpaper/shared/WpAmountInput.vue'"

# 非金额语义（反向边界）—— 命中即拒绝改写并报错，交人工判断
NON_AMOUNT_HINTS: tuple[str, ...] = (
    "比例", "占比", "率", "账龄", "天数", "年度", "年份", "笔数", "数量", "个数", "期数",
)

TAG_RE = re.compile(r"<el-input-number\b[\s\S]*?(?:/>|</el-input-number>)")


def _near_label(src: str, pos: int) -> str:
    """取该标签前最近的 label（列头），用于反向边界判定。"""
    pre = src[max(0, pos - 900) : pos]
    labels = re.findall(r'label="([^"]{1,32})"', pre)
    return labels[-1] if labels else ""


def _convert_tag(tag: str) -> str:
    """`<el-input-number …/>` → `<WpAmountInput …/>`。

    只改标签名；属性逐字保留（`:model-value` / `:precision` / `size` / `class` /
    `style` / `@change` / `v-if` / `:disabled` 在 `WpAmountInput` 上同名可用）。
    `:controls="false"` 是 `el-input-number` 专属（`WpAmountInput` 基于 el-input
    本就无 controls），移除以免落成无意义的 HTML 属性。
    """
    out = tag.replace("<el-input-number", "<WpAmountInput", 1)
    out = out.replace("</el-input-number>", "</WpAmountInput>")
    out = re.sub(r'\s*:controls="false"', "", out)
    return out


def plan(rel: str) -> tuple[list[tuple[int, str]], list[str]]:
    """返回 (待改写标签 [(行号, near_label)], 反向边界告警)。"""
    src = (WP_DIR / rel).read_text(encoding="utf-8")
    todo: list[tuple[int, str]] = []
    warn: list[str] = []
    for m in TAG_RE.finditer(src):
        ln = src[: m.start()].count("\n") + 1
        near = _near_label(src, m.start())
        if any(k in near for k in NON_AMOUNT_HINTS):
            warn.append(f"{rel}:L{ln} near_label={near!r} 命中非金额语义 —— 拒绝改写，请人工确认")
            continue
        todo.append((ln, near))
    return todo, warn


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    total_todo = 0
    all_warn: list[str] = []
    per_file: dict[str, list[tuple[int, str]]] = {}

    for rel in TARGETS:
        p = WP_DIR / rel
        if not p.exists():
            print(f"[ERR] 文件不存在：{rel}")
            return 2
        todo, warn = plan(rel)
        per_file[rel] = todo
        all_warn.extend(warn)
        total_todo += len(todo)
        src = p.read_text(encoding="utf-8")
        print(
            f"[INFO] {rel}: el-input-number={len(TAG_RE.findall(src))} "
            f"待改写={len(todo)} 已有WpAmountInput={src.count('<WpAmountInput')}"
        )

    for w in all_warn:
        print(f"[WARN] {w}")

    print(f"[INFO] 合计待改写 = {total_todo}")

    if args.check:
        print(f"[CHECK] 欠账 {total_todo} 项")
        return 1 if total_todo else 0

    if not args.apply:
        print("[DRY-RUN] 未写回（加 --apply 生效）")
        return 0

    if total_todo == 0:
        print("[OK] 无欠账，文件未改动")
        return 0

    for rel in TARGETS:
        if not per_file[rel]:
            continue
        p = WP_DIR / rel
        src = p.read_text(encoding="utf-8")

        # 逐个替换（跳过命中反向边界的）
        def _repl(m: re.Match[str]) -> str:
            near = _near_label(src, m.start())
            if any(k in near for k in NON_AMOUNT_HINTS):
                return m.group(0)
            return _convert_tag(m.group(0))

        new_src = TAG_RE.sub(_repl, src)

        # 补 import（放在最后一条完整 import 语句之后；避开多行 import 内部）
        if "WpAmountInput" in new_src and IMPORT_LINE not in new_src:
            if "shared/WpAmountInput.vue'" not in new_src:
                lines = new_src.split("\n")
                last = -1
                for i, ln in enumerate(lines):
                    s = ln.strip()
                    if s.startswith("} from '") or (
                        s.startswith("import ") and " from '" in s and not s.endswith("{")
                    ):
                        last = i
                if last < 0:
                    print(f"[ERR] {rel}: 未找到完整 import 语句，拒绝写回")
                    return 2
                lines.insert(last + 1, IMPORT_LINE)
                new_src = "\n".join(lines)

        p.write_text(new_src, encoding="utf-8", newline="")
        print(f"[OK] {rel}: 已改写 {len(per_file[rel])} 处")

    # 结构性自检：不得出现「import { 紧跟 import」
    bad: list[str] = []
    for rel in TARGETS:
        lines = (WP_DIR / rel).read_text(encoding="utf-8").split("\n")
        for i, ln in enumerate(lines[:-1]):
            if ln.strip() == "import {" and lines[i + 1].lstrip().startswith("import "):
                bad.append(f"{rel}:L{i + 1}")
    if bad:
        print(f"[ERR] import 区被插断：{bad}")
        return 2

    print("[OK] 结构自检通过（无被插断的多行 import）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
