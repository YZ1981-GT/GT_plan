/**
 * queryResultLinks.ts — 查询结果行的下钻与公式引用（advanced-query-linkage-closure 任务 27，design §4.1；ADR-AQL-01 / 18；R7.1~R7.3）
 *
 * - `buildRowDrill`：ADR-AQL-01 的唯一实现。每类结果下钻到它的权威页面、只用页面既有深链契约（账簿查询的 query 由
 *   `useLedgerUrlSync.buildLedgerQuery` 生成，与页内同步同一个函数；底稿编辑器路由由 `workpaperEditorRoute` 生成）。
 *   业务视图按数据源键（`kind: 'source'`）、构建器按白名单表名（`kind: 'table'`）映射到同一目标；没有项目上下文
 *   （跨项目结果）一律不下钻；报表行次配置 / 工时 / 合并工作底稿不下钻。
 * - `openRowDrill`：底稿按编码经 `wp-id-by-code` 取实例 id 后，在新标签打开（`window.open(href)`，不加 noopener：
 *   新标签要复制 sessionStorage 里的登录态）。
 * - `buildFormulaRef`：试算表 TB / 报表 ROW / 附注 NOTE / 底稿单元格 WP 四种地址库语法；值里含单引号的不生成（语法无转义）。
 * - `validatePageRefs`：对本页引用批量校验（每批 ≤ 200 个，以「+」连成一条公式调 `POST /api/address-registry/validate`），
 *   按返回问题的 `ref` 回填；底稿格 `not_found` 显示「该单元格未登记为可引用地址」；请求失败时全部不可用。
 */
import { api } from '@/services/apiProxy'
import { addressRegistry as P_ar } from '@/services/apiPaths'
import { resolveWorkpaperByCode } from '@/services/resolveWorkpaperByCode'
import { buildLedgerQuery, type LedgerUrlState } from '@/composables/useLedgerUrlSync'
import { workpaperEditorRoute } from '@/composables/useWorkpaperNavigation'
import { isKnownYear } from '@/components/custom-query/queryPayloads'
import { RESOLVE_FAIL_MSG, reportTypeOfSource } from './querySourceUri'

/** 结果所属的查询：业务视图按数据源键，构建器按白名单表名 */
export interface DrillContext {
  kind: 'source' | 'table'
  key: string
  projectId?: string | null
  year?: number | null
  /** 附注表格：当前显示的是该章节第几张表（缺省 0） */
  tableIndex?: number | null
}

export interface DrillLocation {
  name: string
  params: Record<string, string>
  query?: Record<string, string>
}

/** 一行结果的下钻：目标路由已知，或是底稿编码（打开前经 wp-id-by-code 取实例 id） */
export type RowDrill =
  | { label: string; location: DrillLocation }
  | { label: string; workpaper: { projectId: string; wpCode: string; query?: Record<string, string> } }

export type ResolvedDrill = { ok: true; location: DrillLocation } | { ok: false; reason: string }

type Row = Record<string, unknown>
type Target = 'balance' | 'ledger' | 'aux' | 'tb' | 'report' | 'note' | 'adjustment' | 'wp_list' | 'wp_index' | 'wp_cells'

const LEDGER_LABEL = '在账簿查询中打开'
const REPORT_LABEL = '在报表中定位该行'
const NOTE_LABEL = '在附注中打开该章节'
const ADJUSTMENT_LABEL = '在调整分录中打开该分录组'
const WORKPAPER_LABEL = '在底稿中打开'
const WP_CELL_LABEL = '在底稿中定位该单元格'

