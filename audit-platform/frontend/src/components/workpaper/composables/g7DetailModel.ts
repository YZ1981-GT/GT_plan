/**
 * G7-2 长期股权投资明细表 — 原始模板等价数据模型。
 *
 * 模板分为成本法、权益法、减值准备三大区块；每个区块均保留
 * 未审数 → 账项调整(AJE) → 重分类调整(RJE) → 审定数的完整桥接。
 */
import { useDecimalCalc } from '@/composables/useDecimalCalc'

const amountCalc = useDecimalCalc({ dp: 2 })

function amountSum(...values: number[]): number {
  return Number(amountCalc.sum(...values))
}

function amountSub(a: number, b: number): number {
  return Number(amountCalc.sub(a, b))
}

export type G7Relationship = 'subsidiary' | 'joint_venture' | 'associate'
export type G7DetailSection = 'cost' | 'equity' | 'impairment'

export interface G7CommonInvestmentFields {
  id: string
  section: G7DetailSection
  seq: number
  investeeName: string
  initialInvestmentCost: number
  investmentRatio: number
  investmentDate: string
  investmentMethod: string
}

export interface G7CostRow extends G7CommonInvestmentFields {
  section: 'cost'
  cashDividend: number
  openingRatio: number
  openingAmount: number
  increaseRatio: number
  increaseAmount: number
  increaseIndex: string
  decreaseRatio: number
  decreaseAmount: number
  decreaseIndex: string
  closingRatio: number
  closingAmount: number
  openingAje: number
  openingRje: number
  ajeIncrease: number
  ajeDecrease: number
  rjeIncrease: number
  rjeDecrease: number
  auditedOpeningRatio: number
  auditedOpeningAmount: number
  auditedIncreaseRatio: number
  auditedIncreaseAmount: number
  auditedDecreaseRatio: number
  auditedDecreaseAmount: number
  auditedClosingRatio: number
  auditedClosingAmount: number
}

export interface G7EquityAdjustments {
  openingAje: number
  openingRje: number
  ajeCostIncrease: number
  ajeProfitLoss: number
  ajeOci: number
  ajeOtherEquity: number
  ajeOtherIncrease: number
  ajeCostDecrease: number
  ajeDividend: number
  ajeOtherDecrease: number
  rjeCostIncrease: number
  rjeProfitLoss: number
  rjeOci: number
  rjeOtherEquity: number
  rjeOtherIncrease: number
  rjeCostDecrease: number
  rjeDividend: number
  rjeOtherDecrease: number
}

export interface G7EquityRow extends G7CommonInvestmentFields, G7EquityAdjustments {
  section: 'equity'
  relationship: 'joint_venture' | 'associate'
  openingRatio: number
  openingAmount: number
  increaseRatio: number
  costIncrease: number
  profitLossAdjustment: number
  otherComprehensiveIncome: number
  otherEquityChange: number
  equityIncreaseSubtotal: number
  otherIncrease: number
  decreaseRatio: number
  costDecrease: number
  dividendReceived: number
  otherDecrease: number
  closingRatio: number
  closingAmount: number
  auditedOpeningRatio: number
  auditedOpeningAmount: number
  auditedIncreaseRatio: number
  auditedCostIncrease: number
  auditedProfitLoss: number
  auditedOci: number
  auditedOtherEquity: number
  auditedEquityIncreaseSubtotal: number
  auditedOtherIncrease: number
  auditedDecreaseRatio: number
  auditedCostDecrease: number
  auditedDividend: number
  auditedOtherDecrease: number
  auditedClosingRatio: number
  auditedClosingAmount: number
}

export interface G7ImpairmentRow extends G7CommonInvestmentFields {
  section: 'impairment'
  sourceId: string
  relationship: G7Relationship
  openingAmount: number
  increaseAmount: number
  decreaseAmount: number
  closingAmount: number
  remark: string
  openingAje: number
  openingRje: number
  ajeIncrease: number
  ajeDecrease: number
  rjeIncrease: number
  rjeDecrease: number
  auditedOpeningAmount: number
  auditedIncreaseAmount: number
  auditedDecreaseAmount: number
  auditedClosingAmount: number
}

