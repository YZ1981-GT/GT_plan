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
 *   路由，非项目页不给项目；模板库页只认路由明确带的项目（`TEMPLATE_LIBRARY_ROUTE`，见函数内说明）；侧栏打开（没有事件）
 *   按路由预选数据源；事件带源时经上面的映射。弹窗关闭时调用方丢弃本次结果，下次打开重新计算（不跨次保留事件带来的项目）。
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

/** `open-custom-query` 事件载荷（模板库按钮、Dashboard 快捷入口、业务页行级入口） */
export interface OpenCustomQueryPayload {
  tab?: 'basic' | 'advanced'
  source?: string
  project_id?: string
  /** 业务页行级「按此查询明细」的上下文（W6，ADR-AQL-20；由 `buildQueryEntry` 生成，弹窗按它取数） */
  entry?: QueryEntryRequest
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
/** 模板库页的路由名（全局页：URL 不带项目时页面自取项目列表第一项作演示项目，见 resolveDialogOpenContext） */
export const TEMPLATE_LIBRARY_ROUTE = 'TemplateLibraryMgmt'

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
  let projectId = eventProject || fromRoute.projectId || ''
  if (String(input.route?.name ?? '') === TEMPLATE_LIBRARY_ROUTE) {
    // 模板库页 URL 不带项目时，页面取项目列表第一项作演示项目，经底稿模板详情的「📊 高级查询」进入事件；用户看不到它
    // 从哪来，不能当成所选项目（R10.1 非项目页不自动选中项目，AQ-37）⇒ 只认路由明确带的项目（`params.projectId`，
    // 其次 `?project_id`）：事件带的项目与它一致才采纳，不一致取路由的；路由没带项目、或事件没带项目时为空
    const routeProject = first(input.route?.params?.projectId) || first(input.route?.query?.project_id)
    projectId = routeProject && eventProject ? routeProject : ''
  }
  const out: DialogOpenContext = { projectId, initialTab: event?.tab === 'advanced' ? 'advanced' : 'basic' }
  // 路由的 ?year 属于路由项目：弹窗项目不是路由项目时不套用（交弹窗按所选项目的审计年度取）
  if (fromRoute.year !== undefined && projectId === (fromRoute.projectId ?? '')) out.year = fromRoute.year
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

/* ── W6 业务页行级「按此查询明细」（任务 46，ADR-AQL-20；design §4.3）──────────────
 *
 * 业务对象 → 查询参数的映射只在这里；业务对象 → 科目的解析只在后端 `entry_accounts.py`。
 * 四个宿主页只挂 `QueryDetailEntry.vue` 并把自己取数用的年度传进来，不自己拼参数。
 */

export type QueryEntryKind = 'tb_row' | 'report_row' | 'note_section' | 'workpaper'
/** 筛选值：字符串或字符串数组（`account_code` 支持多值，见后端 R14.2） */
export type QueryEntryFilters = Record<string, string | string[]>

export interface QueryEntrySwitch {
  source: string
  label: string
  /** 换源时同时换筛选（附注章节 → 相关科目要把 `note_section` 带给试算表）；不给则沿用当前筛选 */
  filters?: QueryEntryFilters
}

export interface QueryEntryRequest {
  kind: QueryEntryKind
  projectId: string
  /** 宿主取数用的年度；取不到时不带，交弹窗按 R10.2 解析（不按日历年兜底） */
  year?: number
  source: string
  filters: QueryEntryFilters
  label: string
  switches: QueryEntrySwitch[]
}

export interface QueryEntryRejection {
  disabledReason: string
}

export type QueryEntryResult = QueryEntryRequest | QueryEntryRejection

export function isQueryEntryRejected(result: QueryEntryResult): result is QueryEntryRejection {
  return 'disabledReason' in result
}

/** 入口不可用的原因（界面置灰时按 title 显示；文案在这里集中，组件不自己拼） */
export const ENTRY_NO_PROJECT = '请在项目页使用此入口'
export const ENTRY_TB_TOTAL_ROW = '合计行请在高级查询中按科目查询'
export const ENTRY_TB_NO_ACCOUNT = '该行没有科目编码'
export const ENTRY_REPORT_TOTAL_ROW = '合计行没有直接取数的科目，请在报表页查看公式'
export const ENTRY_REPORT_NO_ROW = '该行没有行次编码'
export const ENTRY_NOTE_NO_SECTION = '请先选择附注章节'
export const ENTRY_WP_NO_CODE = '该底稿没有编码'
export const ENTRY_UNKNOWN_KIND = '不支持的入口类型'

/** 账簿四源：同一筛选可互相切换（当前源也列出，便于切回去；横幅把它显示为已选） */
const LEDGER_SWITCHES: readonly QueryEntrySwitch[] = [
  { source: 'ledger_entries', label: '序时账' },
  { source: 'account_balance', label: '科目余额' },
  { source: 'aux_balance', label: '辅助余额' },
  { source: 'aux_ledger', label: '辅助明细' },
]

const REPORT_TYPE_LABELS: Readonly<Record<string, string>> = {
  balance_sheet: '资产负债表', income_statement: '利润表', cash_flow_statement: '现金流量表',
  equity_statement: '所有者权益变动表', cash_flow_supplement: '现金流量表补充资料',
  impairment_provision: '资产减值准备表',
}

/** 入口目标：各宿主页把自己那一行 / 当前对象原样传进来（字段按宿主的既有命名读） */
export interface QueryEntryTarget {
  year?: number | null
  // 试算表行（TrialBalance 的 DisplayRow）
  standard_account_code?: string | null
  account_name?: string | null
  _isSubtotal?: boolean
  _isTotal?: boolean
  // 报表穿透（useReportDrilldown 的 drilldownData）
  report_type?: string | null
  row_code?: string | null
  row_name?: string | null
  is_total_row?: boolean
  project_id?: string | null
  // 附注章节（DisclosureEditor 的 currentNote）
  note_section?: string | null
  section_title?: string | null
  // 底稿（WorkpaperEditor 的 wpDetail）
  wp_code?: string | null
  wp_name?: string | null
}

function text(value: unknown): string {
  return value === undefined || value === null ? '' : String(value).trim()
}

function label(...parts: unknown[]): string {
  return parts.map(text).filter(Boolean).join(' ')
}

/**
 * 业务对象 → 一次查询请求；不可用时返回 `{disabledReason}`（组件据此置灰并显示原因，不发事件）。
 *
 * 年度 = `target.year ?? hostYear`（宿主取数用的那个年度，附注编辑器页内切年也跟着变，§16 #7）；
 * 都取不到就不带，交弹窗按所选项目的审计年度解析。项目只取当前路由。
 */
export function buildQueryEntry(
  kind: QueryEntryKind,
  target: QueryEntryTarget | null | undefined,
  route: RouteLike | null | undefined,
  hostYear?: number | null,
): QueryEntryResult {
  const projectId = first(route?.params?.projectId)
  if (!projectId) return { disabledReason: ENTRY_NO_PROJECT }
  const year = isKnownYear(target?.year) ? Number(target?.year) : (isKnownYear(hostYear) ? Number(hostYear) : undefined)
  const base = { kind, projectId, ...(year === undefined ? {} : { year }) }

  if (kind === 'tb_row') {
    if (!target) return { disabledReason: ENTRY_TB_NO_ACCOUNT }
    if (target._isSubtotal || target._isTotal) return { disabledReason: ENTRY_TB_TOTAL_ROW }
    const code = text(target.standard_account_code)
    if (!code) return { disabledReason: ENTRY_TB_NO_ACCOUNT }
    return {
      ...base, source: 'ledger_entries', filters: { account_code: code },
      label: label('试算表', code, target.account_name), switches: [...LEDGER_SWITCHES],
    }
  }

  if (kind === 'report_row') {
    if (!target) return { disabledReason: ENTRY_REPORT_NO_ROW }
    if (target.is_total_row) return { disabledReason: ENTRY_REPORT_TOTAL_ROW }
    const rowCode = text(target.row_code)
    const reportType = text(target.report_type) || 'balance_sheet'
    if (!rowCode || !REPORT_TYPE_LABELS[reportType]) return { disabledReason: ENTRY_REPORT_NO_ROW }
    return {
      ...base, source: 'tb_detail', filters: { report_row: `${reportType}:${rowCode}` },
      label: label(REPORT_TYPE_LABELS[reportType], rowCode, target.row_name), switches: [],
    }
  }

  if (kind === 'note_section') {
    const section = text(target?.note_section)
    if (!section) return { disabledReason: ENTRY_NOTE_NO_SECTION }
    return {
      ...base, source: `disclosure_note:${section}`, filters: {},
      label: label('附注', section, target?.section_title),
      switches: [
        { source: `disclosure_note:${section}`, label: '附注表格', filters: {} },
        { source: 'tb_detail', label: '相关科目（试算表）', filters: { note_section: section } },
      ],
    }
  }

  if (kind === 'workpaper') {
    const code = text(target?.wp_code)
    if (!code) return { disabledReason: ENTRY_WP_NO_CODE }
    return {
      ...base, source: 'ledger_entries', filters: { wp_code: code },
      label: label('底稿', code, target?.wp_name), switches: [...LEDGER_SWITCHES],
    }
  }

  return { disabledReason: ENTRY_UNKNOWN_KIND }
}

/**
 * 结果行「查明细」的下一跳（只对带标准科目码的试算表结果行有效）：该科目的序时账，可返回上一查询。
 * 返回 null = 该行不提供下钻（没有科目码，或是合计 / 小计行）。
 */
export function tbRowDrill(
  row: QueryEntryTarget | null | undefined,
  entry: QueryEntryRequest | null | undefined,
): QueryEntryRequest | null {
  if (!entry || !row || row._isSubtotal || row._isTotal) return null
  const code = text(row.standard_account_code)
  if (!code) return null
  return {
    kind: 'tb_row', projectId: entry.projectId, ...(entry.year === undefined ? {} : { year: entry.year }),
    source: 'ledger_entries', filters: { account_code: code },
    label: label(code, row.account_name, '序时账'), switches: [...LEDGER_SWITCHES],
  }
}
