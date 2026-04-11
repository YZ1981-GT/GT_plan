"""数据导入解析器工厂 — BaseParser + GenericParser + 财务软件解析器

Validates: Requirements 4.1, 4.2
"""

import csv
import io
from abc import ABC, abstractmethod
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Column name mappings for each data type (Chinese → English)
# ---------------------------------------------------------------------------

_BALANCE_COLUMN_MAP = {
    # Chinese
    "科目编码": "account_code",
    "科目代码": "account_code",
    "编码": "account_code",
    "科目名称": "account_name",
    "名称": "account_name",
    "期初余额": "opening_balance",
    "期初": "opening_balance",
    "年初余额": "opening_balance",
    "借方发生额": "debit_amount",
    "借方金额": "debit_amount",
    "本期借方": "debit_amount",
    "贷方发生额": "credit_amount",
    "贷方金额": "credit_amount",
    "本期贷方": "credit_amount",
    "期末余额": "closing_balance",
    "期末": "closing_balance",
    "币种": "currency_code",
    "单位编码": "company_code",
    "公司编码": "company_code",
    # English
    "account_code": "account_code",
    "account_name": "account_name",
    "opening_balance": "opening_balance",
    "debit_amount": "debit_amount",
    "credit_amount": "credit_amount",
    "closing_balance": "closing_balance",
    "currency_code": "currency_code",
    "company_code": "company_code",
}

_LEDGER_COLUMN_MAP = {
    "科目编码": "account_code",
    "科目代码": "account_code",
    "科目名称": "account_name",
    "凭证日期": "voucher_date",
    "日期": "voucher_date",
    "记账日期": "voucher_date",
    "凭证号": "voucher_no",
    "凭证编号": "voucher_no",
    "借方金额": "debit_amount",
    "借方发生额": "debit_amount",
    "贷方金额": "credit_amount",
    "贷方发生额": "credit_amount",
    "对方科目": "counterpart_account",
    "摘要": "summary",
    "制单人": "preparer",
    "编制人": "preparer",
    "币种": "currency_code",
    "单位编码": "company_code",
    "公司编码": "company_code",
    # English
    "account_code": "account_code",
    "account_name": "account_name",
    "voucher_date": "voucher_date",
    "voucher_no": "voucher_no",
    "debit_amount": "debit_amount",
    "credit_amount": "credit_amount",
    "counterpart_account": "counterpart_account",
    "summary": "summary",
    "preparer": "preparer",
    "currency_code": "currency_code",
    "company_code": "company_code",
}

_AUX_BALANCE_COLUMN_MAP = {
    "科目编码": "account_code",
    "科目代码": "account_code",
    "科目名称": "account_name",
    "辅助类型": "aux_type",
    "核算类型": "aux_type",
    "辅助编码": "aux_code",
    "核算编码": "aux_code",
    "辅助名称": "aux_name",
    "核算名称": "aux_name",
    "期初余额": "opening_balance",
    "期初": "opening_balance",
    "借方发生额": "debit_amount",
    "借方金额": "debit_amount",
    "贷方发生额": "credit_amount",
    "贷方金额": "credit_amount",
    "期末余额": "closing_balance",
    "期末": "closing_balance",
    "币种": "currency_code",
    "单位编码": "company_code",
    "公司编码": "company_code",
    # English
    "account_code": "account_code",
    "account_name": "account_name",
    "aux_type": "aux_type",
    "aux_code": "aux_code",
    "aux_name": "aux_name",
    "opening_balance": "opening_balance",
    "debit_amount": "debit_amount",
    "credit_amount": "credit_amount",
    "closing_balance": "closing_balance",
    "currency_code": "currency_code",
    "company_code": "company_code",
}

_AUX_LEDGER_COLUMN_MAP = {
    "科目编码": "account_code",
    "科目代码": "account_code",
    "科目名称": "account_name",
    "辅助类型": "aux_type",
    "核算类型": "aux_type",
    "辅助编码": "aux_code",
    "核算编码": "aux_code",
    "辅助名称": "aux_name",
    "核算名称": "aux_name",
    "凭证日期": "voucher_date",
    "日期": "voucher_date",
    "凭证号": "voucher_no",
    "凭证编号": "voucher_no",
    "借方金额": "debit_amount",
    "借方发生额": "debit_amount",
    "贷方金额": "credit_amount",
    "贷方发生额": "credit_amount",
    "摘要": "summary",
    "制单人": "preparer",
    "编制人": "preparer",
    "币种": "currency_code",
    "单位编码": "company_code",
    "公司编码": "company_code",
    # English
    "account_code": "account_code",
    "account_name": "account_name",
    "aux_type": "aux_type",
    "aux_code": "aux_code",
    "aux_name": "aux_name",
    "voucher_date": "voucher_date",
    "voucher_no": "voucher_no",
    "debit_amount": "debit_amount",
    "credit_amount": "credit_amount",
    "summary": "summary",
    "preparer": "preparer",
    "currency_code": "currency_code",
    "company_code": "company_code",
}

