# -*- coding: utf-8 -*-
"""Task 28 辐射面：按**真实 import/引用**反查受本次改动影响的测试文件。
spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 2 Task 28

用法（仓库根目录）::

    py -3 backend/scripts/diagnose/radiation_task28_sync_router.py
    py -3 backend/scripts/diagnose/radiation_task28_sync_router.py --pytest-args

═══ 为什么不能跑全量 ═══

`backend/tests` 下有 1500+ 测试文件，前台跑数分钟无输出会被当成卡死。判据是
**引用关系**：扫每个测试文件的 `ImportFrom` 模块名与源码里对本次改动符号的引用，
命中即纳入辐射面。

═══ 为什么用 AST 而不是裸词 ═══

裸词会把「注释里提到 `wp_sync_router`」的文件也拉进来（本 spec 的 evidence README 与
若干守卫的 docstring 里都逐字写着这些模块名）。AST 只认真实 import 与真实符号引用。

判据同时输出**为什么**命中（哪一条 import / 哪个符号），便于人工复核辐射面不是猜的。
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TESTS = REPO / "backend" / "tests"

#: 本次改动的生产模块（相对 `backend/`，POSIX 分隔符）。
CHANGED_MODULES: tuple[str, ...] = (
    "app.routers.wp_sync_router",
    "app.routers.wp_onlyoffice_router",
    "app.router_registry.workpaper",
    "app.services.workpaper_sync",
    "app.services.workpaper_sync.endpoint_guard",
    "app.services.workpaper_sync.endpoint_payloads",
    "app.services.workpaper_sync.materialize_coordinator",
    "app.services.workpaper_sync.merge",
)

#: 本次改动/新增的符号（被引用即算辐射）。
CHANGED_SYMBOLS: tuple[str, ...] = (
    "wp_sync_router",
    "SyncEndpointGuard",
    "GuardedScope",
    "build_sync_services",
    "build_materialize_coordinator",
    "RETIRED_DEFERRALS",
    "post_sheet_onlyoffice_callback",
    "USER_SYNC_PREFIX",
)


def _imports_of(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                out.add(alias.name)
    return out


def _names_of(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                out.add(alias.asname or alias.name)
    return out


def scan() -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for path in sorted(TESTS.rglob("test_*.py")):
        try:
            # `utf-8-sig` 剥 BOM：仓库里有带 BOM 的测试文件
            # （`test_router_registry_split.py`），`ast.parse` 对 U+FEFF 直接
            # `invalid non-printable character` ⇒ 会被误判成「坏文件」而混进辐射面。
            tree = ast.parse(path.read_text(encoding="utf-8-sig", errors="replace"))
        except SyntaxError:  # pragma: no cover - 坏文件如实报告，不静默跳过
            hits[path.relative_to(REPO).as_posix()] = ["<SyntaxError>"]
            continue
        imports = _imports_of(tree)
        names = _names_of(tree)
        why: list[str] = []
        for module in CHANGED_MODULES:
            if any(imp == module or imp.startswith(module + ".") for imp in imports):
                why.append(f"import:{module}")
        for symbol in CHANGED_SYMBOLS:
            if symbol in names:
                why.append(f"symbol:{symbol}")
        if why:
            hits[path.relative_to(REPO).as_posix()] = sorted(set(why))
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Task 28 辐射面反查")
    parser.add_argument(
        "--pytest-args", action="store_true", help="只输出可直接喂给 pytest 的路径列表"
    )
    parser.add_argument("--json", metavar="PATH", help="把结果落盘为 JSON")
    args = parser.parse_args(argv)

    hits = scan()
    if args.pytest_args:
        print(" ".join(sorted(hits)))
        return 0
    print(f"辐射面：{len(hits)} 个测试文件（全量 "
          f"{len(list(TESTS.rglob('test_*.py')))} 个）\n")
    for path, why in sorted(hits.items()):
        print(f"  {path}")
        print(f"      {', '.join(why)}")
    if args.json:
        Path(args.json).write_text(
            json.dumps({"files": hits}, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n已写入 {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
