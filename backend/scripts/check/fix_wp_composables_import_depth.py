#!/usr/bin/env python
"""fix_wp_composables_import_depth.py — 修复 workpaper 组件对 composables 的相对导入层级。

背景（2026-07-11 K 类底稿 Playwright 实测）：
  多个 `{cycle}/{sub}/*.vue` 底稿 tab 用 `../../../composables/`（3 级 → 解析到不存在的
  `src/components/composables/`），Vite transform 报 500「Failed to resolve import」→
  ErrorBoundary 崩溃。正确应为 `../../composables/`（2 级 → `workpaper/composables/`）。
  vitest/Volar 解析方式不同故未拦截，但浏览器运行时必崩。

本脚本对 `src/components/workpaper/` 下每个 .vue 文件：
  - 计算其相对 workpaper 根的目录深度 depth
  - composables 正确前缀 = ('../' * depth) + 'composables/'
  - 把 import/from 语句里任何 `(../)+composables/` 归一化为正确前缀

安全：以 UTF-8 显式读写，仅替换 ASCII 子串（`../` 与 `composables/`），不触碰中文。
用法：
  python backend/scripts/check/fix_wp_composables_import_depth.py            # dry-run 仅报告（退出码 0）
  python backend/scripts/check/fix_wp_composables_import_depth.py --apply    # 实际写回
  python backend/scripts/check/fix_wp_composables_import_depth.py --check    # CI 守卫：有错退出码 1
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
WP_DIR = REPO_ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
COMPOSABLES_DIR = WP_DIR / "composables"

# 命中 import ... from '<...>/composables/xxx' 中的相对前缀部分
_RE_IMPORT = re.compile(r"(from\s*['\"])((?:\.\./)+)composables/")


def correct_prefix(vue_path: Path) -> str:
    """该 .vue 文件到 workpaper/composables 的正确相对前缀。"""
    rel = vue_path.parent.relative_to(WP_DIR)
    depth = len(rel.parts)  # workpaper 根下的目录层数
    return "../" * depth


def main() -> int:
    apply = "--apply" in sys.argv
    check = "--check" in sys.argv
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    if not COMPOSABLES_DIR.is_dir():
        print(f"::error::composables 目录不存在 {COMPOSABLES_DIR}")
        return 1

    changed_files = 0
    total_repls = 0
    for vue in sorted(WP_DIR.rglob("*.vue")):
        # composables 目录自身跳过
        if COMPOSABLES_DIR in vue.parents:
            continue
        text = vue.read_text(encoding="utf-8")
        prefix = correct_prefix(vue)

        def _sub(m: re.Match) -> str:
            return f"{m.group(1)}{prefix}composables/"

        new_text, n = _RE_IMPORT.subn(_sub, text)
        if n == 0 or new_text == text:
            continue
        # 仅统计真正发生前缀变化的替换
        wrong = sum(1 for m in _RE_IMPORT.finditer(text) if m.group(2) != prefix)
        if wrong == 0:
            continue
        rel = vue.relative_to(REPO_ROOT).as_posix()
        print(f"{'FIX ' if apply else 'DRY '} {rel}  ({wrong} 处 → {prefix}composables/)")
        changed_files += 1
        total_repls += wrong
        if apply:
            vue.write_text(new_text, encoding="utf-8")

    if total_repls == 0:
        print("✅ workpaper composables 相对导入层级检查通过：无错误 ../ 深度")
        return 0

    print(
        f"\n{'已修复' if apply else '发现'}：{total_repls} 处，涉及 {changed_files} 个文件。"
        + ("" if apply else "  （dry-run，加 --apply 写回；--check 用于 CI 阻断）")
    )
    if check:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
