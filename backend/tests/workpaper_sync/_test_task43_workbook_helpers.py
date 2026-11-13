# -*- coding: utf-8 -*-
"""Task 43（G7 两级动态 pilot）守卫的工作簿读写辅助（从 `test_task43_g7_two_level_dynamic_pilot.py` 拆出）。

拆分只为行数门：代码逐行原样搬来，判据与 fixtures 仍在测试模块里。这里放的是**对真实权威册的
操作** —— sheet part 定位、Excel Table 扩行、插行、UUID 列普查、公式缓存回填。

"""
from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path
from typing import Any, Mapping

from app.services.workpaper_sync import pilot_g7_two_level_dynamic as P
from test_task37_excel_extract import _read_entries, _write_entries, patch_cells

_BACKEND = Path(__file__).resolve().parents[2]

FIRST = P.RECORD_FIRST_ROW
LAST = P.RECORD_LAST_ROW
#: 记录表的六个公式列（`A` 是 auto_source 字面量）。
RECORD_FORMULA_COLUMNS = tuple(
    column for _key, column, mode, *_rest in P.RECORD_COLUMNS if mode == "formula"
)
#: 记录表公式格数（6 列 x 5 行，逐格实测）—— 本模块是它的单一来源，测试模块从这里 import。
EXPECTED_RECORD_FORMULA_CELLS = 30

