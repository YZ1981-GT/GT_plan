"""底稿表头填充守卫（``wp_header_service``，生成底稿时写编制单位 / 期间 / 截止日）。

2026-10-26 修「按编码生成时，遇到有合并单元格的模板，表头会静默填不上」：
- 根因：openpyxl 里合并区域除左上角外都是只读的 ``MergedCell``；原先直接写「标签右边一格」、没找到标签就在活动页
  固定格写标准布局，一碰合并格 ``AttributeError``，调用方只记 warning、回执照报成功（按生成链路实测 J2A / K11-4 /
  B10-2 / L1-1 / J2-5 / J2-6 / A10 / A12 / B13-2 全是这样）；
- 同时修掉：不带冒号的表格列头（程序表「索引号」）右边被写底稿编码；标准布局兜底盖掉模板第 1~5 行的内容；
  表头页（底稿目录 / 表头（请先填写） / 目录）的右边是目录表格，只能写在标签冒号后。
"""
from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import openpyxl
import pytest
from openpyxl.cell.cell import MergedCell

from app.services import wp_header_service as hdr
from app.services import wp_template_init_service as init

CLIENT = "某某测试有限公司"
PERIOD = "2025年01月01日至2025年12月31日"
CUTOFF = "2025年12月31日"
VALUES = {"client": CLIENT, "period": PERIOD, "cutoff": CUTOFF, "wp_name": "名称X", "code": "J2A",
          "xref": "", "preparer": "", "reviewer": ""}
HUB_A1 = "底稿开列时，可先在以下单元格填写有关内容，以便其他底稿引用"


