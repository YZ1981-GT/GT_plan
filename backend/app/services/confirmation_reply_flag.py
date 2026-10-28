"""函证汇总行「是否收到回函」三态归一（后端版，与前端 ``confirmation/replyStatus.ts`` 同一词表）。

汇总行 ``is_replied`` 有两种真实持久化形态：完整表格视图写布尔，明细面板 / Excel 导入写「是」/「否」。
原先 H0 / K0 / L0 的「从 X0-1 带入替代程序」只认 ``is_replied is False`` ⇒ 明细面板填的「否」永远带不进来
（spec attachment-confirmation-evidence-loop 需求 1.6）。未填返回 None，不当「否」用（空行不得带进替代程序）。
"""
from __future__ import annotations

from typing import Any

TRUE_TOKENS = frozenset({"是", "y", "yes", "true", "1", "√", "是的", "已回函"})
FALSE_TOKENS = frozenset({"否", "n", "no", "false", "0", "×", "x", "未回函"})


def normalize_reply_flag(value: Any) -> bool | None:
    """True = 已回函，False = 明确未回函，None = 未填 / 认不出。"""
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text in TRUE_TOKENS or text.lower() in TRUE_TOKENS:
        return True
    if text in FALSE_TOKENS or text.lower() in FALSE_TOKENS:
        return False
    return None


def is_unreplied_summary_row(row: dict) -> bool:
    """与前端 ``importFromSummary.defaultUnrepliedFilter`` 同口径：相符情况为未回函，或明确未回函且不是相符。"""
    status = row.get("match_status") or ""
    return status == "未回函" or (normalize_reply_flag(row.get("is_replied")) is False and status != "相符")
