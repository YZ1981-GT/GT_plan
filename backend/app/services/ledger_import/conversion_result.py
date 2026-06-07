"""Converter 结构化输出类型定义。

`convert_balance_rows` 和 `convert_ledger_rows` 的结构化返回值，
包含标准化 rows、aux rows、warnings、sign anomalies 和统计摘要。

Requirements: 3.1, 3.2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .sign_convention_types import SignAnomaly


@dataclass
class BalanceConversionResult:
    """余额表转换结果。

    Attributes:
        rows: 主表标准化行 (tb_balance)
        aux_rows: 辅助余额标准化行 (tb_aux_balance)
        warnings: 转换过程中产生的警告列表
        sign_anomalies: 符号异常记录列表
        stats: 统计摘要 {total_rows, rows_with_direction, anomaly_count, ...}
    """

    rows: list[dict[str, Any]] = field(default_factory=list)
    aux_rows: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    sign_anomalies: list[SignAnomaly] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


@dataclass
class LedgerConversionResult:
    """序时账转换结果。

    Attributes:
        rows: 主表标准化行 (tb_ledger)
        aux_rows: 辅助明细标准化行 (tb_aux_ledger)
        aux_stats: 辅助维度统计 {"客户": 12345, "部门": 678, ...}
        warnings: 转换过程中产生的警告列表
        sign_anomalies: 符号异常记录列表
        stats: 统计摘要
    """

    rows: list[dict[str, Any]] = field(default_factory=list)
    aux_rows: list[dict[str, Any]] = field(default_factory=list)
    aux_stats: dict[str, int] = field(default_factory=dict)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    sign_anomalies: list[SignAnomaly] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "BalanceConversionResult",
    "LedgerConversionResult",
]
