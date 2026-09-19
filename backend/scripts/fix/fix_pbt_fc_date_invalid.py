r"""修复平台级 PBT 陷阱：`fc.date()` 默认会生成 **Invalid Date** ⇒ 依赖日期的属性测试间歇假红/假绿。

spec: i-cycle-extraction-formula-and-disclosure-closure Task 24 补测轮（零回归时随机命中）

## 缺陷

fast-check **4.8.0** 实测（500 次采样）::

    fc.date({min, max})                      → Invalid Date 1 个（约 0.2%/例）
    fc.date({min, max, noInvalidDate: true}) → Invalid Date 0 个

PBT 每轮跑 100~200 例 ⇒ 单个 `fc.date()` 约 **20~40% 概率**至少命中一次 Invalid Date。

## 两种表现（一红一绿，后者更危险）

以 `useI6FormulaEngine.isCutoffCrossover` 为例，实现对无效日期返回 `false`（合理防御）：

* **P7b**「\|diff\| > 5 天 → 返回 true」 ⇒ Invalid Date 时实际 false ⇒ **间歇假红**
  （实测两次连跑：一次 12 passed、一次 1 failed，seed 分别 `2040901817` / `-864990073`）
* **P7**「\|diff\| ≤ 5 天 → 返回 false」 ⇒ Invalid Date 时**恰好**也返回 false ⇒ **假绿**
  （因错误原因通过 —— 与「守卫把错值当基线」同类，只是方向相反）

## 修法

给所有 `fc.date({...})` 加 `noInvalidDate: true`。**用括号配对定位参数区间**，
不用固定字符窗口（memory 铁律：截函数体/参数区禁固定窗口）。

若某处加了该选项后由绿变红，说明它此前是靠 Invalid Date 掩盖的**真缺陷**，需单独查。

用法::

    python backend/scripts/fix/fix_pbt_fc_date_invalid.py --check
    python backend/scripts/fix/fix_pbt_fc_date_invalid.py
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "audit-platform" / "frontend" / "src"
assert _SRC.is_dir(), f"frontend src missing: {_SRC}"

_NEEDLE = "fc.date("
_OPT = "noInvalidDate: true"


def _find_call_spans(text: str) -> list[tuple[int, int]]:
    """返回每个 `fc.date(` 调用的 (参数区起, 参数区止) —— 圆括号配对，跳过字符串。"""
    spans: list[tuple[int, int]] = []
    i = 0
    while True:
        k = text.find(_NEEDLE, i)
        if k < 0:
            break
        open_paren = k + len(_NEEDLE) - 1  # 指向 '('
        depth = 0
        j = open_paren
        quote: str | None = None
        while j < len(text):
            ch = text[j]
            if quote:
                if ch == "\\":
                    j += 2
                    continue
                if ch == quote:
                    quote = None
            elif ch in "'\"`":
                quote = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    spans.append((open_paren + 1, j))
                    break
            j += 1
        i = j + 1 if j > k else k + len(_NEEDLE)
    return spans


def _patch(text: str) -> tuple[str, int, int]:
    """返回 (新文本, 已补数, 已有数)。从后往前改以免偏移失效。"""
    spans = _find_call_spans(text)
    added = present = 0
    for start, end in reversed(spans):
        arg = text[start:end]
        if _OPT in arg:
            present += 1
            continue
        stripped = arg.strip()
        if not stripped.startswith("{"):
            # `fc.date()` 无参 → 补一个完整对象
            text = text[:start] + f"{{ {_OPT} }}" + text[end:]
            added += 1
            continue
        # 在对象字面量的 `{` 之后插入
        brace = start + arg.index("{") + 1
        text = text[:brace] + f" {_OPT}," + text[brace:]
        added += 1
    return text, added, present


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    total_added = total_present = 0
    touched: list[tuple[str, int, int]] = []
    problems: list[str] = []

    for p in sorted(_SRC.rglob("*")):
        if p.suffix != ".ts" or not (".spec." in p.name or ".test." in p.name):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if _NEEDLE not in text:
            continue
        new, added, present = _patch(text)
        total_added += added
        total_present += present
        if not added:
            continue
        rel = str(p.relative_to(_ROOT)).replace("\\", "/")
        touched.append((rel, added, present))
        if args.check:
            print(f"  待补 {added} 处（已有 {present} 处）  {rel}")
            continue
        p.write_text(new, encoding="utf-8")
        verify = p.read_text(encoding="utf-8")
        _, still, now_present = _patch(verify)
        if still:
            problems.append(f"写入后仍有 {still} 处缺 {_OPT}: {rel}")
        print(f"  FIXED {added} 处  {rel}（该文件现共 {now_present} 处带 {_OPT}）")

    print("\n===== 汇总 =====")
    verb = "待补" if args.check else "已补"
    print(f"{verb} {total_added} 处 / {len(touched)} 文件；本已合规 {total_present} 处")
    for rel, a, pr in touched:
        print(f"    +{a}（原有 {pr}）  {rel}")
    if problems:
        print(f"\n异常 {len(problems)} 条：")
        for x in problems:
            print(f"  - {x}")
        return 1
    if total_added == 0:
        print("无待补（幂等）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
