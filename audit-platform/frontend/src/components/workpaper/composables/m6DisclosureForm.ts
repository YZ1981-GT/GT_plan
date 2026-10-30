import type { ChecklistResponse } from './useM6FormData'
import type { M6DisclosureRow, M6Variant } from './m6NoteSectionMap'

export interface M6ListedRow {
  item: string
  currentPeriod: number
  priorPeriod: number
  ratio: string
  isFormula: boolean
  isSubtotal: boolean
  formulaDesc?: string
  key: string
}

export interface M6SoeRow {
  item: string
  priorYearEnd: number
  beginAdj: number
  beginBalance: number
  increase: number
  decrease: number
  endBalance: number
  isFormula: boolean
  isSubtotal: boolean
  formulaDesc?: string
  key: string
}

const LISTED_DEFS: ReadonlyArray<Pick<M6ListedRow, 'key' | 'item' | 'isFormula' | 'isSubtotal' | 'formulaDesc'>> = [
  { key: 'prior-end-before-adj', item: '调整前上期末未分配利润', isFormula: false, isSubtotal: false },
  { key: 'initial-adjustment-total', item: '调整期初未分配利润合计数（调增+，调减-）', isFormula: false, isSubtotal: false },
  { key: 'begin-after-adj', item: '调整后期初未分配利润', isFormula: true, isSubtotal: true, formulaDesc: '= 调整前上期末 + 期初调整合计' },
  { key: 'net-profit', item: '加：本期归属于母公司所有者的净利润', isFormula: false, isSubtotal: false },
  { key: 'surplus-cover-loss', item: '使用盈余公积弥补亏损', isFormula: false, isSubtotal: false },
  { key: 'capital-cover-loss', item: '使用资本公积弥补亏损', isFormula: false, isSubtotal: false },
  { key: 'other-adjustment', item: '其他调整', isFormula: false, isSubtotal: false },
  { key: 'statutory-surplus', item: '减：提取法定盈余公积', isFormula: false, isSubtotal: false },
  { key: 'discretionary-surplus', item: '提取任意盈余公积', isFormula: false, isSubtotal: false },
  { key: 'general-risk-reserve', item: '提取一般风险准备', isFormula: false, isSubtotal: false },
  { key: 'cash-dividend', item: '应付普通股股利', isFormula: false, isSubtotal: false },
  { key: 'other-equity-dividend', item: '应付其他权益持有者的股利', isFormula: false, isSubtotal: false },
  { key: 'stock-dividend', item: '转作股本的普通股股利', isFormula: false, isSubtotal: false },
  { key: 'end-retained', item: '期末未分配利润', isFormula: true, isSubtotal: true, formulaDesc: '= 调整后期初 + 增加项 - 提取及分配项' },
]

const SOE_DEFS: ReadonlyArray<Pick<M6SoeRow, 'key' | 'item' | 'isFormula' | 'isSubtotal' | 'formulaDesc'>> = [
  { key: 'prior-end', item: '上年年末余额', isFormula: false, isSubtotal: false },
  { key: 'initial-adjustment', item: '期初调整金额', isFormula: false, isSubtotal: false },
  { key: 'begin-retained', item: '本期期初余额', isFormula: true, isSubtotal: true, formulaDesc: '= 上年年末余额 + 期初调整金额' },
  { key: 'total-increase', item: '本期增加额', isFormula: true, isSubtotal: true, formulaDesc: '= 净利润转入 + 弥补亏损转入 + 其他调整' },
  { key: 'net-profit', item: '其中：本期净利润转入', isFormula: false, isSubtotal: false },
  { key: 'surplus-cover-loss', item: '盈余公积弥补亏损转入', isFormula: false, isSubtotal: false },
  { key: 'capital-cover-loss', item: '资本公积弥补亏损转入', isFormula: false, isSubtotal: false },
  { key: 'other-adjustment', item: '其他调整因素', isFormula: false, isSubtotal: false },
  { key: 'total-decrease', item: '本期减少额', isFormula: true, isSubtotal: true, formulaDesc: '= 提取盈余公积 + 风险准备 + 股利 + 转增资本 + 其他' },
  { key: 'surplus-extraction', item: '其中：本期提取盈余公积数', isFormula: false, isSubtotal: false },
  { key: 'general-risk-reserve', item: '本期提取一般风险准备', isFormula: false, isSubtotal: false },
  { key: 'cash-dividend', item: '本期分配现金股利数', isFormula: false, isSubtotal: false },
  { key: 'capital-conversion', item: '转增资本', isFormula: false, isSubtotal: false },
  { key: 'other-decrease', item: '其他减少', isFormula: false, isSubtotal: false },
  { key: 'end-retained', item: '本期期末余额', isFormula: true, isSubtotal: true, formulaDesc: '= 本期期初 + 本期增加 - 本期减少' },
]

