"""Oracle EBS / Fusion GL 适配器。

见 design.md §5 / Sprint 1 Task 17。

职责：

- ``id = "oracle"`` / ``priority = 70``。
- 只定义 **关键列 + 次关键列** 的英文别名（``balance`` / ``ledger`` 两张表）；
  ``aux_balance`` / ``aux_ledger`` / ``account_chart`` 返回空 dict，走 ``GenericAdapter``
  的通用模糊匹配兜底。
- 识别特征（``match``）：
    - 文件名命中 ``Oracle|EBS|Fusion\\s*GL`` → ``+0.5``
    - 某个 sheet 的 header 与 Oracle 关键信号集
      ``{"Natural Account","Accounted Debit","Accounted Credit","Batch Name",
      "Journal Name"}`` 交集 ≥ 2 → ``+0.3``
    - 总分 ``min(score, 1.0)``

注册：由 ``adapters/__init__.py`` 统一注册，vendor 文件不得副作用注册。
"""

import re
from typing import TYPE_CHECKING

from .base import BaseAdapter

if TYPE_CHECKING:
    from ..detection_types import FileDetection, TableType


_FILENAME_RE = re.compile(r"(?i)(Oracle|EBS|Fusion\s*GL)")
_HEADER_SIGNATURE: set[str] = {
    "Natural Account",
    "Accounted Debit",
    "Accounted Credit",
    "Batch Name",
    "Journal Name",
}


class OracleAdapter(BaseAdapter):
    """Oracle EBS / Fusion GL 适配器。"""

    id = "oracle"
    display_name = "Oracle EBS / Fusion"
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
                "account_code": ["Natural Account", "Segment Value"],
                "account_name": ["Description", "Account Description"],
                "debit_amount": ["Accounted Debit", "Period Debit"],
                "credit_amount": ["Accounted Credit", "Period Credit"],
                "opening_balance": ["Beginning Balance"],
                "closing_balance": ["Ending Balance"],
            }
        if table_type == "ledger":
            return {
                "voucher_date": ["Effective Date", "Accounting Date"],
                "voucher_no": ["Journal Name", "Batch Name"],
                "summary": ["Line Description", "Description"],
                "debit_amount": ["Accounted Debit"],
                "credit_amount": ["Accounted Credit"],
                "currency_code": ["Currency"],
            }
        return {}


__all__ = ["OracleAdapter"]
