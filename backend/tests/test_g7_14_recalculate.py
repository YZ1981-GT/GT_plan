"""G7-14 服务端公式重算单元测试（对齐前端 recalcRow）。"""

from __future__ import annotations

import io

from app.routers.wp_render_strategies._g7_long_term_equity_method_import_export import (
    _g7_14_recalculate,
    _normalize_g7_14_rows_import,
)
from app.routers.wp_render_strategies._g7_long_term_equity_method_service import (
    G7LongTermEquityMethodService,
)

svc = G7LongTermEquityMethodService()


def test_p10_to_p13_pure_functions():
    assert svc.calc_income_difference(50_000, 60_000, 10_000) == 0.0
    assert svc.calc_ltei_book_balance(100, 20, 5, 3) == 128.0
    assert svc.calc_net_asset_share_variance(128, 400, 0.3) == 8.0
    assert svc.calc_unexplained_variance(8, 10, -1, 2) == 1.0


def test_recalculate_g7_14_row_overwrites_stale_formula_columns():
    row = {
        "investeeName": "联营甲",
        "reportedNetProfit": 1000,
        "internalTransactionAdj": 100,
        "fvDepreciationAdj": 50,
        "accountingPolicyAdj": 20,
        "otherAdj": 10,
        "investmentRatio": 0.3,
        # 故意写入错误的公式列
        "adjustedNetProfit": 9999,
        "equityShare": 9999,
        "incomeDifference": 9999,
        "confirmedIncome": 250,
        "dividendDistributed": 30,
        "ociChange": 100,
        "otherEquityChange": 50,
        "confirmedOci": 0,
        "confirmedOtherEquity": 0,
        "costOpening": 1000,
        "costChange": 0,
        "pnlAdjOpening": 100,
        "pnlAdjChange": 220,
        "ociBalOpening": 10,
        "otherEqBalOpening": 5,
        "auditedNetAssets": 5000,
        "goodwill": 50,
        "cumulativeFvAdj": 20,
        "impairment": 0,
        "openingBalance": 1115,
        "closingBalance": 0,
        "unexplainedVariance": 9999,
    }
    out = svc.recalculate_g7_14_row(dict(row))

    # 调整后净利润 = 1000-100-50+20+10 = 880
    assert out["adjustedNetProfit"] == 880.0
    # ⑤ = 880 * 0.3 = 264
    assert out["equityShare"] == 264.0
    assert out["ociShare"] == 30.0
    assert out["otherEquityShare"] == 15.0
    # ⑩ = 250 - 264 + 30 = 16
    assert out["incomeDifference"] == 16.0
    assert out["costClosing"] == 1000.0
    assert out["pnlAdjClosing"] == 320.0
    assert out["ociBalChange"] == 30.0
    assert out["ociBalClosing"] == 40.0
    assert out["otherEqBalClosing"] == 20.0
    # R = 1000+320+40+20 = 1380
    assert out["lteiBookBalance"] == 1380.0
    assert out["shareOfAuditedNetAssets"] == 1500.0
    # S = 1380 - 1500 = -120
    assert out["netAssetShareVariance"] == -120.0
    # ⑮ = -120 - 50 - 20 + 0 = -190
    assert out["unexplainedVariance"] == -190.0
    # 期末 = 1115 + 264 + 30 + 15 - 30 = 1394
    assert out["closingBalance"] == 1394.0


def test_recalculate_oci_and_other_equity_differences():
    out = svc.recalculate_g7_14_row({
        "reportedNetProfit": 0,
        "investmentRatio": 0.4,
        "ociChange": 100,
        "otherEquityChange": 50,
        "confirmedOci": 30,
        "confirmedOtherEquity": 10,
    })
    assert out["ociShare"] == 40.0
    assert out["otherEquityShare"] == 20.0
    assert out["ociDifference"] == -10.0
    assert out["otherEquityDifference"] == -10.0