const num = (value: unknown): number => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

export function createM6ListedRows(): M6ListedRow[] {
  return LISTED_DEFS.map((row) => ({ ...row, currentPeriod: 0, priorPeriod: 0, ratio: '' }))
}

export function createM6SoeRows(): M6SoeRow[] {
  return SOE_DEFS.map((row) => ({
    ...row, priorYearEnd: 0, beginAdj: 0, beginBalance: 0, increase: 0, decrease: 0, endBalance: 0,
  }))
}

function value(responses: ReadonlyMap<string, ChecklistResponse>, key: string): number | undefined {
  const raw = responses.get(key)?.remark
  if (raw == null || raw === '') return undefined
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : undefined
}

function text(responses: ReadonlyMap<string, ChecklistResponse>, key: string): string {
  return String(responses.get(key)?.remark ?? '')
}

export function recalcM6ListedRows(rows: M6ListedRow[]): M6ListedRow[] {
  const out = rows.map((row) => ({ ...row }))
  const byKey = new Map(out.map((row) => [row.key, row]))
  for (const field of ['currentPeriod', 'priorPeriod'] as const) {
    const begin = byKey.get('begin-after-adj')!
    begin[field] = num(byKey.get('prior-end-before-adj')?.[field]) + num(byKey.get('initial-adjustment-total')?.[field])
    const end = byKey.get('end-retained')!
    end[field] = begin[field]
      + num(byKey.get('net-profit')?.[field])
      + num(byKey.get('surplus-cover-loss')?.[field])
      + num(byKey.get('capital-cover-loss')?.[field])
      + num(byKey.get('other-adjustment')?.[field])
      - num(byKey.get('statutory-surplus')?.[field])
      - num(byKey.get('discretionary-surplus')?.[field])
      - num(byKey.get('general-risk-reserve')?.[field])
      - num(byKey.get('cash-dividend')?.[field])
      - num(byKey.get('other-equity-dividend')?.[field])
      - num(byKey.get('stock-dividend')?.[field])
  }
  return out
}

export function recalcM6SoeRows(rows: M6SoeRow[]): M6SoeRow[] {
  const out = rows.map((row) => ({ ...row }))
  const byKey = new Map(out.map((row) => [row.key, row]))
  const begin = byKey.get('begin-retained')!
  begin.beginBalance = num(byKey.get('prior-end')?.priorYearEnd) + num(byKey.get('initial-adjustment')?.beginAdj)
  begin.endBalance = begin.beginBalance
  const increase = byKey.get('total-increase')!
  increase.increase = ['net-profit', 'surplus-cover-loss', 'capital-cover-loss', 'other-adjustment']
    .reduce((sum, key) => sum + num(byKey.get(key)?.increase), 0)
  const decrease = byKey.get('total-decrease')!
  decrease.decrease = ['surplus-extraction', 'general-risk-reserve', 'cash-dividend', 'capital-conversion', 'other-decrease']
    .reduce((sum, key) => sum + num(byKey.get(key)?.decrease), 0)
  const end = byKey.get('end-retained')!
  end.endBalance = begin.beginBalance + increase.increase - decrease.decrease
  for (const row of out) {
    if (!row.isFormula) row.endBalance = row.beginBalance + row.increase - row.decrease
  }
  return out
}

