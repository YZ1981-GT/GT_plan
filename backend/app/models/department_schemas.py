"""
部门管理相关 Schema
account-field-completion Task 1.4
"""
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
from datetime import datetime
from uuid import UUID


class DepartmentBase(BaseModel):
    """部门基础信息"""
    name: str = Field(..., description="部门名称（唯一）")
    parent_id: Optional[UUID] = Field(None, description="上级部门 ID")
    # head_id 在响应里可能为空（负责人账号被删除时 FK 置空），故基类保持可选；
    # 创建/更新请求各自覆盖为必填。
    head_id: Optional[UUID] = Field(None, description="部门负责人用户 ID（须为合伙人）")
    sort_order: Optional[int] = Field(0, description="排序顺序")
    description: Optional[str] = Field(None, description="部门描述")


class DepartmentCreate(DepartmentBase):
    """创建部门请求"""
    head_id: UUID = Field(..., description="部门负责人用户 ID（必填，须为合伙人）")


class DepartmentUpdate(BaseModel):
    """更新部门请求"""
    name: Optional[str] = Field(None, description="部门名称")
    parent_id: Optional[UUID] = Field(None, description="上级部门 ID")
    # 更新时若提供负责人，不允许置空（必填语义）。
    head_id: Optional[UUID] = Field(None, description="部门负责人用户 ID（须为合伙人）")
    sort_order: Optional[int] = Field(None, description="排序顺序")
    description: Optional[str] = Field(None, description="部门描述")


class DepartmentResponse(DepartmentBase):
    """部门响应"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    head_name: Optional[str] = Field(None, description="部门负责人姓名")
    created_at: datetime
    updated_at: Optional[datetime] = None