def _d(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def uid(row: int) -> str:
    """instrumentation 预生成的行 UUID 字面量（与 `spec.row_uuid` 同形态）。"""
    return f"GTROW-{P.TEMPLATE_ID}-{row:04d}"


def _non_docstring_literals(path: Path) -> list[str]:
    """模块里的**非 docstring** 字符串字面量。

    docstring 必须剥掉：本任务的生产模块 docstring 里刻意写着「参考副本一次都不读」
    「不借用 B60/D2/H1 的 identity」这类**说明**，纯字面量判据会把说明本身判成违规。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = (node.body or [None])[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                docstrings.add(id(first.value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def function_body_code(path: Path, name: str) -> str:
    """某个函数的**可执行体**源码（剥掉 docstring 与注释）。

    🔴 必须剥：本任务的生产函数 docstring 里刻意写着「不写死 5，也不写死 10」「在这里重写
    一遍 ``f"{slot}_{seq}"`` 的后果……」这类**说明**，纯字面量/正则判据会把说明本身判成
    违规（首轮实测就是这么打红的两条）。`ast.unparse` 只输出语句，注释与 docstring 天然
    不在其中。
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            body = list(node.body)
            first = body[0] if body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                body = body[1:]
            assert body, f"{name} 的函数体只有 docstring"
            return "\n".join(ast.unparse(stmt) for stmt in body)
    raise AssertionError(f"{path.name} 里找不到函数 {name}")


def observe_template_resolution() -> Any:
    """借用契约生成器里的**同一个**观测器（不抄第二份）。

    观测器住在 `backend/scripts/gen/` 而不是 `backend/app/`：`find_template_file*` 是
    Task 19 清册登记的 non-canonical resolver 符号，生产模块里出现它们会给收口门增债
    （见 `P.TemplateResolutionFacts` 的 docstring）。
    """
    import importlib.util

    path = _BACKEND / "scripts" / "gen" / "generate_pilot_g7_two_level_dynamic_contract.py"
    spec = importlib.util.spec_from_file_location("_t43_contract_gen", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.observe_template_resolution()


# ═══════════════════════════════════════════════════════════════════════════
# fixtures：真实 manifest / 真实权威模板 / 真实注入产物（不手搓 xlsx）
# ═══════════════════════════════════════════════════════════════════════════


def sheet_part_of(data: bytes, sheet_name: str) -> str:
    """sheet 展示名 → sheet part 路径（**属性顺序无关**）。

    🔴 不复用 `test_task37_excel_extract._sheet_part_of`：它写的是
    ``Id="{rid}"[^>]*Target="..."``，隐含「Id 必须排在 Target 之前」，而本任务的权威模板
    实测是 `Type` → `Target` → `Id` 顺序（生产侧 `excel_instrumentation._sheet_part_for`
    的同一条缺陷已由 Task 42 修掉，本文件的
    `TestUpstreamRelsAndNamespaceShapesStillHold` 对它做反向自检）。
    """
    entries = _read_entries(data)
    workbook = entries["xl/workbook.xml"].decode("utf-8")
    match = re.search(
        r'<sheet [^>]*name="' + re.escape(sheet_name) + r'"[^>]*r:id="(rId\d+)"', workbook
    )
    assert match, sheet_name
    rid = match.group(1)
    rels = entries["xl/_rels/workbook.xml.rels"].decode("utf-8")
    for candidate in re.finditer(r"<Relationship\b[^>]*?/?>", rels):
        if re.search(r'\bId="' + re.escape(rid) + r'"', candidate.group(0)):
            target = re.search(r'\bTarget="([^"]+)"', candidate.group(0))
            assert target, candidate.group(0)
            path = target.group(1).lstrip("/")
            return path if path.startswith("xl/") else f"xl/{path}"
    raise AssertionError(f"rels 里找不到 {rid}")


def grow_table_to(data: bytes, last_row: int) -> bytes:
    """把 Excel Table 的 ref 行区间扩到 `last_row`（模拟 OO 插行）。"""
    entries = _read_entries(data)
    part = next(name for name in entries if name.startswith("xl/tables/"))
    xml = entries[part].decode("utf-8")
    grown, count = re.subn(
        r'ref="A\d+:([A-Z]+)\d+"', rf'ref="A{FIRST}:\g<1>{last_row}"', xml, count=1
    )
    assert count == 1 and grown != xml, "Table ref 未扩 —— fixture 会变成无效变异"
    entries[part] = grown.encode("utf-8")
    return _write_entries(entries)


def add_row(data: bytes, part: str, *, row: int, cells: Mapping[str, Any]) -> bytes:
    """在受管区域**末尾追加一行**：先扩 Table ref，再写该行的格。

    🔴 这是「OO 新增行」的正确 fixture 形态。改**已有行**（清空/换重复 UUID）在语义上是
    「原有 identity 消失」⇒ 先被保留门（Property 66）拦住，身份分类分支根本走不到 ——
    「真实数据上分支不可达 = 永久 GREEN」的典型（Task 37 实测踩过）。
    """
    return patch_cells(grow_table_to(data, row), part, cells)


def uuid_cell_occurrences(data: bytes, part: str) -> dict[str, int]:
    """UUID 列每个坐标在 sheet XML 里出现几次（正常必须恰 1 次）。

    🔴 这条 helper 存在的理由是**本任务修掉的第 4 条生产缺陷**：
    `_add_uuid_cells` 原来无条件在 `</row>` 前追加，而本 sheet 的 `N79..N83` 在模板里已有
    「有样式、无值」的格 ⇒ 同一行出现两个相同 `r` 的 `<c>`（非法 OOXML）。首轮实测时
    `patch_cells` 因此改到了**前一个**（模板那一个），三条结构操作 fixture 静默失效。
    """
    xml = _read_entries(data)[part].decode("utf-8")
    return {
        f"{P.UUID_COL}{row}": len(
            re.findall(rf'<c r="{P.UUID_COL}{row}"(?:\s|/|>)', xml)
        )
        for row in range(FIRST, LAST + 2)
    }


def assert_uuid_cells_are_unique(data: bytes, part: str) -> None:
    counts = uuid_cell_occurrences(data, part)
    duplicated = {coord: n for coord, n in counts.items() if n > 1}
    assert not duplicated, f"UUID 格重复出现 {duplicated} —— 非法 OOXML，fixture 会改错格"


def fill_record_formula_cache(data: bytes, part: str) -> bytes:
    """给记录表六个公式列补缓存值 `<v>`（并按列的 `value_type` 给对的载体）。

    🔴 为什么必须补：权威模板里公式格是 ``<f>…</f><v></v>`` —— **缓存值是空的**（模板从未
    被计算过）。`excel_extract` 按 Task 14 语义把读到 `None` 的格当 MISSING
    （`if not present: continue`），于是公式字段既不进 projection、也不进
    `formula_inventory`。真实 OO 往返回来的工作簿一定带缓存值，所以 fixture 必须补上，
    否则「公式范围」判据会在一个恒空的集合上通过（假绿第⑤源）。

    🔴 文本列必须补 `t="str"`：源格没有 `t` 属性（数值型），直接塞文本会让 openpyxl 在
    `_cast_number` 抛 `ValueError`（实测踩过一次）。模板自身那个「缓存值为空」的事实由
    `TestAuthoritativeTemplate::test_record_formula_cells_ship_without_cached_values`
    单独钉住。
    """
    numeric_columns = {
        column
        for _key, column, mode, value_type, *_rest in P.RECORD_COLUMNS
        if mode == "formula" and value_type != "text"
    }
    entries = _read_entries(data)
    xml = entries[part].decode("utf-8")
    filled = 0
    for column in RECORD_FORMULA_COLUMNS:
        numeric = column in numeric_columns
        for row in range(FIRST, LAST + 1):
            pattern = re.compile(
                r'<c r="' + column + str(row) + r'"([^>]*)>(<f>[^<]*</f>)<v></v>'
            )

            def repl(match: re.Match[str], _col: str = column, _row: int = row,
                     _numeric: bool = numeric) -> str:
                attrs = match.group(1)
                if _numeric:
                    return f'<c r="{_col}{_row}"{attrs}>{match.group(2)}<v>{_row}</v>'
                if 't="' not in attrs:
                    attrs = f'{attrs} t="str"'
                return f'<c r="{_col}{_row}"{attrs}>{match.group(2)}<v>V{_col}{_row}</v>'

            xml, count = pattern.subn(repl, xml, count=1)
            filled += count
    assert filled == EXPECTED_RECORD_FORMULA_CELLS, (
        f"只补了 {filled} 个公式缓存值（期望 {EXPECTED_RECORD_FORMULA_CELLS}）—— "
        "模板的公式格形态已变，公式范围判据会退化成空集"
    )
    entries[part] = xml.encode("utf-8")
    return _write_entries(entries)
