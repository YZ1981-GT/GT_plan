#!/usr/bin/env python
"""migrate_displayprefs_inject.py — 批量迁移底稿 tab 的 displayPrefs inject 模式。

背景（platform-global-hardening Req 1.3 / 1.5）：
  底稿 tab 原有写法：
    inject<{fmtAmount}>('displayPrefs', {硬编码 fallback})
  迁移为单一真源模式：
    inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

  同时替换散落的 `font-size: 13px` 字面量为 CSS 变量 `var(--wp-font-size, 13px)`
  （仅限 <style> 块内）。

安全：以 UTF-8 显式读写，仅结构化文本替换，不触碰中文内容。禁止 PowerShell。
沿用 `fix_wp_composables_import_depth.py` 范式。

用法：
  python backend/scripts/refactor/migrate_displayprefs_inject.py              # dry-run 仅报告（退出码 0）
  python backend/scripts/refactor/migrate_displayprefs_inject.py --check      # CI：有待迁移则退出码 1
  python backend/scripts/refactor/migrate_displayprefs_inject.py --apply      # 实际写回文件
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# ─── 路径 ──────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[3]
WP_DIR = REPO_ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
COMPOSABLES_DIR = WP_DIR / "composables"

# ─── 正则 ──────────────────────────────────────────────────────────────────────

# 匹配旧 inject 调用（可能含泛型参数、单/多行 fallback 对象）：
#   const displayPrefs = inject<...>('displayPrefs', { ... })
# 策略：匹配从 inject 开始到配平的闭括号，支持嵌套 {} 和多行
# 注意：泛型参数内可能含 `=>` 箭头，故用 `.*?` 而非 `[^>]*`
_RE_INJECT_START = re.compile(
    r"^(const\s+displayPrefs\s*=\s*)inject\s*(?:<.*?>)?\s*\(\s*['\"]displayPrefs['\"]",
    re.MULTILINE,
)

# 匹配 <style> 块内的 font-size: 13px（含可选空格）
_RE_FONT_SIZE_13 = re.compile(r"font-size:\s*13px")

# 检测已迁移标志
_ALREADY_MIGRATED = "DisplayPrefs_Key"

# 新 inject 写法
_NEW_INJECT = "inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()"

# 需要添加的 import 行
_IMPORT_DISPLAY_PREFS_KEY_TPL = "import {{ DisplayPrefs_Key }} from '{rel_path}composables/displayPrefsKey'"
_IMPORT_USE_STORE = "import { useDisplayPrefsStore } from '@/stores/displayPrefs'"


# ─── 工具函数 ──────────────────────────────────────────────────────────────────

def _find_balanced_paren(text: str, start: int) -> int:
    """从 text[start] 开始（应指向 '('），找到配平的 ')' 位置。"""
    depth = 0
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1  # 未找到


def _compute_rel_path(vue_path: Path) -> str:
    """计算 vue 文件到 workpaper/composables 的相对路径前缀（如 '../' * depth）。"""
    rel = vue_path.parent.relative_to(WP_DIR)
    depth = len(rel.parts)
    return "../" * depth


def _extract_style_ranges(text: str) -> list[tuple[int, int]]:
    """提取所有 <style ...> ... </style> 的范围。"""
    ranges = []
    for m in re.finditer(r"<style[^>]*>", text):
        start = m.end()
        end_m = re.search(r"</style>", text[start:])
        if end_m:
            ranges.append((start, start + end_m.start()))
    return ranges


def _in_style_block(pos: int, style_ranges: list[tuple[int, int]]) -> bool:
    """判断 pos 是否在某个 <style> 块内。"""
    for s, e in style_ranges:
        if s <= pos < e:
            return True
    return False


def _has_import(text: str, symbol: str) -> bool:
    """检测文件是否已有对 symbol 的 import 语句。"""
    # 只在 import 语句中查找，避免误匹配使用处
    return bool(re.search(rf"^import\s.*\b{re.escape(symbol)}\b", text, re.MULTILINE))


def _add_imports(text: str, vue_path: Path) -> str:
    """在适当位置添加 DisplayPrefs_Key 和 useDisplayPrefsStore 的 import。"""
    rel_path = _compute_rel_path(vue_path)
    lines_to_add = []

    if not _has_import(text, "DisplayPrefs_Key"):
        lines_to_add.append(
            _IMPORT_DISPLAY_PREFS_KEY_TPL.format(rel_path=rel_path)
        )
    if not _has_import(text, "useDisplayPrefsStore"):
        lines_to_add.append(_IMPORT_USE_STORE)

    if not lines_to_add:
        return text

    # 找最后一个 import 语句的行尾，在其后插入
    last_import_end = -1
    for m in re.finditer(r"^import\s.+$", text, re.MULTILINE):
        last_import_end = m.end()

    if last_import_end == -1:
        # 没有 import，找 <script setup> 标签后
        script_m = re.search(r"<script[^>]*setup[^>]*>", text)
        if script_m:
            last_import_end = script_m.end()
        else:
            last_import_end = 0

    insert_text = "\n" + "\n".join(lines_to_add)
    return text[:last_import_end] + insert_text + text[last_import_end:]


def _find_inject_call_paren(text: str, inject_pos: int) -> int:
    """找到 inject<...>( 或 inject( 的参数列表开括号。
    
    跳过可能存在的泛型参数 <...>（含嵌套尖括号和 => 箭头）。
    """
    i = inject_pos + len("inject")
    # 跳过空格
    while i < len(text) and text[i] in " \t\n\r":
        i += 1
    if i < len(text) and text[i] == "<":
        # 跳过泛型参数：需要配平尖括号，但忽略 => 中的 >
        depth = 0
        while i < len(text):
            ch = text[i]
            if ch == "<":
                depth += 1
            elif ch == ">":
                # 检查是否为 => 箭头（前一个字符是 =）
                if i > 0 and text[i - 1] == "=":
                    pass  # 这是 => 的一部分，不是闭合尖括号
                else:
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
            i += 1
    # 跳过空格
    while i < len(text) and text[i] in " \t\n\r":
        i += 1
    if i < len(text) and text[i] == "(":
        return i
    return -1


def migrate_inject(text: str) -> tuple[str, int]:
    """替换旧 inject('displayPrefs', {...}) 为新写法。返回 (新文本, 替换数)。"""
    count = 0
    result = text

    while True:
        m = _RE_INJECT_START.search(result)
        if not m:
            break

        # 找到 inject 关键字位置
        inject_pos = result.find("inject", m.start() + len(m.group(1)))
        if inject_pos == -1:
            break

        # 找到参数列表的开括号（跳过泛型 <...>）
        paren_start = _find_inject_call_paren(result, inject_pos)
        if paren_start == -1:
            break

        paren_end = _find_balanced_paren(result, paren_start)
        if paren_end == -1:
            break

        # 替换整个 inject(...) 调用（包括前面的 const displayPrefs = ）
        prefix = m.group(1)  # "const displayPrefs = "
        new_segment = f"{prefix}{_NEW_INJECT}"

        result = result[:m.start()] + new_segment + result[paren_end + 1:]
        count += 1

    return result, count


def migrate_font_size(text: str) -> tuple[str, int]:
    """在 <style> 块内替换 font-size: 13px → var(--wp-font-size, 13px)。
    
    返回 (新文本, 替换数)。
    """
    style_ranges = _extract_style_ranges(text)
    if not style_ranges:
        return text, 0

    count = 0
    offset = 0
    result = text

    for m in _RE_FONT_SIZE_13.finditer(text):
        pos = m.start()
        if not _in_style_block(pos, style_ranges):
            continue
        # 计算在 result 中的实际位置（考虑已有偏移）
        actual_start = pos + offset
        actual_end = m.end() + offset
        old = result[actual_start:actual_end]
        new = "font-size: var(--wp-font-size, 13px)"
        result = result[:actual_start] + new + result[actual_end:]
        offset += len(new) - len(old)
        count += 1

    return result, count


def process_file(vue_path: Path, apply: bool) -> tuple[int, int]:
    """处理单个文件。返回 (inject替换数, font-size替换数)。"""
    text = vue_path.read_text(encoding="utf-8")

    # 跳过已迁移的文件
    if _ALREADY_MIGRATED in text:
        return 0, 0

    # 执行 inject 迁移
    new_text, inject_count = migrate_inject(text)

    # 执行 font-size 迁移
    new_text, font_count = migrate_font_size(new_text)

    if inject_count == 0 and font_count == 0:
        return 0, 0

    # 如果有 inject 替换，添加必要的 import
    if inject_count > 0:
        new_text = _add_imports(new_text, vue_path)

    if apply:
        vue_path.write_text(new_text, encoding="utf-8")

    return inject_count, font_count


# ─── 主入口 ──────────────────────────────────────────────────────────────────

def main() -> int:
    apply = "--apply" in sys.argv
    check = "--check" in sys.argv

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    if not WP_DIR.is_dir():
        print(f"::error::workpaper 目录不存在 {WP_DIR}")
        return 1

    changed_files = 0
    total_inject = 0
    total_font = 0

    for vue in sorted(WP_DIR.rglob("*.vue")):
        # composables 目录自身跳过
        try:
            vue.relative_to(COMPOSABLES_DIR)
            continue
        except ValueError:
            pass

        try:
            inject_n, font_n = process_file(vue, apply)
        except (UnicodeDecodeError, OSError) as exc:
            # fail-open: 不可读文件跳过
            rel = vue.relative_to(REPO_ROOT).as_posix()
            print(f"SKIP {rel} ({exc.__class__.__name__})")
            continue

        if inject_n == 0 and font_n == 0:
            continue

        rel = vue.relative_to(REPO_ROOT).as_posix()
        parts = []
        if inject_n:
            parts.append(f"inject:{inject_n}")
        if font_n:
            parts.append(f"font-size:{font_n}")
        label = "FIX " if apply else "DRY "
        print(f"{label} {rel}  ({', '.join(parts)})")

        changed_files += 1
        total_inject += inject_n
        total_font += font_n

    # 汇总
    if total_inject == 0 and total_font == 0:
        print("[OK] displayPrefs 迁移检查通过：无待迁移的旧模式")
        return 0

    summary_parts = []
    if total_inject:
        summary_parts.append(f"inject 替换 {total_inject} 处")
    if total_font:
        summary_parts.append(f"font-size 替换 {total_font} 处")

    action = "已修复" if apply else "发现"
    print(
        f"\n{action}：{', '.join(summary_parts)}，涉及 {changed_files} 个文件。"
        + ("" if apply else "  （dry-run，加 --apply 写回；--check 用于 CI 阻断）")
    )

    if check:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
