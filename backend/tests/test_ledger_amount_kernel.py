import pytest
from decimal import Decimal
from app.services.ledger_amount_kernel import convert_amount, is_amount_field, LedgerAmountError, UNIT_FACTORS

class TestConvertAmount:
    def test_none_returns_none(self):
        assert convert_amount(None, Decimal('10000')) is None

    def test_empty_string_returns_none(self):
        assert convert_amount('  ', Decimal('1')) is None

    @pytest.mark.parametrize('unit,factor', [('yuan', 1), ('qian', 1000), ('wan', 10000)])
    def test_three_factors(self, unit, factor):
        result = convert_amount(Decimal('100'), UNIT_FACTORS[unit])
        assert result == Decimal(str(100 * factor)).quantize(Decimal('0.01'))

    def test_round_half_up(self):
        result = convert_amount(Decimal('0.005'), Decimal('1'))
        assert result == Decimal('0.01')

    def test_negative_half_up(self):
        result = convert_amount(Decimal('-0.005'), Decimal('1'))
        assert result == Decimal('-0.01')

    def test_float_nan_raises(self):
        with pytest.raises(LedgerAmountError) as exc:
            convert_amount(float('nan'), Decimal('1'))
        assert exc.value.code == 'LEDGER_AMOUNT_NOT_FINITE'

    def test_float_inf_raises(self):
        with pytest.raises(LedgerAmountError) as exc:
            convert_amount(float('inf'), Decimal('1'))
        assert exc.value.code == 'LEDGER_AMOUNT_NOT_FINITE'

    def test_invalid_string_raises(self):
        with pytest.raises(LedgerAmountError) as exc:
            convert_amount('abc', Decimal('1'))
        assert exc.value.code == 'LEDGER_AMOUNT_INVALID'

    def test_overflow_raises(self):
        huge = Decimal('1' + '0' * 18)
        with pytest.raises(LedgerAmountError) as exc:
            convert_amount(huge, Decimal('1'))
        assert exc.value.code == 'LEDGER_AMOUNT_OVERFLOW'

    def test_string_decimal_parsed(self):
        assert convert_amount('123.456', Decimal('1')) == Decimal('123.46')

    def test_int_converted(self):
        assert convert_amount(100, Decimal('10000')) == Decimal('1000000.00')

    def test_error_contains_location(self):
        with pytest.raises(LedgerAmountError) as exc:
            convert_amount('bad', Decimal('1'), file='a.xlsx', sheet='S1', row=5, field='amount')
        assert exc.value.file == 'a.xlsx'
        assert exc.value.row == 5

class TestIsAmountField:
    @pytest.mark.parametrize('name', ['debit_amount', 'credit_amount', 'balance', 'audited_amount'])
    def test_amount_fields(self, name):
        assert is_amount_field(name) is True

    @pytest.mark.parametrize('name', ['debit_qty', 'amount_fc', 'item_count', 'line_num', 'total_pcs'])
    def test_skip_fields(self, name):
        assert is_amount_field(name) is False
