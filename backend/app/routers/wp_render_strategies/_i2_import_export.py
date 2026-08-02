"""I2 开发支出 — 导入导出3端点（列结构对齐 requirements）.

POST /i2/export-template → 空白结构xlsx
POST /i2/export-data → 当前数据xlsx（含公式结果）
POST /i2/import-data → 解析xlsx→验证→写入checklist_responses

支持sheet: 审定表I2-1, 明细表I2-2, 研发项目构成明细表I2-7,
           截止测试I2-13(账→单据), I2-14(单据→账)
动态行表格（需导入）: I2-1, I2-2, I2-7, I2-13, I2-14
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ─── I2-1 审定表（项目×期初/增加/减少/期末） ────────────────────────────────

_I2_1_HEADERS = [
    "项目", "期初余额", "本期增加(资本化)", "本期减少(转无形)", "本期减少(转费用)",
    "期末余额", "未审数", "AJE", "RJE", "审定数", "备注",
]
_I2_1_KEYS = [
    "item", "openingBalance", "capitalized", "transferToIntangible", "transferToExpense",
    "closingBalance", "unadjusted", "aje", "rje", "audited", "remark",
]

# ─── I2-2 明细表（基础区段） ─────────────────────────────────────────────────

_I2_2_BASE_HEADERS = [
    "项目名称", "立项日期", "研发阶段", "资本化起始日", "预算总额",
]
_I2_2_BASE_KEYS = [
    "projectName", "approvalDate", "rdPhase", "capitalizationStart", "totalBudget",
]

# ─── I2-2 明细表（本期投入区段） ─────────────────────────────────────────────

_I2_2_INPUT_HEADERS = [
    "项目名称", "材料费", "人工费", "折旧摊销", "其他费用", "本期投入合计",
]
_I2_2_INPUT_KEYS = [
    "projectName", "materialCost", "laborCost", "depreciation", "otherCost", "periodTotal",
]

# ─── I2-2 明细表（资本化区段） ─────────────────────────────────────────────

_I2_2_CAP_HEADERS = [
    "项目名称", "累计资本化金额", "本期资本化", "转入无形资产", "期末余额",
]
_I2_2_CAP_KEYS = [
    "projectName", "cumulativeCapitalized", "currentCapitalized", "transferToI1", "closingBalance",
]

# ─── I2-7 研发项目构成明细表（5区段拆分73列→核心汇总） ────────────────────

_I2_7_HEADERS = [
    "项目名称", "材料费", "人工费", "折旧摊销费", "设计费",
    "试验费", "委外费", "其他费用", "费用合计", "费用化金额", "资本化金额",
]
_I2_7_KEYS = [
    "projectName", "materialCost", "laborCost", "depreciationCost", "designCost",
    "testingCost", "outsourcingCost", "otherCost", "totalCost", "expenseAmount", "capitalizedAmount",
]

# ─── I2-13 / I2-14 截止性测试（双向，字段对齐 useCycleCutoff / CutoffRow） ─────

_I2_CUTOFF_FIELD_KEYS = [
    "recordDate", "voucherNo", "amount", "description",
    "documentNo", "documentDate", "documentAmount",
    "recordPeriod", "belongPeriod", "isCrossPeriod", "conclusion", "crossPeriodAmount", "remark",
]

_I2_13_HEADERS = [
    "记账日期", "凭证号", "记账金额", "摘要",
    "凭单编号", "凭单日期", "凭单金额",
    "记账期间", "归属期间", "是否跨期", "结论", "跨期金额", "备注",
]

_I2_14_HEADERS = [
    "凭单编号", "凭单日期", "凭单金额",
    "记账日期", "凭证号", "记账金额", "摘要",
    "记账期间", "归属期间", "是否跨期", "结论", "跨期金额", "备注",
]

_I2_14_FIELD_KEYS = [
    "documentNo", "documentDate", "documentAmount",
    "recordDate", "voucherNo", "amount", "description",
    "recordPeriod", "belongPeriod", "isCrossPeriod", "conclusion", "crossPeriodAmount", "remark",
]

_I2_CUTOFF_HEADER_ALIASES: dict[str, list[str]] = {
    "记账日期": ["凭证日期", "记账凭证日期", "bookDate", "record_date", "voucher_date"],
    "凭证号": ["记账凭证号", "voucherNo", "voucher_no"],
    "记账金额": ["金额", "bookAmount", "voucherAmount"],
    "摘要": ["业务摘要", "summary", "expenseType"],
    "凭单编号": ["支出凭单编号", "原始凭证", "sourceDoc", "document_no"],
    "凭单日期": ["支出凭单日期", "原始凭证日期", "sourceDate", "document_date"],
    "凭单金额": ["支出凭单金额", "sourceAmount", "document_amount"],
    "记账期间": ["记账凭证期间", "bookPeriod", "period", "bookingPeriod"],
    "归属期间": ["belongsPeriod", "belong_period"],
    "是否跨期": ["跨期", "isCrossPeriod", "isCrossover"],
    "跨期金额": ["crossPeriodAmount"],
}

_I2_CUTOFF_GUIDANCE_FORWARD = [
    "I2-13 开发支出截止性测试（账簿→单据）编制说明",
    "",
    "一、本表目的",
    "从期末前后开发支出(1704)记账凭证出发，追查支出凭单真实性与期间归属（关注多记/虚假入账）。",
    "",
    "二、填写要求",
    "1. 样本范围：资产负债表日前后N天、金额大于阈值的1704记账凭证。",
    "2. 凭单日期须查原件后填写；自动取数导入时该列可留空。",
    "3. 跨期判定：记账日期与凭单日期分处截止日两侧即为跨期（系统导入后自动重算）。",
    "4. 结论示例：正常 / 跨期多记 / 跨期漏记。",
    "5. 请与 I2-14（单据→账）交叉评价；摘要含6604/费用化时联动 I6-5/I6-6。",
]

_I2_CUTOFF_GUIDANCE_BACKWARD = [
    "I2-14 开发支出截止性测试（单据→账簿）编制说明",
    "",
    "一、本表目的",
    "从期末前后支出凭单出发，追查是否已记入开发支出(1704)（关注漏记/跨期）。",
    "",
    "二、填写要求",
    "1. 样本范围：资产负债表日前后N天的领料单/工时单/委外结算单等支出凭单。",
    "2. 凭单日期须查原件后填写；自动取数导入时该列可留空。",
    "3. 跨期判定：凭单日期与记账日期分处截止日两侧即为跨期（系统导入后自动重算）。",
    "4. 结论示例：正常 / 跨期漏记 / 跨期多记。",
    "5. 请与 I2-13（账→单据）交叉评价。",
]

# ═══════════════════════════════════════════════════════════════════════════════

_I2_SPECS: dict[str, dict[str, Any]] = {
    "I2-1": {
        "item_id": "I2-1-rows",
        "title": "审定表I2-1（开发支出审定+三角勾稽）",
        "headers": _I2_1_HEADERS,
        "field_keys": _I2_1_KEYS,
        "guidance": [
            "I2-1 审定表 编制说明",
            "",
            "资产类公式：期末=期初+本期增加(资本化)-本期减少(转无形+转费用)（科目1704）。",
            "审定数=未审+AJE+RJE。",
            "三角勾稽：期末余额 ≡ 期初+增加-减少。",
            "本期减少(转无形)联动I1-5增加检查。",
        ],
    },
    "I2-2-base": {
        "item_id": "I2-2-rows",
        "title": "I2-2 明细表（基础信息）",
        "headers": _I2_2_BASE_HEADERS,
        "field_keys": _I2_2_BASE_KEYS,
        "guidance": [
            "I2-2 开发支出明细表 — 基础区段 编制说明",
            "",
            "研发阶段：研究阶段/开发阶段/已资本化/已结转。",
            "资本化起始日：CAS6五条件同时满足之日。",
        ],
    },
    "I2-2-input": {
        "item_id": "I2-2-rows",
        "title": "I2-2 明细表（本期投入）",
        "headers": _I2_2_INPUT_HEADERS,
        "field_keys": _I2_2_INPUT_KEYS,
        "guidance": [
            "I2-2 本期投入区段 编制说明",
            "",
            "本期投入合计=材料费+人工费+折旧摊销+其他费用。",
            "各费用明细联动I2-7项目构成明细表。",
        ],
    },
    "I2-2-cap": {
        "item_id": "I2-2-rows",
        "title": "I2-2 明细表（资本化）",
        "headers": _I2_2_CAP_HEADERS,
        "field_keys": _I2_2_CAP_KEYS,
        "guidance": [
            "I2-2 资本化区段 编制说明",
            "",
            "期末余额=累计资本化+本期资本化-转入无形资产。",
            "转入无形资产联动I1-5无形资产增加检查。",
        ],
    },
    "I2-7": {
        "item_id": "I2-7-rows",
        "title": "I2-7 研发项目构成明细表（73列汇总）",
        "headers": _I2_7_HEADERS,
        "field_keys": _I2_7_KEYS,
        "guidance": [
            "I2-7 项目构成明细表 编制说明",
            "",
            "费用合计=材料费+人工费+折旧摊销费+设计费+试验费+委外费+其他费用。",
            "费用化金额+资本化金额=费用合计（VR-I6-01校验）。",
            "各费用分项联动：I2-8材料/I2-9人员/I2-10工时/I2-11委外。",
        ],
    },
    "I2-13": {
        "item_id": "I2-13-rows",
        "title": "I2-13 截止性测试（账簿→单据）",
        "headers": _I2_13_HEADERS,
        "field_keys": _I2_CUTOFF_FIELD_KEYS,
        "header_aliases": _I2_CUTOFF_HEADER_ALIASES,
        "storage_field": "remark",
        "dual_write": True,
        "guidance": _I2_CUTOFF_GUIDANCE_FORWARD,
    },
    "I2-14": {
        "item_id": "I2-14-rows",
        "title": "I2-14 截止性测试（单据→账簿）",
        "headers": _I2_14_HEADERS,
        "field_keys": _I2_14_FIELD_KEYS,
        "header_aliases": _I2_CUTOFF_HEADER_ALIASES,
        "storage_field": "remark",
        "dual_write": True,
        "guidance": _I2_CUTOFF_GUIDANCE_BACKWARD,
    },
}

router = create_cycle_import_export_router(tag="i2-import-export", api_prefix="i2", specs=_I2_SPECS)
