import {
  buildL5SyncPayload,
  buildL5Within1ySyncPayload,
  type L5DisclosureVariant,
  type L5SyncSnapshot,
  type L5TwoPeriodRow,
} from './l5NoteSectionMap'
import { recalcL5DetailRow, type L5DetailRow } from './useL5Detail'
import type { L5UnrecognizedRow } from './useL5UnrecognizedDetail'
import type { ChecklistResponse } from './useL5FormData'

export interface L5CategoryRow {
  category: string
  endBalance: number
  beginBalance: number
}

export interface L5MaturityRow {
  period: string
  amount: number
}

export interface L5DisclosureState {
  categoryRows: L5CategoryRow[]
  unrecognizedEnd: number
  unrecognizedBegin: number
  periodAmortizationAmount: number
  maturityRows: L5MaturityRow[]
  soeSpecialNote: string
  relatedPartyNote: string
  conclusion: string
  detailRows?: L5DetailRow[]
  unrecognizedRows?: L5UnrecognizedRow[]
  /** 至少一项持久化来源存在；false 时不得把默认 0 主表写入附注。 */
  mainSourceFound: boolean
  /** L5-2 或明确保存的到期分布存在；用于决定是否发独立到期章节。 */
  within1ySourceFound: boolean
}

const LISTED_CATEGORIES = ['融资租赁款', '分期付款购入资产款', '其他长期应付款'] as const
const SOE_CATEGORIES = ['融资租赁款', '分期付款购入资产款', '国有资本融资安排', '其他长期应付款'] as const
const MATURITY_PERIODS = ['1年以内', '1-2年', '2-3年', '3-5年', '5年以上'] as const

const num = (value: unknown): number => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function parseArray<T>(raw: string | null | undefined): T[] | undefined {
  if (raw == null) return undefined
  try {
    const value = JSON.parse(raw)
    return Array.isArray(value) ? value as T[] : undefined
  } catch {
    return undefined
  }
}

function responseNumber(responses: ReadonlyMap<string, ChecklistResponse>, key: string): number | undefined {
  const response = responses.get(key)
  if (!response || response.remark == null || response.remark === '') return undefined
  const value = Number(response.remark)
  return Number.isFinite(value) ? value : undefined
}

export function createL5CategoryRows(variant: L5DisclosureVariant): L5CategoryRow[] {
  const labels = variant === 'listed' ? LISTED_CATEGORIES : SOE_CATEGORIES
  return [
    ...labels.map((category) => ({ category, endBalance: 0, beginBalance: 0 })),
    { category: '合计', endBalance: 0, beginBalance: 0 },
  ]
}

export function createL5MaturityRows(): L5MaturityRow[] {
  return MATURITY_PERIODS.map((period) => ({ period, amount: 0 }))
}

function categoryOf(raw: unknown, variant: L5DisclosureVariant): string {
  const text = String(raw ?? '')
  if (/租赁/.test(text)) return '融资租赁款'
  if (/分期/.test(text)) return '分期付款购入资产款'
  if (variant === 'soe' && /国有|国资|资本/.test(text)) return '国有资本融资安排'
  return '其他长期应付款'
}

function derivedCategoryRows(variant: L5DisclosureVariant, detailRows: readonly L5DetailRow[]): L5CategoryRow[] {
  const rows = createL5CategoryRows(variant)
  const index = new Map(rows.slice(0, -1).map((row) => [row.category, row]))
  for (const raw of detailRows) {
    const row = recalcL5DetailRow(raw)
    const target = index.get(categoryOf(row.category || row.payableName, variant))!
    target.endBalance += num(row.disclosureEnding)
    target.beginBalance += num(row.disclosureBeginning)
  }
  const total = rows.at(-1)!
  total.endBalance = rows.slice(0, -1).reduce((sum, row) => sum + row.endBalance, 0)
  total.beginBalance = rows.slice(0, -1).reduce((sum, row) => sum + row.beginBalance, 0)
  return rows
}

