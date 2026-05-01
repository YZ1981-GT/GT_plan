"""共享配置模板模型

支持5类配置的三层共享：
- system: 事务所默认（全局只读）
- group: 集团级自定义（集团项目下所有子企业可引用）
- personal: 个人自定义（该用户参与的所有项目可引用）

配置类型：
- report_mapping: 国企/上市转换规则
- account_mapping: 科目→报表行次映射
- formula_config: 公式审核配置
- report_template: 报告模板
- workpaper_template: 底稿模板
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, ForeignKey, Integer,
    String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin, SoftDeleteMixin

import enum


class ConfigType(str, enum.Enum):
    report_mapping = "report_mapping"
    account_mapping = "account_mapping"
    formula_config = "formula_config"
    report_template = "report_template"
    workpaper_template = "workpaper_template"


class OwnerType(str, enum.Enum):
    system = "system"       # 事务所默认
    group = "group"         # 集团级
    personal = "personal"   # 个人级


class SharedConfigTemplate(Base, TimestampMixin, SoftDeleteMixin):
    """共享配置模板"""
    __tablename__ = "shared_config_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False, comment="模板名称")
    description = Column(Text, comment="模板说明")
    config_type = Column(String(50), nullable=False, index=True, comment="配置类型")
    owner_type = Column(String(20), nullable=False, index=True, comment="所有者类型: system/group/personal")

    # 所有者信息
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, comment="个人模板的所有者")
    owner_project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True, comment="集团模板的所属项目")
    owner_project_name = Column(String(200), comment="集团/项目名称（冗余，方便展示）")

    # 配置数据
    config_data = Column(JSONB, nullable=False, default=dict, comment="配置数据JSON")
    config_version = Column(Integer, default=1, comment="版本号")
    applicable_standard = Column(String(50), comment="适用标准: soe/listed/both")

    # 权限控制
    is_public = Column(Boolean, default=False, comment="是否公开（所有人可见）")
    allowed_project_ids = Column(JSONB, default=list, comment="允许引用的项目ID列表（空=不限制）")

    # 引用统计
    reference_count = Column(Integer, default=0, comment="被引用次数")
    last_referenced_at = Column(DateTime, comment="最后被引用时间")

    __table_args__ = (
        UniqueConstraint("config_type", "owner_type", "owner_user_id", "owner_project_id", "name",
                         name="uq_shared_config_template"),
    )


class ConfigReference(Base, TimestampMixin):
    """配置引用记录——记录哪个项目引用了哪个模板"""
    __tablename__ = "config_references"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False, index=True)
    template_id = Column(UUID(as_uuid=True), ForeignKey("shared_config_templates.id"), nullable=False)
    config_type = Column(String(50), nullable=False, comment="配置类型")
    applied_at = Column(DateTime, default=datetime.utcnow, comment="引用时间")
    applied_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), comment="操作人")
    is_customized = Column(Boolean, default=False, comment="引用后是否做了本地修改")
