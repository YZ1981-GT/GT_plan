"""I6 研发费用 — 导入导出3端点（损益类/月度12列/截止测试）.

GET  /api/workpapers/{wp_id}/i6/export-template → 空白结构xlsx
GET  /api/workpapers/{wp_id}/i6/export-data → 当前数据xlsx
POST /api/workpapers/{wp_id}/i6/import-data → 解析xlsx→写入checklist_responses

支持sheet:
- I6-2 明细表（月度12列横向宽表）
- I6-3 调整分录汇总

研发费用特殊：
- 明细表65列：固定列(项目/类别) + 12月份列(1月~12月各月金额) + 合计列 + 辅助列
- 标准调整分录10列：借贷平衡
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ─── I6-2 明细表（月度12列横向宽表） ─────────────────────────────────────────

_I6_2_HEADERS = [
    # 基础信息
    "项目名称", "费用类别",
    # 月度12列
    "1月", "2月", "3月", "4月", "5月", "6月",
    "7月", "8月", "9月", "10月", "11月", "12月",
    # 合计
    "合计",
    # 辅助信息
    "同期金额", "变动率(%)", "备注",
]
_I6_2_KEYS = [
    # 基础信息
    "projectName", "expenseCategory",
    # 月度12列
    "m1", "m2", "m3", "m4", "m5", "m6",
    "m7", "m8", "m9", "m10", "m11", "m12",
    # 合计
    "yearTotal",
    # 辅助信息
    "priorAmount", "changeRate", "remark",
]

# ─── I6-3 调整分录汇总（10列） ───────────────────────────────────────────────

_I6_3_HEADERS = [
    "调整事项说明", "类别", "报表项目", "科目名称", "附注项目",
    "摘要", "借方调整金额", "贷方调整金额", "索引", "备注",
]
_I6_3_KEYS = [
    "description", "category", "reportItem", "accountName", "noteItem",
    "summary", "debitAmount", "creditAmount", "indexRef", "remark",
]

# ═══════════════════════════════════════════════════════════════════════════════

_I6_SPECS: dict[str, dict[str, Any]] = {
    "I6-2": {
        "item_id": "I6-2-rows",
        "title": "明细表I6-2（月度12列横向宽表）",
        "headers": _I6_2_HEADERS,
        "field_keys": _I6_2_KEYS,
        "guidance": [
            "I6-2 研发费用明细表 编制说明",
            "",
            "按项目/费用类别逐行记录研发费用月度发生情况。",
            "科目6602研发费用为损益类借方科目：",
            "  - 借方发生=费用增加，贷方发生=费用冲回/结转",
            "  - 净发生额=借方-贷方（正数表示净费用）",
            "合计=SUM(1月~12月)，必须与审定表I6-1净发生额一致。",
            "变动率=(本期合计-同期)/同期×100%。",
            "月度波动>±30%的异常月份需关注。",
        ],
    },
    "I6-3": {
        "item_id": "I6-3-rows",
        "title": "调整分录汇总I6-3（标准借贷平衡）",
        "headers": _I6_3_HEADERS,
        "field_keys": _I6_3_KEYS,
        "guidance": [
            "I6-3 研发费用调整分录汇总 编制说明",
            "",
            "记录本期所有审计调整分录（AJE）和重分类分录（RJE）。",
            "类别：报表调整/账项调整/其他。",
            "借贷平衡：Σ借方调整金额 = Σ贷方调整金额。",
            "调整分录联动审定表I6-1的AJE/RJE列。",
            "注意：6602为损益类科目，调整借方=增加费用，贷方=减少费用。",
        ],
    },
}

router = create_cycle_import_export_router(tag="i6-import-export", api_prefix="i6", specs=_I6_SPECS)
