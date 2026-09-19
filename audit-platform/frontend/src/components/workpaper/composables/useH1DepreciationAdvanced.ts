/**
 * H1-12 折旧测算高级能力（纯函数）
 * - 差异归因 / 期初累计校验 / 税法最低年限
 * - 抽样测算 / 估计变更分段 / 容差与重要性
 * - 导入列映射记忆 / 引擎水印元数据
 */
import {
  calcStraightLine,
  calcMonthsDepreciated,
  calcStraightLineTest,
  parseDepDate,
  type StraightLineTestResult,
} from './useH1DepreciationEngine'

export const H1_12_ENGINE_VERSION = 'H1-12-engine/2.0.0'

// ─── 税法最低折旧年限（《企业所得税法实施条例》第60条）──────────────────────

export const TAX_MIN_LIFE_YEARS: { pattern: RegExp; years: number; label: string }[] = [
  { pattern: /房屋|建筑物|构筑物/, years: 20, label: '房屋建筑物≥20年' },
  { pattern: /飞机|火车|轮船|机器|机械|生产设备/, years: 10, label: '机器生产设备≥10年' },
  { pattern: /器具|工具|家具/, years: 5, label: '器具工具家具≥5年' },
  { pattern: /运输|汽车|车辆|交通/, years: 4, label: '运输工具≥4年' },
  { pattern: /电子|电脑|计算机|办公设备/, years: 3, label: '电子设备≥3年' },
]

export function checkTaxMinLife(category: string, usefulLifeYears: number): {
  ok: boolean
  minYears: number | null
  message: string
} {
  const hit = TAX_MIN_LIFE_YEARS.find((t) => t.pattern.test(category || ''))
  if (!hit) return { ok: true, minYears: null, message: '' }
  if (usefulLifeYears > 0 && usefulLifeYears < hit.years) {
    return {
      ok: false,
      minYears: hit.years,
      message: `会计年限${usefulLifeYears}年 < 税法最低${hit.years}年（${hit.label}，提示性不阻断）`,
    }
  }
  return { ok: true, minYears: hit.years, message: '' }
}

// ─── 容差 / 重要性 ───────────────────────────────────────────────────────────

export interface MaterialityConfig {
  /** 单笔可接受尾差（元），默认 0.01 */
  roundingTolerance: number
  /** 单笔重要性（元）；未设则用合计重要性的 5% */
  singleMateriality: number
  /** 合计重要性（元） */
  aggregateMateriality: number
}

export type DiffSeverity = 'ok' | 'rounding' | 'review' | 'material'

export function classifyDiffAmount(
  absDiff: number,
  cfg: MaterialityConfig,
): DiffSeverity {
  if (absDiff <= cfg.roundingTolerance) return 'ok'
  if (absDiff <= Math.max(cfg.roundingTolerance * 100, 1)) return 'rounding'
  if (absDiff < cfg.singleMateriality) return 'review'
  return 'material'
}

export function defaultMateriality(aggregate?: number): MaterialityConfig {
  const agg = aggregate && aggregate > 0 ? aggregate : 10000
  return {
    roundingTolerance: 0.01,
    singleMateriality: Math.max(agg * 0.05, 100),
    aggregateMateriality: agg,
  }
}

// ─── 差异归因 ────────────────────────────────────────────────────────────────

export type DiffReasonCode =
  | 'timing_one_month'
  | 'fully_depreciated_still'
  | 'disposal_month'
  | 'impairment_timing'
  | 'estimate_change'
  | 'method_mismatch'
  | 'begin_acc_mismatch'
  | 'rounding'
  | 'tax_life'
  | 'unknown'

export interface DiffAttribution {
  codes: DiffReasonCode[]
  labels: string[]
  primary: string
}

