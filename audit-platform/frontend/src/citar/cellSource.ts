/**
 * 表格单元格来源（悬浮溯源卡片，spec citar-cell-source-hover）：类型、标签、跳转换算。
 * 后端只给语义（page + 编码 / 格子），路由只在这里换算；与 fsIssueSources.sourceLink 同一套页面映射。
 */
import { sourceLink as pageLink, type SourceLink } from './fsIssueSources'

export type CellSourcePage =
  | 'balance' | 'journal' | 'mapping' | 'trial_balance' | 'adjustments' | 'reports' | 'statement'
  | 'workpaper' | 'tax_return' | 'ledger_import'

export type CellSourceKind =
  | 'rule' | 'formula' | 'manual' | 'import' | 'derived' | 'synthetic' | 'preset' | 'param' | 'adjustment' | 'none'

export interface CellSourceLink {
  page: CellSourcePage
  code?: string
  sheet?: string
  ref?: string
  row?: string | number
  column?: string
  group?: string
  report_type?: string
  tab?: string
}

export interface CellSourceItem {
  label: string
  detail: string | null
  amount: string | null
  /** 系数：1 / -1 / 常数；"0" = 只列出、不参与合计 */
  sign: string | null
  link: CellSourceLink | null
}

export interface CellSourceManual {
  value: string | null
  auto: string | null
  by_name?: string | null
  at?: string | null
  note?: string | null
}

export interface CellSource {
  kind: CellSourceKind
  title: string
  value: string | null
  items: CellSourceItem[]
  more: number
  linear: boolean
  total: string | null
  diff: string | null
  notes: string[]
  issue: string | null
  manual: CellSourceManual | null
  rule_text: string | null
  /** 前端补的操作提示（点击修改 / 无权修改 / 已恢复，保存后生效） */
  hint?: string | null
}

export interface CellSourceResponse {
  year: number
  cells: Record<string, CellSource>
  notices: string[]
}

export const KIND_LABELS: Record<CellSourceKind, string> = {
  rule: '智能取数',
  formula: '公式计算',
  manual: '手工修改',
  import: '导入数据',
  derived: '推导',
  synthetic: '按下级合计',
  preset: '样表预置',
  param: '表头参数',
  adjustment: '调整分录',
  none: '无来源',
}

/** 前端本地补的来源（后端不返回的格子：样表预置值、空的填写格、本页按下级合计的行等） */
export function localSource(kind: CellSourceKind, title: string, value: string | null = null, extra: Partial<CellSource> = {}): CellSource {
  return { kind, title, value, items: [], more: 0, linear: false, total: null, diff: null, notes: [], issue: null,
    manual: null, rule_text: null, ...extra }
}

/** 构成项的正负号显示：+ / − / ×系数；"0" 返回 null（不参与合计） */
export function signText(sign: string | null): string | null {
  const n = Number(sign ?? 1)
  if (!Number.isFinite(n) || n === 0) return null
  if (n === 1) return '+'
  if (n === -1) return '−'
  return n < 0 ? `− ×${-n}` : `+ ×${n}`
}

// ── 税审底稿 / 汇算申报表格子定位：跳页前记下，目标页读完值后消费一次 ──
export interface TaxCellLocate {
  domain: 'workpaper' | 'tax_return'
  code: string
  sheet: string
  ref: string
}

const LOCATE_PREFIX = 'gt.tax-cell-locate.'
/** 已在目标页时直接派发，页面监听后切表并定位 */
export const TAX_CELL_LOCATE_EVENT = 'gt:tax-cell-locate'

export function savePendingTaxLocate(projectId: string, target: TaxCellLocate) {
  try {
    sessionStorage.setItem(LOCATE_PREFIX + projectId, JSON.stringify(target))
  } catch {
    // 记不住就只跳页不定位
  }
}

/** 取出并清掉（只消费一次）；domain 不符时不取 */
export function takePendingTaxLocate(projectId: string, domain: TaxCellLocate['domain']): TaxCellLocate | null {
  try {
    const raw = sessionStorage.getItem(LOCATE_PREFIX + projectId)
    if (!raw) return null
    const target = JSON.parse(raw) as TaxCellLocate
    if (target?.domain !== domain || !target.code || !target.ref) return null
    sessionStorage.removeItem(LOCATE_PREFIX + projectId)
    return target
  } catch {
    return null
  }
}

/** 菜单段：税审底稿 / 汇算申报表 */
export const TAX_DOMAIN_SEGMENT: Record<TaxCellLocate['domain'], string> = { workpaper: 'workpapers', tax_return: 'tax-return' }

/**
 * 链接 → 本项目菜单与查询参数（statement 本页定位、workpaper / tax_return 格子定位由调用方另行处理，这里返回菜单段）。
 */
export function cellSourceLink(l: CellSourceLink): SourceLink | null {
  switch (l.page) {
    case 'workpaper':
    case 'tax_return':
      return { segment: TAX_DOMAIN_SEGMENT[l.page], query: {} }
    case 'adjustments':
      return { segment: 'adjustments', query: l.group ? { locate: l.group } : {} }
    case 'reports':
      return { segment: 'reports', query: { ...(l.report_type ? { tab: l.report_type } : {}), ...(l.code ? { locate: l.code } : {}) } }
    case 'ledger_import':
      // 带作业 ⇒ 打开那次导入的记录并定位到这一列的映射（code = 作业 id，ref = 定位键，后端给）
      return { segment: 'ledger-import', query: l.code ? { job: l.code, ...(l.ref ? { locate: l.ref } : {}) } : {} }
    default:
      return pageLink(l.page, l.code ?? '')
  }
}

/**
 * 账务查询：列来源（取自导入文件哪个表头）+ 行来源（舍弃的多列映射值、辅助汇总、人工修改）合成一张卡片。
 * 行上的人工修改没有自动值可比，写成说明（修改人 · 时间 · 导入原值 · 原因）。
 */
export function mergeLedgerSources(col: CellSource | null | undefined, row: CellSource | null | undefined, value: string | null): CellSource | null {
  if (!col && !row) return null
  const base = col ?? localSource('import', '导入数据')
  const notes = [...base.notes, ...(row?.notes ?? [])]
  if (row?.manual) {
    const m = row.manual
    notes.unshift(`人工修改过：${[m.by_name, m.at ? m.at.slice(0, 16).replace('T', ' ') : ''].filter(Boolean).join(' · ')}${m.note ? `；${m.note}` : ''}`)
  }
  return {
    ...base,
    kind: row?.manual ? 'manual' : base.kind,
    value,
    items: [...base.items, ...(row?.items ?? [])],
    notes,
    issue: row?.issue ?? base.issue,
    manual: null,
  }
}
