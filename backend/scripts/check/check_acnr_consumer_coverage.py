#!/usr/bin/env python3
"""
check_acnr_consumer_coverage.py — ACNR Consumer Coverage 真实扫描器

扫描 backend/app/ 下 `address_registry.` 直接调用/import，阻断未经 ACNR 的
新增 legacy 消费者。

区分：
- 直接消费：import address_registry 并调用其方法（违规，除非 allowlist 登记）
- 间接经 ACNR facade：import from app.services.acnr.*（合规，不计入违规）

零依赖（仅 stdlib）。显式 UTF-8 读写。

Usage:
    python check_acnr_consumer_coverage.py             # 报告模式（退出码恒 0）
    python check_acnr_consumer_coverage.py --strict    # 严格模式（CI 用，有违规退出码 1）

Feature: acnr-runtime-convergence, Task 13
Requirements: Req-11
Property: P12
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ─── UTF-8 输出 ───────────────────────────────────────────────────────────────
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

# ─── 路径 ─────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent  # GT_plan/
SCAN_ROOT = PROJECT_ROOT / "backend" / "app"
LEDGER_PATH = PROJECT_ROOT / "backend" / "data" / "acnr" / "coverage_ledger.json"

# ─── 正则模式 ─────────────────────────────────────────────────────────────────
# 直接消费模式：import address_registry 模块并调用
RE_IMPORT_ADDRESS_REGISTRY = re.compile(
    r"from\s+app\.services\.address_registry\s+import"
)
RE_IMPORT_ROUTER_ADDRESS_REGISTRY = re.compile(
    r"from\s+app\.routers\.address_registry\s+import"
)
RE_ADDRESS_REGISTRY_DOT_CALL = re.compile(
    r"address_registry\.(?!py\b)\w+"
)

# ACNR facade 模式（不计入违规）
RE_ACNR_FACADE_IMPORT = re.compile(
    r"from\s+app\.services\.acnr"
)

# address_registry 模块自身（排除扫描）
SELF_MODULES = {
    "app/services/address_registry.py",
    "app/routers/address_registry.py",
}

# ACNR 核心模块（允许直调 address_registry 作为 delegation）
ACNR_CORE_PATHS = {
    "app/services/acnr/",
}


def load_ledger(path: Path) -> dict:
    """加载 coverage_ledger.json allowlist。"""
    if not path.exists():
        print(f"[WARN] coverage_ledger.json not found: {path}", file=sys.stderr)
        return {"allowlist": [], "metadata": {}}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_allowlist_set(ledger: dict) -> set[str]:
    """从 ledger 提取 allowlist 文件路径集合（相对于 backend/app/）。"""
    entries = ledger.get("allowlist", [])
    return {entry["file"] for entry in entries if "file" in entry}


def is_self_module(rel_path: str) -> bool:
    """判断是否为 address_registry 模块自身。"""
    normalized = rel_path.replace("\\", "/")
    return any(normalized.endswith(m.replace("app/", "")) for m in SELF_MODULES)


def is_acnr_core(rel_path: str) -> bool:
    """判断是否为 ACNR 核心模块（允许 delegation）。"""
    normalized = rel_path.replace("\\", "/")
    for prefix in ACNR_CORE_PATHS:
        # 从 app/ 开始匹配
        if ("app/" + normalized).startswith(prefix) or normalized.startswith(
            prefix.replace("app/", "")
        ):
            return True
    # 检查路径中是否包含 services/acnr/
    return "services/acnr/" in normalized


def scan_file(filepath: Path, scan_root: Path) -> list[dict]:
    """扫描单个文件，返回直接消费命中列表。

    每项：{line: int, content: str, type: "import"|"call"}
    """
    hits: list[dict] = []
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except (OSError, UnicodeDecodeError):
        return hits

    in_docstring = False
    for i, line in enumerate(content.splitlines(), start=1):
        stripped = line.lstrip()

        # 简易 docstring 跟踪（三引号开合）
        triple_count = stripped.count('"""') + stripped.count("'''")
        if triple_count % 2 == 1:
            in_docstring = not in_docstring
            continue
        if in_docstring:
            continue

        # 跳过注释行
        if stripped.startswith("#"):
            continue

        # 检查 import
        if RE_IMPORT_ADDRESS_REGISTRY.search(line):
            hits.append({"line": i, "content": line.strip(), "type": "import"})
        elif RE_IMPORT_ROUTER_ADDRESS_REGISTRY.search(line):
            hits.append({"line": i, "content": line.strip(), "type": "import"})
        # 检查直接调用（非 import 行）
        elif RE_ADDRESS_REGISTRY_DOT_CALL.search(line):
            hits.append({"line": i, "content": line.strip(), "type": "call"})

    return hits


