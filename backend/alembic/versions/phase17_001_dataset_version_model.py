"""Phase 17: 数据集版本治理模型

新增 4 张表：
- import_artifacts: 上传产物
- import_jobs: 导入作业状态机
- ledger_datasets: 业务级数据集版本
- activation_records: 激活/回滚留痕

新增 4 个枚举：
- dataset_status
- job_status
- artifact_status
- activation_type

Revision ID: phase17_001
Revises: a2f355648e85
"""

revision = "phase17_001"
down_revision = "a2f355648e85"
branch_labels = None
depends_on = None


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


def upgrade() -> None:
    # 枚举类型
    op.execute("CREATE TYPE IF NOT EXISTS dataset_status AS ENUM ('staged','active','superseded','failed','rolled_back')")
    op.execute("CREATE TYPE IF NOT EXISTS job_status AS ENUM ('pending','queued','running','validating','writing','activating','completed','failed','canceled','timed_out')")
    op.execute("CREATE TYPE IF NOT EXISTS artifact_status AS ENUM ('active','expired','consumed')")
    op.execute("CREATE TYPE IF NOT EXISTS activation_type AS ENUM ('activate','rollback')")

    # import_artifacts（先建，因为 import_jobs 引用它）
    op.create_table(
        "import_artifacts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("upload_token", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.Enum("active", "expired", "consumed", name="artifact_status", create_type=False), server_default="active", nullable=False),
        sa.Column("storage_uri", sa.Text, nullable=False),
        sa.Column("checksum", sa.String(128), nullable=True),
        sa.Column("total_size_bytes", sa.BigInteger, server_default="0", nullable=False),
        sa.Column("file_manifest", JSONB, nullable=True),
        sa.Column("file_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("idx_import_artifacts_project", "import_artifacts", ["project_id"])
    op.create_index("idx_import_artifacts_token", "import_artifacts", ["upload_token"], unique=True)

    # import_jobs
    op.create_table(
        "import_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("status", sa.Enum("pending", "queued", "running", "validating", "writing", "activating", "completed", "failed", "canceled", "timed_out", name="job_status", create_type=False), server_default="pending", nullable=False),
        sa.Column("artifact_id", UUID(as_uuid=True), sa.ForeignKey("import_artifacts.id"), nullable=True),
        sa.Column("custom_mapping", JSONB, nullable=True),
        sa.Column("options", JSONB, nullable=True),
        sa.Column("progress_pct", sa.Integer, server_default="0", nullable=False),
        sa.Column("progress_message", sa.Text, nullable=True),
        sa.Column("current_phase", sa.String(50), nullable=True),
        sa.Column("result_summary", JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("retry_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("max_retries", sa.Integer, server_default="3", nullable=False),
        sa.Column("heartbeat_at", sa.DateTime, nullable=True),
        sa.Column("timeout_seconds", sa.Integer, server_default="600", nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )
    op.create_index("idx_import_jobs_project_year", "import_jobs", ["project_id", "year"])
    op.create_index("idx_import_jobs_status", "import_jobs", ["status"])

    # ledger_datasets
    op.create_table(
        "ledger_datasets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("status", sa.Enum("staged", "active", "superseded", "failed", "rolled_back", name="dataset_status", create_type=False), server_default="staged", nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False, server_default="import"),
        sa.Column("source_summary", JSONB, nullable=True),
        sa.Column("record_summary", JSONB, nullable=True),
        sa.Column("validation_summary", JSONB, nullable=True),
        sa.Column("job_id", UUID(as_uuid=True), sa.ForeignKey("import_jobs.id"), nullable=True),
        sa.Column("previous_dataset_id", UUID(as_uuid=True), sa.ForeignKey("ledger_datasets.id"), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("activated_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("activated_at", sa.DateTime, nullable=True),
    )
    op.create_index("idx_ledger_datasets_project_year", "ledger_datasets", ["project_id", "year"])
    op.create_index("idx_ledger_datasets_active", "ledger_datasets", ["project_id", "year", "status"])

    # activation_records
    op.create_table(
        "activation_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("dataset_id", UUID(as_uuid=True), sa.ForeignKey("ledger_datasets.id"), nullable=False),
        sa.Column("action", sa.Enum("activate", "rollback", name="activation_type", create_type=False), nullable=False),
        sa.Column("previous_dataset_id", UUID(as_uuid=True), sa.ForeignKey("ledger_datasets.id"), nullable=True),
        sa.Column("performed_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("performed_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("reason", sa.Text, nullable=True),
    )
    op.create_index("idx_activation_records_project_year", "activation_records", ["project_id", "year"])


def downgrade() -> None:
    op.drop_table("activation_records")
    op.drop_table("ledger_datasets")
    op.drop_table("import_jobs")
    op.drop_table("import_artifacts")
    op.execute("DROP TYPE IF EXISTS activation_type")
    op.execute("DROP TYPE IF EXISTS artifact_status")
    op.execute("DROP TYPE IF EXISTS job_status")
    op.execute("DROP TYPE IF EXISTS dataset_status")
