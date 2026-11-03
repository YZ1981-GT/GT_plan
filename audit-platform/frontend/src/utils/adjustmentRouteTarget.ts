export type AdjustmentRouteTarget =
  | { kind: 'focus'; entryGroupId: string }
  | { kind: 'account'; accountCode: string }
  | { kind: 'impact'; entryGroupId: string }
  | { kind: 'collaboration'; entryGroupId: string }

export interface AdjustmentRouteOptions {
  year?: number | string | null
  status?: string | null
}

export interface AdjustmentRouteLocation {
  name: 'Adjustments'
  params: { projectId: string }
  query?: Record<string, string>
}

export interface ParsedAdjustmentRouteTarget {
  focus: string
  account: string
  impact: string
  group: string
  status: string
  year: number | null
  legacyFocus: 'id' | 'highlight' | null
}

type QueryLike = Record<string, unknown>

function firstText(value: unknown): string {
  const candidates = Array.isArray(value) ? value : [value]
  for (const candidate of candidates) {
    if (typeof candidate === 'string' && candidate.trim()) return candidate.trim()
  }
  return ''
}

function yearText(value: AdjustmentRouteOptions['year']): string {
  if (value === null || value === undefined || value === '') return ''
  const year = Number(value)
  return Number.isInteger(year) && year > 2000 ? String(year) : ''
}
function targetQuery(target?: AdjustmentRouteTarget | null): Record<string, string> {
  if (!target) return {}
  if (target.kind === 'focus') return { focus: target.entryGroupId.trim() }
  if (target.kind === 'account') return { account: target.accountCode.trim() }
  if (target.kind === 'impact') return { impact: target.entryGroupId.trim() }
  return { group: target.entryGroupId.trim() }
}

/** 调整大厅唯一的命名路由构造器。新发送方不得自行拼 query。 */
export function buildAdjustmentRouteTarget(
  projectId: string,
  target?: AdjustmentRouteTarget | null,
  options: AdjustmentRouteOptions = {},
): AdjustmentRouteLocation {
  const query = targetQuery(target)
  for (const key of Object.keys(query)) {
    if (!query[key]) delete query[key]
  }
  const year = yearText(options.year)
  if (year) query.year = year
  if (target?.kind === 'focus' && options.status?.trim()) query.status = options.status.trim()
  return {
    name: 'Adjustments',
    params: { projectId: projectId.trim() },
    ...(Object.keys(query).length ? { query } : {}),
  }
}

/** 供通知和 LinkageContract 等必须返回字符串的调用方使用。 */
export function buildAdjustmentRouteHref(
  projectId: string,
  target?: AdjustmentRouteTarget | null,
  options: AdjustmentRouteOptions = {},
): string {
  const location = buildAdjustmentRouteTarget(projectId, target, options)
  const query = new URLSearchParams(location.query || {}).toString()
  const path = `/projects/${encodeURIComponent(location.params.projectId)}/adjustments`
  return query ? `${path}?${query}` : path
}

/**
 * 调整大厅唯一的 query 解析器。
 * `id`、`highlight` 只读兼容；所有新地址只写 focus/account/impact/group。
 */
export function parseAdjustmentRouteTarget(query: QueryLike): ParsedAdjustmentRouteTarget {
  const canonicalFocus = firstText(query.focus)
  const legacyId = canonicalFocus ? '' : firstText(query.id)
  const legacyHighlight = canonicalFocus || legacyId ? '' : firstText(query.highlight)
  const rawYear = firstText(query.year)
  const parsedYear = Number(rawYear)
  return {
    focus: canonicalFocus || legacyId || legacyHighlight,
    account: firstText(query.account),
    impact: firstText(query.impact),
    group: firstText(query.group),
    status: firstText(query.status),
    year: Number.isInteger(parsedYear) && parsedYear > 2000 ? parsedYear : null,
    legacyFocus: legacyId ? 'id' : (legacyHighlight ? 'highlight' : null),
  }
}
