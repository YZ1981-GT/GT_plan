"""H1 固定资产 — 导入导出3端点（列结构对齐 requirements）.

POST /h1/export-template → 空白结构xlsx（H1-2按4区段分sheet）
POST /h1/export-data → 当前数据xlsx（含公式结果）
POST /h1/import-data → 解析xlsx→验证→写入checklist_responses
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ─── H1-2 明细表（基础区段） ─────────────────────────────────────────────────

_H1_2_BASE_HEADERS = [
    "资产分类", "资产名称", "资产编号", "入账日期", "使用年限(年)", "残值率(%)", "折旧方法",
]
_H1_2_BASE_KEYS = [
    "assetCategory", "assetName", "assetCode", "acquisitionDate", "usefulLife", "salvageRate", "depMethod",
]

# ─── H1-2 明细表（原值变动区段） ─────────────────────────────────────────────

_H1_2_COST_HEADERS = [
    "资产分类", "资产名称", "期初原值", "本期增加", "本期减少", "期末原值",
]
_H1_2_COST_KEYS = [
    "assetCategory", "assetName", "costOpening", "costIncrease", "costDecrease", "costClosing",
]

# ─── H1-2 明细表（折旧区段） ─────────────────────────────────────────────────

_H1_2_DEP_HEADERS = [
    "资产分类", "资产名称", "累计折旧期初", "本期计提", "本期转回", "累计折旧期末", "净值",
]
_H1_2_DEP_KEYS = [
    "assetCategory", "assetName", "depOpening", "depProvision", "depReversal", "depClosing", "netValue",
]

# ─── H1-2 明细表（减值区段） ─────────────────────────────────────────────────

_H1_2_IMPAIR_HEADERS = [
    "资产分类", "资产名称", "减值准备期初", "本期计提", "本期转回", "减值准备期末",
]
_H1_2_IMPAIR_KEYS = [
    "assetCategory", "assetName", "impairOpening", "impairProvision", "impairReversal", "impairClosing",
]

# ─── H1-3 调整分录 ──────────────────────────────────────────────────────────

_H1_3_HEADERS = [
    "序号", "调整事项说明", "类别", "报表项目", "科目代码", "科目名称",
    "附注项目", "摘要", "借方金额", "贷方金额", "对方科目", "索引", "备注",
]
_H1_3_KEYS = [
    "seq", "description", "entryType", "reportItem", "accountCode", "accountName",
    "noteItem", "summary", "debitAmount", "creditAmount", "contraAccount", "indexRef", "remark",
]

# ─── H1-7 增加检查 ──────────────────────────────────────────────────────────

_H1_7_HEADERS = [
    "序号", "资产名称", "资产编号", "入账日期", "原值", "合同", "发票",
    "验收单", "付款凭证", "资本化判断", "入账科目", "折旧起算日", "审计结论", "备注",
]
_H1_7_KEYS = [
    "seq", "assetName", "assetCode", "acquisitionDate", "originalCost", "contract", "invoice",
    "acceptance", "payment", "capitalization", "accountEntry", "depStartDate", "conclusion", "remark",
]

# ─── H1-8 减少检查 ──────────────────────────────────────────────────────────

_H1_8_HEADERS = [
    "序号", "资产名称", "资产编号", "处置日期", "处置方式", "原值", "累计折旧",
    "减值准备", "处置收入", "净值", "处置费用", "处置损益", "审批文件", "结论", "备注",
]
_H1_8_KEYS = [
    "seq", "assetName", "assetCode", "disposalDate", "disposalType", "originalCost", "accDepreciation",
    "impairment", "disposalIncome", "netValue", "disposalCost", "disposalGainLoss", "approvalDoc", "conclusion", "remark",
]

# ─── H1-10 盘点检查 ─────────────────────────────────────────────────────────

_H1_10_HEADERS = [
    "序号", "资产名称", "资产编号", "存放地点", "账面原值", "账面净值",
    "实际状态", "铭牌核对", "数量核对", "成色评估", "盘点结果",
    "差异原因", "差异金额", "处理建议", "盘点人", "备注",
]
_H1_10_KEYS = [
    "seq", "assetName", "assetCode", "location", "bookCost", "bookNetValue",
    "actualStatus", "plateCheck", "qtyCheck", "conditionEval", "stocktakeResult",
    "diffReason", "diffAmount", "suggestion", "inspector", "remark",
]

# ─── H1-16 房屋权属 ─────────────────────────────────────────────────────────

_H1_16_HEADERS = [
    "序号", "资产名称", "坐落地址", "建筑面积", "土地面积", "产权证号",
    "发证日期", "权利人", "是否被审计单位", "用途", "是否抵押",
    "抵押权人", "抵押金额", "抵押到期日", "账面原值", "产权证载原值",
    "差异", "差异原因", "是否限制", "结论", "备注",
]
_H1_16_KEYS = [
    "seq", "assetName", "address", "buildingArea", "landArea", "titleNo",
    "issueDate", "owner", "isAuditee", "purpose", "isMortgaged",
    "mortgagee", "mortgageAmount", "mortgageExpiry", "bookValue", "certValue",
    "difference", "diffReason", "isRestricted", "conclusion", "remark",
]

# ─── H1-19 经营租出 ─────────────────────────────────────────────────────────

_H1_19_HEADERS = [
    "序号", "承租方", "资产名称", "原值", "净值", "租赁起始日", "租赁终止日",
    "租赁期限(月)", "年租金", "月租金", "总租金收入", "折旧分摊", "维修费用",
    "租赁净收益", "收益率(%)", "市场租金参考", "差异", "合同编号", "是否关联", "结论", "备注",
]
_H1_19_KEYS = [
    "seq", "lessee", "assetName", "originalCost", "netValue", "leaseStart", "leaseEnd",
    "leaseTerm", "annualRent", "monthlyRent", "totalRentIncome", "depAlloc", "maintenanceCost",
    "netLeaseIncome", "returnRate", "marketRentRef", "rentDiff", "contractNo", "isRelated", "conclusion", "remark",
]

# ═══════════════════════════════════════════════════════════════════════════════

_H1_SPECS: dict[str, dict[str, Any]] = {
    "H1-2-base": {
        "item_id": "H1-2-rows",
        "title": "H1-2 明细表（基础信息）",
        "headers": _H1_2_BASE_HEADERS,
        "field_keys": _H1_2_BASE_KEYS,
        "guidance": [
            "H1-2 固定资产明细表 — 基础区段 编制说明",
            "",
            "折旧方法可选：直线法/双倍余额递减/年数总和法/工作量法。",
            "残值率通常为3%~5%。使用年限参考CAS4及税法规定。",
        ],
    },
    "H1-2-cost": {
        "item_id": "H1-2-rows",
        "title": "H1-2 明细表（原值变动）",
        "headers": _H1_2_COST_HEADERS,
        "field_keys": _H1_2_COST_KEYS,
        "guidance": [
            "H1-2 原值变动区段 编制说明",
            "",
            "期末原值=期初原值+本期增加-本期减少（资产类借方科目1601）。",
        ],
    },
    "H1-2-dep": {
        "item_id": "H1-2-rows",
        "title": "H1-2 明细表（折旧）",
        "headers": _H1_2_DEP_HEADERS,
        "field_keys": _H1_2_DEP_KEYS,
        "guidance": [
            "H1-2 折旧区段 编制说明",
            "",
            "累计折旧期末=期初+本期计提-本期转回（备抵类贷方科目1602）。",
            "净值=期末原值-累计折旧期末-减值准备期末。",
        ],
    },
    "H1-2-impair": {
        "item_id": "H1-2-rows",
        "title": "H1-2 明细表（减值）",
        "headers": _H1_2_IMPAIR_HEADERS,
        "field_keys": _H1_2_IMPAIR_KEYS,
        "guidance": [
            "H1-2 减值区段 编制说明",
            "",
            "减值准备期末=期初+本期计提-本期转回。",
            "固定资产减值损失一经确认不得转回（CAS8）。",
        ],
    },
    "H1-3": {
        "item_id": "H1-3-rows",
        "title": "H1-3 调整分录汇总表",
        "headers": _H1_3_HEADERS,
        "field_keys": _H1_3_KEYS,
        "guidance": [
            "H1-3 调整分录 编制说明",
            "",
            "类别填 AJE（审计调整分录）或 RJE（重分类调整分录）。",
            "借方合计应等于贷方合计（借贷平衡）。",
        ],
    },
    "H1-7": {
        "item_id": "H1-7-rows",
        "title": "H1-7 固定资产增加检查表",
        "headers": _H1_7_HEADERS,
        "field_keys": _H1_7_KEYS,
        "guidance": [
            "H1-7 增加检查 编制说明",
            "",
            "逐笔核对新增资产的入账依据(合同/发票/验收单/付款凭证)。",
            "资本化判断参照CAS4确认条件。",
        ],
    },
    "H1-8": {
        "item_id": "H1-8-rows",
        "title": "H1-8 固定资产减少检查表",
        "headers": _H1_8_HEADERS,
        "field_keys": _H1_8_KEYS,
        "guidance": [
            "H1-8 减少检查 编制说明",
            "",
            "处置损益=处置收入-净值-处置费用。",
            "处置方式：出售/报废/捐赠/盘亏/非货币资产交换。",
        ],
    },
    "H1-10": {
        "item_id": "H1-10-rows",
        "title": "H1-10 盘点检查表",
        "headers": _H1_10_HEADERS,
        "field_keys": _H1_10_KEYS,
        "guidance": [
            "H1-10 固定资产盘点 编制说明",
            "",
            "盘点结果：账实相符/盘盈/盘亏。",
            "实际状态：在用/闲置/报废。",
        ],
    },
    "H1-16": {
        "item_id": "H1-16-rows",
        "title": "H1-16 房屋建筑物权属检查表",
        "headers": _H1_16_HEADERS,
        "field_keys": _H1_16_KEYS,
        "guidance": [
            "H1-16 房屋权属 编制说明",
            "",
            "差异=账面原值-产权证载原值。",
            "权利人非被审计单位时标记权属异常。",
        ],
    },
    "H1-19": {
        "item_id": "H1-19-rows",
        "title": "H1-19 经营租出固定资产检查表",
        "headers": _H1_19_HEADERS,
        "field_keys": _H1_19_KEYS,
        "guidance": [
            "H1-19 经营租出 编制说明",
            "",
            "月租金=年租金/12；租赁净收益=总租金-折旧-维修费。",
            "收益率=净收益/原值×100%。",
        ],
    },
}

router = create_cycle_import_export_router(tag="h1-import-export", api_prefix="h1", specs=_H1_SPECS)
