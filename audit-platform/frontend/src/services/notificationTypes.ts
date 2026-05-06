/**
 * 通知类型统一字典 — 前端同步
 *
 * 跨轮约束第 1 条：与后端 notification_types.py 保持同步。
 * R2+ 只向本文件追加常量，不重复新建。
 *
 * 本轮收口 Round 1 用到的类型：
 *   - archive_done: 归档完成
 *   - signature_ready: 签字就绪
 *   - gate_alert: 门禁检查告警
 *   - report_finalized: 审计报告终稿
 */

// ── 通知类型常量 ──────────────────────────────────────────────

export const NOTIFICATION_TYPES = {
  ARCHIVE_DONE: 'archive_done',
  SIGNATURE_READY: 'signature_ready',
  GATE_ALERT: 'gate_alert',
  REPORT_FINALIZED: 'report_finalized',
  // Batch 3-2: 审计日志写入失败告警（原 worker 误用 GATE_ALERT 导致跳转错误）
  AUDIT_LOG_WRITE_FAILED: 'audit_log_write_failed',
  // Round 2: 项目经理视角
  WORKPAPER_REMINDER: 'workpaper_reminder',
  WORKHOUR_APPROVED: 'workhour_approved',
  WORKHOUR_REJECTED: 'workhour_rejected',
  ASSIGNMENT_CREATED: 'assignment_created',
  COMMITMENT_DUE: 'commitment_due',
} as const

export type NotificationType = (typeof NOTIFICATION_TYPES)[keyof typeof NOTIFICATION_TYPES]

// ── 通知类型中文标签 ──────────────────────────────────────────

export const NOTIFICATION_LABELS: Record<NotificationType, string> = {
  [NOTIFICATION_TYPES.ARCHIVE_DONE]: '归档完成',
  [NOTIFICATION_TYPES.SIGNATURE_READY]: '签字就绪',
  [NOTIFICATION_TYPES.GATE_ALERT]: '门禁告警',
  [NOTIFICATION_TYPES.REPORT_FINALIZED]: '报告终稿',
  [NOTIFICATION_TYPES.AUDIT_LOG_WRITE_FAILED]: '审计日志告警',
  // Round 2
  [NOTIFICATION_TYPES.WORKPAPER_REMINDER]: '底稿催办',
  [NOTIFICATION_TYPES.WORKHOUR_APPROVED]: '工时已批准',
  [NOTIFICATION_TYPES.WORKHOUR_REJECTED]: '工时已退回',
  [NOTIFICATION_TYPES.ASSIGNMENT_CREATED]: '新委派',
  [NOTIFICATION_TYPES.COMMITMENT_DUE]: '承诺到期',
}

// ── 跳转规则 ──────────────────────────────────────────────────
// 每个通知类型对应一个路由生成函数，接收 metadata 返回前端路由路径

export const NOTIFICATION_JUMP_ROUTES: Record<string, (meta: Record<string, any>) => string> = {
  [NOTIFICATION_TYPES.ARCHIVE_DONE]: (m) =>
    `/projects/${m.project_id}/archive/jobs/${m.job_id}`,

  [NOTIFICATION_TYPES.SIGNATURE_READY]: (m) =>
    `/projects/${m.project_id}/signatures`,

  [NOTIFICATION_TYPES.GATE_ALERT]: (m) =>
    `/projects/${m.project_id}/gate-readiness`,

  [NOTIFICATION_TYPES.REPORT_FINALIZED]: (m) =>
    `/projects/${m.project_id}/report`,

  // Batch 3-2: 审计日志链校验页（全局，无项目上下文）
  [NOTIFICATION_TYPES.AUDIT_LOG_WRITE_FAILED]: () =>
    `/audit-logs/verify-chain`,

  // Round 2: 项目经理视角
  [NOTIFICATION_TYPES.WORKPAPER_REMINDER]: (m) =>
    `/projects/${m.project_id}/workpapers?assigned=me`,

  [NOTIFICATION_TYPES.WORKHOUR_APPROVED]: () =>
    `/work-hours`,

  [NOTIFICATION_TYPES.WORKHOUR_REJECTED]: () =>
    `/work-hours`,

  [NOTIFICATION_TYPES.ASSIGNMENT_CREATED]: (m) =>
    `/projects/${m.project_id}/workpapers?assigned=me`,

  [NOTIFICATION_TYPES.COMMITMENT_DUE]: (m) =>
    `/projects/${m.project_id}/communications`,
}

/**
 * 根据通知类型和元数据获取跳转路由
 * @param type 通知类型
 * @param metadata 通知元数据
 * @returns 路由路径，无匹配规则时返回 null
 */
export function getNotificationJumpRoute(
  type: string,
  metadata: Record<string, any> | null | undefined,
): string | null {
  if (!metadata) return null
  const routeGenerator = NOTIFICATION_JUMP_ROUTES[type]
  if (!routeGenerator) return null
  try {
    return routeGenerator(metadata)
  } catch {
    return null
  }
}
