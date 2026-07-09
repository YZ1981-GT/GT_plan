"""H8 使用权资产 — 导入导出3端点（列结构对齐 requirements）.

POST /h8/export-template → 空白结构xlsx（根据sheet_name导出对应表模板）
POST /h8/export-data → 当前数据xlsx（含已填数据）
POST /h8/import-data → 解析xlsx→验证→写入checklist_responses

支持sheets: H8-2/H8-3/H8-12/H8-13/H8-14/H8-4/H8-7
科目编码: 1901使用权资产（借方/资产类）+ 累计折旧（贷方/备抵类）
CAS21新租赁准则核心底稿，与H9租赁负债强联动

Requirements: 3.3
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ─── H8-2 明细表（58列4区段：基础/初始/折旧/变更） ─────────────────────────────

_H8_2_HEADERS = [
    # 基础区段
    "序号", "租赁合同号", "承租资产名称", "承租资产类别", "出租方", "起始日", "到期日",
    "租赁期(月)", "是否短期租赁", "是否低价值资产",
    # 初始计量区段
    "H9初始计量", "初始直接费用", "租赁激励", "入账值(ROU)",
    "入账日期", "计量基础说明",
    # 折旧区段
    "折旧方法", "使用寿命(月)", "折旧期(月)", "残值",
    "期初原值", "期初累计折旧", "期初净值",
    "本期计提折旧", "本期减值",
    "期末原值", "期末累计折旧", "期末减值准备", "期末净值",
    # 变更区段
    "是否发生变更", "变更类型", "变更日期", "变更前ROU", "变更调整额", "变更后ROU",
    "是否终止", "终止日期", "终止原因",
    # 其他
    "对应H9编号", "GtIndexChip", "核查结论", "备注",
    # 补充列（对齐58列）
    "币种", "汇率", "本位币原值", "本位币折旧", "本位币净值",
    "所属部门", "使用地点", "合同总额", "年租金",
    "续租选择权", "购买选择权", "终止选择权",
    "担保余值", "未担保余值", "编制人", "复核人", "编制日期",
]
_H8_2_KEYS = [
    # 基础区段
    "seq", "contractNo", "assetName", "assetCategory", "lessor", "startDate", "endDate",
    "leaseTermMonths", "isShortTerm", "isLowValue",
    # 初始计量区段
    "h9InitialMeasurement", "directCost", "leaseIncentive", "rouAmount",
    "recognitionDate", "measurementBasis",
    # 折旧区段
    "depMethod", "usefulLifeMonths", "depPeriodMonths", "residualValue",
    "openingCost", "openingAccDep", "openingNetValue",
    "currentDepreciation", "currentImpairment",
    "closingCost", "closingAccDep", "closingImpairment", "closingNetValue",
    # 变更区段
    "hasModification", "modificationType", "modificationDate", "preModROU", "modAdjustment", "postModROU",
    "isTerminated", "terminationDate", "terminationReason",
    # 其他
    "h9Reference", "gtIndexChip", "conclusion", "remark",
    # 补充列
    "currency", "exchangeRate", "localCost", "localDep", "localNetValue",
    "department", "location", "totalContractAmount", "annualRent",
    "renewalOption", "purchaseOption", "terminationOption",
    "guaranteedResidual", "unguaranteedResidual", "preparedBy", "reviewedBy", "preparedDate",
]

# ─── H8-3 调整分录汇总（10列） ────────────────────────────────────────────────

_H8_3_HEADERS = [
    "序号", "调整事项说明", "类别", "科目代码", "科目名称",
    "摘要", "借方金额", "贷方金额", "索引", "备注",
]
_H8_3_KEYS = [
    "seq", "description", "entryType", "accountCode", "accountName",
    "summary", "debitAmount", "creditAmount", "indexRef", "remark",
]

# ─── H8-12 减少检查表（28列：租赁终止/提前退租） ──────────────────────────────

_H8_12_HEADERS = [
    "序号", "租赁合同号", "承租资产", "出租方", "原租赁期",
    "终止原因", "终止日期", "剩余租赁期(月)",
    "使用权资产原值", "累计折旧", "减值准备", "使用权净值",
    "租赁负债余额", "终止损益",
    "是否提前退租", "提前退租违约金", "审批文件",
    "对应H9终止确认", "H9联动状态",
    "会计处理借方科目", "会计处理借方金额", "会计处理贷方科目", "会计处理贷方金额",
    "税务处理", "是否关联交易", "信息披露",
    "核查结论", "备注",
]
_H8_12_KEYS = [
    "seq", "contractNo", "assetName", "lessor", "originalLeaseTerm",
    "terminationReason", "terminationDate", "remainingMonths",
    "rouCost", "accDepreciation", "impairmentProvision", "rouNetValue",
    "leaseliabilityBalance", "terminationGainLoss",
    "isEarlyTermination", "earlyTermPenalty", "approvalDoc",
    "h9TerminationRef", "h9LinkageStatus",
    "debitAccount", "debitAmount", "creditAccount", "creditAmount",
    "taxTreatment", "isRelatedParty", "disclosure",
    "conclusion", "remark",
]

# ─── H8-13 简化处理检查表（18列：短期/低价值租赁） ─────────────────────────────

_H8_13_HEADERS = [
    "序号", "租赁合同号", "承租资产", "出租方",
    "租赁期(月)", "年租金", "资产全新价值",
    "是否短期(≤12月)", "是否低价值(≤4万)", "简化处理类型",
    "费用确认方式", "本期费用金额", "累计费用金额",
    "是否符合简化条件", "不符合原因",
    "费用科目", "核查结论", "备注",
]
_H8_13_KEYS = [
    "seq", "contractNo", "assetName", "lessor",
    "leaseTermMonths", "annualRent", "newAssetValue",
    "isShortTerm", "isLowValue", "simplifiedType",
    "expenseRecognition", "currentExpense", "cumulativeExpense",
    "meetsSimplifiedCriteria", "nonComplianceReason",
    "expenseAccount", "conclusion", "remark",
]

# ─── H8-14 关联交易检查表（15列） ──────────────────────────────────────────────

_H8_14_HEADERS = [
    "序号", "租赁合同号", "承租资产", "关联方名称", "关联关系",
    "年租金", "市场租金参考", "价差率(%)",
    "定价依据", "决策程序", "审批文件",
    "公允性评价", "是否需调整",
    "核查结论", "备注",
]
_H8_14_KEYS = [
    "seq", "contractNo", "assetName", "relatedPartyName", "relationship",
    "annualRent", "marketRentRef", "priceDiffRate",
    "pricingBasis", "decisionProcess", "approvalDoc",
    "fairnessEvaluation", "needsAdjustment",
    "conclusion", "remark",
]

# ─── H8-4 租赁识别检查表（10列） ──────────────────────────────────────────────

_H8_4_HEADERS = [
    "序号", "租赁合同号", "承租资产", "出租方",
    "是否已识别资产", "是否获得控制权", "是否有实质替换权",
    "是否满足租赁定义", "判断说明",
    "备注",
]
_H8_4_KEYS = [
    "seq", "contractNo", "assetName", "lessor",
    "hasIdentifiedAsset", "hasControlRight", "hasSubstitutionRight",
    "meetsLeaseDefinition", "judgmentNote",
    "remark",
]

# ─── H8-7 租赁变更检查表（11列） ─────────────────────────────────────────────

_H8_7_HEADERS = [
    "序号", "租赁合同号", "承租资产", "变更日期",
    "变更类型", "原租赁条款", "新租赁条款",
    "是否单独租赁", "重新计量金额", "会计处理",
    "备注",
]
_H8_7_KEYS = [
    "seq", "contractNo", "assetName", "modificationDate",
    "modificationType", "originalTerms", "newTerms",
    "isSeparateLease", "remeasurementAmount", "accountingTreatment",
    "remark",
]

# ═══════════════════════════════════════════════════════════════════════════════

_H8_SPECS: dict[str, dict[str, Any]] = {
    "H8-2": {
        "item_id": "H8-2-rows",
        "title": "H8-2 使用权资产明细表",
        "headers": _H8_2_HEADERS,
        "field_keys": _H8_2_KEYS,
        "guidance": [
            "H8-2 使用权资产明细表 编制说明",
            "",
            "CAS21新租赁准则核心：使用权资产=租赁负债初始确认+初始直接费用-租赁激励。",
            "58列拆为4区段：基础信息(合同号/资产/出租方/起止日) | 初始计量(H9+直接-激励=入账) | 折旧(累计/本期/净值) | 变更(调整/终止)。",
            "每行对应一份租赁合同的使用权资产，与H9租赁负债明细一一对应。",
            "入账值(ROU) = H9初始计量 + 初始直接费用 - 租赁激励。",
            "折旧期 = min(租赁期, 使用寿命)。",
        ],
    },
    "H8-3": {
        "item_id": "H8-3-rows",
        "title": "H8-3 调整分录汇总表",
        "headers": _H8_3_HEADERS,
        "field_keys": _H8_3_KEYS,
        "guidance": [
            "H8-3 调整分录汇总 编制说明",
            "",
            "类别填 AJE（审计调整分录）或 RJE（重分类调整分录）。",
            "借方合计应等于贷方合计（借贷平衡）。",
            "科目代码以1901开头（使用权资产）或对应累计折旧科目。",
        ],
    },
    "H8-12": {
        "item_id": "H8-12-rows",
        "title": "H8-12 减少检查表（租赁终止/提前退租）",
        "headers": _H8_12_HEADERS,
        "field_keys": _H8_12_KEYS,
        "guidance": [
            "H8-12 使用权资产减少检查 编制说明",
            "",
            "终止损益 = 租赁负债余额 - 使用权资产净值。",
            "租赁终止时，使用权资产和租赁负债应同步终止确认。",
            "检查审批文件、违约金条款，确认会计处理正确性。",
            "必须与H9联动：H8-12终止确认 → H9租赁负债同步终止。",
        ],
    },
    "H8-13": {
        "item_id": "H8-13-rows",
        "title": "H8-13 简化处理的租赁检查表",
        "headers": _H8_13_HEADERS,
        "field_keys": _H8_13_KEYS,
        "guidance": [
            "H8-13 简化处理检查 编制说明",
            "",
            "CAS21豁免条件：短期租赁(≤12个月) 或 低价值资产(全新价值≤40,000元)。",
            "符合简化条件的租赁不确认使用权资产，直接费用化。",
            "不符合简化条件时应红色高亮，提示应确认使用权资产。",
            "底部统计：简化处理笔数/总年租金/应转为使用权资产笔数。",
        ],
    },
    "H8-14": {
        "item_id": "H8-14-rows",
        "title": "H8-14 关联交易检查表",
        "headers": _H8_14_HEADERS,
        "field_keys": _H8_14_KEYS,
        "guidance": [
            "H8-14 关联租赁检查 编制说明",
            "",
            "价差率 = (年租金 - 市场租金参考) / 市场租金参考 × 100%。",
            "关注关联租赁的公允性：价差率绝对值>10%时重点关注。",
            "检查决策程序完整性及关联交易信息披露充分性。",
        ],
    },
    "H8-4": {
        "item_id": "H8-4-rows",
        "title": "H8-4 租赁识别检查表",
        "headers": _H8_4_HEADERS,
        "field_keys": _H8_4_KEYS,
        "guidance": [
            "H8-4 租赁识别 编制说明",
            "",
            "CAS21租赁定义三要素：①已识别资产 ②获得控制权（主导使用+获取经济利益）③无实质替换权。",
            "逐份合同判断是否满足租赁定义，与H8-2明细行一一对应。",
            "每项结论为'是/否/不适用'+说明文本。",
        ],
    },
    "H8-7": {
        "item_id": "H8-7-rows",
        "title": "H8-7 租赁变更检查表",
        "headers": _H8_7_HEADERS,
        "field_keys": _H8_7_KEYS,
        "guidance": [
            "H8-7 租赁变更 编制说明",
            "",
            "变更类型：范围扩大/缩小/对价调整/期限延长/期限缩短/其他。",
            "判断是否构成单独租赁：①范围扩大 ②对价相当增加。",
            "非单独租赁的变更需重新计量使用权资产和租赁负债。",
        ],
    },
}

router = create_cycle_import_export_router(tag="h8-import-export", api_prefix="h8", specs=_H8_SPECS)
