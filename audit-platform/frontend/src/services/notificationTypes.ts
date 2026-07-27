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
  DELIVERABLE_APPROVAL_SUBMITTED: 'deliverable_approval_submitted',
  DELIVERABLE_APPROVAL_DONE: 'deliverable_approval_done',
  DELIVERABLE_APPROVAL_REJECTED: 'deliverable_approval_rejected',
  // ── procedure-delegation-notification / Task 11：程序行任务（与后端 notification_types.py 同步）──
  PROCEDURE_TASK_ASSIGNED: 'procedure_task.assigned',
  PROCEDURE_TASK_REASSIGNED: 'procedure_task.reassigned',
  PROCEDURE_TASK_SUBMITTED: 'procedure_task.submitted',
  PROCEDURE_TASK_CHANGES_REQUESTED: 'procedure_task.changes_requested',
  PROCEDURE_TASK_REVIEWED: 'procedure_task.reviewed',
  PROCEDURE_TASK_REVIEWER_MISSING: 'procedure_task.reviewer_missing',
  PROCEDURE_TASK_DELEGATION_BATCH: 'procedure_task.delegation_batch',
  PROCEDURE_REVIEW_MESSAGE: 'procedure_review_message',
  // ── adjustment-collaboration-and-propagation：调整分录协作接力（与后端 notification_types.py 同步）──
  ADJ_COLLAB_ASSIGNED: 'adjustment_collaboration.assigned',
  ADJ_COLLAB_CONTRIBUTED: 'adjustment_collaboration.contributed',
  ADJ_COLLAB_CONFIRMED: 'adjustment_collaboration.confirmed',
  ADJ_COLLAB_REJECTED: 'adjustment_collaboration.rejected',
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
  [NOTIFICATION_TYPES.DELIVERABLE_APPROVAL_SUBMITTED]: '交付物待审批',
  [NOTIFICATION_TYPES.DELIVERABLE_APPROVAL_DONE]: '交付物审批通过',
  [NOTIFICATION_TYPES.DELIVERABLE_APPROVAL_REJECTED]: '交付物审批驳回',
  // Task 11：程序行任务
  [NOTIFICATION_TYPES.PROCEDURE_TASK_ASSIGNED]: '程序任务已分配',
  [NOTIFICATION_TYPES.PROCEDURE_TASK_REASSIGNED]: '程序任务已转派',
  [NOTIFICATION_TYPES.PROCEDURE_TASK_SUBMITTED]: '程序任务待复核',
  [NOTIFICATION_TYPES.PROCEDURE_TASK_CHANGES_REQUESTED]: '程序任务被退回',
  [NOTIFICATION_TYPES.PROCEDURE_TASK_REVIEWED]: '程序任务已复核',
  [NOTIFICATION_TYPES.PROCEDURE_TASK_REVIEWER_MISSING]: '缺少操作复核人',
  [NOTIFICATION_TYPES.PROCEDURE_TASK_DELEGATION_BATCH]: '程序任务批量委派',
  [NOTIFICATION_TYPES.PROCEDURE_REVIEW_MESSAGE]: '程序复核消息',
  // 调整分录协作接力
  [NOTIFICATION_TYPES.ADJ_COLLAB_ASSIGNED]: '调整分录协作转派',
  [NOTIFICATION_TYPES.ADJ_COLLAB_CONTRIBUTED]: '协作补充已提交',
  [NOTIFICATION_TYPES.ADJ_COLLAB_CONFIRMED]: '协作已确认',
  [NOTIFICATION_TYPES.ADJ_COLLAB_REJECTED]: '协作已退回',
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

  [NOTIFICATION_TYPES.DELIVERABLE_APPROVAL_SUBMITTED]: (m) =>
    `/projects/${m.project_id}/deliverable-center`,
  [NOTIFICATION_TYPES.DELIVERABLE_APPROVAL_DONE]: (m) =>
    `/projects/${m.project_id}/deliverable-center`,
  [NOTIFICATION_TYPES.DELIVERABLE_APPROVAL_REJECTED]: (m) =>
    `/projects/${m.project_id}/deliverable-center`,

  // ── Task 11：程序行任务（metadata 驱动跳转，不解析中文 content）──
  // 有 wp_id → 底稿深链（携带 task_id/sheet_key/definition_key，控制台精确定位程序行）；
  // 无 wp_id（先委派后生成）→ 我的程序任务页（按批次/项目筛选）。已读/未读点击均可跳转。
  [NOTIFICATION_TYPES.PROCEDURE_TASK_ASSIGNED]: (m) => procedureTaskRoute(m),
  [NOTIFICATION_TYPES.PROCEDURE_TASK_REASSIGNED]: (m) => procedureTaskRoute(m),
  [NOTIFICATION_TYPES.PROCEDURE_TASK_SUBMITTED]: (m) => procedureTaskRoute(m),
  [NOTIFICATION_TYPES.PROCEDURE_TASK_CHANGES_REQUESTED]: (m) => procedureTaskRoute(m),
  [NOTIFICATION_TYPES.PROCEDURE_TASK_REVIEWED]: (m) => procedureTaskRoute(m),
  [NOTIFICATION_TYPES.PROCEDURE_REVIEW_MESSAGE]: (m) => procedureTaskRoute(m),
  // reviewer_missing / 批量委派摘要 → 我的程序任务页（批量摘要带 batch/project/filter）
  [NOTIFICATION_TYPES.PROCEDURE_TASK_REVIEWER_MISSING]: (m) => myProceduresRoute(m),
  [NOTIFICATION_TYPES.PROCEDURE_TASK_DELEGATION_BATCH]: (m) => myProceduresRoute(m),
  // ── 调整分录协作接力 → 集中调整页并按 ?group= 定位该分录组（打开协作对话框）──
  // metadata：project_id + object_id(entry_group_id)（后端 _notify 已补 project_id）。
  [NOTIFICATION_TYPES.ADJ_COLLAB_ASSIGNED]: (m) => adjCollabRoute(m),
  [NOTIFICATION_TYPES.ADJ_COLLAB_CONTRIBUTED]: (m) => adjCollabRoute(m),
  [NOTIFICATION_TYPES.ADJ_COLLAB_CONFIRMED]: (m) => adjCollabRoute(m),
  [NOTIFICATION_TYPES.ADJ_COLLAB_REJECTED]: (m) => adjCollabRoute(m),
  // #2: 新调整到达→点通知直达审定表带入
  'adjustment_sync_arrived': (m) => {
    if (!m.project_id) return ''
    const wpCodes = m.affected_wp_codes || []
    // 跳转到第一个受影响底稿的审定表（带 bringIn=true 打开带入弹窗）
    if (wpCodes.length > 0) {
      return `/projects/${m.project_id}/workpapers?view=workbench&highlight=${wpCodes[0]}`
    }
    return `/projects/${m.project_id}/adjustments`
  },
}

