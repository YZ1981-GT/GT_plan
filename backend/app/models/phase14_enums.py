"""Phase 14: 统一门禁引擎枚举定义 — 跨阶段字段契约基础层

Phase 15/16 引用本文件定义，不重复定义。
任何变更必须先回写 Phase 14 design §8 再进入编码。
"""
from enum import Enum


# ── trace_id 格式 ──────────────────────────────────────────────
# 格式: trc_{yyyyMMddHHmmss}_{uuid_short_12}
# 示例: trc_20260428143500_a1b2c3d4e5f6
# 长度: 31 字符
# 生成: trace_event_service.generate_trace_id()


class GateType(str, Enum):
    """门禁入口类型"""
    submit_review = "submit_review"
    sign_off = "sign_off"
    eqcr_approval = "eqcr_approval"  # R5：EQCR 审批门禁，位于 sign_off 与 export_package 之间
    export_package = "export_package"


class GateDecisionResult(str, Enum):
    """门禁判定结果"""
    allow = "allow"
    warn = "warn"
    block = "block"


class GateSeverity(str, Enum):
    """门禁规则严重度"""
    blocking = "blocking"
    warning = "warning"
    info = "info"


class IssueSeverity(str, Enum):
    """问题单严重度（Phase 15 使用）"""
    blocker = "blocker"
    major = "major"
    minor = "minor"
    suggestion = "suggestion"


class ReasonCode(str, Enum):
    """统一原因码（对齐 v2 4.5.6 最小集 + 扩展）"""
    # 门禁/冲突/一致性
    DATA_MISMATCH = "DATA_MISMATCH"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    EXPLANATION_INCOMPLETE = "EXPLANATION_INCOMPLETE"
    PROCEDURE_INCOMPLETE = "PROCEDURE_INCOMPLETE"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    # LLM/AI
    LLM_PENDING_CONFIRM = "LLM_PENDING_CONFIRM"
    LLM_TRIM_CONFLICT = "LLM_TRIM_CONFLICT"
    # 版本/映射
    VERSION_STALE = "VERSION_STALE"
    SOURCE_MAPPING_MISSING = "SOURCE_MAPPING_MISSING"
    # 裁剪
    TRIM_MANDATORY = "TRIM_MANDATORY"
    TRIM_NO_EVIDENCE = "TRIM_NO_EVIDENCE"
    # SoD
    SOD_CONFLICT = "SOD_CONFLICT"
    # 冲突合并
    CONFLICT_ACCEPT_LOCAL = "CONFLICT_ACCEPT_LOCAL"
    CONFLICT_ACCEPT_REMOTE = "CONFLICT_ACCEPT_REMOTE"
    CONFLICT_MANUAL_MERGE = "CONFLICT_MANUAL_MERGE"
    # SLA
    SLA_TIMEOUT = "SLA_TIMEOUT"
    # RC 复核对话
    RC_CREATE_MANUAL = "RC_CREATE_MANUAL"
    RC_MSG_NORMAL = "RC_MSG_NORMAL"
    RC_RESOLVED_EVIDENCE_COMPLETE = "RC_RESOLVED_EVIDENCE_COMPLETE"
    RC_EXPORT_EVIDENCE = "RC_EXPORT_EVIDENCE"
    # 迁移
    BACKFILL_MIGRATION = "BACKFILL_MIGRATION"


class TraceEventType(str, Enum):
    """trace_events 事件类型"""
    # 底稿生命周期
    wp_saved = "wp_saved"
    submit_review = "submit_review"
    review_returned = "review_returned"
    review_passed = "review_passed"
    # 签字/导出
    sign_off = "sign_off"
    export = "export"
    partner_signed = "partner_signed"
    # 裁剪
    trim_applied = "trim_applied"
    trim_rollback = "trim_rollback"
    # 门禁
    gate_evaluated = "gate_evaluated"
    # SoD
    sod_checked = "sod_checked"
    # WOPI
    wopi_access = "wopi_access"
    # 事件编排（Phase 15）
    event_replayed = "event_replayed"
    event_dead_letter = "event_dead_letter"
    # 问题单（Phase 15）
    issue_created = "issue_created"
    issue_status_changed = "issue_status_changed"
    issue_escalated = "issue_escalated"
    # RC（Phase 15）
    rc_evidence_exported = "rc_evidence_exported"
    # 取证/版本（Phase 16）
    export_integrity_checked = "export_integrity_checked"
    integrity_check_failed = "integrity_check_failed"
    conflict_detected = "conflict_detected"
    conflict_resolved = "conflict_resolved"


class TraceObjectType(str, Enum):
    """trace_events 对象类型"""
    workpaper = "workpaper"
    adjustment = "adjustment"
    report = "report"
    note = "note"
    procedure = "procedure"
    conversation = "conversation"
    export = "export"
    gate_decision = "gate_decision"
    issue_ticket = "issue_ticket"
    offline_conflict = "offline_conflict"


class TraceReplayLevel(str, Enum):
    """trace 回放等级"""
    L1 = "L1"  # 摘要: who/what/when
    L2 = "L2"  # 含 before/after snapshot
    L3 = "L3"  # 含 content_hash 可复算校验


class SoDRole(str, Enum):
    """SoD 职责分离角色"""
    preparer = "preparer"
    reviewer = "reviewer"
    partner_approver = "partner_approver"
    qc_reviewer = "qc_reviewer"
