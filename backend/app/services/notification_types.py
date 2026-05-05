"""通知类型统一字典 — Refinement Round 1 创建

跨轮约束第 1 条：新增通知类型时同步更新本文件 + 前端 notificationTypes.ts。
R2+ 只向本文件追加常量，不重复新建。

本轮收口 Round 1 用到的类型：
  - archive_done: 归档完成
  - signature_ready: 签字就绪（轮到某人签字）
  - gate_alert: 门禁检查告警
  - report_finalized: 审计报告终稿（签字状态机联动）
"""

from __future__ import annotations

# ── 通知类型常量 ──────────────────────────────────────────────

ARCHIVE_DONE = "archive_done"
SIGNATURE_READY = "signature_ready"
GATE_ALERT = "gate_alert"
REPORT_FINALIZED = "report_finalized"

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
}

# ── 所有通知类型列表（便于校验） ──────────────────────────────────

ALL_NOTIFICATION_TYPES = [
    ARCHIVE_DONE,
    SIGNATURE_READY,
    GATE_ALERT,
    REPORT_FINALIZED,
]
