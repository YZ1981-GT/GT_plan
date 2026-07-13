"""CI drift guard — bulk manifest 字段 100% 来自 ACNR catalog。

Task 10.1（Phase 4 契约守卫）。Requirements 7.1, 7.2。

`ManifestBuilder` 的铁律：路由元数据只来自 ACNR
（`acnr.manifest.list_import_export` / `wp_bulk_tab_export.list_export_sheets` /
`acnr.catalog.list_sheets`），不手写 sheet 清单、不读分散 JSON、不硬编码
prefix→sheet 映射。本守卫用源码静态扫描 + AST 双重锁定该不变式：若日后有人
在 `manifest_builder.py` 引入非 ACNR 数据源（open()/json.load/硬编码清单/
wp_account_mapping 等），CI 立即失败。

与运行期属性测试互补：
  - test_bulk_import_export_properties_pbt.py::P2 断言"运行期每个 manifest 字段
    可溯源到 ACNR entry"（行为层）。
  - 本文件断言"源码层不存在任何非 ACNR 数据源"（防漂移层）。
"""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import app.services.bulk_tab.manifest_builder as mb


_SRC_PATH = Path(inspect.getfile(mb))
_SRC = _SRC_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1) 数据来源白名单：build_manifest 只调 3 个 ACNR 取数函数
# ---------------------------------------------------------------------------

# 允许的取数函数（全部来自 ACNR / bulk 排序层，后者也只读 ACNR）
_ALLOWED_DATA_FNS = {
    "list_export_sheets",   # wp_bulk_tab_export（内部读 ACNR + 拓扑排序）
    "list_import_export",   # acnr.manifest
    "list_sheets",          # acnr.catalog
}


def test_build_manifest_data_sources_are_acnr_only() -> None:
    """build_manifest 体内 import 的取数符号必须 ⊆ ACNR 白名单。"""
    tree = ast.parse(_SRC)
    build_fn = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "build_manifest"
        ),
        None,
    )
    assert build_fn is not None, "未找到 build_manifest 定义"

    imported_from_acnr: set[str] = set()
    imported_modules: list[str] = []
    for node in ast.walk(build_fn):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            imported_modules.append(mod)
            # 取数函数只允许来自 acnr.* 或 wp_bulk_tab_export
            if mod.startswith("app.services.acnr") or mod == "app.services.wp_bulk_tab_export":
                for alias in node.names:
                    imported_from_acnr.add(alias.name)
            else:
                # build_manifest 体内不得从其它模块 import 取数符号
                # （catalog 异常类型等允许，但取数函数必须来自 ACNR）
                for alias in node.names:
                    assert alias.name not in {"list_export_sheets", "list_import_export", "list_sheets"}, (
                        f"取数函数 {alias.name} 来自非 ACNR 模块 {mod}"
                    )

    # 实际用于取数的三函数必须全部来自 ACNR
    for fn in _ALLOWED_DATA_FNS:
        assert fn in imported_from_acnr, (
            f"build_manifest 未从 ACNR 导入取数函数 {fn}（实际 import 模块：{imported_modules}）"
        )


# ---------------------------------------------------------------------------
# 2) 禁止非 ACNR 数据源：无 open()/json.load/硬编码清单/wp_account_mapping
# ---------------------------------------------------------------------------

_FORBIDDEN_PATTERNS = {
    "open(": r"\bopen\s*\(",
    "json.load": r"\bjson\.loads?\s*\(",
    "wp_account_mapping": r"wp_account_mapping",
    "read_text(": r"\.read_text\s*\(",
    "读硬编码 render schema": r"wp_render_schema",
    "SHEET_COLUMNS 硬编码列": r"\bSHEET_COLUMNS\b",
}


def test_manifest_builder_has_no_non_acnr_data_source() -> None:
    """源码不得出现任何非 ACNR 数据源模式（防止有人绕过 ACNR 手写清单）。"""
    violations: list[str] = []
    for label, pat in _FORBIDDEN_PATTERNS.items():
        if re.search(pat, _SRC):
            violations.append(label)
    assert not violations, (
        f"manifest_builder.py 出现非 ACNR 数据源: {violations} —— "
        f"路由元数据只能来自 ACNR（Req 7.1/7.2）"
    )


# ---------------------------------------------------------------------------
# 3) 路由字段全部从 entry.get(...) 动态取，非硬编码常量
# ---------------------------------------------------------------------------

# ManifestFileEntry 的路由字段（必须逐个从 ACNR entry 动态取）
_ROUTING_FIELDS = [
    "addr_id",
    "sheet_code",
    "api_prefix",
    "item_id",
    "storage_field",
    "wp_id",
    "import_order",
    "depends_on_sheets",
]


def test_routing_fields_read_from_entry() -> None:
    """每个路由字段都以 entry.get('<field>' ...) 形式从 ACNR 条目读取。"""
    missing: list[str] = []
    for fld in _ROUTING_FIELDS:
        # 允许 entry.get("field") 或 cat_entry.get("field")
        pat = rf"\.get\(\s*[\"']{re.escape(fld)}[\"']"
        if not re.search(pat, _SRC):
            missing.append(fld)
    assert not missing, (
        f"路由字段未从 ACNR entry 动态读取（疑似硬编码）: {missing}"
    )


# ---------------------------------------------------------------------------
# 4) catalog 不可用必抛异常（Req 7.4，绝不静默降级）
# ---------------------------------------------------------------------------


def test_catalog_unavailable_raises_not_silent() -> None:
    """源码在 CatalogLoadError 时抛 AcnrCatalogUnavailableError（不静默 fallback）。"""
    assert "AcnrCatalogUnavailableError" in _SRC
    assert "CatalogLoadError" in _SRC
    # 每个 catalog 取数点都 raise（不得 except: pass 静默）
    assert _SRC.count("raise AcnrCatalogUnavailableError") >= 3, (
        "并非每个 ACNR 取数点在 catalog 不可用时都抛异常"
    )
