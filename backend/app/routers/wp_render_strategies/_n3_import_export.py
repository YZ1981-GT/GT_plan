"""N3 递延所得税负债 — 导入导出3端点（明细表/调整分录）.

POST /api/workpapers/{wp_id}/n3/export-template
POST /api/workpapers/{wp_id}/n3/export-data
POST /api/workpapers/{wp_id}/n3/import-data

🔴 storage_field 修正（2026-10-06）：N3 前端 ``useN3FormData.setField()`` 全部写
``checklist_responses.conclusion``，导入导出必须与前端同列，否则导入后前端显示不更新。
``dual_write=True`` 同时写 remark 列保证导出 fallback 兼容（export 先读 conclusion
再 fallback remark，见 ``_cycle_import_export_common._load_rows_fallback``）。
"""
from __future__ import annotations
from typing import Any
from ._cycle_import_export_common import create_cycle_import_export_router

_DETAIL_HEADERS = ["序号", "项目名称", "期初余额", "本期增加", "本期减少", "期末余额", "备注"]
_DETAIL_KEYS = ["seq", "itemName", "beginBalance", "increase", "decrease", "endBalance", "remark"]

_ADJ_HEADERS = ["调整事项说明", "类别", "科目名称", "借方调整金额", "贷方调整金额", "索引", "备注"]
_ADJ_KEYS = ["description", "category", "accountName", "debitAmount", "creditAmount", "indexRef", "remark"]

_SPECS: dict[str, dict[str, Any]] = {
    "N3-2": {
        "item_id": "N3-2-rows",
        "storage_field": "conclusion",
        "dual_write": True,
        "title": "明细表N3-2",
        "headers": _DETAIL_HEADERS,
        "field_keys": _DETAIL_KEYS,
        "guidance": ["N3-2 编制说明", "", "请按项目逐行填写明细数据。"],
    },
    "N3-3": {
        "item_id": "N3-3-adj-entries",
        "storage_field": "conclusion",
        "dual_write": True,
        "title": "调整分录N3-3",
        "headers": _ADJ_HEADERS,
        "field_keys": _ADJ_KEYS,
        "guidance": ["N3-3 编制说明", "", "记录审计调整分录（AJE）和重分类分录（RJE）。"],
    },
}

router = create_cycle_import_export_router(
    tag="n3-import-export",
    api_prefix="n3",
    specs=_SPECS,
    storage_field="conclusion",
)
