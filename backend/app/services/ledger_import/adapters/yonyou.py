"""用友 U8/NC/T+ 适配器。

见 design.md §5.2 / Sprint 1 Task 15。

职责：

- ``id = "yonyou"`` / ``priority = 80``。
- 只定义 **关键列 + 次关键列** 的中文别名（``balance`` / ``ledger`` 两张表）；
  ``aux_balance`` / ``aux_ledger`` / ``account_chart`` 返回空 dict，完全交由
  ``GenericAdapter`` 的通用模糊匹配兜底。
- 识别特征（``match``）：
    - 文件名命中 ``用友|UFIDA|U8|NC\\d|T\\+`` → ``+0.5``
    - 某个 sheet 的 header 与用友关键信号集 ``{"年初余额","本期借方","本期贷方",
      "期末余额","制单人"}`` 交集 ≥ 2 → ``+0.3``
    - 总分 ``min(score, 1.0)``

注册：由 ``adapters/__init__.py`` 在模块加载时统一注册到 ``registry`` 单例，
vendor 文件 **不得** 副作用式 ``registry.register(...)``。
"""

import re
from typing import TYPE_CHECKING

from .base import BaseAdapter

if TYPE_CHECKING:
    from ..detection_types import FileDetection, TableType


_FILENAME_RE = re.compile(r"(?i)(用友|UFIDA|U8|NC\d|T\+)")
_HEADER_SIGNATURE: set[str] = {
    "年初余额",
    "本期借方",
    "本期贷方",
    "期末余额",
    "制单人",
}


class YonyouAdapter(BaseAdapter):
    """用友 U8/NC/T+ 适配器。"""

    id = "yonyou"
    display_name = "用友 U8/NC/T+"
    priority = 80

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
                "account_code": ["科目编码", "科目代码"],
                "account_name": ["科目名称", "科目全名"],
                "opening_balance": ["年初余额", "期初余额"],
                "opening_debit": ["年初借方", "期初借方"],
                "opening_credit": ["年初贷方", "期初贷方"],
                "debit_amount": ["借方本期", "本期借方", "本期借方发生额"],
                "credit_amount": ["贷方本期", "本期贷方", "本期贷方发生额"],
                "closing_balance": ["期末余额"],
                "closing_debit": ["期末借方"],
                "closing_credit": ["期末贷方"],
                "level": ["级次"],
                "currency_code": ["币种", "币别"],
            }
        if table_type == "ledger":
            return {
                "voucher_date": ["日期", "凭证日期", "制单日期"],
                "voucher_no": ["凭证号", "凭证字号"],
                "voucher_type": ["凭证类型", "字"],
                "summary": ["摘要"],
                "account_code": ["科目编码", "科目"],
                "account_name": ["科目名称"],
                "debit_amount": ["借方金额", "借方"],
                "credit_amount": ["贷方金额", "贷方"],
                "preparer": ["制单人", "制单"],
                "currency_code": ["币种"],
            }
        # aux_balance / aux_ledger / account_chart / unknown: 走通用模糊匹配
        return {}


__all__ = ["YonyouAdapter"]
