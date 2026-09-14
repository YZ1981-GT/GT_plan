"""
check_standard_wp_code_re_single.py — CI grep-ban: 阻断新增 [A-I]\\d / [A-S]\\d 副本

CI 脚本，扫描 backend/ 下的 Python 源文件，检测标准底稿码判定正则
`[A-I]\\d` 或 `[A-S]\\d` 的重复定义。

目的：STANDARD_WP_CODE_RE 的单一定义在 grammar_v1.json（R12.1），
所有消费者应从 grammar_v1 import，不得在其他文件中重复硬编码。

允许的位置（白名单）：
  - backend/data/acnr/grammar_v1.json  (唯一权威定义)
  - backend/app/services/acnr/         (ACNR 服务层，import grammar_v1)
  - backend/scripts/acnr/              (ACNR CI 脚本自身)

已知遗留位置（需在 M1 task 8.1 迁移，暂时放行）：
  - backend/app/routers/wp_render_config.py   (将迁移至 grammar_v1 import)
  - backend/app/routers/wp_index_resolve.py   (将迁移至 grammar_v1 import)

排除范围：
  - backend/tests/         (测试文件)
  - 注释行（以 # 开头的行）

用法：
    python backend/scripts/acnr/check_standard_wp_code_re_single.py

退出码：
    0 = 无新增违规
    1 = 检测到新增副本

Validates: Requirements 12.3
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# 仓库根目录
REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"

# 精确检测模式：匹配用于"标准底稿码判定"的正则副本
# 目标模式：[A-I]\d 或 [A-S]\d（后面可选 +/*/?，但不跟其他字母如 A/[A-Z]）
# 排除：[A-S]\d+A（程序表名匹配）、[A-Z]\d（通用单字母匹配）等非标准码判定用途
#
# 具体匹配规则：
#   ✓ [A-I]\d   [A-I]\\d   [A-S]\d   [A-S]\\d
#   ✓ ^[A-I]\d  ^[A-S]\d   (带行首锚)
#   ✗ [A-S]\d+A （程序表匹配，后跟 A）
#   ✗ [A-Z]\d   （全字母范围，不是 I 或 S 上界）
#   ✗ [A-N]\d   （子范围，用于 wp_code 生成器策略等）
PRECISE_PATTERNS = [
    # [A-I]\d 或 [A-I]\\d —— 仅限上界为 I
    re.compile(r"""\[A-I\]\\*d(?!\d*[A-Z*])"""),
    # [A-S]\d 或 [A-S]\\d —— 仅限上界为 S，排除后面紧跟 +A 等程序表模式
    re.compile(r"""\[A-S\]\\*d(?!\d*\+?[A-Z])"""),
]

# ─── 白名单：允许包含这些模式的路径 ─────────────────────────────────────────────
# 相对于 BACKEND_DIR 的路径前缀（使用 / 分隔）
ALLOWED_PATHS: set[str] = {
    # 唯一权威定义
    "data/acnr/grammar_v1.json",
    # ACNR 服务层（从 grammar_v1 import）
    "app/services/acnr",
    # ACNR CI 脚本自身
    "scripts/acnr",
}

# 已知遗留位置（已完成迁移，保留空 dict 结构以备将来需要）
LEGACY_WHITELIST: dict[str, str] = {}

# 排除目录（相对于 BACKEND_DIR）
EXCLUDED_DIRS: set[str] = {
    "tests",
}


def _is_comment_line(line: str) -> bool:
    """判断是否为注释行（去除前导空格后以 # 开头）。"""
    return line.lstrip().startswith("#")


def _relative_path(path: Path) -> str:
    """返回相对于 BACKEND_DIR 的路径字符串（使用 /）。"""
    try:
        return str(path.relative_to(BACKEND_DIR)).replace("\\", "/")
    except ValueError:
        return str(path)


def _is_allowed(rel_path: str) -> bool:
    """检查路径是否在白名单中。"""
    for allowed in ALLOWED_PATHS:
        if rel_path == allowed or rel_path.startswith(allowed + "/"):
            return True
    return False


def _is_legacy(rel_path: str) -> str | None:
    """检查路径是否在遗留白名单中，返回说明或 None。"""
    for legacy_path, reason in LEGACY_WHITELIST.items():
        if rel_path == legacy_path or rel_path.startswith(legacy_path):
            return reason
    return None


