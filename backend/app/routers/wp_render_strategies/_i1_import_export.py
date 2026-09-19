"""I1 无形资产 — 导入导出3端点（列结构对齐 requirements）.

POST /i1/export-template → 空白结构xlsx
POST /i1/export-data → 当前数据xlsx（含公式结果）
POST /i1/import-data → 解析xlsx→验证→写入checklist_responses

支持sheet: 审定表I1, 明细表I1-2, 调整分录I1-3, 增加检查I1-5, 减少明细I1-6, 权属检查I1-8, 摊销分配I1-9
动态行表格（需导入）: I1-2, I1-3, I1-5, I1-6, I1-8
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ─── I1 审定表（三区块固定结构） ─────────────────────────────────────────────

_I1_ADJ_HEADERS = [
    "项目", "期初余额", "本期增加", "本期减少", "期末余额", "未审数", "AJE", "RJE", "审定数",
]
_I1_ADJ_KEYS = [
    "item", "openingBalance", "increase", "decrease", "closingBalance", "unadjusted", "aje", "rje", "audited",
]

# ─── I1-2 明细表（基础区段） ─────────────────────────────────────────────────

_I1_2_BASE_HEADERS = [
    "资产类型", "资产名称", "取得日期", "使用寿命(年)", "残值率(%)", "摊销方法",
]
_I1_2_BASE_KEYS = [
    "assetType", "assetName", "acquisitionDate", "usefulLife", "salvageRate", "amortMethod",
]

# ─── I1-2 明细表（原值变动区段） ─────────────────────────────────────────────

_I1_2_COST_HEADERS = [
    "资产类型", "资产名称", "期初原值", "本期增加", "本期减少", "期末原值",
]
_I1_2_COST_KEYS = [
    "assetType", "assetName", "costOpening", "costIncrease", "costDecrease", "costClosing",
]

# ─── I1-2 明细表（摊销区段） ─────────────────────────────────────────────────

_I1_2_AMORT_HEADERS = [
    "资产类型", "资产名称", "累计摊销期初", "本期摊销", "摊销转出", "累计摊销期末", "净值",
]
_I1_2_AMORT_KEYS = [
    "assetType", "assetName", "amortOpening", "amortProvision", "amortTransferOut", "amortClosing", "netValue",
]

# ─── I1-2 明细表（减值区段） ─────────────────────────────────────────────────

_I1_2_IMPAIR_HEADERS = [
    "资产类型", "资产名称", "减值准备期初", "本期计提", "本期转回", "减值准备期末",
]
_I1_2_IMPAIR_KEYS = [
    "assetType", "assetName", "impairOpening", "impairProvision", "impairReversal", "impairClosing",
]

# ─── I1-3 调整分录 ──────────────────────────────────────────────────────────

_I1_3_HEADERS = [
    "序号", "调整事项", "类别", "科目代码", "科目名称", "摘要", "借方金额", "贷方金额", "索引", "备注",
]
_I1_3_KEYS = [
    "seq", "description", "entryType", "accountCode", "accountName", "summary", "debitAmount", "creditAmount", "indexRef", "remark",
]

# ─── I1-5 增加检查 ──────────────────────────────────────────────────────────

_I1_5_HEADERS = [
    "序号", "资产名称", "取得方式", "入账日期", "入账金额", "合同/发票号", "支付方式", "审查结论",
]
_I1_5_KEYS = [
    "seq", "assetName", "acquisitionMethod", "entryDate", "entryAmount", "contractInvoiceNo", "paymentMethod", "conclusion",
]

# ─── I1-6 减少明细 ──────────────────────────────────────────────────────────

_I1_6_HEADERS = [
    "序号", "资产名称", "原值", "累计摊销", "减值准备", "净值", "处置方式",
    "处置收入", "处置损益", "审批文件", "处置日期", "审计结论", "备注",
]
_I1_6_KEYS = [
    "seq", "assetName", "originalCost", "accAmortization", "impairment", "netValue", "disposalType",
    "disposalIncome", "disposalGainLoss", "approvalDoc", "disposalDate", "conclusion", "remark",
]

# ─── I1-8 权属检查 ──────────────────────────────────────────────────────────

_I1_8_HEADERS = [
    "序号", "资产名称", "资产类型", "证书编号", "登记日期", "有效期",
    "权利人", "是否与账面一致", "账面价值", "权证价值", "差异金额", "差异说明", "审计结论",
]
_I1_8_KEYS = [
    "seq", "assetName", "assetType", "certNo", "registrationDate", "validityPeriod",
    "owner", "isConsistent", "bookValue", "certValue", "difference", "diffReason", "conclusion",
]

# ─── I1-9 摊销分配 ──────────────────────────────────────────────────────────

_I1_9_HEADERS = [
    "资产名称", "摊销总额", "管理费用", "销售费用", "制造费用", "研发费用", "其他", "合计", "分配比例(%)",
]
_I1_9_KEYS = [
    "assetName", "amortTotal", "adminExpense", "salesExpense", "mfgExpense", "rdExpense", "otherExpense", "allocTotal", "allocRatio",
]

# ═══════════════════════════════════════════════════════════════════════════════

_I1_SPECS: dict[str, dict[str, Any]] = {
    "I1": {
        "item_id": "I1-adj-rows",
        "title": "审定表I1（三科目审定+三角勾稽）",
        "headers": _I1_ADJ_HEADERS,
        "field_keys": _I1_ADJ_KEYS,
        "guidance": [
            "I1 审定表 编制说明",
            "",
            "三区块固定结构：一、无形资产-原值（1701）→ 二、累计摊销（1702）→ 三、减值准备（1703）→ 净值合计。",
            "资产类公式：期末=期初+增加-减少（科目1701）。",
            "备抵类公式：期末=期初+贷方-借方（科目1702/1703）。",
            "审定数=未审+AJE+RJE。",
        ],
    },
    "I1-2-base": {
        "item_id": "I1-2-rows",
        "title": "I1-2 明细表（基础信息）",
        "headers": _I1_2_BASE_HEADERS,
        "field_keys": _I1_2_BASE_KEYS,
        "guidance": [
            "I1-2 无形资产明细表 — 基础区段 编制说明",
            "",
            "摊销方法可选：直线法/剩余年限法/产量法。",
            "使用寿命不确定的无形资产不摊销，但需年度减值测试。",
        ],
    },
    "I1-2-cost": {
        "item_id": "I1-2-rows",
        "title": "I1-2 明细表（原值变动）",
        "headers": _I1_2_COST_HEADERS,
        "field_keys": _I1_2_COST_KEYS,
        "guidance": [
            "I1-2 原值变动区段 编制说明",
            "",
            "期末原值=期初原值+本期增加-本期减少（资产类借方科目1701）。",
        ],
    },
    "I1-2-amort": {
        "item_id": "I1-2-rows",
        "title": "I1-2 明细表（摊销）",
        "headers": _I1_2_AMORT_HEADERS,
        "field_keys": _I1_2_AMORT_KEYS,
        "guidance": [
            "I1-2 摊销区段 编制说明",
            "",
            "累计摊销期末=期初+本期摊销-摊销转出（备抵类贷方科目1702）。",
            "净值=期末原值-累计摊销期末-减值准备期末。",
        ],
    },
    "I1-2-impair": {
        "item_id": "I1-2-rows",
        "title": "I1-2 明细表（减值）",
        "headers": _I1_2_IMPAIR_HEADERS,
        "field_keys": _I1_2_IMPAIR_KEYS,
        "guidance": [
            "I1-2 减值区段 编制说明",
            "",
            "减值准备期末=期初+本期计提-本期转回。",
            "无形资产减值损失一经确认不得转回（CAS8）。",
        ],
    },
    "I1-3": {
        "item_id": "I1-3-rows",
        "title": "I1-3 调整分录汇总表",
        "headers": _I1_3_HEADERS,
        "field_keys": _I1_3_KEYS,
        "guidance": [
            "I1-3 调整分录 编制说明",
            "",
            "类别填 AJE（审计调整分录）或 RJE（重分类调整分录）。",
            "借方合计应等于贷方合计（借贷平衡）。",
        ],
    },
    "I1-5": {
        "item_id": "I1-5-rows",
        "title": "I1-5 无形资产增加检查表",
        "headers": _I1_5_HEADERS,
        "field_keys": _I1_5_KEYS,
        "guidance": [
            "I1-5 增加检查 编制说明",
            "",
            "取得方式：外购/自行研发(I2转入)/企业合并/捐赠/投资者投入。",
            "逐笔核对入账依据（合同/发票/研发立项文件等）。",
        ],
    },
    "I1-6": {
        "item_id": "I1-6-rows",
        "title": "I1-6 无形资产减少明细表",
        "headers": _I1_6_HEADERS,
        "field_keys": _I1_6_KEYS,
        "guidance": [
            "I1-6 减少明细 编制说明",
            "",
            "处置损益=处置收入-净值（净值=原值-摊销-减值）。",
            "处置方式：出售/报废/捐赠/对外投资/无偿划转。",
        ],
    },
    "I1-8": {
        "item_id": "I1-8-rows",
        "title": "I1-8 无形资产权属检查表",
        "headers": _I1_8_HEADERS,
        "field_keys": _I1_8_KEYS,
        "guidance": [
            "I1-8 权属检查 编制说明",
            "",
            "按类型分组核查：专利/商标/著作权/土地使用权/软件/特许经营权等。",
            "差异金额=账面价值-权证价值。",
            "权利人非被审计单位时标记权属异常。",
        ],
    },
    "I1-9": {
        "item_id": "I1-9-rows",
        "title": "I1-9 摊销分配分析表",
        "headers": _I1_9_HEADERS,
        "field_keys": _I1_9_KEYS,
        "guidance": [
            "I1-9 摊销分配 编制说明",
            "",
            "各行分配合计应等于摊销总额。",
            "分配比例(%)=各费用科目/摊销总额×100。",
            "联动：管理费用→K8，销售费用→K9，研发费用→I6。",
        ],
    },
}

router = create_cycle_import_export_router(tag="i1-import-export", api_prefix="i1", specs=_I1_SPECS)
