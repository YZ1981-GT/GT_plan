"""H8 使用权资产 — 导入导出3端点（列结构对齐 requirements）.

POST /h8/export-template → 空白结构xlsx（根据sheet_name导出对应表模板）
POST /h8/export-data → 当前数据xlsx（含已填数据）
POST /h8/import-data → 解析xlsx→验证→写入checklist_responses

支持sheets: H8-2/H8-3/H8-4/H8-5/H8-7/H8-12/H8-13/H8-14/H8-14L
科目编码: 1901使用权资产（借方/资产类）+ 累计折旧（贷方/备抵类）
CAS21新租赁准则核心底稿，与H9租赁负债强联动

Requirements: 3.3
"""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

# ─── H8-2 明细表（源模板58列→4区段：基础+初始/原值/折旧/减值净值） ─────────────

_H8_2_HEADERS = [
    # 基础 + CAS21 初始计量
    "序号", "使用权资产类别", "租赁合同号", "资产名称", "资产编号", "出租方",
    "起始日", "到期日", "租赁期(月)",
    "H9初始计量", "初始直接费用", "租赁激励", "入账值(CAS21)",
    # 原值·未审
    "原值期初未审", "本期租入", "负债重估调整", "原值其他增加",
    "转租转为融资租赁(原值)", "转让或持有待售(原值)", "原值其他减少", "原值期末未审",
    "原值期初调整",
    "账项调整-租入", "账项调整-重估", "账项调整-其他增",
    "账项调整-转租减", "账项调整-转让减", "账项调整-其他减",
    "原值期初审定", "原值增加审定", "原值减少审定", "原值期末审定",
    # 累计折旧
    "折旧期初未审", "本期计提折旧", "折旧其他增加",
    "转租融资(折旧减)", "转让待售(折旧减)", "折旧其他减少", "折旧期末未审",
    "折旧期初调整", "账项调整-折旧计提", "账项调整-折旧其他增",
    "账项调整-折旧转租减", "账项调整-折旧转让减", "账项调整-折旧其他减",
    "折旧期初审定", "折旧增加审定", "折旧减少审定", "折旧期末审定",
    # 减值 + 净值 + 变更
    "减值期初未审", "本期计提减值", "减值其他增加",
    "转租融资(减值减)", "转让待售(减值减)", "减值其他减少", "减值期末未审",
    "减值期初调整", "账项调整-减值计提", "账项调整-减值其他增", "账项调整-减值减少",
    "减值期末审定", "期初净值审定", "期末净值审定",
    "变更调整额", "终止日期", "备注",
]
_H8_2_KEYS = [
    "seq", "category", "contractNo", "assetName", "assetNo", "lessor",
    "startDate", "endDate", "leaseTermMonths",
    "h9InitialAmount", "directCost", "incentive", "initialAmount",
    "costBeginUnadj", "costIncLease", "costIncReval", "costIncOther",
    "costDecSublease", "costDecDisposal", "costDecOther", "costEndUnadj",
    "costOpenAdj",
    "costAjeIncLease", "costAjeIncReval", "costAjeIncOther",
    "costAjeDecSublease", "costAjeDecDisposal", "costAjeDecOther",
    "costBeginAud", "costIncAud", "costDecAud", "costEndAud",
    "depBeginUnadj", "depProvUnadj", "depOtherIncUnadj",
    "depDecSublease", "depDecDisposal", "depOtherDecUnadj", "depEndUnadj",
    "depOpenAdj", "depAjeProv", "depAjeOtherInc",
    "depAjeDecSublease", "depAjeDecDisposal", "depAjeOtherDec",
    "depBeginAud", "depIncAud", "depDecAud", "depEndAud",
    "impairBeginUnadj", "impairProvUnadj", "impairOtherIncUnadj",
    "impairDecSublease", "impairDecDisposal", "impairOtherDecUnadj", "impairEndUnadj",
    "impairOpenAdj", "impairAjeProv", "impairAjeOtherInc", "impairAjeDecDisposal",
    "impairEndAud", "netBeginAud", "netEndAud",
    "modificationAmount", "terminationDate", "remark",
]

