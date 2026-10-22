"""PREV / AUX 引用按值代入（spec formula-governance-coverage-closure R7a）。

表间审核与报表「审核」里配置的公式要**严格取数**：取不到数就写明原因并判不通过，不能代入 0 后接着比较
（另一侧恰好是 0 时，「取不到」会被当成「相等、通过」）。``report_engine.evaluate_formula_result`` 对 PREV / AUX
只会置 0（报表生成路径的既有行为），所以严格路径在求值前先用本模块把 PREV / AUX 换成真实数值，缺数即记原因。

口径：

* ``PREV('科目','列')`` / ``PREV(TB('科目','列'))``：上年（年度 − 1）试算表，科目按前缀聚合（与 TB 同口径）。
  上年试算表整体没有数据 ⇒ 缺数；有数据但没有该科目 ⇒ 0（科目上年不存在，是合法的 0）。
* ``AUX('科目','辅助类型','辅助项','列')``：辅助核算余额表的当前数据集（``get_active_filter``），科目按前缀，
  辅助项按名称或编码匹配。该科目本年没有辅助核算余额、或找不到这个辅助项 ⇒ 缺数。
* ``AUX('科目','辅助类型','列')``：该辅助类型全部辅助项的合计；没有该类型的余额 ⇒ 缺数。
* 列名不认识、写法识别不了（例如少参数）⇒ 缺数 —— 不让它落进求值器被静默求 0。

``strict=False`` 时缺数代入 0（供报表生成路径日后改调本模块时保持其置 0 行为）。
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

_Q = r"\s*'([^']*)'\s*"
#: 前面不能紧挨标识符字符：``TB_AUX(…)`` 里的 ``AUX(`` 不是 AUX 引用
_START = r"(?<![A-Za-z0-9_])"
PREV_TB_RE = re.compile(_START + r"PREV\(\s*TB\(" + _Q + "," + _Q + r"\)\s*\)")
PREV_RE = re.compile(_START + r"PREV\(" + _Q + "," + _Q + r"(?:," + _Q + r")?\)")
AUX4_RE = re.compile(_START + r"AUX\(" + _Q + "," + _Q + "," + _Q + "," + _Q + r"\)")
AUX3_RE = re.compile(_START + r"AUX\(" + _Q + "," + _Q + "," + _Q + r"\)")
_LEFTOVER_RE = re.compile(_START + r"(PREV|AUX)\s*\(")

#: 辅助核算余额表的列（中文列名 → ORM 字段）
AUX_COLUMNS = {
    "期末余额": "closing_balance", "期初余额": "opening_balance", "年初余额": "opening_balance",
    "借方发生额": "debit_amount", "本期借方": "debit_amount", "本期借方发生额": "debit_amount",
    "贷方发生额": "credit_amount", "本期贷方": "credit_amount", "本期贷方发生额": "credit_amount",
}


def has_prev_or_aux(expression: str) -> bool:
    return bool(_LEFTOVER_RE.search(expression or ""))


@dataclass
class Substitution:
    """代入结果：``expression`` 里的 PREV / AUX 已换成数值；``missing`` 是取不到数的原因（严格时非空即不可求值）。"""

    expression: str
    missing: list[str] = field(default_factory=list)


def _literal(value: Decimal) -> str:
    return f"({value})"


async def _prior_tb(db: AsyncSession, project_id: uuid.UUID, year: int, codes: set[str]) -> dict[str, dict] | None:
    """上年试算表按前缀聚合；上年没有任何行 ⇒ ``None``（与「有数据但无该科目」区分）。"""
    from app.models.audit_platform_models import TrialBalance
    from app.services.formula_preloader import _load_tb

    exists = (await db.execute(sa.select(sa.func.count()).select_from(TrialBalance).where(
        TrialBalance.project_id == project_id, TrialBalance.year == year,
        TrialBalance.is_deleted == sa.false()))).scalar_one()
    if not exists:
        return None
    return await _load_tb(db, project_id, year, codes)


async def _aux_rows(db: AsyncSession, project_id: uuid.UUID, year: int, account: str) -> list[Any]:
    from app.models.audit_platform_models import TbAuxBalance
    from app.services.dataset_query import get_active_filter

    active = await get_active_filter(db, TbAuxBalance.__table__, project_id, year, strict=True)
    return list((await db.execute(sa.select(
        TbAuxBalance.aux_type, TbAuxBalance.aux_code, TbAuxBalance.aux_name,
        TbAuxBalance.closing_balance, TbAuxBalance.opening_balance,
        TbAuxBalance.debit_amount, TbAuxBalance.credit_amount,
    ).where(active, TbAuxBalance.account_code.like(f"{account}%")))).all())


def _sum(rows: list[Any], column: str) -> Decimal:
    return sum((Decimal(str(getattr(r, column) or 0)) for r in rows), Decimal("0"))


async def substitute_prev_aux(expression: str, *, db: AsyncSession, project_id: uuid.UUID, year: int,
                              strict: bool = True) -> Substitution:
    """把 ``expression`` 里的 PREV / AUX 换成数值。读库包在保存点里：失败不会让调用方的事务停在中止状态。"""
    from app.services.formula_engine import COLUMN_ALIASES

    text = expression or ""
    if not has_prev_or_aux(text):
        return Substitution(text)
    out = Substitution(text)

    def put(token: str, value: Decimal | None, reason: str = "") -> None:
        if value is None:
            out.missing.append(f"{token}：{reason}")
            value = Decimal("0")
        out.expression = out.expression.replace(token, _literal(value), 1)

    async with db.begin_nested():
        prev_hits = [(m.group(0), m.group(1), m.group(2)) for m in (*PREV_TB_RE.finditer(text), *PREV_RE.finditer(text))]
        if prev_hits:
            prior = await _prior_tb(db, project_id, year - 1, {code for _, code, _ in prev_hits})
            for token, code, column in prev_hits:
                std = COLUMN_ALIASES.get(column.strip())
                if std is None:
                    put(token, None, f"列名「{column}」无法识别")
                elif prior is None:
                    put(token, None, f"上年（{year - 1}）试算表无数据")
                else:
                    put(token, Decimal(str((prior.get(code) or {}).get(std, Decimal("0")))))

        aux_cache: dict[str, list[Any]] = {}
        for regex, has_item in ((AUX4_RE, True), (AUX3_RE, False)):
            for m in regex.finditer(text):
                token = m.group(0)
                account, aux_type = m.group(1), m.group(2)
                item, column = (m.group(3), m.group(4)) if has_item else ("", m.group(3))
                attr = AUX_COLUMNS.get(column.strip())
                if attr is None:
                    put(token, None, f"列名「{column}」无法识别")
                    continue
                if account not in aux_cache:
                    aux_cache[account] = await _aux_rows(db, project_id, year, account)
                rows = aux_cache[account]
                if not rows:
                    put(token, None, f"科目 {account} 本年无辅助核算余额")
                    continue
                typed = [r for r in rows if (r.aux_type or "") == aux_type]
                hit = [r for r in typed if item in ((r.aux_name or ""), (r.aux_code or ""))] if has_item else typed
                if not hit:
                    what = f"「{aux_type}」辅助项「{item}」" if has_item else f"「{aux_type}」辅助核算余额"
                    put(token, None, f"科目 {account} 没有{what}")
                    continue
                put(token, _sum(hit, attr))

    for m in _LEFTOVER_RE.finditer(out.expression):
        out.missing.append(f"{m.group(1)} 写法无法识别（PREV 需「科目, 列」，AUX 需「科目, 辅助类型[, 辅助项], 列」）")
        break
    if not strict:
        out.missing = []
    return out
