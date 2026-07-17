/**
 * F2-43 制造费用明细表 — 费用项目×月度（对齐致同源模板）
 *
 * 行：工资、福利费、修理费…其他 + 合计
 * 列：1–12月 + 合计 + 上年度 + 变动率
 */
import { calcSubtotal, calcChangeRate } from './useF2InvValFormulaEngine'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'
import { parseRows, type OverheadRow } from './useF2ProductionCostFormulas'

export const OVERHEAD_MONTH_KEYS = [
  '01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12',
] as const

export type OverheadMonthKey = (typeof OVERHEAD_MONTH_KEYS)[number]

export const OVERHEAD_ITEM_DEFS = [
  { key: 'wages', label: '工资' },
  { key: 'welfare', label: '福利费' },
  { key: 'repair', label: '修理费' },
  { key: 'office', label: '办公费' },
  { key: 'travel', label: '差旅费' },
  { key: 'freight', label: '运费' },
  { key: 'depreciation', label: '折旧费' },
  { key: 'laborProtection', label: '劳动保护费' },
  { key: 'materialConsume', label: '机物料消耗' },
  { key: 'lowValueAmort', label: '低值易耗品摊销' },
  { key: 'utilities', label: '水电费' },
  { key: 'rent', label: '租赁费' },
  { key: 'other', label: '其他' },
] as const

export type OverheadItemKey = (typeof OVERHEAD_ITEM_DEFS)[number]['key']

export interface OverheadMatrixRow {
  key: OverheadItemKey | 'total'
  label: string
  kind: 'item' | 'total'
  months: Record<OverheadMonthKey, number>
  priorYear: number
  changeReason: string
  total: number
  changeRate: number | '' | 'N/A'
}

export interface OverheadMatrixData {
  rows: OverheadMatrixRow[]
}

function emptyMonths(): Record<OverheadMonthKey, number> {
  return Object.fromEntries(OVERHEAD_MONTH_KEYS.map((k) => [k, 0])) as Record<OverheadMonthKey, number>
}

export function defaultOverheadMatrix(): OverheadMatrixData {
  return {
    rows: OVERHEAD_ITEM_DEFS.map((d) => ({
      key: d.key,
      label: d.label,
      kind: 'item' as const,
      months: emptyMonths(),
      priorYear: 0,
      changeReason: '',
      total: 0,
      changeRate: '' as const,
    })),
  }
}

function n(v: number): number {
  return Number.isFinite(v) ? v : 0
}

export function enrichOverheadMatrix(data: OverheadMatrixData): OverheadMatrixData {
  const itemRows = data.rows.filter((r) => r.kind === 'item')
  const monthTotals = Object.fromEntries(
    OVERHEAD_MONTH_KEYS.map((mk) => [
      mk,
      calcSubtotal(itemRows.map((r) => n(r.months[mk]))),
    ]),
  ) as Record<OverheadMonthKey, number>
  const grandTotal = calcSubtotal(OVERHEAD_MONTH_KEYS.map((mk) => monthTotals[mk]))
  const priorTotal = calcSubtotal(itemRows.map((r) => n(r.priorYear)))

  const enrichedItems = itemRows.map((r) => {
    const total = calcSubtotal(OVERHEAD_MONTH_KEYS.map((mk) => n(r.months[mk])))
    return {
      ...r,
      total,
      changeRate: calcChangeRate(r.priorYear, total),
    }
  })

  const totalRow: OverheadMatrixRow = {
    key: 'total',
    label: '合计',
    kind: 'total',
    months: monthTotals,
    priorYear: priorTotal,
    changeReason: '',
    total: grandTotal,
    changeRate: calcChangeRate(priorTotal, grandTotal),
  }

  return { rows: [...enrichedItems, totalRow] }
}

export function sumOverheadAnnual(data: OverheadMatrixData): number {
  return enrichOverheadMatrix(data).rows.find((r) => r.key === 'total')?.total ?? 0
}

const LABEL_TO_KEY = new Map(OVERHEAD_ITEM_DEFS.map((d) => [d.label, d.key]))

export function migrateToOverheadMatrix(legacy: unknown): OverheadMatrixData | null {
  if (!legacy) return null

  if (typeof legacy === 'object' && legacy !== null && 'rows' in legacy) {
    const data = legacy as OverheadMatrixData
    if (Array.isArray(data.rows) && data.rows[0]?.months) return data
  }

  if (Array.isArray(legacy) && legacy.length) {
    const first = legacy[0] as Record<string, unknown>
    if ('actualAmt' in first || 'budgetAmt' in first) {
      const matrix = defaultOverheadMatrix()
      for (const r of legacy as OverheadRow[]) {
        const key = LABEL_TO_KEY.get(r.costItem) || 'other'
        const row = matrix.rows.find((x) => x.key === key)
        if (row) {
          row.months['12'] = n(r.actualAmt)
          row.priorYear = n(r.budgetAmt) || row.priorYear
        }
      }
      return matrix
    }
  }

  return null
}

export function readF2_43OverheadTotal(allResponses: Map<string, ChecklistResponse>): number {
  const raw = readValRowJson(allResponses.get('F2-43-rows'))
  if (!raw) return 0
  try {
    const parsed = JSON.parse(raw)
    const matrix = migrateToOverheadMatrix(parsed)
    if (matrix) return sumOverheadAnnual(matrix)
    const legacy = parseRows<OverheadRow>(raw, () => [])
    return calcSubtotal(legacy.map((r) => r.actualAmt))
  } catch {
    return 0
  }
}

export const F2_43_OBJECTIVES = [
  '制造费用已发生且已记录，并已记录在正确的账户中。',
  '所有应记录的制造费用均已记录，包括所有已发生的披露事项。',
  '制造费用已按恰当的金额记录，所有必要的计价或分摊调整均已记录，并已作出恰当列报和描述。',
] as const

export const F2_43_PROCEDURE =
  '获取本期和上期制造费用明细表，与折旧、摊销等明细表核对一致性；评价制造费用分配方法；关注各月异常波动。'

export const F2_43_TIPS = [
  '核对制造费用汇总表金额是否正确，并与机物料消耗、工资费用分配、折旧、摊销等明细表勾稽。',
  '获取并评价制造费用分配标准及计算方法是否合理，以合理保证计入产品的直接人工和制造费用正确，必要时重新计算。',
  '关注是否将不应计入产品成本的费用（非正常消耗、与存货达到目前场所和状态无关的费用等）计入制造费用。',
  '存货成本应仅包括使存货达到目前场所和状态所发生的支出（不含非正常浪费、完工后仓储费、销售相关运费及不应资本化的借款费用）。',
] as const

export const OVERHEAD_MONTH_LABELS = [
  { key: '01', label: '1月' }, { key: '02', label: '2月' }, { key: '03', label: '3月' },
  { key: '04', label: '4月' }, { key: '05', label: '5月' }, { key: '06', label: '6月' },
  { key: '07', label: '7月' }, { key: '08', label: '8月' }, { key: '09', label: '9月' },
  { key: '10', label: '10月' }, { key: '11', label: '11月' }, { key: '12', label: '12月' },
] as const