def _book(cells: dict[str, Any], merges: tuple[str, ...] = (), title: str = "审定表"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    for coord, value in cells.items():
        ws[coord] = value
    for rng in merges:
        ws.merge_cells(rng)
    return wb


def _add_sheet(wb, title: str, cells: dict[str, Any]):
    ws = wb.create_sheet(title)
    for coord, value in cells.items():
        ws[coord] = value
    return ws


def _written(filled: list[dict[str, str]]) -> set[tuple[str, str, str]]:
    return {(f["sheet"], f["cell"], f["field"]) for f in filled}


# ── 合并格 ──────────────────────────────────────────────────────────────────────


def test_merged_label_value_goes_to_first_column_after_label_range():
    """「被审计单位：」占 A3:B3 ⇒ 右边一格 B3 是只读合并格（原先 AttributeError），值写 C3。"""
    wb = _book({"A3": "被审计单位：", "A4": "会计期间："}, merges=("A3:B3", "A4:B4"))
    filled = hdr._fill_workbook_header(wb, VALUES)
    ws = wb.active
    assert ws["C3"].value == CLIENT and ws["C4"].value == PERIOD
    assert _written(filled) == {("审定表", "C3", "client"), ("审定表", "C4", "period")}


def test_merged_value_region_is_written_at_its_anchor():
    """值区 B3:E3 合并 ⇒ 写左上角 B3（显示在整块里）。"""
    wb = _book({"A3": "编制单位：", "A4": "截止日："}, merges=("B3:E3", "B4:E4"))
    hdr._fill_workbook_header(wb, VALUES)
    assert wb.active["B3"].value == CLIENT and wb.active["B4"].value == CUTOFF


def test_vertical_value_region_shared_by_two_labels_is_not_overwritten():
    """值区 B3:B4 竖向合并、两行各一个标签：B4 是只读合并格（原先 AttributeError）⇒ 第一个标签写左上角 B3，
    第二个落到同一格时改写进自己冒号后，不覆盖前一个。"""
    wb = _book({"A3": "被审计单位：", "A4": "截止日："}, merges=("B3:B4",))
    filled = hdr._fill_workbook_header(wb, VALUES)
    ws = wb.active
    assert ws["B3"].value == CLIENT and ws["A4"].value == f"截止日：{CUTOFF}"
    assert _written(filled) == {("审定表", "B3", "client"), ("审定表", "A4", "cutoff")}


def test_value_region_merged_with_label_neighbour_label_range_ending_inside():
    """标签 A3:C3 合并、值区 D3:F3 合并 ⇒ 写 D3；不碰 B3 / C3 / E3（都是只读合并格）。"""
    wb = _book({"A3": "被审计单位名称："}, merges=("A3:C3", "D3:F3"))
    hdr._fill_workbook_header(wb, VALUES)
    ws = wb.active
    assert ws["D3"].value == CLIENT
    assert isinstance(ws["B3"], MergedCell) and isinstance(ws["E3"], MergedCell)


# ── 标签认法 ───────────────────────────────────────────────────────────────────


def test_column_headers_without_colon_are_not_labels():
    """程序表表头行「索引号」「复核人」「工作底稿索引」不带冒号 ⇒ 不写（原先把底稿编码写进「索引号」列头右边）。"""
    wb = _book({"G5": "索引号", "H5": None, "I5": "复核人", "A6": "工作底稿索引", "A3": "被审计单位："})
    filled = hdr._fill_workbook_header(wb, VALUES)
    ws = wb.active
    assert ws["H5"].value is None and ws["J5"].value is None and ws["B6"].value is None
    assert _written(filled) == {("审定表", "B3", "client")}


def test_label_name_must_match_exactly():
    """按全名认标签：以关键词结尾（「上年审计期间：」「工作底稿索引号：」，原先按结尾匹配会写）或开头的都不算。"""
    wb = _book({"A3": "被函证单位名称：", "A4": "上年审计期间：", "A5": "工作底稿索引号：", "A6": "编制人员数：",
                "A7": "截止日期："})
    filled = hdr._fill_workbook_header(wb, VALUES)
    ws = wb.active
    assert [ws[f"B{r}"].value for r in range(3, 7)] == [None, None, None, None]
    assert _written(filled) == {("审定表", "B7", "cutoff")}


def test_inline_examples_replaced_only_for_client_period_cutoff():
    """冒号后是模板示例：客户名称 / 期间 / 截止日换成本项目的值；索引号（模板自己的）与编制人（生成时没有值）不动。"""
    wb = _book({"A2": "被审计单位：ABC公司", "A3": "会计期间：201X年度", "A4": "截止日：202X年12月31日",
                "A5": "索引号：A10", "A6": "编制人：张三", "A7": "客户名称：  "})
    hdr._fill_workbook_header(wb, VALUES)
    ws = wb.active
    assert ws["A2"].value == f"被审计单位：{CLIENT}"
    assert ws["A3"].value == f"会计期间：{PERIOD}"
    assert ws["A4"].value == f"截止日：{CUTOFF}"
    assert ws["A5"].value == "索引号：A10" and ws["A6"].value == "编制人：张三"
    assert ws["B7"].value == CLIENT, "冒号后只有空白 ⇒ 当作空标签，写右边"


def test_formula_or_template_value_on_the_right_is_kept():
    """右边是公式（引用表头页）或模板自带的值（索引号 A10） ⇒ 不动。"""
    wb = _book({"A3": "编制单位：", "B3": "=底稿目录!A2", "A4": "索引号：", "B4": "A10"})
    _add_sheet(wb, "底稿目录", {"A1": HUB_A1, "A2": "被审计单位："})
    hdr._fill_workbook_header(wb, {**VALUES, "code": "E1-1"})
    ws = wb["审定表"]
    assert ws["B3"].value == "=底稿目录!A2" and ws["B4"].value == "A10"


def test_label_followed_by_another_label_is_filled_after_its_colon():
    """「客户名称：」右边紧挨「编制人：」 ⇒ 写进标签格冒号后，右边的标签不动。"""
    wb = _book({"A2": "客户名称：", "B2": "编制人：", "A3": "会计时点：", "A4": "截止日/会计期间："})
    hdr._fill_workbook_header(wb, VALUES)
    ws = wb.active
    assert ws["A2"].value == f"客户名称：{CLIENT}" and ws["B2"].value == "编制人："
    assert ws["B4"].value == PERIOD, "「截止日/会计期间」整名登记为期间"
    assert ws["B3"].value is None, "「会计时点」未登记，不猜"


# ── 表头页与跨页引用 ─────────────────────────────────────────────────────────────


def _hub_book(hub_title: str, hub_a1: str | None):
    """活动页「审定表」的表头格全是引用表头页的公式；表头页右边是目录表格（序号 / 内容）。"""
    wb = _book({"A1": "致同会计师事务所", "A3": f"='{hub_title}'!A2", "C3": f"='{hub_title}'!A4",
                "A4": f"='{hub_title}'!A3", "G3": "索引号：", "H3": "E1-1"})
    _add_sheet(wb, hub_title, {"A1": hub_a1, "A2": "被审计单位：", "A3": "截止日：202X年12月31日", "A4": "编制人：",
                               "D2": "序号", "E2": "内  容", "D3": 1, "E3": "审定表E1-1"})
    return wb


@pytest.mark.parametrize(("hub_title", "hub_a1"), [("底稿目录", None), ("表头（请先填写）", HUB_A1), ("目录", HUB_A1)])
def test_hub_sheet_is_filled_after_colon_and_directory_table_untouched(hub_title, hub_a1):
    wb = _hub_book(hub_title, hub_a1)
    filled = hdr._fill_workbook_header(wb, {**VALUES, "code": "E1-1"})
    hub, ws = wb[hub_title], wb["审定表"]
    assert hub["A2"].value == f"被审计单位：{CLIENT}" and hub["A3"].value == f"截止日：{CUTOFF}"
    assert hub["A4"].value == "编制人："
    assert (hub["B2"].value, hub["D2"].value, hub["E2"].value, hub["E3"].value) == (None, "序号", "内  容", "审定表E1-1")
    assert ws["A3"].value == f"='{hub_title}'!A2", "活动页的引用公式不动（显示的就是表头页填好的值）"
    assert ws["H3"].value == "E1-1"
    assert _written(filled) == {(hub_title, "A2", "client"), (hub_title, "A3", "cutoff")}


def test_hub_recognised_by_a1_note_even_when_it_is_the_active_sheet():
    """活动页就是表头页（K11-4 / E1 / D2 生成后活动页是「底稿目录」）⇒ 同样只写冒号后。"""
    wb = _hub_book("表头", HUB_A1)
    wb.active = wb.sheetnames.index("表头")
    hdr._fill_workbook_header(wb, {**VALUES, "code": "E1-1"})
    hub = wb["表头"]
    assert hub["A2"].value == f"被审计单位：{CLIENT}" and hub["B2"].value is None and hub["D2"].value == "序号"


def test_two_hop_reference_reaches_the_label_cell():
    """活动页 → 纵向分析 → 横向分析的标签格（A1-13 / B13-2 这类多页分析底稿）：写最终那一格的冒号后，中间的公式不动。"""
    wb = _book({"A2": "='纵向分析'!A2", "B2": "='纵向分析'!E2"}, title="审定表")
    _add_sheet(wb, "纵向分析", {"A2": "='横向分析'!A2", "E2": "='横向分析'!D2"})
    _add_sheet(wb, "横向分析", {"A2": "客户名称：", "D2": "编制人：", "A3": "会计时点："})
    filled = hdr._fill_workbook_header(wb, VALUES)
    assert wb["横向分析"]["A2"].value == f"客户名称：{CLIENT}"
    assert wb["横向分析"]["B2"].value is None, "被引用的格只写冒号后，不写右边"
    assert wb["纵向分析"]["A2"].value == "='横向分析'!A2"
    assert _written(filled) == {("横向分析", "A2", "client")}


def test_reference_to_missing_sheet_or_compound_formula_is_ignored():
    wb = _book({"A2": "='不存在'!A2", "A3": "=底稿目录!A2&\"\"", "A4": "被审计单位："})
    filled = hdr._fill_workbook_header(wb, VALUES)
    assert _written(filled) == {("审定表", "B4", "client")}


# ── fill_workpaper_header：保存与回报 ──────────────────────────────────────────────


class _Result:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class _FakeDB:
    """只回答「按 id 取项目」这一条查询（fill_workpaper_header 唯一的数据库访问）。"""

    def __init__(self, project):
        self.project = project

    async def execute(self, *_args, **_kwargs):
        return _Result(self.project)


def _db(**overrides) -> _FakeDB:
    project = dict(id=uuid.uuid4(), name="【测试】表头填充", client_name=CLIENT, audit_year=2025,
                   audit_period_start=None, audit_period_end=None, wizard_state=None)
    project.update(overrides)
    return _FakeDB(SimpleNamespace(**project))


async def _fill(path: Path, *, code: str = "J2A", db: _FakeDB | None = None, **kwargs) -> dict:
    return await hdr.fill_workpaper_header(
        db=db or _db(), project_id=uuid.uuid4(), wp_id=uuid.uuid4(), file_path=str(path),
        wp_code=code, wp_name="名称X", cycle=code[0], **kwargs,
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def test_merged_template_header_is_saved(tmp_path):
    path = tmp_path / "t.xlsx"
    _book({"A3": "被审计单位：", "A4": "会计期间："}, merges=("A3:B3", "A4:B4")).save(path)
    res = await _fill(path)
    assert res["status"] == "ok" and res["standard_layout"] is False
    wb = openpyxl.load_workbook(path)
    assert (wb.active["C3"].value, wb.active["C4"].value) == (CLIENT, PERIOD)


async def test_template_without_header_labels_is_left_byte_identical(tmp_path):
    """模板里没有可填的表头（说明页 / 指引页）⇒ 成功、什么都不写、也不重存（openpyxl 重存会丢数据验证扩展等）。
    原先这里写标准布局，盖掉模板第 1~5 行（A2-1「说明」页、A3-5「目录」页）。"""
    path = tmp_path / "t.xlsx"
    _book({"A1": "说明", "A2": "本表用于汇总各单体报表", "B3": "序号", "C3": "内容"}, title="说明").save(path)
    before = _sha(path)
    res = await _fill(path, code="A2-1")
    assert res == {"status": "ok", "message": None, "filled": [], "standard_layout": False, "filled_by_search": False}
    assert _sha(path) == before


async def test_blank_workbook_gets_standard_layout(tmp_path):
    """找不到模板时建的空白册（from_template=False）⇒ 按标准布局写表头。"""
    path = tmp_path / "t.xlsx"
    openpyxl.Workbook().save(path)
    res = await _fill(path, code="ZZ9", from_template=False)
    assert res["status"] == "ok" and res["standard_layout"] is True
    ws = openpyxl.load_workbook(path).active
    assert ws["A1"].value == "致同会计师事务所（特殊普通合伙）" and ws["B2"].value == CLIENT and ws["F3"].value == "ZZ9"


async def test_custom_workpaper_always_gets_standard_layout(tmp_path):
    path = tmp_path / "t.xlsx"
    _book({"A3": "被审计单位："}).save(path)
    res = await _fill(path, code="ZZ1", is_custom=True)
    assert res["standard_layout"] is True
    assert openpyxl.load_workbook(path).active["B2"].value == CLIENT


async def test_external_link_header_is_reported_not_silent(tmp_path):
    """表头格全是外部链接（=[4]底稿目录!$A$2：D2-5 / D4-12 这类从别的文件拆出来的模板）⇒ partial + 原因，文件不动。"""
    path = tmp_path / "t.xlsx"
    _book({"A3": "=[4]底稿目录!$A$2", "C3": "=[4]底稿目录!$A$4", "A4": "=[4]底稿目录!$A$3",
           "G3": "索引号：", "H3": "D2-5"}).save(path)
    before = _sha(path)
    res = await _fill(path, code="D2-5")
    assert res["status"] == "partial" and "外部链接" in res["message"] and res["filled"] == []
    assert _sha(path) == before


async def test_external_link_not_reported_when_client_is_shown_elsewhere_on_active_sheet(tmp_path):
    path = tmp_path / "t.xlsx"
    _book({"A3": "被审计单位：", "C3": "=[4]底稿目录!$A$4"}).save(path)
    res = await _fill(path)
    assert res["status"] == "ok" and res["message"] is None
    assert openpyxl.load_workbook(path).active["B3"].value == CLIENT


@pytest.mark.parametrize(("make", "message"), [
    (lambda p: p, "底稿文件不存在"),
    (lambda p: (p.write_bytes(b"not a workbook"), p)[1], "打开底稿文件失败"),
])
async def test_errors_are_reported_without_paths_or_exception_text(tmp_path, make, message):
    """原因会进生成回执给用户看：只写原因，不带服务器路径与异常原文（那些记日志）。"""
    path = make(tmp_path / "t.xlsx")
    res = await _fill(path)
    assert res == {"status": "error", "message": message}
    assert str(tmp_path) not in res["message"]


async def test_period_and_cutoff_come_from_project_dates(tmp_path):
    from datetime import date

    path = tmp_path / "t.xlsx"
    _book({"A3": "会计期间：", "A4": "截止日："}).save(path)
    await _fill(path, db=_db(audit_period_start=date(2025, 4, 1), audit_period_end=date(2026, 3, 31)))
    ws = openpyxl.load_workbook(path).active
    assert ws["B3"].value == "2025年04月01日至2026年03月31日" and ws["B4"].value == "2026年03月31日"


# ── 真实模板（按生成链路建底稿，存储目录指到临时目录） ─────────────────────────────────────

#: 原先在合并格上抛 AttributeError、表头一格没填的编码（按生成链路逐个实测）+ 表头页 / A1 说明表头页 / 多文件合并的典型
_MERGED_CRASH_CODES = ("J2A", "K11-4", "B10-2", "L1-1", "J2-5", "J2-6", "A10", "A12", "B13-2")
_OTHER_LAYOUT_CODES = ("C21", "A5-3", "S34-16", "E1")


def _snapshot(wb) -> dict[tuple[str, str], Any]:
    return {(s.title, c.coordinate): c.value for s in wb.worksheets
            for row in s.iter_rows(min_row=1, max_row=hdr._HEADER_ROWS, max_col=hdr._HEADER_COLS) for c in row
            if not isinstance(c, MergedCell) and c.value not in (None, "")}


def _shown(wb, value: Any, depth: int = 0) -> Any:
    hop = hdr._follow_reference(wb, value) if depth < 4 else None
    if hop is None:
        return value
    cell = hop[0][hop[1]]
    return _shown(wb, None if isinstance(cell, MergedCell) else cell.value, depth + 1)


def _generate(tmp_path: Path, monkeypatch, code: str) -> Path:
    monkeypatch.setattr(init, "STORAGE_DIR", tmp_path / "storage")
    pid = uuid.uuid4()
    (tmp_path / "storage" / str(pid)).mkdir(parents=True)
    path = init.init_workpaper_from_template(pid, uuid.uuid4(), code)
    if path is None:
        pytest.fail(f"{code} 找不到模板（模板目录变了？）")
    assert path.suffix == ".xlsx", f"{code} 生成的不是 xlsx：{path.name}"
    return path


@pytest.mark.parametrize("code", _MERGED_CRASH_CODES + _OTHER_LAYOUT_CODES)
async def test_real_template_header_filled_without_touching_other_content(tmp_path, monkeypatch, code):
    path = _generate(tmp_path, monkeypatch, code)
    wb = openpyxl.load_workbook(path)
    before, sheets = _snapshot(wb), wb.sheetnames
    wb.close()

    res = await _fill(path, code=code)
    assert res["status"] == "ok", res
    assert res["filled"], f"{code} 一格都没填"

    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames == sheets
    after = _snapshot(wb)
    for key, old in before.items():
        new = after.get(key)
        if new == old:
            continue
        prefix = re.match(r"^(.*?[：:])", str(old))
        assert prefix and isinstance(new, str) and new.startswith(prefix.group(1)), (
            f"{code} {key} 原有内容被改：{old!r} → {new!r}（只许在标签冒号后改写）")
    ws = wb.active
    shown = [_shown(wb, c.value) for row in ws.iter_rows(min_row=1, max_row=hdr._HEADER_ROWS, max_col=hdr._HEADER_COLS)
             for c in row if not isinstance(c, MergedCell)]
    assert any(isinstance(v, str) and CLIENT in v for v in shown), f"{code} 活动页「{ws.title}」表头看不到编制单位"


@pytest.mark.parametrize("code", ["D2-5", "D4-12"])
async def test_real_external_link_template_is_reported(tmp_path, monkeypatch, code):
    path = _generate(tmp_path, monkeypatch, code)
    res = await _fill(path, code=code)
    assert res["status"] == "partial" and "外部链接" in res["message"]
