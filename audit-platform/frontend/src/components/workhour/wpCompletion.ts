/**
 * 底稿完成度展示工具 — 复用于 WorkHourApprovalTable / 其他工时审批视图
 *
 * Validates: proposal-remaining-18 task 0.2 (M-5)
 *
 * - rate=null/undefined → "—"（用户在本项目无任何分配底稿）
 * - rate ∈ [0, 100]：el-progress 渲染，按阈值上色
 *
 * 阈值（与底稿进度列保持一致）：
 *   < 30 红 (#F56C6C) / < 70 橙 (#E6A23C) / 其余 绿 (#67C23A)
 */

const COLOR_DANGER = '#F56C6C'
const COLOR_WARNING = '#E6A23C'
const COLOR_SUCCESS = '#67C23A'

export function completionColor(rate: number): string {
  if (rate < 30) return COLOR_DANGER
  if (rate < 70) return COLOR_WARNING
  return COLOR_SUCCESS
}

export function formatCompletion(rate: number): string {
  return `${rate.toFixed(0)}%`
}

export function hasCompletionRate(value: unknown): value is number {
  return typeof value === 'number' && !Number.isNaN(value)
}
