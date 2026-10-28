# -*- coding: utf-8 -*-
"""D7-4 贷方发生额分析「与对方科目核对」列（spec oo-writeback-template-parity-closure R3.1：模板有、前端没有的列前端补上）。

模板「（三）合同负债贷方发生额分析」表头 R19：金额 / 数据来源 / 与对方科目核对 / 说明。前端贷方行补了
``counterCheck``，契约 D 列接它、E 列接 ``remark``（说明）。导入导出跟着带上这一列：导出写出、导入读回；
旧版导出文件没有这一列 ⇒ 照常导入、字段留空（不能因为后加的列把旧文件拒掉）。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:  # pragma: no cover
    sys.path.insert(0, str(_BACKEND))
os.environ.setdefault("DB_DISABLE_SSL", "True")

from app.routers.wp_render_strategies import _d7_import_export as d7  # noqa: E402
from app.services.workpaper_sync.phase5_d7_04_analysis import SPEC_D704_CREDIT  # noqa: E402

_COL = "与对方科目核对"


def test_credit_row_round_trips_counter_check() -> None:
    headers = d7._get_headers("D7-4")
    assert _COL in headers
    credit = {"_rowType": "credit", "item": "银行存款收款", "amount": 1200.5, "dataSource": "序时账",
              "remark": "与银行存款借方发生额核对", "counterCheck": "一致"}
    exported = d7._export_row("D7-4", credit, headers)
    assert len(exported) == len(headers)
    parsed = d7._parse_row("D7-4", tuple(exported), headers)
    assert parsed["_rowType"] == "credit"
    assert parsed["counterCheck"] == "一致"
    assert parsed["remark"] == "与银行存款借方发生额核对"


def test_debit_row_has_no_counter_check() -> None:
    headers = d7._get_headers("D7-4")
    debit = {"_rowType": "debit", "item": "营业收入", "amount": 300, "dataSource": "", "remark": "备注"}
    parsed = d7._parse_row("D7-4", tuple(d7._export_row("D7-4", debit, headers)), headers)
    assert "counterCheck" not in parsed  # 借方区模板没有这一列
    assert parsed["remark"] == "备注"


def test_old_export_file_without_the_column_still_imports() -> None:
    required = d7._required_import_headers("D7-4")
    assert _COL not in required
    assert required == ["记录类型", "项目", "金额", "数据来源", "备注"]
    old_headers = list(required)
    parsed = d7._parse_row("D7-4", ("credit", "应收票据", 10, "总账", "说明"), old_headers)
    assert parsed["counterCheck"] == ""


def test_contract_credit_table_follows_template_header() -> None:
    """契约贷方区：数据行 R21-R22、表头 R19、D / E 两列分别接 counterCheck / remark。"""
    by_col = {fs[1]: (fs[4], fs[5]) for fs in SPEC_D704_CREDIT.field_specs}
    assert by_col == {
        "A": ("item", "项目"), "B": ("amount", "金额"), "C": ("dataSource", "数据来源"),
        "D": ("counterCheck", _COL), "E": ("remark", "说明"),
    }
    assert (SPEC_D704_CREDIT.header_row, SPEC_D704_CREDIT.first_data_row, SPEC_D704_CREDIT.last_data_row,
            SPEC_D704_CREDIT.footer_row) == (19, 21, 22, 24)
    assert SPEC_D704_CREDIT.footer_carries_total_formula is False
