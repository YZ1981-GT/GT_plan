"""K12 营业外收入 — 导入导出3端点（损益类/发生额/按来源明细）.

GET  /api/workpapers/{wp_id}/k12/export-template → 空白结构xlsx
GET  /api/workpapers/{wp_id}/k12/export-data → 当前数据xlsx
POST /api/workpapers/{wp_id}/k12/import-data → 解析xlsx→写入checklist_responses

支持sheet:
- K12-2 明细表（营业外收入按来源明细，26列3区段，动态行max 200）
- K12-3 调整分录汇总（标准借贷平衡10列）

K12特殊：
- 损益类科目6301营业外收入（贷方=收入增加）
- 明细表26列按3区段组织：基础(序号/收入来源/收入类型/对方单位/金额/发生日期)
                           分析(占比/同比/说明)
                           检查(依据文件/凭证号/是否偶发/结论/备注)
- 营业外收入来源：政府补助/债务重组利得/资产盘盈/罚款收入/捐赠利得/无法支付款项转入/其他
- Multi-sheet export: detail + adjustment in separate sheets

Requirements: 3.3, 6.2
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ─── K12-2 明细表（营业外收入按来源明细，26列3区段） ────────────────────────────

_K12_2_HEADERS = [
    # 基础区段 (6列)
    "序号", "收入来源", "收入类型", "对方单位", "金额", "发生日期",
    # 分析区段 (7列)
    "本期发生额", "上期发生额", "同比变动额", "同比变动率", "占比", "累计占比", "说明",
    # 检查区段 (13列)
    "依据文件", "凭证号", "记账日期", "摘要",
    "是否与日常活动无关", "分类是否正确", "期间归属是否正确",
    "是否偶发", "税务处理", "结论", "审计程序", "索引", "备注",
]
_K12_2_KEYS = [
    # 基础区段
    "seq", "incomeSource", "incomeType", "counterparty", "amount", "occurrenceDate",
    # 分析区段
    "currentAmount", "priorAmount", "changeAmount", "changeRate", "proportion", "cumulativeProportion", "explanation",
    # 检查区段
    "supportingDoc", "voucherRef", "bookingDate", "summary",
    "isNonRoutine", "classificationCorrect", "periodCorrect",
    "isOccasional", "taxTreatment", "conclusion", "auditProcedure", "indexRef", "remark",
]

# ─── K12-3 调整分录汇总（10列，标准借贷平衡） ────────────────────────────────

_K12_3_HEADERS = [
    "调整事项说明", "类别", "报表项目", "科目名称", "附注项目",
    "摘要", "借方调整金额", "贷方调整金额", "索引", "备注",
]
_K12_3_KEYS = [
    "description", "category", "reportItem", "accountName", "noteItem",
    "summary", "debitAmount", "creditAmount", "indexRef", "remark",
]

# ═══════════════════════════════════════════════════════════════════════════════

_K12_SPECS: dict[str, dict[str, Any]] = {
    "K12-2": {
        "item_id": "K12-2-rows",
        "title": "明细表K12-2（营业外收入按来源明细）",
        "subtitle": "科目6301 损益类（贷方=收入）| 动态行 | 3区段26列",
        "headers": _K12_2_HEADERS,
        "field_keys": _K12_2_KEYS,
        "guidance": [
            "K12-2 营业外收入明细表 编制说明",
            "",
            "按来源逐笔记录营业外收入发生情况。",
            "科目6301营业外收入为损益类贷方科目：",
            "  - 贷方发生=收入增加，借方发生=冲减/退回",
            "  - 本期发生额=本期贷方发生累计-借方发生(红冲)",
            "",
            "收入来源分类：",
            "  - 政府补助（与资产/收益相关的，计入当期损益部分）",
            "  - 债务重组利得（债务人）",
            "  - 资产盘盈利得（固定资产/存货等盘点净盈余）",
            "  - 罚款收入（合同违约金/罚没收入）",
            "  - 捐赠利得（接受捐赠资产）",
            "  - 无法支付款项转入（超过偿付期的应付款）",
            "  - 其他（保险赔偿/确实无法收回款项的转回等）",
            "",
            "关键核对：",
            "  - 营业外收入 vs 其他收益(6117,K10)：与日常活动无关→营业外，相关→其他收益",
            "  - 分类正确性(是否与日常活动无关)是核心检查项",
            "  - 合计行须与审定表K12-1发生额一致",
            "",
            "区段说明：",
            "  基础(序号~发生日期) → 分析(本期~说明) → 检查(依据文件~备注)",
            "  最大200行，超出截断。",
        ],
    },
    "K12-3": {
        "item_id": "K12-3-rows",
        "title": "调整分录汇总K12-3（标准借贷平衡）",
        "headers": _K12_3_HEADERS,
        "field_keys": _K12_3_KEYS,
        "guidance": [
            "K12-3 营业外收入调整分录汇总 编制说明",
            "",
            "记录本期所有审计调整分录（AJE）和重分类分录（RJE）。",
            "类别：报表调整/账项调整/其他。",
            "借贷平衡：Σ借方调整金额 = Σ贷方调整金额。",
            "调整分录联动审定表K12-1的AJE/RJE列。",
            "",
            "注意：6301为损益类贷方科目：",
            "  - 调整借方=减少收入（冲减/退回）",
            "  - 调整贷方=增加收入（补确认/错漏更正）",
            "",
            "常见调整场景：",
            "  - 跨期收入调整（非本期发生的收入冲回）",
            "  - 分类重分类（营业外收入↔其他收益）",
            "  - 政府补助确认时点调整",
        ],
    },
}

router = create_cycle_import_export_router(
    tag="k12-import-export", api_prefix="k12", specs=_K12_SPECS
)
