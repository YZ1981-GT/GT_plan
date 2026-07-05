"""G2 应收利息 — 导入导出（列结构对齐 requirements + composable field keys）.

支持 7 张动态行表格：
  G2-2 明细表(16列) / G2-3 坏账准备明细(20列) / G2-4 调整分录 /
  G2-5 利息测算表(11列) / G2-6 长期未收回检查(13列) /
  G2-7 坏账准备测算(18列/2区段) / G2-8 凭证检查表(21列/借方+贷方)

字段键与前端 composable（useG2Detail/useG2InterestCalc/... 的行接口）严格对齐，保证 round-trip。
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ── G2-2 明细表（16列）──
_G2_2_HEADERS = [
    "序号", "投资标的", "投资类型", "面值/本金", "票面利率(%)",
    "计息起始日", "计息截止日", "计息天数", "应计利息", "已收利息",
    "期末应收", "企业账面值", "差异", "减值阶段", "备注", "索引",
]
_G2_2_KEYS = [
    "seq", "investTarget", "investType", "faceValue", "couponRate",
    "accrualStart", "accrualEnd", "accruedDays", "accruedInterest", "receivedInterest",
    "netReceivable", "bookValue", "variance", "eclStage", "remark", "indexRef",
]

# ── G2-3 坏账准备明细（20列）──
_G2_3_HEADERS = [
    "序号", "投资标的", "期末余额", "信用等级", "是否显著增加",
    "是否已减值", "划分阶段", "上期阶段", "变动说明",
    "12个月PD", "存续期PD", "适用PD", "LGD", "EAD",
    "ECL金额", "企业计提", "差异", "转移方向", "测算结论", "备注",
]
_G2_3_KEYS = [
    "seq", "investTarget", "closingBalance", "creditRating", "significantIncrease",
    "isImpaired", "determinedStage", "previousStage", "stageChangeNote",
    "pd12Month", "pdLifetime", "applicablePD", "lgd", "ead",
    "eclAmount", "companyProvision", "eclVariance", "transferDirection", "conclusion", "remark",
]

# ── G2-4 调整分录（借贷平衡）──
_G2_4_HEADERS = [
    "序号", "分录类型", "日期", "摘要", "科目代码", "科目名称",
    "借方金额", "贷方金额", "编制人", "备注",
]
_G2_4_KEYS = [
    "seq", "entryType", "date", "summary", "accountCode", "accountName",
    "debit", "credit", "preparer", "remark",
]

# ── G2-5 利息测算表（11列）──
_G2_5_HEADERS = [
    "序号", "投资标的", "面值/本金", "票面利率(%)", "计息天数",
    "测算应收利息", "企业计提利息", "差异", "利息确认日期", "审计结论", "备注",
]
_G2_5_KEYS = [
    "seq", "investTarget", "faceValue", "couponRate", "accruedDays",
    "calculatedInterest", "companyInterest", "variance", "confirmDate", "auditConclusion", "remark",
]

# ── G2-6 长期未收回检查（13列）──
_G2_6_HEADERS = [
    "序号", "投资标的", "应收金额", "约定回收日", "逾期天数",
    "逾期原因", "债务人信用状况", "催收措施", "预计可收回性",
    "是否需阶段转移", "风险等级", "审计建议", "备注",
]
_G2_6_KEYS = [
    "seq", "investTarget", "receivableAmount", "agreedRecoveryDate", "overdueDays",
    "overdueReason", "debtorCreditStatus", "collectionMeasures", "recoverability",
    "needStageTransfer", "riskLevel", "auditSuggestion", "remark",
]

# ── G2-7 坏账准备测算（18列/2区段）──
_G2_7_HEADERS = [
    # 阶段划分区段(9)
    "序号", "投资标的", "期末余额", "信用风险等级", "是否信用风险显著增加",
    "是否已发生减值", "划分阶段", "上期阶段", "阶段变动说明",
    # ECL测算区段(9)
    "12个月PD", "整个存续期PD", "适用PD", "LGD", "EAD",
    "ECL金额", "企业计提", "差异", "测算结论",
]
_G2_7_KEYS = [
    "seq", "investTarget", "closingBalance", "creditRating", "significantIncrease",
    "isImpaired", "determinedStage", "previousStage", "stageChangeNote",
    "pd12Month", "pdLifetime", "applicablePD", "lgd", "ead",
    "eclAmount", "companyProvision", "eclVariance", "conclusion",
]

# ── G2-8 凭证检查表（21列，借方14列+贷方12列合并为宽表）──
_G2_8_HEADERS = [
    "序号", "检查区", "摘要", "对方科目", "金额", "凭证日期", "凭证编号",
    # 借方独有列
    "投资标的", "面值", "利率(%)", "计息天数", "测算利息",
    # 贷方独有列
    "收款银行", "收款日期", "是否到期收回", "逾期天数",
    # 公共列
    "差异", "审计结论", "附件", "备注", "抽凭来源",
]
_G2_8_KEYS = [
    "seq", "checkZone", "summary", "counterAccount", "amount", "voucherDate", "voucherNo",
    "investTarget", "faceValue", "rate", "accruedDays", "calculatedInterest",
    "receivingBank", "receiptDate", "isOnTimeRecovery", "overdueDays",
    "variance", "auditConclusion", "attachment", "remark", "sampleSource",
]


_G2_SPECS: dict[str, dict[str, Any]] = {
    "G2-2": {
        "item_id": "G2-2-rows",
        "title": "G2-2 应收利息明细表（16列）",
        "headers": _G2_2_HEADERS,
        "field_keys": _G2_2_KEYS,
        "guidance": [
            "G2-2 明细表 编制说明",
            "",
            "16列对应 HTML 底稿明细表，公式列（计息天数/应计利息/期末应收/差异）导入后前端自动重算。",
            "计息天数 = 截止日 - 起始日（天）；应计利息 = 面值 × 利率/100 × 天数/365。",
            "期末应收 = 应计利息 - 已收利息；差异 = 期末应收 - 企业账面值。",
            "减值阶段填：Stage1 / Stage2 / Stage3。",
        ],
    },
    "G2-3": {
        "item_id": "G2-3-rows",
        "title": "G2-3 坏账准备明细表（ECL三阶段）",
        "headers": _G2_3_HEADERS,
        "field_keys": _G2_3_KEYS,
        "guidance": [
            "G2-3 坏账准备明细 编制说明",
            "",
            "划分阶段公式：已减值→Stage3；信用风险显著增加→Stage2；否则→Stage1。",
            "适用PD：Stage1用12个月PD，Stage2/3用整个存续期PD。",
            "ECL金额 = EAD × 适用PD × LGD；差异 = ECL金额 - 企业计提。",
        ],
    },
    "G2-4": {
        "item_id": "G2-4-rows",
        "title": "G2-4 应收利息调整分录",
        "headers": _G2_4_HEADERS,
        "field_keys": _G2_4_KEYS,
        "guidance": [
            "G2-4 调整分录 编制说明",
            "",
            "分录类型填 AJE 或 RJE；每张凭证借贷方金额必须相等。",
        ],
    },
    "G2-5": {
        "item_id": "G2-5-rows",
        "title": "G2-5 利息测算表（11列）",
        "headers": _G2_5_HEADERS,
        "field_keys": _G2_5_KEYS,
        "guidance": [
            "G2-5 利息测算 编制说明",
            "",
            "测算应收利息 = 面值 × 票面利率/100 × 计息天数/365（注意是365天基准）。",
            "差异 = 测算应收利息 - 企业计提利息；|差异|>100 前端橙色高亮。",
        ],
    },
    "G2-6": {
        "item_id": "G2-6-rows",
        "title": "G2-6 长期未收回检查表（13列）",
        "headers": _G2_6_HEADERS,
        "field_keys": _G2_6_KEYS,
        "guidance": [
            "G2-6 长期未收回检查 编制说明",
            "",
            "逾期天数 = MAX(0, 当前日 - 约定回收日)。",
            "逾期>180天→建议Stage3，>90天→建议Stage2。",
            "预计可收回性：全额可收回/部分可收回/很可能无法收回/无法收回。",
            "风险等级：低/中/高/极高。",
        ],
    },
    "G2-7": {
        "item_id": "G2-7-rows",
        "title": "G2-7 坏账准备测算（18列/2区段Tab）",
        "headers": _G2_7_HEADERS,
        "field_keys": _G2_7_KEYS,
        "guidance": [
            "G2-7 坏账准备测算 编制说明",
            "",
            "18列拆为2区段Tab：阶段划分(9列) + ECL测算(9列)。",
            "划分阶段逻辑：已减值→Stage3；信用风险显著增加→Stage2；否则→Stage1。",
            "适用PD = Stage1用12个月PD / Stage2/3用整个存续期PD。",
            "ECL金额 = EAD × 适用PD × LGD；差异 = ECL金额 - 企业计提。",
            "|差异|/企业计提>10% 前端橙色高亮。",
        ],
    },
    "G2-8": {
        "item_id": "G2-8-rows",
        "title": "G2-8 凭证检查表（借方/贷方区块，21列）",
        "headers": _G2_8_HEADERS,
        "field_keys": _G2_8_KEYS,
        "guidance": [
            "G2-8 凭证检查表 编制说明",
            "",
            "借方/贷方分区块：检查区列填 debit(借方/利息确认) 或 credit(贷方/利息收回)。",
            "借方区：测算利息 = 面值 × 利率/100 × 计息天数/365；差异 = 测算利息 - 金额。",
            "贷方区：逾期天数 = MAX(0, 当前日 - 约定日)。",
            "可通过抽凭引擎自动填入样本（抽凭来源列标注）。",
        ],
    },
}

router = create_cycle_import_export_router(tag="g2-import-export", api_prefix="g2", specs=_G2_SPECS)
