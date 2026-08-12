"""录入清单 sheet 真实执行守卫 —— Wave 3 Task 9
spec: workpaper-import-export-lifecycle-closure（R2.1~R2.8）

## 🔴 为什么必须「真实执行」而不是源码断言

memory 假绿三源之首：**additive 注入即死代码**。只断言「代码里出现了
`checklist_responses`」或「`write_entry_sheet` 被 import 了」，对以下情形全部无效：

- 函数写好了但调用点传的是 `None`（本模块的 `entry_payloads` 默认就是 `None`）
- sheet 建了但内容为空
- 内容写了但覆盖了模板既有单元格

故本文件的判据一律是：**造载荷 → 真跑导出 → 打开产物逐格核对**。

## 判据清单

| AC | 判据 |
|---|---|
| R2.1 | 只有 checklist 无 html_data 的底稿，产物含其内容 |
| R2.2 | 三形态各自的渲染结构（列名取载荷键集 / 键值两列 / 三列表） |
| R2.3 | 导出前后模板既有 sheet **逐格相等** + 反向自检 |
| R2.5 | sheet 名冲突时递增且唯一 |
| R2.6 | 无非空录入 ⇒ **不产生** 清单 sheet |
| R2.7 | 截断时 sheet 内标注被截断条数 |
| R2.8 | 标注数据来源与导出时点 |
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import openpyxl
import pytest

from app.services.wp_export.entry_payload_reader import (
    EntryPayload,
    EntryPayloadResult,
)
from app.services.wp_export.entry_sheet_writer import (
    ENTRY_SHEET_BASE_NAME,
    resolve_entry_sheet_name,
    write_entry_sheet,
)
from app.services.wp_xlsx_export_service import _sync_export_workpaper_xlsx

# ─── 模板 fixture ────────────────────────────────────────────────────────────

_TEMPLATE_CELLS = {
    "A1": "致同会计师事务所（特殊普通合伙）",
    "A2": "单位：元",
    "A3": "项目",
    "B3": "期末余额",
    "A4": "应收账款",
    "B4": 1234.56,
}


@pytest.fixture()
def template_path():
    with tempfile.TemporaryDirectory() as td:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "审定表T1"
        for ref, val in _TEMPLATE_CELLS.items():
            ws[ref] = val
        p = Path(td) / "tpl.xlsx"
        wb.save(p)
        yield p


def _schema(tpl: Path) -> dict:
    return {
        "wp_code": "T1",
        "template_path": str(tpl),
        "sheets": {"审定表T1": {}},
    }


_META = {"entity_name": "测试公司", "period_end": "2025-12-31"}


def _payload(item_id, shape, *, rows=None, obj=None, text=None,
             src="remark", raw_len=10, truncated=False) -> EntryPayload:
    return EntryPayload(item_id, shape, rows, obj, text, src, raw_len, truncated)


def _result(payloads, **kw) -> EntryPayloadResult:
    return EntryPayloadResult(
        payloads=payloads,
        skipped_blank=kw.get("skipped_blank", 0),
        dropped_by_cap=kw.get("dropped_by_cap", 0),
        total_chars=kw.get("total_chars", 100),
        parse_failures=kw.get("parse_failures", 0),
    )


def _export(tpl: Path, entry: EntryPayloadResult | None, html=None):
    buf = _sync_export_workpaper_xlsx(
        _schema(tpl), html or {}, _META, False, entry,
    )
    return openpyxl.load_workbook(buf)


def _sheet_texts(ws) -> list[str]:
    out: list[str] = []
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value, str) and c.value.strip():
                out.append(c.value)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# R2.1 —— 数据源真的接通了（真实执行）
# ═══════════════════════════════════════════════════════════════════════════


class TestDataSourceActuallyConnected:
    def test_checklist_only_workpaper_产物含其内容(self, template_path):
        """🔴 核心判据：只有 checklist、无 html_data 的底稿，内容必须进产物。

        真实库这类底稿有 126 份（131 有录入 − 5 与 html_data 交集）。
        """
        entry = _result([
            _payload("D2-detail-rows", "json_array",
                     rows=[{"客户": "甲公司", "金额": 100},
                           {"客户": "乙公司", "金额": 200}]),
        ])
        wb = _export(template_path, entry, html={})
        names = [n for n in wb.sheetnames if n.startswith(ENTRY_SHEET_BASE_NAME)]
        assert names, f"未生成录入清单 sheet: {wb.sheetnames}"
        texts = _sheet_texts(wb[names[0]])
        assert any("甲公司" in t for t in texts), f"录入内容未进产物: {texts}"
        assert any("乙公司" in t for t in texts)
        assert any("D2-detail-rows" in t for t in texts), "缺 item_id 标识"

    def test_none_payload_不建_sheet_保持既有行为(self, template_path):
        """`entry_payloads=None`（既有调用方）必须与改造前逐字相同。"""
        wb = _export(template_path, None, html={"审定表T1": {"rows": [{"a": 1}]}})
        assert not any(n.startswith(ENTRY_SHEET_BASE_NAME) for n in wb.sheetnames)


# ═══════════════════════════════════════════════════════════════════════════
# R2.3 —— 不改写模板既有单元格（含反向自检）
# ═══════════════════════════════════════════════════════════════════════════


class TestTemplateCellsUntouched:
    def test_template_sheet_逐格相等(self, template_path):
        entry = _result([
            _payload("x-rows", "json_array", rows=[{"k": "v"}]),
            _payload("y-note", "plain_text", text="文本内容"),
        ])
        wb = _export(template_path, entry, html={})
        ws = wb["审定表T1"]
        for ref, expected in _TEMPLATE_CELLS.items():
            assert ws[ref].value == expected, (
                f"模板单元格 {ref} 被改写: {ws[ref].value!r} != {expected!r}"
            )

    def test_反向自检_故意写一格必被发现(self, template_path):
        """证明上一条不是恒真 —— 篡改一格后同一判据必须打红。"""
        entry = _result([_payload("x", "plain_text", text="v")])
        wb = _export(template_path, entry, html={})
        ws = wb["审定表T1"]
        ws["A1"] = "被篡改"
        mismatched = [
            ref for ref, exp in _TEMPLATE_CELLS.items() if ws[ref].value != exp
        ]
        assert mismatched == ["A1"], (
            "逐格比对无法发现篡改 ⇒ 判据是恒真的，等于没验"
        )

    def test_模板_sheet_数量只增不改(self, template_path):
        entry = _result([_payload("x", "plain_text", text="v")])
        wb = _export(template_path, entry, html={})
        assert "审定表T1" in wb.sheetnames, "模板 sheet 被删"


# ═══════════════════════════════════════════════════════════════════════════
# R2.2 —— 三形态渲染
# ═══════════════════════════════════════════════════════════════════════════


class TestThreeShapeRendering:
    def test_json_array_列名取载荷键集不硬写(self, template_path):
        entry = _result([
            _payload("arr", "json_array",
                     rows=[{"甲列": 1, "乙列": 2}, {"甲列": 3, "丙列": 4}]),
        ])
        wb = _export(template_path, entry, html={})
        texts = _sheet_texts(wb[[n for n in wb.sheetnames
                                 if n.startswith(ENTRY_SHEET_BASE_NAME)][0]])
        # 三个键都要出现（含只在第二行出现的「丙列」——键集须按并集保序）
        for key in ("甲列", "乙列", "丙列"):
            assert key in texts, f"列名 {key} 未出现（键集未取并集）: {texts}"

    def test_json_object_键值两列纵向(self, template_path):
        entry = _result([
            _payload("obj", "json_object", obj={"结论": "无误", "复核人": "张三"}),
        ])
        wb = _export(template_path, entry, html={})
        texts = _sheet_texts(wb[[n for n in wb.sheetnames
                                 if n.startswith(ENTRY_SHEET_BASE_NAME)][0]])
        assert "键" in texts and "值" in texts, f"缺键值表头: {texts}"
        assert "结论" in texts and "无误" in texts
        assert "复核人" in texts and "张三" in texts

    def test_plain_text_三列表含来源列(self, template_path):
        entry = _result([
            _payload("p1", "plain_text", text="已核对", src="remark"),
            _payload("p2", "plain_text", text="待复核", src="conclusion"),
        ])
        wb = _export(template_path, entry, html={})
        texts = _sheet_texts(wb[[n for n in wb.sheetnames
                                 if n.startswith(ENTRY_SHEET_BASE_NAME)][0]])
        assert "item_id" in texts and "值" in texts
        assert "来源列" in texts, "缺来源列（承担 R2.8 数据来源语义）"
        # 两个 source_field 都要如实落盘（不是写死一个）
        assert "remark" in texts and "conclusion" in texts

    def test_嵌套值不抛异常(self, template_path):
        """openpyxl 无法写 dict/list —— 必须压平而不是让导出崩掉。"""
        entry = _result([
            _payload("nested", "json_array",
                     rows=[{"明细": [{"a": 1}], "元数据": {"k": "v"}}]),
        ])
        wb = _export(template_path, entry, html={})  # 不抛即通过
        assert any(n.startswith(ENTRY_SHEET_BASE_NAME) for n in wb.sheetnames)


# ═══════════════════════════════════════════════════════════════════════════
# R2.5 / R2.6 / R2.7 / R2.8
# ═══════════════════════════════════════════════════════════════════════════


class TestSheetNamingAndMeta:
    def test_无录入不产生_sheet(self, template_path):
        """R2.6。"""
        wb = _export(template_path, _result([]), html={})
        assert not any(n.startswith(ENTRY_SHEET_BASE_NAME) for n in wb.sheetnames)

    def test_sheet_名冲突递增且唯一(self):
        """R2.5。"""
        assert resolve_entry_sheet_name([]) == ENTRY_SHEET_BASE_NAME
        n2 = resolve_entry_sheet_name([ENTRY_SHEET_BASE_NAME])
        assert n2 != ENTRY_SHEET_BASE_NAME
        n3 = resolve_entry_sheet_name([ENTRY_SHEET_BASE_NAME, n2])
        assert n3 not in (ENTRY_SHEET_BASE_NAME, n2)

    def test_sheet_名不超_excel_上限(self):
        """Excel 上限 31 字符 —— 超限 openpyxl 会静默截断并可能撞名。"""
        for existing in ([], [ENTRY_SHEET_BASE_NAME], [ENTRY_SHEET_BASE_NAME] * 1):
            assert len(resolve_entry_sheet_name(existing)) <= 31

    def test_真实冲突场景_模板已有同名(self, template_path):
        """模板里已有 `_录入内容` 时，新 sheet 必须换名而不是覆盖。"""
        wb0 = openpyxl.load_workbook(template_path)
        wb0.create_sheet(title=ENTRY_SHEET_BASE_NAME)
        wb0.save(template_path)

        entry = _result([_payload("x", "plain_text", text="v")])
        wb = _export(template_path, entry, html={})
        matched = [n for n in wb.sheetnames if n.startswith(ENTRY_SHEET_BASE_NAME)]
        assert len(matched) == 2, f"应新增一张而非覆盖: {wb.sheetnames}"
        assert len(set(matched)) == 2, "sheet 名重复"

    def test_标注来源与导出时点(self, template_path):
        """R2.8。"""
        entry = _result([_payload("x", "plain_text", text="v")], total_chars=42)
        wb = _export(template_path, entry, html={})
        texts = " ".join(_sheet_texts(
            wb[[n for n in wb.sheetnames if n.startswith(ENTRY_SHEET_BASE_NAME)][0]]
        ))
        assert "checklist_responses" in texts, "缺数据来源标注"
        assert "导出时点" in texts, "缺导出时点标注"

    def test_截断如实标注条数(self, template_path):
        """R2.7 —— 不标注等于骗人。"""
        entry = _result(
            [_payload("big", "plain_text", text="x" * 100,
                      raw_len=866_845, truncated=True)],
            dropped_by_cap=7,
        )
        wb = _export(template_path, entry, html={})
        texts = " ".join(_sheet_texts(
            wb[[n for n in wb.sheetnames if n.startswith(ENTRY_SHEET_BASE_NAME)][0]]
        ))
        assert "不完整" in texts, f"未标注截断: {texts}"
        assert "7" in texts, "未标注被丢弃条数"
        assert "866845" in texts or "866,845" in texts, "未标注原长"

    def test_解析失败也标注(self, template_path):
        entry = _result(
            [_payload("x", "plain_text", text="坏 json")],
            parse_failures=3,
        )
        wb = _export(template_path, entry, html={})
        texts = " ".join(_sheet_texts(
            wb[[n for n in wb.sheetnames if n.startswith(ENTRY_SHEET_BASE_NAME)][0]]
        ))
        assert "无法按结构解析" in texts and "3" in texts


# ═══════════════════════════════════════════════════════════════════════════
# 与自证层的协同
# ═══════════════════════════════════════════════════════════════════════════


class TestCoexistWithSelfEvidence:
    def test_自证_sheet_与录入清单可共存且顺序稳定(self, template_path):
        """html_data 空 + 有录入 ⇒ 两张附加 sheet 都在，且都排在模板 sheet 之前。"""
        entry = _result([_payload("x", "plain_text", text="v")])
        buf = _sync_export_workpaper_xlsx(
            _schema(template_path), {}, _META, True, entry,
        )
        wb = openpyxl.load_workbook(buf)
        assert wb.sheetnames[0].startswith("_导出说明")
        assert wb.sheetnames[1].startswith(ENTRY_SHEET_BASE_NAME)
        assert wb.sheetnames[2] == "审定表T1"
