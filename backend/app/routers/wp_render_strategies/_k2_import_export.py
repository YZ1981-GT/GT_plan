"""K2 其他流动资产 — 导入导出（3张动态行表: K2-2/K2-4/K2-5）."""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ────────────────────────────────────────────────────────────
# K2-2 明细表（18列）
# ────────────────────────────────────────────────────────────
_K2_2_HEADERS = [
    "序号", "项目名称", "性质", "期初余额", "本期增加", "本期减少",
    "期末余额", "增加原因", "减少原因", "凭证号", "金额是否准确",
    "分类是否恰当", "是否仍为流动", "可回收性", "核查结论", "备注",
    "相关合同", "审计师评价",
]
_K2_2_KEYS = [
    "seq", "projectName", "nature", "openingBalance", "increase", "decrease",
    "closingBalance", "increaseReason", "decreaseReason", "voucherNo", "amountAccurate",
    "classificationProper", "stillCurrent", "recoverability", "checkConclusion", "remark",
    "relatedContract", "auditorEval",
]

# ────────────────────────────────────────────────────────────
# K2-4 合同取得成本明细表（23列）
# ────────────────────────────────────────────────────────────
_K2_4_HEADERS = [
    "合同编号", "客户名称", "合同金额", "取得成本类型", "取得成本金额",
    "是否增量成本", "预期可收回", "与合同直接相关", "是否资本化",
    "期初余额", "本期增加", "本期摊销", "期末余额",
    "摊销方法", "摊销期（月）", "起始日期", "到期日期",
    "凭证号", "核查结论", "备注",
    "关联K2-5行号", "差异金额", "审计师评价",
]
_K2_4_KEYS = [
    "contractNo", "customerName", "contractAmount", "costType", "costAmount",
    "isIncremental", "expectedRecoverable", "directlyRelated", "isCapitalized",
    "openingBalance", "increase", "amortization", "closingBalance",
    "amortMethod", "amortPeriodMonths", "startDate", "endDate",
    "voucherNo", "checkConclusion", "remark",
    "linkedK25Row", "varianceAmount", "auditorEval",
]

# ────────────────────────────────────────────────────────────
# K2-5 摊销测算表（28列）
# ────────────────────────────────────────────────────────────
_K2_5_HEADERS = [
    "合同编号", "客户名称", "取得成本金额", "摊销方法", "摊销期（月）",
    "起始日期", "到期日期", "已摊销期数", "剩余期数",
    "本期应摊期数", "本期履约进度", "上期履约进度",
    "本期测算摊销", "累计摊销", "摊余成本",
    "企业本期摊销", "差异", "差异率",
    "是否超重要性", "结论", "备注",
    "日均摊销", "年度摊销预算", "实际vs预算差异",
    "调整建议", "关联K2-4行号", "凭证号", "审计师评价",
]
_K2_5_KEYS = [
    "contractNo", "customerName", "costAmount", "amortMethod", "amortPeriodMonths",
    "startDate", "endDate", "elapsedPeriods", "remainingPeriods",
    "currentPeriods", "currentProgress", "priorProgress",
    "calculatedAmort", "accumulatedAmort", "amortizedBalance",
    "bookedAmort", "variance", "varianceRate",
    "exceedsMateriality", "conclusion", "remark",
    "dailyAmort", "annualBudget", "budgetVariance",
    "adjustSuggestion", "linkedK24Row", "voucherNo", "auditorEval",
]

# ────────────────────────────────────────────────────────────
# K2-3 调整分录汇总（8列，借贷科目分列 —— 与其余循环单科目行不同构）
# 列集合对齐前端 K2TabAdjustment 行模型（adjustment_ie_contract.json / Task 2.4）：
#   借方科目 / 贷方科目各一列（debitAccount / creditAccount 均为文本，不进数值白名单）；行模型无 remark 列
# ────────────────────────────────────────────────────────────
_K2_3_HEADERS = [
    "序号", "分录类型", "摘要", "借方科目", "借方金额",
    "贷方科目", "贷方金额", "编制人",
]
_K2_3_KEYS = [
    "seq", "entryType", "summary", "debitAccount", "debitAmount",
    "creditAccount", "creditAmount", "preparedBy",
]

