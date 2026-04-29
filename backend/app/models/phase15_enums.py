"""Phase 15: 任务树与事件编排枚举定义

引用 Phase 14 的 ReasonCode/TraceEventType 等跨阶段枚举。
"""
from enum import Enum


class NodeLevel(str, Enum):
    """四级任务树节点层级"""
    unit = "unit"
    account = "account"
    workpaper = "workpaper"
    evidence = "evidence"


class TaskNodeStatus(str, Enum):
    """任务节点状态"""
    pending = "pending"
    in_progress = "in_progress"
    blocked = "blocked"
    done = "done"


class TaskEventType(str, Enum):
    """事件总线事件类型"""
    trim_applied = "trim_applied"
    trim_rollback = "trim_rollback"
    task_reassigned = "task_reassigned"
    task_blocked = "task_blocked"
    task_unblocked = "task_unblocked"
    issue_created = "issue_created"
    issue_escalated = "issue_escalated"
    issue_closed = "issue_closed"


class TaskEventStatus(str, Enum):
    """事件处理状态"""
    queued = "queued"
    replaying = "replaying"
    succeeded = "succeeded"
    failed = "failed"
    dead_letter = "dead_letter"


class IssueStatus(str, Enum):
    """问题单状态（对齐 v2 4.5.15A）"""
    open = "open"
    in_fix = "in_fix"
    pending_recheck = "pending_recheck"
    closed = "closed"
    rejected = "rejected"


class IssueSource(str, Enum):
    """问题单来源"""
    L2 = "L2"
    L3 = "L3"
    Q = "Q"


class IssueCategory(str, Enum):
    """问题单分类（对齐 Phase 14 ReasonCode）"""
    data_mismatch = "data_mismatch"
    evidence_missing = "evidence_missing"
    explanation_incomplete = "explanation_incomplete"
    procedure_incomplete = "procedure_incomplete"
    policy_violation = "policy_violation"
