#!/usr/bin/env python
"""check_wp_version_trail.py — 版本链集成守卫

确保 D~N 循环全部底稿主入口组件已接入版本链（useWorkpaperVersionToolbar +
GtWpVersionTrail），防止新增底稿遗漏集成。

检测两个必备标记：
  1. useWorkpaperVersionToolbar — composable 导入或调用
  2. GtWpVersionTrail — template 中挂载版本轨迹组件

用法：
  python backend/scripts/check/check_wp_version_trail.py            # 报告模式（退出码 0）
  python backend/scripts/check/check_wp_version_trail.py --strict   # CI 严格模式（有违规退出码 1）

设计为零依赖（仅标准库），可在 CI 与 pre-commit 直接运行。
参照 check_wp_ref_contract.py 风格。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ─── Windows GBK 安全 ────────────────────────────────────────────────────────
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except (AttributeError, ValueError):
    pass

# ─── 路径定位 ─────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[3]
WP_DIR = REPO_ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
WHITELIST_PATH = Path(__file__).resolve().parent / "version_trail_whitelist.txt"

# ─── 主入口识别正则 ──────────────────────────────────────────────────────────
# 匹配 Gt{D-N}{Digit(s)}*.vue（直接子文件，非子目录）
# 例：GtD3PrepaidAccounts.vue, GtE1CashAndBank.vue, GtG14xxx.vue
_RE_MAIN_ENTRY = re.compile(r"^Gt[D-N]\d+.*\.vue$")

# ─── 必备标记 ─────────────────────────────────────────────────────────────────
MARKER_COMPOSABLE = "useWorkpaperVersionToolbar"
MARKER_COMPONENT = "GtWpVersionTrail"


def load_whitelist(path: Path) -> set[str]:
    """加载白名单文件，返回豁免文件名集合。

    格式：每行一个文件名，# 开头为注释，空行跳过。
    文件不存在视为空白名单。
    """
    if not path.is_file():
        return set()
    whitelist: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        whitelist.add(stripped)
    return whitelist


def scan_file(path: Path) -> tuple[bool, bool]:
    """检测文件是否含两个必备标记。

    Returns:
        (has_composable, has_component)
    """
    try:
        content = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        # 读取失败视为无标记，由调用方决定如何处理
        return (False, False)
    has_composable = MARKER_COMPOSABLE in content
    has_component = MARKER_COMPONENT in content
    return (has_composable, has_component)


def find_main_entries(wp_dir: Path) -> list[Path]:
    """扫描 workpaper/ 直接子文件，识别 D~N 循环主入口组件。"""
    entries: list[Path] = []
    if not wp_dir.is_dir():
        return entries
    for item in sorted(wp_dir.iterdir()):
        if item.is_file() and _RE_MAIN_ENTRY.match(item.name):
            entries.append(item)
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(
        description="版本链集成守卫：检测 D~N 循环主入口是否已接入 version trail"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="严格模式：检测到违规时退出码 1（用于 CI）",
    )
    args = parser.parse_args()

    if not WP_DIR.is_dir():
        print(f"::warning::未找到 workpaper 目录 {WP_DIR}，跳过检查")
        return 0

    whitelist = load_whitelist(WHITELIST_PATH)
    entries = find_main_entries(WP_DIR)

    if not entries:
        print("::warning::未找到任何 D~N 主入口组件，跳过检查")
        return 0

    violations: list[tuple[str, str]] = []  # (filename, missing_description)
    compliant = 0
    whitelisted_count = 0

    for entry in entries:
        fname = entry.name
        if fname in whitelist:
            whitelisted_count += 1
            continue

        has_composable, has_component = scan_file(entry)

        if has_composable and has_component:
            compliant += 1
            continue

        # 构建缺失描述
        missing: list[str] = []
        if not has_composable:
            missing.append(MARKER_COMPOSABLE)
        if not has_component:
            missing.append(MARKER_COMPONENT)
        violations.append((fname, " + ".join(missing)))

    # ─── 输出结果 ─────────────────────────────────────────────────────────
    total = len(entries)
    print(f"扫描 D~N 主入口组件：{total} 个")
    print(f"  已接入：{compliant} 个")
    print(f"  白名单豁免：{whitelisted_count} 个")
    print(f"  违规：{len(violations)} 个")
    print()

    if violations:
        print("未接入版本链的组件：")
        for fname, missing_desc in violations:
            rel = f"audit-platform/frontend/src/components/workpaper/{fname}"
            print(f"  {rel}  [缺少 {missing_desc}]")
        print()
        print(
            "修复：参照 GtD2AccountsReceivable.vue 执行 5 步标准接入\n"
            "  1. import useWorkpaperVersionToolbar + defineAsyncComponent GtWpVersionTrail\n"
            "  2. call composable(wpId, projectId)\n"
            "  3. 保存成功后 scheduleAutoSnapshot()\n"
            "  4. template 末尾 mount <GtWpVersionTrail />\n"
            "  5. provide versionTrailRef + openVersionHistory"
        )

        if args.strict:
            print(f"\n::error::版本链集成守卫失败：{len(violations)} 个组件未接入")
            return 1
        print("\n（报告模式：未阻断。--strict 将 fail）")
        return 0

    print("[OK] 版本链集成守卫通过：所有 D~N 主入口已接入 version trail")
    return 0


if __name__ == "__main__":
    sys.exit(main())