export function attributeDepreciationDiff(input: {
  difference: number
  monthlyDiff: number
  accDepDiff: number
  calcMonthly: number
  bookMonthly: number
  periodMonths: number
  monthsAtEnd: number
  usefulLifeMonths: number
  disposalDate?: string
  impairmentAmount?: number
  impairmentDate?: string
  depMethod?: string
  beginAccDiff?: number
  estimateChanged?: boolean
  taxLifeWarning?: string
  roundingTolerance?: number
}): DiffAttribution {
  const codes: DiffReasonCode[] = []
  const labels: string[] = []
  const tol = input.roundingTolerance ?? 0.01
  const absDiff = Math.abs(input.difference)
  const absMonthly = Math.abs(input.monthlyDiff)

  if (absDiff <= tol && Math.abs(input.accDepDiff) <= tol) {
    return { codes: [], labels: [], primary: '' }
  }

  // 起提差约 1 个月
  if (input.calcMonthly > 0 && Math.abs(absDiff - input.calcMonthly) < Math.max(tol * 10, 1)) {
    codes.push('timing_one_month')
    labels.push('疑似起提/停提差约1个月（CAS次月起提）')
  }

  // 满折后仍提
  if (input.monthsAtEnd >= input.usefulLifeMonths && input.bookMonthly > tol) {
    codes.push('fully_depreciated_still')
    labels.push('已满折但仍有账面月折旧，可能多提')
  }

  // 处置
  if (input.disposalDate) {
    codes.push('disposal_month')
    labels.push(`存在处置日 ${input.disposalDate}，需核对处置当月停提及累计冲减`)
  }

  // 减值时点
  if ((input.impairmentAmount ?? 0) > tol) {
    codes.push('impairment_timing')
    labels.push(input.impairmentDate
      ? `含减值（${input.impairmentDate}），核对减值前后月折旧切换`
      : '含减值但缺减值日期，期中拆分可能不准')
  }

  // 估计变更
  if (input.estimateChanged) {
    codes.push('estimate_change')
    labels.push('本年变更年限/残值率，应按变更日分段测算')
  }

  // 方法不一致
  if (input.depMethod && input.depMethod !== '直线法' && absMonthly > tol) {
    codes.push('method_mismatch')
    labels.push(`折旧方法为「${input.depMethod}」，直线法测算仅作参考`)
  }

  // 期初累计
  if ((input.beginAccDiff ?? 0) > Math.max(tol, 1)) {
    codes.push('begin_acc_mismatch')
    labels.push(`期初累计折旧差异 ${input.beginAccDiff!.toFixed(2)}，应先测期初`)
  }

  // 税龄
  if (input.taxLifeWarning) {
    codes.push('tax_life')
    labels.push(input.taxLifeWarning)
  }

  // 尾差
  if (absDiff > 0 && absDiff <= 1 && !codes.includes('timing_one_month')) {
    codes.push('rounding')
    labels.push('可能为四舍五入尾差')
  }

  if (codes.length === 0) {
    codes.push('unknown')
    labels.push('原因待查（政策变更/停用/错提/系统参数）')
  }

  return { codes, labels, primary: labels[0] || '' }
}

// ─── 期初累计折旧校验 ────────────────────────────────────────────────────────

export interface BeginAccCheck {
  calcAccDepBegin: number
  bookAccDepBegin: number
  diff: number
  ok: boolean
  message: string
}

export function checkBeginAccumulatedDep(input: {
  cost: number
  salvageRate: number
  usefulLifeYears: number
  startDate?: string | null
  periodBegin?: string | null
  bookAccDepBegin: number
  tolerance?: number
}): BeginAccCheck {
  const lifeMonths = Math.max(Math.round(input.usefulLifeYears * 12), 0)
  const monthly = calcStraightLine(input.cost, input.salvageRate, input.usefulLifeYears)
  let monthsBegin = 0
  if (input.periodBegin) {
    const pb = parseDepDate(input.periodBegin)
    const asOf = pb ? new Date(pb.getFullYear(), pb.getMonth(), pb.getDate() - 1) : null
    monthsBegin = calcMonthsDepreciated(input.startDate, asOf, lifeMonths)
  }
  const calcAccDepBegin = Math.round(monthly * monthsBegin * 100) / 100
  const book = input.bookAccDepBegin || 0
  const diff = Math.round((book - calcAccDepBegin) * 100) / 100
  const tol = input.tolerance ?? 0.01
  const ok = Math.abs(diff) <= tol
  return {
    calcAccDepBegin,
    bookAccDepBegin: book,
    diff,
    ok,
    message: ok
      ? ''
      : `期初累计折旧：账面 ${book.toFixed(2)} vs 测算 ${calcAccDepBegin.toFixed(2)}，差 ${diff.toFixed(2)}（应先测期初）`,
  }
}

// ─── 估计变更（年限/残值）分段 ───────────────────────────────────────────────

