#!/usr/bin/env python
"""check_displayprefs_contract.py — 底稿显示偏好（DisplayPrefs）契约守卫

背景（platform-global-hardening Req 1.3 / 1.7）：
  全局显示偏好（金额单位/字号/小数位/密度/负数红字）的唯一真源是
  `useDisplayPrefsStore`（`stores/displayPrefs.ts`）。但大量底稿 tab 历史上写成
  `inject<{fmtAmount}>('displayPrefs', { 本地 toLocaleString 兜底实现 })`——一旦主入口
  provide 缺失或口径变化，tab 会退回自带的硬编码格式化（固定 2 位小数 / 固定「元」口径），
  导致全局设置对底稿失效。同理散落的 `font-size: 13px` 字面量绕过 `var(--wp-font-size)`
  CSS 变量传播，使全局字号设置无效。本守卫把这两条收敛铁律升级为 author-time / CI 门禁。

拦截两类**客观**反模式（正则可判、低误报）：

  A. inject('displayPrefs', {本地格式化实现})
     `inject(...)` 第一参数为字符串 `'displayPrefs'`，且第二参数是**含本地格式化实现**
     的对象字面量（对象体内出现 `toLocaleString` 或 `fmtAmount:` 函数实现）。
     放行：`inject(DisplayPrefs_Key, ...)`（类型化 key，非字符串）、
           `inject('displayPrefs', null)`（第二参非对象字面量，未内嵌 formatter）。

  B. 硬编码 font-size 字面量
     底稿 `<style>` / 模板内 `font-size: 13px`（及 11px/12px/14px）字面量。
     放行：`font-size: var(--wp-font-size, 13px)`（走 CSS 变量传播）。
     白名单：`stores/displayPrefs.ts` / `utils/formatters.ts`（FONT_SIZES 档位定义处）。

用法：
  python backend/scripts/check/check_displayprefs_contract.py            # 报告模式（退出码 0）
  python backend/scripts/check/check_displayprefs_contract.py --check    # 同上，显式报告模式
  python backend/scripts/check/check_displayprefs_contract.py --strict   # 严格模式（有违规退出码 1）

设计为零依赖（仅标准库），可在 CI 与 pre-commit 直接运行。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ─── 扫描范围 ────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[3]
WP_DIR = REPO_ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"

# 反模式 B 白名单（FONT_SIZES 档位真源定义处，允许字面量）
_WHITELIST_SUFFIXES = (
    "stores/displayPrefs.ts",
    "utils/formatters.ts",
)

# ─── 反模式 A：inject('displayPrefs', { ...含 formatter... }) ─────────────────
# 定位 inject 调用中第一参数为字符串 'displayPrefs' 且紧跟 `,` 后是对象字面量 `{`。
# 允许 inject 与 `(` 之间存在可选的 TS 泛型类型参数（如
# `inject<{ fmtAmount: (v: number) => string }>('displayPrefs', {...})`）——
# 泛型体内含 `=>` 箭头的 `>`，故用非贪婪 `[\s\S]*?` 匹配到紧邻 `(` 的 `>`。
_RE_INJECT_DISPLAYPREFS_OBJ = re.compile(
    r"""inject\s*(?:<[\s\S]*?>)?\s*\(\s*(['"])displayPrefs\1\s*,\s*\{""",
    re.MULTILINE,
)
# 对象字面量内「含本地格式化实现」的信号：toLocaleString 调用 或 fmtAmount: 函数键
_RE_LOCAL_FORMATTER = re.compile(r"toLocaleString|fmtAmount\s*[:(]")

# ─── 反模式 B：硬编码 font-size 字面量（紧跟冒号后即为 NNpx，非 var()）──────────
_RE_FONT_SIZE_LITERAL = re.compile(r"font-size\s*:\s*(1[1-4])px")


def _match_object_literal_end(text: str, open_brace_idx: int) -> int:
    """从 `{` 位置起做花括号配对，返回匹配 `}` 的下一位置索引（配对失败返回 len）。

    对字符串/注释不做完整词法分析（守卫场景够用），仅做朴素括号计数。
    """
    depth = 0
    i = open_brace_idx
    n = len(text)
    while i < n:
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def find_pattern_a(text: str) -> list[str]:
    """返回反模式 A 命中的对象字面量片段列表（每命中一处一条）。"""
    hits: list[str] = []
    for m in _RE_INJECT_DISPLAYPREFS_OBJ.finditer(text):
        # 对象字面量起始 `{` 是本次匹配的最后一个字符
        brace_idx = m.end() - 1
        end = _match_object_literal_end(text, brace_idx)
        obj_literal = text[brace_idx:end]
        if _RE_LOCAL_FORMATTER.search(obj_literal):
            snippet = obj_literal.strip().replace("\n", " ")
            if len(snippet) > 120:
                snippet = snippet[:117] + "..."
            hits.append(snippet)
    return hits


def find_pattern_b(text: str) -> list[tuple[int, str]]:
    """返回反模式 B 命中的 [(行号, 行内容)]（硬编码 font-size 字面量）。"""
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        # 允许 var(--wp-font-size, 13px)：该形态冒号后紧跟 var，不匹配下方正则
        if _RE_FONT_SIZE_LITERAL.search(line):
            hits.append((lineno, line.strip()))
    return hits


def scan_text(text: str) -> list[tuple[str, str]]:
    """对源码字符串扫描两类反模式，返回 [(kind, detail)] 违规列表。

    供属性测试直接调用（零 IO）。kind ∈ {'A', 'B'}。
    """
    violations: list[tuple[str, str]] = []
    for snippet in find_pattern_a(text):
        violations.append(("A", snippet))
    for lineno, content in find_pattern_b(text):
        violations.append(("B", f"{lineno}: {content}"))
    return violations


def scan_file(path: Path) -> list[tuple[str, str]]:
    """扫描单个文件；不可读文件 fail-open 返回空列表。"""
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    return scan_text(text)


def _is_whitelisted(path: Path) -> bool:
    posix = path.as_posix()
    return any(posix.endswith(sfx) for sfx in _WHITELIST_SUFFIXES)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="底稿显示偏好（DisplayPrefs）契约守卫")
    parser.add_argument("--check", action="store_true", help="报告模式（退出码恒 0，默认）")
    parser.add_argument(
        "--strict", action="store_true", help="严格模式：检出反模式时退出码 1"
    )
    args = parser.parse_args(argv)

    # Windows 控制台默认 GBK，输出中文会抛 UnicodeEncodeError；强制 utf-8。
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    if not WP_DIR.is_dir():
        print(f"::warning::未找到 workpaper 目录 {WP_DIR}，跳过检查")
        return 0

    total_violations = 0
    files_with_violations = 0
    for vue in sorted(WP_DIR.rglob("*.vue")):
        if _is_whitelisted(vue):
            continue
        v = scan_file(vue)
        if not v:
            continue
        files_with_violations += 1
        rel = vue.relative_to(REPO_ROOT).as_posix()
        for kind, detail in v:
            total_violations += 1
            label = "A(inject 本地 formatter)" if kind == "A" else "B(硬编码 font-size)"
            print(f"{rel}  [{label}]  {detail}")

    if total_violations:
        print(
            f"\n检测到 DisplayPrefs 契约违规：{total_violations} 处，涉及 "
            f"{files_with_violations} 个文件。\n"
            "修复 A：`inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()`，"
            "删除内嵌 toLocaleString/fmtAmount 本地实现（单一真源走 store）。\n"
            "修复 B：`font-size: var(--wp-font-size, 13px)`，删除散落的 13px/11px/12px/14px 字面量。"
        )
        if args.strict:
            return 1
        print("（报告模式：未阻断。CI 强制期后 --strict 将 fail）")
        return 0

    print("✅ DisplayPrefs 契约检查通过：无 inject 本地 formatter / 硬编码 font-size 反模式")
    return 0


if __name__ == "__main__":
    sys.exit(main())
