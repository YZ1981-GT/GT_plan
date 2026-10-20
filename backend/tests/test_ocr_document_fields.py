"""OCR 单据字段清单与规则层一致性（preexisting-test-failures-closure G10 口径）。"""
from __future__ import annotations

import pytest

from app.services import ocr_rule_engine as rules
from app.services.ocr_document_fields import DOCUMENT_FIELD_RULES, DOCUMENT_TYPE_LABELS
from app.services.ocr_service_v2 import OCRService


def _by_name(text: str, doc_type: str) -> dict[str, str]:
    return {f["field_name"]: f["field_value"] for f in rules.extract_fields_by_rules(text, doc_type)}


def test_single_source_shared_with_ocr_service():
    assert OCRService.DOCUMENT_FIELD_RULES is DOCUMENT_FIELD_RULES
    assert OCRService.DOCUMENT_TYPE_LABELS is DOCUMENT_TYPE_LABELS
    assert set(DOCUMENT_FIELD_RULES) == set(DOCUMENT_TYPE_LABELS)


def test_every_type_the_rule_classifier_returns_has_a_field_list():
    """规则分类器给得出的类型都要有清单（原先 7 类报销票据不在表里，提取结果恒为空）。"""
    for doc_type in rules._CLASSIFY_RULES:
        assert DOCUMENT_FIELD_RULES.get(doc_type), doc_type


def test_type_specific_patterns_only_produce_listed_fields():
    """专用正则取的字段必须在本类清单内，否则取了也被丢弃（如原物流单的 weight）。"""
    for doc_type, patterns in rules._TYPE_SPECIFIC_PATTERNS.items():
        assert doc_type in DOCUMENT_FIELD_RULES, doc_type
        assert set(patterns) <= set(DOCUMENT_FIELD_RULES[doc_type]), (doc_type, set(patterns))


def test_field_lists_have_no_duplicates():
    for doc_type, fields in DOCUMENT_FIELD_RULES.items():
        assert len(fields) == len(set(fields)), doc_type


def test_type_specific_pattern_wins_over_generic_invoice_pattern():
    """纳税申报表的 amount 是应纳税额；原先通用「金额」先跑，专用正则被跳过。"""
    text = "增值税纳税申报表\n销售额 金额：100.00\n应纳税额：5,000.00\n申报日期：2025年4月15日"
    fields = _by_name(text, "tax_return")
    assert fields["amount"] == "5000.00"
    assert fields["filing_date"] == "2025-04-15"


@pytest.mark.parametrize(("doc_type", "text", "field", "expected"), [
    ("contract", "合同编号：HT-2025-0089\n签订日期：2025年1月8日", "sign_date", "2025-01-08"),
    ("contract", "合同编号：HT-2025-0089\n签订日期：2025年1月8日", "contract_no", "HT-2025-0089"),
    ("bank_receipt", "交易日期：2024/1/5\n交易金额：1,000.00", "transaction_date", "2024-01-05"),
    ("bank_statement", "银行对账单\n期初余额：1,234,567.89\n期末余额：2,000.00", "opening_balance", "1234567.89"),
    ("bank_reconciliation", "银行余额调节表\n银行对账单余额：3,000.00\n企业账面余额：2,900.00", "book_balance", "2900.00"),
    ("accommodation_receipt", "如家商务酒店\n入住日期：2025年3月1日", "hotel_name", "如家商务酒店"),
    ("accommodation_receipt", "如家商务酒店\n入住日期：2025年3月1日", "check_in", "2025-03-01"),
    ("sales_invoice", "价税合计：¥32,205.00", "total", "32205.00"),
])
def test_values_use_the_same_format_as_the_llm_prompt(doc_type, text, field, expected):
    """日期 YYYY-MM-DD、金额 / 余额去千分位（与 extract_fields 给大模型的格式要求一致）。"""
    assert _by_name(text, doc_type)[field] == expected


def test_bank_receipt_counterparty_only_when_printed():
    two_party = _by_name("付款人：深圳制造有限公司\n收款人：上海贸易有限公司", "bank_receipt")
    assert (two_party["payer_name"], two_party["payee_name"]) == ("深圳制造有限公司", "上海贸易有限公司")
    assert "counterparty_name" not in two_party
    assert _by_name("对方户名：XYZ公司", "bank_receipt")["counterparty_name"] == "XYZ公司"
