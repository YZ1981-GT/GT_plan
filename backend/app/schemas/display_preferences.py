"""Display preferences wire protocol - strict version."""
from __future__ import annotations
import json, math
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, StrictStr, field_validator, model_validator

AmountUnitOverride = Literal["yuan", "qian", "wan"] | None
FontSize = Literal["xs", "sm", "md", "lg"]
Density = Literal["compact", "default", "comfortable"]
GridEditMode = Literal["excel", "click", "classic"]

BUSINESS_FIELD_NAMES = (
    "amount_unit_override", "font_size", "show_zero", "decimals",
    "negative_red", "highlight_threshold", "density", "grid_edit_mode", "fixed_columns",
)
_NON_NULLABLE = frozenset(BUSINESS_FIELD_NAMES) - {"amount_unit_override"}
_MAX_FC_PAGES = 100
_MAX_FC_COLS = 20
_MAX_FC_BYTES = 64 * 1024
_SA_PLACEHOLDER = "9999-12-31T23:59:59.999999+00:00"

class FixedColumnsPatchEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    columns: list[StrictStr]
    @field_validator("columns")
    @classmethod
    def _v(cls, v):
        if len(v) > _MAX_FC_COLS:
            raise ValueError("\u6bcf\u4e2a pageKey \u6700\u591a 20 \u4e2a\u56fa\u5b9a\u5217")
        if any(not 1 <= len(c) <= 100 for c in v):
            raise ValueError("\u5217 key \u957f\u5ea6\u987b\u5728 1~100")
        if len(set(v)) != len(v):
            raise ValueError("\u56fa\u5b9a\u5217\u4e0d\u80fd\u91cd\u590d")
        return v

class FixedColumnsResponseEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    columns: list[StrictStr]
    saved_at: datetime

class DisplayPreferencesResponse(BaseModel):
    amount_unit_override: AmountUnitOverride = None
    font_size: FontSize = "sm"
    show_zero: bool = False
    decimals: int = 2
    negative_red: bool = True
    highlight_threshold: float = 0.2
    density: Density = "default"
    grid_edit_mode: GridEditMode = "excel"
    fixed_columns: dict[StrictStr, FixedColumnsResponseEntry] = Field(default_factory=dict)
    revision: int = 0
    updated_at: datetime | None = None

def fixed_columns_storage_size(fc):
    s = {}
    for pk, item in fc.items():
        raw = item.model_dump(mode="json") if isinstance(item, BaseModel) else dict(item)
        s[pk] = {"columns": list(raw["columns"]), "saved_at": raw.get("saved_at", _SA_PLACEHOLDER)}
    return len(json.dumps(s, ensure_ascii=False, sort_keys=True, separators=(",",":")).encode("utf-8"))

def assert_fixed_columns_storage_size(fc):
    if fixed_columns_storage_size(fc) > _MAX_FC_BYTES:
        raise ValueError("fixed_columns \u89c4\u8303 JSON \u4e0d\u5f97\u8d85\u8fc7 64KiB")

class DisplayPreferencesPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    base_revision: StrictInt = Field(..., ge=0)
    amount_unit_override: AmountUnitOverride = None
    font_size: FontSize | None = None
    show_zero: StrictBool | None = None
    decimals: StrictInt | None = Field(default=None, ge=0, le=6)
    negative_red: StrictBool | None = None
    highlight_threshold: float | None = Field(default=None, ge=0, le=1)
    density: Density | None = None
    grid_edit_mode: GridEditMode | None = None
    fixed_columns: dict[StrictStr, FixedColumnsPatchEntry] | None = None

    @field_validator("highlight_threshold", mode="before")
    @classmethod
    def _ht(cls, v):
        if v is None: return None
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError("highlight_threshold \u5fc5\u987b\u662f JSON \u6570\u5b57")
        n = float(v)
        if not math.isfinite(n):
            raise ValueError("highlight_threshold \u5fc5\u987b\u662f\u6709\u9650\u6570\u5b57")
        try:
            d = Decimal(str(v))
        except (InvalidOperation, ValueError) as e:
            raise ValueError("invalid") from e
        if d.as_tuple().exponent < -4:
            raise ValueError("highlight_threshold \u6700\u591a\u4fdd\u7559 4 \u4f4d\u5c0f\u6570")
        return n

    @model_validator(mode="after")
    def _shape(self):
        submitted = self.model_fields_set
        biz = submitted & set(BUSINESS_FIELD_NAMES)
        if not biz:
            raise ValueError("\u81f3\u5c11\u9700\u8981\u4e00\u4e2a\u4e1a\u52a1\u5b57\u6bb5")
        for name in _NON_NULLABLE:
            if name in submitted and getattr(self, name) is None:
                raise ValueError(f"{name} \u4e0d\u5141\u8bb8\u4e3a null")
        if "fixed_columns" in submitted:
            fc = self.fixed_columns
            if fc is None:
                raise ValueError("fixed_columns \u4e0d\u5141\u8bb8\u4e3a null")
            if len(fc) > _MAX_FC_PAGES:
                raise ValueError("fixed_columns \u6700\u591a 100 \u4e2a pageKey")
            if any(not 1 <= len(pk) <= 100 for pk in fc):
                raise ValueError("pageKey \u957f\u5ea6\u987b\u5728 1~100")
            assert_fixed_columns_storage_size(fc)
        return self

    def business_fields_dict(self):
        v = self.model_dump(exclude_unset=True)
        v.pop("base_revision", None)
        return v

PLATFORM_DEFAULTS = DisplayPreferencesResponse()