def test_recalculate_opening_and_closing_recon_variances():
    out = svc.recalculate_g7_14_row({
        "costOpening": 1000,
        "pnlAdjOpening": 100,
        "ociBalOpening": 50,
        "otherEqBalOpening": 20,
        "g72OpeningTotal": 1170,
        "costChange": 0,
        "pnlAdjChange": 0,
        "ociChange": 0,
        "otherEquityChange": 0,
        "investmentRatio": 0.3,
        "g72ClosingTotal": 1100,
    })
    # P = 1000+100+50+20 - 1170 = 0
    assert out["openingReconVariance"] == 0.0
    # Q/ltei = 1000+100+50+20 = 1170; S = 1170 - 1100 = 70
    assert out["lteiBookBalance"] == 1170.0
    assert out["closingReconVariance"] == 70.0


def test_import_helper_normalizes_ratio_then_recalculates():
    rows = _normalize_g7_14_rows_import([{
        "investeeName": "乙",
        "reportedNetProfit": 200,
        "internalTransactionAdj": 0,
        "fvDepreciationAdj": 0,
        "accountingPolicyAdj": 0,
        "otherAdj": 0,
        "investmentRatio": 30,  # 百分数
        "confirmedIncome": 60,
        "dividendDistributed": 0,
        "adjustedNetProfit": 1,
        "equityShare": 1,
    }])
    assert rows[0]["investmentRatio"] == 0.3
    out = _g7_14_recalculate(rows[0])
    assert out["adjustedNetProfit"] == 200.0
    assert out["equityShare"] == 60.0
    assert out["incomeDifference"] == 0.0


def test_g7_15_import_normalizes_ratio_and_margin_percent():
    from app.routers.wp_render_strategies._g7_long_term_equity_method_import_export import (
        _normalize_g7_15_rows_import,
        _prepare_g7_15_rows_export,
    )

    rows = _normalize_g7_15_rows_import([{
        "investeeName": "联营甲",
        "investeeId": "inv-a",
        "transactionType": "逆流",
        "transactionAmount": 1000,
        "grossMargin": 20,  # 百分数
        "investmentRatio": 30,  # 百分数
        "isRelatedParty": "是",
    }])
    assert rows[0]["grossMargin"] == 0.2
    assert rows[0]["investmentRatio"] == 0.3
    assert rows[0]["isRelatedParty"] is True

    exported = _prepare_g7_15_rows_export(rows)
    assert exported[0]["grossMargin"] == 20.0
    assert exported[0]["investmentRatio"] == 30.0
    assert exported[0]["isRelatedParty"] == "是"


def test_g7_15_import_recalculates_formula_columns():
    from app.routers.wp_render_strategies._g7_long_term_equity_method_import_export import (
        _normalize_g7_15_rows_import,
    )

    rows = _normalize_g7_15_rows_import([{
        "investeeName": "联营甲",
        "transactionType": "逆流",
        "transactionAmount": 1000,
        "grossMargin": 20,  # %
        "investmentRatio": 30,  # %
        "priorElimination": 10,
        "unrealizedProfit": 999,  # 应被公式覆盖
        "unrealizedProfitManual": False,
    }])
    assert rows[0]["grossMargin"] == 0.2
    assert rows[0]["investmentRatio"] == 0.3
    assert rows[0]["unrealizedProfit"] == 200.0
    assert rows[0]["eliminationAmount"] == 60.0
    assert rows[0]["currentChange"] == 50.0


def test_g7_15_import_keeps_manual_profit_when_margin_zero():
    from app.routers.wp_render_strategies._g7_long_term_equity_method_import_export import (
        _normalize_g7_15_rows_import,
    )

    rows = _normalize_g7_15_rows_import([{
        "transactionType": "顺流",
        "transactionAmount": 1000,
        "grossMargin": 0,
        "unrealizedProfit": 80,
        "unrealizedProfitManual": False,
        "priorElimination": 0,
    }])
    assert rows[0]["unrealizedProfitManual"] is True
    assert rows[0]["unrealizedProfit"] == 80.0
    assert rows[0]["eliminationAmount"] == 80.0


