/**
 * F2-42 直接人工分析表 — 产品×月度三表联动（对齐致同源模板）
 *
 * 表1 各月直接人工 | 表2 各月产量/工时 | 表3 单位人工成本 = 表1÷表2
 * 列：1–12月 + 合计/平均值 + 上年度 + 变动率
 */
import { calcSubtotal, calcChangeRate } from './useF2InvValFormulaEngine'
import { readValRowJson, type ChecklistResponse } from './useF2ValuationFormData'
import { parseRows, type DirectLaborRow } from './useF2ProductionCostFormulas'

export const LABOR_MONTH_KEYS = [
  '01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12',
] as const

export type LaborMonthKey = (typeof LABOR_MONTH_KEYS)[number]

export interface LaborProductLine {
  id: string
  productName: string
  laborMonths: Record<LaborMonthKey, number>
  outputMonths: Record<LaborMonthKey, number>
  laborPriorYear: number
  outputPriorYear: number
  unitPriorYear: number
  changeReason: string
}

export interface EnrichedLaborProductLine extends LaborProductLine {
  laborTotal: number
  laborChangeRate: number | '' | 'N/A'
  outputTotal: number
  outputChangeRate: number | '' | 'N/A'
  unitMonths: Record<LaborMonthKey, number>
  unitAverage: number
  unitChangeRate: number | '' | 'N/A'
}

export function newLaborLineId(): string {
  return `f2lb-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

function emptyMonths(): Record<LaborMonthKey, number> {
  return Object.fromEntries(LABOR_MONTH_KEYS.map((k) => [k, 0])) as Record<LaborMonthKey, number>
}

export function emptyLaborProductLine(name = ''): LaborProductLine {
  return {
    id: newLaborLineId(),
    productName: name,
    laborMonths: emptyMonths(),
    outputMonths: emptyMonths(),
    laborPriorYear: 0,
    outputPriorYear: 0,
    unitPriorYear: 0,
    changeReason: '',
  }
}

/** 默认 1 个产品行；需要时由「+ 增行」添加 */
export function defaultLaborProductLines(): LaborProductLine[] {
  return [emptyLaborProductLine('')]
}

function n(v: number): number {
  return Number.isFinite(v) ? v : 0
}

function safeDiv(a: number, b: number): number {
  if (!b) return 0
  return a / b
}

export function enrichLaborProductLine(line: LaborProductLine): EnrichedLaborProductLine {
  const laborTotal = calcSubtotal(LABOR_MONTH_KEYS.map((k) => n(line.laborMonths[k])))
  const outputTotal = calcSubtotal(LABOR_MONTH_KEYS.map((k) => n(line.outputMonths[k])))
  const unitMonths = Object.fromEntries(
    LABOR_MONTH_KEYS.map((k) => [
      k,
      safeDiv(n(line.laborMonths[k]), n(line.outputMonths[k])),
    ]),
  ) as Record<LaborMonthKey, number>
  const unitAverage = safeDiv(laborTotal, outputTotal)
  return {
    ...line,
    laborTotal,
    laborChangeRate: calcChangeRate(line.laborPriorYear, laborTotal),
    outputTotal,
    outputChangeRate: calcChangeRate(line.outputPriorYear, outputTotal),
    unitMonths,
    unitAverage,
    unitChangeRate: calcChangeRate(line.unitPriorYear, unitAverage),
  }
}

export function enrichAllLaborLines(lines: LaborProductLine[]): EnrichedLaborProductLine[] {
  return lines.map(enrichLaborProductLine)
}

export function countAbnormalUnitVariance(
  lines: EnrichedLaborProductLine[],
  thresholdPct = 5,
): number {
  const threshold = thresholdPct / 100
  return lines.filter((l) => {
    const r = l.unitChangeRate
    return typeof r === 'number' && Math.abs(r) > threshold
  }).length
}

export function sumLaborAnnual(lines: LaborProductLine[]): number {
  return calcSubtotal(lines.map((l) => enrichLaborProductLine(l).laborTotal))
}

export function migrateToLaborMatrix(legacy: unknown): LaborProductLine[] | null {
  if (!Array.isArray(legacy) || !legacy.length) return null
  const first = legacy[0] as Record<string, unknown>
  if (first && first.laborMonths && first.outputMonths) {
    return legacy as LaborProductLine[]
  }
  if (first && 'actualLabor' in first) {
    return (legacy as DirectLaborRow[]).map((r) => {
      const line = emptyLaborProductLine(r.department || r.remark || '')
      line.laborMonths['12'] = r.actualLabor
      line.outputMonths['12'] = r.hours
      return line
    })
  }
  return null
}

export function readF2_42LaborTotal(allResponses: Map<string, ChecklistResponse>): number {
  const raw = readValRowJson(allResponses.get('F2-42-rows'))
  if (!raw) return 0
  try {
    const parsed = JSON.parse(raw)
    const lines = migrateToLaborMatrix(parsed)
    if (lines?.length) return sumLaborAnnual(lines)
    const legacy = parseRows<DirectLaborRow>(raw, () => [])
    return calcSubtotal(legacy.map((r) => r.actualLabor))
  } catch {
    return 0
  }
}

export const F2_42_DEFAULT_OBJECTIVE =
  '验证存货金额是否恰当，计价及分摊调整是否正确，披露是否恰当。'

export const F2_42_PROCEDURE =
  '对直接人工费用、产量（工时）及单位人工成本进行分析，关注各月波动及与上年度的差异；对变动异常的产品进一步执行生产成本及单耗分析程序。'

export const F2_42_TIPS = [
  '对变动异常的产品应进一步执行程序，分析产品生产成本及单耗。',
  '如果单位人工成本异常降低，关注是否存在其他方（如关联方）代付工资的情况。',
] as const

export const LABOR_MONTH_LABELS = [
  { key: '01', label: '1月' }, { key: '02', label: '2月' }, { key: '03', label: '3月' },
  { key: '04', label: '4月' }, { key: '05', label: '5月' }, { key: '06', label: '6月' },
  { key: '07', label: '7月' }, { key: '08', label: '8月' }, { key: '09', label: '9月' },
  { key: '10', label: '10月' }, { key: '11', label: '11月' }, { key: '12', label: '12月' },
] as const
