"""新中大适配器。

见 design.md §5 / Sprint 1 Task 17。

职责：

- ``id = "newgrand"`` / ``priority = 60``。
- 只定义 **关键列 + 次关键列** 的中文别名（``balance`` / ``ledger`` 两张表）；
  ``aux_balance`` / ``aux_ledger`` / ``account_chart`` 返回空 dict，走 ``GenericAdapter``
  的通用模糊匹配兜底。
- 识别特征（``match``）：
    - 文件名命中 ``新中大|Newgrand|NC\\s*A[0-9]`` → ``+0.5``
    - 某个 sheet 的 header 与新中大关键信号集
      ``{"会计科目","总账科目","摘要","借方","贷方"}`` 交集 ≥ 2 → ``+0.3``
    - 总分 ``min(score, 1.0)``

注册：由 ``adapters/__init__.py`` 统一注册，vendor 文件不得副作用注册。
"""

import re
from typing import TYPE_CHECKING

from .base import BaseAdapter

if TYPE_CHECKING:
    from ..detection_types import FileDetection, TableType


_FILENAME_RE = re.compile(r"(?i)(新中大|Newgrand|NC\s*A[0-9])")
_HEADER_SIGNATURE: set[str] = {
    "会计科目",
    "总账科目",
    "摘要",
    "借方",
    "贷方",
}


class NewgrandAdapter(BaseAdapter):
    """新中大适配器。"""

    id = "newgrand"
    display_name = "新中大"
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
                "account_code": ["会计科目", "总账科目", "科目代码"],
                "account_name": ["科目名称"],
                "opening_balance": ["期初余额"],
                "debit_amount": ["本期借方"],
                "credit_amount": ["本期贷方"],
                "closing_balance": ["期末余额"],
            }
        if table_type == "ledger":
            return {
                "voucher_date": ["凭证日期"],
                "voucher_no": ["凭证号"],
                "summary": ["摘要"],
                "account_code": ["会计科目"],
                "debit_amount": ["借方"],
                "credit_amount": ["贷方"],
            }
        return {}


__all__ = ["NewgrandAdapter"]
