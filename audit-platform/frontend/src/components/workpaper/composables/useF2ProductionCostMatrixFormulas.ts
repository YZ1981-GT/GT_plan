/**
 * F2-41 生产成本明细表 — 项目×月度矩阵（对齐致同源模板）
 *
 * 行：期初余额 → 本期增加(原材料/燃料动力/人工/制造费用/其他) → 增加合计
 *     → 结转产成品/半成品 → 月末余额
 * 列：1–12月 + 合计 + 上年度 + 变动率 + 变动原因
 * 月末余额 = 期初 + 增加合计 − 结转产成品 − 结转半成品（逐月；2月起期初=上月末）
 */
import { calcSubtotal, calcChangeRate } from './useF2InvValFormulaEngine'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'
import {
  calcProductionPeriodEnd,
  enrichProductionRow,
  parseRows,
  type ProductionCostRow,
} from './useF2ProductionCostFormulas'

export const PROD_COST_MONTH_KEYS = [
  '01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12',
] as const

export type ProdCostMonthKey = (typeof PROD_COST_MONTH_KEYS)[number]

export const INCREASE_ROW_KEYS = [
  'rawMaterial',
  'fuelPower',
  'labor',
  'overhead',
  'other',
] as const

export type ProdCostRowKey =
  | 'opening'
  | (typeof INCREASE_ROW_KEYS)[number]
  | 'increaseTotal'
  | 'transferFG'
  | 'transferWIP'
  | 'monthEnd'

export interface ProdCostRowDef {
  key: ProdCostRowKey
  label: string
  kind: 'opening' | 'increase' | 'computed' | 'transfer' | 'ending'
  indent?: boolean
}

export const PROD_COST_ROW_DEFS: ProdCostRowDef[] = [
  { key: 'opening', label: '期初余额', kind: 'opening' },
  { key: 'rawMaterial', label: '原材料', kind: 'increase', indent: true },
  { key: 'fuelPower', label: '燃料动力', kind: 'increase', indent: true },
  { key: 'labor', label: '人工费用', kind: 'increase', indent: true },
  { key: 'overhead', label: '制造费用', kind: 'increase', indent: true },
  { key: 'other', label: '其他', kind: 'increase', indent: true },
  { key: 'increaseTotal', label: '增加合计', kind: 'computed' },
  { key: 'transferFG', label: '本期结转产成品', kind: 'transfer' },
  { key: 'transferWIP', label: '本期结转半成品', kind: 'transfer' },
  { key: 'monthEnd', label: '月末余额', kind: 'ending' },
]

export interface ProdCostMatrixRow {
  key: ProdCostRowKey
  label: string
  kind: ProdCostRowDef['kind']
  indent?: boolean
  months: Record<ProdCostMonthKey, number>
  priorYear: number
  changeReason: string
  /** 自动 */
  total: number
  changeRate: number | '' | 'N/A'
}

export interface ProdCostProductBlock {
  id: string
  productName: string
  rows: ProdCostMatrixRow[]
}

