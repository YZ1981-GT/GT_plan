"""凭证日期解析 —— `ledger_penetration` / 挂凭链路的伴生模块（V166）。

为什么单独成文件而不是留在 `ledger_penetration.py` 里：该 router 是历史大文件
（1634 行，远超 800 行门禁），本次 V166 改动让它逼近 pre-commit 的「膨胀 >5%」
阈值。按门禁提示的优先顺序「拆分文件或抽伴生模块（优先），确有必要再更新
whitelist 基线」，把这段与 HTTP 无关的纯函数抽出来 —— 它零依赖、可独立测试，
放在 router 里本就不是它的位置。
"""

from __future__ import annotations

from datetime import date


def parse_iso_date(raw: str | None) -> date | None:
    """把 ``YYYY-MM-DD``（或带时间后缀的 ISO 串）解析成 ``date``。

    🔴 解析失败一律返回 None 而不抛异常：voucher_date 是**消歧增强**，
    格式不对时退化为「不按日期区分」，不应让挂凭整体失败。
    但返回 None 会使去重退化到 (project, year, no, NULL, wp)，
    因此前端有责任传规范格式（已在 LedgerPenetration.vue 侧做正则校验）。
    """
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except (ValueError, TypeError):
        return None
