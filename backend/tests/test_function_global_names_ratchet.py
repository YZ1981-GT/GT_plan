"""全部 ``app`` 模块：函数体里引用的模块级名字必须有定义 —— 只许减少的棘轮（spec formula-fetch-followup-defect-closure 7.2）。

为什么需要：``formula_engine`` 的 ``NOTEExecutor`` / ``REPORTExecutor`` 在函数体里写 ``sa.text(...)``，模块从未导入 ``sa``
⇒ 每次调用都 NameError，又被自身的 ``except Exception: return 0`` 吞掉 —— 报表生成、报表审核、表间审核、公式试算里
任何 NOTE 都恒为 0，从来不报错（7.2 浏览器实测：真库安徽 ``NOTE('八、1','合计','期末余额')`` 应为 9,182,572.99）。
``test_deliverable_modules_names_resolve.py`` 有同一判据，但只覆盖交付中心 15 个模块。

判据（同上）：``symtable`` 作用域分析，每个非注解作用域里被引用的隐式全局名，必须在已导入模块的命名空间或内置名里。
源码按 ``utf-8-sig`` 读（有 4 个模块带 BOM，按 utf-8 读 symtable 直接报错 ⇒ 这几个模块会静默漏扫）。

现存缺口冻结在 :data:`KNOWN_UNRESOLVED`：每一条都是调用即 NameError 的真缺陷，各自归属的模块另行修复；修掉一条就从
基线删一条（守卫会提示），不许新增。键不含行号（行号会漂）。
"""

from __future__ import annotations

import builtins
import importlib
import pkgutil
import symtable
from collections import Counter
from pathlib import Path

import pytest

#: (模块, 作用域名, 名字) → 说明。🔴 修复前先读说明：有的修了 NameError 就会把另一个缺陷放出来。
KNOWN_UNRESOLVED: dict[tuple[str, str, str], str] = {
    # 已修（spec formula-fetch-followup-defect-closure A4）：sa 导入 + require_project_access("edit")
    ("app.routers.time_machine", "_load_instance_data", "logger"): "只在异常分支用到：读失败时再抛 NameError",
    ("app.routers.time_machine", "_save_instance_data", "logger"): "同上（写失败分支）",
    ("app.routers.wp_render_strategies._h4_engineering_materials", "_build_h4_detail_prefill", "_is_leaf"):
        "H4 工程物资明细预填调用即 NameError",
    ("app.services.excel_html_converter", "_add_page_number", "Pt"): "Word 页码（python-docx 的 Pt 未导入）",
    ("app.services.guidance_publication_service", "create_draft", "actor_user_id"): "函数体用了不存在的变量名",
    ("app.services.knowledge_index_service", "add_document", "timezone"): "未导入 datetime.timezone",
    ("app.services.knowledge_index_service", "update_index", "timezone"): "同上",
    ("app.services.partner_service", "check_workpaper_readiness", "sa"): "合伙人底稿就绪检查调用即 NameError",
    ("app.services.smart_import_engine", "smart_parse_files", "acct_records"): "智能导入解析：内部函数引用未定义变量",
    ("app.services.smart_import_engine", "smart_parse_files", "project_id"): "同上",
    ("app.services.smart_import_engine", "smart_parse_files", "seen_codes"): "同上",
    ("app.services.smart_import_engine", "smart_parse_files", "by_category"): "同上",
    ("app.services.smart_import_engine", "write_four_tables", "_dataset_id"): "四表写入：引用未定义变量",
}


def _unresolved(mod) -> list[tuple[str, str, str]]:
    path = Path(mod.__file__)
    table = symtable.symtable(path.read_text(encoding="utf-8-sig"), str(path), "exec")
    namespace = vars(mod)
    out: list[tuple[str, str, str]] = []

    def walk(t: symtable.SymbolTable) -> None:
        if t.get_type() == "annotation" or t.get_name() == "_annotation":
            return
        for sym in t.get_symbols():
            name = sym.get_name()
            if (sym.is_global() and sym.is_referenced() and not sym.is_assigned()
                    and name not in namespace and not hasattr(builtins, name)):
                out.append((mod.__name__, t.get_name(), name))
        for child in t.get_children():
            walk(child)

    for child in table.get_children():
        walk(child)
    return out


def _scan(package: str = "app") -> tuple[Counter, list[str]]:
    pkg = importlib.import_module(package)
    found: Counter = Counter()
    failed: list[str] = []
    for info in pkgutil.walk_packages(pkg.__path__, f"{package}."):
        try:
            mod = importlib.import_module(info.name)
        except Exception as exc:  # noqa: BLE001 —— 导入失败如实列出
            failed.append(f"{info.name}: {type(exc).__name__}: {str(exc)[:120]}")
            continue
        if not str(getattr(mod, "__file__", "") or "").endswith(".py"):
            continue
        found.update(_unresolved(mod))
    return found, failed


@pytest.fixture(scope="module")
def scan() -> tuple[Counter, list[str]]:
    return _scan()


def test_every_app_module_was_scanned(scan) -> None:
    _found, failed = scan
    assert not failed, "以下模块导入失败，名字判据无法执行：\n  " + "\n  ".join(failed)


def test_no_new_unresolved_function_globals(scan) -> None:
    found, _failed = scan
    new = sorted(set(found) - set(KNOWN_UNRESOLVED))
    assert not new, ("函数体引用了模块里没有定义的名字（调用即 NameError；若外层有 except 会被吞成静默错值）：\n  "
                     + "\n  ".join(f"{m}: {scope}() 用了 {name}" for m, scope, name in new))


def test_known_gaps_are_still_real(scan) -> None:
    """修掉一条就从基线删一条：基线里不能留已经不存在的缺口（否则以后再犯同一处也不报）。"""
    found, _failed = scan
    stale = sorted(set(KNOWN_UNRESOLVED) - set(found))
    assert not stale, "以下缺口已修复，请从 KNOWN_UNRESOLVED 删除：\n  " + "\n  ".join(map(str, stale))


def test_formula_executors_have_no_unresolved_names() -> None:
    """钉住本次修复：NOTE / REPORT 执行器不再引用未导入的 ``sa``。"""
    assert _unresolved(importlib.import_module("app.services.formula_engine")) == []


def test_detector_flags_missing_import_and_reads_bom_files(tmp_path, monkeypatch) -> None:
    """变异：函数体引用未导入的名字必须被报出；带 BOM 的源文件也要能扫（防判据空转）。"""
    pkg = tmp_path / "zz_names_ratchet_probe"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "m.py").write_text(
        "from __future__ import annotations\n"
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n    from uuid import UUID\n"
        "def ok(x: UUID) -> int:\n    return len([y for y in range(3)])\n"
        "class Executor:\n    @staticmethod\n    async def execute(db):\n        return await db.execute(sa.text('x'))\n",
        encoding="utf-8-sig",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    found, failed = _scan("zz_names_ratchet_probe")
    assert failed == []
    assert list(found) == [("zz_names_ratchet_probe.m", "execute", "sa")]
