"""Phase 14: 统一门禁引擎 ORM 模型

Tables:
  - trace_events: 统一过程留痕主表（对齐 v2 WP-ENT-01 / 5.9.3 D-01）
  - gate_decisions: 门禁决策记录表（对齐 v2 5.9.3 D-02）
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Text, Boolean, DateTime, Index,
    ForeignKey, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.models.base import Base


class TraceEvent(Base):
    """统一过程留痕主表

    覆盖：提交复核/签字/导出/裁剪/回滚/门禁评估/SoD校验/WOPI访问
    Phase 15/16 事件也写入此表，通过 event_type 区分。
    """
    __tablename__ = "trace_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    event_type = Column(String(64), nullable=False, comment="wp_saved/submit_review/sign_off/export/trim_applied/trim_rollback/gate_evaluated/sod_checked/...")
    object_type = Column(String(32), nullable=False, comment="workpaper/adjustment/report/note/procedure/conversation/export/gate_decision/issue_ticket/offline_conflict")
    object_id = Column(UUID(as_uuid=True), nullable=False)
    actor_id = Column(UUID(as_uuid=True), nullable=False)
    actor_role = Column(String(32), nullable=True, comment="assistant/manager/partner/qc/admin")
    action = Column(String(100), nullable=False)
    decision = Column(String(16), nullable=True, comment="allow/block/warn - 门禁/SoD场景")
    reason_code = Column(String(64), nullable=True, comment="对齐 v2 4.5.6 统一原因码")
    from_status = Column(String(32), nullable=True, comment="状态流转起始状态")
    to_status = Column(String(32), nullable=True, comment="状态流转目标状态")
    before_snapshot = Column(JSONB, nullable=True)
    after_snapshot = Column(JSONB, nullable=True)
    content_hash = Column(String(64), nullable=True, comment="对象内容 SHA-256（取证用）")
    version_no = Column(Integer, nullable=True)
    trace_id = Column(String(64), nullable=False, comment="格式: trc_{yyyyMMddHHmmss}_{uuid[:12]}")
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_trace_events_project", "project_id", "event_type", created_at.desc()),
        Index("idx_trace_events_object", "object_type", "object_id", created_at.desc()),
        Index("idx_trace_events_trace_id", "trace_id"),
        Index("idx_trace_events_actor", "actor_id", created_at.desc()),
    )


class GateDecision(Base):
    """门禁决策记录表

    每次 gate_engine.evaluate() 调用写入一条记录。
    """
    __tablename__ = "gate_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), nullable=False)
    wp_id = Column(UUID(as_uuid=True), nullable=True)
    gate_type = Column(String(32), nullable=False, comment="submit_review/sign_off/export_package")
    decision = Column(String(16), nullable=False, comment="allow/warn/block")
    hit_rules = Column(JSONB, nullable=False, comment="[{rule_code, error_code, severity, message, location, suggested_action}]")
    actor_id = Column(UUID(as_uuid=True), nullable=False)
    trace_id = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_gate_decisions_project_gate", "project_id", "gate_type", created_at.desc()),
        Index("idx_gate_decisions_trace", "trace_id"),
    )


class GateRuleConfig(Base):
    """门禁规则配置表 — 平台强制 vs 租户可配置分层

    Phase 14 Task 9: 规则配置分层
    - config_level='platform': 不允许租户覆盖（如关键合规阻断阈值）
    - config_level='tenant': 允许按租户调整（如告警阈值）
    """
    __tablename__ = "gate_rule_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_code = Column(String(32), nullable=False, comment="QC-15 ~ QC-26 / CONSISTENCY-BLOCK")
    config_level = Column(String(16), nullable=False, comment="platform / tenant")
    threshold_key = Column(String(64), nullable=False, comment="如 consistency_diff_threshold / ocr_confidence_threshold")
    threshold_value = Column(String(128), nullable=False, comment="阈值字符串，由规则自行解析")
    tenant_id = Column(UUID(as_uuid=True), nullable=True, comment="租户ID，platform 级为 NULL")
    description = Column(String(200), nullable=True)
    updated_by = Column(UUID(as_uuid=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_gate_rule_configs_rule", "rule_code", "config_level"),
        Index("idx_gate_rule_configs_tenant", "tenant_id", "rule_code"),
    )