# ─── H8-3 调整分录汇总（10列） ────────────────────────────────────────────────

_H8_3_HEADERS = [
    "序号", "调整事项说明", "类别", "报表项目", "科目代码", "科目名称",
    "附注项目", "借方金额", "贷方金额", "索引", "备注",
]
_H8_3_KEYS = [
    "seq", "description", "category", "reportItem", "accountCode", "accountName",
    "noteItem", "debitAmount", "creditAmount", "indexRef", "remark",
]

# ─── H8-12 减少检查表（对齐致同五段式 + CAS21 终止损益 / H9 同步） ─────────────

_H8_12_HEADERS = [
    "序号", "资产类别", "编号/合同号", "资产名称",
    "减少方式", "减少日期", "凭证号", "对方科目", "数量",
    "原值", "累计折旧", "减值准备", "净值",
    "租赁负债余额", "终止损益", "剩余租赁期(月)", "提前退租违约金",
    "支持性文件", "H9联动状态",
    "核对1", "核对2", "核对3", "核对4", "核对5",
    "索引号", "是否异常", "是否关联方", "关联方名称", "备注",
]
_H8_12_KEYS = [
    "seq", "assetCategory", "contractNo", "assetName",
    "reductionMethod", "reductionDate", "voucherNo", "oppositeAccount", "quantity",
    "rouCost", "accDepreciation", "impairmentProvision", "rouNetValue",
    "liabilityBalance", "gainLoss", "remainingMonths", "earlyTermPenalty",
    "supportingDocs", "h9LinkageStatus",
    "check1", "check2", "check3", "check4", "check5",
    "indexRef", "isAbnormal", "isRelatedParty", "relatedPartyName", "remark",
]

# ─── H8-13 简化处理检查表（18列：资格判断 + 费用重算） ─────────────────────────

_H8_13_HEADERS = [
    "序号", "资产类别", "资产名称", "合同号",
    "租赁期开始日", "租赁到期日", "租赁期(月)", "全新资产价值", "简化类型",
    "月租金", "本期应计月数", "本期应计租金", "账面本期租金", "差异",
    "勾稽一致", "费用科目", "核查结论", "索引号",
]
_H8_13_KEYS = [
    "seq", "assetCategory", "assetName", "contractNo",
    "leaseStartDate", "leaseEndDate", "leaseTermMonths", "newAssetValue", "simplifiedType",
    "monthlyRent", "accrualMonths", "expectedExpense", "bookExpense", "difference",
    "reconciled", "expenseAccount", "conclusion", "indexNo",
]

# ─── H8-14 关联交易检查表 — 使用权资产（Excel 15列 + 价差率增强） ──────────────

_H8_14_HEADERS = [
    "序号", "关联单位名称", "关联方关系", "租赁项目", "租赁资产种类",
    "租赁发生时间及到期日",
    "使用权资产原值期末审定数", "使用权资产累计折旧期末审定数",
    "使用权资产减值准备期末审定数", "使用权资产净值",
    "本期新增使用权资产金额（原值）", "使用权资产本期折旧金额",
    "定价政策", "年租金", "市场租金参考", "价差率(%)",
    "关联交易是否存在异常", "备注", "索引号",
]
_H8_14_KEYS = [
    "seq", "relatedPartyName", "relationship", "leaseItem", "assetType",
    "leasePeriod",
    "costEnding", "accumDepEnding",
    "impairmentEnding", "netValue",
    "additionsCost", "periodDep",
    "pricingPolicy", "annualRent", "marketRent", "priceDiffRate",
    "isAbnormal", "remark", "indexNo",
]

# ─── H8-14L 关联交易检查表 — 租赁负债 ─────────────────────────────────────────

