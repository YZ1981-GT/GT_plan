# -*- coding: utf-8 -*-
"""projection digest 的**值表示**口径（单一真源）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure（AC 3.6 幂等复用）

═══ 为什么单开一个模块 ═══

这条规则的关注点是「canonical 序列化时一个业务值长什么样」，与
:func:`definitions.json_safe` / :func:`definitions.canonical_json_bytes` 同层；它既不属于
「提交编排」（`content_mutation` 的职责），也不该埋在某个 payload 构造函数里 ——
埋进去的后果就是下面这个真栈缺陷：判据写在 docstring 里，实现却少了一层。

═══ 修的是什么（2026-09-22 真栈实测）═══

`materialize` 的幂等复用（AC 3.6）比的是 base content version 的 `projection_sha256`
与本次 flush 的 projection digest。真库 wp b3ab3c46 / entry xlsx/gt-d4-operating-revenue
revision 120 实测：

* 已提交 projection 与当次 flush 的 projection **899 个键逐键相等**（0 增 0 减 0 改），
  顶层键逐项相等；
* canonical 字节 121485 vs 121487，digest ``ecb4f807…`` vs ``f22f1e75…``；
* 首个差异在 ``revenue_detail_rows/GTROW-D42-0012/period_total``：
  ``"value":0``（已提交，int）vs ``"value":0.0``（当次 flush，float）。

`json_safe` 规范了 `Decimal` / `date`（正是为了「同一金额两次序列化同字节」），却让裸
`int` / `float` 原样透出。于是同一个金额零的两种 Python 表示算出两个 digest ⇒
**幂等复用永远不命中**，每次点「在线编辑」都走全量 materialize（D4 换页签实测 31.5s）。

═══ 口径 ═══

复用 :func:`merge.normalize_value`（「把值规范化成**比较键**」）这一份单源，不新造第二套：

* `amount` 等十进制族 → `Decimal`，再 ``normalize()`` 抹掉尾随零与指数表示差异
  （``0`` / ``0.0`` / ``0.00`` / ``0E-2`` 一律 ``"0"``；``1.50`` 与 ``1.5`` 同字节），
  最后由 `json_safe` 转成 ``format(v, "f")`` 字符串；
* `integer` → `int`（``0`` 与 ``0.0`` 同值）；`boolean` → `bool`；日期族 → ISO 串。

**语义一条不折叠**：`None` 仍是 JSON ``null``（「未填」与「填了零」是两种审计事实），
`MISSING` 回退原值，空串与 ``"0"`` 互不相等。

规范化失败**回退原值且不抛**：那类值本来就会被 merge 记 ``type_normalization_failure``
交人工裁决，canonicalization 不该把它升级成一次 flush 失败。
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.services.workpaper_sync.definitions import json_safe

__all__ = ["canonical_value_for_digest"]


def canonical_value_for_digest(field: Any) -> Any:
    """把一个 projection 字段的值转成 digest 用的规范表示。见模块 docstring。"""
    from app.services.workpaper_sync.merge import MISSING, normalize_value

    try:
        normalized = normalize_value(field.value, field.value_type)
    except Exception:  # noqa: BLE001 - 规范化失败不得让 flush 失败，见模块 docstring
        return json_safe(field.value)
    if normalized is MISSING:
        return json_safe(field.value)
    if isinstance(normalized, Decimal):
        if normalized == 0:
            # `Decimal('-0')` / `Decimal('0E+1')` 也要归一到同一个零。
            normalized = Decimal(0)
        else:
            normalized = normalized.normalize()
    return json_safe(normalized)
