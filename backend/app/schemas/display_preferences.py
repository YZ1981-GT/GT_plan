"""账号级显示偏好 Pydantic 线协议。

GET 返回完整归一偏好（无记录时为平台默认）。
PATCH 仅改提交字段，revision+1，返回完整归一结果。

design §2：线协议固定 snake_case，PATCH extra='forbid'。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# 共享枚举与类型
# ---------------------------------------------------------------------------

AmountUnitOverride = Literal["yuan", "qian", "wan"] | None
FontSize = Literal["xs", "sm", "md", "lg"]
Density = Literal["compact", "default", "comfortable"]
GridEditMode = Literal["excel", "click", "classic"]


# ---------------------------------------------------------------------------
# GET 响应（完整归一偏好）
# ---------------------------------------------------------------------------

class DisplayPreferencesResponse(BaseModel):
    """GET /api/users/me/display-preferences 的完整响应。"""
    amount_unit_override: AmountUnitOverride = None
    font_size: FontSize = "sm"
    show_zero: bool = False
    decimals: int = 2
    negative_red: bool = True
    highlight_threshold: float = 0.2
    density: Density = "default"
    grid_edit_mode: GridEditMode = "excel"
    fixed_columns: dict[str, Any] = Field(default_factory=dict)
    revision: int = 0
    updated_at: datetime | None = None


# ---------------------------------------------------------------------------
# PATCH 请求
# ---------------------------------------------------------------------------

# design §16 F6：显式 null 与未提交的区分
# 用 sentinel 表示"字段未出现在请求中"
_UNSET = object()


class DisplayPreferencesPatch(BaseModel):
    """PATCH /api/users/me/display-preferences 的请求体。

    extra='forbid' 拒绝额外字段。
    base_revision 必填（CAS），至少一个业务字段。
    """
    model_config = {"extra": "forbid"}

    base_revision: int = Field(..., ge=0, description="乐观锁版本号")

    # 所有业务字段可选；显式传 null 表示"跟随项目"（amount_unit_override）
    amount_unit_override: AmountUnitOverride | None = _UNSET  # type: ignore[assignment]
    font_size: FontSize | None = _UNSET  # type: ignore[assignment]
    show_zero: bool | None = _UNSET  # type: ignore[assignment]
    decimals: int | None = _UNSET  # type: ignore[assignment]
    negative_red: bool | None = _UNSET  # type: ignore[assignment]
    highlight_threshold: float | None = _UNSET  # type: ignore[assignment]
    density: Density | None = _UNSET  # type: ignore[assignment]
    grid_edit_mode: GridEditMode | None = _UNSET  # type: ignore[assignment]
    fixed_columns: dict[str, Any] | None = _UNSET  # type: ignore[assignment]

    @model_validator(mode="after")
    def _at_least_one_business_field(self) -> "DisplayPreferencesPatch":
        """至少一个除 base_revision 外的业务字段。"""
        business_fields = [
            "amount_unit_override", "font_size", "show_zero", "decimals",
            "negative_red", "highlight_threshold", "density",
            "grid_edit_mode", "fixed_columns",
        ]
        has_any = False
        for name in business_fields:
            val = getattr(self, name, _UNSET)
            if val is not _UNSET:
                has_any = True
                break
        if not has_any:
            raise ValueError("至少需要一个业务字段")
        return self

    @model_validator(mode="after")
    def _validate_ranges(self) -> "DisplayPreferencesPatch":
        """校验 decimals/threshold/fixed_columns 边界。"""
        if self.decimals is not _UNSET and self.decimals is not None:
            if not (0 <= self.decimals <= 6):
                raise ValueError("decimals 必须在 0~6 之间")

        if self.highlight_threshold is not _UNSET and self.highlight_threshold is not None:
            if not (0 <= self.highlight_threshold <= 1):
                raise ValueError("highlight_threshold 必须在 0~1 之间")

        if self.fixed_columns is not _UNSET and self.fixed_columns is not None:
            fc = self.fixed_columns
            if len(fc) > 100:
                raise ValueError("fixed_columns 最多 100 个 pageKey")
            for page_key, page_val in fc.items():
                if not (1 <= len(page_key) <= 100):
                    raise ValueError(f"pageKey 长度须在 1~100：{page_key!r}")
                if not isinstance(page_val, dict):
                    raise ValueError(f"pageKey {page_key!r} 的值必须是对象")
                columns = page_val.get("columns")
                if columns is not None:
                    if not isinstance(columns, list):
                        raise ValueError(f"pageKey {page_key!r} 的 columns 必须是数组")
                    if len(columns) > 20:
                        raise ValueError(f"pageKey {page_key!r} 最多 20 个固定列")
                    seen = set()
                    for col in columns:
                        if not isinstance(col, str) or not (1 <= len(col) <= 100):
                            raise ValueError(f"列 key 长度须在 1~100")
                        if col in seen:
                            raise ValueError(f"重复列 key：{col!r}")
                        seen.add(col)
                # 请求不得带 saved_at
                if "saved_at" in page_val:
                    raise ValueError("fixed_columns 请求不得包含 saved_at")

        return self

    def business_fields_dict(self) -> dict[str, Any]:
        """只返回显式提交的业务字段（不含 base_revision 和 _UNSET）。"""
        result = {}
        for name in [
            "amount_unit_override", "font_size", "show_zero", "decimals",
            "negative_red", "highlight_threshold", "density",
            "grid_edit_mode", "fixed_columns",
        ]:
            val = getattr(self, name, _UNSET)
            if val is not _UNSET:
                result[name] = val
        return result


# ---------------------------------------------------------------------------
# 平台默认值（作为常量导出，service/test 共用）
# ---------------------------------------------------------------------------

PLATFORM_DEFAULTS = DisplayPreferencesResponse()
