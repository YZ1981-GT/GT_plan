"""附注模板模式表格克隆路径（spec deliverable-trio-generation-accuracy §2.4 / Task 13a）。

列数一致（参考表叶子列数 = 库内表列数）时不走回退路径（``_render_table`` 结构 + 样例表外观），而是深拷贝样例表、
保留表头合并、按行标签选原型行逐行克隆写值 —— 列宽 / 边框 / 字体 / 表头合并完全保留模板版式。列数不一致时回退。

含故障注入变异（design §5 验收）：关克隆分流 / 关表头合并保留 / 原型行恒取首行，各自打红对应单测。
"""
from __future__ import annotations

import copy

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from app.services import note_template_table_look as tl

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


# ── 夹具：构造模板样例表 ───────────────────────────────────────────────────────


def _mark_header(tr) -> None:
    trpr = tr.get_or_add_trPr()
    trpr.append(OxmlElement("w:tblHeader"))


def _set_grid(tbl, widths: list[int]) -> None:
    """重写样例表网格列宽（模拟模板里精心设计的列宽）。"""
    grid = tbl.find(qn("w:tblGrid"))
    cols = grid.findall(qn("w:gridCol"))
    for g, w in zip(cols, widths):
        g.set(qn("w:w"), str(w))


def _flat_sample(doc, headers: list[str], *, widths: list[int] | None = None, data_rows: int = 3):
    """扁平样例表：1 行表头（标 tblHeader）+ ``data_rows`` 行原型数据行。原型数据行写上「样例文字」。"""
    t = doc.add_table(rows=1 + data_rows, cols=len(headers))
    for i, h in enumerate(headers):
        t.cell(0, i).text = h
    _mark_header(t.rows[0]._tr)
    # 原型数据行：首列不同标签、其余列放样例金额（克隆时应被库内值替换）
    protos = ["货币资金", "合计", "其他"][:data_rows] + [""] * max(0, data_rows - 3)
    for r in range(data_rows):
        t.cell(r + 1, 0).text = protos[r]
        for c in range(1, len(headers)):
            t.cell(r + 1, c).text = "0.00"
    if widths:
        _set_grid(t._tbl, widths)
    return t._tbl


def _merged_header_sample(doc):
    """两行表头、父表头跨两列合并（design §2.4「保留表头合并」）：

    行0: | 项目 (rowspan2) | 期末余额 (colspan2) |
    行1: |                 | 账面价值 | 公允价值 |
    行2+: 三原型数据行
    3 叶子列。
    """
    t = doc.add_table(rows=5, cols=3)
    # 行0
    r0 = t.rows[0]
    r0.cells[0].text = "项目"
    r0.cells[1].text = "期末余额"
    r0.cells[1].merge(r0.cells[2])  # colspan 2
    # 行1
    r1 = t.rows[1]
    r1.cells[0].merge(r0.cells[0])  # rowspan 2（纵向合并到行0）
    r1.cells[1].text = "账面价值"
    r1.cells[2].text = "公允价值"
    _mark_header(r0._tr)
    _mark_header(r1._tr)
    for r in range(2, 5):
        t.cell(r, 0).text = ["存货", "合计", "x"][r - 2]
        t.cell(r, 1).text = "0"
        t.cell(r, 2).text = "0"
    return t._tbl


def _lib(headers, rows, *, column_groups=None):
    d = {"headers": list(headers), "rows": rows}
    if column_groups is not None:
        d["_column_groups"] = column_groups
    return d


def _cells(tr):
    return [(c, s, tc) for c, s, tc in tl._row_cells(tr)]


def _tr(tbl):
    return tbl.findall(qn("w:tr"))


def _text(el):
    return "".join(t.text or "" for t in el.iter(qn("w:t"))).strip()


def _grid_cols(tbl):
    return [int(g.get(qn("w:w"))) for g in tbl.findall(f"{W}tblGrid/{W}gridCol")]


# ── 列数分流 ───────────────────────────────────────────────────────────────────


def test_leaf_column_count_matches_triggers_clone():
    doc = Document()
    sample = _flat_sample(doc, ["项目", "期末余额", "期初余额"])
    lib = _lib(["项目", "期末余额", "期初余额"],
               [{"label": "银行存款", "values": [1234567.5, 2000.0]},
                {"label": "合计", "values": [1234567.5, 2000.0]}])
    assert tl.sample_leaf_columns(sample) == 3
    assert tl.lib_leaf_columns(lib) == 3
    out = tl.render_cloned_table(sample, lib, header_rows=1)
    assert out is not None
    rows = _tr(out)
    # 1 表头 + 2 数据行（原型 3 行里多余的被删）
    assert len(rows) == 3
    assert _text(_cells(rows[0])[0][2]) == "项目"
    assert _text(_cells(rows[1])[0][2]) == "银行存款"
    assert _text(_cells(rows[2])[0][2]) == "合计"
    # 金额右对齐千分位
    assert _text(_cells(rows[1])[1][2]) == "1,234,567.50"
    assert _cells(rows[1])[1][2].find(f"{W}p/{W}pPr/{W}jc").get(f"{W}val") == "right"


