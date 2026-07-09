"""K13 营业外支出 — 导入导出3端点（损益类/发生额/按去向明细）.

POST /api/workpapers/{wp_id}/k13/export-template → 空白结构xlsx
POST /api/workpapers/{wp_id}/k13/export-data → 当前数据xlsx
POST /api/workpapers/{wp_id}/k13/import-data → 解析xlsx→写入checklist_responses

支持sheet:
- K13-2 明细表（营业外支出按去向明细，26列3区段，动态行max 200）
- K13-3 调整分录汇总（标准借贷平衡10列）

K13特殊：
- 损益类科目6711营业外支出（借方=支出增加）
- 明细表26列按3区段组织：基础(支出去向/支出类型/对方单位/1~12月发生额/小计/AJE/RJE/审定)
                           分析(是否偶发/交叉引用/占比/上期金额/上期AJE/上期RJE/上期审定/上期占比/同比变动)
                           检查(备注)
- 营业外支出去向：非流动资产处置损失/捐赠支出/罚款滞纳金/债务重组损失/资产盘亏损失/其他
- Multi-sheet export: detail + adjustment in separate sheets

Requirements: 3.3, 6.2
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ─── K13-2 明细表（营业外支出按去向明细，26列3区段） ────────────────────────────

_K13_2_HEADERS = [
    # 基础区段 (18列: 支出去向+类型+对方+12月+小计+AJE+RJE+审定)
    "支出去向", "支出类型", "对方单位",
    "1月发生额", "2月发生额", "3月发生额", "4月发生额",
    "5月发生额", "6月发生额", "7月发生额", "8月发生额",
    "9月发生额", "10月发生额", "11月发生额", "12月发生额",
    "小计", "AJE", "RJE", "审定数",
    # 分析区段 (7列)
    "是否偶发", "交叉引用", "占比",
    "上期金额", "上期AJE", "上期RJE", "上期审定",
    # 检查区段 (1列)
    "备注",
]
_K13_2_KEYS = [
    # 基础区段
    "project", "expenseType", "counterparty",
    "m1", "m2", "m3", "m4", "m5", "m6", "m7", "m8", "m9", "m10", "m11", "m12",
    "monthTotal", "aje", "rje", "audited",
    # 分析区段
    "nonRecurring", "crossRef", "proportion",
    "priorAmount", "priorAje", "priorRje", "priorAudited",
    # 检查区段
    "remark",
]

# ─── K13-3 调整分录汇总（10列，标准借贷平衡） ────────────────────────────────

_K13_3_HEADERS = [
    "调整事项说明", "类别", "报表项目", "科目名称", "附注项目",
    "摘要", "借方调整金额", "贷方调整金额", "索引", "备注",
]
_K13_3_KEYS = [
    "description", "category", "reportItem", "accountName", "noteItem",
    "summary", "debitAmount", "creditAmount", "indexRef", "remark",
]

# ═══════════════════════════════════════════════════════════════════════════════

_K13_SPECS: dict[str, dict[str, Any]] = {
    "K13-2": {
        "item_id": "K13-2-detail-rows",
        "title": "明细表K13-2（营业外支出按去向明细）",
        "subtitle": "科目6711 损益类（借方=支出）| 动态行 | 3区段26列",
        "headers": _K13_2_HEADERS,
        "field_keys": _K13_2_KEYS,
        "guidance": [
            "K13-2 营业外支出明细表 编制说明",
            "",
            "按去向逐笔记录营业外支出发生情况。",
            "科目6711营业外支出为损益类借方科目：",
            "  - 借方发生=支出增加，贷方发生=冲减/转回",
            "  - 本期发生额=本期借方发生累计-贷方发生(红冲)",
            "",
            "支出去向分类：",
            "  - 非流动资产处置损失（固定资产/无形资产毁损报废）",
            "  - 捐赠支出（公益性/非公益性，影响税前扣除）",
            "  - 罚款滞纳金（行政/合同违约/税务滞纳金）",
            "  - 债务重组损失（债务人重组让步损失）",
            "  - 资产盘亏损失（固定资产/存货等盘点净亏损）",
            "  - 其他（非常损失/保险赔付不足部分等）",
            "",
            "关键核对：",
            "  - 营业外支出 vs 其他支出(管理费用/销售费用)：与日常活动无关→营业外",
            "  - 税前扣除性是核心检查项（捐赠限额/罚款不可扣除）",
            "  - 合计行须与审定表K13-1发生额一致",
            "",
            "列说明：",
            "  1~12月发生额为各月借方发生，小计=Σ月份，审定=小计+AJE+RJE",
            "  最大200行，超出截断。",
        ],
    },
    "K13-3": {
        "item_id": "K13-3-rows",
        "title": "调整分录汇总K13-3（标准借贷平衡）",
        "headers": _K13_3_HEADERS,
        "field_keys": _K13_3_KEYS,
        "guidance": [
            "K13-3 营业外支出调整分录汇总 编制说明",
            "",
            "记录本期所有审计调整分录（AJE）和重分类分录（RJE）。",
            "类别：报表调整/账项调整/其他。",
            "借贷平衡：Σ借方调整金额 = Σ贷方调整金额。",
            "调整分录联动审定表K13-1的AJE/RJE列。",
            "",
            "注意：6711为损益类借方科目：",
            "  - 调整借方=增加支出（补确认/错漏更正）",
            "  - 调整贷方=减少支出（冲减/转回）",
            "",
            "常见调整场景：",
            "  - 跨期支出调整（非本期发生的支出冲回）",
            "  - 分类重分类（营业外支出↔管理费用/其他支出）",
            "  - 捐赠支出确认金额调整（公允价值变动）",
            "  - 资产处置损失金额更正",
        ],
    },
}

router = create_cycle_import_export_router(
    tag="k13-import-export", api_prefix="k13", specs=_K13_SPECS
)
