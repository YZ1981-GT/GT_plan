"""G12 净敞口套期收益 — 导入导出（G12-2 / G12-3 / G12-4 / G12-6）."""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

_G12_2_HEADERS = [
    "序号", "套期关系编号", "套期类型", "被套期项目", "套期工具", "指定日期", "到期日",
    "被套期风险", "套期比率", "套期工具FV变动", "被套期项目FV变动", "套期无效部分",
    "计入损益金额", "有效性评估结论", "索引", "备注",
]
_G12_2_KEYS = [
    "seq", "hedgeRelationId", "hedgeType", "hedgedItem", "hedgingInstrument", "designationDate",
    "maturityDate", "hedgedRisk", "hedgeRatio", "instrumentFVChange", "itemFVChange",
    "ineffectiveness", "profitLossAmount", "effectivenessConclusion", "indexRef", "remark",
]

_G12_3_HEADERS = [
    "序号", "分录类型", "日期", "摘要", "科目代码", "科目名称", "借方", "贷方", "编制人", "备注",
]
_G12_3_KEYS = [
    "seq", "entryType", "date", "summary", "accountCode", "accountName", "debitAmount", "creditAmount",
    "preparedBy", "remark",
]

_G12_4_HEADERS = [
    "套期关系编号", "套期工具名称", "工具类型", "工具期初FV", "工具期末FV", "工具FV变动",
    "估值方法", "公允价值层次", "估值来源", "被套期项目名称", "项目类型", "项目期初FV",
    "项目期末FV", "项目FV变动", "风险因素", "测试方法", "有效性结论",
]
_G12_4_KEYS = [
    "hedgeRelationId", "instrumentName", "instrumentType", "instrumentOpeningFV", "instrumentClosingFV",
    "instrumentFVChange", "instrumentValuationMethod", "instrumentFVLevel", "instrumentValuationSource",
    "itemName", "itemType", "itemOpeningFV", "itemClosingFV", "itemFVChange", "itemRiskFactor",
    "itemTestMethod", "itemEffectivenessConclusion",
]

_G12_6_HEADERS = [
    "序号", "日期", "凭证编号", "业务内容", "关联套期关系", "对方科目", "借方", "贷方",
    "支持性文件描述", "核对1-原始凭证", "核对2-授权批准", "核对3-账务处理", "核对4-套期指定",
    "核对5-估值依据", "索引号", "是否异常", "异常说明", "风险等级", "备注",
]
_G12_6_KEYS = [
    "seq", "voucherDate", "voucherNo", "businessContent", "hedgeRelationId", "counterAccount",
    "debitAmount", "creditAmount", "supportingDocDesc", "check1OriginalComplete", "check2Authorization",
    "check3Accounting", "check4HedgeDesignation", "check5FVValuation", "indexNo", "isAbnormal",
    "abnormalDesc", "riskLevel", "remark",
]

_G12_SPECS: dict[str, dict[str, Any]] = {
    "G12-2": {
        "item_id": "G12-hedge-detail-rows",
        "title": "G12-2 套期关系明细表",
        "headers": _G12_2_HEADERS,
        "field_keys": _G12_2_KEYS,
        "guidance": [
            "G12-2 套期关系明细 编制说明",
            "",
            "套期无效部分=|套期工具FV变动-被套期项目FV变动|；有效性结论与G12-4交叉验证。",
        ],
    },
    "G12-3": {
        "item_id": "G12-aje-rows",
        "title": "G12-3 调整分录汇总表",
        "headers": _G12_3_HEADERS,
        "field_keys": _G12_3_KEYS,
        "guidance": [
            "G12-3 调整分录 编制说明",
            "",
            "类型填 AJE/RJE；借贷须平衡；可同步至审定表调整数。",
        ],
    },
    "G12-4": {
        "item_id": "G12-fv-test-rows",
        "title": "G12-4 公允价值测试表",
        "headers": _G12_4_HEADERS,
        "field_keys": _G12_4_KEYS,
        "guidance": [
            "G12-4 公允价值测试 编制说明",
            "",
            "FV变动=期末-期初；套期工具侧与被套期项目侧通过套期关系编号关联。",
        ],
    },
    "G12-6": {
        "item_id": "G12-voucher-rows",
        "title": "G12-6 凭证检查表",
        "headers": _G12_6_HEADERS,
        "field_keys": _G12_6_KEYS,
        "guidance": [
            "G12-6 凭证检查 编制说明",
            "",
            "核对列填 ✓/✗；任一✗则是否异常=是；借贷须平衡。",
        ],
    },
}

router = create_cycle_import_export_router(
    tag="g12-import-export",
    api_prefix="g12",
    specs=_G12_SPECS,
    storage_field="remark",
)
