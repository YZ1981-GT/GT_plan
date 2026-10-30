"""ledger_dataset_merge 的公开报告类型与领域错误。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


class BaseDatasetChangedError(ValueError):
    """提交时冻结的基准版本已不再 active。"""


class MergeRowCountError(RuntimeError):
    """追加合并后的物理行数不满足守恒式。"""


class BalanceCarryConfirmationRequired(ValueError):
    """新增序时账月份但余额表沿用旧版本，尚未获得用户确认。"""


@dataclass(frozen=True)
class TableMergeReport:
    initial_file_rows: int
    kept_file_rows: int
    copied_rows: int
    expected_rows: int
    actual_rows: int
    file_months: tuple[int, ...] = ()
    base_months: tuple[int, ...] = ()
    inherited_months: tuple[int, ...] = ()
    skipped_months: tuple[int, ...] = ()
    overwritten_months: tuple[int, ...] = ()
    carried: bool = False
    undated_file_rows: int = 0
    undated_base_rows: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_file_rows": self.initial_file_rows,
            "kept_file_rows": self.kept_file_rows,
            "copied_rows": self.copied_rows,
            "expected_rows": self.expected_rows,
            "actual_rows": self.actual_rows,
            "file_months": list(self.file_months),
            "base_months": list(self.base_months),
            "inherited_months": list(self.inherited_months),
            "skipped_months": list(self.skipped_months),
            "overwritten_months": list(self.overwritten_months),
            "carried": self.carried,
            "undated_file_rows": self.undated_file_rows,
            "undated_base_rows": self.undated_base_rows,
        }


@dataclass(frozen=True)
class MergeReport:
    strategy: str
    base_dataset_id: UUID
    staged_dataset_id: UUID
    file_months: tuple[int, ...]
    inherited_months: tuple[int, ...]
    skipped_months: tuple[int, ...]
    overwritten_months: tuple[int, ...]
    tables: dict[str, TableMergeReport] = field(default_factory=dict)
    inherited_batch_id: UUID | None = None
    balance_confirmation_required: bool = False
    balance_carry_confirmed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "base_dataset_id": str(self.base_dataset_id),
            "staged_dataset_id": str(self.staged_dataset_id),
            "file_months": list(self.file_months),
            "inherited_months": list(self.inherited_months),
            "skipped_months": list(self.skipped_months),
            "overwritten_months": list(self.overwritten_months),
            "tables": {name: report.to_dict() for name, report in self.tables.items()},
            "inherited_batch_id": str(self.inherited_batch_id) if self.inherited_batch_id else None,
            "balance_confirmation_required": self.balance_confirmation_required,
            "balance_carry_confirmed": self.balance_carry_confirmed,
        }