export interface EstimateChangeInput {
  cost: number
  startDate?: string | null
  periodBegin?: string | null
  periodEnd?: string | null
  disposalDate?: string | null
  /** 变更前 */
  usefulLifeYearsBefore: number
  salvageRateBefore: number
  /** 变更后 */
  usefulLifeYearsAfter: number
  salvageRateAfter: number
  changeDate: string
  bookMonthly?: number
  bookAccDepEnd?: number
}

/**
 * 会计估计变更：变更日前用旧参数，变更日后以变更日账面净值按新剩余年限重算。
 */
export function calcWithEstimateChangeTest(input: EstimateChangeInput): StraightLineTestResult & {
  monthlyBefore: number
  monthlyAfter: number
  monthsBeforeChange: number
  monthsAfterChange: number
  netAtChange: number
} {
  const base = calcStraightLineTest({
    cost: input.cost,
    salvageRate: input.salvageRateBefore,
    usefulLifeYears: input.usefulLifeYearsBefore,
    startDate: input.startDate,
    periodBegin: input.periodBegin,
    periodEnd: input.periodEnd,
    disposalDate: input.disposalDate,
    bookMonthly: input.bookMonthly,
    bookAccDepEnd: input.bookAccDepEnd,
  })

  const lifeBefore = Math.max(Math.round(input.usefulLifeYearsBefore * 12), 0)
  const elapsedAtChange = calcMonthsDepreciated(input.startDate, input.changeDate, lifeBefore)
  const monthlyBefore = calcStraightLine(input.cost, input.salvageRateBefore, input.usefulLifeYearsBefore)
  const accAtChange = monthlyBefore * elapsedAtChange
  const salvageAfter = input.cost * input.salvageRateAfter
  const netAtChange = Math.max(input.cost - accAtChange, 0)
  const remainingDepreciable = Math.max(netAtChange - salvageAfter, 0)
  // 新剩余月数：按新年限总月数 − 已用月数（或按新年限重新设定）
  const lifeAfterMonths = Math.max(Math.round(input.usefulLifeYearsAfter * 12), 0)
  const remainingMonths = Math.max(lifeAfterMonths - elapsedAtChange, 1)
  const monthlyAfter = remainingDepreciable / remainingMonths

  const begin = base.monthsAtBegin
  const end = base.monthsAtEnd
  const monthsBeforeChange = Math.max(Math.min(elapsedAtChange, end) - begin, 0)
  const monthsAfterChange = Math.max(end - Math.max(elapsedAtChange, begin), 0)
  const periodDep = monthlyBefore * monthsBeforeChange + monthlyAfter * monthsAfterChange
  const calcAccDep = monthlyBefore * Math.min(elapsedAtChange, end)
    + monthlyAfter * Math.max(end - elapsedAtChange, 0)

  return {
    ...base,
    periodMonths: monthsBeforeChange + monthsAfterChange,
    periodDep: round2(periodDep),
    calcAccDep: round2(calcAccDep),
    calcMonthly: round2(monthlyAfter),
    monthlyDiff: round2((input.bookMonthly ?? 0) - monthlyAfter),
    accDepDiff: round2((input.bookAccDepEnd ?? 0) - calcAccDep),
    monthlyBefore: round2(monthlyBefore),
    monthlyAfter: round2(monthlyAfter),
    monthsBeforeChange,
    monthsAfterChange,
    netAtChange: round2(netAtChange),
  }
}

// ─── 抽样测算 ────────────────────────────────────────────────────────────────

export interface SamplingParams {
  /** 原值覆盖率目标 0~1，默认 0.8 */
  costCoverageTarget: number
  /** 随机补样最少件数 */
  minRandom: number
  /** 是否强制纳入新增（本年 startDate 在期内） */
  includeAdditions: boolean
  /** 是否强制纳入有减值 */
  includeImpaired: boolean
  /** 是否强制纳入处置 */
  includeDisposed: boolean
}

export interface SamplingResult<T extends { rowId: string; originalCost: number }> {
  selectedIds: Set<string>
  selected: T[]
  excluded: T[]
  costCoverage: number
  countCoverage: number
  rationale: string[]
}

