"""G3 应收股利 — 导入导出（列结构对齐 requirements + composable field keys）.

支持 5 张动态行表格：
  G3-1 审定表(14列) / G3-2 明细表(33列/4区段) / G3-3 调整分录(10列) /
  G3-4 测算及检查表(18列/2区段) / G3-5 长期未收回检查(13列)

字段键与前端 composable 行接口严格对齐，保证 round-trip。
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ── G3-1 审定表（14列）──
_G3_1_HEADERS = [
    "被投资方", "持股比例(%)", "期初未审", "期初AJE", "期初RJE", "期初审定",
    "本期宣告(借方)", "本期收回(贷方)", "期末未审", "期末AJE", "期末RJE", "期末审定",
    "备注", "索引",
]
_G3_1_KEYS = [
    "investeeName", "shareholdingRatio", "openingUnadjusted", "openingAJE", "openingRJE", "openingAdjusted",
    "currentDeclared", "currentReceived", "closingUnadjusted", "closingAJE", "closingRJE", "closingAdjusted",
    "remark", "indexRef",
]

# ── G3-2 明细表（33列/4区段）──
_G3_2_HEADERS = [
    # 被投资方信息(8列)
    "序号", "被投资方名称", "统一社会信用代码", "注册资本", "行业", "投资类型", "初始投资成本", "投资日期",
    # 持股明细(9列)
    "持股数量(股)", "持股比例(%)", "被投资方净利润", "被投资方净资产", "权益份额", "账面值", "核算方法", "是否上市", "上市代码",
    # 分红方案(8列)
    "决议日期", "分红方案描述", "每股股利(元)", "宣告日", "股权登记日", "除权日", "分红总额", "实际分红率(%)",
    # 应收核算(8列)
    "应收股利", "已收金额", "期末应收", "收款日期", "收款方式", "是否逾期", "逾期天数", "备注",
]
_G3_2_KEYS = [
    "seq", "investeeName", "socialCreditCode", "registeredCapital", "industry", "investType", "initialCost", "investDate",
    "sharesHeld", "shareholdingRatio", "investeeNetProfit", "investeeNetAssets", "equityShare", "bookValue", "accountingMethod", "isListed", "listingCode",
    "resolutionDate", "dividendPlan", "dps", "declarationDate", "recordDate", "exDividendDate", "totalDividend", "payoutRatio",
    "dividendReceivable", "receivedAmount", "netReceivable", "receiptDate", "receiptMethod", "isOverdue", "overdueDays", "remark",
]

# ── G3-3 调整分录（10列）──
_G3_3_HEADERS = [
    "序号", "分录类型", "日期", "摘要", "科目代码", "科目名称",
    "借方金额", "贷方金额", "编制人", "备注",
]
_G3_3_KEYS = [
    "seq", "entryType", "entryDate", "summary", "accountCode", "accountName",
    "debitAmount", "creditAmount", "preparedBy", "remark",
]

# ── G3-4 测算及检查表（18列/2区段）──
_G3_4_HEADERS = [
    # 股利测算区段(9列)
    "序号", "被投资方", "持股数量", "每股股利", "应收股利(测算)", "宣告日", "权利日", "分红文件编号", "测算差异",
    # 凭证检查区段(9列)
    "凭证日期", "凭证编号", "摘要", "对方科目", "金额", "收款银行", "到账日期", "核对结果", "审计结论",
]
_G3_4_KEYS = [
    "seq", "investeeName", "sharesHeld", "dps", "calculatedDividend", "declarationDate", "recordDate", "dividendDocNo", "calcVariance",
    "voucherDate", "voucherNo", "summary", "counterAccount", "amount", "receivingBank", "receiptDate", "reconciliationResult", "auditConclusion",
]

# ── G3-5 长期未收回检查（13列）──
_G3_5_HEADERS = [
    "序号", "被投资方", "应收金额", "宣告日", "约定付款日", "逾期天数",
    "逾期原因", "被投资方经营状况", "历史分红记录", "预计可收回性",
    "风险等级", "审计建议", "备注",
]
_G3_5_KEYS = [
    "seq", "investeeName", "receivableAmount", "declarationDate", "agreedPaymentDate", "overdueDays",
    "overdueReason", "investeeOperatingStatus", "historicalDividendRecord", "recoverability",
    "riskLevel", "auditSuggestion", "remark",
]


_G3_SPECS: dict[str, dict[str, Any]] = {
    "G3-1": {
        "item_id": "G3-1-adj-rows",
        "title": "G3-1 应收股利审定表（按被投资方）",
        "headers": _G3_1_HEADERS,
        "field_keys": _G3_1_KEYS,
        "guidance": [
            "G3-1 审定表 编制说明",
            "",
            "借方科目公式：期末未审 = 期初审定 + 本期宣告(借方) - 本期收回(贷方)。",
            "审定 = 未审 + AJE + RJE。公式列导入后前端自动重算。",
            "按被投资方逐行填列，合计行自动汇总。",
        ],
    },
    "G3-2": {
        "item_id": "G3-2-detail-rows",
        "title": "G3-2 应收股利明细表（33列/4区段）",
        "headers": _G3_2_HEADERS,
        "field_keys": _G3_2_KEYS,
        "guidance": [
            "G3-2 明细表 编制说明",
            "",
            "33列拆为4区段Tab：被投资方信息/持股明细/分红方案/应收核算。",
            "权益份额 = 净资产 × 持股比例/100；分红总额 = 持股数 × 每股股利。",
            "实际分红率 = 分红总额 / 净利润 × 100%（净利润≤0→N/A）。",
            "应收股利 = 持股数 × 每股股利；期末应收 = 应收 - 已收。",
            "投资类型填：long-term-equity / other-equity。",
            "核算方法填：cost / equity。",
        ],
    },
    "G3-3": {
        "item_id": "G3-3-adjustment-rows",
        "title": "G3-3 应收股利调整分录",
        "headers": _G3_3_HEADERS,
        "field_keys": _G3_3_KEYS,
        "guidance": [
            "G3-3 调整分录 编制说明",
            "",
            "分录类型填 AJE 或 RJE；每张凭证借贷方金额必须相等。",
            "科目代码1131为应收股利。",
        ],
    },
    "G3-4": {
        "item_id": "G3-4-calccheck-rows",
        "title": "G3-4 测算及检查表（18列/2区段）",
        "headers": _G3_4_HEADERS,
        "field_keys": _G3_4_KEYS,
        "guidance": [
            "G3-4 测算及检查 编制说明",
            "",
            "18列拆为2区段Tab：股利测算(9列) + 凭证检查(9列)。",
            "应收股利(测算) = 持股数量 × 每股股利。",
            "测算差异 = 应收股利(测算) - 企业入账金额。",
            "|差异|>100元前端橙色高亮。",
            "凭证检查区段可通过抽凭引擎自动填入样本。",
        ],
    },
    "G3-5": {
        "item_id": "G3-5-overdue-rows",
        "title": "G3-5 长期未收回检查表（13列）",
        "headers": _G3_5_HEADERS,
        "field_keys": _G3_5_KEYS,
        "guidance": [
            "G3-5 长期未收回检查 编制说明",
            "",
            "逾期天数 = MAX(0, 当前日期 - 约定付款日)。",
            "逾期>180天→红色高亮(极高风险)，>90天→橙色高亮(高风险)。",
            "预计可收回性：全额可收回/部分可收回/很可能无法收回/无法收回。",
            "风险等级：低/中/高/极高。",
        ],
    },
}

router = create_cycle_import_export_router(tag="g3-import-export", api_prefix="g3", specs=_G3_SPECS)
