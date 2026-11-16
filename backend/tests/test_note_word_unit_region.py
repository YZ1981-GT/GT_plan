"""附注 Word 普通/clone 两条路径消费 `kind`/`scale` 的守卫
（spec platform-global-display-settings-closure 任务 6C / AC-11 的 Word 部分、AC-20、AC-24）。

🔴 改造前：`NoteWordExporter._render_table` 与
`note_template_table_look.render_cloned_table` 两个内核**签名里都没有**
`ExportUnitRegion` —— 所有数字一律 `fmt_amount_gt`（金额格式 + 千分位）：

- 金额列在万元项目里**不折算**（金额差 1 万倍）；
- 比例列被写成「1,234.50」这种**金额形态**（与金额无法区分）。

6C 把列语义下沉到两个内核，且**共用同一套** `_apply_region_policy` / `_fmt_ratio`：
两条路径结果必须一致，否则同一张表走不同路径会差 100 倍或 1 万倍。

判据分五层：
1. 只有 `amount` 执行 divisor；其余 kind 一律不折算
2. `ratio` 按 `ratio_scale` 决定 ×100（fraction）还是原样（percent_points）
3. 缺数 / 零 / 占位文本不破坏
4. **两个内核共用同一套 helper**（结构判据，防「各写一份」漂移）
5. 不传新参数 ⇒ 逐字节等于改造前行为（既有调用方不变）
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.schemas.export_unit_policy import ExportUnitRegion
from app.services.note_word_exporter import (
    NoteWordExporter,
    _apply_region_policy,
    _fmt_ratio,
)

_SRC_DIR = Path(__file__).resolve().parents[1] / "app" / "services"
_EXPORTER_SRC = (_SRC_DIR / "note_word_exporter.py").read_text(encoding="utf-8")
_CLONE_SRC = (_SRC_DIR / "note_template_table_look.py").read_text(encoding="utf-8")


def _region(divisor: int, unit: str = "wan") -> ExportUnitRegion:
    return ExportUnitRegion(
        stable_id="test", measure_kind="amount", unit=unit, divisor=divisor
    )


# ---------------------------------------------------------------------------
# 1. 只有 amount 执行 divisor
# ---------------------------------------------------------------------------


def test_amount_is_converted_by_divisor():
    r = _region(10000)
    assert _apply_region_policy(123456789, kind="amount", region=r) == pytest.approx(12345.68)


def test_amount_divisor_one_unchanged():
    r = _region(1, unit="yuan")
    assert _apply_region_policy(1234.5, kind="amount", region=r) == 1234.5


@pytest.mark.parametrize(
    "kind", ["quantity", "count", "exchange_rate", "unit_price", "ratio", "text"]
)
def test_non_amount_kinds_never_converted(kind):
    """非金额列一律**不折算** —— 数量/次数/汇率/单价折算会让语义完全错。"""
    r = _region(10000)
    assert _apply_region_policy(123456789, kind=kind, region=r) == 123456789


def test_none_region_never_converted():
    """`region is None` ⇒ 不折算（既有调用方行为不变）。"""
    assert _apply_region_policy(123456789, kind="amount", region=None) == 123456789


def test_non_numeric_preserved():
    """占位文本原样保留，不中断整份导出。"""
    r = _region(10000)
    assert _apply_region_policy("[被审计单位]", kind="amount", region=r) == "[被审计单位]"


def test_none_and_empty_preserved():
    r = _region(10000)
    assert _apply_region_policy(None, kind="amount", region=r) is None
    assert _apply_region_policy("", kind="amount", region=r) == ""
    assert _apply_region_policy("   ", kind="amount", region=r) == "   "


def test_round_half_up_not_banker():
    """12500 / 10000 = 1.25 必须进到 1.25（两位）；10050/10000 = 1.005 → 1.01。"""
    r = _region(10000)
    assert _apply_region_policy(10050, kind="amount", region=r) == pytest.approx(1.01)


# ---------------------------------------------------------------------------
# 2. ratio 按 ratio_scale
# ---------------------------------------------------------------------------


def test_ratio_fraction_multiplies_by_100_with_percent():
    """`fraction`：库里 0.2 = 20% ⇒ 显示 `20.00%`。"""
    assert _fmt_ratio(0.2, "fraction") == "20.00%"


def test_ratio_percent_points_kept_as_is():
    """`percent_points`：库里 20 = 20% ⇒ 显示 `20.00`（不再 ×100）。"""
    assert _fmt_ratio(20, "percent_points") == "20.00"


def test_ratio_undeclared_scale_keeps_legacy_amount_format():
    """未声明刻度 ⇒ 保持改造前的金额格式（不猜，避免 100 倍错）。"""
    assert _fmt_ratio(0.2, None) == "0.20"


def test_ratio_zero_and_none_blank():
    assert _fmt_ratio(0, "fraction") == ""
    assert _fmt_ratio(None, "fraction") == ""
    assert _fmt_ratio("", "fraction") == ""


def test_ratio_fraction_and_percent_points_differ_100x():
    """两种刻度必须差 100 倍 —— 混用即错误。"""
    frac = float(_fmt_ratio(0.2, "fraction").rstrip("%"))
    pp = float(_fmt_ratio(0.2, "percent_points"))
    assert frac == pytest.approx(pp * 100)


# ---------------------------------------------------------------------------
# 3. 列语义 API
# ---------------------------------------------------------------------------


def test_default_kind_is_amount_when_not_declared():
    e = NoteWordExporter(None)  # type: ignore[arg-type]
    assert e._col_kind(0) == "amount"
    assert e._col_ratio_scale(0) is None


def test_set_column_semantics_applies():
    e = NoteWordExporter(None)  # type: ignore[arg-type]
    e.set_column_semantics(
        unit_region=_region(10000),
        column_kinds=["amount", "ratio"],
        column_ratio_scales=[None, "fraction"],
    )
    assert e._col_kind(0) == "amount"
    assert e._col_kind(1) == "ratio"
    assert e._col_ratio_scale(1) == "fraction"


def test_out_of_range_index_falls_back_to_amount():
    """越界索引必须回落 `amount`（否则表头变化会让列语义错位）。"""
    e = NoteWordExporter(None)  # type: ignore[arg-type]
    e.set_column_semantics(column_kinds=["amount"], column_ratio_scales=[None])
    assert e._col_kind(99) == "amount"
    assert e._col_ratio_scale(99) is None


# ---------------------------------------------------------------------------
# 4. 两个内核共用同一套 helper（结构判据）
# ---------------------------------------------------------------------------


def test_clone_path_imports_shared_helpers():
    """clone 路径必须 import 与 `_render_table` **同一套** helper。

    🔴 结构判据：若各写一份，改一处口径另一处不动 ⇒ 同一张表走不同路径结果不同。
    """
    tree = ast.parse(_CLONE_SRC)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.services.note_word_exporter":
            imported |= {a.name for a in node.names}
    assert "_apply_region_policy" in imported, imported
    assert "_fmt_ratio" in imported, imported


def test_exporter_has_no_duplicate_ratio_logic():
    """`_render_table` 不得自己再写一份 ×100 逻辑（必须走 `_fmt_ratio`）。"""
    # `_fmt_ratio` 定义里可以有 * 100，但 `_render_table` 函数体内不得有
    tree = ast.parse(_EXPORTER_SRC)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_render_table":
            body_src = ast.get_source_segment(_EXPORTER_SRC, node) or ""
            assert "* 100" not in body_src, "_render_table 内不应重复写 ×100"
            assert "_fmt_ratio" in body_src, "_render_table 必须走 _fmt_ratio"


def test_clone_signature_has_three_new_optional_params():
    """clone 内核签名必须真的接受三个新参数（只加实例字段不算接上）。"""
    import inspect

    from app.services.note_template_table_look import render_cloned_table

    params = inspect.signature(render_cloned_table).parameters
    for name in ("unit_region", "column_kinds", "column_ratio_scales"):
        assert name in params, f"{name} 不在签名里"
        assert params[name].default is None, f"{name} 必须是可选（默认 None）"


# ---------------------------------------------------------------------------
# 5. 不传新参数 ⇒ 行为不变
# ---------------------------------------------------------------------------


def test_clone_path_unchanged_when_no_semantics_passed():
    """不传新参数时，clone 路径的金额格式与改造前一致（`fmt_amount_gt`）。"""
    from docx import Document
    from docx.oxml.ns import qn

    from app.services.note_template_table_look import render_cloned_table

    doc = Document()
    t = doc.add_table(rows=3, cols=3)
    # 表头行
    for i, text in enumerate(["项目", "期末", "期初"]):
        t.rows[0].cells[i].text = text
    # 两条原型数据行
    for r in (1, 2):
        for i in range(3):
            t.rows[r].cells[i].text = "x"
    sample = t._tbl

    table_data = {
        "headers": ["项目", "期末", "期初"],
        "rows": [{"label": "货币资金", "values": [1234.5, 6789]}],
        "value_columns": ["期末", "期初"],
    }
    out = render_cloned_table(sample, table_data)
    assert out is not None
    # 数据行第一个金额格应是 "1,234.50"（改造前行为）
    trs = out.findall(qn("w:tr"))
    data_tr = trs[-1]
    texts = [tc.text for tc in data_tr.iter(qn("w:t"))]
    assert any("1,234.50" in (x or "") for x in texts), texts


# ---------------------------------------------------------------------------
# 6. clone 路径真的走 ratio 分支（变异 M8 存活暴露的盲区）
# ---------------------------------------------------------------------------


def _build_sample_table():
    """3 列样例表：项目 | 期末 | 期初。"""
    from docx import Document

    doc = Document()
    t = doc.add_table(rows=3, cols=3)
    for i, text in enumerate(["项目", "期末", "期初"]):
        t.rows[0].cells[i].text = text
    for r in (1, 2):
        for i in range(3):
            t.rows[r].cells[i].text = "x"
    return t._tbl


def test_clone_path_applies_ratio_scale():
    """clone 路径的 ratio 列必须走 `_fmt_ratio`（**不是**金额格式）。

    🔴 变异 M8（把 `if kind == "ratio"` 改成 `if False`）首轮存活：
    此前只测了 `_fmt_ratio` 纯函数与「不传语义时行为不变」，
    **没有一条用例让 clone 路径真的走进 ratio 分支**。
    盲区的危害：clone 路径的比例列被写成金额形态（`0.20` 而不是 `20.00%`），
    而普通 `_render_table` 路径是对的 ⇒ 同一张表走不同路径结果不一致。
    """
    from docx.oxml.ns import qn

    from app.services.note_template_table_look import render_cloned_table

    sample = _build_sample_table()
    table_data = {
        "headers": ["项目", "期末", "期初"],
        "rows": [{"label": "占比", "values": [0.2, 0.3]}],
        "value_columns": ["期末", "期初"],
    }
    out = render_cloned_table(
        sample,
        table_data,
        column_kinds=["ratio", "ratio"],
        column_ratio_scales=["fraction", "fraction"],
    )
    assert out is not None
    trs = out.findall(qn("w:tr"))
    texts = [tc.text for tc in trs[-1].iter(qn("w:t"))]
    joined = "|".join(x or "" for x in texts)
    # fraction ⇒ 0.2 显示 20.00%（不是 0.20）
    assert "20.00%" in joined, joined
    assert "0.20" not in joined.replace("20.00%", ""), joined


def test_clone_path_applies_amount_divisor():
    """clone 路径的 amount 列必须按 divisor 折算。"""
    from docx.oxml.ns import qn

    from app.services.note_template_table_look import render_cloned_table

    sample = _build_sample_table()
    table_data = {
        "headers": ["项目", "期末", "期初"],
        "rows": [{"label": "货币资金", "values": [123456789, 100000000]}],
        "value_columns": ["期末", "期初"],
    }
    out = render_cloned_table(
        sample,
        table_data,
        unit_region=_region(10000),
        column_kinds=["amount", "amount"],
    )
    assert out is not None
    trs = out.findall(qn("w:tr"))
    texts = [tc.text for tc in trs[-1].iter(qn("w:t"))]
    joined = "|".join(x or "" for x in texts)
    # 123456789 / 10000 = 12345.68
    assert "12,345.68" in joined, joined
    assert "123,456,789.00" not in joined, joined


def test_clone_path_quantity_not_converted():
    """clone 路径的 quantity 列不折算（数量不是金额）。"""
    from docx.oxml.ns import qn

    from app.services.note_template_table_look import render_cloned_table

    sample = _build_sample_table()
    table_data = {
        "headers": ["项目", "期末", "期初"],
        "rows": [{"label": "数量", "values": [123456789, 1]}],
        "value_columns": ["期末", "期初"],
    }
    out = render_cloned_table(
        sample,
        table_data,
        unit_region=_region(10000),
        column_kinds=["quantity", "quantity"],
    )
    assert out is not None
    trs = out.findall(qn("w:tr"))
    texts = [tc.text for tc in trs[-1].iter(qn("w:t"))]
    joined = "|".join(x or "" for x in texts)
    assert "123,456,789.00" in joined, joined


def test_render_table_ratio_path():
    """普通 `_render_table` 路径的 ratio 列也必须走 `_fmt_ratio`。"""
    from docx import Document
    from docx.oxml.ns import qn

    doc = Document()
    exporter = NoteWordExporter(None)  # type: ignore[arg-type]
    exporter.set_column_semantics(
        column_kinds=["ratio"], column_ratio_scales=["fraction"]
    )
    table_data = {
        "headers": ["项目", "占比"],
        "rows": [{"label": "资产负债率", "values": [0.4567]}],
        "value_columns": ["占比"],
    }
    exporter._render_table(doc, table_data)
    body = doc.element.body
    texts = [t.text for t in body.iter(qn("w:t"))]
    joined = "|".join(x or "" for x in texts)
    assert "45.67%" in joined, joined


# ---------------------------------------------------------------------------
# 7. 生产调用方接线
# ---------------------------------------------------------------------------


def test_table_semantics_binds_project_region_and_catalog_columns():
    """生产 `_table_semantics` 必须把项目单位绑定到 6A catalog 的列数组。"""
    e = NoteWordExporter(None)  # type: ignore[arg-type]
    e._base_unit_region = _region(10000)
    region, kinds, scales = e._table_semantics(
        {
            "table_id": "note-1-table-0",
            "column_kinds": ["text", "amount", "ratio"],
            "column_ratio_scales": [None, None, "fraction"],
        }
    )
    assert region is not None
    assert region.stable_id == "note-1-table-0"
    assert region.divisor == 10000
    assert kinds == ["text", "amount", "ratio"]
    assert scales == [None, None, "fraction"]


def test_template_block_fill_passes_semantics_to_both_paths():
    """模板块填充源码必须把同一套 semantics 传给 clone 与普通 fallback。"""
    source = Path(
        _SRC_DIR / "note_template_block_fill.py"
    ).read_text(encoding="utf-8")
    assert "exporter._table_semantics(t)" in source
    assert "unit_region=unit_region" in source
    assert "column_kinds=column_kinds" in source
    assert "column_ratio_scales=column_ratio_scales" in source
    # 普通 fallback 也必须有显式传参，不只是 clone 路径接线。
    assert "exporter._render_table(" in source
    assert "exporter._table_semantics(table)" in source
