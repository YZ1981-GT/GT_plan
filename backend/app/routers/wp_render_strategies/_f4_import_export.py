"""F4 应付账款 — 导入导出（列结构对齐 requirements）."""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

_ADJ_HEADERS = ["序号", "分录类型", "日期", "摘要", "科目代码", "科目名称", "借方金额", "贷方金额", "编制人", "备注"]
_ADJ_KEYS = ["seq", "entryType", "date", "summary", "accountCode", "accountName", "debitAmount", "creditAmount", "preparer", "remark"]

_F4_SPECS: dict[str, dict[str, Any]] = {
    "F4-1-nature": {
        "item_id": "F4-1-adj-nature-rows",
        "title": "F4-1 应付账款审定表 — 按性质分类",
        "headers": [
            "项目", "期初未审数", "期初账项调整", "期初重分类调整",
            "期末未审数", "期末账项调整", "期末重分类调整", "原因分析",
        ],
        "field_keys": [
            "label", "openingUnadjusted", "openingAje", "openingRje",
            "closingUnadjusted", "closingAje", "closingRje", "reasonAnalysis",
        ],
        "guidance": [
            "F4-1 按性质分类 编制说明",
            "",
            "1. 固定项目依次为：货款、工程款、设备款、服务费、其他。",
            "2. 审定数、变动额和变动率为公式列，导入后由系统自动计算。",
            "3. F4-2存在有效明细时，期末未审、账项调整和重分类由明细表自动汇总。",
            "4. 变动率绝对值超过30%的项目必须填写原因分析。",
        ],
    },
    "F4-1-aging": {
        "item_id": "F4-1-adj-aging-rows",
        "title": "F4-1 应付账款审定表 — 按账龄分类",
        "headers": [
            "项目", "期初未审数", "期初账项调整", "期初重分类调整",
            "期末未审数", "期末账项调整", "期末重分类调整", "原因分析",
        ],
        "field_keys": [
            "label", "openingUnadjusted", "openingAje", "openingRje",
            "closingUnadjusted", "closingAje", "closingRje", "reasonAnalysis",
        ],
        "guidance": [
            "F4-1 按账龄分类 编制说明",
            "",
            "1. 固定项目依次为：1年以内、1至2年、2至3年、3年以上、其他/未分类。",
            "2. 按账龄合计应与按性质合计一致；期初、期末分别与试算平衡表核对。",
            "3. F4-2存在有效明细时，期末账龄数据由明细表自动汇总。",
        ],
    },
    "F4-2": {
        "item_id": "F4-2-rows",
        "title": "F4-2 应付账款明细表（源表A:AA 27列）",
        "headers": [
            "债权人名称", "公司代码", "关联方类型", "款项性质",
            "期初未审余额", "期初账项调整", "期初重分类调整", "期初审定余额",
            "借方发生", "贷方发生", "期末余额", "被审计单位重分类调整", "期末未审余额",
            "未审账龄-1年以下", "未审账龄-1～2年", "未审账龄-2～3年", "未审账龄-3年以上",
            "账项调整", "重分类调整", "审定数",
            "审定账龄-1年以下", "审定账龄-1～2年", "审定账龄-2～3年", "审定账龄-3年以上",
            "是否函证", "期后付款", "备注",
        ],
        "field_keys": [
            "creditor", "companyCode", "relatedPartyType", "paymentNature",
            "openingUnadjusted", "openingAje", "openingRje", "openingAdjusted",
            "currentDebit", "currentCredit", "closingBalance",
            "entityReclassification", "closingUnadjusted",
            "unadjustedAgingLt1", "unadjustedAging1to2", "unadjustedAging2to3", "unadjustedAgingGt3",
            "closingAje", "closingRje", "closingAdjusted",
            "auditedAgingLt1", "auditedAging1to2", "auditedAging2to3", "auditedAgingGt3",
            "isConfirmed", "subsequentPayment", "remark",
        ],
        "guidance": [
            "F4-2 明细表 编制说明",
            "",
            "1. 列顺序严格对应源表A:AA；公式列可留空，导入后由系统重算。",
            "2. 关联方类型：合并范围内关联方、合并范围外关联方、非关联方。",
            "3. 款项性质：货款、工程款、设备款、服务费、其他。",
            "4. 期初审定=期初未审+期初AJE+期初RJE；期末余额=期初未审+贷方-借方。",
            "5. 期末未审=期末余额+被审计单位重分类；审定数=期末未审+AJE+RJE。",
            "6. 未审账龄四档合计应等于期末未审余额；审定账龄四档合计应等于审定数。",
            "7. 账龄超过1年的大额款项应在备注中说明未偿还或未结转原因及期后偿还情况。",
        ],
    },
    "F4-3": {
        "item_id": "F4-3-rows",
        "title": "F4-3 调整分录汇总表",
        "headers": _ADJ_HEADERS,
        "field_keys": _ADJ_KEYS,
        "guidance": ["F4-3 调整分录 编制说明", "", "分录类型填 AJE 或 RJE；借贷应平衡。"],
    },
    "F4-5": {
        "item_id": "F4-5-rows",
        "title": "F4-5 账龄1年以上的应付账款检查表",
        "headers": [
            "债权人名称", "期末余额", "账龄", "经济业务说明", "未偿还或未结转的原因",
            "是否无法支付", "是否诉讼", "支付计划", "审定金额", "支持性证据", "备注",
        ],
        "field_keys": [
            "creditor", "closingBalance", "aging", "businessDescription", "unsettledReason",
            "unableToPay", "litigation", "paymentPlan", "auditedAmount", "supportingEvidence", "remark",
        ],
        "guidance": [
            "F4-5 账龄1年以上应付账款检查表 编制说明",
            "",
            "1. 按实际债权人逐项填写，不使用占位名称。",
            "2. 账龄通常填写：1～2年、2～3年、3年以上；多账龄可用顿号组合。",
            "3. 是否无法支付、是否诉讼填写：是、否或不适用。",
            "4. 未偿还/未结转原因、支付计划和支持性证据不得为空；证据应注明名称、编号及结论。",
            "5. 期末余额与审定金额存在差异时，应在备注中说明审计调整。",
        ],
    },
    "F4-6": {
        "item_id": "F4-6-rows",
        "title": "F4-6 应付账款关联方及交易检查表",
        "headers": [
            "关联方名称", "关联关系", "期初余额", "本期借方", "本期贷方", "期末余额",
            "账龄", "定价政策", "发生原因（款项性质）", "期后付款金额", "索引号", "备注",
        ],
        "field_keys": [
            "partyName", "relationship", "openingBalance", "currentDebit", "currentCredit", "closingBalance",
            "aging", "pricingPolicy", "transactionNature", "postPaymentAmount", "indexNo", "remark",
        ],
        "guidance": [
            "F4-6 应付账款关联方及交易检查表 编制说明",
            "",
            "1. 按实际关联方逐项填写，关联关系应使用经核实的具体类别，不使用占位名称。",
            "2. 期末余额=期初余额+本期贷方-本期借方；导入时可保留期末余额用于核对。",
            "3. 账龄可填写1年以内、1～2年、2～3年、3年以上；多账龄用顿号组合。",
            "4. 定价政策应说明市场定价、协议定价、成本加成、第三方价格或其他依据。",
            "5. 发生原因应说明交易背景及款项性质；索引号应指向合同、定价和付款证据。",
        ],
    },
    "F4-7-payment-window": {
        "item_id": "F4-7-payment-window-rows",
        "title": "F4-7（一）期后付款是否在平均付款天数内",
        "headers": [
            "供应商名称", "期初余额", "本期借方", "本期贷方", "期末余额",
            "平均付款天数", "期后付款金额", "差异", "期后付款是否在平均付款天数内", "备注",
        ],
        "field_keys": [
            "supplierName", "openingBalance", "currentDebit", "currentCredit", "closingBalance",
            "averagePaymentDays", "postPaymentAmount", "difference", "withinAverageDays", "remark",
        ],
        "guidance": [
            "F4-7（一）平均付款期分析 编制说明", "",
            "期末余额=期初余额+本期贷方-本期借方；平均付款天数=365×期末余额÷本期贷方；差异=期后付款-期末余额。",
        ],
    },
    "F4-7-estimated-inbound": {
        "item_id": "F4-7-estimated-inbound-rows",
        "title": "F4-7（二）料到单未到——存货暂估入库",
        "headers": [
            "入库单日期", "入库单编号", "数量", "合同单价（不含税）", "暂估金额",
            "记账凭证日期", "记账凭证号", "凭证金额", "是否应调整", "备注",
        ],
        "field_keys": [
            "receiptDate", "receiptNo", "quantity", "contractUnitPrice", "estimatedAmount",
            "voucherDate", "voucherNo", "voucherAmount", "shouldAdjust", "remark",
        ],
        "guidance": [
            "F4-7（二）暂估入库检查 编制说明", "",
            "暂估金额=入库数量×合同不含税单价；将入库单、合同/订单与暂估记账凭证逐笔匹配。",
        ],
    },
    "F4-7-unprocessed-invoice": {
        "item_id": "F4-7-unprocessed-invoice-rows",
        "title": "F4-7（三）截止现场结束日未处理的供应商发票",
        "headers": [
            "购货发票日期", "购货发票编号", "数量", "发票内容", "金额",
            "供应商名称", "是否应计入报告期", "应计入报告期金额", "备注",
        ],
        "field_keys": [
            "invoiceDate", "invoiceNo", "quantity", "invoiceContent", "amount",
            "supplierName", "shouldIncludeReportPeriod", "reportPeriodAmount", "remark",
        ],
        "guidance": ["F4-7（三）未处理供应商发票 编制说明", "", "根据货物/服务取得时点判断相关负债是否应计入报告期。"],
    },
    "F4-7-subsequent-payment": {
        "item_id": "F4-7-subsequent-payment-rows",
        "title": "F4-7（四）应付账款期后付款核对",
        "headers": [
            "记账凭证日期", "记账凭证编号", "银行付款凭单日期", "银行付款凭单编号",
            "金额", "供应商名称", "是否应计入报告期", "应计入报告期金额", "备注",
        ],
        "field_keys": [
            "voucherDate", "voucherNo", "bankDocumentDate", "bankDocumentNo",
            "amount", "supplierName", "shouldIncludeReportPeriod", "reportPeriodAmount", "remark",
        ],
        "guidance": ["F4-7（四）期后付款核对 编制说明", "", "付款凭证应与银行付款凭单/银行对账单核对一致，并反查负债归属期。"],
    },
    "F4-7-subsequent-increase": {
        "item_id": "F4-7-subsequent-increase-rows",
        "title": "F4-7（五）应付账款期后增加额核对",
        "headers": [
            "记账凭证日期", "记账凭证编号", "购货发票日期", "购货发票编号",
            "金额", "供应商名称", "是否应计入报告期", "应计入报告期金额", "备注",
        ],
        "field_keys": [
            "voucherDate", "voucherNo", "purchaseInvoiceDate", "purchaseInvoiceNo",
            "amount", "supplierName", "shouldIncludeReportPeriod", "reportPeriodAmount", "remark",
        ],
        "guidance": ["F4-7（五）期后增加额核对 编制说明", "", "核对期后凭证与购货发票日期、编号及金额，判断入账期间是否合理。"],
    },
    "F4-8-debit": {
        "item_id": "F4-8-debit-rows",
        "title": "F4-8 本期借方金额检查（付款/减少）",
        "headers": [
            "供应商名称", "日期", "凭证编号", "业务内容", "对方科目", "明细科目", "借方金额",
            "付款审批单日期/编号", "是否经过恰当审批",
            "银行回单日期", "收款方", "回单金额",
            "其他证据", "索引号", "是否异常", "异常/检查说明",
        ],
        "field_keys": [
            "supplierName", "voucherDate", "voucherNo", "businessContent", "counterAccount",
            "detailAccount", "amount",
            "approvalDateNo", "approvalProper",
            "bankReceiptDate", "bankPayee", "bankAmount",
            "otherEvidence", "indexNo", "isAbnormal", "issueDesc",
        ],
        "guidance": [
            "F4-8 本期借方金额检查 编制说明", "",
            "1. 科目2202借方发生（付款/减少），逐笔核对记账凭证、付款审批单、银行回单。",
            "2. 是否经过恰当审批填：是 / 否；是否异常填：是 / 否。",
            "3. 回单金额与凭证金额不符、收款方与供应商不一致时，系统标记勾稽不符，需在异常/检查说明中说明。",
            "4. 检查比例与F4-2账面借方发生额比对，比例较低应扩大样本量或说明原因。",
        ],
    },
    "F4-8-credit": {
        "item_id": "F4-8-credit-rows",
        "title": "F4-8 本期贷方金额检查（采购/增加，可结合F2-33）",
        "headers": [
            "供应商名称", "日期", "凭证编号", "业务内容", "对方科目", "明细科目", "贷方金额",
            "入库单日期/编号", "品名", "单位", "数量",
            "发票日期/编号", "对手方名称", "发票金额",
            "其他证据", "索引号", "是否异常", "异常/检查说明",
        ],
        "field_keys": [
            "supplierName", "voucherDate", "voucherNo", "businessContent", "counterAccount",
            "detailAccount", "amount",
            "receiptDateNo", "receiptProduct", "receiptUnit", "receiptQty",
            "invoiceDateNo", "invoiceCounterparty", "invoiceAmount",
            "otherEvidence", "indexNo", "isAbnormal", "issueDesc",
        ],
        "guidance": [
            "F4-8 本期贷方金额检查 编制说明", "",
            "1. 科目2202贷方发生（采购/增加），逐笔核对记账凭证、入库单/验收单、采购发票；可结合存货采购入库检查F2-33。",
            "2. 发票金额与凭证金额不符、发票对手方与供应商不一致时，系统标记勾稽不符，需在异常/检查说明中说明。",
            "3. 检查比例与F4-2账面贷方发生额比对，比例较低应扩大样本量或说明原因。",
        ],
    },
    "F4-9": {
        "item_id": "F4-9-rows",
        "title": "F4-9 供应商融资检查表",
        "headers": [
            "供应商名称", "承诺付款方", "融资单号", "资金提供方（金融机构）", "状态",
            "融资金额", "供应商签收日期", "放款日期", "转让日期", "承诺还款日期", "实际还款日期",
            "本期采购金额", "借款余额", "备注",
        ],
        "field_keys": [
            "supplierName", "promisedPayer", "financingNo", "fundProvider", "status",
            "financingAmount", "supplierSignDate", "disbursementDate", "transferDate",
            "promisedRepayDate", "actualRepayDate", "purchaseAmount", "loanBalance", "remark",
        ],
        "guidance": [
            "F4-9 供应商融资检查表 编制说明", "",
            "1. 按供应商动态分组登记融资明细；同名供应商多笔融资分多行，系统自动按组小计并合计。",
            "2. 差异=融资金额−本期采购金额（公式列，导入后由系统重算，无需填入）。",
            "3. 若融资金额大于采购金额，应关注资金流向及体外循环，必要时执行穿透检查。",
            "4. 可从F4-2明细表引用供应商并带入本期贷方作为采购金额参考。",
        ],
    },
}

router = create_cycle_import_export_router(
    tag="f4-import-export",
    api_prefix="f4",
    specs=_F4_SPECS,
    # F4前端动态行统一写入remark；导入导出必须使用同一字段，避免导入成功后页面无数据。
    storage_field="remark",
)