def test_column_count_mismatch_returns_none():
    doc = Document()
    sample = _flat_sample(doc, ["项目", "期末余额", "期初余额"])  # 3 列
    lib = _lib(["项目", "期末余额"], [{"label": "银行存款", "values": [100.0]}])  # 2 列
    assert tl.lib_leaf_columns(lib) == 2
    assert tl.render_cloned_table(sample, lib, header_rows=1) is None


def test_no_sample_or_no_rows_returns_none():
    doc = Document()
    sample = _flat_sample(doc, ["项目", "期末"])
    assert tl.render_cloned_table(None, _lib(["项目", "期末"], [{"label": "x", "values": [1.0]}])) is None
    assert tl.render_cloned_table(sample, _lib(["项目", "期末"], []), header_rows=1) is None


# ── 表头合并保留 ───────────────────────────────────────────────────────────────


def test_merged_header_cells_are_preserved():
    doc = Document()
    sample = _merged_header_sample(doc)
    assert tl.sample_leaf_columns(sample) == 3
    lib = _lib(["项目", "账面价值", "公允价值"],
               [{"label": "存货", "values": [500.0, 600.0]}],
               column_groups=[{"group": "期末余额", "start": 1, "span": 2}])
    assert tl.lib_leaf_columns(lib) == 3
    out = tl.render_cloned_table(sample, lib, header_rows=2)
    assert out is not None
    rows = _tr(out)
    # 2 表头行保留
    assert len(rows) == 1 + 2  # 2 header + 1 data
    # 行0「期末余额」仍是跨 2 列（gridSpan=2）
    r0_cells = _cells(rows[0])
    span_cell = next(tc for c, s, tc in r0_cells if _text(tc) == "期末余额")
    gs = span_cell.find(f"{W}tcPr/{W}gridSpan")
    assert gs is not None and gs.get(f"{W}val") == "2"
    # 行0「项目」是纵向合并（vMerge restart）
    proj = next(tc for c, s, tc in r0_cells if _text(tc) == "项目")
    assert proj.find(f"{W}tcPr/{W}vMerge") is not None
    # 数据行写进了库内值
    data = _cells(rows[2])
    assert _text(data[0][2]) == "存货"
    assert _text(data[1][2]) == "500.00" and _text(data[2][2]) == "600.00"


# ── 原型行三级选择 ─────────────────────────────────────────────────────────────


def test_prototype_same_name_row_is_reused():
    """原型按同名行选：库内「合计」行应克隆样例表的「合计」原型行（而非首行）。"""
    doc = Document()
    sample = _flat_sample(doc, ["项目", "金额"])
    # 给「合计」原型行加粗标识，确认克隆的是它
    t = sample.findall(qn("w:tr"))
    total_proto = next(tr for tr in t if _text(tl._row_cells(tr)[0][2]) == "合计")
    rpr = total_proto.find(f"{W}tc/{W}p/{W}r").get_or_add_rPr() if total_proto.find(f"{W}tc/{W}p/{W}r") is not None else None
    # 用 shd 底纹作为可识别标记打在「合计」原型行首格
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), "CCCCCC")
    tl._row_cells(total_proto)[0][2].get_or_add_tcPr().append(shd)
    lib = _lib(["项目", "金额"], [{"label": "合计", "values": [999.0]}])
    out = tl.render_cloned_table(sample, lib, header_rows=1)
    data = _tr(out)[1]
    assert _text(tl._row_cells(data)[0][2]) == "合计"
    assert tl._row_cells(data)[0][2].find(f"{W}tcPr/{W}shd") is not None  # 克隆了「合计」原型行


def test_prototype_falls_back_to_total_then_first():
    """库内行名在样例表里找不到：先取合计 / 小计 / 总计原型行，否则首行。"""
    doc = Document()
    # 原型行首列：空、合计、x（无「银行存款」）
    sample = _flat_sample(doc, ["项目", "金额"], data_rows=3)
    # 标记「合计」原型
    total_proto = next(tr for tr in sample.findall(qn("w:tr")) if _text(tl._row_cells(tr)[0][2]) == "合计")
    shd = OxmlElement("w:shd"); shd.set(qn("w:fill"), "AAAAAA")
    tl._row_cells(total_proto)[0][2].get_or_add_tcPr().append(shd)
    lib = _lib(["项目", "金额"], [{"label": "银行存款", "values": [1.0]}])
    out = tl.render_cloned_table(sample, lib, header_rows=1)
    data = _tr(out)[1]
    assert _text(tl._row_cells(data)[0][2]) == "银行存款"
    assert tl._row_cells(data)[0][2].find(f"{W}tcPr/{W}shd") is not None  # 回退取了「合计」原型


