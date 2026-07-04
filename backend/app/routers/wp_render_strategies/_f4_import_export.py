"""F4 应付账款 — 导入导出（列结构对齐 requirements）."""

from __future__ import annotations

from typing import Any

from ._cycle_import_export_common import create_cycle_import_export_router

_ADJ_HEADERS = ["序号", "分录类型", "日期", "摘要", "科目代码", "科目名称", "借方金额", "贷方金额", "编制人", "备注"]
_ADJ_KEYS = ["seq", "entryType", "date", "summary", "accountCode", "accountName", "debitAmount", "creditAmount", "preparer", "remark"]

_F4_SPECS: dict[str, dict[str, Any]] = {
    "F4-2": {
        "item_id": "F4-2-rows",
        "title": "F4-2 应付账款明细表（27列）",
        "headers": [
            "序号", "债权人", "公司代码", "关联方类型", "款项性质", "期初审定", "本期借方", "本期贷方", "期末余额",
            "账龄1年以内", "1-2年", "2-3年", "3年以上", "账龄合计", "是否函证", "函证结果",
            "期后付款金额", "期后付款日期", "备注",
            "账项调整", "重分类", "审定余额", "审定账龄1年内", "审定1-2年", "审定2-3年", "审定3年以上", "索引",
        ],
        "field_keys": [
            "seq", "creditor", "companyCode", "relationType", "nature", "openingAdjusted", "debit", "credit", "closingBalance",
            "agingLt1", "aging1to2", "aging2to3", "agingGt3", "agingTotal", "isConfirmed", "confirmResult",
            "postPaymentAmt", "postPaymentDate", "remark",
            "aje", "rje", "auditedBalance", "auditedAgingLt1", "auditedAging1to2", "auditedAging2to3", "auditedAgingGt3", "indexRef",
        ],
        "guidance": [
            "F4-2 明细表 编制说明",
            "",
            "27列与 HTML 底稿三区段Tab（基础9+账龄核对10+调整审定8）合并为宽表。",
            "期末余额=期初审定+贷方-借方；账龄合计应等于期末余额。",
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
        "title": "F4-5 长期挂账检查表",
        "headers": [
            "序号", "债权人", "挂账金额", "挂账起始日", "挂账天数", "款项性质", "挂账原因",
            "是否有合同纠纷", "是否需转营业外收入", "处理建议", "备注",
        ],
        "field_keys": [
            "seq", "creditor", "hangAmount", "hangStartDate", "hangDays", "nature", "hangReason",
            "hasDispute", "needTransferIncome", "advice", "remark",
        ],
        "guidance": ["F4-5 长期挂账 编制说明", "", "挂账天数=审计截止日-挂账起始日；>730天橙色、>1095天红色关注。"],
    },
    "F4-6": {
        "item_id": "F4-6-rows",
        "title": "F4-6 关联方检查表",
        "headers": [
            "序号", "关联方名称", "关联关系", "款项性质", "期初余额", "本期增加", "本期减少", "期末余额",
            "占比(%)", "结算周期", "是否超期", "定价公允性", "账龄", "审计评价", "备注",
        ],
        "field_keys": [
            "seq", "partyName", "relationship", "nature", "openingBalance", "increase", "decrease", "closingBalance",
            "sharePct", "settlementCycle", "isOverdue", "fairness", "aging", "auditEvaluation", "remark",
        ],
        "guidance": ["F4-6 关联方检查 编制说明", "", "占比=期末余额/应付账款总余额；>30%需重点关注。"],
    },
    "F4-7-purchase": {
        "item_id": "F4-7-purchase-rows",
        "title": "F4-7 未入账检查 — 期后采购",
        "headers": ["序号", "采购日期", "供应商", "金额", "采购单号", "商品/服务", "是否应入当期", "入账建议", "备注"],
        "field_keys": ["seq", "date", "vendor", "amount", "docNo", "goods", "shouldCurrent", "suggestion", "remark"],
        "guidance": ["F4-7 期后采购区 编制说明", "", "资产负债表日±5天采购凭证；「是否应入当期」填 是/否。"],
    },
    "F4-7-inbound": {
        "item_id": "F4-7-inbound-rows",
        "title": "F4-7 未入账检查 — 期后入库",
        "headers": ["序号", "入库日期", "供应商", "金额", "入库单号", "商品名称", "是否应入当期", "入账建议", "备注"],
        "field_keys": ["seq", "date", "vendor", "amount", "docNo", "goods", "shouldCurrent", "suggestion", "remark"],
        "guidance": ["F4-7 期后入库区 编制说明"],
    },
    "F4-7-invoice": {
        "item_id": "F4-7-invoice-rows",
        "title": "F4-7 未入账检查 — 期后收票",
        "headers": ["序号", "收票日期", "开票方", "金额", "发票号", "服务期间", "是否应入当期", "入账建议", "备注"],
        "field_keys": ["seq", "date", "vendor", "amount", "docNo", "servicePeriod", "shouldCurrent", "suggestion", "remark"],
        "guidance": ["F4-7 期后收票区 编制说明"],
    },
    "F4-8-debit": {
        "item_id": "F4-8-debit-rows",
        "title": "F4-8 应付账款检查 — 借方区(付款/减少)",
        "headers": [
            "序号", "摘要", "对方科目", "金额", "凭证日期", "凭证编号",
            "付款方式", "银行流水", "付款审批", "审计结论", "备注",
        ],
        "field_keys": [
            "seq", "summary", "counterAccount", "amount", "voucherDate", "voucherNo",
            "paymentMethod", "bankReconciliation", "paymentApproval", "auditConclusion", "remark",
        ],
        "guidance": ["F4-8 借方检查区 编制说明", "", "对应应付账款借方发生/付款凭证抽查。"],
    },
    "F4-8-credit": {
        "item_id": "F4-8-credit-rows",
        "title": "F4-8 应付账款检查 — 贷方区(采购/增加)",
        "headers": [
            "序号", "摘要", "对方科目", "金额", "凭证日期", "凭证编号",
            "采购订单", "入库单", "发票核对", "三单匹配", "审计结论", "备注",
        ],
        "field_keys": [
            "seq", "summary", "counterAccount", "amount", "voucherDate", "voucherNo",
            "purchaseOrder", "goodsReceipt", "invoiceCheck", "threeWayMatch", "auditConclusion", "remark",
        ],
        "guidance": ["F4-8 贷方检查区 编制说明", "", "对应应付账款贷方发生/采购凭证抽查。"],
    },
    "F4-9-factoring": {
        "item_id": "F4-9-factoring-rows",
        "title": "F4-9 供应商融资 — 保理融资",
        "headers": [
            "序号", "供应商", "保理公司", "保理金额", "保理日期", "到期日", "保理费率",
            "是否有追索权", "是否终止确认", "列报科目", "审计评价", "备注",
        ],
        "field_keys": [
            "seq", "vendor", "factor", "amount", "startDate", "dueDate", "rate",
            "hasRecourse", "derecognized", "reportingAccount", "auditEvaluation", "remark",
        ],
        "guidance": ["F4-9 保理融资区 编制说明"],
    },
    "F4-9-note": {
        "item_id": "F4-9-note-rows",
        "title": "F4-9 供应商融资 — 票据融资",
        "headers": [
            "序号", "供应商", "票据类型", "票据金额", "出票日", "到期日", "贴现金额",
            "贴现利率", "是否背书转让", "列报适当性", "审计评价", "备注",
        ],
        "field_keys": [
            "seq", "vendor", "noteType", "noteAmount", "issueDate", "dueDate", "discountAmount",
            "discountRate", "isEndorsed", "reportingAppropriate", "auditEvaluation", "remark",
        ],
        "guidance": ["F4-9 票据融资区 编制说明"],
    },
    "F4-9-supply": {
        "item_id": "F4-9-supply-rows",
        "title": "F4-9 供应商融资 — 供应链融资",
        "headers": [
            "序号", "供应商", "核心企业", "融资金额", "融资日期", "到期日", "融资利率",
            "平台名称", "是否修改付款条件", "是否应重分类", "审计评价", "备注",
        ],
        "field_keys": [
            "seq", "vendor", "coreEnterprise", "amount", "startDate", "dueDate", "rate",
            "platform", "paymentTermsChanged", "needReclass", "auditEvaluation", "remark",
        ],
        "guidance": ["F4-9 供应链融资区 编制说明"],
    },
}

router = create_cycle_import_export_router(tag="f4-import-export", api_prefix="f4", specs=_F4_SPECS)
