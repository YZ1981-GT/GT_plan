"""浪潮 GS 适配器。

见 design.md §5 / Sprint 1 Task 17。

职责：

- ``id = "inspur"`` / ``priority = 60``。
- 只定义 **关键列 + 次关键列** 的中文别名（``balance`` / ``ledger`` 两张表）；
  ``aux_balance`` / ``aux_ledger`` / ``account_chart`` 返回空 dict，走 ``GenericAdapter``
  的通用模糊匹配兜底。
- 识别特征（``match``）：
    - 文件名命中 ``浪潮|Inspur|GS\\s*Cloud`` → ``+0.5``
    - 某个 sheet 的 header 与浪潮关键信号集
      ``{"账户代码","账户名称","期初数","本期借方","本期贷方"}`` 交集 ≥ 2 → ``+0.3``
    - 总分 ``min(score, 1.0)``

注册：由 ``adapters/__init__.py`` 统一注册，vendor 文件不得副作用注册。
"""

import re
from typing import TYPE_CHECKING

from .base import BaseAdapter

if TYPE_CHECKING:
    from ..detection_types import FileDetection, TableType


_FILENAME_RE = re.compile(r"(?i)(浪潮|Inspur|GS\s*Cloud)")
_HEADER_SIGNATURE: set[str] = {
    "账户代码",
    "账户名称",
    "期初数",
    "本期借方",
    "本期贷方",
}


class InspurAdapter(BaseAdapter):
    """浪潮 GS 适配器。"""

    id = "inspur"
    display_name = "浪潮 GS"
    priority = 60

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
                "account_code": ["账户代码", "科目代码"],
                "account_name": ["账户名称", "科目名称"],
                "opening_balance": ["期初数", "年初数"],
                "debit_amount": ["本期借方发生", "借方本期"],
                "credit_amount": ["本期贷方发生", "贷方本期"],
                "closing_balance": ["期末数"],
            }
        if table_type == "ledger":
            return {
                "voucher_date": ["凭证日期"],
                "voucher_no": ["凭证号"],
                "summary": ["摘要"],
                "account_code": ["账户代码"],
                "debit_amount": ["借方金额"],
                "credit_amount": ["贷方金额"],
            }
        return {}


__all__ = ["InspurAdapter"]
