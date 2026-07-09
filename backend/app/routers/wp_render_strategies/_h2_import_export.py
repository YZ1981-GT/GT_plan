"""H2 在建工程 — 导入导出3端点（列结构对齐 requirements）.

POST /h2/export-template → 空白结构xlsx（H2-2按3区段分sheet）
POST /h2/export-data → 当前数据xlsx（含公式结果）
POST /h2/import-data → 解析xlsx→验证→写入checklist_responses
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ─── H2-2 明细表（基本区段） ─────────────────────────────────────────────────

_H2_2_BASE_HEADERS = [
    "工程名称", "工程编号", "预算金额", "开工日期", "预计完工日期",
    "工程负责人", "施工单位", "合同金额", "资金来源",
]
_H2_2_BASE_KEYS = [
    "projectName", "projectCode", "budgetAmount", "startDate", "plannedEndDate",
    "projectManager", "contractor", "contractAmount", "fundingSource",
]

# ─── H2-2 明细表（增减区段） ─────────────────────────────────────────────────

_H2_2_CHANGE_HEADERS = [
    "工程名称", "工程编号", "期初余额", "本期增加-材料", "本期增加-人工",
    "本期增加-费用", "本期增加-利息", "本期增加-其他", "本期增加-小计",
    "本期减少-转固", "本期减少-报废", "本期减少-其他", "本期减少-小计", "期末余额",
]
_H2_2_CHANGE_KEYS = [
    "projectName", "projectCode", "openingBalance", "increaseMaterial", "increaseLabor",
    "increaseExpense", "increaseInterest", "increaseOther", "increaseSubtotal",
    "decreaseTransfer", "decreaseDisposal", "decreaseOther", "decreaseSubtotal", "closingBalance",
]

# ─── H2-2 明细表（竣工结转区段） ────────────────────────────────────────────

_H2_2_TRANSFER_HEADERS = [
    "工程名称", "工程编号", "完工进度(%)", "实际完工日期", "转固日期",
    "转入资产类别", "转固金额", "资本化利息", "累计投入", "是否验收",
    "CAS4条件1", "CAS4条件2", "CAS4条件3", "CAS4条件4", "CAS4条件5", "转固结论",
]
_H2_2_TRANSFER_KEYS = [
    "projectName", "projectCode", "completionRate", "actualEndDate", "transferDate",
    "targetAssetCategory", "transferAmount", "capitalizedInterest", "accumulatedCost", "isAccepted",
    "cas4Cond1", "cas4Cond2", "cas4Cond3", "cas4Cond4", "cas4Cond5", "transferConclusion",
]

# ─── H2-3 调整分录 ──────────────────────────────────────────────────────────

_H2_3_HEADERS = [
    "序号", "调整事项说明", "类别", "报表项目", "科目代码", "科目名称",
    "附注项目", "摘要", "借方金额", "贷方金额", "对方科目", "索引", "备注",
]
_H2_3_KEYS = [
    "seq", "description", "entryType", "reportItem", "accountCode", "accountName",
    "noteItem", "summary", "debitAmount", "creditAmount", "contraAccount", "indexRef", "remark",
]

# ─── H2-5 转固时点检查 ──────────────────────────────────────────────────────

_H2_5_HEADERS = [
    "序号", "工程名称", "工程编号", "预算金额", "实际支出", "完工日期",
    "转固日期", "延迟天数", "CAS4条件1-实体建造完成", "CAS4条件2-达到设计要求",
    "CAS4条件3-试运转正常", "CAS4条件4-支出已确定", "CAS4条件5-可使用状态",
    "五条件判定", "转固金额", "目标科目", "审计结论", "备注",
]
_H2_5_KEYS = [
    "seq", "projectName", "projectCode", "budgetAmount", "actualCost", "completionDate",
    "transferDate", "delayDays", "cas4Cond1", "cas4Cond2",
    "cas4Cond3", "cas4Cond4", "cas4Cond5",
    "cas4AllMet", "transferAmount", "targetAccount", "conclusion", "remark",
]

# ─── H2-7 工程造价比较 ──────────────────────────────────────────────────────

_H2_7_HEADERS = [
    "序号", "工程名称", "工程编号", "预算金额", "合同金额", "实际成本",
    "造价差异额", "造价差异率(%)", "超预算额", "超预算率(%)",
    "合同vs实际差异", "变更签证金额", "索赔金额", "结算金额", "审计结论", "备注",
]
_H2_7_KEYS = [
    "seq", "projectName", "projectCode", "budgetAmount", "contractAmount", "actualCost",
    "costDiffAmount", "costDiffRate", "overBudgetAmount", "overBudgetRate",
    "contractVsActualDiff", "variationAmount", "claimAmount", "settlementAmount", "conclusion", "remark",
]

# ─── H2-8 增加检查 ──────────────────────────────────────────────────────────

_H2_8_HEADERS = [
    "序号", "工程名称", "入账日期", "金额", "供应商/施工方", "合同编号",
    "发票号", "验收单", "付款凭证", "资本化判断", "入账科目",
    "资本化利息", "审计结论", "备注",
]
_H2_8_KEYS = [
    "seq", "projectName", "entryDate", "amount", "supplier", "contractNo",
    "invoiceNo", "acceptance", "payment", "capitalization", "accountEntry",
    "capitalizedInterest", "conclusion", "remark",
]

# ─── H2-9 减少检查 ──────────────────────────────────────────────────────────

_H2_9_HEADERS = [
    "序号", "工程名称", "减少日期", "减少方式", "减少金额", "原因说明",
    "审批文件", "处置收入", "处置费用", "处置损益", "审计结论", "备注",
]
_H2_9_KEYS = [
    "seq", "projectName", "decreaseDate", "decreaseType", "decreaseAmount", "reason",
    "approvalDoc", "disposalIncome", "disposalCost", "disposalGainLoss", "conclusion", "remark",
]

# ─── H2-13 盘点检查 ─────────────────────────────────────────────────────────

_H2_13_HEADERS = [
    "序号", "工程名称", "工程编号", "所在地点", "账面金额", "实地状态",
    "施工进度", "是否停工", "停工原因", "停工起始日", "物资堆放",
    "安全措施", "盘点结果", "差异原因", "审计结论", "备注",
]
_H2_13_KEYS = [
    "seq", "projectName", "projectCode", "location", "bookAmount", "fieldStatus",
    "constructionProgress", "isStopped", "stopReason", "stopStartDate", "materialStorage",
    "safetyMeasure", "stocktakeResult", "diffReason", "conclusion", "remark",
]

# ─── H2-17 关联交易 ─────────────────────────────────────────────────────────

_H2_17_HEADERS = [
    "序号", "工程名称", "关联方名称", "关联关系", "交易内容", "交易金额",
    "定价方式", "市场价格", "价格差异", "差异率(%)", "是否公允",
    "审批程序", "披露情况", "审计结论", "备注",
]
_H2_17_KEYS = [
    "seq", "projectName", "relatedParty", "relationship", "transactionContent", "transactionAmount",
    "pricingMethod", "marketPrice", "priceDiff", "priceDiffRate", "isFair",
    "approvalProcess", "disclosureStatus", "conclusion", "remark",
]

# ═══════════════════════════════════════════════════════════════════════════════

_H2_SPECS: dict[str, dict[str, Any]] = {
    "H2-2-base": {
        "item_id": "H2-2-rows",
        "title": "H2-2 在建工程明细表（基本信息）",
        "headers": _H2_2_BASE_HEADERS,
        "field_keys": _H2_2_BASE_KEYS,
        "guidance": [
            "H2-2 在建工程明细表 — 基本区段 编制说明",
            "",
            "记录各在建工程项目的基本参数：预算/开工/施工/资金来源。",
            "预算金额以批准的可行性研究报告或概算为准。",
        ],
    },
    "H2-2-change": {
        "item_id": "H2-2-rows",
        "title": "H2-2 在建工程明细表（增减变动）",
        "headers": _H2_2_CHANGE_HEADERS,
        "field_keys": _H2_2_CHANGE_KEYS,
        "guidance": [
            "H2-2 增减变动区段 编制说明",
            "",
            "期末余额=期初+增加小计-减少小计（资产类借方科目1604）。",
            "增加小计=材料+人工+费用+利息+其他。",
            "减少小计=转固+报废+其他。",
        ],
    },
    "H2-2-transfer": {
        "item_id": "H2-2-rows",
        "title": "H2-2 在建工程明细表（竣工结转）",
        "headers": _H2_2_TRANSFER_HEADERS,
        "field_keys": _H2_2_TRANSFER_KEYS,
        "guidance": [
            "H2-2 竣工结转区段 编制说明",
            "",
            "CAS4固定资产确认五条件须全部满足方可转固。",
            "转固金额=累计投入（含资本化利息）。",
            "完工进度(%)=累计投入/预算金额×100。",
        ],
    },
    "H2-3": {
        "item_id": "H2-3-rows",
        "title": "H2-3 调整分录汇总表",
        "headers": _H2_3_HEADERS,
        "field_keys": _H2_3_KEYS,
        "guidance": [
            "H2-3 调整分录 编制说明",
            "",
            "类别填 AJE（审计调整分录）或 RJE（重分类调整分录）。",
            "借方合计应等于贷方合计（借贷平衡）。",
        ],
    },
    "H2-5": {
        "item_id": "H2-5-rows",
        "title": "H2-5 转固时点检查表",
        "headers": _H2_5_HEADERS,
        "field_keys": _H2_5_KEYS,
        "guidance": [
            "H2-5 转固时点检查 编制说明",
            "",
            "CAS4第四条规定的确认条件全部满足时应转为固定资产。",
            "延迟天数=实际转固日期-工程完工日期（应为0或正数）。",
            "延迟超过30天的应特别关注并说明原因。",
        ],
    },
    "H2-7": {
        "item_id": "H2-7-rows",
        "title": "H2-7 工程造价比较表",
        "headers": _H2_7_HEADERS,
        "field_keys": _H2_7_KEYS,
        "guidance": [
            "H2-7 工程造价比较 编制说明",
            "",
            "造价差异率=(实际成本-预算金额)/预算金额×100%。",
            "超预算率=(实际成本-预算金额)/预算金额×100%（正数=超预算）。",
            "差异率超10%须关注并说明原因。",
        ],
    },
    "H2-8": {
        "item_id": "H2-8-rows",
        "title": "H2-8 增加检查表",
        "headers": _H2_8_HEADERS,
        "field_keys": _H2_8_KEYS,
        "guidance": [
            "H2-8 增加检查 编制说明",
            "",
            "逐笔核对新增在建工程的入账依据(合同/发票/验收单/付款凭证)。",
            "资本化判断参照CAS17借款费用确认条件。",
        ],
    },
    "H2-9": {
        "item_id": "H2-9-rows",
        "title": "H2-9 减少检查表",
        "headers": _H2_9_HEADERS,
        "field_keys": _H2_9_KEYS,
        "guidance": [
            "H2-9 减少检查 编制说明",
            "",
            "减少方式：转固/报废/毁损/出售。",
            "处置损益=处置收入-处置费用-减少金额。",
        ],
    },
    "H2-13": {
        "item_id": "H2-13-rows",
        "title": "H2-13 盘点检查表",
        "headers": _H2_13_HEADERS,
        "field_keys": _H2_13_KEYS,
        "guidance": [
            "H2-13 在建工程盘点检查 编制说明",
            "",
            "实地状态：正常施工/停工/完工待转固。",
            "停工工程须评估是否存在减值迹象（CAS8）。",
        ],
    },
    "H2-17": {
        "item_id": "H2-17-rows",
        "title": "H2-17 关联交易检查表",
        "headers": _H2_17_HEADERS,
        "field_keys": _H2_17_KEYS,
        "guidance": [
            "H2-17 关联交易检查 编制说明",
            "",
            "差异率=(交易金额-市场价格)/市场价格×100%。",
            "差异率超10%应关注定价公允性。",
        ],
    },
}

router = create_cycle_import_export_router(tag="h2-import-export", api_prefix="h2", specs=_H2_SPECS)
