/**
 * H9 附注披露（上市/国企）数据模型
 * 对齐源 xlsx「附注披露信息（上市公司/国企）」+ note_template 五、47 / 八、52
 */
import { H9_LISTED_GUIDANCE } from './h9NoteSectionMap'

export const H9_LISTED_KEYS = {
  pack: 'H9-disc-listed-rows',
  auditNote: 'H9-disc-listed-audit-note',
  auditConclusion: 'H9-disc-listed-audit-conclusion',
} as const

export const H9_SOE_KEYS = {
  pack: 'H9-disc-soe-rows',
  auditNote: 'H9-disc-soe-audit-note',
  auditConclusion: 'H9-disc-soe-audit-conclusion',
} as const

export interface H9ListedCategoryRow {
  /**
   * 稳定行 key（`H9-listed-{seq}`）。
   *
   * 🔴 **不用 label 作 key** —— 改名会丢持久化数据、同名会撞键。
   * 历史行无此字段（`undefined`），由 `load()` 按序补齐以保证零丢数。
   */
  rowId?: string
  item: string
  endBalance: number | null
  lastYearEnd: number | null
}

export interface H9WithinOneYear {
  end: number | null
  last: number | null
}

export interface H9InterestBreakdown {
  /** 本期计提利息合计（元） */
  total: number | null
  /** 计入财务费用-利息支出（元） */
  financeExpense: number | null
  /** 计入固定资产/资本化（元） */
  capitalized: number | null
  /** 年份，如 2025 */
  year: string
}

export interface H9ListedDisclosureState {
  rows: H9ListedCategoryRow[]
  withinOneYear: H9WithinOneYear
  interest: H9InterestBreakdown
  /** 覆盖自动生成的利息说明；空则用 interest 生成 */
  interestNoteOverride: string
  auditNote: string
  auditConclusion: string
}

export interface H9SoeLineRow {
  /**
   * 行语义。前三个是源模板固定行（准则用语，不可增删改名）；
   * `extra` 对应源模板 `A11` 的 `……` **可续扣减行**。
   */
  key: 'payment' | 'unearned' | 'reclass' | 'extra'
  /** 稳定行 key（`H9-soe-extra-{seq}`），仅 `extra` 行有值 */
  rowId?: string
  item: string
  endBalance: number | null
  beginBalance: number | null
}

export interface H9SoeDisclosureState {
  rows: H9SoeLineRow[]
  supplementNote: string
  auditNote: string
  auditConclusion: string
}

/**
 * 上市租赁类别 seed 行（源模板 `A8:A10` 是**空白自由列示区**，这四行只是首次进入的
 * 建议值，可增删改名）。
 *
 * 🔴 **必须带显式 `rowId`**：否则 `nextListedRowId()` 对「只剩默认行」的状态返回
 * `H9-listed-1`，而 `load()` 又按序把默认行补成 `H9-listed-1` → **撞键**，
 * 按 rowId 查行会命中错行（PBT `Property 11` 用 `amt=0` 抓到过这个）。
 */
export const H9_LISTED_DEFAULT_ROWS: H9ListedCategoryRow[] = [
  { rowId: 'H9-listed-1', item: '房屋及建筑物租赁', endBalance: null, lastYearEnd: null },
  { rowId: 'H9-listed-2', item: '设备租赁', endBalance: null, lastYearEnd: null },
  { rowId: 'H9-listed-3', item: '车辆租赁', endBalance: null, lastYearEnd: null },
  { rowId: 'H9-listed-4', item: '其他', endBalance: null, lastYearEnd: null },
]

export const H9_SOE_DEFAULT_ROWS: H9SoeLineRow[] = [
  { key: 'payment', item: '租赁付款额', endBalance: null, beginBalance: null },
  { key: 'unearned', item: '减：未确认的融资费用', endBalance: null, beginBalance: null },
  { key: 'reclass', item: '重分类至一年内到期的非流动负债', endBalance: null, beginBalance: null },
]

export function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

export function amt(v: number): number {
  return Math.round(num(v) * 100) / 100
}

export function createDefaultListedState(): H9ListedDisclosureState {
  return {
    rows: H9_LISTED_DEFAULT_ROWS.map((r) => ({ ...r })),
    withinOneYear: { end: null, last: null },
    interest: { total: null, financeExpense: null, capitalized: null, year: String(new Date().getFullYear()) },
    interestNoteOverride: '',
    auditNote: '',
    auditConclusion: '',
  }
}

export function createDefaultSoeState(): H9SoeDisclosureState {
  return {
    rows: H9_SOE_DEFAULT_ROWS.map((r) => ({ ...r })),
    supplementNote: '',
    auditNote: '',
    auditConclusion: '',
  }
}