/** 业务视图数据源键 → 下钻目标（`consol_unit:{单位}:{类型}` 按类型） */
const SOURCE_TARGETS: Readonly<Record<string, Target>> = {
  account_balance: 'balance', ledger_entries: 'ledger', aux_balance: 'aux', aux_ledger: 'aux',
  tb_detail: 'tb', trial_balance: 'tb', disclosure: 'note', adj_aje: 'adjustment', adj_rje: 'adjustment',
  adj_rcl: 'adjustment', adjustment: 'adjustment', workpaper: 'wp_list',
}
/** 构建器白名单表 → 下钻目标（与业务视图同一目标页） */
const TABLE_TARGETS: Readonly<Record<string, Target>> = {
  trial_balance: 'tb', tb_balance: 'balance', tb_ledger: 'ledger', tb_aux_balance: 'aux', tb_aux_ledger: 'aux',
  adjustments: 'adjustment', disclosure_notes: 'note', working_paper: 'wp_list', wp_index: 'wp_index',
  financial_report: 'report',
}
const UUID_RE = /^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$/i

function str(v: unknown): string {
  return v === undefined || v === null ? '' : String(v).trim()
}

function yearOf(v: unknown): number | null {
  const n = typeof v === 'string' && v.trim() ? Number(v) : v
  return isKnownYear(n) ? n : null
}

function sourceTarget(key: string): Target | null {
  if (key.startsWith('workpaper:')) return key.includes('|') ? 'wp_cells' : 'wp_index'
  if (key.startsWith('disclosure_note:')) return 'note'
  if (reportTypeOfSource(key)) return 'report'
  const consol = /^consol_unit:[^:]+:(.+)$/.exec(key)
  return SOURCE_TARGETS[consol ? consol[1] : key] ?? null
}

function ledger(projectId: string, state: Partial<LedgerUrlState>, year: number | null): RowDrill | null {
  if (!state.account) return null
  return { label: LEDGER_LABEL, location: { name: 'LedgerPenetration', params: { projectId }, query: buildLedgerQuery(state, year) } }
}

function withYear(year: number | null, query: Record<string, string>): Record<string, string> {
  return year === null ? query : { year: String(year), ...query }
}

/** 一行结果 → 下钻目标；没有项目、目标页不接受这类结果或行里缺定位键时返回 null */
export function buildRowDrill(ctx: DrillContext, row: Row | null | undefined): RowDrill | null {
  const projectId = str(ctx.projectId)
  if (!projectId || !row) return null
  const target = ctx.kind === 'table' ? TABLE_TARGETS[ctx.key] ?? null : sourceTarget(ctx.key)
  if (!target) return null
  // 构建器行可能来自多个年度（未限定年度时）：优先用行自己的年度
  const year = ctx.kind === 'table' ? yearOf(row.year) ?? yearOf(ctx.year) : yearOf(ctx.year)
  const account = str(row.account_code)
  switch (target) {
    case 'balance':
      return ledger(projectId, { level: 'ledger', account }, year)
    case 'ledger': {
      const voucherNo = str(row.voucher_no)
      return voucherNo
        ? ledger(projectId, { level: 'voucher', account, voucherNo, voucherDate: str(row.voucher_date).slice(0, 10) }, year)
        : ledger(projectId, { level: 'ledger', account }, year)
    }
    case 'aux': {
      const auxType = str(row.aux_type)
      const auxCode = str(row.aux_code)
      return auxType && auxCode
        ? ledger(projectId, { level: 'aux_ledger', account, auxType, auxCode }, year)
        : ledger(projectId, { level: 'ledger', account }, year)
    }
    case 'tb':
      return ledger(projectId, { account: str(row.standard_account_code) }, year)
    case 'report': {
      const tab = ctx.kind === 'table' ? str(row.report_type) : reportTypeOfSource(ctx.key) ?? ''
      const rowCode = str(row.row_code)
      if (!tab || !rowCode) return null
      return { label: REPORT_LABEL, location: { name: 'Reports', params: { projectId }, query: withYear(year, { tab, highlight: rowCode }) } }
    }
    case 'note': {
      const section = ctx.key.startsWith('disclosure_note:') ? ctx.key.slice('disclosure_note:'.length) : str(row.note_section)
      if (!section) return null
      const rawIndex = ctx.key.startsWith('disclosure_note:') ? ctx.tableIndex ?? 0 : row.table_index
      const index = Number(rawIndex)
      const query: Record<string, string> = { section }
      if (rawIndex !== undefined && rawIndex !== null && rawIndex !== '' && Number.isInteger(index) && index >= 0) {
        query.table_index = String(index)
      }
      return { label: NOTE_LABEL, location: { name: 'DisclosureNotes', params: { projectId }, query: withYear(year, query) } }
    }
    case 'adjustment': {
      const group = str(row.entry_group_id)
      if (!group) return null
      // ?focus= 在调整大厅定位并高亮该分录（?group= 是打开协作对话框，用于协作通知）
      return { label: ADJUSTMENT_LABEL, location: { name: 'Adjustments', params: { projectId }, query: withYear(year, { focus: group }) } }
    }
    case 'wp_list': {
      // 底稿清单的隐藏列 id 即底稿实例 id：直接打开；没有时按编码解析
      const wpId = str(row.id)
      if (UUID_RE.test(wpId)) return { label: WORKPAPER_LABEL, location: workpaperEditorRoute(projectId, wpId) }
      const wpCode = str(row.wp_code)
      return wpCode ? { label: WORKPAPER_LABEL, workpaper: { projectId, wpCode } } : null
    }
    case 'wp_index': {
      const wpCode = str(row.wp_code) || (ctx.key.startsWith('workpaper:') ? ctx.key.slice('workpaper:'.length) : '')
      return wpCode ? { label: WORKPAPER_LABEL, workpaper: { projectId, wpCode } } : null
    }
    case 'wp_cells': {
      const wpCode = str(row.wp_code)
      if (!wpCode) return null
      const query: Record<string, string> = {}
      if (str(row.sheet_name)) query.sheet = str(row.sheet_name)
      if (str(row.cell_ref)) query.cell = str(row.cell_ref)
      return { label: WP_CELL_LABEL, workpaper: { projectId, wpCode, query } }
    }
    default:
      return null
  }
}

