"""K8 销售费用 — 导入导出3端点（损益类/实质性分析/截止测试/合同检查）.

GET  /api/workpapers/{wp_id}/k8/export-template → 空白结构xlsx
GET  /api/workpapers/{wp_id}/k8/export-data → 当前数据xlsx
POST /api/workpapers/{wp_id}/k8/import-data → 解析xlsx→写入checklist_responses

支持sheet:
- K8-2 明细表（费用明细科目发生额）
- K8-3 调整分录汇总
- K8-5 合同检查表
- K8-6 截止性测试(记账凭证至原始凭证)
- K8-7 截止性测试(原始凭证至记账凭证)
- K8-8 销售费用检查表

销售费用特殊：
- 明细表按费用明细科目列示发生额（非月度12列）
- 截止双向各44行
- 实质性分析为只读计算无需导入
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ─── K8-2 明细表（费用明细科目发生额） ─────────────────────────────────────────

_K8_2_HEADERS = [
    "序号", "明细科目代码", "明细科目名称",
    "本期借方发生", "本期贷方发生", "净发生额",
    "上期发生额", "同比变动额", "同比变动率(%)",
    "占收入比(%)", "波动说明", "核查结论", "备注",
]
_K8_2_KEYS = [
    "seq", "accountCode", "accountName",
    "debitAmount", "creditAmount", "netAmount",
    "priorAmount", "changeAmount", "changeRate",
    "revenueRatio", "fluctuationNote", "checkConclusion", "remark",
]

# ─── K8-3 调整分录汇总（9列） ────────────────────────────────────────────────
# 列集合对齐前端 K8TabAdjustment 行模型（adjustment_ie_contract.json / Task 2.3）：
#   前端只有单 summary 担任「调整事项说明」→ 消除后端 description + summary 双列，
#   「调整事项说明」列直接绑 summary（否则用户填的该列在前端永远读不到）
_K8_3_HEADERS = [
    "调整事项说明", "类别", "报表项目", "科目名称", "附注项目",
    "借方调整金额", "贷方调整金额", "索引", "备注",
]
_K8_3_KEYS = [
    "summary", "category", "reportItem", "accountName", "noteItem",
    "debitAmount", "creditAmount", "indexRef", "remark",
]

# ─── K8-5 合同检查表 ─────────────────────────────────────────────────────────

_K8_5_HEADERS = [
    "序号", "合同名称", "合同类型", "对方单位", "合同金额",
    "本期入账金额", "发票号码", "审批流程", "真实性结论", "备注",
]
_K8_5_KEYS = [
    "seq", "contractName", "contractType", "counterparty", "contractAmount",
    "bookedAmount", "invoiceNo", "approvalProcess", "authenticityConclusion", "remark",
]

# ─── K8-6 截止性测试(记账凭证至原始凭证) ─────────────────────────────────────

_K8_6_HEADERS = [
    "序号", "凭证号", "记账日期", "摘要", "金额",
    "费用类型", "原始凭证日期", "归属期间", "是否跨期", "结论", "备注",
]
_K8_6_KEYS = [
    "seq", "voucherNo", "bookDate", "summary", "amount",
    "expenseType", "sourceDate", "belongsPeriod", "isCrossover", "conclusion", "remark",
]

# ─── K8-7 截止性测试(原始凭证至记账凭证) ─────────────────────────────────────

_K8_7_HEADERS = [
    "序号", "原始凭证", "原始凭证日期", "金额", "费用类型",
    "记账日期", "记账期间", "是否及时入账", "是否跨期", "结论", "备注",
    "归属期间",
]
_K8_7_KEYS = [
    "seq", "sourceDoc", "sourceDate", "amount", "expenseType",
    "bookDate", "bookPeriod", "isTimely", "isCrossover", "conclusion", "remark",
    "belongsPeriod",
]

# ─── K8-8 销售费用检查表 ─────────────────────────────────────────────────────

_K8_8_HEADERS = [
    "序号", "检查项目", "检查内容", "结论", "证据说明", "备注",
]
_K8_8_KEYS = [
    "seq", "checkItem", "checkContent", "conclusion", "evidence", "remark",
]

# ═══════════════════════════════════════════════════════════════════════════════

_K8_SPECS: dict[str, dict[str, Any]] = {
    "K8-2": {
        "item_id": "K8-2-rows",
        "title": "明细表K8-2（费用明细科目发生额）",
        "headers": _K8_2_HEADERS,
        "field_keys": _K8_2_KEYS,
        "guidance": [
            "K8-2 销售费用明细表 编制说明",
            "",
            "按费用明细科目逐行记录销售费用发生情况。",
            "科目6601销售费用为损益类借方科目：",
            "  - 借方发生=费用增加，贷方发生=费用冲回/结转",
            "  - 净发生额=借方-贷方（正数表示净费用）",
            "合计须与审定表K8-1净发生额一致。",
            "同比变动率=(本期-上期)/上期×100%。",
            "占收入比=费用/营业收入×100%。",
        ],
    },
    "K8-3": {
        # item_id / storage_field 对齐前端持久化键（K8TabAdjustment: ITEM_PREFIX='K8-3-adj' + '-entries'，写 remark 列；
        # K8TabDetail / K8TabContractCheck 亦直写该键）
        "item_id": "K8-3-adj-entries",
        "storage_field": "remark",
        "title": "调整分录汇总K8-3（标准借贷平衡）",
        "headers": _K8_3_HEADERS,
        "field_keys": _K8_3_KEYS,
        "guidance": [
            "K8-3 销售费用调整分录汇总 编制说明",
            "",
            "记录本期所有审计调整分录（AJE）和重分类分录（RJE）。",
            "类别：报表调整/账项调整/其他。",
            "借贷平衡：Σ借方调整金额 = Σ贷方调整金额。",
            "调整分录联动审定表K8-1的AJE/RJE列。",
            "注意：6601为损益类科目，调整借方=增加费用，贷方=减少费用。",
        ],
    },
    "K8-5": {
        "item_id": "K8-5-rows",
        "title": "合同检查表K8-5",
        "headers": _K8_5_HEADERS,
        "field_keys": _K8_5_KEYS,
        "guidance": [
            "K8-5 销售费用合同检查表 编制说明",
            "",
            "检查重大费用合同（广告/推广/运输等）的真实性、金额匹配和审批合规。",
            "合同类型：广告合同/推广合同/运输合同/服务合同/其他。",
            "真实性结论：真实/存疑/不合规。",
            "金额匹配：合同金额与入账金额差异说明。",
        ],
    },
    "K8-6": {
        "item_id": "K8-6-rows",
        "title": "截止性测试(记账凭证至原始凭证)K8-6",
        "headers": _K8_6_HEADERS,
        "field_keys": _K8_6_KEYS,
        "guidance": [
            "K8-6 截止性测试（记账凭证至原始凭证）编制说明",
            "",
            "从记账凭证出发，验证已入账费用的原始凭证支持及期间正确性。",
            "测试范围：期末±5天的记账凭证。",
            "跨期判断：原始凭证日期与记账日期分属不同会计期间。",
            "结论：无跨期/存在跨期需调整/不适用。",
        ],
    },
    "K8-7": {
        "item_id": "K8-7-rows",
        "title": "截止性测试(原始凭证至记账凭证)K8-7",
        "headers": _K8_7_HEADERS,
        "field_keys": _K8_7_KEYS,
        "guidance": [
            "K8-7 截止性测试（原始凭证至记账凭证）编制说明",
            "",
            "从原始凭证出发，验证已发生费用是否及时完整入账（完整性认定）。",
            "测试范围：期末±5天的原始凭证。",
            "及时入账：原始凭证日期至记账日期间隔≤5个工作日为及时。",
            "跨期判断：原始凭证日期与记账日期分属不同会计期间。",
        ],
    },
    "K8-8": {
        "item_id": "K8-8-rows",
        "title": "销售费用检查表K8-8",
        "headers": _K8_8_HEADERS,
        "field_keys": _K8_8_KEYS,
        "guidance": [
            "K8-8 销售费用检查表 编制说明",
            "",
            "综合检查销售费用各项合规性。",
            "逐项判断：合规/不合规/不适用。",
            "存在'不合规'项时须记录证据并提示调整。",
        ],
    },
}

router = create_cycle_import_export_router(
    tag="k8-import-export", api_prefix="k8", specs=_K8_SPECS
)
