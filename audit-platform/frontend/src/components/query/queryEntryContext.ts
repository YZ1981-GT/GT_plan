/**
 * queryEntryContext.ts — 打开高级查询时的入口上下文（advanced-query-linkage-closure 任务 27，design §4.1；ADR-AQL-15；R10.1~R10.3、R10.5）
 *
 * 唯一映射处（三个纯函数，布局接线在任务 31）：
 * - `resolveQueryEntryContext(route)`：当前路由 → 项目、年度与预选数据源（试算表 / 报表 / 附注 / 调整分录 / 账簿查询 /
 *   辅助汇总 / 底稿编辑器各一个预选源）；
 * - `resolveTemplateLibrarySource(uri)`：模板库「📊 高级查询」按钮发的是模板口径的源 URI（AQ-38）：`report:<类型>` →
 *   `report_<类型>`；`note:<模板章节号>` → 附注目录 `disclosure` + 编号体系提示（模板「五-1-1」与项目「八、1」不是同一体系，
 *   不猜对应）；`workpaper:…` 与注册表源键原样；
 * - `resolveDialogOpenContext({route, eventPayload})`：弹窗每次打开时的项目、年度、页签与预选源——事件带的项目优先于
 *   路由，非项目页不给项目；侧栏打开（没有事件）按路由预选数据源；事件带源时经上面的映射。弹窗关闭时调用方丢弃本次结果，
 *   下次打开重新计算（不跨次保留事件带来的项目）。
 */
import { isKnownYear } from '@/components/custom-query/queryPayloads'

/** 路由的最小形状（`RouteLocationNormalizedLoaded` 的子集，便于纯函数测试） */
export interface RouteLike {
  name?: string | symbol | null
  params?: Record<string, unknown>
  query?: Record<string, unknown>
}

export interface QueryEntryContext {
  projectId?: string
  year?: number
  source?: string
}

/** `open-custom-query` 事件载荷（模板库按钮、Dashboard 快捷入口） */
export interface OpenCustomQueryPayload {
  tab?: 'basic' | 'advanced'
  source?: string
  project_id?: string
}

export interface DialogOpenContext {
  /** 空串 = 不预选项目（非项目页，弹窗不取列表第一项） */
  projectId: string
  year?: number
  initialTab: 'basic' | 'advanced'
  initialSource?: string
  initialNotice?: string
}

/** 报表页签 = 报表类型（ReportView 的六个报表页签；跨表核对 / 多年对比不是数据源） */
export const REPORT_TAB_TYPES: ReadonlySet<string> = new Set([
  'balance_sheet', 'income_statement', 'cash_flow_statement', 'equity_statement', 'cash_flow_supplement',
  'impairment_provision',
])
export const TEMPLATE_NOTE_NOTICE = '模板章节号与项目附注编号不同，请在目录中选择章节'

/** 账簿查询页 `?level` → 数据源（凭证层级仍是序时账） */
const LEDGER_LEVEL_SOURCES: Readonly<Record<string, string>> = {
  ledger: 'ledger_entries', voucher: 'ledger_entries', aux_balance: 'aux_balance', aux_ledger: 'aux_ledger',
}

function first(v: unknown): string {
  const x = Array.isArray(v) ? v[0] : v
  return x === undefined || x === null ? '' : String(x).trim()
}

function routeSource(route: RouteLike): string | undefined {
  const query = route.query ?? {}
  switch (String(route.name ?? '')) {
    case 'TrialBalance':
      return 'tb_detail'
    case 'Reports': {
      const tab = first(query.tab)
      return `report_${REPORT_TAB_TYPES.has(tab) ? tab : 'balance_sheet'}`
    }
    case 'DisclosureNotes': {
      const section = first(query.section)
      return section ? `disclosure_note:${section}` : 'disclosure'
    }
    case 'Adjustments':
      return 'adj_aje'
    case 'LedgerPenetration':
      return LEDGER_LEVEL_SOURCES[first(query.level)] ?? 'account_balance'
    case 'AuxSummary':
      return 'aux_balance'
    case 'WorkpaperEditor':
      return 'workpaper'
    default:
      return undefined
  }
}

/** 当前路由 → 项目、年度（`?year` 合法时）与预选数据源 */
export function resolveQueryEntryContext(route: RouteLike | null | undefined): QueryEntryContext {
  if (!route) return {}
  const out: QueryEntryContext = {}
  const projectId = first(route.params?.projectId)
  if (projectId) out.projectId = projectId
  const yearText = first(route.query?.year)
  const year = yearText ? Number(yearText) : NaN
  if (isKnownYear(year)) out.year = year
  const source = routeSource(route)
  if (source) out.source = source
  return out
}

/** 模板库按钮的模板口径源 URI → 注册表源键（AQ-38）；无法映射时不预选 */
export function resolveTemplateLibrarySource(uri: string | null | undefined): { source?: string; notice?: string } {
  const raw = (uri ?? '').trim()
  if (!raw) return {}
  if (raw.startsWith('report:')) {
    const type = raw.slice('report:'.length).split('|')[0].trim()
    return REPORT_TAB_TYPES.has(type) ? { source: `report_${type}` } : {}
  }
  if (raw.startsWith('note:')) return { source: 'disclosure', notice: TEMPLATE_NOTE_NOTICE }
  return { source: raw }
}

/** 弹窗打开时的上下文（每次打开重新计算） */
export function resolveDialogOpenContext(input: {
  route: RouteLike | null | undefined
  eventPayload?: OpenCustomQueryPayload | null
}): DialogOpenContext {
  const fromRoute = resolveQueryEntryContext(input.route)
  const event = input.eventPayload ?? null
  const eventProject = first(event?.project_id)
  const projectId = eventProject || fromRoute.projectId || ''
  const out: DialogOpenContext = { projectId, initialTab: event?.tab === 'advanced' ? 'advanced' : 'basic' }
  // 路由的 ?year 属于路由项目：事件带来别的项目时不套用（交弹窗按所选项目的审计年度取）
  if (fromRoute.year !== undefined && (!eventProject || eventProject === fromRoute.projectId)) out.year = fromRoute.year
  if (event?.source) {
    const mapped = resolveTemplateLibrarySource(event.source)
    if (mapped.source) out.initialSource = mapped.source
    if (mapped.notice) out.initialNotice = mapped.notice
  } else if (!event && fromRoute.source && fromRoute.projectId) {
    // 侧栏打开：按当前页预选数据源（只在项目页；非项目页没有项目，不预选）
    out.initialSource = fromRoute.source
  }
  return out
}
