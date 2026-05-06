"""Refinement Round 6: QC Rule Definitions table

Revision ID: round6_qc_rule_definitions_20260507
Revises: round5_eqcr_check_constraints_20260506

新建 ``qc_rule_definitions`` 表，存储 QC 规则元数据与开关。
22 条内置规则（QC-01~14 + QC-19~26）通过 seed 数据加载，不在 migration 中插入。

字段说明：
- rule_code: 唯一规则编码（如 QC-01）
- severity: blocking | warning | info
- scope: workpaper | project | submit_review | sign_off | export_package | eqcr_approval
- expression_type: python | jsonpath | sql | regex（后两者本轮预留）
- expression: Python dotted path 或 JSONPath 表达式
- enabled: 规则开关
- version: 规则版本号

遵循 ``backend/alembic/MIGRATION_GUIDE.md`` 的幂等原则：使用 ``IF [NOT] EXISTS``
+ inspector 防重。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "round6_qc_rule_definitions_20260507"
down_revision = "round5_eqcr_check_constraints_20260506"
branch_labels = None
depends_on = None


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def _inspector():
    bind = op.get_bind()
    return sa.inspect(bind)


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    indexes = {ix["name"] for ix in _inspector().get_indexes(table_name)}
    return index_name in indexes


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    if not _has_table("qc_rule_definitions"):
        op.create_table(
            "qc_rule_definitions",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                nullable=False,
            ),
            sa.Column("rule_code", sa.String(length=30), nullable=False),
            sa.Column("severity", sa.String(length=20), nullable=False),
            sa.Column("scope", sa.String(length=30), nullable=False),
            sa.Column("category", sa.String(length=50), nullable=False),
            sa.Column("title", sa.String(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column(
                "standard_ref",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column(
                "expression_type",
                sa.String(length=20),
                nullable=False,
                server_default="python",
            ),
            sa.Column("expression", sa.Text(), nullable=True),
            sa.Column(
                "parameters_schema",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
            sa.Column(
                "enabled",
                sa.Boolean(),
                server_default=sa.text("true"),
                nullable=False,
            ),
            sa.Column(
                "version",
                sa.Integer(),
                server_default=sa.text("1"),
                nullable=False,
            ),
            sa.Column(
                "created_by",
                postgresql.UUID(as_uuid=True),
                nullable=True,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.func.now(),
                nullable=False,
            ),
            # Unique constraint on rule_code
            sa.UniqueConstraint("rule_code", name="uq_qc_rule_definitions_rule_code"),
        )

    # Indexes
    if not _has_index("qc_rule_definitions", "idx_qc_rule_definitions_scope"):
        op.create_index(
            "idx_qc_rule_definitions_scope",
            "qc_rule_definitions",
            ["scope"],
        )

    if not _has_index("qc_rule_definitions", "idx_qc_rule_definitions_enabled"):
        op.create_index(
            "idx_qc_rule_definitions_enabled",
            "qc_rule_definitions",
            ["enabled"],
        )


# ---------------------------------------------------------------------------
# downgrade
# ---------------------------------------------------------------------------


def downgrade() -> None:
    if _has_index("qc_rule_definitions", "idx_qc_rule_definitions_enabled"):
        op.drop_index(
            "idx_qc_rule_definitions_enabled",
            table_name="qc_rule_definitions",
        )
    if _has_index("qc_rule_definitions", "idx_qc_rule_definitions_scope"):
        op.drop_index(
            "idx_qc_rule_definitions_scope",
            table_name="qc_rule_definitions",
        )
    if _has_table("qc_rule_definitions"):
        op.drop_table("qc_rule_definitions")
