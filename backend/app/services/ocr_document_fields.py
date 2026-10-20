"""OCR 单据类型与每类要识别的字段（单一来源；OCRService 与规则层共用）。

口径（preexisting-test-failures-closure G10，2026-10-20 按实际用途定）：

- 提取结果只含本类单据清单内的字段：规则层先取，取不到的交大模型补，清单外的一律不输出
  （原先通用发票正则对所有单据都跑，银行回单会多出一个由「日期」误抓的 invoice_date）。
- 清单按审计用途定：单据拿来与序时账 / 凭证核对、填底稿，每类都要回答「多少钱、哪天、和谁、什么单号」，
  再加该类单据特有的关键数。值一律按大模型提示词同一格式：金额去千分位，日期 YYYY-MM-DD。
"""
from __future__ import annotations

DOCUMENT_TYPE_LABELS: dict[str, str] = {
    "sales_invoice": "销售发票",
    "purchase_invoice": "采购发票",
    "bank_receipt": "银行收付款回单",
    "bank_statement": "银行对账单",
    "outbound_order": "出库单",
    "inbound_order": "入库单",
    "logistics_order": "物流单据",
    "voucher": "记账凭证",
    "tax_return": "纳税申报表",
    "contract": "合同协议",
    "bank_reconciliation": "银行余额调节表",
    # 以下 7 类只由规则分类器给出（大模型分类只在 12 类里选）；原先不在字段表里 ⇒ 提取结果恒为空
    "train_ticket": "火车票",
    "flight_itinerary": "航空运输电子客票行程单",
    "taxi_receipt": "出租车发票",
    "accommodation_receipt": "住宿发票",
    "toll_invoice": "通行费发票",
    "catering_receipt": "餐饮发票",
    "fixed_amount_invoice": "定额发票",
    "other": "其他单据",
}

_INVOICE_FIELDS = [
    # 两方名称都印在票面上：销项核对购买方是否为客户、进项核对销售方是否为供应商，另一方核对是否为本单位；
    # total（价税合计）是应收 / 应付的挂账金额，规则层还用它校验「金额 + 税额」
    "invoice_no", "invoice_date", "buyer_name", "seller_name", "goods_name",
    "amount", "tax_amount", "total",
]

DOCUMENT_FIELD_RULES: dict[str, list[str]] = {
    "sales_invoice": list(_INVOICE_FIELDS),
    "purchase_invoice": list(_INVOICE_FIELDS),
    # 付款人 / 收款人照票面取，不猜哪一方是「对方」（收款回单上的收款人就是本单位）；
    # 票面写了「对方户名」时才有 counterparty_name
    "bank_receipt": [
        "transaction_date", "payer_name", "payee_name", "counterparty_name",
        "amount", "summary", "transaction_type",
    ],
    # 对账单与调节表核对的是账户和余额（E1 银行存款），不是单笔交易
    "bank_statement": ["bank_name", "account_no", "statement_date", "opening_balance", "closing_balance"],
    "bank_reconciliation": ["bank_name", "account_no", "statement_date", "bank_balance", "book_balance"],
    "outbound_order": ["outbound_date", "product_name", "quantity", "unit_price", "amount", "customer", "warehouse"],
    "inbound_order": ["inbound_date", "product_name", "quantity", "unit_price", "amount", "supplier", "warehouse"],
    # 签收日期是收入截止测试的关键
    "logistics_order": ["tracking_no", "ship_date", "sign_date", "sender", "receiver"],
    "voucher": ["voucher_no", "date", "summary", "account_code", "account_name", "amount", "debit", "credit"],
    "tax_return": ["tax_type", "period", "amount", "filing_date"],
    "contract": [
        "contract_no", "party_a", "party_b", "contract_amount",
        "sign_date", "expire_date", "payment_terms",
    ],
    # 报销类票据（费用凭证抽查）：日期、金额，加能核对业务真实性的行程 / 商户
    "train_ticket": ["travel_date", "train_no", "departure", "arrival", "seat_class", "passenger_name", "amount"],
    "flight_itinerary": ["flight_date", "flight_no", "departure", "arrival", "passenger_name", "amount"],
    "taxi_receipt": ["invoice_no", "invoice_date", "amount"],
    "accommodation_receipt": ["hotel_name", "check_in", "check_out", "nights", "amount"],
    "toll_invoice": ["invoice_no", "invoice_date", "amount"],
    "catering_receipt": ["restaurant_name", "invoice_date", "amount"],
    "fixed_amount_invoice": ["invoice_no", "amount"],
    "other": [],
}