_COLUMN_MAPS = {
    "tb_balance": _BALANCE_COLUMN_MAP,
    "tb_ledger": _LEDGER_COLUMN_MAP,
    "tb_aux_balance": _AUX_BALANCE_COLUMN_MAP,
    "tb_aux_ledger": _AUX_LEDGER_COLUMN_MAP,
}

# Data type aliases
_DATA_TYPE_ALIASES = {
    "balance": "tb_balance",
    "ledger": "tb_ledger",
    "aux_balance": "tb_aux_balance",
    "aux_ledger": "tb_aux_ledger",
    "tb_balance": "tb_balance",
    "tb_ledger": "tb_ledger",
    "tb_aux_balance": "tb_aux_balance",
    "tb_aux_ledger": "tb_aux_ledger",
}


def normalize_data_type(data_type: str) -> str:
    """Normalize data_type to canonical form (tb_balance, tb_ledger, etc.)."""
    normalized = _DATA_TYPE_ALIASES.get(data_type)
    if not normalized:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的数据类型: {data_type}，支持: balance/ledger/aux_balance/aux_ledger",
        )
    return normalized


# ---------------------------------------------------------------------------
# Value parsing helpers
# ---------------------------------------------------------------------------


def _parse_decimal(value: str | None) -> Decimal | None:
    """Parse a string to Decimal, return None for empty/invalid."""
    if value is None:
        return None
    value = str(value).strip().replace(",", "").replace("，", "")
    if not value or value == "None" or value == "":
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


def _parse_date(value: str | None) -> date | None:
    """Parse a string to date, supporting multiple formats."""
    if value is None:
        return None
    value = str(value).strip()
    if not value or value == "None":
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# BaseParser abstract class
# ---------------------------------------------------------------------------


class BaseParser(ABC):
    """解析器基类 — 所有财务数据解析器的抽象接口。"""

    @abstractmethod
    def parse(self, content: bytes, data_type: str) -> list[dict]:
        """Parse file content into a list of normalized dicts.

        Args:
            content: Raw file bytes (Excel or CSV).
            data_type: One of tb_balance, tb_ledger, tb_aux_balance, tb_aux_ledger.

        Returns:
            List of dicts with normalized English keys and parsed values.
        """
        ...


# ---------------------------------------------------------------------------
# GenericParser — standard template parser
# ---------------------------------------------------------------------------


