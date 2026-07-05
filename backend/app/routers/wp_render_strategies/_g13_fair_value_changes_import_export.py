"""G13 公允价值变动收益 — 导入导出（G13-2 明细 / G13-3 调整）."""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

_G13_2_HEADERS = [
    "金融工具名称", "所属科目", "金融工具类型", "期初公允价值", "期末公允价值",
    "本期未审数", "调整数", "源科目索引", "交叉验证结论", "备注",
]
_G13_2_KEYS = [
    "instrumentName", "belongAccount", "instrumentType", "openingFairValue", "closingFairValue",
    "currentUnadjusted", "adjustment", "sourceIndex", "crossVerification", "remark",
]

_G13_3_HEADERS = [
    "类型", "日期", "摘要", "科目编码", "科目名称", "借方", "贷方", "编制人", "备注",
]
_G13_3_KEYS = [
    "entryType", "date", "summary", "accountCode", "accountName", "debitAmount", "creditAmount", "preparedBy", "remark",
]

_G13_SPECS: dict[str, dict[str, Any]] = {
    "G13-2": {
        "item_id": "G13-detail-rows",
        "title": "G13-2 公允价值变动明细表",
        "headers": _G13_2_HEADERS,
        "field_keys": _G13_2_KEYS,
        "guidance": [
            "G13-2 明细表 编制说明",
            "",
            "FV变动=期末-期初；审定=未审+调整；与源科目 G1/G8/G9/G10 交叉验证。",
        ],
    },
    "G13-3": {
        "item_id": "G13-aje-rows",
        "title": "G13-3 调整分录汇总表",
        "headers": _G13_3_HEADERS,
        "field_keys": _G13_3_KEYS,
        "guidance": [
            "G13-3 调整分录 编制说明",
            "",
            "类型填 AJE/RJE；借贷须平衡；可同步至明细表调整数。",
        ],
    },
}

router = create_cycle_import_export_router(
    tag="g13-import-export",
    api_prefix="g13",
    specs=_G13_SPECS,
    storage_field="remark",
)
