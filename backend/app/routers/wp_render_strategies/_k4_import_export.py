"""K4 其他流动负债 — 导入导出（2张动态行表: K4-2明细表/K4-3调整分录）.

科目 2245 其他流动负债（贷方/负债类）。
K4-2 明细表 18 列 2 区段：基础(序号/项目/性质/期初/期末) | 检查(增减原因/凭证号/核查结论/备注)。
K4-3 调整分录汇总。
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ────────────────────────────────────────────────────────────
# K4-2 明细表（18列，2区段合并导出）
# 基础: 序号/项目名称/性质/期初余额/本期增加(贷方)/本期减少(借方)/期末余额
# 检查: 增减原因/凭证号/核查结论/备注/分类正确性/流动性判断/完整性/合规性/审计师评价/备注2/关联方标记/期后清理
# ────────────────────────────────────────────────────────────
_K4_2_HEADERS = [
    "序号", "项目名称", "性质", "期初余额",
    "本期增加(贷方)", "本期减少(借方)", "期末余额",
    "增减原因", "凭证号", "核查结论", "备注",
    "分类正确性", "流动性判断", "完整性", "合规性",
    "审计师评价", "备注2", "关联方标记",
]
_K4_2_KEYS = [
    "seq", "itemName", "nature", "openingBalance",
    "increase", "decrease", "closingBalance",
    "changeReason", "voucherNo", "checkConclusion", "remark",
    "classificationCorrect", "liquidityJudge", "completeness", "compliance",
    "auditorEval", "remark2", "isRelatedParty",
]

# ────────────────────────────────────────────────────────────
# K4-3 调整分录汇总（12列）
# 列集合对齐前端 K4TabAdjustment 行模型（adjustment_ie_contract.json / Task 2.2）：
#   去掉前端不存在的 noteRef/voucherNo，补 entryNo（编号）/offsetAccount（对方科目）/
#   preparedBy（编制人）/source（来源）
# ────────────────────────────────────────────────────────────
_K4_3_HEADERS = [
    "序号", "编号", "分录类型", "摘要", "科目代码", "科目名称", "对方科目",
    "借方金额", "贷方金额", "编制人", "来源", "备注",
]
_K4_3_KEYS = [
    "seq", "entryNo", "entryType", "summary", "accountCode", "accountName", "offsetAccount",
    "debitAmount", "creditAmount", "preparedBy", "source", "remark",
]

# ────────────────────────────────────────────────────────────
# Sheet Specs 汇总
# ────────────────────────────────────────────────────────────
_K4_SPECS: dict[str, dict[str, Any]] = {
    "K4-2": {
        "item_id": "K4-2-rows",
        "title": "K4-2 其他流动负债明细表",
        "headers": _K4_2_HEADERS,
        "field_keys": _K4_2_KEYS,
        "guidance": [
            "K4-2 明细表 编制说明",
            "",
            "18列对应2区段：基础(序号/项目名称/性质/期初/增加/减少/期末)",
            "| 检查(增减原因/凭证号/核查结论/备注/分类正确性/流动性/完整性/合规性/审计师评价/备注2/关联方标记)。",
            "",
            "负债类方向：期末 = 期初 + 增加(贷方) - 减少(借方)。",
            "金额为数值型，单位：元。正数表示贷方余额（负债）。",
            "分类正确性：判断该项目是否应归入其他流动负债。",
            "完整性：检查是否存在应计未计的负债项目。",
        ],
    },
    "K4-3": {
        # item_id / storage_field 对齐前端持久化键（K4TabAdjustment: ITEM_PREFIX='K4-3-adj' + '-entries'，写 remark 列）
        "item_id": "K4-3-adj-entries",
        "storage_field": "remark",
        "title": "K4-3 其他流动负债调整分录汇总",
        "headers": _K4_3_HEADERS,
        "field_keys": _K4_3_KEYS,
        "guidance": [
            "K4-3 调整分录 编制说明",
            "",
            "12列：序号/编号/分录类型(AJE/RJE)/摘要/科目代码/科目名称/对方科目/借方金额/贷方金额/编制人/来源/备注。",
            "编号形如 K4-AJE-001；来源填 手工 / K4-4 / 导入。",
            "借贷必须平衡：∑借方 = ∑贷方。",
            "分录类型填 AJE（审计调整）或 RJE（重分类调整）。",
            "金额单位：元。",
        ],
    },
}

router = create_cycle_import_export_router(tag="k4-import-export", api_prefix="k4", specs=_K4_SPECS)
