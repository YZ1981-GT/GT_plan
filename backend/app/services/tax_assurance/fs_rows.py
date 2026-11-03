"""单体财务报表行计算（纯函数，单测直接构造余额）：按 ``fs_enterprise_system.json`` 的行定义取数与合计。

余额口径一律「借正贷负」，键为标准科目码。科目按前缀汇总（``1231`` 含 ``1231-01``、``2211`` 含 ``221101``），
``!`` 后剔除下级。行值 = 借正贷负合计 ×（贷方表取反）×（``negate`` 取反）。
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from functools import lru_cache
from typing import Any

from app.services.tax_assurance.common import DATA_DIR

CONFIG_PATH = DATA_DIR / "fs_enterprise_system.json"
PL_CLOSE = "PL_CLOSE"
_ZERO = Decimal(0)
_SUM_RE = re.compile(r"SUM\((\d+):(\d+)\)")
_TERM_RE = re.compile(r"([+-]?)\s*(SUM\(\d+:\d+\)|\d+)")


@lru_cache(maxsize=1)
def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def statement_def(key: str) -> dict:
    for s in load_config()["statements"]:
        if s["key"] == key:
            return s
    raise KeyError(key)


def is_pl_code(code: str) -> bool:
    """损益类：标准科目表 5xxx（旧体系）/ 6xxx。"""
    return code[:1] in ("5", "6")


def _matches(code: str, prefix: str) -> bool:
    return code == prefix or (code.startswith(prefix) and len(code) > len(prefix))


def account_total(balances: dict[str, Decimal], term: str, pl_close: Decimal = _ZERO) -> Decimal:
    """一个科目项的借正贷负合计：``2211!221102`` = 2211 及下级，剔除 221102 及其下级。"""
    if term == PL_CLOSE:
        return pl_close
    prefix, *excludes = term.split("!")
    total = _ZERO
    for code, amount in balances.items():
        if _matches(code, prefix) and not any(_matches(code, ex) for ex in excludes):
            total += amount
    return total


def _formula(expr: str, values: dict[int, Decimal | None]) -> Decimal:
    total = _ZERO
    for sign, term in _TERM_RE.findall(expr.replace(" ", "")):
        m = _SUM_RE.fullmatch(term)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            v = sum((values.get(r) or _ZERO for r in range(lo, hi + 1)), _ZERO)
        else:
            v = values.get(int(term)) or _ZERO
        total += -v if sign == "-" else v
    return total


def compute_statement(
    stmt: dict,
    balances: dict[str, Decimal] | None,
    pl_close: Decimal = _ZERO,
    cf_values: dict[str, Decimal] | None = None,
    from_values: dict[str, dict[int, Decimal | None]] | None = None,
) -> dict[int, Decimal | None]:
    """一列（本期或上期）的行值。``balances`` 为 None ⇒ 取数行全空（合计仍按 0 加，便于看出缺数）。

    ``cf_values``：平台现金流量表 / 补充资料行名（已规范化）→ 金额；``from_values``：其他表已算出的行值。
    """
    out: dict[int, Decimal | None] = {}
    flip = Decimal(-1) if stmt["side"] == "credit" else Decimal(1)
    for row in stmt["rows"]:
        r = row["r"]
        if row.get("heading") or row.get("note"):
            out[r] = None
        elif "accounts" in row:
            if balances is None:
                out[r] = None
                continue
            v = sum((account_total(balances, t, pl_close) for t in row["accounts"]), _ZERO) * flip
            out[r] = -v if row.get("negate") else v
        elif "cf" in row:
            if cf_values is None:
                out[r] = None
                continue
            hits = [cf_values[n] for n in (normalize_name(x) for x in row["cf"]) if n in cf_values]
            out[r] = sum(hits, _ZERO) if hits else None
        elif "from" in row:
            key, line = row["from"].split(":")
            out[r] = (from_values or {}).get(key, {}).get(int(line))
        else:
            out[r] = None
    # 合计行按行序依次算（下方合计可引用上方合计）
    for row in stmt["rows"]:
        if "formula" in row:
            out[row["r"]] = _formula(row["formula"], out)
    return out


_NAME_STRIP_RE = re.compile(r"[\s△▲*＊]")


def normalize_name(name: Any) -> str:
    """平台报表行名 → 匹配用：去空白与 △▲* 标记、全角引号统一。"""
    return _NAME_STRIP_RE.sub("", str(name or "")).replace("“", "\"").replace("”", "\"")
