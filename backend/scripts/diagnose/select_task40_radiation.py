# -*- coding: utf-8 -*-
"""Task 40 辐射面选取：按 **AST 级 import / 符号引用 / 生成物文件名** 推导受影响测试文件。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 3 Task 40

═══ 为什么不用词面搜索 ═══

`backend/tests` 下约 2285 个测试文件，整跑会被当成卡死。本 spec 已实测过词面搜索的后果：
一次产生 67 个假阳性、把 14 个无关失败拖进判定。因此只认三类结构化证据：

1. **import 图** —— 测试文件是否 import 了本任务新建/改动的模块；
2. **符号引用** —— 是否以 `Name` / `Attribute` / `ImportFrom` 形式引用本任务新增的符号；
3. **生成物文件名** —— 是否以 **`ast.Constant` 字符串**引用了本任务重生成的数据文件。

第 3 类是 Task 39 的选取器没有的：本任务改的不只是 Python 模块，还重生成了
`workpaper_writer_inventory.json` 与 `workpaper_resolver_migration_matrix.json`。
消费它们的守卫（Task 12 的 `test_matrix_is_fresh`、Task 30 的 closure gate、Wave 0 的
writer 清册特征测试）在 import 图与符号图上**都看不见**这次改动 —— 它们只是读一个
JSON 路径。漏掉这一类，收口就会得出「辐射面全绿」而 CI 在干净 checkout 下打红。

只看 `ast.Constant` 而不是整文件 grep：登记表的 `why` 文案、注释、docstring 里也写着
这些文件名（本任务的守卫 docstring 就提到了 inventory），词面匹配会把它们全算进来。

═══ 本任务的改动面 ═══

* **新建** `pilot_simple_checklist.py`（本轮：`_template_index_wp_codes()` 改为取
  `wp_template_finder.INDEX_FILE`，不再自己拼 `wp_templates` 路径 ⇒ 它从 writer/resolver
  清册里整行消失）
* **重生成** `workpaper_writer_inventory.json` / `workpaper_resolver_migration_matrix.json`
* **只加不动** `adapters/registry.py`（`DELIVERED_PER_ENTRY_CONTRACTS` 追加一条）、
  `routers/wp_sync_router.py`（两个接线点）
* **新增磁盘契约** `backend/data/workpaper_sync_contracts/b60.hour_budget.json`
  ⇒ 「契约目录 ↔ 交付登记表双向等值」（Task 13）会变化

用法::

    py -3 backend/scripts/diagnose/select_task40_radiation.py
    py -3 backend/scripts/diagnose/select_task40_radiation.py --print-args
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
TESTS = BACKEND / "tests"

#: 本任务新建 + 只加不动的生产模块。
#:
#: `wp_template_finder` 在列，是因为本轮把模板索引位置的真源收敛到它的 `INDEX_FILE`：
#: 任何「谁在读模板索引」的判据都会因此变化。它本身**只读不改**（文件领地禁止改动）。
CHANGED_MODULES: tuple[str, ...] = (
    "app.services.workpaper_sync.pilot_simple_checklist",
    "app.services.workpaper_sync.adapters.registry",
    "app.routers.wp_sync_router",
    "app.services.wp_template_finder",
)

#: 本任务新增/改动的符号。
CHANGED_SYMBOLS: frozenset[str] = frozenset(
    {
        # pilot_simple_checklist 新建
        "PILOT_ADAPTER_ID",
        "PILOT_CLASS",
        "PILOT_ENTRY_ID",
        "PILOT_WP_CODES",
        "MANAGED_SHEET",
        "MANAGED_FIELD_SPECS",
        "META_FIELD_SPECS",
        "TEMPLATE_SHA256",
        "TEMPLATE_RELATIVE_PATH",
        "AUTHORITY_MODEL",
        "FORMULA_MASK",
        "FOOTER_MARKER",
        "PilotDefinitions",
        "PilotSelectionError",
        # 🔴 Task 75 删掉了 `UPSTREAM_DEBT_PUBLISHED_IDENTITY_OBSERVER`（欠账已结清）。
        #    这份集合是按 **AST Name 引用**取交集来选辐射面的，已删符号永不可能命中 ⇒
        #    留着就是死成员（选择器会声称一个不存在的符号「变了」）。它在本任务里的替身
        #    是下面的 `resolve_published_frozen_definitions`（真被改动的那个符号）。
        "assert_contract_file_matches_source",
        "assert_manifest_capability_enabled",
        "assert_pilot_entry_selectable",
        "attach_pilot_adapters",
        "authoritative_template_path",
        "authority_model_payload",
        "build_contract_payload",
        "build_pilot_matcher",
        "build_pilot_registration",
        "instrumentation_definition_payload",
        "instrumentation_spec",
        "load_pilot_contract",
        "publish_pilot_definitions",
        "read_authoritative_template",
        "register_pilot_adapter",
        "resolve_published_frozen_definitions",
        "template_definition_payload",
        # registry.py 只加不动（交付登记表追加一条）
        "DELIVERED_PER_ENTRY_CONTRACTS",
        # 模板索引真源收敛
        "INDEX_FILE",
    }
)

#: 本任务重生成 / 新增的数据文件（按**文件名**匹配 `ast.Constant` 字符串）。
CHANGED_DATA_FILES: frozenset[str] = frozenset(
    {
        "workpaper_writer_inventory.json",
        "workpaper_resolver_migration_matrix.json",
        "workpaper_writer_domain_overlay.json",
        "b60.hour_budget.json",
        "workpaper_sync_contracts",
        "generate_workpaper_writer_inventory.py",
        "generate_workpaper_resolver_migration_matrix.py",
        "check_workpaper_writer_revision_gate.py",
    }
)

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


def _string_constants(tree: ast.AST) -> set[str]:
    """只取真正的字符串**字面量**（docstring 除外由调用方判重，注释天然不在 AST）。"""
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


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
    # 生成物：文件名可能作为整串出现（"…/workpaper_writer_inventory.json"）或单段出现
    consts = _string_constants(tree)
    data_hits = {
        name
        for name in CHANGED_DATA_FILES
        if name in consts or any(name in value for value in consts if len(value) < 200)
    }
    if data_hits:
        reasons.append("data:" + ",".join(sorted(data_hits)[:3]))
    return (bool(reasons), reasons)


def _test_module_edges() -> dict[str, set[str]]:
    """测试模块 → 它 import 的其它测试模块（fixture 复用链）。"""
    edges: dict[str, set[str]] = {}
    for path in sorted(TESTS.rglob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        edges[path.stem] = {
            name.split(".")[0]
            for name in _module_names(tree)
            if name.startswith(TEST_MODULE_PREFIX)
        }
    return edges


def main() -> int:
    parser = argparse.ArgumentParser(description="Task 40 辐射面选取")
    parser.add_argument("--print-args", action="store_true", help="只输出 pytest 参数")
    args = parser.parse_args()

    direct: dict[Path, list[str]] = {}
    for path in sorted(TESTS.rglob("test_*.py")):
        touched, reasons = _touches(path)
        if touched:
            direct[path] = reasons

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
        print(f"{rel}  <- {', '.join(direct[REPO / rel])}")
    print(f"\n辐射面：{len(rels)} 个测试文件（AST 级 import/符号引用/生成物文件名 + 测试模块 import 闭包）")
    print(f"分母参考：backend/tests 下共 {len(list(TESTS.rglob('test_*.py')))} 个测试文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
