"""Phase 15: 任务树与事件编排 ORM 模型

Tables:
  - task_tree_nodes: 四级任务树节点
  - task_events: 事件总线与补偿队列
  - issue_tickets: 统一问题单（对齐 v2 4.5.15A）
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Text, Boolean, DateTime, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.models.base import Base


class TaskTreeNode(Base):
    """四级任务树节点：unit/account/workpaper/evidence"""
    __tablename__ = "task_tree_nodes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    node_level = Column(String(16), nullable=False, comment="unit/account/workpaper/evidence")
    parent_id = Column(UUID(as_uuid=True), nullable=True)
    ref_id = Column(UUID(as_uuid=True), nullable=False, comment="关联业务对象ID")
    status = Column(String(16), nullable=False, default="pending", comment="pending/in_progress/blocked/done")
    assignee_id = Column(UUID(as_uuid=True), nullable=True)
    due_at = Column(DateTime, nullable=True)
    meta = Column(JSONB, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_task_tree_project_level", "project_id", "node_level", "status"),
        Index("idx_task_tree_parent", "parent_id"),
        Index("idx_task_tree_assignee", "assignee_id", "status"),
    )


class TaskEvent(Base):
    """事件总线与补偿队列"""
    __tablename__ = "task_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    event_type = Column(String(64), nullable=False)
    task_node_id = Column(UUID(as_uuid=True), nullable=True)
    payload = Column(JSONB, nullable=False)
    status = Column(String(16), nullable=False, default="queued", comment="queued/replaying/succeeded/failed/dead_letter")
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    next_retry_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    trace_id = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_task_events_project_status", "project_id", "status", created_at.desc()),
        Index("idx_task_events_trace", "trace_id"),
    )


class IssueTicket(Base):
    """统一问题单（对齐 v2 4.5.15A）

    L2/L3/Q 问题统一管理，支持 SLA 升级。

    R1 一次性扩展 ``source`` 枚举为 5 轮共享的全量 11 值，避免后续轮次多次迁移
    （依据 ``refinement-round1-review-closure`` 需求 2.2 与 README v2.2
    "数据库迁移约定" 第 4 条）。可选值：``L2 / L3 / Q / review_comment /
    consistency / ai / reminder / client_commitment / pbc / confirmation /
    qc_inspection``。
    """
    __tablename__ = "issue_tickets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    wp_id = Column(UUID(as_uuid=True), nullable=True)
    task_node_id = Column(UUID(as_uuid=True), nullable=True)
    conversation_id = Column(UUID(as_uuid=True), nullable=True)
    source = Column(
        String(32),
        nullable=False,
        comment=(
            "L2/L3/Q/review_comment/consistency/ai/reminder/client_commitment/"
            "pbc/confirmation/qc_inspection"
        ),
    )
    # R1: 源对象 ID，用于双向追溯（如对应 ReviewRecord.id）
    source_ref_id = Column(UUID(as_uuid=True), nullable=True)
    severity = Column(String(16), nullable=False, comment="blocker/major/minor/suggestion")
    category = Column(String(64), nullable=False, comment="data_mismatch/evidence_missing/...")
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    owner_id = Column(UUID(as_uuid=True), nullable=False)
    due_at = Column(DateTime, nullable=True)
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    account_code = Column(String(20), nullable=True)
    status = Column(String(20), nullable=False, default="open", comment="open/in_fix/pending_recheck/closed/rejected")
    thread_id = Column(UUID(as_uuid=True), nullable=True)
    evidence_refs = Column(JSONB, default=list)
    reason_code = Column(String(64), nullable=True)
    trace_id = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_issue_tickets_project_status", "project_id", "status", created_at.desc()),
        Index("idx_issue_tickets_owner", "owner_id", "status"),
        Index("idx_issue_tickets_source", "source", "severity"),
        Index("idx_issue_tickets_conversation", "conversation_id"),
    )
