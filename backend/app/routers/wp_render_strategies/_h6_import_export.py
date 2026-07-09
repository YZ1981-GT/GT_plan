"""H6 固定资产清理 — 导入导出3端点（列结构对齐 requirements）.

POST /h6/export-template → 空白结构xlsx（根据sheet_name导出对应表模板）
POST /h6/export-data → 当前数据xlsx（含已填数据）
POST /h6/import-data → 解析xlsx→验证→写入checklist_responses

支持sheets: H6-2/H6-3/H6-4
科目编码: 1606固定资产清理（借方/资产类，过渡科目）

Requirements: 3.6
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ─── H6-2 明细表（清理项目25列2区块） ─────────────────────────────────────────

_H6_2_HEADERS = [
    "序号", "资产名称", "原值", "累计折旧", "净值", "清理原因", "开始日期",
    "处置收入", "清理费用", "税费", "净损益", "结转科目", "完成日期",
    "状态", "联动H1编号", "联动H10编号",
]
_H6_2_KEYS = [
    "seq", "assetName", "originalCost", "accDepreciation", "netBookValue",
    "disposalReason", "startDate",
    "disposalIncome", "disposalExpenses", "tax", "netGainLoss",
    "transferAccount", "completionDate",
    "status", "h1Reference", "h10Reference",
]

# ─── H6-3 调整分录汇总 ─────────────────────────────────────────────────────

_H6_3_HEADERS = [
    "序号", "调整事项说明", "类别", "科目代码", "科目名称",
    "摘要", "借方金额", "贷方金额", "索引", "备注",
]
_H6_3_KEYS = [
    "seq", "description", "entryType", "accountCode", "accountName",
    "summary", "debitAmount", "creditAmount", "indexRef", "remark",
]

# ─── H6-4 检查表（清理过程逐项检查） ──────────────────────────────────────────

_H6_4_HEADERS = [
    "清理项目名称", "清理审批", "资产评估", "税务处理", "会计处理",
    "收入确认", "费用归集", "结转时点", "核查结论", "备注",
]
_H6_4_KEYS = [
    "projectName", "approvalCheck", "assetValuation", "taxTreatment",
    "accountingTreatment", "revenueRecognition", "expenseCollection",
    "transferTiming", "conclusion", "remark",
]

# ═══════════════════════════════════════════════════════════════════════════════

_H6_SPECS: dict[str, dict[str, Any]] = {
    "H6-2": {
        "item_id": "H6-2-rows",
        "title": "H6-2 固定资产清理明细表",
        "headers": _H6_2_HEADERS,
        "field_keys": _H6_2_KEYS,
        "guidance": [
            "H6-2 固定资产清理明细表 编制说明",
            "",
            "净值=原值-累计折旧；净损益=处置收入-净值-清理费用-税费。",
            "状态可选：清理中/已完成/已结转。",
            "联动H1编号对应H1-8减少检查中的处置项目。",
            "联动H10编号对应H10资产处置损益明细行。",
            "过渡科目1606：期末余额应为0，确认所有清理已结转。",
        ],
    },
    "H6-3": {
        "item_id": "H6-3-rows",
        "title": "H6-3 调整分录汇总表",
        "headers": _H6_3_HEADERS,
        "field_keys": _H6_3_KEYS,
        "guidance": [
            "H6-3 调整分录汇总 编制说明",
            "",
            "类别填 AJE（审计调整分录）或 RJE（重分类调整分录）。",
            "借方合计应等于贷方合计（借贷平衡）。",
            "科目代码以1606开头（固定资产清理）。",
            "调整分录将通过EventBus同步到H6-1审定表和A13错报汇总。",
        ],
    },
    "H6-4": {
        "item_id": "H6-4-rows",
        "title": "H6-4 固定资产清理检查表",
        "headers": _H6_4_HEADERS,
        "field_keys": _H6_4_KEYS,
        "guidance": [
            "H6-4 固定资产清理检查表 编制说明",
            "",
            "每行对应H6-2明细表的一个清理项目。",
            "各检查项填写：合规/不合规/不适用。",
            "核查结论综合评价清理过程的合规性。",
            "不合规项需关注并在审计报告中反映。",
        ],
    },
}

router = create_cycle_import_export_router(
    tag="h6-import-export", api_prefix="h6", specs=_H6_SPECS,
)
