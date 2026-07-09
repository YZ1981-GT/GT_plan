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
}

router = create_cycle_import_export_router(tag="k5-import-export", api_prefix="k5", specs=_K5_SPECS)