/** 下钻目标 → 路由；底稿编码取不到实例时给出原因 */
export async function resolveRowDrill(drill: RowDrill): Promise<ResolvedDrill> {
  if ('location' in drill) return { ok: true, location: drill.location }
  const { projectId, wpCode, query } = drill.workpaper
  const found = await resolveWorkpaperByCode(projectId, wpCode, true)
  if (!found) return { ok: false, reason: RESOLVE_FAIL_MSG.wpNotFound(wpCode) }
  const q = query && Object.keys(query).length ? query : undefined
  return { ok: true, location: workpaperEditorRoute(projectId, found.wpId, q) }
}

/** 在新标签打开下钻目标；打不开时返回原因（调用方提示），成功返回 null */
export async function openRowDrill(
  drill: RowDrill, router: { resolve: (to: DrillLocation) => { href: string } },
): Promise<string | null> {
  const resolved = await resolveRowDrill(drill)
  if (!resolved.ok) return resolved.reason
  window.open(router.resolve(resolved.location).href, '_blank')
  return null
}

// ─── 公式引用（ADR-AQL-18） ───────────────────────────────────────────────────────────────────

/** 试算表结果列 → TB() 列名（地址库 tb 域的登记列名，`address_registry._TB_LEGACY_COLUMNS`） */
export const TB_REF_COLUMNS: Readonly<Record<string, string>> = {
  audited_amount: '审定数',
  unadjusted_amount: '未审数',
  aje_adjustment: 'AJE调整',
  rje_adjustment: 'RJE调整',
  opening_balance: '期初余额',
}
/** 只给行复制一条引用时取的试算表列 */
export const DEFAULT_TB_REF_COLUMN = 'audited_amount'

/** 引用参数：非空且不含单引号（地址库语法没有转义写法） */
function arg(v: unknown): string | null {
  const s = str(v)
  return s && !s.includes("'") ? s : null
}

/**
 * 一行结果 → 公式引用；该源 / 列没有引用语法或缺定位值时返回 null。
 * 附注表格需 `labelKey`（行标签所在列）与 `columnKey`（取值列的表头）。
 */
