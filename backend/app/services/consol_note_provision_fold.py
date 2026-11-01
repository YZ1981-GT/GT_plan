"""单体「小计 / 减：坏账准备 / 合计」→ 合并「合计」行的账面余额与坏账准备列（spec note-table-structure-formula-pull-closure R6.6）。

国企单体账龄表只有一组金额列（期末数 / 期初数）：坏账准备写成表尾「减：坏账准备」一行，「合计」是账面价值。国企合并
账龄表把坏账准备做成列（期末数·账面余额 / 期末数·坏账准备 …），没有「小计」「减：坏账准备」两行。原先这两行在明细映射里
永远对不上（每家企业都要人工处理），合并表的坏账准备列整列为空。

折法（只在合并模板没有「减：…准备」这一行、且坏账准备列没对上来源列时）：
- 「合计」行的坏账准备列 = 「减：…准备」行同期间账面余额列的数；
- 合并模板也没有「小计」行 ⇒ 「合计」行的账面余额列 = 「小计」行的数（账面余额合计，不是账面价值）；
- 去掉这两行。apply 按本表重算合计：账面余额列按各账龄档相加；坏账准备列各档都空 ⇒ 取来源合计
  （``consol_note_table_totals.build_note_rows``）。
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from app.services.note_table_header_library import ColumnKey, norm

__all__ = ["fold_provision_rows", "provision_pairs"]

_MINUS_RE = re.compile(r"减[:：](?:坏账|减值|信用减值|.{0,10}跌价)准备")
_PROVISION_WORDS = ("坏账准备", "减值准备", "跌价准备")
#: 账面余额列：计量写了「账面余额」，或只写了期间（单体「期末数」）
_GROSS_MEASURES = frozenset({(), ("账面余额",)})


def _key(label: Any) -> str:
    return norm(label).rstrip(":")


def provision_pairs(target_keys: Sequence[ColumnKey], matched: Sequence[int]) -> list[tuple[int, int]]:
    """没对上来源列的准备列 → 同期间、对上了的账面余额列：``[(准备列, 余额列)]``（合并模板列号，第 0 列是行名）。"""
    done = set(matched)
    pairs: list[tuple[int, int]] = []
    for k in target_keys[1:]:
        if k.kind != "amount" or k.index in done or not any(w in "".join(k.measure) for w in _PROVISION_WORDS):
            continue
        gross = [g.index for g in target_keys[1:] if g.kind == "amount" and g.index in done
                 and g.period == k.period and tuple(g.measure) in _GROSS_MEASURES]
        if len(gross) == 1:
            pairs.append((k.index, gross[0]))
    return pairs


def fold_provision_rows(
    rows: list[dict[str, Any]], target_keys: Sequence[ColumnKey], matched: Sequence[int], template_labels: Sequence[Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """来源行（``values[k]`` 对合并模板第 ``k+1`` 列）按上面的折法改写 → (新来源行, 折掉的行名)；不适用时原样返回。"""
    pairs = provision_pairs(target_keys, matched)
    if not pairs:
        return rows, []
    template = {_key(label) for label in template_labels}
    minus = [i for i, r in enumerate(rows) if r.get("row_type") == "data" and _MINUS_RE.fullmatch(_key(r.get("label")))]
    if len(minus) != 1 or _key(rows[minus[0]].get("label")) in template:
        return rows, []
    m = minus[0]
    total = next((i for i in range(m + 1, len(rows)) if rows[i].get("row_type") == "total"), None)
    if total is None:
        return rows, []
    sub = m - 1 if m and rows[m - 1].get("row_type") == "subtotal" and _key(rows[m - 1].get("label")) not in template \
        else None
    values = list(rows[total].get("values") or [])
    for prov, gross in pairs:
        if 0 < prov <= len(values) and 0 < gross <= len(values):
            values[prov - 1] = rows[m]["values"][gross - 1]
            if sub is not None:
                values[gross - 1] = rows[sub]["values"][gross - 1]
    drop = {m} if sub is None else {m, sub}
    out = [{**r, "values": values} if i == total else r for i, r in enumerate(rows) if i not in drop]
    return out, [str(rows[i].get("label") or "") for i in sorted(drop)]
