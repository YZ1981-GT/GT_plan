"""AmountDecimal Pydantic 字段类型测试 — V3 收官增强 Req 2 Task 2.2

覆盖 ``backend/app/schemas/_common.py`` 中 ``AmountDecimal`` /
``OptionalAmountDecimal`` 在 5 核心 schema 上的接入：

- AdjustmentCreate / AdjustmentLineItem (debit_amount / credit_amount)
- MisstatementCreate / MisstatementUpdate (misstatement_amount)
- ToggleModeRequest (附注 cell manual_value，DisclosureCellUpdate)
- PrefillChange (底稿 prefill cell，PrefillCellUpdate)

关键断言：
- NaN / Infinity / -Infinity 均被 Pydantic 422 拒绝（中文错误消息）
- str / int / float / Decimal 合法值正常转 Decimal
- 空字符串拒绝，None 仅在可选字段下放行
"""

from __future__ import annotations

import math
from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from app.models.audit_platform_schemas import (
    AdjustmentCreate,
    AdjustmentLineItem,
    AdjustmentType,
    MisstatementCreate,
    MisstatementType,
    MisstatementUpdate,
)
from app.routers.note_wp_mapping import ToggleModeRequest
from app.routers.wp_prefill_preview import PrefillChange
from app.schemas._common import AmountDecimal, OptionalAmountDecimal


# ==========================================================================
# AmountDecimal / OptionalAmountDecimal 通用契约
# ==========================================================================


class _RequiredModel(BaseModel):
    value: AmountDecimal


class _OptionalModel(BaseModel):
    value: OptionalAmountDecimal = None


class TestAmountDecimalBasic:
    """AmountDecimal 类型基础契约（不依赖具体业务 schema）。"""

    # --- 合法输入 ---

    def test_string_number_accepted(self):
        m = _RequiredModel(value="123.45")
        assert m.value == Decimal("123.45")
        assert isinstance(m.value, Decimal)

    def test_int_accepted(self):
        m = _RequiredModel(value=100)
        assert m.value == Decimal("100")

    def test_float_accepted_via_str_conversion(self):
        # to_decimal 内部用 str(value) 避免浮点表示误差
        m = _RequiredModel(value=3.14)
        assert m.value == Decimal(str(3.14))

    def test_decimal_passthrough(self):
        d = Decimal("99.99")
        m = _RequiredModel(value=d)
        assert m.value == d

    def test_negative_value_accepted(self):
        m = _RequiredModel(value="-500.25")
        assert m.value == Decimal("-500.25")

    def test_scientific_notation_accepted(self):
        m = _RequiredModel(value="1.5e3")
        assert m.value == Decimal("1500")

    def test_zero_accepted(self):
        m = _RequiredModel(value=0)
        assert m.value == Decimal("0")

    # --- NaN / Infinity 拒绝 ---

    def test_nan_string_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            _RequiredModel(value="NaN")
        assert "NaN 或 Infinity" in str(exc_info.value)

    def test_infinity_string_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            _RequiredModel(value="Infinity")
        assert "NaN 或 Infinity" in str(exc_info.value)

    def test_negative_infinity_string_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            _RequiredModel(value="-Infinity")
        assert "NaN 或 Infinity" in str(exc_info.value)

    def test_float_nan_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            _RequiredModel(value=float("nan"))
        assert "NaN 或 Infinity" in str(exc_info.value)

    def test_float_inf_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            _RequiredModel(value=math.inf)
        assert "NaN 或 Infinity" in str(exc_info.value)

    def test_float_neg_inf_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            _RequiredModel(value=-math.inf)
        assert "NaN 或 Infinity" in str(exc_info.value)

    # --- 非法格式 ---

    def test_empty_string_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            _RequiredModel(value="")
        assert "格式非法" in str(exc_info.value)

    def test_garbage_string_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            _RequiredModel(value="abc")
        assert "格式非法" in str(exc_info.value)

    # --- None 处理：required 拒绝，optional 放行 ---

    def test_required_none_rejected(self):
        with pytest.raises(ValidationError):
            _RequiredModel(value=None)

    def test_optional_none_passthrough(self):
        m = _OptionalModel(value=None)
        assert m.value is None

    def test_optional_default_is_none(self):
        m = _OptionalModel()
        assert m.value is None

    def test_optional_nan_still_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            _OptionalModel(value="NaN")
        assert "NaN 或 Infinity" in str(exc_info.value)


