# -*- coding: utf-8 -*-
"""D3-4 贷方发生额分析「与对方科目核对」列 + 行身份键（spec oo-writeback-template-parity-closure R3 任务 9.4c）。

模板「（三）预收账款贷方发生额分析」表头 R20：（A 空）/ 金额 / 数据来源 / 与对方科目核对 / 说明。原契约两区共用
借方区 R10 的四列 ⇒ D「与对方科目核对」接成了备注、E「说明」没管；行身份键写的 ``rowId``，而前端与导入只写
``rowKey`` ⇒ 一接通每行都按「缺少稳定行身份」拒收。现：贷方区 D 接 ``counterCheck``、E 接 ``remark``，两区身份键
``rowKey``；导入导出带上这一列，旧版导出文件没有它照常导入、字段留空（同 D7-4）。
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

import openpyxl  # noqa: E402
import pytest  # noqa: E402

from app.routers.wp_render_strategies import _d3_import_export as d3  # noqa: E402
from app.services.workpaper_sync.phase5_d3_04_analysis import (  # noqa: E402
    MANAGED_SHEET_D304,
    SPEC_D304_CREDIT,
    SPEC_D304_DEBIT,
)
from app.services.workpaper_sync.phase5_row_table_sheet import (  # noqa: E402
    RowTableStorePayloadError,
    iter_store_rows,
)

_COL = "与对方科目核对"
_TEMPLATE = _BACKEND / "wp_templates" / "D" / "D3 预收账款.xlsx"


def test_credit_row_round_trips_counter_check() -> None:
    headers = d3._get_headers("D3-4-credit")
    assert headers[-1] == _COL
    credit = {"rowKey": "bank", "label": "其中：银行存款收款", "amount": 1200.5, "source": "序时账",
              "remark": "与银行存款借方发生额核对", "counterCheck": "一致"}
    exported = d3._export_d3_4_row(credit, credit=True)
    assert len(exported) == len(headers)
    parsed = d3._parse_d3_4_row(tuple(exported), headers, credit=True)
    assert parsed is not None
    assert parsed["rowKey"] == "bank"
    assert parsed["counterCheck"] == "一致"
    assert parsed["remark"] == "与银行存款借方发生额核对"


def test_debit_row_has_no_counter_check() -> None:
    headers = d3._get_headers("D3-4-debit")
    assert _COL not in headers  # 借方区模板没有这一列
    debit = {"rowKey": "fa", "label": "固定资产", "amount": 300, "source": "", "remark": "备注"}
    exported = d3._export_d3_4_row(debit)
    assert len(exported) == len(headers)
    parsed = d3._parse_d3_4_row(tuple(exported), headers)
    assert parsed is not None and "counterCheck" not in parsed
    assert parsed["remark"] == "备注"


def test_old_export_file_without_the_column_still_imports() -> None:
    required = d3._required_import_headers("D3-4-credit")
    assert required == ["行键", "项目", "金额", "来源", "备注"]
    parsed = d3._parse_d3_4_row(("bill", "应收票据", 10, "总账", "说明"), list(required), credit=True)
    assert parsed is not None and parsed["counterCheck"] == ""
    # 其他 sheet 的必填列不受影响
    assert d3._required_import_headers("D3-4-debit") == d3._get_headers("D3-4-debit")


def test_contract_credit_table_follows_template_header() -> None:
    """契约贷方区：表头 R20、数据行 R22-R23、D / E 分别接 counterCheck / remark；借方区不变。"""
    by_col = {fs[1]: (fs[4], fs[5]) for fs in SPEC_D304_CREDIT.field_specs}
    assert by_col == {
        "A": ("label", "项目"), "B": ("amount", "金额"), "C": ("source", "数据来源"),
        "D": ("counterCheck", _COL), "E": ("remark", "说明"),
    }
    assert (SPEC_D304_CREDIT.header_row, SPEC_D304_CREDIT.first_data_row, SPEC_D304_CREDIT.last_data_row,
            SPEC_D304_CREDIT.footer_row) == (20, 22, 23, 25)
    assert {fs[1]: fs[4] for fs in SPEC_D304_DEBIT.field_specs} == {
        "A": "label", "B": "amount", "C": "source", "D": "remark",
    }
    assert SPEC_D304_DEBIT.header_row == 10


def test_contract_headers_match_the_template_cells() -> None:
    """表头文字逐格取模板（A20 空 ⇒ 不比 A 列）：防止契约与模板再次错位。"""
    warnings.filterwarnings("ignore")
    wb = openpyxl.load_workbook(_TEMPLATE, data_only=False, read_only=True)
    try:
        ws = wb[MANAGED_SHEET_D304]
        for spec in (SPEC_D304_DEBIT, SPEC_D304_CREDIT):
            for fs in spec.field_specs:
                cell = ws[f"{fs[1]}{spec.header_row}"].value
                if fs[1] == "A" and spec is SPEC_D304_CREDIT:
                    assert cell is None
                    continue
                assert str(cell).strip() == fs[5], (spec.store_item_id, fs[1], cell)
    finally:
        wb.close()


def test_both_tables_key_rows_by_row_key() -> None:
    """前端 / 导入只写 rowKey ⇒ 按 rowKey 认行；只带 rowId 的形状被拒（不静默按位置认行）。"""
    assert SPEC_D304_DEBIT.row_identity_key == SPEC_D304_CREDIT.row_identity_key == "rowKey"
    # 导入的形状（`_parse_d3_4_row` 的输出）原样能认出行身份
    imported = d3._parse_d3_4_row(("bank", "其中：银行存款收款", 5, "", "", "一致"),
                                  d3._get_headers("D3-4-credit"), credit=True)
    assert [ident for ident, _row in iter_store_rows(SPEC_D304_CREDIT, [imported])] == ["bank"]
    with pytest.raises(RowTableStorePayloadError, match="缺少稳定行身份 'rowKey'"):
        list(iter_store_rows(SPEC_D304_DEBIT, [{"rowId": "x", "label": "固定资产", "amount": 1}]))
