"""Phase 16: 取证包与版本链 ORM 模型

Tables:
  - version_line_stamps: 版本链统一戳记
  - evidence_hash_checks: 取证包完整性校验
  - offline_conflicts: 离线冲突与人工合并队列
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Integer, Text, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.models.base import Base


class VersionLineStamp(Base):
    __tablename__ = "version_line_stamps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    object_type = Column(String(32), nullable=False, comment="report/note/workpaper/procedure")
    object_id = Column(UUID(as_uuid=True), nullable=False)
    version_no = Column(Integer, nullable=False)
    source_snapshot_id = Column(String(64), nullable=True)
    trace_id = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_version_line_project_object", "project_id", "object_type", "object_id", version_no.desc()),
        Index("idx_version_line_trace", "trace_id"),
    )


class EvidenceHashCheck(Base):
    __tablename__ = "evidence_hash_checks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    export_id = Column(UUID(as_uuid=True), nullable=False)
    file_path = Column(Text, nullable=False)
    sha256 = Column(String(64), nullable=False)
    signature_digest = Column(String(128), nullable=True)
    check_status = Column(String(16), nullable=False, comment="passed/failed")
    checked_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_evidence_hash_export", "export_id", checked_at.desc()),
    )


class OfflineConflict(Base):
    __tablename__ = "offline_conflicts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    wp_id = Column(UUID(as_uuid=True), nullable=False)
    procedure_id = Column(UUID(as_uuid=True), nullable=False)
    field_name = Column(String(64), nullable=False)
    local_value = Column(JSONB, nullable=True)
    remote_value = Column(JSONB, nullable=True)
    merged_value = Column(JSONB, nullable=True)
    status = Column(String(16), nullable=False, comment="open/resolved/rejected")
    resolver_id = Column(UUID(as_uuid=True), nullable=True)
    reason_code = Column(String(64), nullable=True)
    qc_replay_job_id = Column(UUID(as_uuid=True), nullable=True)
    trace_id = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_offline_conflicts_project_status", "project_id", "status", created_at.desc()),
        Index("idx_offline_conflicts_wp", "wp_id", "status"),
        Index("idx_offline_conflicts_trace", "trace_id"),
    )
