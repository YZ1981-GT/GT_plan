"""交付中心三件套链路模块：函数体里引用的模块级名字都必须真的有定义（spec deliverable-trio-generation-accuracy）。

为什么需要（2026-10-16）：``routers/deliverable.py`` 的 OnlyOffice 配置端点在可编辑态调用 ``deliverable_doc_key``，
模块从未导入它 ⇒ 打开草稿交付件在线编辑必 ``NameError``（500）。既有守卫按**源码文本**判「路由引用了
``deliverable_doc_key``」，名字写在那里就算通过 —— 文本匹配分不清「引用」与「已定义」。

判据用 ``symtable``（编译器自己的作用域分析，含嵌套函数 / 推导式 / 类体）：每个非注解作用域里被引用的
隐式全局名，必须在已导入模块的命名空间或内置名里。注解块（``from __future__ import annotations`` 下不求值，
``TYPE_CHECKING`` 专用名合法地缺席）跳过。
"""

from __future__ import annotations

import builtins
import importlib
import symtable
from pathlib import Path

import pytest

MODULES = [
    "app.routers.deliverable",
    "app.services.note_word_exporter",
    "app.services.note_template_export_fill",
    "app.services.note_template_block_fill",
    "app.services.note_template_doc_ops",
    "app.services.note_template_table_look",
    "app.services.note_template_docx_base",
    "app.services.note_deliverable_outline",
    "app.services.note_deliverable_filter",
    "app.services.report_excel_exporter",
    "app.services.report_excel_sheet_ops",
    "app.services.report_template_binding",
    "app.services.report_export_checks",
    "app.services.report_prior_period",
    "app.services.financial_report_drift_service",
]


def _unresolved(module_name: str) -> list[str]:
    mod = importlib.import_module(module_name)
    path = Path(mod.__file__)
    table = symtable.symtable(path.read_text(encoding="utf-8"), str(path), "exec")
    namespace = vars(mod)
    out: list[str] = []

    def walk(t: symtable.SymbolTable) -> None:
        if t.get_type() == "annotation" or t.get_name() == "_annotation":
            return
        for sym in t.get_symbols():
            name = sym.get_name()
            if (sym.is_global() and sym.is_referenced() and not sym.is_assigned()
                    and name not in namespace and not hasattr(builtins, name)):
                out.append(f"{t.get_name()}(L{t.get_lineno()}): {name}")
        for child in t.get_children():
            walk(child)

    for child in table.get_children():
        walk(child)
    return out


@pytest.mark.parametrize("module_name", MODULES)
def test_function_level_global_names_are_defined(module_name: str) -> None:
    assert _unresolved(module_name) == []


def test_detector_catches_missing_module_import(tmp_path, monkeypatch) -> None:
    """变异：函数体引用一个未导入的名字必须被报出（防判据空转）。"""
    pkg = tmp_path / "zz_names_probe"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "m.py").write_text(
        "from __future__ import annotations\n"
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n    from uuid import UUID\n"
        "def ok(x: UUID) -> int:\n    return len([y for y in range(3)])\n"
        "def bad(task_id):\n    return deliverable_doc_key(task_id, 1)\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    assert _unresolved("zz_names_probe.m") == ["bad(L7): deliverable_doc_key"]
