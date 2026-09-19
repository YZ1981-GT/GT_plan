# -*- coding: utf-8 -*-
"""Task 38 辐射面选取：按 **AST 级 import / 符号引用** 推导受影响测试文件。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 3 Task 38

═══ 为什么不用词面搜索 ═══

`backend/tests` 根目录下有约 2285 个测试文件，整跑会被当成卡死。本 spec 已实测过词面搜索的
后果：一次产生 67 个假阳性、把 14 个无关失败拖进判定。因此这里只认两类结构化证据：

1. **import 图** —— 测试文件（含它 import 的其它测试模块）是否 import 了本任务改动的模块；
2. **符号引用** —— 是否在 AST 里以 `Name` / `Attribute` 形式引用了本任务新增/改动的符号。

两者都从 `ast` 取，不看注释、不看字符串（登记表的 `reason` 文案里就写着这些名字）。

用法::

    py -3 backend/scripts/diagnose/select_task38_radiation.py
    py -3 backend/scripts/diagnose/select_task38_radiation.py --print-args
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
TESTS = BACKEND / "tests"

#: 本任务改动的生产模块（新建 + 只加不动）。
CHANGED_MODULES: tuple[str, ...] = (
    "app.services.workpaper_sync.excel_materialize",
    "app.services.workpaper_sync.excel_rematerialize",
    "app.services.workpaper_sync.adapters.excel",
    "app.services.workpaper_sync.excel_extract",
    "app.services.workpaper_sync.adapters.registry",
    "app.services.workpaper_sync.merge",
)

#: 本任务新增/改动的符号（含只加不动的那三处登记表与新读侧入口）。
CHANGED_SYMBOLS: frozenset[str] = frozenset(
    {
        # excel_extract 只加不动
        "read_runtime_binding_pairs",
        # registry 只加不动
        "DELIVERED_ENGINE_ADAPTERS",
        "PENDING_ENGINE_ADAPTERS",
        "TASK13_ADAPTER_MODULES",
        # merge 只加不动
        "RETIRED_DEFERRALS",
        # materialize / rematerialize / adapter 新建
        "materialize_projection",
        "plan_managed_writes",
        "select_write_strategy",
        "apply_plan_zip",
        "apply_plan_openpyxl",
        "assert_dynamic_column_binding_usable",
        "assert_footer_anchor_stable",
        "assert_footer_formula_covers_managed_rows",
        "assert_output_outside_template_library",
        "FAILURE_KINDS",
        "materialize_for_editing",
        "rematerialize_merged_projection",
        "plan_representation_upgrade",
        "derive_baseline_from_representation",
        "protected_conflicts_from_incoming",
        "ExcelSyncAdapter",
        "build_excel_adapter",
    }
)

#: 测试模块之间的 import（本任务的两个测试文件 import 了 Task 37 / Task 15 的 fixture）。
TEST_MODULE_PREFIX = "test_"


def _module_names(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out.update(f"{node.module}.{alias.name}" for alias in node.names)
    return out


def _referenced_symbols(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, ast.ImportFrom):
            out.update(alias.name for alias in node.names)
    return out


def _touches(path: Path) -> tuple[bool, list[str]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return (False, [])
    modules = _module_names(tree)
    reasons: list[str] = []
    for module in CHANGED_MODULES:
        if any(name == module or name.startswith(module + ".") for name in modules):
            reasons.append(f"import:{module.rsplit('.', 1)[-1]}")
    hits = CHANGED_SYMBOLS & _referenced_symbols(tree)
    if hits:
        reasons.append("symbols:" + ",".join(sorted(hits)[:4]))
    return (bool(reasons), reasons)


def _test_module_edges() -> dict[str, set[str]]:
    """测试模块 → 它 import 的其它测试模块（本任务的 fixture 复用链）。"""
    edges: dict[str, set[str]] = {}
    for path in sorted(TESTS.rglob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        names = {
            name.split(".")[0]
            for name in _module_names(tree)
            if name.startswith(TEST_MODULE_PREFIX)
        }
        edges[path.stem] = names
    return edges


def main() -> int:
    parser = argparse.ArgumentParser(description="Task 38 辐射面选取")
    parser.add_argument("--print-args", action="store_true", help="只输出 pytest 参数")
    args = parser.parse_args()

    direct: dict[Path, list[str]] = {}
    for path in sorted(TESTS.rglob("test_*.py")):
        touched, reasons = _touches(path)
        if touched:
            direct[path] = reasons

    # 反向闭包：import 了「直接命中的测试模块」的测试也进辐射面（fixture 复用链）。
    edges = _test_module_edges()
    hit_stems = {p.stem for p in direct}
    grown = True
    while grown:
        grown = False
        for path in sorted(TESTS.rglob("test_*.py")):
            if path in direct:
                continue
            if edges.get(path.stem, set()) & hit_stems:
                direct[path] = ["test-import-closure"]
                hit_stems.add(path.stem)
                grown = True

    rels = sorted(p.relative_to(REPO).as_posix() for p in direct)
    if args.print_args:
        print(" ".join(rels))
        return 0
    for rel in rels:
        path = REPO / rel
        print(f"{rel}  <- {', '.join(direct[path])}")
    print(f"\n辐射面：{len(rels)} 个测试文件（AST 级 import/符号引用 + 测试模块 import 闭包）")
    print(f"分母参考：backend/tests 下共 {len(list(TESTS.rglob('test_*.py')))} 个测试文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
