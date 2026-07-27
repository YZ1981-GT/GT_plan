"""M8 一般风险准备 — 导入导出3端点（明细表/调整分录）.

POST /api/workpapers/{wp_id}/m8/export-template
POST /api/workpapers/{wp_id}/m8/export-data
POST /api/workpapers/{wp_id}/m8/import-data
"""
from __future__ import annotations
from typing import Any
from ._cycle_import_export_common import create_cycle_import_export_router

_DETAIL_HEADERS = ["序号", "项目名称", "期初余额", "本期增加", "本期减少", "期末余额", "备注"]
_DETAIL_KEYS = ["seq", "itemName", "beginBalance", "increase", "decrease", "endBalance", "remark"]

_ADJ_HEADERS = ["调整事项说明", "类别", "科目名称", "借方调整金额", "贷方调整金额", "索引", "备注"]
_ADJ_KEYS = ["description", "category", "accountName", "debitAmount", "creditAmount", "indexRef", "remark"]

_SPECS: dict[str, dict[str, Any]] = {
    "M8-2": {
        "item_id": "M8-2-rows",
        "storage_field": "remark",
        "title": "明细表M8-2",
        "headers": _DETAIL_HEADERS,
        "field_keys": _DETAIL_KEYS,
        "guidance": ["M8-2 编制说明", "", "请按项目逐行填写明细数据。"],
    },
    "M8-3": {
        "item_id": "M8-3-adj-entries",
        "storage_field": "remark",
        "title": "调整分录M8-3",
        "headers": _ADJ_HEADERS,
        "field_keys": _ADJ_KEYS,
        "guidance": ["M8-3 编制说明", "", "记录审计调整分录（AJE）和重分类分录（RJE）。"],
    },
}

router = create_cycle_import_export_router(
    tag="m8-import-export",
    api_prefix="m8",
    specs=_SPECS,
    storage_field="remark",
)
