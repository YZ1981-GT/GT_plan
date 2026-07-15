"""程序行任务通知类型 —— 前后端单一真源（Task 15 / CI guard 前后端通知类型）

Feature: procedure-delegation-notification
需求：10.4-10.9, 13.9, 14.1-14.3
Design：D8（有序 outbox 与聚合通知分离）、C10、F4

本模块是 **后端权威** 的程序行任务通知/SSE 事件类型清单。前端
``audit-platform/frontend/src/constants/procedureNotificationTypes.ts`` 必须镜像同一集合；
CI guard ``check_procedure_delegation_architecture.py`` 的 notification-type-sync 检查会解析
两侧清单并在漂移时失败（Req 13.9）。

约束（不变量，由 guard 校验）：
- ``ProcedureDeliveryDispatcher`` 逐事件投影使用的 event_type（``_EVENT_RECIPIENT_RULES`` /
  ``_title_for`` 的键）必须是本清单的子集；新增领域通知类型必须先登记到此处并同步前端。
- 聚合摘要通知 ``delegation_batch_summary`` 与复核对话 ``comment`` / ``reply`` /
  ``reviewer_missing`` 一并纳入，保证前端 NotificationCenter 深链能覆盖全部类型。
"""

from __future__ import annotations

# 逐事件领域通知类型（dispatcher 逐事件投影产生）。
NOTIFICATION_ASSIGNED = "assigned"
NOTIFICATION_REASSIGNED = "reassigned"
NOTIFICATION_SUBMITTED = "submitted"
NOTIFICATION_CHANGES_REQUESTED = "changes_requested"
NOTIFICATION_REVIEWED = "reviewed"
# 复核对话/回退闭环通知类型（Task 13）。
NOTIFICATION_REVIEWER_MISSING = "reviewer_missing"
NOTIFICATION_COMMENT = "comment"
NOTIFICATION_REPLY = "reply"
# 批量委派聚合摘要通知类型（Task 11，按 delegation_batch_id + recipient 聚合）。
NOTIFICATION_DELEGATION_BATCH_SUMMARY = "delegation_batch_summary"

# 前后端必须完全一致的规范集合（顺序无关；guard 比较集合相等）。
PROCEDURE_NOTIFICATION_TYPES: tuple[str, ...] = (
    NOTIFICATION_ASSIGNED,
    NOTIFICATION_REASSIGNED,
    NOTIFICATION_SUBMITTED,
    NOTIFICATION_CHANGES_REQUESTED,
    NOTIFICATION_REVIEWED,
    NOTIFICATION_REVIEWER_MISSING,
    NOTIFICATION_COMMENT,
    NOTIFICATION_REPLY,
    NOTIFICATION_DELEGATION_BATCH_SUMMARY,
)
