"""项目配置的严格线协议。

项目金额单位是正式输出和“跟随项目”屏幕显示的共同输入，因此它只接受
``yuan``、``qian``、``wan`` 三个稳定值。路由与 service 都消费本模块，避免各层
各自用字符串兜底导致协议漂移。
"""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

AmountUnit = Literal["yuan", "qian", "wan"]


class ProjectConfigResponse(BaseModel):
    """项目配置的完整读取结果。"""

    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    report_standard: str
    report_scope: str
    amount_unit: AmountUnit
    note_template_type: str
    export_preferences: dict[str, Any]


class ProjectConfigUpdate(BaseModel):
    """项目配置更新请求。

    ``amount_unit`` 在省略时不修改；显式传入 ``null`` 不属于三值合同，必须拒绝，
    不能静默退回默认元。
    """

    model_config = ConfigDict(extra="forbid")

    report_standard: str | None = Field(default=None, description="报表标准: soe/listed")
    report_scope: str | None = Field(default=None, description="报表范围: consolidated/standalone")
    consolidation_type: str | None = Field(
        default=None,
        description="已停用：合并方式由下级企业的与上级关系自动识别，传入非空值即拒绝",
    )
    amount_unit: AmountUnit | None = Field(default=None, description="项目默认金额单位")
    note_template_type: str | None = Field(default=None, description="附注模板: auto/soe/listed")
    export_preferences: dict[str, Any] | None = Field(default=None, description="导出格式偏好")

    @model_validator(mode="after")
    def reject_explicit_null_amount_unit(self) -> "ProjectConfigUpdate":
        if "amount_unit" in self.model_fields_set and self.amount_unit is None:
            raise ValueError("amount_unit 仅支持 yuan、qian、wan，不能为 null")
        return self


class ProjectConfigUpdateResponse(ProjectConfigResponse):
    """更新成功后的完整配置与本次影响摘要。"""

    message: str = "配置已更新"
    changed_fields: list[str] = Field(default_factory=list)
    stale_artifacts_marked: int = 0
