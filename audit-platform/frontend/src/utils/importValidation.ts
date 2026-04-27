export interface ImportValidationItemLike {
  file?: string | null
  sheet?: string | null
  message?: string | null
  severity?: string | null
  blocking?: boolean
}

export interface ImportValidationSummaryLike {
  total?: number
  blocking_count?: number
  has_blocking?: boolean
  by_severity?: Record<string, number>
}

export interface ResolvedImportValidationSummary {
  total: number
  fatal: number
  error: number
  warning: number
  info: number
  blocking_count: number
  has_blocking: boolean
}

export interface GroupedImportValidationItems<T> {
  fatal: T[]
  error: T[]
  warning: T[]
  info: T[]
}

export type ImportValidationAlertType = 'success' | 'warning' | 'info'

export interface ImportSuccessSummaryEntry {
  key: string
  label: string
  count: number
}

export function resolveImportValidationSummary<T extends ImportValidationItemLike>(
  items: T[] | null | undefined,
  backendSummary?: ImportValidationSummaryLike | null,
): ResolvedImportValidationSummary {
  if (backendSummary) {
    return {
      total: backendSummary.total ?? 0,
      fatal: backendSummary.by_severity?.fatal ?? 0,
      error: backendSummary.by_severity?.error ?? 0,
      warning: backendSummary.by_severity?.warning ?? 0,
      info: backendSummary.by_severity?.info ?? 0,
      blocking_count: backendSummary.blocking_count ?? 0,
      has_blocking: backendSummary.has_blocking ?? (backendSummary.blocking_count ?? 0) > 0,
    }
  }

  const summary: ResolvedImportValidationSummary = {
    total: 0,
    fatal: 0,
    error: 0,
    warning: 0,
    info: 0,
    blocking_count: 0,
    has_blocking: false,
  }

  for (const item of items || []) {
    summary.total += 1
    const severity = String(item.severity || 'info').toLowerCase()
    if (severity === 'fatal') summary.fatal += 1
    else if (severity === 'error') summary.error += 1
    else if (severity === 'warning') summary.warning += 1
    else summary.info += 1
    if (item.blocking) summary.blocking_count += 1
  }

  summary.has_blocking = summary.blocking_count > 0
  return summary
}

export function groupImportValidationItems<T extends ImportValidationItemLike>(
  items: T[] | null | undefined,
): GroupedImportValidationItems<T> {
  const grouped: GroupedImportValidationItems<T> = {
    fatal: [],
    error: [],
    warning: [],
    info: [],
  }

  for (const item of items || []) {
    const severity = String(item.severity || 'info').toLowerCase()
    if (severity === 'fatal') grouped.fatal.push(item)
    else if (severity === 'error') grouped.error.push(item)
    else if (severity === 'warning') grouped.warning.push(item)
    else grouped.info.push(item)
  }

  return grouped
}

export function getImportValidationAlertType(
  summary: ResolvedImportValidationSummary,
): ImportValidationAlertType {
  if (summary.has_blocking) return 'warning'
  if (summary.warning > 0) return 'info'
  return 'success'
}

export function getImportValidationSummaryTitle(
  summary: ResolvedImportValidationSummary,
): string {
  if (summary.has_blocking) {
    return '导入已完成，但存在需要处理的校验问题'
  }
  if (summary.warning > 0) {
    return '导入已完成，存在可继续关注的警告信息'
  }
  return '导入校验通过'
}

export function extractImportValidationMessage<T extends ImportValidationItemLike>(
  items: T[] | null | undefined,
  fallback: string,
): string {
  if (!items?.length) return fallback
  const prioritized = items
    .filter(item => item.blocking || item.severity === 'fatal' || item.severity === 'error')
  const source = prioritized.length ? prioritized : items
  return source
    .slice(0, 3)
    .map((item) => {
      const location = [item.file, item.sheet].filter(Boolean).join(' / ')
      return location ? `${location}：${item.message || fallback}` : (item.message || fallback)
    })
    .join('；') || fallback
}

export function buildImportSuccessMessage(
  baseMessage: string,
  entries?: ImportSuccessSummaryEntry[] | null,
): string {
  const parts = (entries || [])
    .filter(entry => entry.count > 0)
    .map(entry => `${entry.label} ${entry.count.toLocaleString()} 条`)
  return parts.length ? `${baseMessage}，同时导入 ${parts.join('、')}` : baseMessage
}
