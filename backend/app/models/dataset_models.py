"""数据集版本治理模型

企业级账表导入的核心数据模型：
- LedgerDataset: 业务级数据集版本（一次完整导入的产物）
- ImportJob: 导入作业（任务执行状态机）
- ImportArtifact: 上传产物（文件引用）
- ActivationRecord: 激活/回滚留痕

设计原则：
- ImportBatch 保留为底层写入批次（兼容过渡）
- LedgerDataset 是业务级版本，同一 project+year 只有一个 active
- ImportJob 关注任务执行过程，与数据版本解耦
- ImportArtifact 关注文件存储，支持跨节点访问
"""

import enum
import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import ForeignKey, Index, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------


class DatasetStatus(str, enum.Enum):
    """数据集版本状态"""
    staged = "staged"          # 已写入但未激活
    active = "active"          # 当前生效版本
    superseded = "superseded"  # 被新版本替代
    failed = "failed"          # 导入失败
    rolled_back = "rolled_back"  # 已回滚


class JobStatus(str, enum.Enum):
    """导入作业状态机"""
    pending = "pending"
    queued = "queued"
    running = "running"
    validating = "validating"
    writing = "writing"
    activating = "activating"
    completed = "completed"
    failed = "failed"
    canceled = "canceled"
    timed_out = "timed_out"


class ArtifactStatus(str, enum.Enum):
    """上传产物状态"""
    active = "active"
    expired = "expired"
    consumed = "consumed"  # 已被导入作业消费


class ActivationType(str, enum.Enum):
    """激活动作类型"""
    activate = "activate"
    rollback = "rollback"
    force_unbind = "force_unbind"


class OutboxStatus(str, enum.Enum):
    """导入事件 outbox 发布状态"""
    pending = "pending"
    published = "published"
    failed = "failed"


# ---------------------------------------------------------------------------
# LedgerDataset — 业务级数据集版本
# ---------------------------------------------------------------------------


class LedgerDataset(Base):
    """业务级数据集版本

    同一 project_id + year 只有一个 status=active 的记录。
    导入成功后 staged → active，旧 active → superseded。
    """

    __tablename__ = "ledger_datasets"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # F41 / Sprint 7.5: 多租户预留列（暂恒为 'default'）
    tenant_id: Mapped[str] = mapped_column(
        String(64), server_default=text("'default'"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    status: Mapped[DatasetStatus] = mapped_column(
        sa.Enum(DatasetStatus, name="dataset_status", create_type=False),
        server_default=text("'staged'"),
        nullable=False,
    )

    # 来源信息
    source_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="import"
    )  # import / migration / rollback
    source_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {"files": ["余额表.xlsx", "序时账.csv"], "total_records": 1200000}

    # 统计摘要
    record_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {"tb_balance": 827, "tb_ledger": 1147414, "tb_aux_balance": 127618, "tb_aux_ledger": 2732674}

    # 校验报告
    validation_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {"total": 5, "blocking_count": 0, "by_severity": {...}}

    # 关联
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_jobs.id"), nullable=True
    )
    previous_dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ledger_datasets.id"), nullable=True
    )

    # 操作者与时间
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    activated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    activated_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index("idx_ledger_datasets_project_year", "project_id", "year"),
        Index("idx_ledger_datasets_active", "project_id", "year", "status"),
        # F41 / Sprint 7.5: tenant 维度复合索引
        Index(
            "idx_ledger_datasets_tenant_project_year",
            "tenant_id", "project_id", "year",
        ),
    )


# ---------------------------------------------------------------------------
# ImportJob — 导入作业状态机
# ---------------------------------------------------------------------------


class ImportJob(Base):
    """导入作业 — 关注任务执行过程

    与 LedgerDataset 解耦：一个 Job 产生一个 Dataset。
    Job 关注"怎么执行"，Dataset 关注"产出了什么"。
    """

    __tablename__ = "import_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        sa.Enum(JobStatus, name="job_status_enum", create_type=False),
        server_default=text("'pending'"),
        nullable=False,
    )

    # 作业配置
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("import_artifacts.id"), nullable=True
    )
    custom_mapping: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    options: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # {"skip_validation": false, "force_activate": false}

    # 进度
    progress_pct: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    progress_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_phase: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # pending → queued → running → validating → writing → activating → completed

    # 结果
    result_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    max_retries: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("3"), nullable=False
    )

    # 心跳（durable job 用）
    heartbeat_at: Mapped[datetime | None] = mapped_column(nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("600"), nullable=False
    )  # 默认 10 分钟超时

    # P1-Q1: 乐观锁版本号（防并发 cancel/retry 竞态）
    # 每次 status/progress 更新时 +1，端点调用时传入预期版本号做 WHERE 守卫
    version: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )

    # F42 / Sprint 7.10: 规模异常强制继续标记
    # detect 阶段若返回 EMPTY_LEDGER_WARNING / SUSPICIOUS_DATASET_SIZE，submit
    # 时必须传 ``force_submit=True`` 才能绕过门控；该值持久化到 ImportJob 以保留
    # "用户明确覆盖了规模警告"的审计轨迹（见 design D30 / requirements F42）。
    force_submit: Mapped[bool] = mapped_column(
        sa.Boolean, server_default=text("false"), nullable=False
    )

    # 操作者与时间
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    # F22 / Sprint 5.9: 接管链路记录
    # 格式: [{"user_id": "A", "action": "create", "at": "..."}, ...]
    creator_chain: Mapped[list | None] = mapped_column(
        JSONB, server_default=text("'[]'"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index("idx_import_jobs_project_year", "project_id", "year"),
        Index("idx_import_jobs_status", "status"),
    )


# ---------------------------------------------------------------------------
# ImportArtifact — 上传产物
# ---------------------------------------------------------------------------


class ImportArtifact(Base):
    """上传产物 — 平台级文件引用

    从本地 bundle 升级为可跨节点访问的产物对象。
    支持本地/共享卷/对象存储三种后端。
    """

    __tablename__ = "import_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    upload_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[ArtifactStatus] = mapped_column(
        sa.Enum(ArtifactStatus, name="artifact_status", create_type=False),
        server_default=text("'active'"),
        nullable=False,
    )

    # 存储信息
    storage_uri: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # local:///path/to/bundle 或 s3://bucket/key
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)  # SHA256
    total_size_bytes: Mapped[int] = mapped_column(
        sa.BigInteger, server_default=text("0"), nullable=False
    )

    # 文件清单
    file_manifest: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # [{"file_name": "余额表.xlsx", "size_bytes": 1024, "mime_type": "..."}]

    # 治理
    file_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # F53 / Sprint 8.38: 留档合规保留期分类
    # - transient（默认）：90 天过期，purge 任务物理删
    # - archived       ：10 年过期，元数据永久保留
    # - legal_hold     ：法定保留，永不删除
    # 由 DatasetService.activate → compute_retention_class 联动决策（F53 / Sprint 8.40）。
    retention_class: Mapped[str] = mapped_column(
        String(20), server_default=text("'transient'"), nullable=False
    )
    retention_expires_at: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True), nullable=True
    )

    # 操作者与时间
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("idx_import_artifacts_project", "project_id"),
        Index("idx_import_artifacts_token", "upload_token", unique=True),
        # F53 / Sprint 8.41: purge 任务按 retention_class + retention_expires_at 扫描
        Index(
            "idx_import_artifacts_retention",
            "retention_class", "retention_expires_at",
        ),
    )


