"""I2 开发支出 — 导入导出3端点（列结构对齐 requirements）.

POST /i2/export-template → 空白结构xlsx
POST /i2/export-data → 当前数据xlsx（含公式结果）
POST /i2/import-data → 解析xlsx→验证→写入checklist_responses

支持sheet: 审定表I2-1, 明细表I2-2, 研发项目构成明细表I2-7
动态行表格（需导入）: I2-1, I2-2, I2-7
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
            "资产类公式：期末=期初+本期增加(资本化)-本期减少(转无形+转费用)（科目1717）。",
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
}

router = create_cycle_import_export_router(tag="i2-import-export", api_prefix="i2", specs=_I2_SPECS)
