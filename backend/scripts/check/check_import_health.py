#!/usr/bin/env python3
"""推送前 import 健康检查 —— 拦截缺失模块和不存在的导入名。

检查范围：
  1. 后端 app/ 下所有 from app.xxx import yyy：
     - 目标模块是否在磁盘上存在（文件或包）
     - 导入名是否可解析（显式定义 / re-export / 子模块）
  2. 前端 components.d.ts 无死注册（引用不存在的 .vue 文件）

不检查的情况（避免误报）：
  - TYPE_CHECKING 块内的 import（只在类型检查器跑）
  - 运行时动态赋值的名字（如 X3_SHEET_SPECS = _load()）无法静态识别，
    已知的动态模式写在白名单里
  - 第三方包引用

返回码：
  0  全部通过
  1  发现缺陷，拒绝推送

被 .git-hooks/pre-push 调用。也可独立运行：
  python backend/scripts/check/check_import_health.py [--root <dir>]
"""
from __future__ import annotations

import argparse
import ast
import pathlib
import sys


# ── 已知动态导出白名单 ──────────────────────────────────────
# 这些名字在目标模块里通过动态机制定义，AST 静态扫描看不到。
# 格式：(module, name)
_DYNAMIC_EXPORT_WHITELIST: set[tuple[str, str]] = {
    # _x3: X3_SHEET_SPECS, COLUMN_ORDER = _load()
    ("app.routers.wp_render_strategies._x3_adjustment_import_export", "X3_SHEET_SPECS"),
    ("app.routers.wp_render_strategies._x3_adjustment_import_export", "COLUMN_ORDER"),
    # database: engine = create_async_engine(...)，在 if/else 分支内
    ("app.core.database", "engine"),
    ("app.core.database", "async_engine"),
    ("app.core.database", "get_db"),
    ("app.core.database", "get_sync_db"),
    ("app.core.database", "set_rls_context"),
    ("app.core.database", "async_session"),
    # note_template_docx_base: _W_P, _W_TBL = qn("w:p"), qn("w:tbl")（tuple unpack）
    ("app.services.note_template_docx_base", "_W_P"),
    ("app.services.note_template_docx_base", "_W_TBL"),
    # archive_inventory: OK, MISSING, SKIPPED = "ok", "missing", "skipped"（tuple unpack）
    ("app.services.archive_inventory", "OK"),
    ("app.services.archive_inventory", "MISSING"),
    ("app.services.archive_inventory", "SKIPPED"),
    # excel_row_shift: _derive_structure_tables() 动态赋值
    ("app.services.workpaper_sync.excel_row_shift", "STRUCTURE_BARE_ROW_ATTRS"),
    ("app.services.workpaper_sync.excel_row_shift", "STRUCTURE_ROW_BEARING_ATTRS"),
    ("app.services.workpaper_sync.excel_row_shift", "STRUCTURE_ROW_BEARING_TEXT_TAGS"),
    # note_prior_year_plan: STATUS_AUTO, STATUS_CONFIRM, STATUS_NONE = "auto", ...（tuple unpack）
    ("app.services.note_prior_year_plan", "STATUS_AUTO"),
    ("app.services.note_prior_year_plan", "STATUS_CONFIRM"),
    ("app.services.note_prior_year_plan", "STATUS_NONE"),
    # stale_propagation_engine: 模块级实例
    ("app.services.stale_propagation_engine", "stale_engine"),
    # ledger_import.metrics: Prometheus 可选依赖，try/except 保护
    ("app.services.ledger_import.metrics", "IMPORT_DURATION"),
    ("app.services.ledger_import.metrics", "_PROMETHEUS_AVAILABLE"),
    # _e1_monetary_fund: _build_four_table_prefill 在 try/except 保护下按需调用
    ("app.routers.wp_render_strategies._e1_monetary_fund", "_build_four_table_prefill"),
    # FinancialReport: ORM 类在 audit_platform_models 中通过动态注册
    ("app.models.audit_platform_models", "FinancialReport"),
    ("app.models.audit_platform_models", "ReportType"),
    # ai_chat.audit: audit_event 在 try/except 保护下，审计失败不阻断启动
    ("app.services.ai_chat.audit", "audit_event"),
}

# 已知的 importlib 动态 re-export 包（__init__.py 用 importlib + setattr 代理子模块）
# 对这些包不做名字检查（子模块的全部属性通过 setattr 暴露）
_DYNAMIC_REEXPORT_PACKAGES: set[str] = {
    "app.services.event_handlers",
    "app.routers.wp_render_strategies._d1_import_export",
}

# 已知的 __getattr__ 延迟转发模块
_GETATTR_MODULES: set[str] = {
    "app.services.guidance_inventory",
    "app.services.guidance_source_refs",
}

# 已知的未创建模块（条件开关=False 的预留接口）
_UNBUILT_MODULE_WHITELIST: set[str] = {
    # phase5_f4_09: _INCLUDE_F409 = False，模块尚未创建
    "app.services.workpaper_sync.phase5_f4_09_supplier_financing",
}


