"""QC 规则定义 ORM 模型

Refinement Round 6 — 需求 4：QC 规则定义表与管理。

支持 expression_type:
- 'python': dotted path 加载 Rule 类
- 'jsonpath': 校验 parsed_data（jsonpath-ng）
- 'sql' / 'regex': 枚举预留，本轮不实现执行器（NotImplementedError）
"""

import uuid

import sqlalchemy as sa
from sqlalchemy import Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class QcRuleDefinition(Base, TimestampMixin):
    """QC 规则定义表 — 元数据 + 开关

    每条规则对应一个可执行的质控检查逻辑。
    expression_type 决定执行器分派方式：
    - python: expression 为 dotted module path（如 app.services.qc_engine.ConclusionNotEmptyRule）
    - jsonpath: expression 为 JSONPath 表达式（如 $.parsed_data.conclusion）
    - sql / regex: 预留，执行时抛 NotImplementedError
    """

    __tablename__ = "qc_rule_definitions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rule_code: Mapped[str] = mapped_column(
        String(30), unique=True, nullable=False
    )  # QC-01 ~ QC-26
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # blocking | warning | info
    scope: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # workpaper | project | submit_review | sign_off | export_package | eqcr_approval
    category: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 分类标签
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    standard_ref: Mapped[list | None] = mapped_column(
        JSONB, nullable=True
    )  # ["CAS 1301.12", ...]
    expression_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="python"
    )  # python | jsonpath | sql | regex
    expression: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Python dotted path 或表达式
    parameters_schema: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # JSON Schema for rule params
    enabled: Mapped[bool] = mapped_column(
        sa.Boolean, default=True, nullable=False
    )
    version: Mapped[int] = mapped_column(
        sa.Integer, default=1, nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )

    __table_args__ = (
        Index("idx_qc_rule_definitions_scope", "scope"),
        Index("idx_qc_rule_definitions_enabled", "enabled"),
    )