# ────────────────────────────────────────────────────────────
# Sheet Specs 汇总
# ────────────────────────────────────────────────────────────
_K2_SPECS: dict[str, dict[str, Any]] = {
    "K2-2": {
        "item_id": "K2-2-rows",
        "title": "K2-2 其他流动资产明细表",
        "headers": _K2_2_HEADERS,
        "field_keys": _K2_2_KEYS,
        "guidance": [
            "K2-2 明细表 编制说明",
            "",
            "18列对应：序号/项目名称/性质/期初余额/本期增加/本期减少/期末余额/",
            "增加原因/减少原因/凭证号/金额是否准确/分类是否恰当/是否仍为流动/可回收性/核查结论/备注/相关合同/审计师评价。",
            "期末余额应等于期初+增加-减少（资产类三角勾稽）。",
            "金额为数值型，单位：元。",
        ],
    },
    "K2-3": {
        # item_id / storage_field 对齐前端持久化键（K2TabAdjustment: ITEM_PREFIX='K2-3-adj' + '-entries'，写 remark 列）
        "item_id": "K2-3-adj-entries",
        "storage_field": "remark",
        "title": "K2-3 其他流动资产调整分录汇总",
        "headers": _K2_3_HEADERS,
        "field_keys": _K2_3_KEYS,
        "guidance": [
            "K2-3 调整分录 编制说明",
            "",
            "8列：序号/分录类型(AJE/RJE)/摘要/借方科目/借方金额/贷方科目/贷方金额/编制人。",
            "本表为借贷科目分列结构：同一行同时记录借方科目与贷方科目。",
            "借贷必须平衡：∑借方金额 = ∑贷方金额。",
            "分录类型填 AJE（审计调整）或 RJE（重分类调整）。",
            "金额单位：元。",
        ],
    },
    "K2-4": {
        "item_id": "K2-4-rows",
        "title": "K2-4 合同取得成本明细表",
        "headers": _K2_4_HEADERS,
        "field_keys": _K2_4_KEYS,
        "guidance": [
            "K2-4 合同取得成本明细表 编制说明",
            "",
            "23列：合同信息(编号/客户/金额/类型/成本金额) + 资本化判断(增量/可收回/相关/结论) +",
            "摊销信息(期初/增加/摊销/期末) + 检查(方法/期限/起止日/凭证/结论/备注/关联/差异/评价)。",
            "资本化条件（CAS14）：增量成本 + 预期可收回 + 与合同直接相关。",
            "期末余额=期初+增加-摊销。金额单位：元。",
        ],
    },
    "K2-5": {
        "item_id": "K2-5-rows",
        "title": "K2-5 摊销测算表",
        "headers": _K2_5_HEADERS,
        "field_keys": _K2_5_KEYS,
        "guidance": [
            "K2-5 摊销测算表 编制说明",
            "",
            "28列：基础(合同/客户/成本/方法/期限/起止日/已摊/剩余) +",
            "测算(本期期数/本期进度/上期进度/测算摊销/累计/摊余) +",
            "比较(企业摊销/差异/差异率/超重要性/结论/备注) +",
            "辅助(日均/年度预算/预算差异/调整建议/关联/凭证/评价)。",
            "直线法：本期摊销 = 取得成本 / 总期数 × 本期期数。",
            "进度法：本期摊销 = 取得成本 × (本期进度 - 上期进度)。",
            "差异 = 测算摊销 - 企业摊销。金额单位：元。",
        ],
    },
}

router = create_cycle_import_export_router(tag="k2-import-export", api_prefix="k2", specs=_K2_SPECS)
