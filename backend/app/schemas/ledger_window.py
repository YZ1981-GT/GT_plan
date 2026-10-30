"""Ledger window request/response contracts.

Money is serialized as decimal strings.  Synthetic opening/month rows are
materialized by the frontend from ``summary`` and ``subtotals``; ``entries``
always contains business rows only, so ``limit`` means business rows.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LedgerWindowKind = Literal["ledger", "aux_ledger"]
AmountDirection = Literal["all", "debit", "credit"]


class LedgerWindowQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    year: int = Field(ge=2000, le=2100)
    account_code: str = Field(min_length=1, max_length=100)
    date_from: date | None = None
    date_to: date | None = None
    keyword: str | None = Field(default=None, max_length=200)
    amount_dir: AmountDirection = "all"
    aux_type: str | None = Field(default=None, max_length=100)
    aux_code: str | None = Field(default=None, max_length=200)
    cursor: str | None = Field(default=None, max_length=16384)
    limit: int = Field(default=200, ge=1, le=500)

    @field_validator("account_code", "keyword", "aux_type", "aux_code", mode="before")
    @classmethod
    def strip_text(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        stripped = value.strip()
        return stripped or None

    @model_validator(mode="after")
    def validate_range(self) -> "LedgerWindowQuery":
        if self.date_from and self.date_from.year != self.year:
            raise ValueError("开始日期必须属于查询年度")
        if self.date_to and self.date_to.year != self.year:
            raise ValueError("结束日期必须属于查询年度")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("开始日期不能晚于结束日期")
        return self


class LedgerMonthSummary(BaseModel):
    month: str | None
    label: str
    row_count: int
    debit_total: str
    credit_total: str
    closing_balance: str
    closing_balance_signed: str
    closing_direction: Literal["debit", "credit"]


class LedgerWindowSummary(BaseModel):
    total: int
    annual_opening: str
    annual_opening_signed: str
    annual_opening_direction: Literal["debit", "credit"]
    range_opening: str
    range_opening_signed: str
    range_opening_direction: Literal["debit", "credit"]
    debit_total: str
    credit_total: str
    undated_count: int = 0
    months: list[LedgerMonthSummary] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class LedgerWindowPage(BaseModel):
    limit: int
    page_index: int
    start: int
    end: int
    has_more: bool
    next_cursor: str | None = None


class LedgerWindowSubtotal(BaseModel):
    after_entry_id: str
    month: LedgerMonthSummary


class LedgerWindowResponse(BaseModel):
    kind: LedgerWindowKind
    dataset_id: str
    query_fingerprint: str
    entries: list[dict[str, Any]]
    summary: LedgerWindowSummary
    page: LedgerWindowPage
    extra_columns: list[str] = Field(default_factory=list)
    subtotals: list[LedgerWindowSubtotal] = Field(default_factory=list)
