"""SAP ERP / B1 适配器。

见 design.md §5 / Sprint 1 Task 17。

职责：

- ``id = "sap"`` / ``priority = 70``。
- 只定义 **关键列 + 次关键列** 的英文别名（``balance`` / ``ledger`` 两张表）；
  ``aux_balance`` / ``aux_ledger`` / ``account_chart`` 返回空 dict，走 ``GenericAdapter``
  的通用模糊匹配兜底。
- 识别特征（``match``）：
    - 文件名命中 ``SAP`` 且左右非字母（``_`` / 数字 / 空白 / 句末均视为边界，
      设计文档 ``\\bSAP\\b`` 的实现版；注：Python ``\\b`` 视 ``_`` 为字符，
      但真实文件名常见 ``SAP_GL_...`` 需识别，因此改用字母 look-around）
      → ``+0.5``
    - 某个 sheet 的 header 与 SAP 关键信号集
      ``{"Posting Date","Document Number","G/L Account","Debit","Credit"}`` 交集 ≥ 2
      → ``+0.3``
    - 总分 ``min(score, 1.0)``

注册：由 ``adapters/__init__.py`` 统一注册，vendor 文件不得副作用注册。
"""

import re
from typing import TYPE_CHECKING

from .base import BaseAdapter

if TYPE_CHECKING:
    from ..detection_types import FileDetection, TableType


_FILENAME_RE = re.compile(r"(?i)(?<![A-Za-z])SAP(?![A-Za-z])")
_HEADER_SIGNATURE: set[str] = {
    "Posting Date",
    "Document Number",
    "G/L Account",
    "Debit",
    "Credit",
}


class SapAdapter(BaseAdapter):
    """SAP ERP / B1 适配器。"""

    id = "sap"
    display_name = "SAP ERP / B1"
    priority = 70

    def match(self, fd: "FileDetection") -> float:
        score = 0.0
        if _FILENAME_RE.search(fd.file_name or ""):
            score += 0.5

        best_header_hit = 0
        for sheet in fd.sheets:
            headers = {
                (m.column_header or "").strip()
                for m in sheet.column_mappings
                if m.column_header
            }
            best_header_hit = max(best_header_hit, len(headers & _HEADER_SIGNATURE))

        if best_header_hit >= 2:
            score += 0.3

        return min(score, 1.0)

    def get_column_aliases(self, table_type: "TableType") -> dict[str, list[str]]:
        if table_type == "balance":
            return {
                "account_code": ["G/L Account", "Account"],
                "account_name": ["Account Description", "G/L Account Name"],
                "opening_balance": ["Opening Balance", "Carry-forward"],
                "debit_amount": ["Debit"],
                "credit_amount": ["Credit"],
                "closing_balance": ["Closing Balance", "Balance"],
            }
        if table_type == "ledger":
            return {
                "voucher_date": ["Posting Date", "Document Date"],
                "voucher_no": ["Document Number", "Doc. No."],
                "summary": ["Text", "Line Item Text"],
                "account_code": ["G/L Account"],
                "debit_amount": ["Debit"],
                "credit_amount": ["Credit"],
                "currency_code": ["Currency"],
            }
        return {}


__all__ = ["SapAdapter"]
