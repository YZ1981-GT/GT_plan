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
    name: str = Field(..., description="部门名称")
    code: str = Field(..., description="部门编码")
    parent_id: Optional[UUID] = Field(None, description="上级部门 ID")
    sort_order: Optional[int] = Field(0, description="排序顺序")
    description: Optional[str] = Field(None, description="部门描述")


class DepartmentCreate(DepartmentBase):
    """创建部门请求"""
    pass


class DepartmentUpdate(BaseModel):
    """更新部门请求"""
    name: Optional[str] = Field(None, description="部门名称")
    code: Optional[str] = Field(None, description="部门编码")
    parent_id: Optional[UUID] = Field(None, description="上级部门 ID")
    sort_order: Optional[int] = Field(None, description="排序顺序")
    description: Optional[str] = Field(None, description="部门描述")


class DepartmentResponse(DepartmentBase):
    """部门响应"""
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

