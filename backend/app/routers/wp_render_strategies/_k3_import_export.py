"""K3 其他应付款 — 导入导出（2张动态行表: K3-2明细表/K3-3调整分录）.

科目 2241 其他应付款（贷方/负债类）。
K3-2 明细表 27 列 3 区段：基础 | 账龄 | 检查。
K3-3 调整分录汇总。
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ────────────────────────────────────────────────────────────
# K3-2 明细表（27列，3区段合并导出）
# 基础: 序号/往来对象/性质/关联关系/期初余额/本期增加(贷方)/本期减少(借方)/期末余额
# 账龄: 1年内/1-2年/2-3年/3年以上/账龄合计
# 检查: 形成原因/预计偿付时间/是否长期挂账/疑似未入账/凭证号/结论/备注
# ────────────────────────────────────────────────────────────
_K3_2_HEADERS = [
    "序号", "往来对象", "性质", "关联关系",
    "期初余额", "本期增加(贷方)", "本期减少(借方)", "期末余额",
    "1年内", "1-2年", "2-3年", "3年以上", "账龄合计",
    "形成原因", "预计偿付时间", "是否长期挂账", "疑似未入账",
    "凭证号", "结论", "备注",
    "大额标记", "关联方标记", "期后偿付金额", "期后偿付日期",
    "核查状态", "审计师评价", "备注2",
]
_K3_2_KEYS = [
    "seq", "counterparty", "nature", "relatedParty",
    "openingBalance", "increase", "decrease", "closingBalance",
    "agingLt1", "aging1to2", "aging2to3", "agingGt3", "agingTotal",
    "formationReason", "expectedPaymentTime", "isLongOutstanding", "suspectedUnrecorded",
    "voucherNo", "conclusion", "remark",
    "isLargeAmount", "isRelatedParty", "postPaymentAmt", "postPaymentDate",
    "checkStatus", "auditorEval", "remark2",
]

# ────────────────────────────────────────────────────────────
# K3-3 调整分录汇总（10列）
# ────────────────────────────────────────────────────────────
_K3_3_HEADERS = [
    "序号", "分录类型", "摘要", "科目代码", "科目名称",
    "借方金额", "贷方金额", "附注说明", "凭证号", "备注",
]
_K3_3_KEYS = [
    "seq", "entryType", "summary", "accountCode", "accountName",
    "debitAmount", "creditAmount", "noteRef", "voucherNo", "remark",
]

# ────────────────────────────────────────────────────────────
# Sheet Specs 汇总
# ────────────────────────────────────────────────────────────
_K3_SPECS: dict[str, dict[str, Any]] = {
    "K3-2": {
        "item_id": "K3-2-rows",
        "title": "K3-2 其他应付款明细表",
        "headers": _K3_2_HEADERS,
        "field_keys": _K3_2_KEYS,
        "guidance": [
            "K3-2 明细表 编制说明",
            "",
            "27列对应3区段：基础(序号/往来对象/性质/关联关系/期初/增加/减少/期末)",
            "| 账龄(1年内/1-2年/2-3年/3年以上/账龄合计)",
            "| 检查(形成原因/偿付时间/长期挂账/疑似未入账/凭证号/结论/备注/大额/关联方/期后偿付/日期/核查/评价/备注2)。",
            "",
            "负债类方向：期末 = 期初 + 增加(贷方) - 减少(借方)。",
            "账龄合计应等于期末余额。",
            "金额为数值型，单位：元。正数表示贷方余额（应付）。",
            "3年以上账龄行自动标记长期挂账风险（橙色背景）。",
        ],
    },
    "K3-3": {
        "item_id": "K3-3-rows",
        "title": "K3-3 其他应付款调整分录汇总",
        "headers": _K3_3_HEADERS,
        "field_keys": _K3_3_KEYS,
        "guidance": [
            "K3-3 调整分录 编制说明",
            "",
            "10列：序号/分录类型(AJE/RJE)/摘要/科目代码/科目名称/借方金额/贷方金额/附注说明/凭证号/备注。",
            "借贷必须平衡：∑借方 = ∑贷方。",
            "分录类型填 AJE（审计调整）或 RJE（重分类调整）。",
            "金额单位：元。",
        ],
    },
}

router = create_cycle_import_export_router(tag="k3-import-export", api_prefix="k3", specs=_K3_SPECS)
