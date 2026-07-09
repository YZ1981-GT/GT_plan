"""H4 工程物资 — 导入导出3端点（列结构对齐 requirements）.

POST /h4/export-template → 空白结构xlsx（根据sheet_name导出对应表模板）
POST /h4/export-data → 当前数据xlsx（含已填数据）
POST /h4/import-data → 解析xlsx→验证→写入checklist_responses

支持sheets: H4-2/H4-3/H4-4/H4-5/H4-6/H4-9
科目编码: 1605工程物资（借方/资产类）

Requirements: 3.8, 4.6
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ─── H4-2 明细表（物资分类/入库/出库） ──────────────────────────────────────

_H4_2_HEADERS = [
    "物资分类", "名称", "规格", "数量", "单位", "供应商",
    "期初金额", "本期采购", "其他增加", "领用出库", "退货", "报废", "其他减少",
]
_H4_2_KEYS = [
    "category", "name", "spec", "quantity", "unit", "supplier",
    "openingAmount", "purchased", "otherIncrease", "usedOut", "returned", "scrapped", "otherDecrease",
]

# ─── H4-3 调整分录汇总 ─────────────────────────────────────────────────────

_H4_3_HEADERS = [
    "调整事项说明", "类别", "科目代码", "科目名称",
    "摘要", "借方金额", "贷方金额", "索引", "备注",
]
_H4_3_KEYS = [
    "description", "entryType", "accountCode", "accountName",
    "summary", "debitAmount", "creditAmount", "indexRef", "remark",
]

# ─── H4-4 增加检查表 ───────────────────────────────────────────────────────

_H4_4_HEADERS = [
    "物资名称", "规格型号", "数量", "单价", "金额", "供应商",
    "合同编号", "入库日期", "入库单号", "发票号", "发票金额",
    "验收人", "核查结论", "备注",
]
_H4_4_KEYS = [
    "materialName", "specModel", "quantity", "unitPrice", "amount", "supplier",
    "contractNo", "receiptDate", "receiptNo", "invoiceNo", "invoiceAmount",
    "inspector", "conclusion", "remark",
]

# ─── H4-5 减少检查表 ───────────────────────────────────────────────────────

_H4_5_HEADERS = [
    "物资名称", "规格", "数量", "金额", "减少原因", "减少日期",
    "领料单号", "领用部门", "领用工程项目", "审批人",
    "对应H2编号", "核查结论", "备注",
]
_H4_5_KEYS = [
    "materialName", "spec", "quantity", "amount", "reason", "decreaseDate",
    "requisitionNo", "department", "projectName", "approver",
    "h2Reference", "conclusion", "remark",
]

# ─── H4-6 盘点检查表 ───────────────────────────────────────────────────────

_H4_6_HEADERS = [
    "物资名称", "规格", "账面数量", "账面金额",
    "盘点数量", "盘点金额", "存放位置", "盘点日期", "备注",
]
_H4_6_KEYS = [
    "materialName", "spec", "bookQuantity", "bookAmount",
    "countQuantity", "countAmount", "location", "countDate", "remark",
]

# ─── H4-9 关联交易检查表 ───────────────────────────────────────────────────

_H4_9_HEADERS = [
    "物资名称", "交易对手", "关联关系", "交易金额", "市场价格",
    "合同日期", "合同编号", "定价依据", "审批流程",
    "是否公允", "决策程序", "披露情况", "核查结论", "备注",
]
_H4_9_KEYS = [
    "materialName", "counterparty", "relationship", "transAmount", "marketPrice",
    "contractDate", "contractNo", "pricingBasis", "approvalProcess",
    "isFair", "decisionProcess", "disclosure", "conclusion", "remark",
]

# ═══════════════════════════════════════════════════════════════════════════════

_H4_SPECS: dict[str, dict[str, Any]] = {
    "H4-2": {
        "item_id": "H4-2-rows",
        "title": "H4-2 工程物资明细表",
        "headers": _H4_2_HEADERS,
        "field_keys": _H4_2_KEYS,
        "guidance": [
            "H4-2 工程物资明细表 编制说明",
            "",
            "物资分类：按工程物资类别分类填列。",
            "期末余额=期初金额+本期采购+其他增加-领用出库-退货-报废-其他减少。",
            "领用出库联动H2在建工程，需填写对应H2编号。",
        ],
    },
    "H4-3": {
        "item_id": "H4-3-rows",
        "title": "H4-3 调整分录汇总表",
        "headers": _H4_3_HEADERS,
        "field_keys": _H4_3_KEYS,
        "guidance": [
            "H4-3 调整分录汇总 编制说明",
            "",
            "类别填 AJE（审计调整分录）或 RJE（重分类调整分录）。",
            "借方合计应等于贷方合计（借贷平衡）。",
            "科目代码以1605开头（工程物资）。",
        ],
    },
    "H4-4": {
        "item_id": "H4-4-rows",
        "title": "H4-4 增加检查表",
        "headers": _H4_4_HEADERS,
        "field_keys": _H4_4_KEYS,
        "guidance": [
            "H4-4 工程物资增加检查 编制说明",
            "",
            "逐笔核对入库单、发票、合同的一致性。",
            "差异=金额-发票金额，差异不为零时需说明原因。",
        ],
    },
    "H4-5": {
        "item_id": "H4-5-rows",
        "title": "H4-5 减少检查表",
        "headers": _H4_5_HEADERS,
        "field_keys": _H4_5_KEYS,
        "guidance": [
            "H4-5 工程物资减少检查 编制说明",
            "",
            "减少原因：领用出库/退货/报废/盘亏/其他。",
            "领用出库须填写对应H2编号（H2在建工程关联）。",
            "检查审批文件、领料单据的完整性。",
        ],
    },
    "H4-6": {
        "item_id": "H4-6-rows",
        "title": "H4-6 盘点检查表",
        "headers": _H4_6_HEADERS,
        "field_keys": _H4_6_KEYS,
        "guidance": [
            "H4-6 工程物资盘点检查 编制说明",
            "",
            "差异数量=盘点数量-账面数量；差异金额=盘点金额-账面金额。",
            "差异不为零时需调查原因并跟踪处理。",
        ],
    },
    "H4-9": {
        "item_id": "H4-9-rows",
        "title": "H4-9 关联交易检查表",
        "headers": _H4_9_HEADERS,
        "field_keys": _H4_9_KEYS,
        "guidance": [
            "H4-9 工程物资关联交易检查 编制说明",
            "",
            "价差率=(交易金额-市场价格)/市场价格×100%。",
            "价差率绝对值>10%时重点关注定价合理性。",
            "关注决策程序完整性及信息披露充分性。",
        ],
    },
}

router = create_cycle_import_export_router(tag="h4-import-export", api_prefix="h4", specs=_H4_SPECS)