def scan_directory(scan_root: Path) -> list[dict]:
    """扫描 backend/app/ 下所有 .py 文件。

    返回违规列表（排除 self 模块和 ACNR 核心模块）。
    每项：{file: str, hits: [{line, content, type}]}
    """
    violations: list[dict] = []

    for root_dir, _dirs, files in os.walk(scan_root):
        for fname in files:
            if not fname.endswith(".py"):
                continue

            fpath = Path(root_dir) / fname
            rel_path = str(fpath.relative_to(scan_root)).replace("\\", "/")

            # 排除自身模块
            if is_self_module(rel_path):
                continue

            # 排除 ACNR 核心模块（它们被允许 delegate 调用 address_registry）
            if is_acnr_core(rel_path):
                continue

            hits = scan_file(fpath, scan_root)
            if hits:
                violations.append({"file": rel_path, "hits": hits})

    return violations


def classify_violations(
    violations: list[dict], allowlist: set[str]
) -> tuple[list[dict], list[dict]]:
    """将违规分为已登记（allowlist）和未登记（新增违规）。"""
    registered: list[dict] = []
    unregistered: list[dict] = []

    for v in violations:
        if v["file"] in allowlist:
            registered.append(v)
        else:
            unregistered.append(v)

    return registered, unregistered


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ACNR Consumer Coverage Guard — 扫描 address_registry. 直接消费"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="严格模式（新增未登记消费者退出码 1）",
    )
    parser.add_argument(
        "--scan-root",
        type=Path,
        default=SCAN_ROOT,
        help="扫描根目录（默认 backend/app/）",
    )
    parser.add_argument(
        "--ledger-path",
        type=Path,
        default=LEDGER_PATH,
        help="coverage_ledger.json 路径",
    )
    args = parser.parse_args()

    print("[ACNR Consumer Coverage] Scanning for address_registry. direct usage...")
    print(f"  Scan root: {args.scan_root}")
    print(f"  Ledger: {args.ledger_path}")

    # 加载 allowlist
    ledger = load_ledger(args.ledger_path)
    allowlist = get_allowlist_set(ledger)
    print(f"  Allowlist entries: {len(allowlist)}")

    # 扫描
    all_violations = scan_directory(args.scan_root)

    # 分类
    registered, unregistered = classify_violations(all_violations, allowlist)

    # 输出报告
    print(f"\n  Total direct consumers found: {len(all_violations)}")
    print(f"  Registered in allowlist: {len(registered)}")
    print(f"  Unregistered (new): {len(unregistered)}")

    if registered:
        print("\n  [INFO] Registered consumers (allowlist):")
        for v in registered:
            print(f"    - {v['file']} ({len(v['hits'])} hit(s))")

    if unregistered:
        print("\n  [VIOLATION] Unregistered consumers:")
        for v in unregistered:
            print(f"    - {v['file']}:")
            for h in v["hits"]:
                print(f"        L{h['line']}: {h['content']}")

        if args.strict:
            print(
                f"\n[FAIL] {len(unregistered)} file(s) contain address_registry. "
                f"direct usage without allowlist registration."
            )
            print(
                "  Register them in backend/data/acnr/coverage_ledger.json "
                "or migrate to ACNR facade."
            )
            return 1
    else:
        print("\n[OK] All address_registry consumers are registered or ACNR-facade.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
