"""I3 商誉 — 导入导出3端点（列结构对齐 requirements）.

POST /i3/export-template → 空白结构xlsx
POST /i3/export-data → 当前数据xlsx（含公式结果）
POST /i3/import-data → 解析xlsx→验证→写入checklist_responses

支持sheet: 审定表I3-1, 明细表I3-2, 调整分录I3-3, 入账价值I3-4, 减值测试I3-6, 可收回金额I3-7
动态行表格（需导入）: I3-2, I3-3, I3-4, I3-6, I3-7

商誉特殊：
- 审定表无摊销行（期末=期初+新并购-减值）
- 明细表按被投资单位（CGU）维度
- I3-6/I3-7 为DCF减值核心表
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ─── I3-1 审定表（商誉不摊销！单科目1711） ────────────────────────────────────

_I3_1_HEADERS = [
    "被投资单位", "初始确认", "期初余额", "本期增加(新并购)", "本期减少(减值)",
    "期末余额", "未审数", "AJE", "RJE", "审定数", "减值准备", "净额",
]
_I3_1_KEYS = [
    "investee", "initialRecognition", "openingBalance", "newAcquisition", "impairment",
    "closingBalance", "unadjusted", "aje", "rje", "audited", "impairmentReserve", "netValue",
]

# ─── I3-2 明细表（30列3区段：基础/入账/减值） ─────────────────────────────────

_I3_2_BASE_HEADERS = [
    "被投资单位", "并购日期", "合并对价", "被购方净资产公允价值", "持股比例(%)",
]
_I3_2_BASE_KEYS = [
    "investee", "acquisitionDate", "mergerConsideration", "netAssetFairValue", "equityRatio",
]

_I3_2_ENTRY_HEADERS = [
    "被投资单位", "合并成本", "可辨认净资产公允", "商誉原值", "确认依据",
]
_I3_2_ENTRY_KEYS = [
    "investee", "mergerCost", "identifiableNetAssetFV", "goodwillOriginalCost", "recognitionBasis",
]

_I3_2_IMPAIR_HEADERS = [
    "被投资单位", "商誉原值", "累计减值", "本期减值", "期末净额",
]
_I3_2_IMPAIR_KEYS = [
    "investee", "goodwillOriginal", "accImpairment", "currentImpairment", "endingNetValue",
]

# ─── I3-3 调整分录 ──────────────────────────────────────────────────────────

_I3_3_HEADERS = [
    "序号", "调整事项", "类别", "科目代码", "科目名称", "摘要", "借方金额", "贷方金额", "索引", "备注",
]
_I3_3_KEYS = [
    "seq", "description", "entryType", "accountCode", "accountName", "summary", "debitAmount", "creditAmount", "indexRef", "remark",
]

# ─── I3-4 入账价值测算 ──────────────────────────────────────────────────────

_I3_4_HEADERS = [
    "被投资单位", "合并成本", "对价形式", "或有对价", "交易费用",
    "被购方可辨认净资产公允", "少数股东权益", "商誉", "确认日期", "备注",
]
_I3_4_KEYS = [
    "investee", "mergerCost", "considerationType", "contingentConsideration", "transactionCosts",
    "identifiableNetAssetFV", "minorityInterest", "goodwill", "recognitionDate", "remark",
]

# ─── I3-6 减值测试（按CGU） ─────────────────────────────────────────────────

_I3_6_HEADERS = [
    "CGU名称", "包含商誉", "商誉账面", "资产组其他资产账面", "资产组账面(含商誉)",
    "可收回金额", "减值金额", "商誉分摊减值", "其他资产分摊减值", "减值后商誉净额", "结论",
]
_I3_6_KEYS = [
    "cguName", "includesGoodwill", "goodwillBookValue", "otherAssetsBookValue", "totalBookValue",
    "recoverableAmount", "impairmentAmount", "goodwillImpairment", "otherAssetsImpairment", "goodwillNetAfter", "conclusion",
]

# ─── I3-7 可收回金额测试（DCF核心100行） ─────────────────────────────────────

_I3_7_HEADERS = [
    "CGU名称", "预测年份", "营业收入", "营业成本", "营业利润",
    "所得税", "折旧摊销", "资本支出", "营运资金变动", "自由现金流",
    "折现率(WACC)", "折现因子", "现值", "永续增长率", "终值", "终值现值",
]
_I3_7_KEYS = [
    "cguName", "forecastYear", "revenue", "costOfGoods", "operatingProfit",
    "incomeTax", "depreciation", "capex", "workingCapitalChange", "freeCashFlow",
    "waccRate", "discountFactor", "presentValue", "growthRate", "terminalValue", "terminalValuePV",
]

# ═══════════════════════════════════════════════════════════════════════════════

_I3_SPECS: dict[str, dict[str, Any]] = {
    "I3-1": {
        "item_id": "I3-1-adj-rows",
        "title": "审定表I3-1（商誉不摊销！期末=期初+新并购-减值）",
        "headers": _I3_1_HEADERS,
        "field_keys": _I3_1_KEYS,
        "guidance": [
            "I3-1 商誉审定表 编制说明",
            "",
            "商誉不摊销！期末余额=期初+本期增加(新并购)-本期减少(减值)。",
            "本期增加仅来自新并购（正常情况为0）。",
            "本期减少仅来自减值（商誉减值不可转回！）。",
            "审定数=未审+AJE+RJE。",
            "净额=商誉原值-累计减值准备。",
        ],
    },
    "I3-2-base": {
        "item_id": "I3-2-rows",
        "title": "I3-2 明细表（基础信息：并购来源）",
        "headers": _I3_2_BASE_HEADERS,
        "field_keys": _I3_2_BASE_KEYS,
        "guidance": [
            "I3-2 商誉明细表 — 基础区段 编制说明",
            "",
            "逐笔记录每笔商誉来源的被投资单位、并购日期及对价信息。",
            "持股比例用于确认非同一控制下企业合并。",
        ],
    },
    "I3-2-entry": {
        "item_id": "I3-2-rows",
        "title": "I3-2 明细表（入账价值）",
        "headers": _I3_2_ENTRY_HEADERS,
        "field_keys": _I3_2_ENTRY_KEYS,
        "guidance": [
            "I3-2 入账价值区段 编制说明",
            "",
            "商誉原值=合并成本-可辨认净资产公允价值。",
            "合并成本包含对价+或有对价+交易费用。",
        ],
    },
    "I3-2-impair": {
        "item_id": "I3-2-rows",
        "title": "I3-2 明细表（减值情况）",
        "headers": _I3_2_IMPAIR_HEADERS,
        "field_keys": _I3_2_IMPAIR_KEYS,
        "guidance": [
            "I3-2 减值区段 编制说明",
            "",
            "期末净额=商誉原值-累计减值。",
            "商誉减值不可转回（CAS8明确规定）。",
        ],
    },
    "I3-3": {
        "item_id": "I3-3-rows",
        "title": "I3-3 调整分录汇总表",
        "headers": _I3_3_HEADERS,
        "field_keys": _I3_3_KEYS,
        "guidance": [
            "I3-3 调整分录 编制说明",
            "",
            "类别填 AJE（审计调整分录）或 RJE（重分类调整分录）。",
            "借方合计应等于贷方合计（借贷平衡）。",
            "商誉减值调整分录：借记资产减值损失，贷记商誉减值准备。",
        ],
    },
    "I3-4": {
        "item_id": "I3-4-rows",
        "title": "I3-4 入账价值测算表",
        "headers": _I3_4_HEADERS,
        "field_keys": _I3_4_KEYS,
        "guidance": [
            "I3-4 入账价值测算 编制说明",
            "",
            "商誉=合并成本-被购方可辨认净资产公允价值份额。",
            "合并成本=支付对价+或有对价公允+直接相关交易费用。",
            "仅非同一控制下企业合并产生商誉。",
        ],
    },
    "I3-6": {
        "item_id": "I3-6-rows",
        "title": "I3-6 商誉减值测试（按CGU分摊）",
        "headers": _I3_6_HEADERS,
        "field_keys": _I3_6_KEYS,
        "guidance": [
            "I3-6 商誉减值测试 编制说明",
            "",
            "减值金额=MAX(资产组账面-可收回金额, 0)。",
            "分摊规则：先冲商誉（至零为止），剩余按比例分摊至资产组其他资产。",
            "商誉减值不可转回！可收回金额取自I3-7 DCF测试。",
        ],
    },
    "I3-7": {
        "item_id": "I3-7-rows",
        "title": "I3-7 可收回金额测试（DCF核心100行×16列）",
        "headers": _I3_7_HEADERS,
        "field_keys": _I3_7_KEYS,
        "guidance": [
            "I3-7 可收回金额测试 编制说明",
            "",
            "DCF模型：PV=Σ(FCF_i/(1+WACC)^i) + TV/(1+WACC)^n。",
            "终值=FCF_n×(1+g)/(WACC-g)（永续增长模型）。",
            "可收回金额=MAX(公允价值-处置费用, 使用价值DCF)。",
            "需进行敏感性分析：WACC±1%/增长率±0.5%/收入±10%。",
        ],
    },
}

router = create_cycle_import_export_router(tag="i3-import-export", api_prefix="i3", specs=_I3_SPECS)
