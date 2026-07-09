"""K7 递延收益 — 导入导出（2张动态行表: K7-2明细表/K7-3调整分录）.

科目 2401 递延收益（贷方/负债类）。
K7-2 明细表 32 列 3 区段：基础 | 分摊 | 检查。
K7-3 调整分录汇总。
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ────────────────────────────────────────────────────────────
# K7-2 明细表（32列，3区段合并导出）
# 基础: 序号/补助项目/批文号/补助类型/与资产或收益相关/收到金额/收到日期
# 分摊: 分摊方法/分摊期(月)/期初余额/本期收到/本期分摊/期末余额
# 检查: 计入科目/凭证号/分摊起止/累计分摊/剩余期限/结论/备注
# ────────────────────────────────────────────────────────────
_K7_2_HEADERS = [
    "序号", "补助项目", "批文号", "补助类型", "相关类型",
    "收到金额", "收到日期",
    "分摊方法", "分摊期(月)", "期初余额", "本期收到", "本期分摊", "期末余额",
    "计入科目", "凭证号", "分摊起始日", "分摊终止日", "累计分摊", "剩余期限(月)",
    "结论", "备注",
]
_K7_2_KEYS = [
    "seq", "grantProject", "approvalNo", "grantType", "relatedType",
    "receivedAmount", "receivedDate",
    "amortMethod", "amortPeriod", "openingBalance", "currentReceived", "currentAmort", "closingBalance",
    "creditAccount", "voucherNo", "amortStartDate", "amortEndDate", "accumulatedAmort", "remainingPeriod",
    "conclusion", "remark",
]

# ────────────────────────────────────────────────────────────
# K7-3 调整分录汇总（10列）
# ────────────────────────────────────────────────────────────
_K7_3_HEADERS = [
    "序号", "分录类型", "摘要", "科目代码", "科目名称",
    "借方金额", "贷方金额", "附注说明", "凭证号", "备注",
]
_K7_3_KEYS = [
    "seq", "entryType", "summary", "accountCode", "accountName",
    "debitAmount", "creditAmount", "noteRef", "voucherNo", "remark",
]

# ────────────────────────────────────────────────────────────
# Sheet Specs 汇总
# ────────────────────────────────────────────────────────────
_K7_SPECS: dict[str, dict[str, Any]] = {
    "K7-2": {
        "item_id": "K7-2-rows",
        "title": "K7-2 递延收益明细表",
        "headers": _K7_2_HEADERS,
        "field_keys": _K7_2_KEYS,
        "guidance": [
            "K7-2 明细表 编制说明",
            "",
            "21列对应3区段：基础(序号/补助项目/批文号/补助类型/相关类型/收到金额/收到日期)",
            "| 分摊(分摊方法/分摊期/期初/本期收到/本期分摊/期末)",
            "| 检查(计入科目/凭证号/分摊起止/累计分摊/剩余期限/结论/备注)。",
            "",
            "负债类方向：期末 = 期初 + 收到 - 分摊。",
            "相关类型：与资产相关 / 与收益相关。",
            "分摊方法：直线法(与资产相关按使用寿命) / 分期(与收益相关按补偿期)。",
            "金额为数值型，单位：元。正数表示贷方余额（递延收益）。",
            "计入科目：其他收益(6117) 或 营业外收入(6301)。",
        ],
    },
    "K7-3": {
        "item_id": "K7-3-rows",
        "title": "K7-3 递延收益调整分录汇总",
        "headers": _K7_3_HEADERS,
        "field_keys": _K7_3_KEYS,
        "guidance": [
            "K7-3 调整分录 编制说明",
            "",
            "10列：序号/分录类型(AJE/RJE)/摘要/科目代码/科目名称/借方金额/贷方金额/附注说明/凭证号/备注。",
            "借贷必须平衡：∑借方 = ∑贷方。",
            "分录类型填 AJE（审计调整）或 RJE（重分类调整）。",
            "金额单位：元。",
        ],
    },
}

router = create_cycle_import_export_router(tag="k7-import-export", api_prefix="k7", specs=_K7_SPECS)
