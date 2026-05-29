/**
 * statusEnum.ts — 全局状态字符串常量（R8-S2-11）
 *
 * 目的：消除代码中散落的 `=== 'draft'` / `=== 'final'` 等字符串比较
 * 用法：
 *   import { WP_STATUS } from '@/constants/statusEnum'
 *   if (status === WP_STATUS.DRAFT) { ... }
 *
 * 注意：这些常量值必须与后端枚举严格一致。修改前必须 grep 核对。
 */

/** 底稿状态（WpFileStatus） */
export const WP_STATUS = {
  DRAFT: 'draft',
  EDIT_COMPLETE: 'edit_complete',
  PENDING_REVIEW: 'pending_review',
  UNDER_REVIEW: 'under_review',
  REVIEW_PASSED: 'review_passed',
  REJECTED: 'rejected',
  ARCHIVED: 'archived',
} as const

/** 底稿复核状态（WpReviewStatus） */
export const WP_REVIEW_STATUS = {
  PENDING: 'pending',
  REVIEWING: 'reviewing',
  APPROVED: 'approved',
  REJECTED: 'rejected',
} as const

/** 审计报告状态（ReportStatus，R5 扩展） */
export const REPORT_STATUS = {
  DRAFT: 'draft',
  REVIEW: 'review',
  EQCR_APPROVED: 'eqcr_approved',
  FINAL: 'final',
} as const

/** 调整分录状态（AdjustmentReviewStatus） */
export const ADJUSTMENT_STATUS = {
  DRAFT: 'draft',
  PENDING_REVIEW: 'pending_review',
  APPROVED: 'approved',
  REJECTED: 'rejected',
} as const

/** 调整分录类型 */
export const ADJUSTMENT_TYPE = {
  AJE: 'aje',
  RJE: 'rje',
} as const

/** 项目状态（ProjectStatus） */
export const PROJECT_STATUS = {
  CREATED: 'created',
  PLANNING: 'planning',
  EXECUTION: 'execution',
  COMPLETION: 'completion',
  REPORTING: 'reporting',
  ARCHIVED: 'archived',
} as const

/** 问题单状态（IssueTicket.status） */
export const ISSUE_STATUS = {
  OPEN: 'open',
  IN_PROGRESS: 'in_progress',
  RESOLVED: 'resolved',
  CLOSED: 'closed',
  REJECTED: 'rejected',
} as const

/** 问题单严重度（IssueTicket.severity） */
export const ISSUE_SEVERITY = {
  BLOCKER: 'blocker',
  MAJOR: 'major',
  MINOR: 'minor',
  SUGGESTION: 'suggestion',
} as const

/** 工时状态（WorkHour.status） */
export const WORKHOUR_STATUS = {
  DRAFT: 'draft',
  PENDING: 'pending',
  APPROVED: 'approved',
  REJECTED: 'rejected',
  TRACKING: 'tracking',
} as const

/** 客户承诺状态（Project.wizard_state.communications[].commitments[].status） */
export const COMMITMENT_STATUS = {
  PENDING: 'pending',
  IN_PROGRESS: 'in_progress',
  DONE: 'done',
  CANCELLED: 'cancelled',
} as const

/** 模板状态（Template.status） */
export const TEMPLATE_STATUS = {
  DRAFT: 'draft',
  PUBLISHED: 'published',
  DEPRECATED: 'deprecated',
} as const

/** PDF 导出任务状态（PdfTask.status） */
export const PDF_TASK_STATUS = {
  PENDING: 'pending',
  PROCESSING: 'processing',
  SUCCESS: 'success',
  FAILED: 'failed',
} as const

/** 导出任务状态（ExportTask.status） */
export const EXPORT_TASK_STATUS = {
  QUEUED: 'queued',
  PROCESSING: 'processing',
  COMPLETED: 'completed',
  FAILED: 'failed',
} as const

/** QC 抽查结论（InspectionItem.verdict） */
export const QC_INSPECTION_VERDICT = {
  PENDING: 'pending',
  PASS: 'pass',
  FAIL: 'fail',
  NOT_APPLICABLE: 'not_applicable',
} as const

/** 归档范围（ArchiveOptions.scope） */
export const ARCHIVE_SCOPE = {
  FINAL: 'final',
  INTERIM: 'interim',
} as const

/** 归档作业状态（ArchiveJob.status） */
export const ARCHIVE_JOB_STATUS = {
  PENDING: 'pending',
  RUNNING: 'running',
  SUCCEEDED: 'succeeded',
  FAILED: 'failed',
  TIMED_OUT: 'timed_out',
  CANCELED: 'canceled',
} as const

/** EQCR 意见结论（EqcrOpinion.verdict） */
export const EQCR_VERDICT = {
  AGREE: 'agree',
  DISAGREE: 'disagree',
  NEED_MORE_EVIDENCE: 'need_more_evidence',
} as const

/** 账套导入作业状态 */
export const IMPORT_JOB_STATUS = {
  QUEUED: 'queued',
  RUNNING: 'running',
  COMPLETED: 'completed',
  FAILED: 'failed',
  TIMED_OUT: 'timed_out',
  CANCELED: 'canceled',
} as const