export function restoreM6ListedRows(responses: ReadonlyMap<string, ChecklistResponse>): M6ListedRow[] {
  const rows = createM6ListedRows()
  for (const row of rows) {
    if (row.isFormula) continue
    for (const field of ['currentPeriod', 'priorPeriod'] as const) {
      const saved = value(responses, `M6-disclosure-listed-${row.key}-${field}`)
      if (saved !== undefined) row[field] = saved
    }
    row.ratio = text(responses, `M6-disclosure-listed-${row.key}-ratio`)
  }
  // 旧结构无合计调整键时，迁移三项期初调整；旧“其他扣减”按负数并入期间其他调整。
  if (!responses.has('M6-disclosure-listed-initial-adjustment-total-currentPeriod')) {
    for (const field of ['currentPeriod', 'priorPeriod'] as const) {
      rows.find((row) => row.key === 'initial-adjustment-total')![field] =
        ['policy-change-adj', 'error-correction-adj', 'other-adj']
          .reduce((sum, key) => sum + num(value(responses, `M6-disclosure-listed-${key}-${field}`)), 0)
      rows.find((row) => row.key === 'other-adjustment')![field] =
        num(value(responses, `M6-disclosure-listed-oci-transfer-${field}`))
        - num(value(responses, `M6-disclosure-listed-other-deduction-${field}`))
    }
  }
  return recalcM6ListedRows(rows)
}

export function restoreM6SoeRows(responses: ReadonlyMap<string, ChecklistResponse>): M6SoeRow[] {
  const rows = createM6SoeRows()
  for (const row of rows) {
    if (row.isFormula) continue
    for (const field of ['priorYearEnd', 'beginAdj', 'increase', 'decrease'] as const) {
      const saved = value(responses, `M6-disclosure-soe-${row.key}-${field}`)
      if (saved !== undefined) row[field] = saved
    }
  }
  // 旧结构迁移：期初行、政策/差错调整、两类盈余公积和股利。
  if (!responses.has('M6-disclosure-soe-prior-end-priorYearEnd')) {
    const prior = rows.find((row) => row.key === 'prior-end')!
    prior.priorYearEnd = num(value(responses, 'M6-disclosure-soe-begin-retained-priorYearEnd'))
    const adjustment = rows.find((row) => row.key === 'initial-adjustment')!
    adjustment.beginAdj = num(value(responses, 'M6-disclosure-soe-begin-retained-beginAdj'))
      + num(value(responses, 'M6-disclosure-soe-policy-change-beginAdj'))
      + num(value(responses, 'M6-disclosure-soe-error-correction-beginAdj'))
    const extraction = rows.find((row) => row.key === 'surplus-extraction')!
    extraction.decrease = num(value(responses, 'M6-disclosure-soe-statutory-surplus-decrease'))
      + num(value(responses, 'M6-disclosure-soe-discretionary-surplus-decrease'))
    rows.find((row) => row.key === 'cash-dividend')!.decrease =
      num(value(responses, 'M6-disclosure-soe-dividend-decrease'))
  }
  return recalcM6SoeRows(rows)
}

export function m6WireRows(variant: M6Variant, rows: readonly M6ListedRow[] | readonly M6SoeRow[]): M6DisclosureRow[] {
  if (variant === 'listed') {
    return (rows as readonly M6ListedRow[]).map((row) => ({
      label: row.item, current: row.currentPeriod, prior: row.priorPeriod, ratio: row.ratio,
    }))
  }
  return (rows as readonly M6SoeRow[]).map((row) => {
    let current = row.increase - row.decrease
    if (row.key === 'prior-end') current = row.priorYearEnd
    else if (row.key === 'initial-adjustment') current = row.beginAdj
    else if (row.key === 'begin-retained') current = row.beginBalance
    else if (row.key === 'total-increase' || ['net-profit', 'surplus-cover-loss', 'capital-cover-loss', 'other-adjustment'].includes(row.key)) current = row.increase
    else if (row.key === 'total-decrease' || ['surplus-extraction', 'general-risk-reserve', 'cash-dividend', 'capital-conversion', 'other-decrease'].includes(row.key)) current = row.decrease
    else if (row.key === 'end-retained') current = row.endBalance
    return { label: row.item, current, prior: row.priorYearEnd }
  })
}

export function m6NoteText(responses: ReadonlyMap<string, ChecklistResponse>, variant: M6Variant): string {
  const keys = variant === 'listed'
    ? ['M6-disclosure-listed-policy-change', 'M6-disclosure-listed-distribution-plan', 'M6-disclosure-listed-subsidiary']
    : ['M6-disclosure-soe-risk-reserve', 'M6-disclosure-soe-distribution']
  return keys.map((key) => text(responses, key).trim()).filter(Boolean).join('\n\n')
}