_H8_14L_HEADERS = [
    "序号", "关联方名称", "关联方关系", "租赁项目", "租赁资产种类",
    "租赁发生时间及到期日",
    "租赁负债期末审定数", "本期应支付的租赁款项", "本期承担的租赁负债利息支出",
    "定价政策", "年租金", "市场租金参考", "价差率(%)",
    "关联交易是否存在异常", "备注", "索引号",
]
_H8_14L_KEYS = [
    "seq", "relatedPartyName", "relationship", "leaseItem", "assetType",
    "leasePeriod",
    "liabilityEnding", "periodPayments", "periodInterest",
    "pricingPolicy", "annualRent", "marketRent", "priceDiffRate",
    "isAbnormal", "remark", "indexNo",
]

# ─── H8-4 租赁识别检查表（对齐 H8-4-records 段落型模型）────────────────────

_H8_4_HEADERS = [
    "记录ID", "租赁合同号", "资产简述",
    "物理可区分", "实质替换权",
    "主导使用目的方式", "使用预先确定", "几乎全部经济利益",
    "分拆是否适用", "合并是否适用",
    "短期是否适用", "续租后≤12月", "无购买选择权",
    "低价值是否适用", "全新低价值", "全新价值", "无转租预期",
    "本项结论", "说明",
]
_H8_4_KEYS = [
    "recordId", "contractNo", "assetDesc",
    "physicallyDistinct", "supplierSubstantiveSubstitution",
    "canDirectPurposeManner", "usePredetermined", "economicBenefits",
    "splitApplicable", "combineApplicable",
    "shortTermApplicable", "termWithRenewalWithin12", "noPurchaseOption",
    "lowValueApplicable", "lowValueWhenNew", "newAssetValue", "noSubleaseExpected",
    "conclusion", "explanation",
]

# ─── H8-5 租赁期确定（对齐 H8-5-records 段落型模型）──────────────────────────

_H8_5_HEADERS = [
    "记录ID", "租赁合同号",
    "签订日至开始日信息", "开始日信息", "开始日",
    "不可撤销期间信息", "不可撤销月数",
    "仅出租人有权终止", "仅承租人有权终止", "合理确定不行使终止权", "双方均可无重大罚金终止",
    "终止选择权月数",
    "续租信息", "续租月数", "合理确定行使续租",
    "购买选择权信息", "合理确定行使购买",
    "确定的租赁期(月)", "租赁期截止日", "索引号",
    "重大改良", "重大定制", "相关经营决策",
    "行使未纳入选择权", "未行使已纳入选择权", "事件强制行使", "事件禁止行使",
    "重新确定说明", "重新确定租赁期(月)",
    "说明", "结论",
]
_H8_5_KEYS = [
    "recordId", "contractNo",
    "signingToCommencementInfo", "commencementInfo", "commencementDate",
    "nonCancellableInfo", "nonCancellableMonths",
    "lessorOnlyTerminate", "lesseeOnlyTerminate", "lesseeReasonablyCertainNotTerminate", "bothCanTerminateNoPenalty",
    "terminationOptionMonths",
    "renewalInfo", "renewalMonths", "renewalReasonablyCertain",
    "purchaseOptionInfo", "purchaseReasonablyCertain",
    "determinedLeaseTermMonths", "termEndDate", "indexRef",
    "majorImprovement", "majorCustomization", "relatedBusinessDecision",
    "exercisedOptionNotIncluded", "didNotExerciseIncludedOption", "eventForcesExercise", "eventPreventsExercise",
    "redeterminedInfo", "redeterminedLeaseTermMonths",
    "explanation", "conclusion",
]

# ─── H8-7 租赁变更检查表 ─────────────────────────────────────────────────────

_H8_7_HEADERS = [
    "序号", "租赁合同号", "承租资产", "变更日期",
    "扩大范围", "对价相当单独价格", "范围减少",
    "变更类型", "原租赁条款", "新租赁条款", "变更说明",
    "变更日账面负债", "变更日账面ROU",
    "修订折现率", "付款时点", "剩余年付款", "剩余期数",
    "变更后负债现值", "终止比例", "终止损益",
    "调整额", "重计量后ROU", "会计处理", "结论", "备注",
]
_H8_7_KEYS = [
    "seq", "contractNo", "assetName", "modificationDate",
    "expandsScope", "standalonePrice", "scopeReduction",
    "modificationType", "originalTerms", "newTerms", "modificationDesc",
    "carryingLiability", "carryingROU",
    "revisedDiscountRate", "paymentTiming", "remainingAnnualPayment", "remainingPeriods",
    "newLiabilityPV", "reductionRatio", "scopeGainLoss",
    "adjustmentAmount", "remeasuredROUAmount", "accountingTreatment", "conclusion", "remark",
]

