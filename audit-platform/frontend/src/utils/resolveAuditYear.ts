/**
 * 全平台审计年度解析（与后端 project_audit_year 规则对齐）
 *
 * 优先级：显式 prop > render-config > 路由 query > store.auditYear > store.year
 *         > audit_period_end > audit_period_start > 项目名 _YYYY 后缀 > 去年
 */

const MIN_YEAR = 2000

export interface AuditYearSources {
  propYear?: unknown
  configYear?: unknown
  routeYear?: unknown
  storeAuditYear?: number | null
  storeYear?: number | null
  periodEnd?: string | null
  periodStart?: string | null
  projectName?: string | null
}

export function parseAuditYear(value: unknown): number | null {
  const n = Number(value)
  return Number.isFinite(n) && n > MIN_YEAR ? n : null
}

/**
 * 跳转查询串里的年度：有效才带。年度缺失时不带（`String(null)` 会写成 `year=null`），
 * 目标页按项目审计年度取 —— 不拿去年兜底（spec post-push-residual-defect-closure 6.5）。
 */
export function yearQuery(year: unknown): { year?: string } {
  const y = parseAuditYear(year)
  return y != null ? { year: String(y) } : {}
}

export function yearFromIsoDate(iso?: string | null): number | null {
  if (!iso || iso.length < 4) return null
  const y = parseInt(iso.slice(0, 4), 10)
  return y > MIN_YEAR ? y : null
}

export function yearFromProjectName(name?: string | null): number | null {
  if (!name) return null
  const m = name.match(/_(\d{4})$/)
  return m ? parseAuditYear(m[1]) : null
}

/** 从项目 API 响应解析审计年度（与后端 resolve_project_audit_year 对齐） */
export function resolveAuditYearFromProject(project: {
  audit_year?: unknown
  audit_period_end?: string | null
  audit_period_start?: string | null
  name?: string | null
} | null | undefined): number | null {
  if (!project) return null
  return (
    parseAuditYear(project.audit_year)
    ?? yearFromIsoDate(project.audit_period_end)
    ?? yearFromIsoDate(project.audit_period_start)
    ?? yearFromProjectName(project.name)
  )
}

/**
 * 多来源合并为审计年度；全部缺失返回 null（不按日历猜）。
 * 写请求一律用它（或 `useProjectAuditYear`）：取不到就不发、提示先填年度（spec audit-year-calendar-fallback-ratchet R0 / R3）。
 */
export function resolveAuditYearOrNull(sources: AuditYearSources): number | null {
  const candidates: unknown[] = [
    sources.propYear,
    sources.configYear,
    sources.routeYear,
    sources.storeAuditYear,
    sources.storeYear,
    yearFromIsoDate(sources.periodEnd),
    yearFromIsoDate(sources.periodStart),
    yearFromProjectName(sources.projectName),
  ]
  for (const c of candidates) {
    const y = parseAuditYear(c)
    if (y) return y
  }
  return null
}

/**
 * 多来源合并为最终查询年度；全部缺失返回 null。
 * 调用方须处理 null：写请求不发 + 提示，读请求显示空态。
 * （spec audit-year-calendar-fallback-ratchet R3.1：删去年兜底，选方案 B）
 */
export function resolveEffectiveAuditYear(sources: AuditYearSources): number | null {
  return resolveAuditYearOrNull(sources)
}
