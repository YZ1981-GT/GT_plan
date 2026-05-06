/**
 * statusMaps.ts — 状态标签映射集中管理 [R6.2]
 *
 * 每个映射对象：{ [statusValue]: { label: string; type: ElTagType } }
 * 配合 GtStatusTag 组件使用，消除各模块重复的 statusTagType/statusLabel 函数
 */

export type ElTagType = 'success' | 'warning' | 'danger' | 'info' | 'primary'

export interface StatusEntry {
  label: string
  type: ElTagType
}

export type StatusMap = Record<string, StatusEntry>

// ── 底稿状态（WorkpaperList / WorkpaperEditor）──
export const WP_STATUS: StatusMap = {
  not_started:           { label: '未开始',     type: 'info' },
  in_progress:           { label: '编制中',     type: 'warning' },
  draft:                 { label: '草稿',       type: 'warning' },
  draft_complete:        { label: '初稿完成',   type: 'primary' },
  edit_complete:         { label: '编制完成',   type: 'primary' },
  under_review:          { label: '复核中',     type: 'primary' },
  revision_required:     { label: '退回修改',   type: 'danger' },
  review_passed:         { label: '复核通过',   type: 'success' },
  review_level1_passed:  { label: '一级复核通过', type: 'success' },
  review_level2_passed:  { label: '二级复核通过', type: 'success' },
  archived:              { label: '已归档',     type: 'info' },
}

// ── 底稿复核状态 ──
export const WP_REVIEW_STATUS: StatusMap = {
  not_submitted:      { label: '未提交',     type: 'info' },
  pending_level1:     { label: '待一级复核', type: 'warning' },
  level1_in_progress: { label: '一级复核中', type: 'warning' },
  level1_passed:      { label: '一级通过',   type: 'success' },
  level1_rejected:    { label: '一级退回',   type: 'danger' },
  pending_level2:     { label: '待二级复核', type: 'warning' },
  level2_in_progress: { label: '二级复核中', type: 'warning' },
  level2_passed:      { label: '二级通过',   type: 'success' },
  level2_rejected:    { label: '二级退回',   type: 'danger' },
}

// ── 调整分录状态（Adjustments / TrialBalance）──
export const ADJUSTMENT_STATUS: StatusMap = {
  draft:          { label: '草稿',   type: 'info' },
  pending_review: { label: '待复核', type: 'warning' },
  approved:       { label: '已批准', type: 'success' },
  rejected:       { label: '已驳回', type: 'danger' },
}

// ── 报告状态（AuditReportEditor）──
export const REPORT_STATUS: StatusMap = {
  draft:  { label: '草稿',   type: 'info' },
  review: { label: '复核中', type: 'warning' },
  eqcr_approved: { label: 'EQCR已锁定', type: 'danger' },
  final:  { label: '已定稿', type: 'success' },
}

// ── 模板状态（TemplateManager）──
export const TEMPLATE_STATUS: StatusMap = {
  draft:      { label: '草稿',   type: 'info' },
  published:  { label: '已发布', type: 'success' },
  deprecated: { label: '已废弃', type: 'danger' },
}

// ── 项目状态（Projects / Dashboard / ConsolidationHub）──
export const PROJECT_STATUS: StatusMap = {
  created:    { label: '已创建', type: 'info' },
  planning:   { label: '计划中', type: 'warning' },
  execution:  { label: '执行中', type: 'primary' },
  completion: { label: '已完成', type: 'success' },
  reporting:  { label: '报告',   type: 'primary' },
  archived:   { label: '已归档', type: 'info' },
}

// ── 问题工单状态（IssueTicketList）──
export const ISSUE_STATUS: StatusMap = {
  open:             { label: '待处理', type: 'info' },
  in_fix:           { label: '修复中', type: 'warning' },
  pending_recheck:  { label: '待复验', type: 'warning' },
  closed:           { label: '已关闭', type: 'success' },
  rejected:         { label: '已驳回', type: 'danger' },
}

// ── PDF 导出任务状态（PDFExportPanel）──
export const PDF_TASK_STATUS: StatusMap = {
  queued:     { label: '排队中', type: 'info' },
  processing: { label: '处理中', type: 'warning' },
  completed:  { label: '已完成', type: 'success' },
  failed:     { label: '失败',   type: 'danger' },
}

// ── 辅助函数 ──

/** 获取状态中文标签，未匹配时返回原始值 */
export function getStatusLabel(map: StatusMap, status: string | undefined | null): string {
  if (!status) return '—'
  return map[status]?.label ?? status
}

/** 获取 el-tag type，未匹配时返回 'info' */
export function getStatusType(map: StatusMap, status: string | undefined | null): ElTagType {
  if (!status) return 'info'
  return map[status]?.type ?? 'info'
}
