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
