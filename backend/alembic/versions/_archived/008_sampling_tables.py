"""008 sampling tables — 抽样配置 + 抽样记录

Revision ID: 008
Revises: 007
Create Date: 2025-01-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- 枚举类型 ----
    sampling_type_enum = sa.Enum(
        "statistical", "non_statistical",
        name="sampling_type",
    )
    sampling_type_enum.create(op.get_bind(), checkfirst=True)

    sampling_method_enum = sa.Enum(
        "mus", "attribute", "random", "systematic", "stratified",
        name="sampling_method",
    )
    sampling_method_enum.create(op.get_bind(), checkfirst=True)

    applicable_scenario_enum = sa.Enum(
        "control_test", "substantive_test",
        name="applicable_scenario",
    )
    applicable_scenario_enum.create(op.get_bind(), checkfirst=True)

    # ---- 23.1 sampling_config ----
    op.create_table(
        "sampling_config",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("config_name", sa.String, nullable=False),
        sa.Column(
            "sampling_type",
            sa.Enum("statistical", "non_statistical",
                    name="sampling_type", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "sampling_method",
            sa.Enum("mus", "attribute", "random", "systematic", "stratified",
                    name="sampling_method", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "applicable_scenario",
            sa.Enum("control_test", "substantive_test",
                    name="applicable_scenario", create_type=False),
            nullable=False,
        ),
        sa.Column("confidence_level", sa.Numeric(5, 4), nullable=True),
        sa.Column("expected_deviation_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("tolerable_deviation_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("tolerable_misstatement", sa.Numeric(20, 2), nullable=True),
        sa.Column("population_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("population_count", sa.Integer, nullable=True),
        sa.Column("calculated_sample_size", sa.Integer, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_sampling_config_project_method",
        "sampling_config",
        ["project_id", "sampling_method"],
    )

    # ---- 23.2 sampling_records ----
    op.create_table(
        "sampling_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("working_paper_id", UUID(as_uuid=True), sa.ForeignKey("working_paper.id"), nullable=True),
        sa.Column("sampling_config_id", UUID(as_uuid=True), sa.ForeignKey("sampling_config.id"), nullable=True),
        sa.Column("sampling_purpose", sa.Text, nullable=False),
        sa.Column("population_description", sa.Text, nullable=False),
        sa.Column("population_total_amount", sa.Numeric(20, 2), nullable=True),
        sa.Column("population_total_count", sa.Integer, nullable=True),
        sa.Column("sample_size", sa.Integer, nullable=False),
        sa.Column("sampling_method_description", sa.Text, nullable=True),
        sa.Column("deviations_found", sa.Integer, nullable=True),
        sa.Column("misstatements_found", sa.Numeric(20, 2), nullable=True),
        sa.Column("projected_misstatement", sa.Numeric(20, 2), nullable=True),
        sa.Column("upper_misstatement_limit", sa.Numeric(20, 2), nullable=True),
        sa.Column("conclusion", sa.Text, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_sampling_records_project_wp",
        "sampling_records",
        ["project_id", "working_paper_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_sampling_records_project_wp", table_name="sampling_records")
    op.drop_table("sampling_records")

    op.drop_index("idx_sampling_config_project_method", table_name="sampling_config")
    op.drop_table("sampling_config")

    # Drop enums
    sa.Enum(name="applicable_scenario").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="sampling_method").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="sampling_type").drop(op.get_bind(), checkfirst=True)
