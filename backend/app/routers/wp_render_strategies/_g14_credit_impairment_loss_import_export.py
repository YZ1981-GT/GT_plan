"""G14 信用减值损失 — 导入导出（G14-2 明细 / G14-3 调整）."""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

_G14_2_HEADERS = [
    "行键", "项目", "对应科目", "本期未审", "本期调整", "期初余额", "本期计提", "本期转回", "本期转销", "期末余额", "索引号",
]
_G14_2_KEYS = [
    "rowKey", "label", "provisionAccount", "currentUnadjusted", "currentAdjustment",
    "openingProvision", "currentProvision", "currentReversal", "currentWriteoff", "closingProvision", "indexRef",
]

_G14_3_HEADERS = [
    "调整事项说明", "类别", "报表项目", "科目名称", "附注项目", "借方调整金额", "贷方调整金额", "索引", "备注",
]
_G14_3_KEYS = [
    "description", "category", "reportItem", "accountName", "noteItem", "debitAmount", "creditAmount", "indexRef", "remark",
]

_G14_SPECS: dict[str, dict[str, Any]] = {
    "G14-2": {
        "item_id": "G14-detail-rows",
        "title": "G14-2 信用减值损失明细表",
        "headers": _G14_2_HEADERS,
        "field_keys": _G14_2_KEYS,
        "guidance": [
            "G14-2 明细表 编制说明",
            "",
            "固定9类减值来源行；期末=期初+计提+转回(带符号)-转销；核对列验证审定=计入损益。",
            "本期转回常以负数录入（K=计提+转回）。",
            "行键(rowKey)须与模板一致：notes/ar/rfin/othar/debt/othdebt/ltar/guarantee/other。",
        ],
    },
    "G14-3": {
        "item_id": "G14-aje-rows",
        "title": "G14-3 调整分录汇总表",
        "headers": _G14_3_HEADERS,
        "field_keys": _G14_3_KEYS,
        "guidance": [
            "G14-3 调整分录 编制说明",
            "",
            "类别填：账项调整/报表调整/重分类调整/其他；借贷须平衡。",
        ],
    },
}

router = create_cycle_import_export_router(
    tag="g14-import-export",
    api_prefix="g14",
    specs=_G14_SPECS,
    storage_field="remark",
)