# ── 金额格式与列宽继承 ─────────────────────────────────────────────────────────


def test_zero_and_empty_are_blank_and_text_passthrough():
    doc = Document()
    sample = _flat_sample(doc, ["项目", "期末", "期初"])
    lib = _lib(["项目", "期末", "期初"],
               [{"label": "应收账款", "values": [0, None]},
                {"label": "坏账", "values": ["不适用", 12.5]}])
    out = tl.render_cloned_table(sample, lib, header_rows=1)
    r1, r2 = _tr(out)[1], _tr(out)[2]
    assert _text(tl._row_cells(r1)[1][2]) == "" and _text(tl._row_cells(r1)[2][2]) == ""  # 0 与空留白
    assert _text(tl._row_cells(r2)[1][2]) == "不适用"  # 非数值文本原样
    assert _text(tl._row_cells(r2)[2][2]) == "12.50"


def test_template_grid_widths_are_preserved():
    """克隆路径保留模板精心设计的列宽（回退路径会按最长数值重算）。"""
    doc = Document()
    sample = _flat_sample(doc, ["项目", "期末", "期初"], widths=[3600, 2400, 2400])
    lib = _lib(["项目", "期末", "期初"], [{"label": "货币资金", "values": [1.0, 2.0]}])
    out = tl.render_cloned_table(sample, lib, header_rows=1)
    assert _grid_cols(out) == [3600, 2400, 2400]


# ── 端到端：rebuild_block 按列数一致 / 不一致分流 ─────────────────────────────


def _exporter():
    from app.services.note_word_exporter import NoteWordExporter

    return NoteWordExporter(db=None)


def _one_block_doc(sample_headers: list[str]):
    """一个 ##SECTION## 块：标题 + 表位 + 一张样例表（列数由 ``sample_headers`` 决定）。"""
    doc = Document()
    doc.add_paragraph("##SECTION:八、1##")
    doc.add_paragraph("货币资金", style="Heading 3")
    doc.add_paragraph("{{table:八、1:0}}")
    t = doc.add_table(rows=1 + 2, cols=len(sample_headers))
    for i, h in enumerate(sample_headers):
        t.cell(0, i).text = h
    _mark_header(t.rows[0]._tr)
    for r in range(2):
        t.cell(r + 1, 0).text = ["银行存款", "合计"][r]
        for c in range(1, len(sample_headers)):
            t.cell(r + 1, c).text = "0.00"
    _set_grid(t._tbl, [3600] + [2400] * (len(sample_headers) - 1))
    doc.add_paragraph("##/SECTION:八、1##")
    return doc


def _note(code, title, tables):
    from types import SimpleNamespace

    return SimpleNamespace(note_section=code, section_title=title, text_content="",
                           table_data={"_tables": tables}, source_template=None,
                           is_deleted=False, status=None, is_empty=False)


def _rebuild(doc, code, note):
    from app.services import note_template_block_fill as tbf
    from app.services.word_doc_utils import scan_section_blocks

    tbf.absorb_trailing_content(doc)
    blocks = {b.section_code: b for b in scan_section_blocks(doc)}
    return tbf.rebuild_block(doc, blocks[code], note, exporter=_exporter())


def test_rebuild_uses_clone_path_when_columns_match():
    doc = _one_block_doc(["项目", "期末余额", "期初余额"])  # 3 列样例表
    note = _note("八、1", "货币资金",
                 [{"name": "货币资金", "headers": ["项目", "期末余额", "期初余额"],
                   "rows": [{"label": "银行存款", "values": [1234567.5, 100.0]},
                            {"label": "合计", "values": [1234567.5, 100.0]}]}])
    rebuilt = _rebuild(doc, "八、1", note)
    assert rebuilt.stats.tables_cloned == 1 and rebuilt.stats.tables_rendered == 1
    from app.services.word_doc_utils import scan_section_blocks

    b = next(x for x in scan_section_blocks(doc) if x.section_code == "八、1")
    tbl = next(el for el in b.elements if el.tag == f"{W}tbl")
    # 模板列宽保留（克隆路径），值已写入
    assert _grid_cols(tbl) == [3600, 2400, 2400]
    assert _text(_tr(tbl)[1]) .startswith("银行存款")
    assert "1,234,567.50" in _text(_tr(tbl)[1])


def test_rebuild_falls_back_when_columns_mismatch():
    doc = _one_block_doc(["项目", "期末余额", "期初余额"])  # 3 列样例表
    note = _note("八、1", "货币资金",
                 [{"name": "货币资金", "headers": ["项目", "期末余额"],  # 2 列：不一致
                   "rows": [{"label": "银行存款", "values": [100.0]},
                            {"label": "合计", "values": [100.0]}]}])
    rebuilt = _rebuild(doc, "八、1", note)
    assert rebuilt.stats.tables_cloned == 0 and rebuilt.stats.tables_rendered == 1