export function newProdCostBlockId(): string {
  return `f2pcb-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

function emptyMonths(): Record<ProdCostMonthKey, number> {
  return Object.fromEntries(PROD_COST_MONTH_KEYS.map((k) => [k, 0])) as Record<ProdCostMonthKey, number>
}

export function emptyProdCostBlock(productName = ''): ProdCostProductBlock {
  return {
    id: newProdCostBlockId(),
    productName,
    rows: PROD_COST_ROW_DEFS.map((d) => ({
      key: d.key,
      label: d.label,
      kind: d.kind,
      indent: d.indent,
      months: emptyMonths(),
      priorYear: 0,
      changeReason: '',
      total: 0,
      changeRate: '',
    })),
  }
}

/** 源模板通常为单一成本对象；支持多产品块增删 */
export function defaultProdCostBlocks(): ProdCostProductBlock[] {
  return [emptyProdCostBlock('')]
}

function n(v: number): number {
  return Number.isFinite(v) ? v : 0
}

function prevMonth(key: ProdCostMonthKey): ProdCostMonthKey | null {
  const i = PROD_COST_MONTH_KEYS.indexOf(key)
  return i > 0 ? PROD_COST_MONTH_KEYS[i - 1] : null
}

function rowMap(block: ProdCostProductBlock): Map<ProdCostRowKey, ProdCostMatrixRow> {
  return new Map(block.rows.map((r) => [r.key, { ...r, months: { ...r.months } }]))
}

function calcRowTotal(key: ProdCostRowKey, months: Record<ProdCostMonthKey, number>): number {
  if (key === 'opening') return n(months['01'])
  if (key === 'monthEnd') return n(months['12'])
  return calcSubtotal(PROD_COST_MONTH_KEYS.map((m) => n(months[m])))
}

export function enrichProdCostBlock(block: ProdCostProductBlock): ProdCostProductBlock {
  const map = rowMap(block)
  const opening = map.get('opening')!
  const increaseTotal = map.get('increaseTotal')!
  const monthEnd = map.get('monthEnd')!
  const transferFG = map.get('transferFG')!
  const transferWIP = map.get('transferWIP')!

  const monthEndValues = emptyMonths()

  for (const mk of PROD_COST_MONTH_KEYS) {
    let inc = 0
    for (const ik of INCREASE_ROW_KEYS) {
      inc += n(map.get(ik)!.months[mk])
    }
    increaseTotal.months[mk] = inc

    const pm = prevMonth(mk)
    const effectiveOpening = pm ? n(monthEndValues[pm]) : n(opening.months[mk])
    if (!pm) {
      opening.months[mk] = n(opening.months[mk])
    } else {
      opening.months[mk] = effectiveOpening
    }

    monthEndValues[mk] = calcProductionPeriodEnd(
      effectiveOpening,
      inc,
      n(transferFG.months[mk]) + n(transferWIP.months[mk]),
    )
    monthEnd.months[mk] = monthEndValues[mk]
  }

  const rows = PROD_COST_ROW_DEFS.map((d) => {
    const row = map.get(d.key)!
    const total = calcRowTotal(d.key, row.months)
    const changeRate = calcChangeRate(row.priorYear, total)
    return { ...row, total, changeRate }
  })

  return { ...block, rows }
}

export function getBlockYearEndTotal(block: ProdCostProductBlock): number {
  const e = enrichProdCostBlock(block)
  return e.rows.find((r) => r.key === 'monthEnd')?.months['12'] ?? 0
}

export function sumBlocksYearEnd(blocks: ProdCostProductBlock[]): number {
  return calcSubtotal(blocks.map(getBlockYearEndTotal))
}

export function readMatrixSourceTotals(blocks: ProdCostProductBlock[]): {
  material: number
  labor: number
  overhead: number
} {
  let material = 0
  let labor = 0
  let overhead = 0
  for (const b of blocks) {
    const e = enrichProdCostBlock(b)
    for (const r of e.rows) {
      if (r.key === 'rawMaterial') material += r.total
      if (r.key === 'labor') labor += r.total
      if (r.key === 'overhead') overhead += r.total
    }
  }
  return { material, labor, overhead }
}

/** 迁移旧扁平产品行 */
export function migrateToProdCostBlocks(
  legacy: unknown,
): ProdCostProductBlock[] | null {
  if (!Array.isArray(legacy) || !legacy.length) return null

  const first = legacy[0] as Record<string, unknown>
  if (first && Array.isArray(first.rows) && first.rows[0] && 'months' in (first.rows[0] as object)) {
    return legacy as ProdCostProductBlock[]
  }

  if (first && 'dmOpening' in first) {
    return (legacy as ProductionCostRow[]).map((r) => {
      const b = emptyProdCostBlock(r.productName)
      const opening = b.rows.find((x) => x.key === 'opening')!
      opening.months['01'] = r.dmOpening + r.dlOpening + r.ohOpening
      const rm = b.rows.find((x) => x.key === 'rawMaterial')!
      rm.months['12'] = r.dmInput
      const lb = b.rows.find((x) => x.key === 'labor')!
      lb.months['12'] = r.dlInput
      const oh = b.rows.find((x) => x.key === 'overhead')!
      oh.months['12'] = r.ohInput
      const fg = b.rows.find((x) => x.key === 'transferFG')!
      fg.months['12'] = r.dmTransfer + r.dlTransfer + r.ohTransfer
      return b
    })
  }

  return null
}

export function readF2_41SourceTotals(allResponses: Map<string, ChecklistResponse>): {
  material: number
  labor: number
  overhead: number
} {
  const raw = readValRowJson(allResponses.get('F2-41-rows'))
  if (!raw) return { material: 0, labor: 0, overhead: 0 }
  try {
    const parsed = JSON.parse(raw)
    const blocks = migrateToProdCostBlocks(parsed)
    if (blocks?.length) return readMatrixSourceTotals(blocks)
    const legacy = parseRows<ProductionCostRow>(raw, () => [])
    return {
      material: calcSubtotal(legacy.map((r) => enrichProductionRow(r).dmClosing)),
      labor: calcSubtotal(legacy.map((r) => enrichProductionRow(r).dlClosing)),
      overhead: calcSubtotal(legacy.map((r) => enrichProductionRow(r).ohClosing)),
    }
  } catch {
    return { material: 0, labor: 0, overhead: 0 }
  }
}

export const F2_41_TIPS = [
  '关注生产成本是否包含不应计入产品成本的费用，如非正常消耗、完工后仓储费、销售相关运输费及不应资本化的借款费用等。',
  '核对原材料、人工费用、制造费用合计数与材料汇总表、工资费用分配表、制造费用分配表及相关总账记录是否一致，注意交叉索引。',
  '检查生产成本在完工产品与在产品之间的分配是否正确、合理，分配方法与分配标准是否与上期一致。',
] as const

export const F2_41_DEFAULT_OBJECTIVE =
  '验证生产成本归集与结转的完整性、准确性，确认在产品期末结存计价合理，为存货成本真实性提供基础证据。'
