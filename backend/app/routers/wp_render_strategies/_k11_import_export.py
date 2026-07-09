"""K11 资产减值损失 — 导入导出3端点（损益类/减值汇总/源底稿核对）.

GET  /api/workpapers/{wp_id}/k11/export-template → 空白结构xlsx
GET  /api/workpapers/{wp_id}/k11/export-data → 当前数据xlsx
POST /api/workpapers/{wp_id}/k11/import-data → 解析xlsx→写入checklist_responses

支持sheet:
- K11-2 明细表（按资产类别的减值损失明细）
- K11-3 调整分录汇总

K11特殊：
- 明细表按资产类别列示（存货跌价/固定资产/无形资产/商誉/在建工程/长投/其他）
- 商誉减值不可转回（转回列为0）
- 各类别须与源底稿（F2/H1/I1/I3）减值计提核对

Requirements: 6.2
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ─── K11-2 明细表（按资产类别减值损失明细） ────────────────────────────────────

_K11_2_HEADERS = [
    "序号", "资产类别", "减值项目",
    "本期计提", "本期转回", "本期发生额",
    "来源底稿", "源底稿计提金额", "差异",
    "凭证", "结论", "备注",
]
_K11_2_KEYS = [
    "seq", "assetCategory", "impairmentItem",
    "currentProvision", "currentReversal", "currentAmount",
    "sourceWp", "sourceAmount", "variance",
    "voucherRef", "conclusion", "remark",
]

# ─── K11-3 调整分录汇总（10列） ──────────────────────────────────────────────

_K11_3_HEADERS = [
    "调整事项说明", "类别", "报表项目", "科目名称", "附注项目",
    "摘要", "借方调整金额", "贷方调整金额", "索引", "备注",
]
_K11_3_KEYS = [
    "description", "category", "reportItem", "accountName", "noteItem",
    "summary", "debitAmount", "creditAmount", "indexRef", "remark",
]

# ═══════════════════════════════════════════════════════════════════════════════

_K11_SPECS: dict[str, dict[str, Any]] = {
    "K11-2": {
        "item_id": "K11-2-rows",
        "title": "明细表K11-2（资产减值损失明细）",
        "headers": _K11_2_HEADERS,
        "field_keys": _K11_2_KEYS,
        "guidance": [
            "K11-2 资产减值损失明细表 编制说明",
            "",
            "按资产类别逐行记录各类减值损失发生情况。",
            "科目6701资产减值损失为损益类借方科目：",
            "  - 借方发生=减值增加（计提），贷方发生=减值转回/红冲",
            "  - 本期发生额=本期计提-本期转回（正数表示净减值）",
            "资产类别：存货跌价/固定资产减值/无形资产减值/商誉减值/在建工程减值/长期股权投资减值/其他",
            "注意：商誉减值不可转回（转回列填0）。",
            "差异=本期发生额-源底稿计提金额，差异应为0。",
            "各类别须与源底稿核对：F2(存货)/H1(固定资产)/I1(无形资产)/I3(商誉)。",
        ],
    },
    "K11-3": {
        "item_id": "K11-3-rows",
        "title": "调整分录汇总K11-3（标准借贷平衡）",
        "headers": _K11_3_HEADERS,
        "field_keys": _K11_3_KEYS,
        "guidance": [
            "K11-3 资产减值损失调整分录汇总 编制说明",
            "",
            "记录本期所有审计调整分录（AJE）和重分类分录（RJE）。",
            "类别：报表调整/账项调整/其他。",
            "借贷平衡：Σ借方调整金额 = Σ贷方调整金额。",
            "调整分录联动审定表K11-1的AJE/RJE列。",
            "注意：6701为损益类科目，调整借方=增加减值，贷方=减少减值。",
        ],
    },
}

router = create_cycle_import_export_router(
    tag="k11-import-export", api_prefix="k11", specs=_K11_SPECS
)