/** 万元展示（附注模板用语） */
export function toWan(yuan: number | null | undefined): string {
  if (yuan == null || !Number.isFinite(Number(yuan))) return 'XX'
  return amt(Number(yuan) / 10000).toFixed(2)
}

export function formatListedInterestNote(interest: H9InterestBreakdown): string {
  const y = interest.year || String(new Date().getFullYear())
  return `${y}年计提的租赁负债利息费用金额为${toWan(interest.total)}万元，计入财务费用-利息支出金额为${toWan(interest.financeExpense)}万元，计入固定资产金额为${toWan(interest.capitalized)}万元。`
}

export function resolveListedInterestNote(state: H9ListedDisclosureState): string {
  const override = String(state.interestNoteOverride || '').trim()
  if (override) return override
  const hasAny =
    state.interest.total != null
    || state.interest.financeExpense != null
    || state.interest.capitalized != null
  if (!hasAny) return ''
  return formatListedInterestNote(state.interest)
}

export interface H9ListedDisplayRow {
  item: string
  endBalance: number | null
  lastYearEnd: number | null
  kind: 'category' | 'subtotal' | 'within' | 'total'
  rowIndex?: number
}

export function buildListedDisplayRows(state: H9ListedDisclosureState): H9ListedDisplayRow[] {
  const rows = state.rows
  const subEnd = rows.reduce((s, r) => s + num(r.endBalance), 0)
  const subLast = rows.reduce((s, r) => s + num(r.lastYearEnd), 0)
  const wEnd = num(state.withinOneYear.end)
  const wLast = num(state.withinOneYear.last)
  return [
    ...rows.map((r, i) => ({
      item: r.item,
      endBalance: r.endBalance,
      lastYearEnd: r.lastYearEnd,
      kind: 'category' as const,
      rowIndex: i,
    })),
    { item: '小  计', endBalance: amt(subEnd), lastYearEnd: amt(subLast), kind: 'subtotal' },
    {
      item: '减：一年内到期的租赁负债',
      endBalance: state.withinOneYear.end,
      lastYearEnd: state.withinOneYear.last,
      kind: 'within',
    },
    {
      item: '合  计',
      endBalance: amt(subEnd - wEnd),
      lastYearEnd: amt(subLast - wLast),
      kind: 'total',
    },
  ]
}

export interface H9SoeDisplayRow {
  item: string
  endBalance: number | null
  beginBalance: number | null
  kind: 'line' | 'net'
  rowIndex?: number
  key?: H9SoeLineRow['key']
}

export function buildSoeDisplayRows(state: H9SoeDisclosureState): H9SoeDisplayRow[] {
  const lines = state.rows
  const payment = lines.find((r) => r.key === 'payment')
  const unearned = lines.find((r) => r.key === 'unearned')
  const reclass = lines.find((r) => r.key === 'reclass')
  // 🔴 续加扣减项（源模板 `A11` 的 `……`）也是**扣减**项，必须计入净额，
  //    否则加了扣减项后「净额」与各行不勾稽。
  const extraEnd = lines
    .filter((r) => r.key === 'extra')
    .reduce((s, r) => s + num(r.endBalance), 0)
  const extraBegin = lines
    .filter((r) => r.key === 'extra')
    .reduce((s, r) => s + num(r.beginBalance), 0)
  const endNet =
    num(payment?.endBalance) - num(unearned?.endBalance) - num(reclass?.endBalance) - extraEnd
  const beginNet =
    num(payment?.beginBalance) - num(unearned?.beginBalance) - num(reclass?.beginBalance) - extraBegin
  return [
    ...lines.map((r, i) => ({
      item: r.item,
      endBalance: r.endBalance,
      beginBalance: r.beginBalance,
      kind: 'line' as const,
      rowIndex: i,
      key: r.key,
    })),
    {
      item: '租赁负债净额',
      endBalance: amt(endNet),
      beginBalance: amt(beginNet),
      kind: 'net',
    },
  ]
}

/** 按类别名粗匹配上市默认行 */
export function mapToListedCategoryItem(name: string): string {
  const s = String(name || '').trim()
  if (!s) return '其他'
  if (/房屋|建筑|办公|房产|不动产/.test(s)) return '房屋及建筑物租赁'
  if (/设备|机器|生产|机械/.test(s)) return '设备租赁'
  if (/车|运输|货车|客车/.test(s)) return '车辆租赁'
  return s.length <= 20 ? s : '其他'
}

export { H9_LISTED_GUIDANCE }
