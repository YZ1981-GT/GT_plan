"""通知类型统一字典 — Refinement Round 1 创建

跨轮约束第 1 条：新增通知类型时同步更新本文件 + 前端 notificationTypes.ts。
R2+ 只向本文件追加常量，不重复新建。

本轮收口 Round 1 用到的类型：
  - archive_done: 归档完成
  - signature_ready: 签字就绪（轮到某人签字）
  - gate_alert: 门禁检查告警
  - report_finalized: 审计报告终稿（签字状态机联动）
  - audit_log_write_failed: 审计日志写入失败告警（Batch 3-2 新增）
"""

from __future__ import annotations

# ── 通知类型常量 ──────────────────────────────────────────────

ARCHIVE_DONE = "archive_done"
SIGNATURE_READY = "signature_ready"
GATE_ALERT = "gate_alert"
REPORT_FINALIZED = "report_finalized"
# Batch 3-2: 审计日志写入失败 — 原先复用 GATE_ALERT 导致跳转到 gate-readiness
# 页面找不到对应项目，现独立为一种类型，跳转到审计日志链校验页
AUDIT_LOG_WRITE_FAILED = "audit_log_write_failed"

# ── Round 2 新增（项目经理视角） ─────────────────────────────────
WORKPAPER_REMINDER = "workpaper_reminder"
WORKHOUR_APPROVED = "workhour_approved"
WORKHOUR_REJECTED = "workhour_rejected"
ASSIGNMENT_CREATED = "assignment_created"
COMMITMENT_DUE = "commitment_due"
BUDGET_ALERT_80 = "budget_alert_80"
BUDGET_OVERRUN = "budget_overrun"
HANDOVER_RECEIVED = "handover_received"

# ── 通知元数据字典 ──────────────────────────────────────────────
# 每个类型对应 title_template / content_template / jump_route
# title_template 和 content_template 支持 Python str.format() 占位符
# jump_route 是前端路由模板，{xxx} 由 metadata 字段填充

NOTIFICATION_META: dict[str, dict[str, str]] = {
    ARCHIVE_DONE: {
        "title_template": "项目归档完成",
        "content_template": "项目「{project_name}」已成功归档，归档作业 ID: {job_id}",
        "jump_route": "/projects/{project_id}/archive/jobs/{job_id}",
    },
    SIGNATURE_READY: {
        "title_template": "签字就绪",
        "content_template": "项目「{project_name}」已轮到您签字（第 {order} 级），请尽快处理",
        "jump_route": "/projects/{project_id}/signatures",
    },
    GATE_ALERT: {
        "title_template": "门禁检查告警",
        "content_template": "项目「{project_name}」的 {gate_type} 门禁检查发现 {finding_count} 项问题",
        "jump_route": "/projects/{project_id}/gate-readiness",
    },
    REPORT_FINALIZED: {
        "title_template": "审计报告终稿",
        "content_template": "项目「{project_name}」的审计报告已定稿，所有签字已完成",
        "jump_route": "/projects/{project_id}/report",
    },
    # Batch 3-2: 审计日志写入失败告警
    # jump_route 固定到全局审计日志链校验入口（无项目上下文）
    AUDIT_LOG_WRITE_FAILED: {
        "title_template": "审计日志写入失败告警",
        "content_template": "审计日志 writer 连续失败 {retry_count} 次，{lost_count} 条日志可能丢失",
        "jump_route": "/audit-logs/verify-chain",
    },
    # ── Round 2 新增 ──
    WORKPAPER_REMINDER: {
        "title_template": "底稿催办提醒",
        "content_template": "您编制的底稿 {wp_code} {wp_name} 已创建 {days} 天尚未完成，请尽快推进",
        "jump_route": "/projects/{project_id}/workpapers?assigned=me",
    },
    WORKHOUR_APPROVED: {
        "title_template": "工时已批准",
        "content_template": "您 {date} 提交的 {hours} 小时工时已被批准",
        "jump_route": "/work-hours",
    },
    WORKHOUR_REJECTED: {
        "title_template": "工时已退回",
        "content_template": "您 {date} 提交的 {hours} 小时工时已被退回，原因：{reason}",
        "jump_route": "/work-hours",
    },
    ASSIGNMENT_CREATED: {
        "title_template": "新委派通知",
        "content_template": "项目「{project_name}」的底稿 {wp_code} 已委派给您，请及时处理",
        "jump_route": "/projects/{project_id}/workpapers?assigned=me",
    },
    COMMITMENT_DUE: {
        "title_template": "客户承诺到期提醒",
        "content_template": "项目「{project_name}」的客户承诺「{commitment_content}」将于 {due_date} 到期",
        "jump_route": "/projects/{project_id}/communications",
    },
    BUDGET_ALERT_80: {
        "title_template": "项目预算预警（80%）",
        "content_template": "项目「{project_name}」工时已使用 {utilization_pct}%，请关注预算控制",
        "jump_route": "/projects/{project_id}/cost-overview",
    },
    BUDGET_OVERRUN: {
        "title_template": "项目预算超支",
        "content_template": "项目「{project_name}」工时已超出预算（{utilization_pct}%），请立即处理",
        "jump_route": "/projects/{project_id}/cost-overview",
    },
    HANDOVER_RECEIVED: {
        "title_template": "工作交接通知",
        "content_template": "有 {workpapers_moved} 张底稿、{issues_moved} 张工单、{assignments_moved} 个项目委派已转交给您",
        "jump_route": "/staff-management",
    },
}