def _is_excluded(rel_path: str) -> bool:
    """检查路径是否在排除目录中。"""
    for excluded in EXCLUDED_DIRS:
        if rel_path.startswith(excluded + "/") or rel_path == excluded:
            return True
    return False


def _has_violation(line: str) -> bool:
    """检查单行是否包含违规模式。"""
    for pattern in PRECISE_PATTERNS:
        if pattern.search(line):
            return True
    return False


def scan_file(filepath: Path) -> list[tuple[int, str]]:
    """扫描单个文件，返回违规行列表 [(行号, 行内容)]。"""
    violations: list[tuple[int, str]] = []
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            for lineno, line in enumerate(f, start=1):
                # 跳过注释行
                if _is_comment_line(line):
                    continue
                if _has_violation(line):
                    violations.append((lineno, line.rstrip()))
    except OSError:
        pass
    return violations


def main() -> int:
    """主入口。"""
    print("=" * 60)
    print("ACNR STANDARD_WP_CODE_RE 单一定义守卫 (R12.3)")
    print("grep-ban: 阻断新增 [A-I]\\d / [A-S]\\d 副本")
    print("=" * 60)

    if not BACKEND_DIR.exists():
        print(f"❌ 后端目录不存在: {BACKEND_DIR}")
        return 1

    new_violations: list[tuple[str, int, str]] = []  # (rel_path, lineno, line)
    legacy_hits: list[tuple[str, str]] = []  # (rel_path, reason)

    # 扫描所有 Python 文件
    py_files = sorted(BACKEND_DIR.rglob("*.py"))
    scanned = 0

    for filepath in py_files:
        rel_path = _relative_path(filepath)

        # 跳过排除目录
        if _is_excluded(rel_path):
            continue

        # 跳过白名单路径
        if _is_allowed(rel_path):
            continue

        # 检查是否为遗留白名单
        legacy_reason = _is_legacy(rel_path)

        scanned += 1
        violations = scan_file(filepath)

        if violations:
            if legacy_reason:
                legacy_hits.append((rel_path, legacy_reason))
            else:
                for lineno, line in violations:
                    new_violations.append((rel_path, lineno, line))

    # 同时扫描非 ACNR 的 JSON 文件（排除 grammar_v1.json 本身）
    for filepath in sorted(BACKEND_DIR.rglob("*.json")):
        rel_path = _relative_path(filepath)
        if _is_excluded(rel_path):
            continue
        if _is_allowed(rel_path):
            continue
        legacy_reason = _is_legacy(rel_path)
        violations = scan_file(filepath)
        if violations:
            if legacy_reason:
                legacy_hits.append((rel_path, legacy_reason))
            else:
                for lineno, line in violations:
                    new_violations.append((rel_path, lineno, line))

    print(f"\n   扫描 Python 文件数: {scanned}")
    print(f"   权威定义位置: backend/data/acnr/grammar_v1.json")

    # 报告遗留白名单命中
    if legacy_hits:
        print(f"\n⚠️  遗留白名单命中 ({len(legacy_hits)} 处，需在 M1 迁移):")
        for rel_path, reason in legacy_hits:
            print(f"   ⚠️  {rel_path} — {reason}")

    # 报告新增违规
    if new_violations:
        print(f"\n❌ 检测到新增副本 ({len(new_violations)} 处违规):")
        print("   以下文件包含 [A-I]\\d 或 [A-S]\\d 模式副本，")
        print("   应改为从 grammar_v1.json 导入 STANDARD_WP_CODE_RE。\n")
        for rel_path, lineno, line in new_violations:
            print(f"   {rel_path}:{lineno}")
            print(f"     {line}")
            print()
        print("=" * 60)
        print(f"❌ 校验失败：{len(new_violations)} 处新增副本")
        print("   修复方法：从 backend/data/acnr/grammar_v1.json 导入 STANDARD_WP_CODE_RE")
        return 1

    # 全部通过
    print("\n" + "=" * 60)
    print("✅ 校验通过：无新增 [A-I]\\d / [A-S]\\d 副本")
    return 0


if __name__ == "__main__":
    sys.exit(main())