function manualCategoryRows(
  responses: ReadonlyMap<string, ChecklistResponse>,
  variant: L5DisclosureVariant,
): { rows: L5CategoryRow[]; found: boolean } {
  const rows = createL5CategoryRows(variant)
  let found = false
  for (let index = 0; index < rows.length; index += 1) {
    for (const field of ['endBalance', 'beginBalance'] as const) {
      const value = responseNumber(responses, `L5-disclosure-${variant}-cat-${index}-${field}`)
      if (value !== undefined) {
        rows[index][field] = value
        found = true
      }
    }
  }
  return { rows, found }
}

function unrecognizedTotals(rows: readonly L5UnrecognizedRow[] | undefined) {
  if (rows === undefined) return undefined
  return rows.reduce((out, row) => {
    const end = row.unrecognizedBalance != null
      ? num(row.unrecognizedBalance)
      : num(row.initialUnrecognized) - num(row.cumulativeAmortization)
    out.end += end
    out.begin += num(row.beginning)
    out.amortization += num(row.periodAmortization)
    return out
  }, { end: 0, begin: 0, amortization: 0 })
}

export function restoreL5DisclosureState(
  responses: ReadonlyMap<string, ChecklistResponse>,
  variant: L5DisclosureVariant,
): L5DisclosureState {
  const detailResponse = responses.get('L5-L5-2-rows')
  const unrecognizedResponse = responses.get('L5-L5-3-rows')
  const detailRows = parseArray<L5DetailRow>(detailResponse?.remark)
  const unrecognizedRows = parseArray<L5UnrecognizedRow>(unrecognizedResponse?.remark)
  const manualCategories = manualCategoryRows(responses, variant)
  const categoryRows = manualCategories.found
    ? manualCategories.rows
    : detailRows !== undefined ? derivedCategoryRows(variant, detailRows) : manualCategories.rows

  const unrecognized = unrecognizedTotals(unrecognizedRows)
  const scalarEnd = responseNumber(responses, `L5-disclosure-${variant}-unrecognized-end`)
  const scalarBegin = responseNumber(responses, `L5-disclosure-${variant}-unrecognized-begin`)
  const scalarAmort = responseNumber(responses, `L5-disclosure-${variant}-amortization`)

  const maturityRows = createL5MaturityRows()
  let manualMaturityFound = false
  for (let index = 0; index < maturityRows.length; index += 1) {
    const value = responseNumber(responses, `L5-disclosure-${variant}-maturity-${index}`)
    if (value !== undefined) {
      maturityRows[index].amount = value
      manualMaturityFound = true
    }
  }
  const scalarFound = scalarEnd !== undefined || scalarBegin !== undefined || scalarAmort !== undefined
  return {
    categoryRows,
    unrecognizedEnd: scalarEnd ?? unrecognized?.end ?? 0,
    unrecognizedBegin: scalarBegin ?? unrecognized?.begin ?? 0,
    periodAmortizationAmount: scalarAmort ?? unrecognized?.amortization ?? 0,
    maturityRows,
    soeSpecialNote: String(responses.get('L5-disclosure-soe-special')?.remark ?? ''),
    relatedPartyNote: String(responses.get('L5-disclosure-soe-related')?.remark ?? ''),
    conclusion: String(responses.get(`L5-disc-${variant}-conclusion`)?.remark ?? ''),
    detailRows,
    unrecognizedRows,
    mainSourceFound: manualCategories.found || detailResponse !== undefined || unrecognizedResponse !== undefined || scalarFound,
    within1ySourceFound: detailResponse !== undefined || manualMaturityFound,
  }
}

function byNatureGross(state: L5DisclosureState): L5TwoPeriodRow[] {
  return state.categoryRows.slice(0, -1).map((row) => ({
    label: row.category, endAmount: row.endBalance, priorAmount: row.beginBalance,
  }))
}

