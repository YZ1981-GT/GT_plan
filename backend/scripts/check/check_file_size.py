"""文件行数卡点（pre-commit hook）。

migration-runner-resilience / 全局改进 #5 落地。

策略：
- 默认上限：backend Python ≤800 行，前端 .vue/.ts ≤1500 行
- whitelist：现有大文件列入 `backend/scripts/file_size_whitelist.txt`，
  每次模块打磨完成后从 whitelist 移除该文件（强制 ≤800/1500）
- 新加文件强制不超限（不在 whitelist 即检查）
- whitelist 中文件**仍然**检查"是否变得更大"：若行数 > whitelist 记录值 +5%，仍报错
  （防止"打磨倒退"）

退出码：
- 0 = 通过
- 1 = 有文件超限
- 2 = whitelist 文件膨胀 >5%

用法：
    python backend/scripts/check_file_size.py [files...]

未传 files 则扫描 backend/app + audit-platform/frontend/src
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WHITELIST_FILE = Path(__file__).parent / "file_size_whitelist.txt"

# 默认上限（按文件类型）
LIMITS = {
    ".py": 800,
    ".vue": 1500,
    ".ts": 1500,
    ".tsx": 1500,
}

EXCLUDE_PARTS = {".git", ".venv", "__pycache__", "node_modules", "dist", "build",
                 ".pytest_cache", ".hypothesis", "_archive", "auto-imports.d.ts",
                 "components.d.ts", "alembic"}


def load_whitelist() -> dict[str, int]:
    """读 whitelist：`path  baseline_lines`（空格分隔，# 注释）。"""
    if not WHITELIST_FILE.exists():
        return {}
    result: dict[str, int] = {}
    for line in WHITELIST_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            result[parts[0]] = int(parts[1])
        except ValueError:
            continue
    return result


def count_lines(p: Path) -> int:
    try:
        return sum(1 for _ in p.read_text(encoding="utf-8").splitlines())
    except Exception:
        return 0


def check_file(rel_path: str, abs_path: Path, whitelist: dict[str, int]) -> tuple[int, str]:
    """检查单文件。返回 (exit_code, message)。"""
    suffix = abs_path.suffix
    limit = LIMITS.get(suffix)
    if limit is None:
        return 0, ""
    lines = count_lines(abs_path)

    if rel_path in whitelist:
        baseline = whitelist[rel_path]
        # 允许 ±5% 浮动避免抖动
        threshold = int(baseline * 1.05)
        if lines > threshold:
            return 2, (
                f"❌ [膨胀] {rel_path}: {lines} 行 > whitelist 基线 {baseline} +5% "
                f"({threshold})；打磨应让文件变小不变大"
            )
        return 0, ""

    if lines > limit:
        return 1, (
            f"❌ [超限] {rel_path}: {lines} 行 > 上限 {limit}；"
            f"请拆分或加入 whitelist（仅历史大文件许可）"
        )
    return 0, ""


def scan_default() -> list[Path]:
    """默认扫描全仓代码文件。"""
    targets: list[Path] = []
    for d in ("backend/app", "audit-platform/frontend/src"):
        root = ROOT / d
        if not root.exists():
            continue
        for f in root.rglob("*"):
            if not f.is_file() or f.suffix not in LIMITS:
                continue
            if any(p in f.parts for p in EXCLUDE_PARTS):
                continue
            targets.append(f)
    return targets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="文件行数卡点")
    parser.add_argument("files", nargs="*", help="检查文件路径（pre-commit 传入）")
    parser.add_argument("--print-current-violations", action="store_true",
                        help="输出当前所有超限文件，用于生成 whitelist 基线")
    args = parser.parse_args(argv)

    whitelist = load_whitelist()

    if args.print_current_violations:
        # 用于初始化 whitelist：列出所有超限文件 + 当前行数
        for f in scan_default():
            rel = str(f.relative_to(ROOT)).replace("\\", "/")
            limit = LIMITS.get(f.suffix, 99999)
            lines = count_lines(f)
            if lines > limit:
                print(f"{rel} {lines}")
        return 0

    if args.files:
        files = [ROOT / Path(f) for f in args.files]
    else:
        files = scan_default()

    exit_code = 0
    messages: list[str] = []
    for f in files:
        if not f.exists() or not f.is_file():
            continue
        rel = str(f.resolve().relative_to(ROOT)).replace("\\", "/") if f.is_absolute() \
              else str(f).replace("\\", "/")
        if any(p in Path(rel).parts for p in EXCLUDE_PARTS):
            continue
        if Path(rel).suffix not in LIMITS:
            continue
        code, msg = check_file(rel, f if f.is_absolute() else (ROOT / rel), whitelist)
        if msg:
            messages.append(msg)
        if code > exit_code:
            exit_code = code

    if messages:
        print("\n".join(messages), file=sys.stderr)
        print("", file=sys.stderr)
        print(f"共 {len(messages)} 个文件超限/膨胀。", file=sys.stderr)
        print(f"whitelist 路径: {WHITELIST_FILE.relative_to(ROOT)}", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
