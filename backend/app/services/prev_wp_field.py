"""``PREV('底稿','表','字段')`` 三参：上年同底稿取数（spec formula-fetch-and-wp-generation-defect-closure R2）。

不读上年底稿的单元格（底稿没有年度维度），而是与报表上期「用本年配置公式在上年数据上求值」同一思路：

1. 上年数据来源：``prior_year_context.resolve_prior_source``（同项目有上年试算表 → 同项目；否则上年项目）。
2. 字段定义：本项目该公式位 ``{底稿}|{表}|{字段}`` 的有效定义（本项目底稿公式 > 全局 > 系统预设，
   ``formula_settings.effective.effective_slots``，只认取值类公式）。没有该公式位、而字段是试算表列名（审定数 /
   期末余额 …）且该表有「未审数」公式位 ⇒ 用「未审数」的定义、把其中试算表取数的列换成该字段
   （审定表的上年审定数 = 同一组科目的上年审定数）。
3. 定义只许试算表 / 调整类取数与运算（TB / SUM_TB / TB_SUM / ADJ / ABS / ROUND / MAX / MIN / IF）：占位、序时账、
   底稿 / 附注 / 报表引用、再套 PREV 不在上年数据上重算 ⇒ 缺数并写明原因。
4. 在上年数据上用底稿求值器严格求值（``evaluate_wp_formula_expression``）：上年数据里没有该科目 = 0（合法的 0），
   其余取不到 ⇒ 缺数并写明原因。缺数一律不代入 0，由调用方报错 / 留空。

调用方：严格路径 ``formula_ref_preload.substitute_prev_aux``（底稿可编辑公式、表间审核、Tier A 预设求值）、
统一预载层 ``formula_preloader.preload``（重新预填 / 用户公式试算 → L1）。

初次预填（``prefill_workpaper_xlsx``）不写三参 PREV 的格：映射里这些格的位置是语义名（「上年审定数」等），现有定位
规则（列头含「上年」或「审定数」）在模板上落到「本期审定数」或「本期与上期审定数比较」列，写入会把上年数写进
错误的列（宁缺勿造，见 spec design §9）。
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.prior_year_context import PriorSource, resolve_prior_source

logger = logging.getLogger(__name__)

_CALL_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_QUOTED_RE = re.compile(r"'[^']*'")
#: 试算表取数调用（第二参是列名）；``TB_SUM`` 是预设的旧写法，求值前改写成底稿求值器认的 ``SUM_TB``
_TB_CALL_RE = re.compile(r"(?<![A-Za-z0-9_])(TB|SUM_TB|TB_SUM)\(\s*'([^']*)'\s*,\s*'([^']*)'\s*\)", re.IGNORECASE)
_TB_FUNCTIONS = frozenset({"TB", "SUM_TB", "TB_SUM"})
#: 允许在上年数据上重算的函数（取数只限试算表 / 调整；其余是纯运算）
ALLOWED_FUNCTIONS = _TB_FUNCTIONS | {"ADJ", "ABS", "ROUND", "MAX", "MIN", "IF"}
#: 「未审数」公式位：审定表的科目范围定义（上年审定数等试算表列由它换列得到）
UNADJUSTED_FIELD = "未审数"
#: 只有取值类公式是字段的取数定义（检查类公式只出问题清单）
_VALUE_TYPES = ("", "auto_calc")


@dataclass(frozen=True)
class PrevFieldValue:
    """``value`` 为 ``None`` 时 ``reason`` 是取不到的原因；``expression`` 是在上年数据上求值的表达式。"""

    value: Decimal | None
    reason: str = ""
    expression: str = ""


def called_functions(expression: str) -> list[str]:
    """调用的函数名（大写、去重、按出现顺序；引号内文字不算）。"""
    names: list[str] = []
    for m in _CALL_RE.finditer(_QUOTED_RE.sub("''", expression or "")):
        name = m.group(1).upper()
        if name not in names:
            names.append(name)
    return names


def _tb_call_total(expression: str) -> int:
    """试算表取数调用的个数（含重复；引号内文字不算）。"""
    return sum(1 for m in _CALL_RE.finditer(_QUOTED_RE.sub("''", expression or "")) if m.group(1).upper() in _TB_FUNCTIONS)


def _rewrite_tb_calls(expression: str, column: str | None = None) -> str:
    """试算表取数归一：``TB_SUM`` → ``SUM_TB``；给了 ``column`` 时把列换成它。"""
    def repl(m: re.Match) -> str:
        func = "TB" if m.group(1).upper() == "TB" else "SUM_TB"
        return f"{func}('{m.group(2)}','{column if column is not None else m.group(3)}')"

    return _TB_CALL_RE.sub(repl, expression)


def _value_expression(slot: Any) -> str:
    """有效公式位 → 取值表达式（去前导 ``=``）；没有 / 停用 / 检查类 ⇒ 空串。"""
    if slot is None or getattr(slot, "disabled", False):
        return ""
    definition = getattr(slot, "definition", None) or {}
    if str(definition.get("formula_type") or "").strip() not in _VALUE_TYPES:
        return ""
    return str(definition.get("expression") or "").strip().lstrip("=").strip()


def _is_tb_column(field: str) -> bool:
    from app.services.formula_engine import COLUMN_ALIASES

    return field in COLUMN_ALIASES


class PriorWpFieldResolver:
    """一次求值内复用：上年数据来源与本项目底稿公式有效定义各取一次。

    读库都在保存点里、异常转成缺数原因：调用方（严格路径 / 预载层）的事务不会因此停在中止状态。
    """

    def __init__(self, db: AsyncSession, project_id: uuid.UUID, year: int):
        self.db, self.project_id, self.year = db, project_id, year
        self._source: PriorSource | None = None
        self._slots: dict[str, Any] | None = None
        self._slots_error = ""
        self._cache: dict[tuple[str, str, str], PrevFieldValue] = {}

    async def source(self) -> PriorSource:
        if self._source is None:
            try:
                async with self.db.begin_nested():
                    self._source = await resolve_prior_source(self.db, self.project_id, self.year)
            except Exception as exc:  # noqa: BLE001 —— 记为缺数原因，不中断调用方
                logger.warning("上年数据来源查询失败 project=%s: %s", self.project_id, exc)
                self._source = PriorSource(None, self.year - 1, reason=f"上年数据来源查询失败：{exc}")
        return self._source

    async def _definitions(self) -> dict[str, Any]:
        if self._slots is None:
            from app.services.formula_settings.effective import effective_slots

            try:
                async with self.db.begin_nested():
                    self._slots = await effective_slots(self.db, "wp", self.project_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("底稿公式有效定义读取失败 project=%s: %s", self.project_id, exc)
                self._slots, self._slots_error = {}, f"底稿公式定义读取失败：{exc}"
        return self._slots

    async def definition(self, wp_code: str, sheet: str, field: str) -> tuple[str | None, str]:
        """字段的取数定义（未归一）→ ``(表达式, 原因)``；取不到时表达式为 ``None``。"""
        from app.services.formula_settings.domain_stores import wp_slot

        slots = await self._definitions()
        if self._slots_error:
            return None, self._slots_error
        own = _value_expression(slots.get(wp_slot(wp_code, sheet, field)))
        if own:
            return own, ""
        base = _value_expression(slots.get(wp_slot(wp_code, sheet, UNADJUSTED_FIELD)))
        if base and _is_tb_column(field):
            other = [f for f in called_functions(base) if f not in _TB_FUNCTIONS]
            if other:
                return None, (f"底稿 {wp_code}「{sheet}」没有「{field}」的取数定义，「{UNADJUSTED_FIELD}」的定义"
                              f"不是单纯的试算表取数（{'、'.join(other)}），无法换列取上年数")
            if _tb_call_total(base) != len(_TB_CALL_RE.findall(base)):
                # 换不到列的调用（单参 TB 等）会按原列 / 缺省列取数 ⇒ 不是所要的字段，宁缺勿造
                return None, (f"底稿 {wp_code}「{sheet}」没有「{field}」的取数定义，「{UNADJUSTED_FIELD}」的定义里有试算表取数"
                              "不是「科目, 列」写法，无法换列取上年数")
            return _rewrite_tb_calls(base, field), ""
        return None, f"底稿 {wp_code}「{sheet}」没有「{field}」的取数定义"

    async def resolve(self, wp_code: str, sheet: str, field: str) -> PrevFieldValue:
        key = (wp_code.strip(), sheet.strip(), field.strip())
        if key not in self._cache:
            self._cache[key] = await self._resolve(*key)
        return self._cache[key]

    async def _resolve(self, wp_code: str, sheet: str, field: str) -> PrevFieldValue:
        expression, reason = await self.definition(wp_code, sheet, field)
        if expression is None:
            return PrevFieldValue(None, reason)
        blocked = [f for f in called_functions(expression) if f not in ALLOWED_FUNCTIONS]
        if blocked:
            what = "是占位（需人工填写）" if blocked == ["PLACEHOLDER"] else f"用了 {'、'.join(blocked)}"
            return PrevFieldValue(None, f"「{field}」的取数定义{what}，不在上年数据上重算（只重算试算表 / 调整类取数）",
                                  expression)
        source = await self.source()
        if source.project_id is None:
            return PrevFieldValue(None, source.reason, expression)
        from app.services.wp_formula_eval_service import evaluate_wp_formula_expression

        expression = _rewrite_tb_calls(expression)
        try:
            async with self.db.begin_nested():
                value, errors = await evaluate_wp_formula_expression(
                    self.db, project_id=source.project_id, year=source.year, expression=expression)
        except Exception as exc:  # noqa: BLE001
            logger.warning("上年数据求值失败 %s: %s", expression, exc)
            return PrevFieldValue(None, f"上年数据求值失败：{exc}", expression)
        if errors:
            return PrevFieldValue(None, "上年数据求值失败：" + "；".join(errors), expression)
        return PrevFieldValue(value, "", expression)