# ── 所有通知类型列表（便于校验） ──────────────────────────────────

ALL_NOTIFICATION_TYPES = [
    ARCHIVE_DONE,
    SIGNATURE_READY,
    GATE_ALERT,
    REPORT_FINALIZED,
    AUDIT_LOG_WRITE_FAILED,
    # Round 2
    WORKPAPER_REMINDER,
    WORKHOUR_APPROVED,
    WORKHOUR_REJECTED,
    ASSIGNMENT_CREATED,
    COMMITMENT_DUE,
    BUDGET_ALERT_80,
    BUDGET_OVERRUN,
    HANDOVER_RECEIVED,
]


# ── 必需 metadata 字段校验 ──────────────────────────────────────────

import logging as _logging

_logger = _logging.getLogger(__name__)

REQUIRED_METADATA_FIELDS: dict[str, list[str]] = {
    ARCHIVE_DONE: ["object_type", "object_id", "project_name", "job_id"],
    SIGNATURE_READY: ["object_type", "object_id", "project_name", "order"],
    GATE_ALERT: ["object_type", "object_id", "project_name", "gate_type", "finding_count"],
    REPORT_FINALIZED: ["object_type", "object_id", "project_name"],
    AUDIT_LOG_WRITE_FAILED: ["retry_count", "lost_count"],
    WORKPAPER_REMINDER: ["object_type", "object_id", "project_id", "wp_code", "wp_name", "days"],
    WORKHOUR_APPROVED: ["date", "hours"],
    WORKHOUR_REJECTED: ["date", "hours", "reason"],
    ASSIGNMENT_CREATED: ["object_type", "object_id"],
    COMMITMENT_DUE: ["object_type", "object_id", "project_name", "commitment_content", "due_date"],
    BUDGET_ALERT_80: ["object_type", "object_id", "project_id", "project_name", "threshold", "utilization_pct"],
    BUDGET_OVERRUN: ["object_type", "object_id", "project_id", "project_name", "threshold", "utilization_pct"],
    HANDOVER_RECEIVED: ["workpapers_moved", "issues_moved", "assignments_moved"],
}


def validate_metadata(notification_type: str, metadata: dict | None) -> bool:
    """校验通知 metadata 是否包含必需字段。

    缺失字段时记录 warning 日志，返回 False；全部满足返回 True。
    未注册的 notification_type 直接返回 True（不阻断）。
    """
    required = REQUIRED_METADATA_FIELDS.get(notification_type)
    if required is None:
        return True
    if metadata is None:
        _logger.warning(
            "[NOTIFICATION] type=%s metadata is None, required fields: %s",
            notification_type, required,
        )
        return False
    missing = [f for f in required if f not in metadata]
    if missing:
        _logger.warning(
            "[NOTIFICATION] type=%s metadata missing fields: %s",
            notification_type, missing,
        )
        return False
    return True
