"""F5 营业成本 — 导入导出（列结构对齐 requirements）."""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

_ADJ_HEADERS = ["序号", "分录类型", "日期", "摘要", "科目代码", "科目名称", "借方金额", "贷方金额", "编制人", "备注"]
_ADJ_KEYS = ["seq", "entryType", "date", "summary", "accountCode", "accountName", "debitAmount", "creditAmount", "preparer", "remark"]

_F5_2_HEADERS = [
    "品种", "1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月", "9月", "10月", "11月", "12月",
    "上半年合计", "上半年占比", "上半年月均", "上半年最高月", "上半年最低月", "波动系数",
    "下半年合计", "全年合计", "上期合计", "变动额", "变动率",
]
_F5_2_KEYS = [
    "variety", "m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8", "m9", "m10", "m11", "m12",
    "h1Total", "h1Share", "h1Avg", "h1Max", "h1Min", "volCoef",
    "h2Total", "yearTotal", "priorTotal", "changeAmt", "changeRate",
]

_F5_SPECS: dict[str, dict[str, Any]] = {
    "F5-2": {
        "item_id": "F5-2-rows",
        "title": "F5-2 主营业务成本月度明细（24列）",
        "headers": _F5_2_HEADERS,
        "field_keys": _F5_2_KEYS,
        "guidance": [
            "F5-2 月度明细 编制说明",
            "",
            "24列与 HTML 底稿两区段Tab（上半年13列+下半年11列）合并为宽表。",
            "1~12月为各品种月度成本；上半年/下半年/全年合计等为公式列，导入后可重算。",
        ],
    },
    "F5-3": {
        "item_id": "F5-3-rows",
        "title": "F5-3 其他业务成本明细",
        "headers": [
            "序号", "成本项目", "本期金额", "上期金额", "变动额", "变动率", "成本构成占比",
            "对应收入", "成本率", "收入确认时点", "成本结转时点", "配比合理性", "审计评价", "备注",
        ],
        "field_keys": [
            "seq", "costItem", "currentAmt", "priorAmt", "changeAmt", "changeRate", "sharePct",
            "relatedRevenue", "costRate", "revenueTiming", "costTiming", "matchingReasonable", "auditEvaluation", "remark",
        ],
        "guidance": ["F5-3 其他业务成本 编制说明", "", "变动率=(本期-上期)/上期；成本率=本期/对应收入。"],
    },
    "F5-4": {
        "item_id": "F5-4-rows",
        "title": "F5-4 调整分录汇总表",
        "headers": _ADJ_HEADERS,
        "field_keys": _ADJ_KEYS,
        "guidance": ["F5-4 调整分录 编制说明", "", "分录类型填 AJE 或 RJE。"],
    },
    "F5-5": {
        "item_id": "F5-5-rows",
        "title": "F5-5 与上年度比较分析表",
        "headers": [
            "品种", "本期收入", "本期成本", "本期毛利", "本期毛利率", "上期收入", "上期成本", "上期毛利", "上期毛利率",
            "收入变动额", "收入变动率", "成本变动额", "成本变动率", "毛利率变动", "变动原因", "审计评价", "备注",
        ],
        "field_keys": [
            "variety", "currentRevenue", "currentCost", "currentGross", "currentMargin",
            "priorRevenue", "priorCost", "priorGross", "priorMargin",
            "revenueChange", "revenueChangeRate", "costChange", "costChangeRate", "marginChange",
            "changeReason", "auditEvaluation", "remark",
        ],
        "guidance": ["F5-5 比较分析 编制说明", "", "毛利=收入-成本；毛利率=毛利/收入。"],
    },
    "F5-6": {
        "item_id": "F5-6-rows",
        "title": "F5-6 数量核对表",
        "headers": [
            "序号", "品种", "规格", "计量单位", "销售数量", "结转成本数量", "数量差异", "差异率",
            "差异原因分类", "期初库存", "本期产量", "本期采购", "可供销售量", "期末库存", "理论结转量", "理论差异",
        ],
        "field_keys": [
            "seq", "variety", "spec", "unit", "qtySold", "qtyCost", "qtyDiff", "qtyDiffRate",
            "diffReason", "openingStock", "production", "purchase", "availableQty", "closingStock", "theoreticalQty", "theoreticalDiff",
        ],
        "guidance": ["F5-6 数量核对 编制说明", "", "数量差异=销售数量-结转成本数量；可供销售=期初+产量+采购。"],
    },
    "F5-8": {
        "item_id": "F5-8-rows",
        "title": "F5-8 重大调整事项",
        "headers": ["序号", "调整日期", "调整事项", "调整金额", "调整原因", "审批依据", "凭证编号", "审计评价"],
        "field_keys": ["seq", "adjustDate", "adjustItem", "adjustAmount", "adjustReason", "approvalBasis", "voucherNo", "auditEvaluation"],
        "guidance": ["F5-8 重大调整 编制说明"],
    },
}

router = create_cycle_import_export_router(tag="f5-import-export", api_prefix="f5", specs=_F5_SPECS)
