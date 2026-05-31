"""底稿定位坐标契约 LocateTarget（wp-locate-foundation Spec Task 1.1, 1.2）

统一所有 trace service 输出的定位目标格式：
- LocateTarget dataclass：内部传递用
- LocateTargetSchema：Pydantic BaseModel，API 序列化用
- trace_item_to_locate_target：TraceItem → LocateTarget 转换函数

Requirements: 1.1, 1.2
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.services.wp_trace_service import TraceItem

# 有效的 component_type 值
VALID_COMPONENT_TYPES = (
    "a-program-console",
    "b-index",
    "c-note-table",
    "d-form-table",
    "d-form-paragraph",
    "d-form-qa",
    "d-form-confirmation",
    "d-form-review",
    "e-control-test",
    "h-static-doc",
    "univer",
)

ComponentType = Literal[
    "a-program-console",
    "b-index",
    "c-note-table",
    "d-form-table",
    "d-form-paragraph",
    "d-form-qa",
    "d-form-confirmation",
    "d-form-review",
    "e-control-test",
    "h-static-doc",
    "univer",
]


@dataclass
class LocateTarget:
    """底稿定位坐标（内部数据结构）

    所有 trace service 输出统一为此格式：
    - wp_trace_service.TraceItem → LocateTarget
    - report_trace_service → LocateTarget 列表
    """

    wp_code: str
    wp_id: str | None = None
    sheet_name: str | None = None
    cell_ref: str | None = None  # "A1" / "B3:D5" 范围
    component_type: str | None = None  # HTML componentType 或 "univer"
    value: str | None = None  # 目标值（辅助定位）
    label: str | None = None  # 人类可读标签


class LocateTargetSchema(BaseModel):
    """底稿定位坐标 Pydantic Schema（API 序列化）"""

    wp_code: str = Field(..., description="底稿编码，如 D2-1")
    wp_id: str | None = Field(default=None, description="底稿 UUID")
    sheet_name: str | None = Field(default=None, description="目标 sheet 名称")
    cell_ref: str | None = Field(
        default=None, description="单元格引用，如 A1 或 B3:D5"
    )
    component_type: ComponentType | None = Field(
        default=None, description="HTML componentType 或 univer"
    )
    value: str | None = Field(default=None, description="目标值（辅助定位）")
    label: str | None = Field(default=None, description="人类可读标签")

    @classmethod
    def from_dataclass(cls, target: LocateTarget) -> LocateTargetSchema:
        """从 LocateTarget dataclass 转换为 Pydantic schema"""
        return cls(
            wp_code=target.wp_code,
            wp_id=target.wp_id,
            sheet_name=target.sheet_name,
            cell_ref=target.cell_ref,
            component_type=target.component_type,  # type: ignore[arg-type]
            value=target.value,
            label=target.label,
        )


# ─── TraceItem → LocateTarget 转换（Task 1.2）───────────────────────────────


def trace_item_to_locate_target(item: TraceItem) -> LocateTarget:
    """将 wp_trace_service.TraceItem 映射为统一 LocateTarget 坐标。

    映射规则：
    - wp_code → wp_code（直接映射）
    - sheet → sheet_name（字段重命名）
    - cell → cell_ref（字段重命名）
    - value → value（转为 str，None 保持 None）
    - label → label（直接映射）
    - wp_id → None（TraceItem 不携带 wp_id，需调用方补充）
    - component_type → None（需由 wp_classification_service 解析，前端按需查询）

    Requirements: 1.2
    """
    return LocateTarget(
        wp_code=item.wp_code,
        wp_id=None,
        sheet_name=item.sheet,
        cell_ref=item.cell,
        component_type=None,
        value=str(item.value) if item.value is not None else None,
        label=item.label,
    )