# ═══════════════════════════════════════════════════════════════════════════════

_H8_SPECS: dict[str, dict[str, Any]] = {
    "H8-2": {
        "item_id": "H8-2-rows",
        "title": "H8-2 使用权资产明细表",
        "headers": _H8_2_HEADERS,
        "field_keys": _H8_2_KEYS,
        "guidance": [
            "H8-2 使用权资产、累计折旧及减值准备明细表 编制说明",
            "",
            "对齐致同源模板：原值 / 累计折旧 / 减值准备 各自「未审→期初调整/账项调整→审定」+ 审定净值。",
            "原值增加：本期租入、租赁负债重估调整、其他增加；减少：转租转为融资租赁、转让或持有待售、其他减少。",
            "CAS21：入账值 = H9租赁负债初始 + 初始直接费用 − 租赁激励；每行合同与 H9-2 一一对应。",
            "CAS8：使用权资产减值一经确认不得转回（减少仅为处置/转租结转）。",
            "短期租赁/低价值资产租赁走 H8-13，不登记本表。",
        ],
    },
    "H8-3": {
        "item_id": "H8-3-rows",
        "title": "H8-3 调整分录汇总表",
        "headers": _H8_3_HEADERS,
        "field_keys": _H8_3_KEYS,
        "dual_write": True,
        "storage_field": "remark",
        "guidance": [
            "H8-3 调整分录汇总 编制说明",
            "",
            "对齐 Excel：调整事项说明 / 类别(账项调整·报表调整·其他) / 报表项目 / 科目 / 附注项目 / 借贷 / 索引 / 备注。",
            "「账项调整」→ AJE 影响审定数；「报表调整」→ RJE 仅列报；「其他」按账项调整。",
            "借方合计应等于贷方合计（借贷平衡）。",
            "科目代码以1901（使用权资产）/1902（累计折旧）或对应对方科目（如2205租赁负债）为主。",
        ],
    },
    "H8-12": {
        "item_id": "H8-12-rows",
        "title": "H8-12 使用权资产/租赁负债减少检查表",
        "headers": _H8_12_HEADERS,
        "field_keys": _H8_12_KEYS,
        "guidance": [
            "H8-12 使用权资产/租赁负债减少检查 编制说明（致同五段式）",
            "",
            "一、审计目标 → 二、样本选取 → 三、测试 → 四、说明 → 五、结论。",
            "净值 = 原值 − 累计折旧 − 减值准备；终止损益 = 租赁负债余额 − 使用权资产净值。",
            "检查比例 = 样本原值合计 ÷ 本期减少总体（总体优先取 H8-1 原值贷方）。",
            "核对内容 1–5：凭证齐全/相符/账务正确/截止/H9同步与违约金。",
            "必须与 H9 联动：H8-12 终止确认 → H9 租赁负债同步终止。",
            "到期终止净额应接近 0；提前退租关注违约金条款。",
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
            "双轨逻辑：①资格判断 ②费用重算。",
            "CAS21§32：短期租赁(≤12个月，不含购买选择权) 或 低价值资产(全新价值≤40,000元且未转租)。",
            "简化类型由租赁期/全新价值自动判断；不符合者应转入 H8-2/H9 确认使用权资产。",
            "本期应计租金 = 月租金 × 本期应计月数；差异 = 应计 − 账面；重大差异须追查。",
            "本表索引号为 H8-13，勿与 H8-12（减少/终止）混淆。",
        ],
    },
    "H8-14": {
        "item_id": "H8-14-rows",
        "title": "H8-14 关联交易检查表（使用权资产）",
        "headers": _H8_14_HEADERS,
        "field_keys": _H8_14_KEYS,
        "guidance": [
            "H8-14 关联租赁检查（使用权资产）编制说明",
            "",
            "对齐 Excel：关联单位/关系/租赁项目/资产种类/起止日/原值/累计折旧/减值/净值/本期新增/本期折旧/定价政策/是否异常/备注/索引。",
            "净值 = 原值期末 − 累计折旧期末 − 减值准备期末。",
            "价差率 = (年租金 − 市场租金参考) / 市场租金参考 × 100%，绝对值>10%重点关注。",
            "仅登记合并范围外关联方租赁；宜与 H8-14L 租赁负债表成对核查，并与 H8-2/H9 勾稽。",
        ],
    },
    "H8-14L": {
        "item_id": "H8-14-liability-rows",
        "title": "H8-14 关联交易检查表（租赁负债）",
        "headers": _H8_14L_HEADERS,
        "field_keys": _H8_14L_KEYS,
        "guidance": [
            "H8-14 关联租赁检查（租赁负债）编制说明",
            "",
            "登记关联方租赁负债期末审定、本期应付款、本期利息支出。",
            "价差率 = (年租金 − 市场租金参考) / 市场租金参考 × 100%。",
            "金额应与 H9 租赁负债底稿交叉验证。",
        ],
    },
    "H8-4": {
        "item_id": "H8-4-records",
        "title": "H8-4 租赁识别检查表",
        "headers": _H8_4_HEADERS,
        "field_keys": _H8_4_KEYS,
        "dual_write": True,
        "storage_field": "remark",
        "guidance": [
            "H8-4 租赁识别 编制说明",
            "",
            "活数据键：H8-4-records（段落型：三要素/分拆/合并/短期/低价值）。",
            "旧 H8-4-rows 已废弃，请用本表导入导出。",
            "CAS21：已识别资产∩主导使用权∩几乎全部经济利益 → 含租赁。",
            "结论列：是=含租赁 / 否=不含 / 不适用。",
        ],
    },
    "H8-5": {
        "item_id": "H8-5-records",
        "title": "H8-5 租赁期的确定",
        "headers": _H8_5_HEADERS,
        "field_keys": _H8_5_KEYS,
        "dual_write": True,
        "storage_field": "remark",
        "guidance": [
            "H8-5 租赁期确定 编制说明",
            "",
            "活数据键：H8-5-records（段落型：§1 构成期间 + §2 重新评估/修改）。",
            "租赁期 = 不可撤销期间 ＋ 续租选择权期（合理确定行使）＋ 终止选择权期（合理确定不行使）。",
            "签订日至开始日不计入；双方均可无重大罚金终止则不再可强制执行。",
            "确定后请回写 H8-6 计量参数 / H8-8 折旧行；≤12月且无购买权可推送 H8-13。",
            "是/否列填：是 / 否；结论列：是 / 否 / 不适用。",
        ],
    },
    "H8-7": {
        "item_id": "H8-7-rows",
        "title": "H8-7 租赁变更检查表",
        "headers": _H8_7_HEADERS,
        "field_keys": _H8_7_KEYS,
        "guidance": [
            "H8-7 租赁变更 编制说明（CAS21第28-30条）",
            "",
            "判定树：1.1 扩大范围+对价相当单独价格 → 单独租赁；否则 1.2 区分范围减少与其他变更（二者与 1.1 互斥）。",
            "其他变更：调整额 = 变更后付款额现值 − 变更日账面负债；重计量 ROU = 账面 ROU + 调整额。",
            "范围减少：按终止比例冲减 ROU/负债，差额计入损益。",
            "修订折现率请填小数（如 0.06）或按导出表头说明；付款时点填 期初/期末。",
            "可与 H8-2 明细、H8-6 计量参数交叉取数；变更后逐年摊销详见 H8-6。",
        ],
    },
}

router = create_cycle_import_export_router(tag="h8-import-export", api_prefix="h8", specs=_H8_SPECS)