def test_g7_15_legacy_14col_sheet_parses_by_header_name():
    """旧 14 列模板（无毛利率/ID）应按表头名导入，并 warning。"""
    from openpyxl import Workbook

    from app.routers.wp_render_strategies._g7_long_term_equity_method_import_export import (
        _G7_15_CORE_HEADERS,
        _normalize_g7_15_rows_import,
        _parse_g7_15_sheet_rows,
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "G7-15"
    ws.append(["G7-15 内部交易抵销测算表"])  # title row 1
    ws.append(list(_G7_15_CORE_HEADERS))  # header row 2
    # 故意打乱列顺序：把「持股比例(%)」放到末尾前一列附近仍按名匹配
    # 这里保持 CORE 顺序即可；另测缺可选列
    ws.append([
        "联营甲", "逆流", "销售商品", 1000,
        200, 30, 60, 10,
        50, "借：投资收益", "是", "合理",
        "G7-15-1", "旧模板",
    ])
    buf = io.BytesIO()
    wb.save(buf)
    content = buf.getvalue()

    rows, errors, warnings = _parse_g7_15_sheet_rows(content)
    assert not errors
    assert any("旧模板" in w or "缺列" in w for w in warnings)
    assert len(rows) == 1
    assert rows[0]["investeeName"] == "联营甲"
    assert rows[0]["grossMargin"] == 0.0  # 缺列 → 0
    assert rows[0].get("unrealizedProfitManual") is True  # 有未实现利润无毛利率
    rows = _normalize_g7_15_rows_import(rows)
    assert rows[0]["investmentRatio"] == 0.3
    assert rows[0]["isRelatedParty"] is True


def test_g7_15_reordered_columns_still_map_by_name():
    """列顺序打乱时仍按表头名映射。"""
    from openpyxl import Workbook

    from app.routers.wp_render_strategies._g7_long_term_equity_method_import_export import (
        _G7_15_HEADERS,
        _parse_g7_15_sheet_rows,
        _normalize_g7_15_rows_import,
    )

    # 打乱：毛利率紧挨被投资单位，持股比例靠前
    shuffled = [
        "被投资单位", "毛利率(%)", "持股比例(%)", "交易类型", "交易内容",
        "交易金额", "未实现利润", "未实现利润手工覆盖", "应抵销金额", "上年抵销", "本年变动",
        "抵销分录", "是否关联交易", "审计结论", "索引", "备注", "被投资单位ID",
    ]
    assert set(shuffled) == set(_G7_15_HEADERS)

    wb = Workbook()
    ws = wb.active
    ws.title = "G7-15"
    ws.append(["title"])
    ws.append(shuffled)
    # values follow shuffled order
    ws.append([
        "联营乙", 20, 40, "顺流", "服务",
        5000, 0, "否", 0, 0, 0,
        "", "否", "合理", "", "", "id-乙",
    ])
    buf = io.BytesIO()
    wb.save(buf)

    rows, errors, warnings = _parse_g7_15_sheet_rows(buf.getvalue())
    assert not errors
    assert not warnings  # 全列齐全
    rows = _normalize_g7_15_rows_import(rows)
    assert rows[0]["investeeName"] == "联营乙"
    assert rows[0]["investeeId"] == "id-乙"
    assert rows[0]["grossMargin"] == 0.2
    assert rows[0]["investmentRatio"] == 0.4
    assert rows[0]["transactionType"] == "顺流"
    assert rows[0]["transactionAmount"] == 5000.0
    assert rows[0]["unrealizedProfit"] == 1000.0  # 公式重算
    assert rows[0]["eliminationAmount"] == 1000.0
