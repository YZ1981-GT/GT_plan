"""附注标题本体与标题后编制提示的单一口径。

用户 2026-10-17 明确：标题**后面**的括号或中括号内容是给编制人的提示，不属于标题本体；例如
「应收账款（以下不适用的，请删除）」与「资产负债表日后利润分配情况（只写现金分配，若仅有转增，则不写）」。
标题中间的括号（「公司（企业）基本情况」）和开头序号（「（1）一年内到期的长期借款」）仍是标题。
"""
from __future__ import annotations

import re

__all__ = ["merge_title_hint_guidance", "split_title_hint"]

# 尾部一个括注；嵌套括号不猜，保留原文并由真实 Word 守卫暴露。
_TITLE_HINT_TAIL = re.compile(
    r"\s*(?:（([^（）]*)）|\(([^()]*)\)|【([^【】]*)】|\[([^\[\]]*)\])\s*$"
)


def split_title_hint(text: str | None) -> tuple[str, str | None]:
    """返回 ``(标题本体, 提示)``；连续尾部括注按原顺序以换行连接。"""
    title, hints = (text or "").strip(), []
    while (match := _TITLE_HINT_TAIL.search(title)) and match.start() > 0:
        hints.insert(0, next(part for part in match.groups() if part is not None).strip())
        title = title[: match.start()].rstrip()
    return title, "\n".join(hint for hint in hints if hint) or None


def merge_title_hint_guidance(title_hint: str | None, guidance: str | None) -> str | None:
    """把标题提示写入现有 ``guidance_text`` 展示链；不把提示混入正文或交付件标题。"""
    hint = (title_hint or "").strip()
    body = (guidance or "").strip()
    if not hint:
        return body or None
    prefix = f"标题提示：{hint}"
    if hint in body:  # 模板正文里已经逐字承载同一提示时不重复
        return body
    return f"{prefix}\n\n{body}" if body else prefix
