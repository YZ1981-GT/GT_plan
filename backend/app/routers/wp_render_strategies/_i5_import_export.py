"""I5 其他非流动资产 — 导入导出3端点（列结构对齐 requirements）.

POST /i5/export-template → 空白结构xlsx
POST /i5/export-data → 当前数据xlsx（含公式结果）
POST /i5/import-data → 解析xlsx→验证→写入checklist_responses

支持sheet: 明细表I5-2, 调整分录I5-3
动态行表格（需导入）: I5-2, I5-3

其他非流动资产特殊：
- 明细表26列3区段：基础(名称/类型/发生日/到期日) | 金额(期初/增加/减少/期末) | 检查(凭证号/备注/结论)
- 调整分录10列：标准借贷平衡
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ─── I5-2 明细表（26列3区段：基础/金额/检查） ─────────────────────────────────

_I5_2_HEADERS = [
    # 区段1: 基础信息
    "项目名称", "资产类型", "发生日期", "到期日期",
    # 区段2: 金额（期初）
    "期初借方", "期初贷方", "期初余额",
    # 区段2: 金额（AJE/RJE）
    "AJE借方", "AJE贷方", "RJE借方", "RJE贷方",
    # 区段2: 金额（期末）
    "期末借方", "期末贷方", "期末余额", "期末审定",
    # 区段3: 检查
    "凭证号", "合同编号", "对方单位", "用途说明",
    "预计收回日", "是否逾期", "减值迹象", "分类正确性",
    "可回收性", "备注", "结论",
]
_I5_2_KEYS = [
    # 区段1: 基础信息
    "projectName", "assetType", "startDate", "maturityDate",
    # 区段2: 金额（期初）
    "openingDebit", "openingCredit", "openingBalance",
    # 区段2: 金额（AJE/RJE）
    "ajeDebit", "ajeCredit", "rjeDebit", "rjeCredit",
    # 区段2: 金额（期末）
    "closingDebit", "closingCredit", "closingBalance", "auditedAmount",
    # 区段3: 检查
    "voucherNo", "contractNo", "counterparty", "purpose",
    "expectedRecoveryDate", "isOverdue", "impairmentSign", "classificationCorrect",
    "recoverability", "remark", "conclusion",
]

# ─── I5-3 调整分录汇总（10列） ───────────────────────────────────────────────

_I5_3_HEADERS = [
    "调整事项说明", "类别", "报表项目", "科目名称", "附注项目",
    "摘要", "借方调整金额", "贷方调整金额", "索引", "备注",
]
_I5_3_KEYS = [
    "description", "category", "reportItem", "accountName", "noteItem",
    "summary", "debitAmount", "creditAmount", "indexRef", "remark",
]

# ═══════════════════════════════════════════════════════════════════════════════

_I5_SPECS: dict[str, dict[str, Any]] = {
    "I5-2": {
        "item_id": "I5-2-rows",
        "title": "明细表I5-2（26列3区段：基础/金额/检查）",
        "headers": _I5_2_HEADERS,
        "field_keys": _I5_2_KEYS,
        "guidance": [
            "I5-2 其他非流动资产明细表 编制说明",
            "",
            "逐项记录每笔其他非流动资产的基础信息、金额变动及检查结论。",
            "期初余额=期初借方-期初贷方（资产类借方科目1911）。",
            "期末借方=期初借方+AJE借方+RJE借方。",
            "期末贷方=期初贷方+AJE贷方+RJE贷方。",
            "期末余额=期末借方-期末贷方。",
            "期末审定=期初余额+增加-减少（三角勾稽）。",
            "合计行需联动审定表I5-1。",
        ],
    },
    "I5-3": {
        "item_id": "I5-3-rows",
        "title": "调整分录汇总I5-3（标准借贷平衡）",
        "headers": _I5_3_HEADERS,
        "field_keys": _I5_3_KEYS,
        "guidance": [
            "I5-3 其他非流动资产调整分录汇总 编制说明",
            "",
            "记录本期所有审计调整分录（AJE）和重分类分录（RJE）。",
            "类别：报表调整/账项调整/其他。",
            "借贷平衡：Σ借方调整金额 = Σ贷方调整金额。",
            "调整分录联动审定表I5-1的AJE/RJE列。",
        ],
    },
}

router = create_cycle_import_export_router(tag="i5-import-export", api_prefix="i5", specs=_I5_SPECS)
