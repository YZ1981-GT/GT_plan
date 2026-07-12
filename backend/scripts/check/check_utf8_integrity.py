#!/usr/bin/env python
"""check_utf8_integrity.py — UTF-8 / U+FFFD 完整性守卫

背景（platform-global-hardening Req 3.1 / 3.7）：
  平台反复踩坑「用 PowerShell `Set-Content` / `-replace` 操作 Vue 文件 → 中文被写成
  U+FFFD 替换字符（replacement char, 字节序列 `\\xef\\xbf\\xbd`）→ 编译报错 / 乱码」。
  该类破坏能穿过 vue-tsc / get_diagnostics / vitest（它们对损坏的 SFC 结构宽松放过），
  唯有字节级统计 `raw.count(b'\\xef\\xbf\\xbd')` 才能客观检出。本守卫把这条铁律
  升级为 author-time / pre-commit / CI 的硬门禁。

判定（客观、零误报）：
  对每个目标文本文件，`raw = path.read_bytes(); count = raw.count(b'\\xef\\xbf\\xbd')`；
  `count > 0` → 违规。对 `.vue` 文件命中时，报告额外标注「疑似 shell 文本替换破坏」，
  提示禁用 PowerShell `Set-Content` / `-replace`。

用法：
  python backend/scripts/check/check_utf8_integrity.py                 # 报告模式（退出码 0）
  python backend/scripts/check/check_utf8_integrity.py --check         # 同上，显式报告模式
  python backend/scripts/check/check_utf8_integrity.py --strict        # 严格模式（有违规退出码 1）
  python backend/scripts/check/check_utf8_integrity.py a.vue b.ts ...  # 只扫给定路径（pre-commit diff 模式）

设计为零依赖（仅标准库），可在 CI 与 pre-commit（git diff 文件列表）直接运行。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# ─── 常量 ────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[3]

# U+FFFD REPLACEMENT CHARACTER 的 UTF-8 字节序列
FFFD = b"\xef\xbf\xbd"

# 目标文本文件扩展名
TEXT_EXTENSIONS = (".vue", ".ts", ".py", ".md")

# Vue 文件命中时的额外标注（Req 3.7）
VUE_MARKER = "疑似 shell 文本替换破坏（禁用 PowerShell Set-Content/-replace）"

# 默认扫描根（未显式给定路径列表时），相对仓库根
DEFAULT_SCAN_ROOTS = (
    "audit-platform/frontend/src",
    "backend/app",
    "backend/scripts",
)

# 遍历时剪枝的目录名（避免扫 node_modules / .hypothesis 等海量非源码）
PRUNE_DIRS = {
    "node_modules",
    ".git",
    ".hypothesis",
    ".venv",
    "venv",
    "dist",
    "build",
    ".codegraph",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "coverage",
    ".turbo",
    ".cache",
}


# ─── 纯函数核心（供属性测试直接调用，零 IO）────────────────────────────────
def count_replacement_chars(raw: bytes) -> int:
    """统计字节内容中的 U+FFFD 替换字符数量。"""
    return raw.count(FFFD)


def is_violation(raw: bytes) -> bool:
    """当且仅当字节内容含 ≥1 个 U+FFFD 时判定为违规。"""
    return count_replacement_chars(raw) > 0


def format_violation(rel_path: str, count: int) -> str:
    """构造单条违规报告行；`.vue` 文件额外标注疑似 shell 破坏。"""
    line = f"{rel_path}  [U+FFFD × {count}]"
    if rel_path.endswith(".vue"):
        line += f"  {VUE_MARKER}"
    return line


# ─── 文件扫描 ────────────────────────────────────────────────────────────────
def scan_file(path: Path) -> int | None:
    """返回文件中的 U+FFFD 数量；不可读文件 fail-open 返回 None（跳过）。"""
    try:
        raw = path.read_bytes()
    except (OSError,):
        return None
    return count_replacement_chars(raw)


def _iter_default_targets() -> list[Path]:
    """遍历默认扫描根，产出全部目标文本文件（剪枝非源码目录）。"""
    targets: list[Path] = []
    for root_rel in DEFAULT_SCAN_ROOTS:
        root = REPO_ROOT / root_rel
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            # 就地剪枝
            dirnames[:] = [d for d in dirnames if d not in PRUNE_DIRS]
            for fn in filenames:
                if fn.endswith(TEXT_EXTENSIONS):
                    targets.append(Path(dirpath) / fn)
    return sorted(targets)


def _resolve_explicit_targets(paths: list[str]) -> list[Path]:
    """把命令行传入的路径列表解析为目标文件（只保留文本扩展名）。"""
    targets: list[Path] = []
    for p in paths:
        path = Path(p)
        if not path.is_absolute():
            path = (REPO_ROOT / p) if not path.exists() else path
        if path.is_file() and path.name.endswith(TEXT_EXTENSIONS):
            targets.append(path)
    return targets


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="UTF-8 / U+FFFD 完整性守卫")
    parser.add_argument(
        "paths",
        nargs="*",
        help="待检查的文件路径列表（pre-commit diff 模式）；缺省时扫描默认源码根",
    )
    parser.add_argument("--check", action="store_true", help="报告模式（退出码恒 0，默认）")
    parser.add_argument(
        "--strict", action="store_true", help="严格模式：检出 U+FFFD 时退出码 1"
    )
    args = parser.parse_args(argv)

    # Windows 控制台默认 GBK，输出中文会抛 UnicodeEncodeError；强制 utf-8。
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass

    targets = (
        _resolve_explicit_targets(args.paths)
        if args.paths
        else _iter_default_targets()
    )

    total_violations = 0
    skipped = 0
    for path in targets:
        count = scan_file(path)
        if count is None:
            skipped += 1
            print(f"::warning::无法读取，跳过 {_rel(path)}")
            continue
        if count > 0:
            total_violations += 1
            print(format_violation(_rel(path), count))

    if total_violations:
        print(
            f"\n检测到 U+FFFD 替换字符：{total_violations} 个文件受影响。\n"
            "根因：多为 PowerShell Set-Content/-replace 破坏 UTF-8 中文编码。\n"
            "修复：用 git checkout 恢复受损文件，改用结构化编辑工具（禁止 PowerShell 文本替换）。"
        )
        if args.strict:
            return 1
        print("（报告模式：未阻断。CI 强制期后 --strict 将 fail）")
        return 0

    print(f"✅ UTF-8 完整性检查通过：{len(targets)} 个文件无 U+FFFD（跳过 {skipped} 个不可读）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
