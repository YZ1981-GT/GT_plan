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
# 🔴 经 pydantic.Field(default_factory=…) 注入同一哨兵（闭包捕获同一对象）：
#    直接赋默认值时 pydantic 生成 OpenAPI JSON Schema 会报
#    PydanticJsonSchemaWarning（object() 不可 JSON 序列化），每次启动打 9 条日志噪音。
#    default_factory 返回的仍是同一个 _UNSET，`is` 判据与校验行为完全不变
#    （2026-11-14 探针验证：警告 1→0、哨兵身份一致、传值/默认行为一致）。


def _unset() -> Any:
    return _UNSET


class DisplayPreferencesPatch(BaseModel):
    """PATCH /api/users/me/display-preferences 的请求体。

    extra='forbid' 拒绝额外字段。
    base_revision 必填（CAS），至少一个业务字段。
    strict=True：R2 的 wire 合同要求类型、范围、精度在边界拒绝——
    ``1`` 不是 bool、``"2"`` 不是 int、NaN/超过 4 位小数的阈值不允许
    经 lax 宽化悄悄通过（spec 阶段 A 合同测试逐条钉住）。
    """
    model_config = {"extra": "forbid", "strict": True}

    base_revision: int = Field(..., ge=0, description="乐观锁版本号")

    # 所有业务字段可选；显式传 null 表示"跟随项目"（amount_unit_override）
    # 默认值统一走 _unset()（见上方注释：避开 PydanticJsonSchemaWarning）
    amount_unit_override: AmountUnitOverride | None = Field(default_factory=_unset)  # type: ignore[assignment]
    font_size: FontSize | None = Field(default_factory=_unset)  # type: ignore[assignment]
    show_zero: bool | None = Field(default_factory=_unset)  # type: ignore[assignment]
    decimals: int | None = Field(default_factory=_unset)  # type: ignore[assignment]
    negative_red: bool | None = Field(default_factory=_unset)  # type: ignore[assignment]
    highlight_threshold: float | None = Field(default_factory=_unset)  # type: ignore[assignment]
    density: Density | None = Field(default_factory=_unset)  # type: ignore[assignment]
    grid_edit_mode: GridEditMode | None = Field(default_factory=_unset)  # type: ignore[assignment]
    fixed_columns: dict[str, Any] | None = Field(default_factory=_unset)  # type: ignore[assignment]

    @model_validator(mode="after")
    def _at_least_one_business_field(self) -> "DisplayPreferencesPatch":
        """至少一个除 base_revision 外的业务字段。

        strict=True 下 ``None`` 无法通过 ``Literal``/``bool`` 等强类型字段的
        校验（那正是设计想要的：不允许业务字段传 null，显式 null 只属于
        ``amount_unit_override`` 的可选语义）。因此「显式 null = 跟随项目」
        的合法输入在这里只剩 ``amount_unit_override``；其余字段传 null 会被
        strict 校验直接拒绝，无需在此重复判断。
        """
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
    def _reject_explicit_null_for_non_override_fields(self) -> "DisplayPreferencesPatch":
        """design §16 F6：仅 amount_unit_override 允许显式 null。

        strict 模式下 ``Literal`` 字段遇到 ``None`` 报的是类型错误；
        这里把 bool/数值/枚举/字典字段的 null 统一翻译成稳定业务文案，
        测试按文案断言，不依赖 pydantic 的类型错误措辞。
        """
        non_nullable = {
            "font_size": "font_size 不允许为 null",
            "show_zero": "show_zero 不允许为 null",
            "decimals": "decimals 不允许为 null",
            "negative_red": "negative_red 不允许为 null",
            "highlight_threshold": "highlight_threshold 不允许为 null",
            "density": "density 不允许为 null",
            "grid_edit_mode": "grid_edit_mode 不允许为 null",
            "fixed_columns": "fixed_columns 不允许为 null",
        }
        raw = self.model_dump(exclude_unset=True)
        for field, message in non_nullable.items():
            if field in raw and raw[field] is None:
                raise ValueError(message)
        return self

    @model_validator(mode="after")
    def _validate_ranges(self) -> "DisplayPreferencesPatch":
        """校验 decimals/threshold/fixed_columns 边界。"""
        import math

        if self.decimals is not _UNSET and self.decimals is not None:
            if not (0 <= self.decimals <= 6):
                raise ValueError("decimals 必须在 0~6 之间")

        if self.highlight_threshold is not _UNSET and self.highlight_threshold is not None:
            threshold = self.highlight_threshold
            if isinstance(threshold, float):
                if math.isnan(threshold) or math.isinf(threshold):
                    raise ValueError("highlight_threshold 必须是有限数值")
                # 线协议只承诺 4 位小数精度（前端滑块步长 0.0001）
                if round(threshold, 4) != threshold:
                    raise ValueError("highlight_threshold 最多 4 位小数")
            if not (0 <= threshold <= 1):
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
                # 请求值只认 columns 键；saved_at/其他键一律拒绝
                allowed_keys = {"columns"}
                extra_keys = set(page_val.keys()) - allowed_keys
                if extra_keys:
                    raise ValueError(
                        f"fixed_columns 请求只允许 columns 键，"
                        f"收到未知键：{sorted(extra_keys)!r}"
                    )
                if "columns" not in page_val:
                    raise ValueError(f"pageKey {page_key!r} 缺少 columns")

            # wire 边界粗筛：请求体阶段的 fixed_columns 已超 64KiB 时直接拒绝，
            # 不等 service 的规范 JSON 精确校验（那层还含 saved_at 注入后的体积）。
            import json as _json
            _canonical = _json.dumps(
                fc, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            )
            if len(_canonical.encode("utf-8")) > 64 * 1024:
                raise ValueError("fixed_columns 规范化后超过 64KiB 存储上限")

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
