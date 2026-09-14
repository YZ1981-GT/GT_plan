"""K10 其他收益 — 导入导出3端点（损益类/发生额/政府补助明细）.

POST /api/workpapers/{wp_id}/k10/export-template → 空白结构xlsx
POST /api/workpapers/{wp_id}/k10/export-data → 当前数据xlsx
POST /api/workpapers/{wp_id}/k10/import-data → 解析xlsx→写入checklist_responses

支持sheet:
- K10-2 明细表（其他收益按补助项目明细，12列，动态行max 200）
- K10-4 政府补助核对表（补助核对引擎，10列，动态行）

K10特殊：
- 损益类科目6117其他收益（贷方=收益增加）
- 明细表12列按补助项目组织：序号/补助项目/批文号/补助类型/来源/本期计入金额/计入依据/凭证号/同比/结论/索引/备注
- 政府补助核对表10列：补助项目/收到金额/直接计入/递延分摊计入/合计计入/递延收益期末/是否与K7一致/K7索引/结论/备注
- Multi-sheet export: detail + grant reconcile in separate sheets

Requirements: 3.3, 7.2
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ─── K10-2 明细表（其他收益按补助项目明细，12列） ────────────────────────────

_K10_2_HEADERS = [
    "序号", "补助项目", "批文号", "补助类型", "来源",
    "本期计入金额", "计入依据", "凭证号",
    "同比变动", "结论", "索引", "备注",
]
_K10_2_KEYS = [
    "seq", "grantProject", "approvalRef", "grantType", "recognitionSource",
    "currentAmount", "recognitionBasis", "voucherRef",
    "yoyChange", "conclusion", "indexRef", "remark",
]

# ─── K10-4 政府补助核对表（与K7递延收益分摊核对，10列） ────────────────────────

_K10_4_HEADERS = [
    "补助项目", "收到金额", "直接计入其他收益", "递延分摊计入",
    "合计计入", "递延收益期末", "是否与K7一致",
    "K7索引", "结论", "备注",
]
_K10_4_KEYS = [
    "grantProject", "receivedAmount", "directRecognition", "deferredAmortization",
    "totalRecognized", "deferredIncomeClosing", "consistentWithK7",
    "k7IndexRef", "conclusion", "remark",
]

# ═══════════════════════════════════════════════════════════════════════════════

_K10_SPECS: dict[str, dict[str, Any]] = {
    "K10-2": {
        "item_id": "K10-2-rows",
        "title": "明细表K10-2（其他收益按补助项目明细）",
        "subtitle": "科目6117 损益类（贷方=收益）| 动态行 | 12列",
        "headers": _K10_2_HEADERS,
        "field_keys": _K10_2_KEYS,
        "guidance": [
            "K10-2 其他收益明细表 编制说明",
            "",
            "按补助项目逐笔记录其他收益发生情况。",
            "科目6117其他收益为损益类贷方科目：",
            "  - 贷方发生=收益增加，借方发生=冲减/退回",
            "  - 本期发生额=本期贷方发生累计-借方发生(红冲)",
            "",
            "来源分类：",
            "  - 直接计入：政府补助直接计入其他收益（与日常活动相关）",
            "  - 递延分摊：递延收益按期分摊计入其他收益",
            "",
            "补助类型示例：",
            "  - 即征即退增值税",
            "  - 财政贴息（含与资产/与收益相关）",
            "  - 研发补助（研发费加计扣除等）",
            "  - 稳岗补贴",
            "  - 产业扶持资金",
            "  - 其他政府补助",
            "",
            "关键核对：",
            "  - 其他收益(6117/K10) vs 营业外收入(6301/K12)：与日常活动相关→其他收益",
            "  - 合计行须与审定表K10-1发生额一致",
            "  - 递延分摊须与K10-4政府补助核对表/K7递延收益核对",
            "",
            "最大200行，超出截断。",
        ],
    },
    "K10-4": {
        "item_id": "K10-4-rows",
        "title": "政府补助核对表K10-4（与K7递延收益分摊核对）",
        "subtitle": "合计计入=直接+递延分摊 | 与K7一致性校验",
        "headers": _K10_4_HEADERS,
        "field_keys": _K10_4_KEYS,
        "guidance": [
            "K10-4 政府补助核对表 编制说明",
            "",
            "核对政府补助收益确认的完整性和分类正确性。",
            "",
            "核心公式：",
            "  合计计入 = 直接计入其他收益 + 递延分摊计入",
            "",
            "与K7一致性校验：",
            "  递延分摊计入金额 应== K7递延收益(2401)本期分摊转入金额",
            "  差额|<0.01 → 一致；否则→不一致（红色标记）",
            "",
            "分类正确性：",
            "  - 与日常活动相关的政府补助 → 其他收益(6117,K10)",
            "  - 与日常活动无关的政府补助 → 营业外收入(6301,K12)",
            "",
            "K7索引：填写K7递延收益底稿对应行的GtIndexChip引用",
        ],
    },
}

router = create_cycle_import_export_router(
    tag="k10-import-export", api_prefix="k10", specs=_K10_SPECS
)