# ---------------------------------------------------------------------------
# ActivationRecord — 激活/回滚留痕
# ---------------------------------------------------------------------------


class ActivationRecord(Base):
    """激活/回滚操作留痕

    每次数据集状态变更（staged→active, active→rolled_back）都记录一条。
    """

    __tablename__ = "activation_records"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("ledger_datasets.id"), nullable=False
    )
    action: Mapped[ActivationType] = mapped_column(
        sa.Enum(ActivationType, name="activation_type", create_type=False),
        nullable=False,
    )
    previous_dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("ledger_datasets.id"), nullable=True
    )

    # 操作者与时间
    performed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    performed_at: Mapped[datetime] = mapped_column(server_default=func.now())
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # F25 / Sprint 5.18: 审计溯源扩展字段
    # 用于"谁在什么时间、从哪里、花了多久激活哪个版本"的完整轨迹
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    # 记录激活/回滚前后的四表行数，防静默数据损失
    # 形如 {"tb_balance": 827, "tb_ledger": 1147414, "tb_aux_balance": 127618, "tb_aux_ledger": 2732674}
    before_row_counts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_row_counts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("idx_activation_records_project_year", "project_id", "year"),
    )


class ImportEventOutbox(Base):
    """导入域事件 outbox。

    与激活/回滚状态变更在同一事务写入，提交后异步发布并标记 published。
    如果进程在 commit 与 publish 之间崩溃，pending 记录可被重放补偿。
    """

    __tablename__ = "import_event_outbox"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[OutboxStatus] = mapped_column(
        sa.Enum(OutboxStatus, name="import_event_outbox_status", create_type=False),
        server_default=text("'pending'"),
        nullable=False,
    )
    attempt_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    published_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index("idx_import_event_outbox_status", "status", "created_at"),
        Index("idx_import_event_outbox_project_year", "project_id", "year"),
    )


class EventOutboxDLQ(Base):
    """事件广播死信队列（F45）。

    ``import_event_outbox`` 的事件重试 N 次仍失败后（N = ``LEDGER_IMPORT_OUTBOX_MAX_RETRY_ATTEMPTS``），
    Worker 会把事件 snapshot 进本表作为"死信"保留，原 outbox 行保留 status=failed 作审计。

    - ``original_event_id``：指向原 outbox 行（FK nullable，原行被清理后自动 SET NULL）
    - ``payload``：事件载荷 snapshot，独立存储便于手动重投
    - ``failure_reason``：最后一次失败的异常信息
    - ``attempt_count``：进入 DLQ 时的累计尝试次数
    - ``resolved_at / resolved_by``：人工处理回执（``null`` = 未处理）
    """

    __tablename__ = "event_outbox_dlq"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    original_event_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("import_event_outbox.id", ondelete="SET NULL"),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id"), nullable=False
    )
    year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(
        sa.Integer, server_default=text("0"), nullable=False
    )
    moved_to_dlq_at: Mapped[datetime] = mapped_column(server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (
        Index(
            "idx_event_outbox_dlq_project_year",
            "project_id", "year", "moved_to_dlq_at",
        ),
        # 未处理的 DLQ 行（运维优先查的场景）
        Index(
            "idx_event_outbox_dlq_unresolved",
            "moved_to_dlq_at",
            postgresql_where=text("resolved_at IS NULL"),
        ),
    )


class ImportEventConsumption(Base):
    """事件消费幂等记录。

    使用 (event_id, handler_name) 唯一约束保证同一事件不会被同一处理器重复执行。
    """

    __tablename__ = "import_event_consumptions"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    handler_name: Mapped[str] = mapped_column(String(200), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    year: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    consumed_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        Index("uq_import_event_consumptions_event_handler", "event_id", "handler_name", unique=True),
        Index("idx_import_event_consumptions_project_year", "project_id", "year"),
    )
