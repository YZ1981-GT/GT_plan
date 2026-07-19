"""G3 应收股利 — 导入导出（列结构对齐 requirements + composable field keys）.

支持 5 张动态行表格：
  G3-1 审定表(14列) / G3-2 明细表(33列/4区段) / G3-3 调整分录(10列) /
  G3-4 测算及检查表(增加+减少) / G3-4-subsequent 期后收回 /
  G3-5 长期未收回款项检查(Excel滚动态+约定付款日)

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

# ── G3-4 测算及检查表（被投资方行：增加测算 + 减少检查）──
_G3_4_HEADERS = [
    # ① 增加测算
    "序号", "被投资方", "持股比例(%)", "持股数量", "每股股利", "被投资方分红总额",
    "应收股利(测算)", "比例×总额验算", "账面已计股利", "测算差异",
    "宣告日", "主要股利政策", "分红文件编号", "差异原因", "索引号", "已在长投核实",
    # ② 减少检查
    "本期减少", "收现金额", "其他减少科目", "其他减少金额", "其他减少原因",
    "减少差异", "减少索引号", "减少备注",
]
_G3_4_KEYS = [
    "seq", "investeeName", "shareholdingRatio", "sharesHeld", "dps", "investeeTotalDividend",
    "calculatedDividend", "calcByRatio", "bookedAmount", "calcVariance",
    "declarationDate", "dividendPolicy", "dividendDocNo", "varianceReason", "indexNo", "skipDuplicate",
    "periodDecrease", "cashReceived", "otherDecreaseAccount", "otherDecreaseAmount", "otherDecreaseReason",
    "decreaseDiff", "decreaseIndexNo", "decreaseRemark",
]

# ── G3-4 期后收回检查（凭证行）──
_G3_4_SUBSEQUENT_HEADERS = [
    "序号", "被投资方", "日期", "凭证编号", "业务内容", "对方科目", "对方明细科目",
    "借方", "贷方", "金额", "支持性文件",
    "核对1", "核对2", "核对3", "核对4", "核对5",
    "索引号", "是否异常", "异常说明",
]
_G3_4_SUBSEQUENT_KEYS = [
    "seq", "investeeName", "voucherDate", "voucherNo", "summary", "counterAccount", "counterDetailAccount",
    "debitAmount", "creditAmount", "amount", "supportingDocs",
    "check1", "check2", "check3", "check4", "check5",
    "indexNo", "isAbnormal", "abnormalNote",
]

# ── G3-5 长期未收回检查（Excel 滚动态 + 股利逾期勾稽列）──
_G3_5_HEADERS = [
    "序号", "被投资方", "期初余额", "本期借方发生额", "本期贷方发生额", "期末余额",
    "账龄", "经营业务说明", "未收回或未结转的原因", "是否无法收回", "处理计划",
    "审定余额", "期后收款金额", "宣告日", "约定付款日", "逾期天数", "备注",
]
_G3_5_KEYS = [
    "seq", "investeeName", "openingBalance", "periodDebit", "periodCredit", "closingBalance",
    "aging", "businessDesc", "unrecoveredReason", "isUncollectible", "actionPlan",
    "auditedBalance", "postPeriodCollection", "declarationDate", "agreedPaymentDate",
    "overdueDays", "remark",
]


_G3_SPECS: dict[str, dict[str, Any]] = {
    "G3-1": {
        "item_id": "G3-1-adj-rows",
        "title": "G3-1 应收股利审定表（按被投资方）",
        "headers": _G3_1_HEADERS,
        "field_keys": _G3_1_KEYS,
        # 前端 useG3Adjudication 将行 JSON 存于 remark（与 G2-1 一致）
        "storage_field": "remark",
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
        "storage_field": "conclusion",
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
        "storage_field": "conclusion",
        "guidance": [
            "G3-3 调整分录 编制说明",
            "",
            "分录类型填 AJE 或 RJE；每张凭证借贷方金额必须相等。",
            "科目代码1131为应收股利。确认后净调整回写 G3-1 期末 AJE/RJE。",
        ],
    },
    "G3-4": {
        "item_id": "G3-4-calccheck-rows",
        "title": "G3-4 测算及检查表（增加测算+减少检查）",
        "headers": _G3_4_HEADERS,
        "field_keys": _G3_4_KEYS,
        "storage_field": "conclusion",
        # 兼容旧模板：缺新增列时填空；旧表头「企业入账金额」→账面已计
        "allow_missing_headers": True,
        "header_aliases": {
            "账面已计股利": ["企业入账金额"],
            "被投资方分红总额": ["被投资项目股利分配总额", "股利分配总额"],
            "主要股利政策": ["主要股利分配政策"],
        },
        "guidance": [
            "G3-4 测算及检查 编制说明（被投资方行）",
            "",
            "应收股利(测算) = 持股数量 × 每股股利。",
            "测算差异 = 账面已计股利 − 应收股利(测算)；|差异|>100 须填原因或索引。",
            "减少差异 = 本期减少 − 收现金额 − 其他减少金额。",
            "已在长投核实填：是 / 否。",
            "期后收回请使用 sheet=G3-4-subsequent。",
            "兼容旧列名：企业入账金额→账面已计股利。",
        ],
    },
    "G3-4-subsequent": {
        "item_id": "G3-4-subsequent-rows",
        "title": "G3-4 期后收回检查",
        "headers": _G3_4_SUBSEQUENT_HEADERS,
        "field_keys": _G3_4_SUBSEQUENT_KEYS,
        "storage_field": "conclusion",
        "allow_missing_headers": True,
        "header_aliases": {
            "日期": ["凭证日期"],
            "业务内容": ["摘要"],
            "支持性文件": ["收款银行"],
            "是否异常": ["核对结果", "审计结论"],
        },
        "guidance": [
            "G3-4 期后收回检查 编制说明",
            "",
            "核对1~5：√ / — / 空；对应原始凭证齐全、账证一致、处理正确、期间正确、与宣告持股勾稽。",
            "是否异常填：是 / 否。",
            "金额优先取借方，否则取贷方；可由抽凭引擎填入。",
        ],
    },
    "G3-5": {
        "item_id": "G3-5-overdue-rows",
        "title": "G3-5 长期未收回款项检查表",
        "headers": _G3_5_HEADERS,
        "field_keys": _G3_5_KEYS,
        "storage_field": "conclusion",
        "guidance": [
            "G3-5 长期未收回款项检查 编制说明",
            "",
            "期末余额 = 期初余额 + 本期借方 − 本期贷方（公式列导入后前端重算）。",
            "逾期天数 = MAX(0, 当前日期 − 约定付款日)；逾期≥365天汇总至 G3-1「一年以上」。",
            "是否无法收回填：是 / 否 / 部分。",
            "期后收款用于验证可收回性，可与 G3-4 凭证检查勾稽。",
            "参考结论：A 未见异常；B 除…外未见异常；C 证据不足无法表示意见。",
        ],
    },
}

router = create_cycle_import_export_router(tag="g3-import-export", api_prefix="g3", specs=_G3_SPECS)