def _build_index(app_dir: pathlib.Path, backend_dir: pathlib.Path):
    """构建模块索引和导出名索引。"""
    all_files: set[str] = set()
    all_modules: set[str] = set()
    module_exports: dict[str, set[str]] = {}

    for py in app_dir.rglob("*.py"):
        if "__pycache__" in str(py):
            continue
        rel = str(py.relative_to(backend_dir)).replace("\\", "/")
        all_files.add(rel)
        mod = rel.replace("/", ".").removesuffix(".py")
        parts = mod.split(".")
        for i in range(1, len(parts) + 1):
            all_modules.add(".".join(parts[:i]))

        try:
            raw = py.read_bytes()
            if raw.startswith(b"\xef\xbb\xbf"):
                raw = raw[3:]
            tree = ast.parse(raw.decode("utf-8", "replace"))
        except Exception:
            continue

        exports: set[str] = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                exports.add(node.name)
            elif isinstance(node, ast.ClassDef):
                exports.add(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        exports.add(t.id)
                    elif isinstance(t, ast.Tuple):
                        for elt in t.elts:
                            if isinstance(elt, ast.Name):
                                exports.add(elt.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                exports.add(node.target.id)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    exports.add(alias.asname or alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    exports.add(alias.asname or alias.name.split(".")[-1])
        module_exports[mod] = exports

    return all_files, all_modules, module_exports


def _mod_on_disk(mod: str, all_modules: set[str], all_files: set[str]) -> bool:
    if mod in all_modules:
        return True
    return (mod.replace(".", "/") + ".py") in all_files or \
           (mod.replace(".", "/") + "/__init__.py") in all_files


def _name_resolvable(mod: str, name: str,
                     all_modules: set[str], all_files: set[str],
                     module_exports: dict[str, set[str]]) -> bool:
    # 白名单
    if (mod, name) in _DYNAMIC_EXPORT_WHITELIST:
        return True
    # 动态 re-export 包
    if mod in _DYNAMIC_REEXPORT_PACKAGES:
        return True
    # __getattr__ 延迟转发
    if mod in _GETATTR_MODULES:
        return True
    # 显式导出
    if mod in module_exports and name in module_exports[mod]:
        return True
    init = mod + ".__init__"
    if init in module_exports and name in module_exports[init]:
        return True
    # 子模块
    sub = mod + "." + name
    if _mod_on_disk(sub, all_modules, all_files):
        return True
    # 未创建模块白名单
    if sub in _UNBUILT_MODULE_WHITELIST:
        return True
    return False


def _is_type_checking(tree: ast.AST, lineno: int) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            if isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
                if hasattr(node, "end_lineno") and node.lineno <= lineno <= node.end_lineno:
                    return True
    return False


def check_backend(root: pathlib.Path) -> list[str]:
    """检查后端 import 健康度，返回错误消息列表。"""
    backend = root / "backend"
    app_dir = backend / "app"
    if not app_dir.exists():
        return ["backend/app/ 目录不存在"]

    all_files, all_modules, module_exports = _build_index(app_dir, backend)
    errors: list[str] = []
    seen: set[tuple[str, str, str]] = set()

    for py in sorted(app_dir.rglob("*.py")):
        if "__pycache__" in str(py):
            continue
        rel = str(py.relative_to(backend)).replace("\\", "/")
        try:
            raw = py.read_bytes()
            if raw.startswith(b"\xef\xbb\xbf"):
                raw = raw[3:]
            tree = ast.parse(raw.decode("utf-8", "replace"))
        except Exception:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if not node.module or not node.module.startswith("app."):
                continue
            if _is_type_checking(tree, node.lineno):
                continue

            mod = node.module
            if not _mod_on_disk(mod, all_modules, all_files):
                # 整个模块缺失
                if mod in _UNBUILT_MODULE_WHITELIST:
                    continue
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    key = (rel, mod, alias.name)
                    if key in seen:
                        continue
                    seen.add(key)
                    # 白名单检查（整个模块在白名单包中也放行）
                    if (mod, alias.name) in _DYNAMIC_EXPORT_WHITELIST:
                        continue
                    if mod in _DYNAMIC_REEXPORT_PACKAGES or mod in _GETATTR_MODULES:
                        continue
                    errors.append(f"  {rel}:{node.lineno} -> from {mod} import {alias.name}  [MODULE_MISSING]")
                continue

            for alias in node.names:
                if alias.name == "*":
                    continue
                key = (rel, mod, alias.name)
                if key in seen:
                    continue
                seen.add(key)
                if not _name_resolvable(mod, alias.name, all_modules, all_files, module_exports):
                    errors.append(f"  {rel}:{node.lineno} -> from {mod} import {alias.name}  [NAME_MISSING]")

    return errors


def check_frontend_dts(root: pathlib.Path) -> list[str]:
    """检查 components.d.ts 中注册的组件文件是否存在。"""
    import re
    fe_src = root / "audit-platform" / "frontend" / "src"
    dts = fe_src / "components.d.ts"
    if not dts.exists():
        return []  # 文件不存在时不报错（可能未生成）

    text = dts.read_text("utf-8", errors="replace")
    import_re = re.compile(r"""typeof import\(['"](\./[^'"]+)['"]\)""")
    errors: list[str] = []

    for imp in import_re.findall(text):
        target = fe_src / imp.lstrip("./")
        candidates = [target, target.with_suffix(".ts"), target.with_suffix(".vue")]
        if not any(c.exists() for c in candidates):
            errors.append(f"  components.d.ts -> {imp}  [FILE_MISSING]")

    return errors


def main():
    parser = argparse.ArgumentParser(description="Import 健康检查")
    parser.add_argument("--root", default=".", help="仓库根目录")
    args = parser.parse_args()
    root = pathlib.Path(args.root).resolve()

    print("[import-health] 检查后端 import 引用...")
    be_errors = check_backend(root)
    print("[import-health] 检查前端 components.d.ts...")
    fe_errors = check_frontend_dts(root)

    all_errors = be_errors + fe_errors
    if all_errors:
        print(f"\n[import-health] ❌ 发现 {len(all_errors)} 处 import 缺陷：")
        for e in all_errors:
            print(e)
        print()
        print("[import-health] 修复后再推送。紧急救急：git push --no-verify")
        return 1
    else:
        print("[import-health] ✅ 后端 import + 前端 components.d.ts 全部通过")
        return 0


if __name__ == "__main__":
    sys.exit(main())