function byNatureUnrecognized(state: L5DisclosureState, variant: L5DisclosureVariant): L5TwoPeriodRow[] {
  const rows = state.unrecognizedRows
  if (rows?.length) {
    const grouped = new Map<string, L5TwoPeriodRow>()
    for (const row of rows) {
      const label = categoryOf(row.payableName, variant)
      const item = grouped.get(label) ?? { label, endAmount: 0, priorAmount: 0 }
      item.endAmount += row.unrecognizedBalance != null
        ? num(row.unrecognizedBalance)
        : num(row.initialUnrecognized) - num(row.cumulativeAmortization)
      item.priorAmount += num(row.beginning)
      grouped.set(label, item)
    }
    return [...grouped.values()]
  }
  return state.unrecognizedEnd || state.unrecognizedBegin
    ? [{ label: '未确认融资费用', endAmount: state.unrecognizedEnd, priorAmount: state.unrecognizedBegin }]
    : []
}

export function l5Within1yRows(state: L5DisclosureState): L5TwoPeriodRow[] {
  if (state.detailRows !== undefined) {
    return state.detailRows
      .map((raw) => recalcL5DetailRow(raw))
      .filter((row) => String(row.payableName ?? '').trim() && (num(row.minusEndDue) !== 0 || num(row.minusPriorDue) !== 0))
      .map((row) => ({
        label: String(row.payableName).trim(),
        endAmount: num(row.minusEndDue),
        priorAmount: num(row.minusPriorDue),
      }))
  }
  return state.maturityRows
    .filter((row) => row.amount !== 0)
    .map((row) => ({ label: row.period, endAmount: row.amount, priorAmount: 0 }))
}

function mainSnapshot(state: L5DisclosureState, variant: L5DisclosureVariant): L5SyncSnapshot {
  const total = state.categoryRows.at(-1) ?? { endBalance: 0, beginBalance: 0 }
  const longTerm = {
    end: num(total.endBalance) - state.unrecognizedEnd,
    prior: num(total.beginBalance) - state.unrecognizedBegin,
  }
  const withinRows = l5Within1yRows(state)
  const within1y = {
    end: withinRows.reduce((sum, row) => sum + row.endAmount, 0),
    prior: withinRows.reduce((sum, row) => sum + row.priorAmount, 0),
  }
  if (variant === 'listed') {
    return {
      variant,
      longTerm,
      special: { end: 0, prior: 0 },
      byNature: { gross: byNatureGross(state), unrecognized: byNatureUnrecognized(state, variant), within1y },
    }
  }
  const items = byNatureGross(state).filter((row) => row.label !== '其他长期应付款')
  const otherRow = byNatureGross(state).find((row) => row.label === '其他长期应付款')
  return {
    variant,
    longTerm,
    special: { end: 0, prior: 0 },
    top5: {
      items: items.slice(0, 5),
      other: {
        end: otherRow?.endAmount ?? 0,
        prior: otherRow?.priorAmount ?? 0,
      },
      within1y,
    },
  }
}

/** 返回一个或两个章节；没有持久化来源时不发默认零。 */
export function buildL5DisclosureSyncBodies(input: {
  variant: L5DisclosureVariant
  wpId: string
  applicableStandards?: readonly string[] | null
  state: L5DisclosureState
}) {
  const { variant, wpId, applicableStandards, state } = input
  const bodies: NonNullable<ReturnType<typeof buildL5SyncPayload>>[] = []
  if (state.mainSourceFound) {
    const main = buildL5SyncPayload(wpId, mainSnapshot(state, variant), applicableStandards)
    if (main) {
      const notes = variant === 'soe'
        ? [
            { section: 'l5-soe-special', title: '国资体系专项披露', text: state.soeSpecialNote.trim() },
            { section: 'l5-soe-related', title: '关联方长期应付款公允性说明', text: state.relatedPartyNote.trim() },
          ].filter((item) => item.text)
        : []
      if (notes.length) (main.sub_table_data as any)._note_texts = notes
      bodies.push(main)
    }
  }
  if (state.within1ySourceFound) {
    const within = buildL5Within1ySyncPayload(wpId, variant, l5Within1yRows(state), applicableStandards)
    if (within) bodies.push(within)
  }
  return bodies
}