/** 批注状态（Annotation.status） */
export const ANNOTATION_STATUS = {
  PENDING: 'pending',
  REPLIED: 'replied',
  RESOLVED: 'resolved',
} as const

/** 独立性声明状态（IndependenceDeclaration.status） */
export const INDEPENDENCE_STATUS = {
  DRAFT: 'draft',
  SUBMITTED: 'submitted',
  APPROVED: 'approved',
  PENDING_CONFLICT_REVIEW: 'pending_conflict_review',
} as const

/** 问题单来源（IssueTicket.source） */
export const ISSUE_SOURCE = {
  REVIEW_COMMENT: 'review_comment',
  CONSISTENCY: 'consistency',
  AI: 'ai',
  REMINDER: 'reminder',
  CLIENT_COMMITMENT: 'client_commitment',
  PBC: 'pbc',
  CONFIRMATION: 'confirmation',
  QC_INSPECTION: 'qc_inspection',
  Q: 'Q',
  L2: 'L2',
  L3: 'L3',
} as const

/** 审计程序执行状态（Procedure.execution_status） */
export const PROCEDURE_EXECUTION_STATUS = {
  PENDING: 'pending',
  IN_PROGRESS: 'in_progress',
  COMPLETED: 'completed',
  REVIEWED: 'reviewed',
  NOT_APPLICABLE: 'not_applicable',
  SKIP: 'skip',
} as const

/** 已完成状态合集（跨多业务通用） */
export const COMPLETED_STATUSES: readonly string[] = [
  WP_STATUS.REVIEW_PASSED,
  WP_STATUS.ARCHIVED,
  REPORT_STATUS.FINAL,
  ISSUE_STATUS.CLOSED,
  ISSUE_STATUS.RESOLVED,
]

/** 通用类型导出（供 :type="WP_STATUS_TYPE"） */
export type WpStatus = typeof WP_STATUS[keyof typeof WP_STATUS]
export type ReportStatus = typeof REPORT_STATUS[keyof typeof REPORT_STATUS]
export type AdjustmentStatus = typeof ADJUSTMENT_STATUS[keyof typeof ADJUSTMENT_STATUS]
export type ProjectStatus = typeof PROJECT_STATUS[keyof typeof PROJECT_STATUS]
export type IssueStatus = typeof ISSUE_STATUS[keyof typeof ISSUE_STATUS]
export type IssueSeverity = typeof ISSUE_SEVERITY[keyof typeof ISSUE_SEVERITY]
export type AnnotationStatus = typeof ANNOTATION_STATUS[keyof typeof ANNOTATION_STATUS]
export type IndependenceStatus = typeof INDEPENDENCE_STATUS[keyof typeof INDEPENDENCE_STATUS]
export type IssueSource = typeof ISSUE_SOURCE[keyof typeof ISSUE_SOURCE]
export type ProcedureExecutionStatus = typeof PROCEDURE_EXECUTION_STATUS[keyof typeof PROCEDURE_EXECUTION_STATUS]

// ─── 中文 label 映射（Req 8.4.4 + Req 13 中文化前置） ───
// 与后端 system_dicts._DICTS 保持一致，前端 dictStore 优先从后端加载，
// 此处作为离线 fallback + 类型安全的单一真源。

export interface StatusDictEntry {
  label: string
  color: 'success' | 'warning' | 'danger' | 'info' | 'primary' | ''
}

/** 底稿状态中文映射 */
export const WP_STATUS_LABELS: Record<string, StatusDictEntry> = {
  not_started:          { label: '未开始',       color: 'info' },
  in_progress:          { label: '编制中',       color: 'warning' },
  draft:                { label: '草稿',         color: 'warning' },
  draft_complete:       { label: '初稿完成',     color: '' },
  edit_complete:        { label: '编制完成',     color: '' },
  pending_review:       { label: '待复核',       color: 'warning' },
  under_review:         { label: '复核中',       color: '' },
  revision_required:    { label: '退回修改',     color: 'danger' },
  review_passed:        { label: '复核通过',     color: 'success' },
  review_level1_passed: { label: '一级复核通过', color: 'success' },
  review_level2_passed: { label: '二级复核通过', color: 'success' },
  rejected:             { label: '已退回',       color: 'danger' },
  archived:             { label: '已归档',       color: 'info' },
}

/** 底稿复核状态中文映射 */
export const WP_REVIEW_STATUS_LABELS: Record<string, StatusDictEntry> = {
  not_submitted:      { label: '未提交',     color: 'info' },
  pending_level1:     { label: '待一级复核', color: 'warning' },
  level1_in_progress: { label: '一级复核中', color: 'warning' },
  level1_passed:      { label: '一级通过',   color: 'success' },
  level1_rejected:    { label: '一级退回',   color: 'danger' },
  pending_level2:     { label: '待二级复核', color: 'warning' },
  level2_in_progress: { label: '二级复核中', color: 'warning' },
  level2_passed:      { label: '二级通过',   color: 'success' },
  level2_rejected:    { label: '二级退回',   color: 'danger' },
}

