"""G13 公允价值变动收益 — 导入导出（G13-2 明细 / G13-3 调整）."""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

_G13_2_HEADERS = [
    "金融工具名称", "所属科目", "金融工具类型", "期初公允价值", "期末公允价值",
    "本期未审数", "调整数", "成本", "本期公允价值变动", "累计公允价值变动",
    "公允价值", "计入损益", "源科目索引", "交叉验证结论", "备注",
]
_G13_2_KEYS = [
    "instrumentName", "belongAccount", "instrumentType", "openingFairValue", "closingFairValue",
    "currentUnadjusted", "adjustment", "cost", "periodFvChange", "cumulativeFvChange",
    "fairValue", "amountInPl", "sourceIndex", "crossVerification", "remark",
]

_G13_3_HEADERS = [
    "调整事项说明", "类别", "报表项目", "科目编码", "科目名称", "附注项目",
    "所属科目", "借方调整金额", "贷方调整金额", "索引", "备注",
]
_G13_3_KEYS = [
    "description", "category", "reportItem", "accountCode", "accountName", "noteItem",
    "belongAccount", "debitAmount", "creditAmount", "indexRef", "remark",
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
            "损益侧：FV变动=期末-期初；审定=未审+调整。",
            "对应科目侧：成本+累计公允价值变动=公允价值；计入损益应等于审定数（致同核对列）。",
            "与源科目 G1/G8/G9/G10/H3 交叉验证后汇总至 G13-1。",
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
            "对齐 Excel：调整事项说明 / 类别(账项调整·报表调整·其他) / 报表项目 / 科目 / 附注项目 / 所属科目 / 借贷 / 索引 / 备注。",
            "账项调整汇总 6101 贷−借净额按所属科目回写 G13-2；报表调整不回写；整表借贷须平衡。",
        ],
    },
}

router = create_cycle_import_export_router(
    tag="g13-import-export",
    api_prefix="g13",
    specs=_G13_SPECS,
    storage_field="remark",
)
