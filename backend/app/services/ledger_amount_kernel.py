from __future__ import annotations
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Literal
import math

_MAX_ABS = Decimal('999999999999999999.99')

UNIT_FACTORS = {'yuan': Decimal('1'), 'qian': Decimal('1000'), 'wan': Decimal('10000')}

_SKIP = ('_qty', '_fc', '_count', '_num', '_pcs')

AmountErrorCode = Literal['LEDGER_AMOUNT_INVALID', 'LEDGER_AMOUNT_NOT_FINITE', 'LEDGER_AMOUNT_OVERFLOW']

class LedgerAmountError(Exception):
    def __init__(self, code: AmountErrorCode, *, file: str = '', sheet: str = '', row: int = 0, field: str = '') -> None:
        self.code, self.file, self.sheet, self.row, self.field = code, file, sheet, row, field
        super().__init__(f'{code} file={file} sheet={sheet} row={row} field={field}')

def is_amount_field(name: str) -> bool:
    return not any(name.lower().endswith(s) for s in _SKIP)

def convert_amount(value: object, factor: Decimal, *, file: str = '', sheet: str = '', row: int = 0, field: str = '') -> Decimal | None:
    if value is None:
        return None
    loc = dict(file=file, sheet=sheet, row=row, field=field)
    d: Decimal
    if isinstance(value, Decimal):
        d = value
    elif isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            raise LedgerAmountError('LEDGER_AMOUNT_NOT_FINITE', **loc)
        try:
            d = Decimal(str(value))
        except (InvalidOperation, ValueError, OverflowError):
            raise LedgerAmountError('LEDGER_AMOUNT_INVALID', **loc)
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            d = Decimal(s)
        except (InvalidOperation, ValueError):
            raise LedgerAmountError('LEDGER_AMOUNT_INVALID', **loc)
    else:
        raise LedgerAmountError('LEDGER_AMOUNT_INVALID', **loc)
    if not d.is_finite():
        raise LedgerAmountError('LEDGER_AMOUNT_NOT_FINITE', **loc)
    result = (d * factor).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if abs(result) > _MAX_ABS:
        raise LedgerAmountError('LEDGER_AMOUNT_OVERFLOW', **loc)
    return result
