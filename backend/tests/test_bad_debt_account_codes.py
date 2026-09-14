"""坏账科目编码解析单元测试。"""

from app.services.account_chart_service import resolve_standard_account_by_name
from app.services.bad_debt_account_codes import (
    bad_debt_provision_account,
    impairment_loss_account,
)


def test_resolve_bad_debt_provision_from_standard_chart():
    code, name = bad_debt_provision_account()
    assert code == "1231"
    assert name == "坏账准备"


def test_resolve_impairment_loss_prefers_credit_impairment():
    code, name = impairment_loss_account()
    assert code in ("6701", "6702")
    assert name in ("信用减值损失", "资产减值损失")


def test_resolve_standard_account_by_name_exact():
    code, name = resolve_standard_account_by_name("银行存款")
    assert code == "1002"
    assert name == "银行存款"
