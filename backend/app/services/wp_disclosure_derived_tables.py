"""底稿披露同步后的跨 owner 派生表。"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


@dataclass(frozen=True)
class _OtherPayablesConfig:
    variant: str
    section: str
    summary_table: str
    sources: tuple[tuple[str, str], ...]
    prior_label: str


_CONFIGS = (
    _OtherPayablesConfig(
        variant="listed",
        section="五、42",
        summary_table="其他应付款",
        sources=(
            ("应付利息", "应付利息"),
            ("应付股利", "应付股利"),
            ("其他应付款", "其他应付款（按款项性质列示）"),
        ),
        prior_label="上年年末余额",
    ),
    _OtherPayablesConfig(
        variant="soe",
        section="八、42",
        summary_table="其他应付款",
        sources=(
            ("应付利息", "应付利息"),
            ("应付股利", "应付股利"),
            ("其他应付款项", "按款项性质列示"),
        ),
        prior_label="期初余额",
    ),
)


def _variant(current_standard: str | None) -> str | None:
    value = str(current_standard or "").lower()
    if value.startswith("listed"):
        return "listed"
    if value.startswith("soe"):
        return "soe"
    return None
def _decimal(value: Any) -> Decimal:
    if value is None or isinstance(value, bool):
        return Decimal(0)
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)
    return result if result.is_finite() else Decimal(0)


def _json_number(value: Decimal) -> int | float:
    integral = value.to_integral_value()
    return int(integral) if value == integral else float(value)


def _norm_label(value: Any) -> str:
    return "".join(str(value or "").split())


def _table_total(rows: Any) -> tuple[Decimal, Decimal]:
    if not isinstance(rows, list):
        return Decimal(0), Decimal(0)
    total_row = next((
        row for row in rows
        if isinstance(row, Mapping)
        and (row.get("is_total") is True or _norm_label(row.get("label")) == "合计")
    ), None)
    if total_row is not None:
        return _decimal(total_row.get("end_amount")), _decimal(total_row.get("prior_amount"))
    end = Decimal(0)
    prior = Decimal(0)
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        end += _decimal(row.get("end_amount"))
        prior += _decimal(row.get("prior_amount"))
    return end, prior


def _config(current_standard: str | None, section_id: str) -> _OtherPayablesConfig | None:
    variant = _variant(current_standard)
    return next((item for item in _CONFIGS if item.variant == variant and item.section == section_id), None)
def rebuild_other_payables_summary(
    table_data: dict[str, Any],
    *,
    current_standard: str | None,
    section_id: str,
) -> set[str]:
    """从 L2/M1/K3 独占明细表确定性重建其他应付款共享主表。

    三个前端 builder 均不拥有主表整表写权。每次浅合并和 owner 内删除完成后，
    本函数读取合并后的权威明细表合计，重建三行及总计。未出现任何来源表时 no-op。
    返回本次派生的表名，调用方须把它加入公式推送格的 touched 集合。
    """
    config = _config(current_standard, section_id)
    if config is None:
        return set()
    sub = table_data.get("sub_table_data")
    if not isinstance(sub, dict):
        return set()
    if not any(source_table in sub for _label, source_table in config.sources):
        return set()

    summary: list[dict[str, Any]] = []
    total_end = Decimal(0)
    total_prior = Decimal(0)
    for label, source_table in config.sources:
        end, prior = _table_total(sub.get(source_table))
        total_end += end
        total_prior += prior
        summary.append({
            "label": label,
            "end_amount": _json_number(end),
            "prior_amount": _json_number(prior),
        })
    summary.append({
        "label": "合计",
        "end_amount": _json_number(total_end),
        "prior_amount": _json_number(total_prior),
        "is_total": True,
    })
    sub[config.summary_table] = summary

    columns = table_data.get("_sub_table_columns")
    if not isinstance(columns, dict):
        columns = {}
        table_data["_sub_table_columns"] = columns
    columns[config.summary_table] = [
        {"key": "label", "label": "项目", "is_label": True, "flat": True},
        {"key": "end_amount", "label": "期末余额", "format": "amount"},
        {"key": "prior_amount", "label": config.prior_label, "format": "amount"},
    ]
    return {config.summary_table}


__all__ = ["rebuild_other_payables_summary"]