export type G7DetailStoredRow = G7CostRow | G7EquityRow | G7ImpairmentRow

export interface G7DetailState {
  costRows: G7CostRow[]
  equityRows: G7EquityRow[]
  impairmentRows: G7ImpairmentRow[]
}

export interface G7MovementSummary {
  opening: number
  increase: number
  decrease: number
  closing: number
}

export interface G7AdjustmentSummary extends G7MovementSummary {
  ajeOpening: number
  ajeIncrease: number
  ajeDecrease: number
  rjeOpening: number
  rjeIncrease: number
  rjeDecrease: number
}

export interface G7DetailSummary {
  cost: G7AdjustmentSummary
  jointVenture: G7AdjustmentSummary
  associate: G7AdjustmentSummary
  gross: G7MovementSummary
  impairment: G7MovementSummary
  net: G7MovementSummary
}

export function g7Num(value: unknown): number {
  if (value == null || value === '') return 0
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

function uid(prefix: string): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `${prefix}-${crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

export function createG7CostRow(seq: number, investeeName = ''): G7CostRow {
  return recalcG7CostRow({
    id: uid('g7-cost'),
    section: 'cost',
    seq,
    investeeName,
    initialInvestmentCost: 0,
    investmentRatio: 0,
    investmentDate: '',
    investmentMethod: '',
    cashDividend: 0,
    openingRatio: 0,
    openingAmount: 0,
    increaseRatio: 0,
    increaseAmount: 0,
    increaseIndex: '',
    decreaseRatio: 0,
    decreaseAmount: 0,
    decreaseIndex: '',
    closingRatio: 0,
    closingAmount: 0,
    openingAje: 0,
    openingRje: 0,
    ajeIncrease: 0,
    ajeDecrease: 0,
    rjeIncrease: 0,
    rjeDecrease: 0,
    auditedOpeningRatio: 0,
    auditedOpeningAmount: 0,
    auditedIncreaseRatio: 0,
    auditedIncreaseAmount: 0,
    auditedDecreaseRatio: 0,
    auditedDecreaseAmount: 0,
    auditedClosingRatio: 0,
    auditedClosingAmount: 0,
  })
}

export function createG7EquityRow(
  seq: number,
  investeeName = '',
  relationship: 'joint_venture' | 'associate' = 'joint_venture',
): G7EquityRow {
  return recalcG7EquityRow({
    id: uid('g7-equity'),
    section: 'equity',
    seq,
    investeeName,
    relationship,
    initialInvestmentCost: 0,
    investmentRatio: 0,
    investmentDate: '',
    investmentMethod: '',
    openingRatio: 0,
    openingAmount: 0,
    increaseRatio: 0,
    costIncrease: 0,
    profitLossAdjustment: 0,
    otherComprehensiveIncome: 0,
    otherEquityChange: 0,
    equityIncreaseSubtotal: 0,
    otherIncrease: 0,
    decreaseRatio: 0,
    costDecrease: 0,
    dividendReceived: 0,
    otherDecrease: 0,
    closingRatio: 0,
    closingAmount: 0,
    openingAje: 0,
    openingRje: 0,
    ajeCostIncrease: 0,
    ajeProfitLoss: 0,
    ajeOci: 0,
    ajeOtherEquity: 0,
    ajeOtherIncrease: 0,
    ajeCostDecrease: 0,
    ajeDividend: 0,
    ajeOtherDecrease: 0,
    rjeCostIncrease: 0,
    rjeProfitLoss: 0,
    rjeOci: 0,
    rjeOtherEquity: 0,
    rjeOtherIncrease: 0,
    rjeCostDecrease: 0,
    rjeDividend: 0,
    rjeOtherDecrease: 0,
    auditedOpeningRatio: 0,
    auditedOpeningAmount: 0,
    auditedIncreaseRatio: 0,
    auditedCostIncrease: 0,
    auditedProfitLoss: 0,
    auditedOci: 0,
    auditedOtherEquity: 0,
    auditedEquityIncreaseSubtotal: 0,
    auditedOtherIncrease: 0,
    auditedDecreaseRatio: 0,
    auditedCostDecrease: 0,
    auditedDividend: 0,
    auditedOtherDecrease: 0,
    auditedClosingRatio: 0,
    auditedClosingAmount: 0,
  })
}

export function createG7ImpairmentRow(
  source: G7CostRow | G7EquityRow,
  seq: number,
): G7ImpairmentRow {
  const relationship: G7Relationship = source.section === 'cost'
    ? 'subsidiary'
    : source.relationship
  return recalcG7ImpairmentRow({
    id: uid('g7-impairment'),
    section: 'impairment',
    sourceId: source.id,
    seq,
    investeeName: source.investeeName,
    relationship,
    initialInvestmentCost: source.initialInvestmentCost,
    investmentRatio: source.investmentRatio,
    investmentDate: source.investmentDate,
    investmentMethod: source.investmentMethod,
    openingAmount: 0,
    increaseAmount: 0,
    decreaseAmount: 0,
    closingAmount: 0,
    remark: '',
    openingAje: 0,
    openingRje: 0,
    ajeIncrease: 0,
    ajeDecrease: 0,
    rjeIncrease: 0,
    rjeDecrease: 0,
    auditedOpeningAmount: 0,
    auditedIncreaseAmount: 0,
    auditedDecreaseAmount: 0,
    auditedClosingAmount: 0,
  })
}

export function recalcG7CostRow(row: G7CostRow): G7CostRow {
  row.closingRatio = g7Num(row.openingRatio) + g7Num(row.increaseRatio) - g7Num(row.decreaseRatio)
  row.closingAmount = amountSub(
    amountSum(g7Num(row.openingAmount), g7Num(row.increaseAmount)),
    g7Num(row.decreaseAmount),
  )
  row.auditedOpeningRatio = g7Num(row.openingRatio)
  row.auditedOpeningAmount = amountSum(
    g7Num(row.openingAmount), g7Num(row.openingAje), g7Num(row.openingRje),
  )
  row.auditedIncreaseRatio = g7Num(row.increaseRatio)
  row.auditedIncreaseAmount = amountSum(
    g7Num(row.increaseAmount), g7Num(row.ajeIncrease), g7Num(row.rjeIncrease),
  )
  row.auditedDecreaseRatio = g7Num(row.decreaseRatio)
  row.auditedDecreaseAmount = amountSum(
    g7Num(row.decreaseAmount), g7Num(row.ajeDecrease), g7Num(row.rjeDecrease),
  )
  row.auditedClosingRatio = row.auditedOpeningRatio + row.auditedIncreaseRatio - row.auditedDecreaseRatio
  row.auditedClosingAmount = amountSub(
    amountSum(row.auditedOpeningAmount, row.auditedIncreaseAmount),
    row.auditedDecreaseAmount,
  )
  return row
}

export function recalcG7EquityRow(row: G7EquityRow): G7EquityRow {
  row.equityIncreaseSubtotal = amountSum(
    g7Num(row.profitLossAdjustment),
    g7Num(row.otherComprehensiveIncome),
    g7Num(row.otherEquityChange),
  )
  row.closingRatio = g7Num(row.openingRatio) + g7Num(row.increaseRatio) - g7Num(row.decreaseRatio)
  row.closingAmount = amountSub(
    amountSub(
      amountSub(
        amountSum(
          g7Num(row.openingAmount),
          g7Num(row.costIncrease),
          row.equityIncreaseSubtotal,
          g7Num(row.otherIncrease),
        ),
        g7Num(row.costDecrease),
      ),
      g7Num(row.dividendReceived),
    ),
    g7Num(row.otherDecrease),
  )

  row.auditedOpeningRatio = g7Num(row.openingRatio)
  row.auditedOpeningAmount = amountSum(
    g7Num(row.openingAmount), g7Num(row.openingAje), g7Num(row.openingRje),
  )
  row.auditedIncreaseRatio = g7Num(row.increaseRatio)
  row.auditedCostIncrease = amountSum(
    g7Num(row.costIncrease), g7Num(row.ajeCostIncrease), g7Num(row.rjeCostIncrease),
  )
  row.auditedProfitLoss = amountSum(
    g7Num(row.profitLossAdjustment), g7Num(row.ajeProfitLoss), g7Num(row.rjeProfitLoss),
  )
  row.auditedOci = amountSum(
    g7Num(row.otherComprehensiveIncome), g7Num(row.ajeOci), g7Num(row.rjeOci),
  )
  row.auditedOtherEquity = amountSum(
    g7Num(row.otherEquityChange), g7Num(row.ajeOtherEquity), g7Num(row.rjeOtherEquity),
  )
  row.auditedEquityIncreaseSubtotal = amountSum(
    row.auditedProfitLoss, row.auditedOci, row.auditedOtherEquity,
  )
  row.auditedOtherIncrease = amountSum(
    g7Num(row.otherIncrease), g7Num(row.ajeOtherIncrease), g7Num(row.rjeOtherIncrease),
  )
  row.auditedDecreaseRatio = g7Num(row.decreaseRatio)
  row.auditedCostDecrease = amountSum(
    g7Num(row.costDecrease), g7Num(row.ajeCostDecrease), g7Num(row.rjeCostDecrease),
  )
  row.auditedDividend = amountSum(
    g7Num(row.dividendReceived), g7Num(row.ajeDividend), g7Num(row.rjeDividend),
  )
  row.auditedOtherDecrease = amountSum(
    g7Num(row.otherDecrease), g7Num(row.ajeOtherDecrease), g7Num(row.rjeOtherDecrease),
  )
  row.auditedClosingRatio = row.auditedOpeningRatio + row.auditedIncreaseRatio - row.auditedDecreaseRatio
  // 原表 BB = AO + AQ + AU - AX - AY；AV/AZ“其他”列保留展示和调整轨迹，
  // 但不进入审定期末公式。
  row.auditedClosingAmount = amountSub(
    amountSub(
      amountSum(row.auditedOpeningAmount, row.auditedCostIncrease, row.auditedEquityIncreaseSubtotal),
      row.auditedCostDecrease,
    ),
    row.auditedDividend,
  )
  return row
}

export function recalcG7ImpairmentRow(row: G7ImpairmentRow): G7ImpairmentRow {
  row.closingAmount = amountSub(
    amountSum(g7Num(row.openingAmount), g7Num(row.increaseAmount)),
    g7Num(row.decreaseAmount),
  )
  row.auditedOpeningAmount = amountSum(
    g7Num(row.openingAmount), g7Num(row.openingAje), g7Num(row.openingRje),
  )
  row.auditedIncreaseAmount = amountSum(
    g7Num(row.increaseAmount), g7Num(row.ajeIncrease), g7Num(row.rjeIncrease),
  )
  row.auditedDecreaseAmount = amountSum(
    g7Num(row.decreaseAmount), g7Num(row.ajeDecrease), g7Num(row.rjeDecrease),
  )
  row.auditedClosingAmount = amountSub(
    amountSum(row.auditedOpeningAmount, row.auditedIncreaseAmount),
    row.auditedDecreaseAmount,
  )
  return row
}

export function recalcG7DetailRow(row: G7DetailStoredRow): G7DetailStoredRow {
  if (row.section === 'cost') return recalcG7CostRow(row)
  if (row.section === 'equity') return recalcG7EquityRow(row)
  return recalcG7ImpairmentRow(row)
}

function mergeRow<T extends G7DetailStoredRow>(base: T, raw: Record<string, unknown>): T {
  Object.assign(base, raw)
  base.id = String(raw.id || base.id)
  base.investeeName = String(raw.investeeName ?? raw.investee_name ?? base.investeeName)
  return recalcG7DetailRow(base) as T
}

function migrateLegacyRow(raw: Record<string, unknown>, seq: number): G7CostRow | G7EquityRow {
  const controlType = String(raw.controlType || 'subsidiary')
  if (controlType === 'joint_venture' || controlType === 'associate') {
    return mergeRow(createG7EquityRow(seq, String(raw.investeeName || ''), controlType), {
      initialInvestmentCost: raw.openingInvestCost,
      investmentRatio: raw.holdingRatio,
      openingRatio: raw.holdingRatio,
      openingAmount: g7Num(raw.openingInvestCost) + g7Num(raw.openingEquityAdj),
      costIncrease: raw.increaseNewInvest,
      profitLossAdjustment: raw.increaseEquityMethod,
      otherComprehensiveIncome: raw.otherComprehensiveIncome,
      otherEquityChange: raw.otherEquityChange,
      costDecrease: raw.decreaseDisposal,
      dividendReceived: raw.profitDistribution,
      openingAje: 0,
      ajeOtherIncrease: raw.auditAdjustment,
    })
  }
  return mergeRow(createG7CostRow(seq, String(raw.investeeName || '')), {
    initialInvestmentCost: raw.openingInvestCost,
    investmentRatio: raw.holdingRatio,
    openingRatio: raw.holdingRatio,
    openingAmount: raw.openingInvestCost,
    increaseAmount: raw.increaseNewInvest,
    decreaseAmount: raw.decreaseDisposal,
    cashDividend: raw.dividendIncome,
    ajeIncrease: raw.auditAdjustment,
  })
}

export function normalizeG7DetailRows(payload: unknown): G7DetailState {
  const rows: Record<string, unknown>[] = Array.isArray(payload)
    ? payload as Record<string, unknown>[]
    : Array.isArray((payload as any)?.rows)
      ? (payload as any).rows
      : []
  const state: G7DetailState = { costRows: [], equityRows: [], impairmentRows: [] }

  for (const raw of rows) {
    const section = String(raw.section || '')
    if (section === 'cost') {
      state.costRows.push(mergeRow(
        createG7CostRow(state.costRows.length + 1, String(raw.investeeName || '')),
        raw,
      ))
    } else if (section === 'equity') {
      const relationship = raw.relationship === 'associate' ? 'associate' : 'joint_venture'
      state.equityRows.push(mergeRow(
        createG7EquityRow(state.equityRows.length + 1, String(raw.investeeName || ''), relationship),
        raw,
      ))
    } else if (section === 'impairment') {
      const shell = createG7CostRow(1, String(raw.investeeName || ''))
      state.impairmentRows.push(mergeRow(
        createG7ImpairmentRow(shell, state.impairmentRows.length + 1),
        raw,
      ))
    } else if (raw.investeeName || raw.investee_name) {
      const migrated = migrateLegacyRow(raw, state.costRows.length + state.equityRows.length + 1)
      if (migrated.section === 'cost') state.costRows.push(migrated)
      else state.equityRows.push(migrated)
    }
  }

  resequenceG7DetailState(state)
  syncG7ImpairmentRows(state)
  return state
}

export function resequenceG7DetailState(state: G7DetailState): void {
  state.costRows.forEach((row, i) => { row.seq = i + 1 })
  const jv = state.equityRows.filter(row => row.relationship === 'joint_venture')
  const associate = state.equityRows.filter(row => row.relationship === 'associate')
  jv.forEach((row, i) => { row.seq = i + 1 })
  associate.forEach((row, i) => { row.seq = i + 1 })
  state.impairmentRows.forEach((row, i) => { row.seq = i + 1 })
}

export function syncG7ImpairmentRows(state: G7DetailState): void {
  const sources: Array<G7CostRow | G7EquityRow> = [...state.costRows, ...state.equityRows]
  const validIds = new Set(sources.map(row => row.id))
  state.impairmentRows = state.impairmentRows.filter(row => validIds.has(row.sourceId))
  for (const source of sources) {
    let row = state.impairmentRows.find(item => item.sourceId === source.id)
    if (!row) {
      row = createG7ImpairmentRow(source, state.impairmentRows.length + 1)
      state.impairmentRows.push(row)
    }
    row.investeeName = source.investeeName
    row.initialInvestmentCost = source.initialInvestmentCost
    row.investmentRatio = source.investmentRatio
    row.investmentDate = source.investmentDate
    row.investmentMethod = source.investmentMethod
    row.relationship = source.section === 'cost' ? 'subsidiary' : source.relationship
    recalcG7ImpairmentRow(row)
  }
  resequenceG7DetailState(state)
}

export function serializeG7DetailState(state: G7DetailState): G7DetailStoredRow[] {
  return [
    ...state.costRows.map(row => recalcG7CostRow({ ...row })),
    ...state.equityRows.map(row => recalcG7EquityRow({ ...row })),
    ...state.impairmentRows.map(row => recalcG7ImpairmentRow({ ...row })),
  ]
}

function sum(rows: G7DetailStoredRow[], field: string): number {
  return amountSum(...rows.map(row => g7Num((row as any)[field])))
}

function costSummary(rows: G7CostRow[]): G7AdjustmentSummary {
  return {
    opening: sum(rows, 'auditedOpeningAmount'),
    increase: sum(rows, 'auditedIncreaseAmount'),
    decrease: sum(rows, 'auditedDecreaseAmount'),
    closing: sum(rows, 'auditedClosingAmount'),
    ajeOpening: sum(rows, 'openingAje'),
    ajeIncrease: sum(rows, 'ajeIncrease'),
    ajeDecrease: sum(rows, 'ajeDecrease'),
    rjeOpening: sum(rows, 'openingRje'),
    rjeIncrease: sum(rows, 'rjeIncrease'),
    rjeDecrease: sum(rows, 'rjeDecrease'),
  }
}

function equitySummary(rows: G7EquityRow[]): G7AdjustmentSummary {
  return {
    opening: sum(rows, 'auditedOpeningAmount'),
    increase: amountSum(...rows.flatMap(row =>
      [row.auditedCostIncrease, row.auditedEquityIncreaseSubtotal])),
    decrease: amountSum(...rows.flatMap(row =>
      [row.auditedCostDecrease, row.auditedDividend])),
    closing: sum(rows, 'auditedClosingAmount'),
    ajeOpening: sum(rows, 'openingAje'),
    ajeIncrease: amountSum(...rows.flatMap(row =>
      [row.ajeCostIncrease, row.ajeProfitLoss, row.ajeOci, row.ajeOtherEquity])),
    ajeDecrease: amountSum(...rows.flatMap(row =>
      [row.ajeCostDecrease, row.ajeDividend])),
    rjeOpening: sum(rows, 'openingRje'),
    rjeIncrease: amountSum(...rows.flatMap(row =>
      [row.rjeCostIncrease, row.rjeProfitLoss, row.rjeOci, row.rjeOtherEquity])),
    rjeDecrease: amountSum(...rows.flatMap(row =>
      [row.rjeCostDecrease, row.rjeDividend])),
  }
}

function movement(rows: G7DetailStoredRow[], prefix = 'audited'): G7MovementSummary {
  const title = prefix === 'audited' ? 'audited' : ''
  const field = (name: string) => `${title}${title ? name[0].toUpperCase() + name.slice(1) : name}Amount`
  return {
    opening: sum(rows, field('opening')),
    increase: sum(rows, field('increase')),
    decrease: sum(rows, field('decrease')),
    closing: sum(rows, field('closing')),
  }
}

export function calcG7DetailSummary(state: G7DetailState): G7DetailSummary {
  const cost = costSummary(state.costRows)
  const jointVenture = equitySummary(
    state.equityRows.filter(row => row.relationship === 'joint_venture'),
  )
  const associate = equitySummary(
    state.equityRows.filter(row => row.relationship === 'associate'),
  )
  const gross: G7MovementSummary = {
    opening: amountSum(cost.opening, jointVenture.opening, associate.opening),
    increase: amountSum(cost.increase, jointVenture.increase, associate.increase),
    decrease: amountSum(cost.decrease, jointVenture.decrease, associate.decrease),
    closing: amountSum(cost.closing, jointVenture.closing, associate.closing),
  }
  const impairment = movement(state.impairmentRows)
  const net: G7MovementSummary = {
    opening: amountSub(gross.opening, impairment.opening),
    increase: amountSub(gross.increase, impairment.increase),
    decrease: amountSub(gross.decrease, impairment.decrease),
    closing: amountSub(gross.closing, impairment.closing),
  }
  return { cost, jointVenture, associate, gross, impairment, net }
}
