import type { ReportConsistencyCheck, ReportConsistencyCheckItem } from './auditPlatformApi'

export const REPORT_CHECK_STATUSES = ['passed', 'failed', 'not_executed', 'not_applicable', 'error'] as const
export type ReportCheckStatus = typeof REPORT_CHECK_STATUSES[number]
export const REPORT_CHECK_LABELS: Record<ReportCheckStatus, string> = {
  passed: '通过', failed: '未通过', not_executed: '未执行', not_applicable: '不适用', error: '错误',
}
const severityLabels: Record<string, string> = {
  info: '提示', warning: '警告', error: '错误', blocking: '阻断', critical: '严重',
  high: '高', medium: '中', low: '低',
}
const own = (value: object, key: PropertyKey) => Object.prototype.hasOwnProperty.call(value, key)
const text = (value: unknown) => typeof value === 'string' ? value.trim() : ''

/** 自有 status 即为权威；坏状态不得删除后退到 passed。 */
export function getReportCheckPresentation(check: Partial<ReportConsistencyCheckItem>) {
  let status: ReportCheckStatus
  let invalidReason = ''
  if (own(check, 'status')) {
    if (REPORT_CHECK_STATUSES.includes(check.status as ReportCheckStatus)) {
      status = check.status as ReportCheckStatus
    } else {
      status = 'error'
      invalidReason = check.status == null || check.status === ''
        ? '检查状态缺失或为空' : `未知检查状态：${String(check.status)}`
    }
  } else if (typeof check.passed === 'boolean') {
    status = check.passed ? 'passed' : 'failed'
  } else {
    status = 'error'
    invalidReason = '检查状态缺失或为空'
  }
  const reason = [...new Set([invalidReason, text(check.reason), text(check.message)].filter(Boolean))].join('；')
  const severity = text(check.severity)
  return { status, label: REPORT_CHECK_LABELS[status], reason,
    severityLabel: severity ? severityLabels[severity] ?? `未识别：${severity}` : '—',
    isHint: severity === 'warning' || severity === 'info',
  }
}

export function hasReportCheckValue(value: unknown): value is number | string {
  return typeof value === 'number' ? Number.isFinite(value) : typeof value === 'string' && value.trim() !== ''
}
export function reportCheckValueText(value: unknown): string {
  return hasReportCheckValue(value) ? String(value) : '—'
}

export function getReportBalanceDetails(checks: ReportConsistencyCheckItem[] = []) {
  return checks.map(check => ({ ...check, presentation: getReportCheckPresentation(check) }))
}
export function getReportBalancePresentation(result: Partial<ReportConsistencyCheck> | null) {
  const checks = Array.isArray(result?.checks) ? result.checks : []
  const details = getReportBalanceDetails(checks)
  const counts = { passed: 0, failed: 0, not_executed: 0, not_applicable: 0, error: 0 }
  let hints = 0
  for (const { presentation } of details) {
    counts[presentation.status]++
    if (presentation.status === 'failed' && presentation.isHint) hints++
  }
  const blockingFailures = counts.failed - hints
  let status: 'unverified' | 'passed' | 'error' | 'warning' | 'hint' | 'not_applicable' | 'completed' = 'unverified'
  if (details.length) {
    if (counts.passed === details.length) status = 'passed'
    else if (counts.error) status = 'error'
    else if (blockingFailures) status = 'warning'
    else if (counts.failed) status = 'hint'
    else if (counts.not_executed) status = 'unverified'
    else if (counts.not_applicable === details.length) status = 'not_applicable'
    else status = 'completed'
  }
  const message = details.length
    ? `审核明细 ${details.length} 项：${REPORT_CHECK_STATUSES.map(key => `${REPORT_CHECK_LABELS[key]} ${counts[key]} 项`).join('，')}`
    : '未验证：暂无审核明细，汇总信息不能证明检查通过'
  return { status, message, checks, counts, details, blockingFailures, hints,
    failed_count: result?.failed_count, hint_count: result?.hint_count }
}
export type ReportBalanceResult = ReturnType<typeof getReportBalancePresentation>

/** 所有字段统一转义；0 是值，缺数不伪造为 0。 */
export function reportChecksToCsv(checks: ReportConsistencyCheckItem[]): string {
  const escape = (value: unknown) => `"${String(value ?? '').replace(/"/g, '""')}"`
  const header = ['结果', '审核项目', '期望值', '实际值', '差额', '类型', '公式/来源', '原因', '严重度']
  const rows = checks.map(check => {
    const presentation = getReportCheckPresentation(check)
    return [presentation.label, check.name, reportCheckValueText(check.expected),
      reportCheckValueText(check.actual), reportCheckValueText(check.diff), check.category_label,
      check.formula || check.source, presentation.reason, presentation.severityLabel]
  })
  return [header, ...rows].map(row => row.map(escape).join(',')).join('\r\n')
}
