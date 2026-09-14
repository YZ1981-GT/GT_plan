"""G2 应收利息 — 导入导出（列结构对齐 requirements + composable field keys）.

支持：
  G2-1 审定表（keyed store，对齐 G1-1）/
  G2-2 明细表（含动态账龄列）/
  G2-3~G2-8 动态行表格

字段键与前端 composable 严格对齐，保证 round-trip。
存储统一走 checklist_responses.remark。
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ── G2-1 审定表（keyed remark store：{rowKey: cell}）──
_G2_1_HEADERS = [
    "行键", "项目", "区段",
    "期初本账数", "期初账项调整", "期末本账数", "期末账项调整", "差异分析",
]
_G2_1_KEYS = [
    "rowKey", "label", "section",
    "openingUnadjusted", "openingAdjustment", "closingUnadjusted", "closingAdjustment", "reasonAnalysis",
]
_G2_1_KEEP_KEYS = [
    "openingUnadjusted", "openingAdjustment", "closingUnadjusted", "closingAdjustment", "reasonAnalysis",
]

_G2_1_METHODS = [
    ("individual", "其中：单项计提坏账准备"),
    ("collective", "按组合计提坏账准备"),
]
_G2_1_SECTIONS = [
    ("gross", "原值"),
    ("provision", "坏账准备"),
]


def _build_g2_1_prefill():
    rows = []
    for section, section_label in _G2_1_SECTIONS:
        for method_key, method_label in _G2_1_METHODS:
            row_key = f"{section}-{method_key}"
            rows.append([
                row_key,
                method_label,
                section_label,
                0, 0, 0, 0, "",
            ])
    return rows


# ── G2-2 明细表（对齐纸质滚动核对 + 动态账龄；公式列导入后前端重算）──
_G2_2_BASE_HEADERS = [
    "序号", "投资种类", "投资项目",
    "期初余额", "期初调整数", "借方发生", "贷方发生", "账项调整",
    "结息日", "原计收项目期", "流通或期后收款情况",
    "面值/本金", "票面利率(%)", "计息起始日", "计息截止日", "已收利息",
    "减值阶段", "备注", "索引",
]
_G2_2_BASE_KEYS = [
    "seq", "investType", "investTarget",
    "openingUnadjusted", "openingAdjustment", "debit", "credit", "closingAdjustment",
    "interestDueDate", "accrualPeriod", "collectionStatus",
    "faceValue", "couponRate", "accrualStart", "accrualEnd", "receivedInterest",
    "eclStage", "remark", "indexRef",
]
# 无 aging 时的全量列（含公式列，便于导出可读）
_G2_2_HEADERS = [
    "序号", "投资种类", "投资项目",
    "期初余额", "期初调整数", "期初余额审定数",
    "借方发生", "贷方发生", "期末余额", "账项调整", "应收利息余额审定数",
    "结息日", "原计收项目期", "流通或期后收款情况",
    "面值/本金", "票面利率(%)", "计息起始日", "计息截止日", "计息天数",
    "应计利息", "已收利息", "测算期末应收",
    "减值阶段", "备注", "索引",
]
_G2_2_KEYS = [
    "seq", "investType", "investTarget",
    "openingUnadjusted", "openingAdjustment", "openingAudited",
    "debit", "credit", "closingUnadjusted", "closingAdjustment", "closingAudited",
    "interestDueDate", "accrualPeriod", "collectionStatus",
    "faceValue", "couponRate", "accrualStart", "accrualEnd", "accruedDays",
    "accruedInterest", "receivedInterest", "netReceivable",
    "eclStage", "remark", "indexRef",
]

# ── G2-3 坏账准备明细（滚动态：单项 + 组合账龄）──
_G2_3_HEADERS = [
    "分类", "账龄键", "项目",
    "期初未审数", "期初账项调整",
    "本期计提", "其他增加",
    "转回", "转销", "其他减少",
    "期末账项调整", "原因",
]
_G2_3_KEYS = [
    "category", "agingKey", "item",
    "openingUnadjusted", "openingAdjustment",
    "provisionIncrease", "otherIncrease",
    "reversal", "writeOff", "otherDecrease",
    "closingAdjustment", "reason",
]

# ── G2-4 调整分录（对齐 D4-4 / Excel 列结构）──
_G2_4_HEADERS = [
    "调整事项说明", "类别", "报表项目", "科目名称", "科目编码", "附注项目",
    "借方调整金额", "贷方调整金额", "索引", "备注",
]
_G2_4_KEYS = [
    "description", "category", "reportItem", "accountName", "accountCode", "noteItem",
    "debitAmount", "creditAmount", "indexRef", "remark",
]

# ── G2-5 利息测算表（对齐 Excel + useG2InterestCalc 存储字段；公式列导入后前端重算）──
_G2_5_HEADERS = [
    "序号", "投资项目", "账面金额①", "票面年利率②(%)",
    "计息开始日期", "计息结束日期", "计息天数③",
    "应计利息④", "其中：已到期可收取⑤", "已计利息⑥", "差异⑦",
    "差异原因", "实际利率法(进工具余额)", "备注", "来源明细ID",
]
_G2_5_KEYS = [
    "seq", "investTarget", "faceValue", "couponRate",
    "accrualStart", "accrualEnd", "accruedDays",
    "calculatedInterest", "maturedCollectible", "companyAccrual", "variance",
    "varianceReason", "eirInInstrument", "remark", "sourceDetailId",
]

# ── G2-6 长期未收回检查（对齐 Excel 13 列）──
_G2_6_HEADERS = [
    "序号", "债务人名称", "期初余额", "本期借方发生额", "本期贷方发生额",
    "账龄", "经济业务说明", "未收回或未结转的原因", "是否无法收回",
    "处理计划", "审定余额", "期后收款金额", "备注",
]
_G2_6_KEYS = [
    "seq", "debtorName", "openingBalance", "periodDebit", "periodCredit",
    "aging", "businessDesc", "unrecoveredReason", "isUncollectible",
    "actionPlan", "auditedBalance", "postPeriodCollection", "remark",
]

# ── G2-7 坏账准备测算（单项 + 账龄组合扁平导出）──
_G2_7_HEADERS = [
    "区段", "组合名称", "账龄段键", "账龄/标的",
    "审定余额", "损失率", "应计提", "账面准备", "差异", "计提依据", "索引",
]
_G2_7_KEYS = [
    "section", "groupName", "segmentKey", "label",
    "auditedBalance", "lossRate", "expectedProvision", "bookBalance", "difference", "basis", "indexRef",
]

# ── G2-8 凭证检查表──
_G2_8_HEADERS = [
    "序号", "检查区", "摘要", "对方科目", "金额", "凭证日期", "凭证编号",
    "投资标的", "面值", "利率(%)", "计息天数", "测算利息",
    "收款银行", "收款日期", "是否到期收回", "逾期天数",
    "差异", "审计结论", "附件", "备注", "抽凭来源",
]
_G2_8_KEYS = [
    "seq", "checkZone", "summary", "counterAccount", "amount", "voucherDate", "voucherNo",
    "investTarget", "faceValue", "rate", "accruedDays", "calculatedInterest",
    "receivingBank", "receiptDate", "isOnTimeRecovery", "overdueDays",
    "variance", "auditConclusion", "attachment", "remark", "sampleSource",
]


_G2_SPECS: dict[str, dict[str, Any]] = {
    "G2-1": {
        "item_id": "G2-1-rows",
        "title": "G2-1 应收利息审定表",
        "headers": _G2_1_HEADERS,
        "field_keys": _G2_1_KEYS,
        "storage_field": "remark",
        "keyed_by": "rowKey",
        "keep_keys": _G2_1_KEEP_KEYS,
        "template_prefill": _build_g2_1_prefill(),
        "guidance": [
            "G2-1 审定表 编制说明",
            "",
            "行键(rowKey)须与模板一致，勿改动；仅填写本账数/账项调整/差异分析。",
            "区段：原值(gross) / 坏账准备(provision)；净值由前端自动=原值−坏账。",
            "方法：individual(单项计提) / collective(按组合计提)。",
            "审定=本账+账项调整；|变动率|>30% 时差异分析必填。",
        ],
    },
    "G2-2": {
        "item_id": "G2-2-detail-rows",
        "title": "G2-2 应收利息明细表（含账龄）",
        "headers": _G2_2_HEADERS,
        "field_keys": _G2_2_KEYS,
        "storage_field": "remark",
        "aging": {
            "subject": "G2",
            "periods": ["prior", "audited"],
            "base_headers": _G2_2_BASE_HEADERS,
            "base_field_keys": _G2_2_BASE_KEYS,
        },
        "guidance": [
            "G2-2 明细表 编制说明（对齐纸质底稿滚动核对）",
            "",
            "期初审定 = 期初余额 + 期初调整数；期末余额 = 期初审定 + 借方 − 贷方；期末审定 = 期末余额 + 账项调整。",
            "公式列（期初/期末审定、计息天数/应计利息等）导入后由前端自动重算，模板仅需填基础列。",
            "账龄列为动态列（期初审定/期末审定），口径支持「3年段 / 5年段 / 自定义」枚举（对齐 F1-1）。",
            "结息日、原计收项目期、期后收款情况按纸质底稿填列；减值阶段填 Stage1/Stage2/Stage3。",
        ],
    },
    "G2-3": {
        "item_id": "G2-3-bad-debt-rows",
        "title": "G2-3 坏账准备明细表（滚动态）",
        "headers": _G2_3_HEADERS,
        "field_keys": _G2_3_KEYS,
        "storage_field": "remark",
        "guidance": [
            "G2-3 坏账准备明细 编制说明",
            "",
            "分类填 individual(单项) 或 portfolio(组合)；组合行账龄键填 within1/y1to2/… 与项目账龄配置一致。",
            "期初审定=期初未审+账项调整；期末未审=期初审定+计提+其他增加−转回−转销−其他减少；期末审定=期末未审+账项调整。",
            "公式列由前端自动重算；ECL 三阶段测算请使用 G2-7。",
        ],
    },
    "G2-4": {
        "item_id": "G2-4-rows",
        "title": "G2-4 应收利息调整分录汇总",
        "headers": _G2_4_HEADERS,
        "field_keys": _G2_4_KEYS,
        "storage_field": "remark",
        "guidance": [
            "G2-4 调整分录 编制说明（对齐 D4-4）",
            "",
            "类别填：账项调整 / 报表调整 / 其他（账项调整→AJE，报表调整→RJE）。",
            "仅列示与应收利息（1132）相关的审计调整；借贷合计须平衡。",
            "可从调整分录模块同步；确认后回写 G2-1 审定表期末账项调整。",
        ],
    },
    "G2-5": {
        "item_id": "G2-5-interest-calc-rows",
        "title": "G2-5 应收利息测算表",
        "headers": _G2_5_HEADERS,
        "field_keys": _G2_5_KEYS,
        "storage_field": "remark",
        "guidance": [
            "G2-5 应收利息测算 编制说明（对齐 Excel）",
            "",
            "应计利息④ = 账面金额① × 票面年利率② × 计息天数③ / 365（365天基准）。",
            "差异⑦ = 应计利息④ − 已计利息⑥；|差异|>100 须填差异原因。",
            "已到期可收取⑤对应报表应收利息口径；实际利率法列填 是/否/true/false/1/0。",
            "勾选实际利率法后⑤不计入科目1132勾稽（利息进金融工具账面余额）。",
            "计息天数③、应计利息④、差异⑦为公式列，导入后由前端按起止日重算。",
        ],
    },
    "G2-6": {
        "item_id": "G2-6-overdue-rows",
        "title": "G2-6 长期未收回款项检查表",
        "headers": _G2_6_HEADERS,
        "field_keys": _G2_6_KEYS,
        "storage_field": "remark",
        "guidance": [
            "G2-6 长期未收回检查 编制说明",
            "",
            "期末余额 = 期初余额 + 本期借方 − 本期贷方（前端自动计算，无需导入）。",
            "账龄填项目账龄枚举标签（如 1年以内 / 1-2年 / …），可表内切换 3年段/5年段/自定义。",
            "是否无法收回填：是 / 否 / 部分。",
            "审定余额、期后收款金额用于可收回性验证；重大无法收回衔接 G2-3/G2-7。",
        ],
    },
    "G2-7": {
        "item_id": "G2-7-flat-export",
        "title": "G2-7 坏账准备测算（单项/账龄组合/其他组合）",
        "headers": _G2_7_HEADERS,
        "field_keys": _G2_7_KEYS,
        "storage_field": "remark",
        "guidance": [
            "G2-7 坏账准备测算 编制说明（对齐纸质底稿）",
            "",
            "区段填：individual(单项) / aging(账龄组合) / other(其他组合)。",
            "应计提 = 审定余额 × 损失率；差异 = 应计提 − 账面准备（公式列导入后前端重算）。",
            "账龄段支持 3年段/5年段/自定义枚举；账龄组合行随口径自动增减。",
            "差异可在前端推送至 G2-4 调整分录。",
            "导入扁平表后前端自动还原至单项/账龄组合/其他组合存储。",
        ],
    },
    "G2-8": {
        "item_id": "G2-8-rows",
        "title": "G2-8 凭证检查表",
        "headers": _G2_8_HEADERS,
        "field_keys": _G2_8_KEYS,
        "storage_field": "remark",
        "guidance": [
            "G2-8 凭证检查表 编制说明",
            "",
            "检查区列填 debit(借方/利息确认) 或 credit(贷方/利息收回)。",
            "借方区：测算利息 = 面值 × 利率/100 × 计息天数/365。",
        ],
    },
}

router = create_cycle_import_export_router(
    tag="g2-import-export",
    api_prefix="g2",
    specs=_G2_SPECS,
    storage_field="remark",
)