class GenericParser(BaseParser):
    """通用标准模板解析器 — 解析 Excel/CSV 四表数据。

    Validates: Requirements 4.1, 4.2
    """

    def parse(self, content: bytes, data_type: str) -> list[dict]:
        """Parse Excel or CSV content for the given data type."""
        data_type = normalize_data_type(data_type)
        column_map = _COLUMN_MAPS[data_type]

        # Try Excel first, then CSV
        rows = self._try_parse_excel(content)
        if rows is None:
            rows = self._parse_csv(content)

        if not rows:
            return []

        # Normalize column names
        normalized = self._normalize_columns(rows, column_map)

        # Parse values based on data type
        return self._parse_values(normalized, data_type)

    def _try_parse_excel(self, content: bytes) -> list[dict] | None:
        """Try to parse as Excel. Returns None if not an Excel file."""
        try:
            import openpyxl
            wb = openpyxl.load_workbook(
                io.BytesIO(content), read_only=True, data_only=True
            )
        except Exception:
            return None

        ws = wb.active
        if ws is None:
            wb.close()
            return None

        rows_iter = ws.iter_rows(values_only=True)
        try:
            header = next(rows_iter)
        except StopIteration:
            wb.close()
            return []

        headers = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(header)]

        result = []
        for row in rows_iter:
            if all(cell is None for cell in row):
                continue
            row_dict = {}
            for i, cell in enumerate(row):
                if i < len(headers):
                    row_dict[headers[i]] = str(cell) if cell is not None else ""
            result.append(row_dict)

        wb.close()
        return result

    def _parse_csv(self, content: bytes) -> list[dict]:
        """Parse CSV with encoding detection."""
        for encoding in ("utf-8-sig", "gbk", "utf-8"):
            try:
                text = content.decode(encoding)
                break
            except (UnicodeDecodeError, ValueError):
                continue
        else:
            raise HTTPException(
                status_code=400,
                detail="无法识别文件编码，请使用 UTF-8 或 GBK 编码",
            )

        reader = csv.DictReader(io.StringIO(text))
        return list(reader)

    def _normalize_columns(
        self, rows: list[dict], column_map: dict[str, str]
    ) -> list[dict]:
        """Normalize column names using the provided mapping."""
        normalized = []
        for row in rows:
            new_row = {}
            for key, value in row.items():
                if key is None:
                    continue
                key_str = str(key).strip()
                mapped = column_map.get(key_str, key_str)
                new_row[mapped] = value
            normalized.append(new_row)
        return normalized

    def _parse_values(self, rows: list[dict], data_type: str) -> list[dict]:
        """Parse and convert values based on data type."""
        result = []
        for row in rows:
            parsed = self._parse_single_row(row, data_type)
            if parsed:
                result.append(parsed)
        return result

    def _parse_single_row(self, row: dict, data_type: str) -> dict | None:
        """Parse a single row based on data type."""
        account_code = str(row.get("account_code", "")).strip()
        if not account_code:
            return None

        base = {
            "account_code": account_code,
            "account_name": str(row.get("account_name", "")).strip() or None,
            "company_code": str(row.get("company_code", "")).strip() or "default",
            "currency_code": str(row.get("currency_code", "")).strip() or "CNY",
        }

        if data_type == "tb_balance":
            base.update({
                "opening_balance": _parse_decimal(row.get("opening_balance")),
                "debit_amount": _parse_decimal(row.get("debit_amount")),
                "credit_amount": _parse_decimal(row.get("credit_amount")),
                "closing_balance": _parse_decimal(row.get("closing_balance")),
            })
        elif data_type == "tb_ledger":
            voucher_date = _parse_date(row.get("voucher_date"))
            voucher_no = str(row.get("voucher_no", "")).strip()
            if not voucher_date or not voucher_no:
                return None
            base.update({
                "voucher_date": voucher_date,
                "voucher_no": voucher_no,
                "debit_amount": _parse_decimal(row.get("debit_amount")),
                "credit_amount": _parse_decimal(row.get("credit_amount")),
                "counterpart_account": str(row.get("counterpart_account", "")).strip() or None,
                "summary": str(row.get("summary", "")).strip() or None,
                "preparer": str(row.get("preparer", "")).strip() or None,
            })
        elif data_type == "tb_aux_balance":
            aux_type = str(row.get("aux_type", "")).strip()
            if not aux_type:
                return None
            base.update({
                "aux_type": aux_type,
                "aux_code": str(row.get("aux_code", "")).strip() or None,
                "aux_name": str(row.get("aux_name", "")).strip() or None,
                "opening_balance": _parse_decimal(row.get("opening_balance")),
                "debit_amount": _parse_decimal(row.get("debit_amount")),
                "credit_amount": _parse_decimal(row.get("credit_amount")),
                "closing_balance": _parse_decimal(row.get("closing_balance")),
            })
        elif data_type == "tb_aux_ledger":
            base.update({
                "aux_type": str(row.get("aux_type", "")).strip() or None,
                "aux_code": str(row.get("aux_code", "")).strip() or None,
                "aux_name": str(row.get("aux_name", "")).strip() or None,
                "voucher_date": _parse_date(row.get("voucher_date")),
                "voucher_no": str(row.get("voucher_no", "")).strip() or None,
                "debit_amount": _parse_decimal(row.get("debit_amount")),
                "credit_amount": _parse_decimal(row.get("credit_amount")),
                "summary": str(row.get("summary", "")).strip() or None,
                "preparer": str(row.get("preparer", "")).strip() or None,
            })

        return base


# ---------------------------------------------------------------------------
# Stub parsers for specific financial software
# ---------------------------------------------------------------------------


class YonyouParser(BaseParser):
    """用友U8/T+解析器 — 当前委托给 GenericParser。

    Validates: Requirements 4.1
    """

    def __init__(self) -> None:
        self._generic = GenericParser()

    def parse(self, content: bytes, data_type: str) -> list[dict]:
        return self._generic.parse(content, data_type)


class KingdeeParser(BaseParser):
    """金蝶K3/KIS解析器 — 当前委托给 GenericParser。

    Validates: Requirements 4.1
    """

    def __init__(self) -> None:
        self._generic = GenericParser()

    def parse(self, content: bytes, data_type: str) -> list[dict]:
        return self._generic.parse(content, data_type)


class SAPParser(BaseParser):
    """SAP解析器 — 当前委托给 GenericParser。

    Validates: Requirements 4.1
    """

    def __init__(self) -> None:
        self._generic = GenericParser()

    def parse(self, content: bytes, data_type: str) -> list[dict]:
        return self._generic.parse(content, data_type)


# ---------------------------------------------------------------------------
# ParserFactory
# ---------------------------------------------------------------------------


class ParserFactory:
    """解析器工厂 — 根据数据源类型返回对应解析器。

    Validates: Requirements 4.1
    """

    _parsers: dict[str, type[BaseParser]] = {
        "generic": GenericParser,
        "yonyou": YonyouParser,
        "kingdee": KingdeeParser,
        "sap": SAPParser,
    }

    @classmethod
    def get_parser(cls, source_type: str) -> BaseParser:
        """Get parser instance for the given source type."""
        parser_cls = cls._parsers.get(source_type)
        if not parser_cls:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的数据源类型: {source_type}，支持: {', '.join(cls._parsers.keys())}",
            )
        return parser_cls()
