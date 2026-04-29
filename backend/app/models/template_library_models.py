"""模板库三层体系数据模型

三层架构：
- 第一层：事务所默认模板（firm_default）— 全所共享
- 第二层：集团定制模板（group_custom）— 按集团分组
- 第三层：项目级模板（project）— 具体项目使用

模板类型：
- report_template: 报告模板（国企版/上市版）
- workpaper_template: 底稿模板（预设/自定义）
"""

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TemplateLevel(str, enum.Enum):
    """模板层级"""
    firm_default = "firm_default"    # 事务所默认
    group_custom = "group_custom"    # 集团定制
    project = "project"              # 项目级


class TemplateType(str, enum.Enum):
    """模板类型"""
    report_soe = "report_soe"              # 报告模板-国企版
    report_listed = "report_listed"        # 报告模板-上市版
    workpaper_preset = "workpaper_preset"  # 底稿模板-预设
    workpaper_custom = "workpaper_custom"  # 底稿模板-自定义


class TemplateLibraryItem(Base):
    """模板库条目

    统一管理报告模板和底稿模板的三层体系。
    """

    __tablename__ = "template_library"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # 模板基本信息
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    template_type: Mapped[TemplateType] = mapped_column(
        sa.Enum(TemplateType, name="template_type_enum", create_type=False),
        nullable=False,
    )
    level: Mapped[TemplateLevel] = mapped_column(
        sa.Enum(TemplateLevel, name="template_level_enum", create_type=False),
        nullable=False,
    )

    # 归属
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )  # 集团定制时的集团项目ID
    group_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )  # 项目级时的项目ID

    # 来源追溯
    source_template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("template_library.id"), nullable=True
    )  # 从哪个模板派生（集团从事务所派生，项目从集团派生）
    version: Mapped[str] = mapped_column(String(20), server_default=text("'1.0'"), nullable=False)

    # 文件信息
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)  # 文件存储路径
    file_size: Mapped[int] = mapped_column(sa.BigInteger, server_default=text("0"))
    knowledge_folder_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )  # 关联知识库文件夹

    # 底稿专用字段
    wp_code: Mapped[str | None] = mapped_column(String(20), nullable=True)  # 底稿编号如E1-1
    audit_cycle: Mapped[str | None] = mapped_column(String(10), nullable=True)  # 审计循环如E/D/H
    account_codes: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # 关联科目编码

    # 报告专用字段
    report_scope: Mapped[str | None] = mapped_column(String(20), nullable=True)  # consolidated/standalone
    opinion_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # standard/qualified/...

    # 描述与标签
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # 元数据
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())
    is_deleted: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)

    __table_args__ = (
        Index("idx_template_library_type_level", "template_type", "level"),
        Index("idx_template_library_group", "group_id"),
        Index("idx_template_library_project", "project_id"),
        Index("idx_template_library_wp_code", "wp_code"),
    )


class ProjectTemplateSelection(Base):
    """项目模板选择记录

    记录项目选择了哪个模板源（事务所默认/集团定制），
    以及拉取到项目后的联动状态。
    """

    __tablename__ = "project_template_selections"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("template_library.id"), nullable=False
    )
    template_type: Mapped[TemplateType] = mapped_column(
        sa.Enum(TemplateType, name="template_type_enum", create_type=False),
        nullable=False,
    )

    # 拉取状态
    pulled_at: Mapped[datetime | None] = mapped_column(nullable=True)  # 拉取到项目的时间
    is_active: Mapped[bool] = mapped_column(server_default=text("true"), nullable=False)

    # 联动状态
    linked_trial_balance: Mapped[bool] = mapped_column(server_default=text("false"))  # 是否已与试算表联动
    linked_adjustments: Mapped[bool] = mapped_column(server_default=text("false"))  # 是否已与调整分录联动
    linked_attachments: Mapped[bool] = mapped_column(server_default=text("false"))  # 是否已与附件联动
    last_sync_at: Mapped[datetime | None] = mapped_column(nullable=True)  # 最后同步时间

    # 元数据
    selected_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_project_template_sel_project", "project_id"),
        Index("idx_project_template_sel_type", "project_id", "template_type"),
    )