# ==========================================================================
# AdjustmentCreate / AdjustmentLineItem
# ==========================================================================


def _build_line_item(*, debit="0", credit="0") -> dict:
    return {
        "standard_account_code": "1001",
        "account_name": "库存现金",
        "debit_amount": debit,
        "credit_amount": credit,
    }


class TestAdjustmentCreate:
    """AdjustmentCreate / AdjustmentLineItem 应在借贷金额上拒绝 NaN/Infinity。"""

    def test_create_accepts_string_decimal(self):
        body = AdjustmentCreate(
            adjustment_type=AdjustmentType.aje,
            year=2025,
            description="借现金 100 / 贷应付账款 100",
            line_items=[
                _build_line_item(debit="100.50"),
                _build_line_item(credit="100.50"),
            ],
        )
        assert body.line_items[0].debit_amount == Decimal("100.50")
        assert body.line_items[1].credit_amount == Decimal("100.50")

    def test_create_accepts_int_and_float(self):
        body = AdjustmentCreate(
            adjustment_type=AdjustmentType.aje,
            year=2025,
            line_items=[_build_line_item(debit=100, credit=99.99)],
        )
        assert body.line_items[0].debit_amount == Decimal("100")
        assert body.line_items[0].credit_amount == Decimal(str(99.99))

    def test_line_item_default_zero(self):
        # 默认值仍为 Decimal("0")，AmountDecimal 装饰不影响默认
        item = AdjustmentLineItem(standard_account_code="1001")
        assert item.debit_amount == Decimal("0")
        assert item.credit_amount == Decimal("0")

    def test_debit_nan_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            AdjustmentCreate(
                adjustment_type=AdjustmentType.aje,
                year=2025,
                line_items=[_build_line_item(debit="NaN")],
            )
        assert "NaN 或 Infinity" in str(exc_info.value)

    def test_credit_infinity_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            AdjustmentCreate(
                adjustment_type=AdjustmentType.aje,
                year=2025,
                line_items=[_build_line_item(credit=float("inf"))],
            )
        assert "NaN 或 Infinity" in str(exc_info.value)


# ==========================================================================
# MisstatementCreate / MisstatementUpdate
# ==========================================================================


def _misstatement_payload(amount) -> dict:
    return {
        "year": 2025,
        "misstatement_description": "存货跌价准备少计提",
        "affected_account_code": "1232",
        "misstatement_amount": amount,
        "misstatement_type": MisstatementType.judgmental,
    }


class TestMisstatementSchemas:
    """MisstatementCreate / Update 拒绝 NaN/Infinity 金额。"""

    def test_create_accepts_string_amount(self):
        m = MisstatementCreate(**_misstatement_payload("12345.67"))
        assert m.misstatement_amount == Decimal("12345.67")

    def test_create_accepts_int_amount(self):
        m = MisstatementCreate(**_misstatement_payload(50000))
        assert m.misstatement_amount == Decimal("50000")

    def test_create_rejects_nan(self):
        with pytest.raises(ValidationError) as exc_info:
            MisstatementCreate(**_misstatement_payload("NaN"))
        assert "NaN 或 Infinity" in str(exc_info.value)

    def test_create_rejects_infinity(self):
        with pytest.raises(ValidationError) as exc_info:
            MisstatementCreate(**_misstatement_payload(float("inf")))
        assert "NaN 或 Infinity" in str(exc_info.value)

    def test_update_accepts_none(self):
        # Update 字段全部可选；不传金额时通过
        m = MisstatementUpdate(misstatement_description="补充说明")
        assert m.misstatement_amount is None

    def test_update_accepts_decimal_string(self):
        m = MisstatementUpdate(misstatement_amount="888.88")
        assert m.misstatement_amount == Decimal("888.88")

    def test_update_rejects_nan(self):
        with pytest.raises(ValidationError) as exc_info:
            MisstatementUpdate(misstatement_amount="NaN")
        assert "NaN 或 Infinity" in str(exc_info.value)

    def test_update_rejects_negative_infinity(self):
        with pytest.raises(ValidationError) as exc_info:
            MisstatementUpdate(misstatement_amount=-math.inf)
        assert "NaN 或 Infinity" in str(exc_info.value)