/** 调整分录状态中文映射 */
export const ADJUSTMENT_STATUS_LABELS: Record<string, StatusDictEntry> = {
  draft:          { label: '草稿',   color: 'info' },
  pending_review: { label: '待复核', color: 'warning' },
  approved:       { label: '已批准', color: 'success' },
  rejected:       { label: '已驳回', color: 'danger' },
}

/** 报告状态中文映射 */
export const REPORT_STATUS_LABELS: Record<string, StatusDictEntry> = {
  draft:         { label: '草稿',      color: 'info' },
  review:        { label: '复核中',    color: 'warning' },
  eqcr_approved: { label: 'EQCR已锁', color: '' },
  final:         { label: '已定稿',    color: 'success' },
}

/** 项目状态中文映射 */
export const PROJECT_STATUS_LABELS: Record<string, StatusDictEntry> = {
  created:    { label: '已创建', color: 'info' },
  planning:   { label: '计划中', color: 'warning' },
  execution:  { label: '执行中', color: '' },
  completion: { label: '已完成', color: 'success' },
  reporting:  { label: '报告',   color: '' },
  archived:   { label: '已归档', color: 'info' },
}

/** 问题工单状态中文映射 */
export const ISSUE_STATUS_LABELS: Record<string, StatusDictEntry> = {
  open:            { label: '待处理', color: 'info' },
  in_fix:          { label: '修复中', color: 'warning' },
  pending_recheck: { label: '待复验', color: 'warning' },
  closed:          { label: '已关闭', color: 'success' },
  rejected:        { label: '已驳回', color: 'danger' },
}

/** 模板状态中文映射 */
export const TEMPLATE_STATUS_LABELS: Record<string, StatusDictEntry> = {
  draft:      { label: '草稿',   color: 'info' },
  published:  { label: '已发布', color: 'success' },
  deprecated: { label: '已废弃', color: 'danger' },
}

/** 工时状态中文映射 */
export const WORKHOUR_STATUS_LABELS: Record<string, StatusDictEntry> = {
  draft:     { label: '草稿',   color: 'info' },
  tracking:  { label: '计时中', color: 'warning' },
  confirmed: { label: '已确认', color: '' },
  approved:  { label: '已审批', color: 'success' },
  rejected:  { label: '已退回', color: 'danger' },
}

/** PDF 导出任务状态中文映射 */
export const PDF_TASK_STATUS_LABELS: Record<string, StatusDictEntry> = {
  queued:     { label: '排队中', color: 'info' },
  processing: { label: '处理中', color: 'warning' },
  completed:  { label: '已完成', color: 'success' },
  failed:     { label: '失败',   color: 'danger' },
}

/** 审计程序执行状态中文映射 */
export const PROCEDURE_STATUS_LABELS: Record<string, StatusDictEntry> = {
  pending:        { label: '未开始',   color: 'info' },
  in_progress:    { label: '进行中',   color: 'warning' },
  completed:      { label: '已完成',   color: 'success' },
  reviewed:       { label: '已复核',   color: 'success' },
  not_applicable: { label: '不适用',   color: '' },
  skip:           { label: '跳过',     color: '' },
}

/**
 * 全局状态字典聚合（与后端 /api/system/dicts 结构对齐）
 * dictStore 加载失败时可作为 fallback
 */
export const STATUS_DICT: Record<string, Record<string, StatusDictEntry>> = {
  wp_status: WP_STATUS_LABELS,
  wp_review_status: WP_REVIEW_STATUS_LABELS,
  adjustment_status: ADJUSTMENT_STATUS_LABELS,
  report_status: REPORT_STATUS_LABELS,
  project_status: PROJECT_STATUS_LABELS,
  issue_status: ISSUE_STATUS_LABELS,
  template_status: TEMPLATE_STATUS_LABELS,
  workhour_status: WORKHOUR_STATUS_LABELS,
  pdf_task_status: PDF_TASK_STATUS_LABELS,
  procedure_status: PROCEDURE_STATUS_LABELS,
}

/**
 * 通用 label 查询函数（dictStore 离线 fallback）
 * @param dictKey 字典键（如 'wp_status'）
 * @param value 状态值（如 'draft'）
 * @returns 中文 label，未找到时返回原值
 */
export function getStatusLabel(dictKey: string, value: string | null | undefined): string {
  if (!value) return '—'
  const dict = STATUS_DICT[dictKey]
  if (!dict) return value
  return dict[value]?.label ?? value
}

/**
 * 通用 color 查询函数（dictStore 离线 fallback）
 * @param dictKey 字典键
 * @param value 状态值
 * @returns el-tag type 值
 */
export function getStatusColor(dictKey: string, value: string | null | undefined): StatusDictEntry['color'] {
  if (!value) return 'info'
  const dict = STATUS_DICT[dictKey]
  if (!dict) return 'info'
  return dict[value]?.color ?? 'info'
}
