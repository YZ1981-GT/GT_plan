# -*- coding: utf-8 -*-
"""Task 41 辐射面选取：按 **AST 级 import / 符号引用 / 生成物文件名** 推导受影响测试文件。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 4 Task 41

═══ 为什么不用词面搜索 ═══

`backend/tests` 下约 2300 个测试文件，整跑会被当成卡死。本 spec 已实测过词面搜索的后果：
一次产生 67 个假阳性、把 14 个无关失败拖进判定。因此只认三类结构化证据：

1. **import 图** —— 测试文件是否 import 了本任务新建/改动的模块；
2. **符号引用** —— 是否以 `Name` / `Attribute` / `ImportFrom` 形式引用本任务新增的符号；
3. **生成物 / 数据文件名** —— 是否以 **`ast.Constant` 字符串**引用了本任务新增或会被本任务
   改变判定的数据文件（新契约 `d2.receivable_detail.json`、契约目录、清册与矩阵）。

第 3 类不可省：消费这些 JSON 的守卫（Task 13 的契约目录边界、Task 12 的 `test_matrix_is_fresh`、
Task 30 的 closure gate、Wave 0 的 writer 清册特征测试）在 import 图与符号图上**都看不见**
本次改动 —— 它们只是读一个路径。漏掉这一类，收口就会得出「辐射面全绿」而 CI 在干净
checkout 下打红。

只看 `ast.Constant` 而不是整文件 grep：登记表的 `why` 文案、注释、docstring 里也写着这些
文件名（本任务的守卫 docstring 就提到了 inventory），词面匹配会把它们全算进来。

═══ 本任务的改动面 ═══

* **新建** `app/services/workpaper_sync/pilot_d2_large_json.py`
* **新建** 磁盘契约 `backend/data/workpaper_sync_contracts/d2.receivable_detail.json`
  ⇒ 「契约目录 ↔ 交付登记表双向等值」（Task 13）判定变化
* **新建** 生成器 `backend/scripts/gen/generate_pilot_d2_large_json_contract.py`
* **只加不动** `adapters/registry.py`（`DELIVERED_PER_ENTRY_CONTRACTS` 追加第二条）、
  `routers/wp_sync_router.py`（两个接线点各加一行 D2 attach）
* **只加不动**（新增可选参数）`pilot_d2_large_json` 依赖的既有模块一个都没改；
  `workpaper_writer_inventory.json` / `workpaper_resolver_migration_matrix.json`
  实测**未过期**（本模块 0 条 writer/resolver 行），但消费它们的守卫仍列进辐射面，
  因为「未过期」这一结论本身要被验证。

用法::

    py -3 backend/scripts/diagnose/select_task41_radiation.py
    py -3 backend/scripts/diagnose/select_task41_radiation.py --print-args
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BACKEND = REPO / "backend"
TESTS = BACKEND / "tests"

#: 本任务新建 + 只加不动的生产模块。
CHANGED_MODULES: tuple[str, ...] = (
    "app.services.workpaper_sync.pilot_d2_large_json",
    "app.services.workpaper_sync.adapters.registry",
    "app.routers.wp_sync_router",
    # 契约目录 / 契约加载的判定随新契约文件变化。
    "app.services.workpaper_sync.contracts",
    # 本 pilot 的 required set 与 pilot 类边界由它们判定。
    "app.services.workpaper_sync.pilot_harness",
    "app.services.workpaper_sync.evidence",
)

#: 本任务新增的符号（含另一个 pilot 的同名符号 —— 两者必须能被区分）。
CHANGED_SYMBOLS: frozenset[str] = frozenset(
    {
        # pilot_d2_large_json 新建
        "PILOT_ADAPTER_ID",
        "PILOT_CLASS",
        "PILOT_ENTRY_ID",
        "PILOT_WP_CODES",
        "MANAGED_SHEET",
        "MANAGED_FIELD_SPECS",
        "SCALAR_FIELD_SPECS",
        "AGING_GROUPS",
        "AGING_SEGMENTS",
        "GROUP_HEADER_CELLS",
        "GROUP_HEADER_LABELS",
        "FORMULA_TEMPLATES",
        "FORMULA_MASK",
        "FOOTER_MARKER",
        "STORE_ITEM_ID",
        "ROW_IDENTITY_STORE_KEY",
        "ROWS_TABLE_KEY",
        "TEMPLATE_SHA256",
        "TEMPLATE_RELATIVE_PATH",
        "RENDER_SCHEMA_RELATIVE_PATH",
        "AUTHORITY_MODEL",
        "PilotDefinitions",
        "PilotSelectionError",
        "StorePayloadError",
        "TemplateResolutionFacts",
        "UPSTREAM_DEBT_BOOLEAN_CELL_ROUNDTRIP",
        "UPSTREAM_DEBT_DYNAMIC_FAMILY_GATED_ON_MOUNT_CARDINALITY",
        # 🔴 Task 75 删掉了 `UPSTREAM_DEBT_PUBLISHED_IDENTITY_OBSERVER`（欠账已结清）。
        #    本集合按 **AST Name 引用**取交集选辐射面，已删符号永不命中 ⇒ 留着是死成员。
        #    它的替身是下面的 `resolve_published_frozen_definitions`。
        "assert_contract_file_matches_source",
        "assert_dynamic_family_is_unreachable_for_xlsx_entries",
        "assert_manifest_capability_enabled",
        "assert_no_implicit_template_fallback",
        "assert_pilot_entry_selectable",
        "attach_pilot_adapters",
        "authoritative_template_path",
        "authority_model_payload",
        "build_contract_payload",
        "build_store_projection",
        "instrumentation_definition_payload",
        "instrumentation_spec",
        "iter_store_rows",
        "load_pilot_contract",
        "publish_pilot_definitions",
        "read_authoritative_template",
        "register_pilot_adapter",
        "render_schema_template_path",
        "resolve_published_frozen_definitions",
        "split_store_row",
        "stable_key_for",
        "store_row_identity",
        "template_definition_payload",
        # registry.py 只加不动（交付登记表追加第二条）
        "DELIVERED_PER_ENTRY_CONTRACTS",
        # 契约目录清册
        "available_contract_ids",
        "contract_path_for",
        # 分块 sidecar / 预算（本任务复用并端到端跑）
        "write_projection_sidecar",
        "read_projection_sidecar",
        "StreamingProjectionBudget",
        "rows_per_chunk",
        # DYNAMIC 家族欠账的判据对象
        "DYNAMIC_SCENARIOS",
    }
)

#: 本任务新增 / 会被本任务改变判定的数据文件（按**文件名**匹配 `ast.Constant` 字符串）。
CHANGED_DATA_FILES: frozenset[str] = frozenset(
    {
        "d2.receivable_detail.json",
        "workpaper_sync_contracts",
        "workpaper_writer_inventory.json",
        "workpaper_resolver_migration_matrix.json",
        "workpaper_writer_domain_overlay.json",
        "workpaper_sync_entry_manifest.json",
        "generate_pilot_d2_large_json_contract.py",
        "generate_workpaper_writer_inventory.py",
        "generate_workpaper_resolver_migration_matrix.py",
        "check_workpaper_writer_revision_gate.py",
        "D2A.yaml",
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
    parser = argparse.ArgumentParser(description="Task 41 辐射面选取")
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
    print(
        f"\n辐射面：{len(rels)} 个测试文件"
        "（AST 级 import/符号引用/生成物文件名 + 测试模块 import 闭包）"
    )
    print(f"分母参考：backend/tests 下共 {len(list(TESTS.rglob('test_*.py')))} 个测试文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
