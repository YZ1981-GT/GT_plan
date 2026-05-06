"""QC 规则定义 ORM 模型

Refinement Round 3 — 需求 1：QC 规则定义表与管理。

支持 expression_type:
- 'python': dotted path 加载 Rule 类（沙箱 timeout=10s）
- 'jsonpath': 校验 parsed_data（jsonpath-ng）
- 'sql' / 'regex': 枚举预留，本轮不实现执行器（NotImplementedError）
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin


class QcRuleDefinition(Base, SoftDeleteMixin, TimestampMixin):
    """QC 规则定义

    每条规则对应一个可执行的质控检查逻辑。
    expression_type 决定执行器分派方式：
    - python: expression 为 dotted module path（如 app.services.qc_engine.ConclusionNotEmptyRule）
    - jsonpath: expression 为 JSONPath 表达式（如 $.parsed_data.conclusion）
    - sql / regex: 预留，执行时抛 NotImplementedError

    Refinement Round 3 — 需求 1, 10。
    """

    __tablename__ = "qc_rule_definitions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rule_code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False
    )  # e.g. 'QC-01', 'QC-CUSTOM-001'
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'blocking' | 'warning' | 'info'
    scope: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # 'workpaper' | 'project' | 'consolidation' | 'audit_log'
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    standard_ref: Mapped[list | None] = mapped_column(
        JSONB, nullable=True
    )  # [{code: '1301', section: '6.2', name: '审计工作底稿'}]
    expression_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # 'python' | 'jsonpath' | 'sql' | 'regex'
    expression: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # python: dotted path / jsonpath: $.parsed_data.xxx
    parameters_schema: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # JSON Schema for rule params
    enabled: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=text("true"), nullable=False
    )
    version: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("1"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )

    __table_args__ = (
        Index("idx_qc_rule_definitions_rule_code", "rule_code", unique=True),
        Index("idx_qc_rule_definitions_scope", "scope"),
        Index("idx_qc_rule_definitions_enabled", "enabled"),
        Index(
            "idx_qc_rule_definitions_active",
            "scope",
            "enabled",
            postgresql_where=text("is_deleted = false AND enabled = true"),
        ),
    )