/** 调整分录协作通知 → 集中调整页 + ?group=（Adjustments.vue 消费定位/开协作对话框）。 */
function adjCollabRoute(m: Record<string, any>): string {
  if (!m.project_id) return ''
  return `/projects/${m.project_id}/adjustments${buildQuery({ group: m.object_id })}`
}

/** 拼接 query（跳过空值），返回 `?a=b&c=d` 或空串。 */
function buildQuery(params: Record<string, any>): string {
  const parts: string[] = []
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
  }
  return parts.length ? `?${parts.join('&')}` : ''
}

/** 我的程序任务页（批量摘要/reviewer_missing 落地，带 batch/project/filter）。 */
function myProceduresRoute(m: Record<string, any>): string {
  const filter = m.filter || {}
  return `/my-procedures${buildQuery({
    project_id: m.project_id || filter.project_id,
    batch_id: m.batch_id || filter.delegation_batch_id,
  })}`
}

/**
 * 单个程序行任务跳转：
 * - 有 wp_id → 底稿深链（GtAProgramConsole 按 sheet_key+definition_key 精确定位）。
 * - 无 wp_id（先委派后生成）→ 我的程序任务页（“底稿未生成”空态）。
 */
function procedureTaskRoute(m: Record<string, any>): string {
  if (m.wp_id && m.project_id) {
    return `/projects/${m.project_id}/workpapers${buildQuery({
      wp: m.wp_id,
      task_id: m.task_id,
      sheet_key: m.sheet_key,
      definition_key: m.definition_key,
    })}`
  }
  return myProceduresRoute(m)
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
