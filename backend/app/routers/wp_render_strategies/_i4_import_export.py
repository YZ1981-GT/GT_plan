"""I4 长期待摊费用 — 导入导出3端点（列结构对齐 requirements）.

POST /i4/export-template → 空白结构xlsx
POST /i4/export-data → 当前数据xlsx（含公式结果）
POST /i4/import-data → 解析xlsx→验证→写入checklist_responses

支持sheet: 明细表I4-2, 摊销测算I4-6(直线法), 摊销测算I4-7(工作量法)
动态行表格（需导入）: I4-2, I4-6, I4-7

长期待摊费用特殊：
- 明细表25列3区段：基础/摊销/余额
- I4-6 直线法：月摊销=原始金额÷总月数，横向12月矩阵
- I4-7 工作量法：月摊销=原始金额×(本月量÷总量)，横向12月矩阵
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

# ─── I4-6 摊销测算表直线法（65行×28列，39公式） ─────────────────────────────────

_I4_6_HEADERS = [
    "项目名称", "原始金额", "摊销期限(月)", "已摊月数", "月摊销额",
    "1月", "2月", "3月", "4月", "5月", "6月",
    "7月", "8月", "9月", "10月", "11月", "12月",
    "本年摊销合计", "累计已摊", "剩余月数", "期末余额",
]
_I4_6_KEYS = [
    "projectName", "originalAmount", "totalMonths", "elapsedMonths", "monthlyAmort",
    "month01", "month02", "month03", "month04", "month05", "month06",
    "month07", "month08", "month09", "month10", "month11", "month12",
    "yearTotal", "accAmortization", "remainingMonths", "endingBalance",
]

# ─── I4-7 摊销测算表工作量法（65行×28列，21公式） ─────────────────────────────

_I4_7_HEADERS = [
    "项目名称", "原始金额", "总预计工作量", "已完成工作量", "本月工作量",
    "1月", "2月", "3月", "4月", "5月", "6月",
    "7月", "8月", "9月", "10月", "11月", "12月",
    "本年摊销合计", "累计已摊", "剩余工作量", "期末余额",
]
_I4_7_KEYS = [
    "projectName", "originalAmount", "totalUnits", "completedUnits", "currentUnits",
    "month01", "month02", "month03", "month04", "month05", "month06",
    "month07", "month08", "month09", "month10", "month11", "month12",
    "yearTotal", "accAmortization", "remainingUnits", "endingBalance",
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
        "title": "摊销测算表I4-6直线法（横向12月矩阵）",
        "headers": _I4_6_HEADERS,
        "field_keys": _I4_6_KEYS,
        "guidance": [
            "I4-6 直线法摊销测算 编制说明",
            "",
            "直线法：月摊销额=原始金额÷摊销总月数（按月平均摊销）。",
            "横向12月矩阵逐月填列摊销金额。",
            "本年摊销合计=Σ(1月~12月)。",
            "期末余额=原始金额-累计已摊。",
            "剩余月数=摊销期限-已摊月数。",
        ],
    },
    "I4-7": {
        "item_id": "I4-7-rows",
        "title": "摊销测算表I4-7工作量法（横向12月矩阵）",
        "headers": _I4_7_HEADERS,
        "field_keys": _I4_7_KEYS,
        "guidance": [
            "I4-7 工作量法摊销测算 编制说明",
            "",
            "工作量法：月摊销=原始金额×(本月工作量÷总预计工作量)。",
            "适用于按产量/工作量摊销的项目（如模具费按产品产量摊销）。",
            "横向12月矩阵逐月按实际工作量计算摊销。",
            "本年摊销合计=Σ(1月~12月)。",
            "期末余额=原始金额-累计已摊。",
        ],
    },
}

router = create_cycle_import_export_router(tag="i4-import-export", api_prefix="i4", specs=_I4_SPECS)
