"""底稿内容语义契约 schema 定义.

定义 SheetContentType、FieldSourceContract、ProgramStatusContract 三个核心类型，
为底稿渲染、字段来源追踪和审计程序状态提供统一的语义约定。

分层说明
--------
- `sheet_type` (SheetContentType): 描述 sheet 的**业务语义角色**。
  用于导航分组、权限判定、来源面板和状态汇总。
- `componentType` (WpComponentType): 描述 sheet 的**前端渲染组件**。
  用于 htmlRendererRegistry 分发渲染。

两者正交：同一 sheet_type 可由不同 componentType 渲染（如 audit_sheet 既可
用 audit-sheet 也可用 univer-grid），反之亦然。渲染分发仍由 componentType 完成，
语义分层由 sheet_type 承接。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from backend.app.schemas.evidence_ref import EvidenceRef


# ---------------------------------------------------------------------------
# SheetContentType 枚举
# ---------------------------------------------------------------------------

class SheetContentType(str, Enum):
    """Sheet 的审计语义角色。

    每个值对应一种业务含义，与渲染组件 (componentType) 无关。
    """

    control_panel = "control_panel"
    """程序控制台、科目驾驶舱"""

    audit_sheet = "audit_sheet"
    """审定表"""

    detail_table = "detail_table"
    """明细表"""

    analysis = "analysis"
    """账龄、趋势、毛利率、集中度等分析"""

    procedure = "procedure"
    """审计程序执行表"""

    control_understanding = "control_understanding"
    """内控了解"""

    control_test = "control_test"
    """控制测试"""

    confirmation_summary = "confirmation_summary"
    """函证汇总视图"""

    disclosure = "disclosure"
    """附注披露表"""

    adjustment = "adjustment"
    """调整分录视图"""

    conclusion = "conclusion"
    """科目结论和复核"""

    legacy = "legacy"
    """历史/修订前/只读"""

    unknown = "unknown"
    """迁移期未知类型"""


# ---------------------------------------------------------------------------
# FieldSourceContract
# ---------------------------------------------------------------------------

class FieldSourceType(str, Enum):
    """字段来源类型。"""

    trial_balance = "trial_balance"
    formula = "formula"
    manual = "manual"
    linked = "linked"
    ai_generated = "ai_generated"


class StalePolicy(str, Enum):
    """字段 stale 策略，定义字段何时需要刷新。"""

    refresh_on_tb_updated = "refresh_on_tb_updated"
    refresh_on_report_regen = "refresh_on_report_regen"
    manual_refresh = "manual_refresh"
    none = "none"


class FieldSourceContract(BaseModel):
    """字段来源契约，描述单个字段的来源、权限和刷新策略。

    用于来源面板展示、stale 判断、复核追问和签发检查。
    """

    field_id: str = Field(..., description="字段唯一标识，如 d1.audit_sheet.current_unadjusted")
    label: str = Field(..., description="字段中文标签")
    source_type: FieldSourceType = Field(..., description="来源类型")
    source_ref: dict = Field(
        ...,
        description="来源引用对象，包含 module/account_code/amount_basis 等",
    )
    editable: bool = Field(default=False, description="是否允许用户编辑")
    override_allowed: bool = Field(default=False, description="是否允许人工覆盖")
    requires_confirmation: bool = Field(default=False, description="AI 生成内容是否需要人工确认")
    traceable: bool = Field(default=True, description="是否可审计追踪")
    stale_policy: StalePolicy = Field(
        default=StalePolicy.none,
        description="字段 stale 刷新策略",
    )


# ---------------------------------------------------------------------------
# ProgramStatusContract
# ---------------------------------------------------------------------------

class ProgramStatus(str, Enum):
    """审计程序执行状态。"""

    not_started = "not_started"
    in_progress = "in_progress"
    completed = "completed"
    reviewed = "reviewed"
    rejected = "rejected"


class ReviewStatus(str, Enum):
    """复核状态。"""

    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ProgramStatusContract(BaseModel):
    """审计程序状态契约，覆盖程序适用性、执行状态、证据、复核和留痕。

    持久化由项目级状态存储（account_package_program_status 表）承接，
    本契约定义序列化格式和字段约束。
    """

    project_id: UUID = Field(..., description="项目 ID")
    account_package_id: str = Field(..., description="科目工作包 ID")
    program_code: str = Field(..., description="程序编码")
    sheet_name: str = Field(..., description="关联 sheet 名称")
    applicable: bool = Field(default=True, description="程序是否适用")
    status: ProgramStatus = Field(
        default=ProgramStatus.not_started,
        description="程序执行状态",
    )
    evidence_refs: list[EvidenceRef] = Field(
        default_factory=list,
        description="附件、函证、抽样、访谈等证据引用列表",
    )
    conclusion: Optional[str] = Field(default=None, description="程序结论")
    review_status: ReviewStatus = Field(
        default=ReviewStatus.pending,
        description="复核状态",
    )
    not_applicable_reason: Optional[str] = Field(
        default=None,
        description="不适用理由（applicable=False 时必填）",
    )
    updated_by: Optional[UUID] = Field(default=None, description="最后更新人")
    updated_at: Optional[datetime] = Field(default=None, description="最后更新时间")
    reviewer: Optional[UUID] = Field(default=None, description="复核人")
    reviewed_at: Optional[datetime] = Field(default=None, description="复核时间")

    @model_validator(mode="after")
    def _check_not_applicable_reason(self) -> "ProgramStatusContract":
        """applicable=False 时 not_applicable_reason 必填。"""
        if not self.applicable:
            if not self.not_applicable_reason or not self.not_applicable_reason.strip():
                raise ValueError(
                    "not_applicable_reason is required when applicable=False"
                )
        return self