export function buildFormulaRef(
  source: string, row: Row | null | undefined, columnKey?: string | null, opts: { labelKey?: string | null } = {},
): string | null {
  if (!row || !source) return null
  if (source === 'tb_detail' || source === 'trial_balance') {
    const code = arg(row.standard_account_code)
    const column = TB_REF_COLUMNS[columnKey || DEFAULT_TB_REF_COLUMN]
    return code && column ? `TB('${code}','${column}')` : null
  }
  if (reportTypeOfSource(source)) {
    if (columnKey && columnKey !== 'current_period_amount') return null
    const rowCode = arg(row.row_code)
    return rowCode ? `ROW('${rowCode}')` : null
  }
  if (source.startsWith('disclosure_note:')) {
    const section = arg(source.slice('disclosure_note:'.length))
    const label = opts.labelKey ? arg(row[opts.labelKey]) : null
    const column = arg(columnKey)
    return section && label && column ? `NOTE('${section}','${label}','${column}')` : null
  }
  if (source.startsWith('workpaper:') && source.includes('|')) {
    const wpCode = arg(row.wp_code)
    const sheet = arg(row.sheet_name)
    const cell = arg(row.cell_ref)
    return wpCode && sheet && cell ? `WP('${wpCode}','${sheet}','${cell}')` : null
  }
  return null
}

export interface RefCheck {
  ok: boolean
  /** 不可用时的中文原因 */
  reason?: string
}

export const REF_BATCH_SIZE = 200
export const REF_CHECK_UNAVAILABLE = '引用校验暂不可用'
export const WP_REF_NOT_REGISTERED = '该单元格未登记为可引用地址'
const REF_NEEDS_CONTEXT = '缺少项目或审计年度，无法校验引用'

interface ValidateIssue { ref?: string; status?: string; message?: string }

function issueReason(issue: ValidateIssue): string {
  if (str(issue.ref).startsWith('WP(') && issue.status === 'not_found') return WP_REF_NOT_REGISTERED
  return str(issue.message) || '该引用在当前项目中不存在'
}

/**
 * 批量校验本页引用：每批 ≤ 200 个，以「+」连成一条公式校验一次，按返回问题的 `ref` 回填（与顺序无关）。
 * 任一批请求失败 ⇒ 全部不可用（「引用校验暂不可用」）。
 */
export async function validatePageRefs(
  refs: readonly (string | null | undefined)[],
  ctx: { projectId?: string | null; year?: number | null; templateType?: string | null },
): Promise<Map<string, RefCheck>> {
  const unique = [...new Set(refs.filter((r): r is string => typeof r === 'string' && r.length > 0))]
  const out = new Map<string, RefCheck>()
  if (!unique.length) return out
  if (!str(ctx.projectId) || !isKnownYear(ctx.year)) {
    for (const ref of unique) out.set(ref, { ok: false, reason: REF_NEEDS_CONTEXT })
    return out
  }
  try {
    for (let i = 0; i < unique.length; i += REF_BATCH_SIZE) {
      const batch = unique.slice(i, i + REF_BATCH_SIZE)
      const body: Record<string, unknown> = { formula: batch.join('+'), project_id: ctx.projectId, year: ctx.year }
      if (ctx.templateType) body.template_type = ctx.templateType
      const resp = await api.post<{ issues?: ValidateIssue[] }>(P_ar.validate, body, { _silent: true } as any)
      const reasons = new Map<string, string>()
      for (const issue of resp?.issues ?? []) {
        const ref = str(issue?.ref)
        if (ref && !reasons.has(ref)) reasons.set(ref, issueReason(issue))
      }
      for (const ref of batch) {
        const reason = reasons.get(ref)
        out.set(ref, reason ? { ok: false, reason } : { ok: true })
      }
    }
  } catch {
    for (const ref of unique) out.set(ref, { ok: false, reason: REF_CHECK_UNAVAILABLE })
  }
  return out
}