export function selectDepreciationSample<T extends {
  rowId: string
  originalCost: number
  startDate?: string
  disposalDate?: string
  impairmentEnd?: number
  impairmentAmount?: number
  impairmentProvision?: number
  difference?: number
  recommendedBranch?: string
}>(
  population: T[],
  periodBegin: string,
  params?: Partial<SamplingParams>,
): SamplingResult<T> {
  const p: SamplingParams = {
    costCoverageTarget: params?.costCoverageTarget ?? 0.8,
    minRandom: params?.minRandom ?? 3,
    includeAdditions: params?.includeAdditions ?? true,
    includeImpaired: params?.includeImpaired ?? true,
    includeDisposed: params?.includeDisposed ?? true,
  }

  const totalCost = population.reduce((s, r) => s + (r.originalCost || 0), 0) || 1
  const selected = new Set<string>()
  const rationale: string[] = []

  const force = (pred: (r: T) => boolean, reason: string) => {
    let n = 0
    for (const r of population) {
      if (pred(r) && !selected.has(r.rowId)) {
        selected.add(r.rowId)
        n++
      }
    }
    if (n) rationale.push(`${reason} ${n} 项`)
  }

  if (p.includeImpaired) {
    force(
      (r) => (r.impairmentEnd || r.impairmentAmount || r.impairmentProvision || 0) > 0.005
        || r.recommendedBranch === 'B' || r.recommendedBranch === 'C',
      '减值全覆盖',
    )
  }
  if (p.includeDisposed) {
    force((r) => !!r.disposalDate, '处置全覆盖')
  }
  if (p.includeAdditions && periodBegin) {
    force((r) => !!r.startDate && r.startDate >= periodBegin, '本期新增全覆盖')
  }

  // 按原值降序补足覆盖率
  const byCost = [...population].sort((a, b) => (b.originalCost || 0) - (a.originalCost || 0))
  let covered = [...selected].reduce((s, id) => {
    const row = population.find((r) => r.rowId === id)
    return s + (row?.originalCost || 0)
  }, 0)

  for (const r of byCost) {
    if (covered / totalCost >= p.costCoverageTarget) break
    if (!selected.has(r.rowId)) {
      selected.add(r.rowId)
      covered += r.originalCost || 0
    }
  }
  rationale.push(`原值覆盖率目标 ${(p.costCoverageTarget * 100).toFixed(0)}%，实际 ${((covered / totalCost) * 100).toFixed(1)}%`)

  // 随机补样（未入选中抽）
  const remaining = population.filter((r) => !selected.has(r.rowId))
  const need = Math.min(p.minRandom, remaining.length)
  for (let i = 0; i < need; i++) {
    const idx = Math.floor(pseudoRandom(remaining[i].rowId + String(i)) * remaining.length) % remaining.length
    const pick = remaining[idx]
    if (pick && !selected.has(pick.rowId)) {
      selected.add(pick.rowId)
      rationale.push(`随机补样 ${pick.rowId}`)
    }
  }

  const selectedRows = population.filter((r) => selected.has(r.rowId))
  const excluded = population.filter((r) => !selected.has(r.rowId))
  const costCoverage = selectedRows.reduce((s, r) => s + (r.originalCost || 0), 0) / totalCost

  return {
    selectedIds: selected,
    selected: selectedRows,
    excluded,
    costCoverage,
    countCoverage: population.length ? selectedRows.length / population.length : 0,
    rationale,
  }
}

function pseudoRandom(seed: string): number {
  let h = 0
  for (let i = 0; i < seed.length; i++) h = (Math.imul(31, h) + seed.charCodeAt(i)) | 0
  return ((h >>> 0) % 10000) / 10000
}

// ─── 导入列映射记忆 ──────────────────────────────────────────────────────────

const MAPPING_STORAGE_PREFIX = 'h1-12-col-map:'

export type ColumnMapping = Record<string, string> // 标准字段 → 原始表头

export function loadColumnMapping(projectId: string): ColumnMapping | null {
  try {
    const raw = localStorage.getItem(MAPPING_STORAGE_PREFIX + projectId)
    if (!raw) return null
    return JSON.parse(raw) as ColumnMapping
  } catch {
    return null
  }
}

export function saveColumnMapping(projectId: string, mapping: ColumnMapping): void {
  try {
    localStorage.setItem(MAPPING_STORAGE_PREFIX + projectId, JSON.stringify(mapping))
  } catch { /* ignore quota */ }
}

