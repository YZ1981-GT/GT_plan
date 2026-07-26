"""I6 研发费用 — 导入导出3端点（损益类/月度12列/截止测试）.

POST /api/workpapers/{wp_id}/i6/export-template → 空白结构xlsx
POST /api/workpapers/{wp_id}/i6/export-data → 当前数据xlsx
POST /api/workpapers/{wp_id}/i6/import-data → 解析xlsx→写入checklist_responses

支持sheet:
- I6-2 明细表（月度12列横向宽表）
- I6-3 调整分录汇总
- I6-5 截止性测试（账簿→单据）
- I6-6 截止性测试（单据→账簿）

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

# ─── I6-5 / I6-6 截止性测试（双向，字段对齐 useCycleCutoff / CutoffRow） ─────

_I6_CUTOFF_FIELD_KEYS = [
    "recordDate", "voucherNo", "amount", "description",
    "documentNo", "documentDate", "documentAmount",
    "recordPeriod", "belongPeriod", "isCrossPeriod", "conclusion", "crossPeriodAmount", "remark",
]

_I6_5_HEADERS = [
    "记账日期", "凭证号", "记账金额", "摘要",
    "支出凭单编号", "支出凭单日期", "支出凭单金额",
    "记账期间", "归属期间", "是否跨期", "结论", "跨期金额", "备注",
]

_I6_6_HEADERS = [
    "支出凭单编号", "支出凭单日期", "支出凭单金额",
    "记账日期", "凭证号", "记账金额", "摘要",
    "记账期间", "归属期间", "是否跨期", "结论", "跨期金额", "备注",
]

_I6_6_FIELD_KEYS = [
    "documentNo", "documentDate", "documentAmount",
    "recordDate", "voucherNo", "amount", "description",
    "recordPeriod", "belongPeriod", "isCrossPeriod", "conclusion", "crossPeriodAmount", "remark",
]

_I6_CUTOFF_HEADER_ALIASES: dict[str, list[str]] = {
    "记账日期": ["凭证日期", "记账凭证日期", "bookDate", "record_date", "voucher_date"],
    "凭证号": ["记账凭证号", "voucherNo", "voucher_no"],
    "记账金额": ["金额", "bookAmount", "voucherAmount"],
    "摘要": ["业务摘要", "summary", "expenseType"],
    "支出凭单编号": ["凭单编号", "原始凭证", "sourceDoc", "document_no"],
    "支出凭单日期": ["凭单日期", "原始凭证日期", "sourceDate", "document_date"],
    "支出凭单金额": ["凭单金额", "sourceAmount", "document_amount"],
    "记账期间": ["记账凭证期间", "bookPeriod", "period", "bookingPeriod"],
    "归属期间": ["belongsPeriod", "belong_period"],
    "是否跨期": ["跨期", "isCrossPeriod", "isCrossover"],
    "跨期金额": ["crossPeriodAmount"],
}

_I6_CUTOFF_GUIDANCE_FORWARD = [
    "I6-5 研发费用截止性测试（账簿→单据）编制说明",
    "",
    "一、本表目的",
    "从期末前后研发费用(6602)记账凭证出发，追查支出凭单真实性与期间归属（关注多记/提前入账）。",
    "",
    "二、填写要求",
    "1. 样本范围：资产负债表日前后N天、金额大于阈值的6602记账凭证。",
    "2. 支出凭单日期须查原件后填写；自动取数导入时该列可留空。",
    "3. 跨期判定：记账日期与凭单日期分处截止日两侧即为跨期（系统导入后自动重算）。",
    "4. 结论示例：正常 / 跨期多记 / 跨期漏记。",
    "5. 请与 I6-6（单据→账）交叉评价；摘要含资本化/1717时联动 I2-13/I2-14。",
]

_I6_CUTOFF_GUIDANCE_BACKWARD = [
    "I6-6 研发费用截止性测试（单据→账簿）编制说明",
    "",
    "一、本表目的",
    "从期末前后支出凭单出发，追查是否已记入研发费用(6602)（关注漏记/跨期）。",
    "",
    "二、填写要求",
    "1. 样本范围：资产负债表日前后N天的领料单/工时单/委外结算单等支出凭单。",
    "2. 支出凭单日期须查原件后填写；自动取数导入时该列可留空。",
    "3. 跨期判定：凭单日期与记账日期分处截止日两侧即为跨期（系统导入后自动重算）。",
    "4. 结论示例：正常 / 跨期漏记 / 跨期多记。",
    "5. 请与 I6-5（账→单据）交叉评价，并与 I2-14 开发支出截止底稿联动。",
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
        # 前端 useI6Adjustment / i6AdjDraftHelpers 读写 remark 列，工厂默认 conclusion 会写错列（Task 2.7）
        "storage_field": "remark",
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
    "I6-5": {
        "item_id": "I6-5-rows",
        "title": "I6-5 截止性测试（账簿→单据）",
        "headers": _I6_5_HEADERS,
        "field_keys": _I6_CUTOFF_FIELD_KEYS,
        "header_aliases": _I6_CUTOFF_HEADER_ALIASES,
        "storage_field": "remark",
        "dual_write": True,
        "guidance": _I6_CUTOFF_GUIDANCE_FORWARD,
    },
    "I6-6": {
        "item_id": "I6-6-rows",
        "title": "I6-6 截止性测试（单据→账簿）",
        "headers": _I6_6_HEADERS,
        "field_keys": _I6_6_FIELD_KEYS,
        "header_aliases": _I6_CUTOFF_HEADER_ALIASES,
        "storage_field": "remark",
        "dual_write": True,
        "guidance": _I6_CUTOFF_GUIDANCE_BACKWARD,
    },
}

router = create_cycle_import_export_router(tag="i6-import-export", api_prefix="i6", specs=_I6_SPECS)
