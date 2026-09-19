"""修复 `HiFourTableSourcePanel` 用 `v-if` 插进 `v-if/v-else-if` 链中间的平台级 P0。

**缺陷**

12 个宿主（H5~H10 / I1~I6）把溯源面板写成::

    <XTabIndex           v-if="currentSheet === 'X'" />
    <CycleTabProcedure   v-else-if="currentSheet === 'XA'" />
    <HiFourTableSourcePanel v-if="props.htmlData?.hi_extraction_enabled" />   ← 断链
    <XTabAdjudication    v-else-if="currentSheet === 'X-1'" />
    <XTabDetail          v-else-if="currentSheet === 'X-2'" />
    ...

`v-if` 开启**新链**：`hi_extraction_enabled` 为真时面板胜出，
它**之后的全部 `v-else-if` 成为死分支** → 审定表 / 两个披露 Tab / 各明细表
**一律渲染不出来**（页面只剩顶部工具栏 + 溯源面板 + 编制指导）。

`HI_CYCLE_FOUR_TABLE_EXTRACTION_ENABLED` 于 2026-08-02 翻为 True 后立刻全量生效。
`get_diagnostics`(Volar) / vitest / Vite transform 全部查不出 —— Vue 编译器对
「v-if 打断 v-else-if 链」不报错（语法完全合法），只有浏览器打开才暴露。

**修法**（保持原意：面板在审定表页、位于审定表内容之上）::

    <template v-else-if="currentSheet === 'X-1'">
      <HiFourTableSourcePanel v-if="props.htmlData?.hi_extraction_enabled" ... />
      <XTabAdjudication ... />
    </template>

`<template v-else-if>` 续上原链，面板作为其子节点不再参与分发。

用法::

    python backend/scripts/fix/fix_hi_source_panel_vif_chain.py --check
    python backend/scripts/fix/fix_hi_source_panel_vif_chain.py --dry-run
    python backend/scripts/fix/fix_hi_source_panel_vif_chain.py --apply

spec: .kiro/specs/h-cycle-four-table-extraction-and-account-mapping/
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WP_DIR = REPO_ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"

PANEL = "HiFourTableSourcePanel"
PANEL_VIF = 'v-if="props.htmlData?.hi_extraction_enabled"'


def _find_block(lines: list[str], start: int) -> int:
    """返回自闭合标签块的结束行索引（含）。"""
    for i in range(start, min(start + 40, len(lines))):
        stripped = lines[i].rstrip()
        if stripped.endswith("/>") or stripped.endswith(">") and i > start:
            if stripped.endswith("/>"):
                return i
    return start


def _indent_of(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def plan_file(path: Path) -> tuple[str, str] | None:
    """返回 ``(原文, 新文)``；无需改动返回 None。"""
    src = path.read_text(encoding="utf-8")
    if PANEL not in src or PANEL_VIF not in src:
        return None

    lines = src.splitlines(keepends=False)

    # 1. 定位面板块
    panel_start = None
    for i, line in enumerate(lines):
        if re.search(r"<" + PANEL + r"\b", line):
            panel_start = i
            break
    if panel_start is None:
        return None

    panel_end = _find_block(lines, panel_start)
    panel_block = lines[panel_start : panel_end + 1]
    if not any(PANEL_VIF in l for l in panel_block):
        return None  # 已是 v-if 以外的形态（可能已修）

    # 2. 面板之前必须已有 v-if/v-else-if（否则它本就是链首，不算断链）
    before = "\n".join(lines[:panel_start])
    if not re.search(r"\bv-(?:if|else-if)=", before):
        return None

    # 3. 紧随其后的兄弟必须是 v-else-if（被打死的第一个分支）
    sib_start = panel_end + 1
    while sib_start < len(lines) and not lines[sib_start].strip():
        sib_start += 1
    if sib_start >= len(lines) or not lines[sib_start].strip().startswith("<"):
        return None
    sib_end = _find_block(lines, sib_start)
    sib_block = lines[sib_start : sib_end + 1]
    sib_text = "\n".join(sib_block)
    m = re.search(r'v-else-if="([^"]+)"', sib_text)
    if not m:
        return None
    condition = m.group(1)

    base_indent = _indent_of(lines[panel_start])
    inner = base_indent + "  "

    def reindent(block: list[str]) -> list[str]:
        out = []
        for l in block:
            if not l.strip():
                out.append(l)
            else:
                out.append(inner + l[len(base_indent):] if l.startswith(base_indent) else inner + l.lstrip())
        return out

    # 兄弟块去掉 v-else-if（条件上移到 <template>）
    sib_no_cond: list[str] = []
    for l in sib_block:
        if f'v-else-if="{condition}"' in l:
            cleaned = l.replace(f'v-else-if="{condition}"', "").rstrip()
            # 整行只剩缩进则丢弃
            if not cleaned.strip():
                continue
            sib_no_cond.append(cleaned)
        else:
            sib_no_cond.append(l)

    new_block: list[str] = []
    new_block.append(f'{base_indent}<template v-else-if="{condition}">')
    new_block.extend(reindent(panel_block))
    new_block.extend(reindent(sib_no_cond))
    new_block.append(f"{base_indent}</template>")

    new_lines = lines[:panel_start] + new_block + lines[sib_end + 1 :]
    new_src = "\n".join(new_lines)
    if src.endswith("\n"):
        new_src += "\n"
    return src, new_src


def validate(new_src: str) -> list[str]:
    """校验：面板不得再作为链中间的裸 v-if 出现。"""
    problems: list[str] = []
    lines = new_src.splitlines()
    for i, line in enumerate(lines):
        if not re.search(r"<" + PANEL + r"\b", line):
            continue
        # 面板必须包在 <template v-else-if> 里（上溯 3 行）
        ctx = "\n".join(lines[max(0, i - 3) : i])
        if "<template v-else-if=" not in ctx and "<template v-if=" not in ctx:
            problems.append(f"line {i+1}: 面板未被 <template v-else-if> 包裹")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true", help="有欠账则 exit 1")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not WP_DIR.is_dir():
        print(f"[FAIL] 目录不存在: {WP_DIR}")
        return 2

    todo: list[tuple[Path, str, str]] = []
    for path in sorted(WP_DIR.glob("Gt*.vue")):
        planned = plan_file(path)
        if planned is None:
            continue
        old, new = planned
        if old != new:
            todo.append((path, old, new))

    if not todo:
        print("[OK] 无欠账：所有宿主的溯源面板都未打断 v-else-if 链")
        return 0

    print(f"[PLAN] {len(todo)} 个宿主需修复：")
    for path, old, new in todo:
        dead = len(re.findall(r"\bv-else-if=", old)) - len(re.findall(r"\bv-else-if=", new))
        print(f"  {path.name}（面板下方 v-else-if 链已断）")
        problems = validate(new)
        if problems:
            print(f"    [FAIL] 校验失败: {problems}")
            return 2

    if args.check:
        print(f"[FAIL] {len(todo)} 项欠账未修")
        return 1
    if not args.apply:
        print("[DRY-RUN] 未写盘（加 --apply 生效）")
        return 0

    for path, _old, new in todo:
        path.write_text(new, encoding="utf-8")
        print(f"[WRITE] {path.name}")
    print(f"[DONE] 已修 {len(todo)} 个宿主")
    return 0


if __name__ == "__main__":
    sys.exit(main())