export function clearColumnMapping(projectId: string): void {
  try {
    localStorage.removeItem(MAPPING_STORAGE_PREFIX + projectId)
  } catch { /* ignore */ }
}

/** 用记忆映射：原始表头行 → fieldIndex */
export function applyRememberedMapping(
  headers: unknown[],
  remembered: ColumnMapping,
): Map<string, number> {
  const fieldIndex = new Map<string, number>()
  const norm = (h: unknown) => String(h ?? '').replace(/\s+/g, '').toLowerCase()
  for (const [field, headerText] of Object.entries(remembered)) {
    const idx = headers.findIndex((h) => norm(h) === norm(headerText))
    if (idx >= 0) fieldIndex.set(field, idx)
  }
  return fieldIndex
}

export function buildMappingFromFieldIndex(
  headers: unknown[],
  fieldIndex: Map<string, number>,
): ColumnMapping {
  const mapping: ColumnMapping = {}
  for (const [field, idx] of fieldIndex.entries()) {
    mapping[field] = String(headers[idx] ?? '')
  }
  return mapping
}

// ─── 引擎水印 / 导出元数据 ───────────────────────────────────────────────────

export interface EngineWatermark {
  engineVersion: string
  branch: string
  periodEnd: string
  calculatedAt: string
  rowCount: number
  sampleMode: boolean
  sampleCoverage?: number
}

export function buildEngineWatermark(input: {
  branch: string
  periodEnd: string
  rowCount: number
  sampleMode?: boolean
  sampleCoverage?: number
}): EngineWatermark {
  return {
    engineVersion: H1_12_ENGINE_VERSION,
    branch: input.branch,
    periodEnd: input.periodEnd,
    calculatedAt: new Date().toISOString(),
    rowCount: input.rowCount,
    sampleMode: !!input.sampleMode,
    sampleCoverage: input.sampleCoverage,
  }
}

export function formatWatermarkLine(w: EngineWatermark): string {
  const sample = w.sampleMode
    ? ` | 抽样覆盖${((w.sampleCoverage ?? 0) * 100).toFixed(0)}%`
    : ' | 全量'
  return `[${w.engineVersion}] 分支${w.branch} 截止日${w.periodEnd || '—'} 行数${w.rowCount}${sample} @${w.calculatedAt.slice(0, 19)}`
}

// ─── H1-8 / H1-14 解析辅助 ───────────────────────────────────────────────────

export interface DisposalLinkRow {
  assetNo: string
  name: string
  disposalDate: string
  accDep: number
  originalCost: number
}

export function parseH18DisposalRows(remark: string | null | undefined): DisposalLinkRow[] {
  if (!remark) return []
  try {
    const arr = JSON.parse(remark)
    if (!Array.isArray(arr)) return []
    return arr.map((r: any) => ({
      assetNo: String(r.assetNo ?? r.assetCode ?? ''),
      name: String(r.name ?? r.assetName ?? ''),
      disposalDate: String(r.disposalDate ?? ''),
      accDep: Number(r.accDep ?? r.accumDep ?? 0) || 0,
      originalCost: Number(r.originalCost ?? 0) || 0,
    })).filter((r: DisposalLinkRow) => r.disposalDate || r.assetNo || r.name)
  } catch {
    return []
  }
}

export interface ImpairmentLinkRow {
  assetGroup: string
  category: string
  impairmentAmount: number
  alreadyProvided: number
  supplement: number
  indexRef: string
}

export function parseH14ImpairmentRows(remark: string | null | undefined): ImpairmentLinkRow[] {
  if (!remark) return []
  try {
    const arr = JSON.parse(remark)
    if (!Array.isArray(arr)) return []
    return arr.map((r: any) => ({
      assetGroup: String(r.assetGroup ?? r.name ?? ''),
      category: String(r.category ?? ''),
      impairmentAmount: Number(r.impairmentAmount ?? 0) || 0,
      alreadyProvided: Number(r.alreadyProvided ?? 0) || 0,
      supplement: Math.max(Number(r.difference ?? 0) || 0, 0),
      indexRef: String(r.indexRef ?? ''),
    })).filter((r: ImpairmentLinkRow) => r.assetGroup || r.impairmentAmount > 0)
  } catch {
    return []
  }
}

function round2(n: number): number {
  if (!Number.isFinite(n)) return 0
  return Math.round(n * 100) / 100
}
