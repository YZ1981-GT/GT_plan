"""N1 递延所得税资产 — 导入导出3端点（明细表/调整分录）.

POST /api/workpapers/{wp_id}/n1/export-template
POST /api/workpapers/{wp_id}/n1/export-data
POST /api/workpapers/{wp_id}/n1/import-data
"""
from __future__ import annotations
from typing import Any
from ._cycle_import_export_common import create_cycle_import_export_router

_DETAIL_HEADERS = ["序号", "项目名称", "期初余额", "本期增加", "本期减少", "期末余额", "备注"]
_DETAIL_KEYS = ["seq", "itemName", "beginBalance", "increase", "decrease", "endBalance", "remark"]

_ADJ_HEADERS = ["调整事项说明", "类别", "科目名称", "借方调整金额", "贷方调整金额", "索引", "备注"]
_ADJ_KEYS = ["description", "category", "accountName", "debitAmount", "creditAmount", "indexRef", "remark"]

_SPECS: dict[str, dict[str, Any]] = {
    "N1-2": {
        "item_id": "N1-2-detail-rows",
        "storage_field": "remark",
        "title": "明细表N1-2",
        "headers": _DETAIL_HEADERS,
        "field_keys": _DETAIL_KEYS,
        "guidance": ["N1-2 编制说明", "", "请按项目逐行填写明细数据。"],
    },
    "N1-3": {
        "item_id": "N1-3-adj-entries",
        "storage_field": "remark",
        "title": "调整分录N1-3",
        "headers": _ADJ_HEADERS,
        "field_keys": _ADJ_KEYS,
        "guidance": ["N1-3 编制说明", "", "记录审计调整分录（AJE）和重分类分录（RJE）。"],
    },
}

router = create_cycle_import_export_router(
    tag="n1-import-export",
    api_prefix="n1",
    specs=_SPECS,
    storage_field="remark",
)
