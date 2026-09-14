"""H6 固定资产清理 — 导入导出3端点（列结构对齐前端模型）.

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

# ─── H6-2 明细表（字段名对齐 useH6Detail 持久化） ──────────────────────────────

_H6_2_HEADERS = [
    "序号", "资产名称", "原值", "累计折旧", "减值准备", "净值", "清理原因", "转入清理时间",
    "处置收入", "清理费用", "税费", "净损益", "结转科目", "完成日期",
    "状态", "联动H1编号", "联动H10编号", "超1年进展情况", "备注",
]
_H6_2_KEYS = [
    "seq", "assetName", "originalCost", "accumulatedDepreciation", "impairmentProvision", "netBookValue",
    "disposalReason", "startDate",
    "disposalIncome", "disposalExpenses", "taxAmount", "gainLoss",
    "transferAccount", "completionDate",
    "status", "refH1Code", "refH10Code",
    "overOneYearProgress", "remarks",
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

# ─── H6-4 检查表（含核对1–5，对齐 useH6Check） ───────────────────────────────

_H6_4_HEADERS = [
    "日期", "凭证编号", "固定资产类别", "固定资产名称", "对方科目",
    "原值", "累计折旧", "减值准备", "净值",
    "清理费用", "清理收入", "清理净损益",
    "转营业外收入/支出", "转资产处置收益", "期末余额",
    "清理原因", "批准人", "索引号", "联动H1", "联动H10",
    "核对1", "核对2", "核对3", "核对4", "核对5",
    "是否异常", "备注",
]
_H6_4_KEYS = [
    "date", "voucherNo", "category", "assetName", "counterpartAccount",
    "originalCost", "accumulatedDepreciation", "impairment", "netValue",
    "clearingExpense", "clearingIncome", "clearingGainLoss",
    "toNonOperating", "toDisposalGain", "endingBalance",
    "clearingReason", "approvedBy", "indexRef", "refH1Code", "refH10Code",
    "check1", "check2", "check3", "check4", "check5",
    "isAbnormal", "remark",
]

# ═══════════════════════════════════════════════════════════════════════════════

_H6_SPECS: dict[str, dict[str, Any]] = {
    "H6-2": {
        "item_id": "H6-2-rows",
        "title": "H6-2 固定资产清理明细表",
        "headers": _H6_2_HEADERS,
        "field_keys": _H6_2_KEYS,
        "header_aliases": {
            "累计折旧": ["accDepreciation", "accDep"],
            "税费": ["tax"],
            "净损益": ["netGainLoss"],
            "联动H1编号": ["h1Reference", "联动H1"],
            "联动H10编号": ["h10Reference", "联动H10"],
        },
        "guidance": [
            "H6-2 固定资产清理明细表 编制说明",
            "",
            "净值=原值-累计折旧-减值准备；净损益=处置收入-净值-清理费用-税费。",
            "状态可选：清理中/已完成/已结转；已结转后净损益≠0属正常（结转至损益科目）。",
            "清理原因建议：出售/报废/毁损/对外投资/非货币性资产交换/债务重组/其他。",
            "转入清理超过1年且未结转时，须填写「超1年进展情况」（长期挂账关注）。",
            "联动H1编号对应H1-8减少检查；联动H10编号对应H10资产处置损益明细。",
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
            "H6-4 固定资产清理检查表 编制说明（致同五段式）",
            "",
            "一、审计目标 → 二、测试原因/抽样 → 三、凭证级明细 → 四、说明 → 五、结论。",
            "净值=原值−累计折旧−减值准备；清理净损益=清理收入−清理费用−净值。",
            "检查比例=样本净值合计÷H6-2本期减少净值合计；偏低须扩样或说明。",
            "核对1–5：凭证齐全/相符/账务正确/截止/结转分摊与1606清零及H10勾稽。",
            "结转列区分「转营业外收入/支出」与「转资产处置收益」（CAS30）。",
            "1606为过渡科目，样本期末余额原则上应清零。",
        ],
    },
}

router = create_cycle_import_export_router(
    tag="h6-import-export", api_prefix="h6", specs=_H6_SPECS,
    # 前端以 remark 为权威存储字段；工厂默认 conclusion 会导致导入读不到/导出恒空。
    storage_field="remark",
)
