"""CI size guard — 行数上限卡点。

Feature: platform-global-hardening

对拆分后的关键文件设置行数上限，防止拆分成果退化回膨胀。
同时对 workpaper/ .vue 和 backend/app/ .py 设置 2000 行软上限。

用法:
    python backend/scripts/check/check_file_size_guard.py          # REPORT 模式（默认）
    python backend/scripts/check/check_file_size_guard.py --check  # 同 REPORT 模式
    python backend/scripts/check/check_file_size_guard.py --strict # 超限退出码 1

退出码:
    0 = 全部通过（或 REPORT 模式下有违规但不阻断）
    1 = --strict 模式下有文件超限
"""

from __future__ import annotations

import sys
import argparse
from pathlib import Path

# Windows GBK 防崩
sys.stdout.reconfigure(encoding="utf-8")

# ──────────────────────────────────────────────────────────────────────
# 仓库根目录定位
# ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[3]

# ──────────────────────────────────────────────────────────────────────
# 1. 精确文件行数上限（拆分后 orchestrator / facade）
# ──────────────────────────────────────────────────────────────────────
EXACT_FILE_LIMITS: dict[str, int] = {
    # 前端：拆分后的 orchestrator 上限
    "audit-platform/frontend/src/views/LedgerPenetration.vue": 1000,
    "audit-platform/frontend/src/views/TrialBalance.vue": 1000,
    # 后端：拆分后的 facade __init__.py 上限
    "backend/app/routers/wp_render_strategies/_d1_import_export/__init__.py": 100,
    "backend/app/services/event_handlers/__init__.py": 100,
    "backend/app/services/consistency_gate/__init__.py": 100,
}

# ──────────────────────────────────────────────────────────────────────
# 2. 泛类 soft limit（2000 行）
# ──────────────────────────────────────────────────────────────────────
GENERIC_SOFT_LIMIT = 2000

# 排除目录
EXCLUDE_PARTS = frozenset({
    ".git", "node_modules", "__pycache__", "dist", "build",
    ".venv", ".pytest_cache", ".hypothesis", "_archive",
})


def count_lines(path: Path) -> int | None:
    """计算文件行数。不可读文件返回 None（fail-open）。"""
    try:
        return sum(1 for _ in path.read_text(encoding="utf-8").splitlines())
    except (OSError, UnicodeDecodeError):
        return None


def is_excluded(rel_path: str) -> bool:
    """检查路径是否含排除目录。"""
    parts = Path(rel_path).parts
    return any(p in EXCLUDE_PARTS for p in parts)


def check_exact_files() -> list[tuple[str, int, int]]:
    """检查精确文件上限。返回 [(rel_path, lines, max_lines), ...]"""
    violations: list[tuple[str, int, int]] = []
    for rel_path, max_lines in EXACT_FILE_LIMITS.items():
        abs_path = ROOT / rel_path
        if not abs_path.exists():
            # 文件不存在（可能尚未创建或已删除）→ fail-open 跳过
            continue
        lines = count_lines(abs_path)
        if lines is None:
            # 不可读 → fail-open，打印 warning 跳过
            print(f"  [WARN] 无法读取 {rel_path}，跳过")
            continue
        if lines > max_lines:
            violations.append((rel_path, lines, max_lines))
    return violations


def check_generic_soft_limit() -> list[tuple[str, int, int]]:
    """检查泛类 2000 行 soft limit。返回 [(rel_path, lines, 2000), ...]"""
    violations: list[tuple[str, int, int]] = []

    # workpaper/ .vue 文件
    wp_dir = ROOT / "audit-platform" / "frontend" / "src" / "components" / "workpaper"
    if wp_dir.exists():
        for f in wp_dir.rglob("*.vue"):
            if not f.is_file():
                continue
            rel = str(f.relative_to(ROOT)).replace("\\", "/")
            if is_excluded(rel):
                continue
            lines = count_lines(f)
            if lines is None:
                continue
            if lines > GENERIC_SOFT_LIMIT:
                violations.append((rel, lines, GENERIC_SOFT_LIMIT))

    # backend/app/ .py 文件
    app_dir = ROOT / "backend" / "app"
    if app_dir.exists():
        for f in app_dir.rglob("*.py"):
            if not f.is_file():
                continue
            rel = str(f.relative_to(ROOT)).replace("\\", "/")
            if is_excluded(rel):
                continue
            lines = count_lines(f)
            if lines is None:
                continue
            if lines > GENERIC_SOFT_LIMIT:
                violations.append((rel, lines, GENERIC_SOFT_LIMIT))

    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CI size guard — 行数上限卡点")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--strict", action="store_true",
        help="严格模式：超限退出码 1（用于 CI 阻断）"
    )
    group.add_argument(
        "--check", action="store_true",
        help="报告模式（默认）：列出超限文件但退出码恒 0"
    )
    args = parser.parse_args(argv)

    strict = args.strict

    print("=" * 60)
    print("CI Size Guard — 行数上限检查")
    print("=" * 60)
    print()

    # 1. 精确文件检查
    exact_violations = check_exact_files()
    if exact_violations:
        print("[精确文件上限] 以下文件超限：")
        for rel, lines, max_lines in exact_violations:
            print(f"  ❌ {rel}: {lines} 行 > 上限 {max_lines}")
        print()
    else:
        print("[精确文件上限] 全部通过 ✓")
        print()

    # 2. 泛类 soft limit 检查
    generic_violations = check_generic_soft_limit()
    if generic_violations:
        print(f"[泛类 soft limit ({GENERIC_SOFT_LIMIT} 行)] 以下文件超限：")
        for rel, lines, max_lines in generic_violations:
            print(f"  ⚠️  {rel}: {lines} 行 > soft limit {max_lines}")
        print()
    else:
        print(f"[泛类 soft limit ({GENERIC_SOFT_LIMIT} 行)] 全部通过 ✓")
        print()

    # 汇总
    total = len(exact_violations) + len(generic_violations)
    if total == 0:
        print("✅ 所有文件行数在限额内。")
        return 0

    print(f"共 {total} 个文件超限（精确 {len(exact_violations)} / 泛类 {len(generic_violations)}）。")

    if strict:
        print("\n❌ --strict 模式：构建失败。")
        return 1
    else:
        print("\n⚠️  报告模式：仅报告，不阻断。")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
