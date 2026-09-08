"""``render-config`` 线上响应契约。

模型只约束 wire 外壳；``schema``、``html_data``、``guidance`` 等业务载荷继续保持
开放对象。路由使用 ``response_model_exclude_unset=True``，从而保留普通分支显式
``null``，同时不向 redirect 分支注入并不存在的默认字段。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _StrictWireModel(BaseModel):
    """禁止在响应外壳中静默丢弃生产字段。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class CrossRefItem(_StrictWireModel):
    wp_code: str
    cell: str | None


class SheetRenderConfig(_StrictWireModel):
    sheet_name: str
    sheet_code: str | None = None
    sheet_code_reason: str | None = None
    whole_workbook: bool = False
    componentType: str
    schema_: dict[str, Any] | None = Field(
        alias="schema",
        serialization_alias="schema",
    )
    html_data: dict[str, Any] | None
    cross_refs: list[CrossRefItem]
    sheet_type: str | None = None
    field_sources: dict[str, Any] | None = None


class RenderPermissions(_StrictWireModel):
    edit: bool


class RenderDecisionWire(_StrictWireModel):
    """Task 6-8 将接入的 reserved 裁决追踪结构。"""

    sheet_key: str
    chosen_component_type: str
    candidate_sources: list[str]
    winning_source: str
    override_hit: bool
    redirect_applied: bool
    fallback_reason: str | None = None


class RenderConfigResponse(_StrictWireModel):
    """普通、redirect 与 word-template 分支的统一 wire 外壳。"""

    wp_id: str
    wp_code: str
    project_id: str
    scope: str
    is_real_workpaper: bool
    template_version: str | None
    sheets: list[SheetRenderConfig]

    # 普通渲染分支；redirect 分支不设置这些字段。
    audit_year: int | None = None
    applicable_standards: list[str] = Field(default_factory=list)
    fill_results: dict[str, Any] = Field(default_factory=dict)
    guidance: dict[str, Any] | None = None

    # redirect 分支。
    redirect: bool = False
    delegated_module: str | None = None
    target_path: str | None = None

    # word-template 分支。
    sign_status: str | None = None
    permissions: RenderPermissions | None = None

    # reserved：render planner 七阶段拆分后由 finalize 阶段下发。
    decision_trace: list[RenderDecisionWire] = Field(default_factory=list)
