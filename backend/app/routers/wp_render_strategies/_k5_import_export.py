"""K5 预计负债 — 导入导出（2张动态行表: K5-2明细表/K5-3调整分录）.

科目 2701 预计负债（贷方/负债类）。
K5-2 明细表 23 列 3 区段：基础(序号/项目/类型/现时义务描述/期初/期末) | 判断(可能性级别/是否确认/确认依据/计量方法) | 估计(最佳估计数/上限/下限/期望值/凭证/结论)。
K5-3 调整分录汇总。
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ────────────────────────────────────────────────────────────
# K5-2 明细表（23列，3区段合并导出）
# 基础: 序号/项目名称/类型/现时义务描述/期初余额/期末余额
# 判断: 可能性级别/是否确认/确认依据/计量方法/最佳估计数/上限/下限/期望值
# 估计: 本期计提/本期转销/凭证号/结论/备注/关联方标记/审计师评价/弃置标记/质保标记
# ────────────────────────────────────────────────────────────
_K5_2_HEADERS = [
    "序号", "项目名称", "类型", "现时义务描述", "期初余额", "期末余额",
    "可能性级别", "是否确认", "确认依据", "计量方法",
    "最佳估计数", "上限", "下限", "期望值",
    "本期计提", "本期转销", "凭证号", "结论", "备注",
    "关联方标记", "审计师评价", "弃置标记", "质保标记",
]
_K5_2_KEYS = [
    "seq", "itemName", "provisionType", "obligationDesc", "openingBalance", "closingBalance",
    "likelihoodLevel", "isRecognized", "recognitionBasis", "measureMethod",
    "bestEstimate", "upperLimit", "lowerLimit", "expectedValue",
    "currentProvision", "currentRelease", "voucherNo", "conclusion", "remark",
    "isRelatedParty", "auditorEval", "isDecommission", "isWarranty",
]

# ────────────────────────────────────────────────────────────
# K5-3 调整分录汇总（10列）
# ────────────────────────────────────────────────────────────
_K5_3_HEADERS = [
    "序号", "分录类型", "摘要", "科目代码", "科目名称",
    "借方金额", "贷方金额", "附注说明", "凭证号", "备注",
]
_K5_3_KEYS = [
    "seq", "entryType", "summary", "accountCode", "accountName",
    "debitAmount", "creditAmount", "noteRef", "voucherNo", "remark",
]

# ────────────────────────────────────────────────────────────
# K5-4 产品质量保修 — 重新测算主表（11列，负债类期末=期初+计提-使用）
# ────────────────────────────────────────────────────────────
_K5_4_HEADERS = [
    "产品类别", "计提基数(收入)", "计提比例", "应计提金额", "账面已计提",
    "差异金额", "差异原因", "期初", "本期计提", "本期使用", "期末",
]
_K5_4_KEYS = [
    "productName", "revenue", "warrantyRate", "estimatedExpense", "bookProvision",
    "variance", "varianceReason", "beginBalance", "periodProvision", "periodUsed", "endBalance",
]

# ────────────────────────────────────────────────────────────
# K5-5 弃置费用 — 现值折现测算主表（11列）
# 现值/利息调整/期末为公式列，导入后前端重算
# ────────────────────────────────────────────────────────────
_K5_5_HEADERS = [
    "资产名称", "预计弃置支出", "年数", "折现率", "现值",
    "期初", "增加", "利息调整", "期末", "结论", "备注",
]
_K5_5_KEYS = [
    "assetName", "futureExpense", "expectedYears", "discountRate", "presentValue",
    "beginBalance", "periodIncrease", "interestAdjustment", "endBalance", "conclusion", "remark",
]

# ────────────────────────────────────────────────────────────
# K5-6 未决诉讼检查（13列，含我方角色/律师函状态）
# 差异金额为公式列（应赔−已计提），导入后前端重算
# ────────────────────────────────────────────────────────────
_K5_6_HEADERS = [
    "案件名称", "涉案金额", "我方角色", "诉讼阶段", "律师意见",
    "败诉可能性", "应赔/预计损失", "已计提预计负债", "差异金额", "差异原因",
    "律师函状态", "索引号", "备注",
]
_K5_6_KEYS = [
    "caseName", "amount", "partyRole", "stage", "lawyerOpinion",
    "lossLikelihood", "estimatedLoss", "bookProvision", "variance", "varianceReason",
    "lawyerLetterStatus", "indexRef", "remark",
]

# ────────────────────────────────────────────────────────────
# Sheet Specs 汇总
# ────────────────────────────────────────────────────────────
_K5_SPECS: dict[str, dict[str, Any]] = {
    "K5-2": {
        "item_id": "K5-2-rows",
        "title": "K5-2 预计负债明细表",
        "headers": _K5_2_HEADERS,
        "field_keys": _K5_2_KEYS,
        "guidance": [
            "K5-2 明细表 编制说明",
            "",
            "23列对应3区段：基础(序号/项目名称/类型/现时义务描述/期初/期末)",
            "| 判断(可能性级别/是否确认/确认依据/计量方法/最佳估计数/上限/下限/期望值)",
            "| 估计(本期计提/本期转销/凭证号/结论/备注/关联方/审计师评价/弃置标记/质保标记)。",
            "",
            "负债类方向：期末 = 期初 + 计提(增加) - 转销(减少)。",
            "金额为数值型，单位：元。正数表示贷方余额（预计负债）。",
            "可能性级别：很可能/可能/极小可能（CAS13三级）。",
            "计量方法：单值/区间中值/期望值加权。",
            "类型：产品质量保证/未决诉讼/亏损合同/重组义务/弃置义务/其他。",
        ],
    },
    "K5-3": {
        "item_id": "K5-3-rows",
        "title": "K5-3 预计负债调整分录汇总",
        "headers": _K5_3_HEADERS,
        "field_keys": _K5_3_KEYS,
        "guidance": [
            "K5-3 调整分录 编制说明",
            "",
            "10列：序号/分录类型(AJE/RJE)/摘要/科目代码/科目名称/借方金额/贷方金额/附注说明/凭证号/备注。",
            "借贷必须平衡：∑借方 = ∑贷方。",
            "分录类型填 AJE（审计调整）或 RJE（重分类调整）。",
            "金额单位：元。",
        ],
    },
    "K5-4": {
        "item_id": "K5-4-rows",
        "storage_field": "remark",
        "title": "K5-4 产品质量保修重新测算",
        "headers": _K5_4_HEADERS,
        "field_keys": _K5_4_KEYS,
        "guidance": [
            "K5-4 产品质量保修检查表（重新测算主表）编制说明",
            "",
            "11列：产品类别/计提基数(收入)/计提比例/应计提金额/账面已计提/差异金额/差异原因/期初/本期计提/本期使用/期末。",
            "应计提金额 = 计提基数 × 计提比例；差异金额 = 应计提 − 账面已计提（导入后前端重算）。",
            "负债类期末 = 期初 + 本期计提 − 本期使用；金额单位：元。",
            "本表仅导入(三)重新测算主表；政策/历史保修率/预计发生时间等区块请在页面直接编辑。",
        ],
    },
    "K5-5": {
        "item_id": "K5-5-rows",
        "storage_field": "remark",
        "title": "K5-5 弃置费用现值折现测算",
        "headers": _K5_5_HEADERS,
        "field_keys": _K5_5_KEYS,
        "guidance": [
            "K5-5 弃置费用检查表（现值折现测算主表）编制说明",
            "",
            "11列：资产名称/预计弃置支出/年数/折现率/现值/期初/增加/利息调整/期末/结论/备注。",
            "现值 = 预计弃置支出 /(1+折现率)^年数；利息调整 = 期初 × 折现率；期末 = 期初 + 增加 + 利息调整（导入后前端重算）。",
            "折现率填小数（如0.05表示5%）；金额单位：元。",
            "本表仅导入(三)现值折现测算主表；完整性/关键假设/借贷方分析等区块请在页面直接编辑。",
        ],
    },
    "K5-6": {
        "item_id": "K5-6-rows",
        "storage_field": "remark",
        "title": "K5-6 未决诉讼检查",
        "headers": _K5_6_HEADERS,
        "field_keys": _K5_6_KEYS,
        "guidance": [
            "K5-6 未决诉讼检查表 编制说明",
            "",
            "13列：案件名称/涉案金额/我方角色/诉讼阶段/律师意见/败诉可能性/应赔预计损失/已计提预计负债/差异金额/差异原因/律师函状态/索引号/备注。",
            "我方角色：defendant(被告)/plaintiff(原告)/third_party(第三人)。",
            "败诉可能性：very_likely(很可能>50%→确认)/possible(可能≤50%→披露)/remote(极小可能→不处理)。",
            "律师函状态：not_sent(未发)/sent(已发函)/replied(已回函)。",
            "差异金额 = 应赔预计损失 − 已计提预计负债（导入后前端重算）；金额单位：元。",
        ],
    },
}

router = create_cycle_import_export_router(tag="k5-import-export", api_prefix="k5", specs=_K5_SPECS)
