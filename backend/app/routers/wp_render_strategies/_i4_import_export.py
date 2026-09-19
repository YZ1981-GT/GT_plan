"""I4 长期待摊费用 — 导入导出3端点（列结构对齐 requirements）.

POST /i4/export-template → 空白结构xlsx
POST /i4/export-data → 当前数据xlsx（含公式结果）
POST /i4/import-data → 解析xlsx→验证→写入checklist_responses

支持sheet: 明细表I4-2, 摊销测算I4-6(直线法), 摊销测算I4-7(工作量法)
动态行表格（需导入）: I4-2, I4-6, I4-7

长期待摊费用特殊：
- 明细表25列3区段：基础/摊销/余额
- I4-6 直线法：对齐源表测算vs账面（月限/到期日/本期月数四分支/月摊差异/累计差异）
- I4-7 工作量法：对齐源表测算vs账面vs差异（摊销标准=原值/工作标准）
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ─── I4-2 明细表（25列3区段：基础/摊销/余额） ─────────────────────────────────

_I4_2_HEADERS = [
    "项目名称", "发生日期", "费用类型", "原始金额", "摊销方法",
    "摊销期限(月)", "已摊月数", "累计摊销", "本期摊销",
    "期初余额", "本期增加", "本期减少", "期末余额", "剩余月数",
]
_I4_2_KEYS = [
    "projectName", "startDate", "expenseType", "originalAmount", "amortMethod",
    "totalMonths", "elapsedMonths", "accAmortization", "currentAmortization",
    "openingBalance", "currentIncrease", "currentDecrease", "closingBalance", "remainingMonths",
]

# ─── I4-6 摊销测算表直线法（对齐源表：测算 vs 账面 vs 差异） ─────────────────

_I4_6_HEADERS = [
    "类别名称", "明细项目", "原值", "累计摊销", "开始使用日期", "使用年限", "账面月摊销额",
    "使用月限", "测算到期日", "已摊销月份", "剩余摊销月份", "本期摊销月份",
    "测算月摊销额", "当期摊销", "月摊销额差异", "累计摊销费用", "累计摊销额差异", "备注",
]
_I4_6_KEYS = [
    "category", "itemName", "originalAmount", "bookAccumAmort", "startDate", "usefulLife", "bookMonthlyAmort",
    "lifeMonths", "fullAmortDate", "monthsAmortized", "remainingMonths", "periodMonths",
    "calcMonthlyAmort", "periodAmortization", "monthlyDiff", "calcAccumAmort", "accumDiff", "remark",
]

# ─── I4-7 摊销测算表工作量法（对齐源表：测算 vs 账面 vs 差异） ─────────────────

_I4_7_HEADERS = [
    "类别名称", "明细项目", "原值", "开始使用日期", "工作标准", "摊销标准",
    "本期工作量", "累计工作量",
    "测算本年摊销额", "测算累计摊销额",
    "账面本期摊销额", "账面累计摊销额",
    "本期摊销差异", "累计摊销差异", "备注",
]
_I4_7_KEYS = [
    "category", "itemName", "originalAmount", "startDate", "workStandard", "amortStandard",
    "periodUnits", "accumUnits",
    "calcPeriodAmort", "calcAccumAmort",
    "bookPeriodAmort", "bookAccumAmort",
    "periodDiff", "accumDiff", "remark",
]

# ═══════════════════════════════════════════════════════════════════════════════

_I4_SPECS: dict[str, dict[str, Any]] = {
    "I4-2": {
        "item_id": "I4-2-rows",
        "title": "明细表I4-2（25列3区段：基础/摊销/余额）",
        "headers": _I4_2_HEADERS,
        "field_keys": _I4_2_KEYS,
        "guidance": [
            "I4-2 长期待摊费用明细表 编制说明",
            "",
            "逐项记录每笔长期待摊费用项目的基础信息、摊销进度及余额。",
            "期末余额=期初+增加-摊销-减少。",
            "剩余月数=摊销期限-已摊月数。",
            "合计行需联动审定表I4-1。",
        ],
    },
    "I4-6": {
        "item_id": "I4-6-rows",
        "title": "摊销测算表I4-6直线法（测算vs账面vs差异）",
        "headers": _I4_6_HEADERS,
        "field_keys": _I4_6_KEYS,
        "guidance": [
            "I4-6 直线法摊销测算 编制说明",
            "",
            "测算月摊=原值÷使用月限；当期摊销=测算月摊×本期月数。",
            "本期月数按摊销期初/期末与项目起止四分支计算，不超过剩余月数。",
            "月摊差异=账面月摊−测算月摊；累计差异=账面累计−测算累计。",
            "开始日为空时不推算到期日（避免1900-1-0）。",
            "本表仅用于长期待摊费用，不得套用无形资产寿命规则。",
        ],
    },
    "I4-7": {
        "item_id": "I4-7-rows",
        "title": "摊销测算表I4-7工作量法（测算vs账面vs差异）",
        "headers": _I4_7_HEADERS,
        "field_keys": _I4_7_KEYS,
        "guidance": [
            "I4-7 工作量法摊销测算 编制说明",
            "",
            "摊销标准=原值÷工作标准；测算本年=本期工作量×摊销标准；测算累计=累计工作量×摊销标准。",
            "差异=测算−账面；本期/累计差异重大时追查工作量数据或政策适用性。",
            "适用于受益与产出相关的长期待摊费用（如模具费按产量、矿权按采矿量）。",
            "工作标准/实际工作量须有生产统计或合同依据；不得套用无形资产寿命判断规则。",
            "合计行与「其中」类别小计应勾稽 I4-1 本期摊销。",
        ],
    },
}

router = create_cycle_import_export_router(tag="i4-import-export", api_prefix="i4", specs=_I4_SPECS)