# ==========================================================================
# DisclosureCellUpdate (ToggleModeRequest.manual_value)
# ==========================================================================


class TestDisclosureCellUpdate:
    """附注 cell 手动值 manual_value 拒绝 NaN/Infinity（OptionalAmountDecimal）。"""

    def test_manual_value_string_accepted(self):
        m = ToggleModeRequest(
            row_label="货币资金",
            col_index=2,
            mode="manual",
            manual_value="1234.56",
        )
        assert m.manual_value == Decimal("1234.56")

    def test_manual_value_int_accepted(self):
        m = ToggleModeRequest(
            row_label="货币资金", col_index=2, mode="manual", manual_value=1234
        )
        assert m.manual_value == Decimal("1234")

    def test_manual_value_float_accepted(self):
        m = ToggleModeRequest(
            row_label="货币资金", col_index=2, mode="manual", manual_value=1234.56
        )
        assert m.manual_value == Decimal(str(1234.56))

    def test_manual_value_none_for_auto_mode(self):
        # 切回 auto 模式时 manual_value 不传 → None
        m = ToggleModeRequest(row_label="货币资金", col_index=2, mode="auto")
        assert m.manual_value is None

    def test_manual_value_nan_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            ToggleModeRequest(
                row_label="货币资金", col_index=2, mode="manual", manual_value="NaN"
            )
        assert "NaN 或 Infinity" in str(exc_info.value)

    def test_manual_value_infinity_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            ToggleModeRequest(
                row_label="货币资金",
                col_index=2,
                mode="manual",
                manual_value=float("inf"),
            )
        assert "NaN 或 Infinity" in str(exc_info.value)


# ==========================================================================
# PrefillCellUpdate (PrefillChange.old_value / new_value)
# ==========================================================================


def _prefill_payload(*, old=None, new=None) -> dict:
    return {
        "sheet": "Sheet1",
        "cell_ref": "B7",
        "formula": "=TB('1001','closing')",
        "old_value": old,
        "new_value": new,
        "change_pct": 0.0,
        "is_highlight": False,
    }


class TestPrefillCellUpdate:
    """Prefill 单元格的 old/new value 拒绝 NaN/Infinity（OptionalAmountDecimal）。"""

    def test_string_values_accepted(self):
        c = PrefillChange(**_prefill_payload(old="100.00", new="200.50"))
        assert c.old_value == Decimal("100.00")
        assert c.new_value == Decimal("200.50")

    def test_int_values_accepted(self):
        c = PrefillChange(**_prefill_payload(old=100, new=200))
        assert c.old_value == Decimal("100")
        assert c.new_value == Decimal("200")

    def test_float_values_accepted(self):
        c = PrefillChange(**_prefill_payload(old=100.5, new=200.75))
        assert c.old_value == Decimal(str(100.5))
        assert c.new_value == Decimal(str(200.75))

    def test_none_values_accepted(self):
        # 新增 cell（old_value=None） / 删除 cell（new_value=None）合法
        c = PrefillChange(**_prefill_payload(old=None, new="500"))
        assert c.old_value is None
        assert c.new_value == Decimal("500")

    def test_old_value_nan_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            PrefillChange(**_prefill_payload(old="NaN", new="100"))
        assert "NaN 或 Infinity" in str(exc_info.value)

    def test_new_value_infinity_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            PrefillChange(**_prefill_payload(old="100", new=float("inf")))
        assert "NaN 或 Infinity" in str(exc_info.value)
