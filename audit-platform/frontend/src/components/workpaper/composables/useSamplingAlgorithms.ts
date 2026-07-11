/**
 * useSamplingAlgorithms — 前端展示用算法镜像（纯函数模块）
 *
 * Spec: .kiro/specs/voucher-sampling-engine/
 * Task: 4.1
 *
 * 职责：
 * - 导出所有 TypeScript 类型：SamplingMethod、Phase、FillMode、CheckResult、StratumConfig、
 *   SamplingConfig、SampledVoucher、EditTrailEntry、CoverageStats、ComplianceWarning
 * - computeCoverage：计算笔数覆盖率 + 金额覆盖率
 * - checkCAS1314Compliance：CAS 1314 合规性检查（覆盖率/方法合规/样本充分性）
 * - validateSamplingConfig：按方法校验必填参数
 * - computeVersionDiff：按 voucher_no 计算两次抽凭的 diff
 *
 * Requirements: 8.3, 12.1, 12.2, 6.3
 *
 * ── 方法学增强（spec: voucher-check-sampling-integration, Task 1）──
 * 新增科学样本量推导基座：reliabilityFactor / computeMusInterval /
 * computeSampleSize / markHighValueItems，内置 CAS 1314 泊松可信赖度系数常量表。
 * 金额一律用 Decimal 字符串运算，避免浮点误差。
 * Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 17.1, 17.2, 17.3, 17.4, 20.1
 */

import Decimal from 'decimal.js'

// ─── Types ───────────────────────────────────────────────────────────────────

export type SamplingMethod = 'random' | 'stratified' | 'specific_item' | 'systematic' | 'mus'

export type Phase = 'preliminary' | 'final'

export type FillMode = 'append' | 'replace' | 'merge'

export type CheckResult = 'Y' | 'N' | '异常' | ''

export interface StratumConfig {
  lowerBound: string   // Decimal字符串
  upperBound: string
  sampleSize: number
}

export interface SamplingConfig {
  samplingMethod: SamplingMethod
  // random
  sampleSize?: number
  // stratified
  strata?: StratumConfig[]
  // specific_item
  materialityThreshold?: string  // Decimal字符串
  // systematic
  startPoint?: number
  interval?: number
  // mus
  musSampleSize?: number
  // 通用
  randomSeed?: number | null
  // 过滤条件
  accountCodes: string[]
  periodRange: number[]          // 会计月份 1-12
  amountMin?: string
  amountMax?: string
  directionFilter: 'debit' | 'credit' | 'all'
  voucherTypeFilter: string[]
  summaryKeyword: string
  excludeExtracted: boolean
  // ─── 方法学增强（可选，向后兼容）─────────────────────────────────
  /** 置信度/信赖水平，如 0.95（R20）；驱动可信赖度系数与样本量推导 */
  confidenceLevel?: number
  /** 可容忍错报（Decimal 字符串）。默认取重要性/B15（R16），统计法必填（R20） */
  tolerableMisstatement?: string
  /** 预期错报（Decimal 字符串，R20）；须小于可容忍错报 */
  expectedMisstatement?: string
  /** 系统建议样本量（R15 留痕）；供手工覆盖时保留原始建议值 */
  suggestedSampleSize?: number
  /** 重抽原因（R22）；重抽治理与可追溯 */
  resampleReason?: string
}

export interface EditTrailEntry {
  userId: string
  timestamp: string
  field: string
  oldValue: string
  newValue: string
}

export interface SampledVoucher {
  voucherNo: string
  voucherDate: string
  summary: string | null
  debitAmount: string | null
  creditAmount: string | null
  accountCode: string
  accountName: string | null
  counterpartAccount: string | null
  voucherType: string | null
  accountingPeriod: number | null
  checkResult: CheckResult
  abnormal: boolean
  remark: string
  selected: boolean
  phase: Phase
  editTrail: EditTrailEntry[]
  // ─── 方法学增强（可选，向后兼容）─────────────────────────────────
  /** MUS 高值必选项标识：单笔金额 ≥ 抽样间隔者为 true（R17） */
  isHighValue?: boolean
  /** 审计师录入的该样本实际错报金额（Decimal 字符串，R18） */
  actualMisstatement?: string
  /** 特定选取原因：审计师对该凭证标注的选取理由，随样本回填（R6.5） */
  selectionReason?: string
}

export interface CoverageStats {
  populationCount: number
  populationAmount: string    // 总体金额合计
  sampleCount: number
  sampleAmount: string        // 样本金额合计
  countCoverageRate: string   // 笔数覆盖率%
  amountCoverageRate: string  // 金额覆盖率%
}

export interface ComplianceWarning {
  type: 'coverage_low' | 'specific_item_high' | 'mus_insufficient'
  message: string
  level: 'warning' | 'suggestion'
}

// ─── 方法学增强：错报推断与总体结论数据模型 ─────────────────────────────────
//
// spec: voucher-check-sampling-integration, Task 2（design B.1）
// 金额一律用 Decimal 字符串运算，避免浮点误差。

/**
 * 错报推断结果（R18）
 *
 * - `projected`：推断错报（外推到总体，恒 ≥ 0）。
 * - `knownHighValue`：高值层（100% 检查）已知错报之和，直接计入不外推。
 * - `basicPrecision`：基本抽样风险余量（MUS = 可信赖度系数 × 抽样间隔）。
 * - `incrementalAllowance`：增量准备（按污染率排序的递增因子准备）。
 * - `upperLimit`：错报上限 UML = projected + basicPrecision + incrementalAllowance。
 */
export interface MisstatementResult {
  projected: string
  knownHighValue: string
  basicPrecision: string
  incrementalAllowance: string
  upperLimit: string
}

/**
 * 抽样结论（R18.5/18.6）
 *
 * - `accepted`：UML ≤ 可容忍错报 → 总体可接受（边界 UML == tolerable 视为可接受）。
 * - `message`：结论说明文案。
 */
export interface SamplingConclusion {
  accepted: boolean
  message: string
}

/**
 * 总体完整性校验结果（R19）
 *
 * - `diff = |samplingPopulationAmount − bookAmount|`。
 * - `withinThreshold = diff ≤ bookAmount × thresholdPct`。
 */
export interface PopulationReconcile {
  samplingPopulationAmount: string
  bookAmount: string
  diff: string
  withinThreshold: boolean
}

// ─── Version Diff Result ─────────────────────────────────────────────────────

export interface VersionDiffResult {
  added: string[]     // B \ A（B有A无）
  removed: string[]   // A \ B（A有B无）
  retained: string[]  // A ∩ B（两者都有）
}

// ─── computeCoverage ─────────────────────────────────────────────────────────

/**
 * 计算抽样覆盖率统计
 *
 * - 笔数覆盖率 = sampleCount / populationCount × 100，精度2位小数
 * - 金额覆盖率 = sampleAmount / populationAmount × 100，精度2位小数
 * - 当 populationCount=0 或 populationAmount=0 时对应覆盖率为 "0.00"
 */
export function computeCoverage(
  populationCount: number,
  populationAmount: string,
  sampleCount: number,
  sampleAmount: string,
): CoverageStats {
  const popAmount = parseFloat(populationAmount) || 0
  const samAmount = parseFloat(sampleAmount) || 0

  const countRate = populationCount > 0
    ? (sampleCount / populationCount * 100).toFixed(2)
    : '0.00'

  const amountRate = popAmount > 0
    ? (samAmount / popAmount * 100).toFixed(2)
    : '0.00'

  return {
    populationCount,
    populationAmount,
    sampleCount,
    sampleAmount,
    countCoverageRate: countRate,
    amountCoverageRate: amountRate,
  }
}

// ─── checkCAS1314Compliance ──────────────────────────────────────────────────

/**
 * CAS 1314 合规性检查
 *
 * 规则：
 * 1. 金额覆盖率 < 60% → warning "覆盖率偏低，建议增大样本量或调整抽样条件"
 * 2. specific_item 占比 > 50% → suggestion "特定项目过多，建议增加随机样本补充"
 * 3. MUS sample_size < expected → warning "MUS样本量不足"
 *
 * @param stats 覆盖率统计
 * @param method 当前抽样方法
 * @param sampleCount 当前方法的实际样本量
 * @param totalCount 总样本量（含所有方法的已填充行数）
 */
export function checkCAS1314Compliance(
  stats: CoverageStats,
  method: SamplingMethod,
  sampleCount: number,
  totalCount: number,
): ComplianceWarning[] {
  const warnings: ComplianceWarning[] = []

  // 规则1：金额覆盖率 < 60%
  const amountRate = parseFloat(stats.amountCoverageRate) || 0
  if (amountRate < 60) {
    warnings.push({
      type: 'coverage_low',
      message: '覆盖率偏低，建议增大样本量或调整抽样条件',
      level: 'warning',
    })
  }

  // 规则2：specific_item 占比 > 50%
  if (method === 'specific_item' && totalCount > 0) {
    const ratio = sampleCount / totalCount
    if (ratio > 0.5) {
      warnings.push({
        type: 'specific_item_high',
        message: '特定项目过多，建议增加随机样本补充',
        level: 'suggestion',
      })
    }
  }

  // 规则3：MUS sample_size < expected（样本量不足）
  if (method === 'mus') {
    // MUS 期望样本量：基于总体金额和间隔计算
    // 此处 sampleCount 是实际抽到的样本量，totalCount 是配置的期望样本量
    if (sampleCount < totalCount) {
      warnings.push({
        type: 'mus_insufficient',
        message: 'MUS样本量不足，实际抽取数量低于期望样本量',
        level: 'warning',
      })
    }
  }

  return warnings
}

// ─── validateSamplingConfig ──────────────────────────────────────────────────

/**
 * 校验抽样配置参数
 *
 * 按方法校验必填参数：
 * - random: sampleSize > 0
 * - stratified: strata.length > 0，每层 lowerBound < upperBound，sampleSize > 0
 * - specific_item: materialityThreshold 非空且 > 0
 * - systematic: startPoint >= 1，interval >= 2
 * - mus: musSampleSize > 0
 *
 * @returns errors Record<string, string>，空对象表示校验通过
 */
export function validateSamplingConfig(config: SamplingConfig): Record<string, string> {
  const errors: Record<string, string> = {}

  // 通用校验
  if (!config.accountCodes || config.accountCodes.length === 0) {
    errors.accountCodes = '科目范围不能为空'
  }

  // 按方法校验
  switch (config.samplingMethod) {
    case 'random':
      if (!config.sampleSize || config.sampleSize <= 0) {
        errors.sampleSize = '样本量必须大于0'
      }
      break

    case 'stratified':
      if (!config.strata || config.strata.length === 0) {
        errors.strata = '至少配置一个层级'
      } else {
        for (let i = 0; i < config.strata.length; i++) {
          const stratum = config.strata[i]
          const lower = parseFloat(stratum.lowerBound)
          const upper = parseFloat(stratum.upperBound)
          if (isNaN(lower) || isNaN(upper)) {
            errors[`strata_${i}_bounds`] = `第${i + 1}层金额边界无效`
          } else if (lower >= upper) {
            errors[`strata_${i}_bounds`] = `第${i + 1}层下限必须小于上限`
          }
          if (!stratum.sampleSize || stratum.sampleSize <= 0) {
            errors[`strata_${i}_sampleSize`] = `第${i + 1}层样本量必须大于0`
          }
        }
      }
      break

    case 'specific_item':
      if (!config.materialityThreshold) {
        errors.materialityThreshold = '重要性水平金额不能为空'
      } else {
        const threshold = parseFloat(config.materialityThreshold)
        if (isNaN(threshold) || threshold <= 0) {
          errors.materialityThreshold = '重要性水平金额必须大于0'
        }
      }
      break

    case 'systematic':
      if (!config.startPoint || config.startPoint < 1) {
        errors.startPoint = '起始点必须大于等于1'
      }
      if (!config.interval || config.interval < 2) {
        errors.interval = '间隔必须大于等于2'
      }
      break

    case 'mus':
      if (!config.musSampleSize || config.musSampleSize <= 0) {
        errors.musSampleSize = 'MUS样本量必须大于0'
      }
      break
  }

  // ─── 方法学参数校验（R20）─────────────────────────────────────────
  // 货币单元抽样（MUS）是以置信度/可容忍错报驱动抽样间隔与样本量推导的统计法，
  // 必填置信度与可容忍错报。随机/系统/分层保留既有基于自身参数的校验以向后兼容
  // （既有 random 配置无需方法学字段即视为有效）。预期错报须小于可容忍错报（两者均提供时）。
  const statistical = STATISTICAL_METHODS.includes(config.samplingMethod)
  const tol = config.tolerableMisstatement
  const hasTolerable = tol != null && tol !== '' && toDecimal(tol).gt(0)

  if (statistical) {
    const cl = config.confidenceLevel
    if (cl == null || !(cl > 0 && cl < 1)) {
      errors.confidenceLevel = '统计抽样方法必须填写置信度（介于0与1之间）'
    }
    if (!hasTolerable) {
      errors.tolerableMisstatement = '统计抽样方法必须填写可容忍错报且大于0'
    }
  }

  // R20.3：预期错报 ≥ 可容忍错报 时参数不合理（两者均提供时校验）
  if (hasTolerable && config.expectedMisstatement != null && config.expectedMisstatement !== '') {
    const exp = toDecimal(config.expectedMisstatement)
    if (exp.gte(toDecimal(tol as string))) {
      errors.expectedMisstatement = '预期错报必须小于可容忍错报'
    }
  }

  return errors
}

/**
 * 强制方法学参数（置信度/可容忍错报）必填的统计抽样方法集合（R20）。
 *
 * 仅 MUS 纳入：其抽样间隔与样本量由置信度/可容忍错报推导，缺参无法执行。
 * random/systematic/stratified 保留既有基于各自参数（sampleSize/interval/strata）的
 * 校验以向后兼容；specific_item 为判断（非统计）选取。
 */
const STATISTICAL_METHODS: ReadonlyArray<SamplingMethod> = ['mus']

// ─── computeVersionDiff ──────────────────────────────────────────────────────

/**
 * 计算版本对比 diff（按 voucher_no 集合匹配）
 *
 * - added: B \ A（在 B 中但不在 A 中）
 * - removed: A \ B（在 A 中但不在 B 中）
 * - retained: A ∩ B（两者都有）
 *
 * 保证三集合互斥且完全覆盖 A ∪ B
 */
export function computeVersionDiff(
  vouchersA: string[],
  vouchersB: string[],
): VersionDiffResult {
  const setA = new Set(vouchersA)
  const setB = new Set(vouchersB)

  const added: string[] = []
  const removed: string[] = []
  const retained: string[] = []

  // B \ A + A ∩ B
  for (const v of setB) {
    if (setA.has(v)) {
      retained.push(v)
    } else {
      added.push(v)
    }
  }

  // A \ B
  for (const v of setA) {
    if (!setB.has(v)) {
      removed.push(v)
    }
  }

  return { added, removed, retained }
}

// ─── 方法学增强：科学样本量推导（MUS）纯函数基座 ──────────────────────────────
//
// 金额一律用 Decimal 字符串运算，避免浮点误差。
//
// Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 17.1, 17.2, 17.3, 17.4, 20.1

/**
 * Decimal 安全解析：非法/非有限输入回退为 0。
 * 内部辅助，所有金额运算入口统一走此函数。
 */
function toDecimal(v: string | number | null | undefined): Decimal {
  try {
    const d = new Decimal(v ?? 0)
    return d.isFinite() ? d : new Decimal(0)
  } catch {
    return new Decimal(0)
  }
}

/**
 * CAS 1314 泊松可信赖度系数常量表（附录常用因子）
 *
 * - `base`：预期错报为 0 时的可信赖度系数（如 95%→3.0、90%→2.31）。
 * - `increment`：每增加一个（当量）预期错报的 tainting 增量因子
 *   （由标准泊松表「1 个错报因子 − 0 个错报因子」推导，用于按预期错报线性外推）。
 *
 * 置信度落在表格之间时取最近邻。
 */
export interface ReliabilityRow {
  confidence: number
  base: number
  increment: number
}

export const CAS1314_RELIABILITY_TABLE: ReadonlyArray<ReliabilityRow> = [
  { confidence: 0.50, base: 0.70, increment: 1.14 },
  { confidence: 0.63, base: 1.00, increment: 1.21 },
  { confidence: 0.70, base: 1.21, increment: 1.27 },
  { confidence: 0.75, base: 1.39, increment: 1.32 },
  { confidence: 0.80, base: 1.61, increment: 1.38 },
  { confidence: 0.85, base: 1.90, increment: 1.47 },
  { confidence: 0.90, base: 2.31, increment: 1.58 },
  { confidence: 0.95, base: 3.00, increment: 1.75 },
  { confidence: 0.99, base: 4.61, increment: 2.03 },
]

/**
 * 取与目标置信度最近邻的可信赖度系数表行。
 */
function nearestReliabilityRow(confidenceLevel: number): ReliabilityRow {
  let best = CAS1314_RELIABILITY_TABLE[0]
  let bestDist = Math.abs(best.confidence - confidenceLevel)
  for (const row of CAS1314_RELIABILITY_TABLE) {
    const dist = Math.abs(row.confidence - confidenceLevel)
    if (dist < bestDist) {
      best = row
      bestDist = dist
    }
  }
  return best
}

/**
 * R15 可信赖度系数 R(置信度, 预期错报数)
 *
 * 泊松因子随预期错报数线性外推：`base + max(0, expectedErrors) × increment`。
 * `expectedErrors` 允许为小数（如按 预期错报/可容忍错报 得到的当量错报负荷）。
 *
 * @param confidenceLevel 置信度，如 0.95（取最近邻表行）
 * @param expectedErrors 预期错报数（当量），负值按 0 处理
 * @returns 可信赖度系数（正数，保留 6 位小数以消除浮点噪声）
 */
export function reliabilityFactor(confidenceLevel: number, expectedErrors: number): number {
  const row = nearestReliabilityRow(confidenceLevel)
  const errors = Number.isFinite(expectedErrors) && expectedErrors > 0 ? expectedErrors : 0
  const factor = row.base + errors * row.increment
  return Math.round(factor * 1e6) / 1e6
}

/**
 * R15/R17 MUS 抽样间隔
 *
 * 间隔 = 可容忍错报 / 可信赖度系数。预期错报以「预期错报/可容忍错报」当量错报负荷
 * 抬升可信赖度系数（预期错报越大 → 系数越大 → 间隔越小 → 样本量越大）。
 * 间隔恒 > 0（当可容忍错报 > 0 时）。金额用 Decimal，结果保留 2 位小数。
 *
 * @param tolerable 可容忍错报（Decimal 字符串）
 * @param confidenceLevel 置信度，如 0.95
 * @param expected 预期错报（Decimal 字符串）
 * @returns 抽样间隔（Decimal 字符串，2 位小数）；可容忍错报 ≤ 0 时返回 "0.00"
 */
export function computeMusInterval(
  tolerable: string,
  confidenceLevel: number,
  expected: string,
): string {
  const tol = toDecimal(tolerable)
  if (tol.lte(0)) return (0).toFixed(2)

  const exp = toDecimal(expected)
  // 当量错报负荷 = 预期错报 / 可容忍错报（非负）
  const load = exp.gt(0) ? exp.div(tol).toNumber() : 0
  const rf = reliabilityFactor(confidenceLevel, load)
  if (rf <= 0) return (0).toFixed(2)

  return tol.div(new Decimal(rf)).toFixed(2, Decimal.ROUND_HALF_EVEN)
}

/**
 * R15 科学样本量推导（MUS）
 *
 * 样本量 = ceil(总体金额 / 抽样间隔)。
 * 随可容忍错报增大而不增（样本量↓），随置信度提高而不减（样本量↑）。
 *
 * @param populationAmount 总体金额（Decimal 字符串）
 * @param tolerable 可容忍错报（Decimal 字符串）
 * @param expected 预期错报（Decimal 字符串）
 * @param confidenceLevel 置信度，如 0.95
 * @returns 建议样本量（非负整数）；间隔或总体金额 ≤ 0 时返回 0
 */
export function computeSampleSize(
  populationAmount: string,
  tolerable: string,
  expected: string,
  confidenceLevel: number,
): number {
  const interval = toDecimal(computeMusInterval(tolerable, confidenceLevel, expected))
  if (interval.lte(0)) return 0

  const pop = toDecimal(populationAmount)
  if (pop.lte(0)) return 0

  return pop.div(interval).ceil().toNumber()
}

/**
 * R17 高值层标识：单笔金额 ≥ 抽样间隔的凭证 100% 必选
 *
 * - 金额 ≥ interval：`isHighValue = true` 且 `selected = true`。
 * - 金额 < interval：`isHighValue = false`，不强制选中（保留原 selected）。
 * 单笔金额取借贷方绝对值较大者。返回新数组，不修改入参。
 *
 * @param vouchers 候选样本
 * @param interval 抽样间隔（Decimal 字符串）
 */
export function markHighValueItems(
  vouchers: SampledVoucher[],
  interval: string,
): SampledVoucher[] {
  const intv = toDecimal(interval)
  return vouchers.map((v) => {
    const amount = Decimal.max(
      toDecimal(v.debitAmount).abs(),
      toDecimal(v.creditAmount).abs(),
    )
    const isHigh = intv.gt(0) && amount.gte(intv)
    return {
      ...v,
      isHighValue: isHigh,
      selected: isHigh ? true : v.selected,
    }
  })
}

// ─── 方法学增强：错报推断与总体结论纯函数 ──────────────────────────────────
//
// spec: voucher-check-sampling-integration, Task 2（design B.2）
// 金额一律用 Decimal 字符串运算，避免浮点误差。
//
// Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 19.1, 19.2, 19.3, 20.2, 20.3

/** 经典（比率估计）法抽样风险余量基准（相对 95% 可信赖度系数缩放）。 */
const CLASSIC_BASE_MARGIN = 0.5

/** 取单笔凭证的账面金额（借贷方绝对值较大者）。 */
function voucherBookAmount(v: SampledVoucher): Decimal {
  return Decimal.max(toDecimal(v.debitAmount).abs(), toDecimal(v.creditAmount).abs())
}

/** 单笔污染率 tainting = clamp(实际错报 / 账面, 0, 1)；账面 ≤ 0 时为 0。 */
function voucherTainting(v: SampledVoucher): Decimal {
  const book = voucherBookAmount(v)
  if (book.lte(0)) return new Decimal(0)
  const ratio = toDecimal(v.actualMisstatement).div(book)
  if (ratio.lte(0)) return new Decimal(0)
  return ratio.gte(1) ? new Decimal(1) : ratio
}

/**
 * R18 错报推断
 *
 * - 货币单元抽样（mus）：
 *   - 高值层（isHighValue，100% 检查）已知错报直接汇总（不外推）。
 *   - 常规层：projected_sampling = Σ(tainting_i × 间隔)。
 *   - 基本准备 basicPrecision = 可信赖度系数(0错报) × 间隔。
 *   - 增量准备 incrementalAllowance = Σ(可信赖度增量因子 − 1) × tainting × 间隔（常规层）。
 * - 经典（随机/系统/分层/特定）：比率估计 projected = (Σ样本错报 / Σ样本金额) × 总体金额；
 *   基本准备为 0，增量准备按可信赖度系数相对 95% 缩放的余量比例计算。
 *
 * `projected` 恒 ≥ 0；样本错报全为 0 → projected = 0。
 * `upperLimit` 由 computeUpperMisstatementLimit 计算填入。
 *
 * @param samples 已检查样本（含 actualMisstatement / isHighValue）
 * @param method 抽样方法
 * @param interval MUS 抽样间隔（Decimal 字符串，经典法可传 "0"）
 * @param populationAmount 总体金额（Decimal 字符串）
 * @param confidenceLevel 置信度（默认 0.95），用于基本/增量准备的可信赖度系数
 */
export function projectMisstatement(
  samples: SampledVoucher[],
  method: SamplingMethod,
  interval: string,
  populationAmount: string,
  confidenceLevel = 0.95,
): MisstatementResult {
  const list = Array.isArray(samples) ? samples : []
  const rfBase = new Decimal(reliabilityFactor(confidenceLevel, 0))

  if (method === 'mus') {
    const intv = toDecimal(interval)
    let knownHighValue = new Decimal(0)
    let projectedSampling = new Decimal(0)
    let incremental = new Decimal(0)

    // 可信赖度增量因子（用于增量准备）；取最近邻表行的 increment。
    const incFactor = new Decimal(nearestReliabilityIncrement(confidenceLevel))
    const incMinusOne = Decimal.max(incFactor.minus(1), new Decimal(0))

    for (const v of list) {
      if (v.isHighValue) {
        // 高值层：已知错报直接计入（clamp ≥ 0，避免低估上限）
        const err = Decimal.max(toDecimal(v.actualMisstatement), new Decimal(0))
        knownHighValue = knownHighValue.plus(err)
      } else {
        const tainting = voucherTainting(v)
        const contrib = tainting.times(intv)
        projectedSampling = projectedSampling.plus(contrib)
        incremental = incremental.plus(incMinusOne.times(contrib))
      }
    }

    const projected = Decimal.max(projectedSampling.plus(knownHighValue), new Decimal(0))
    // 基本准备 = 可信赖度系数(0错报) × 间隔（间隔 ≤ 0 时为 0）
    const basicPrecision = intv.gt(0) ? rfBase.times(intv) : new Decimal(0)

    const result: MisstatementResult = {
      projected: projected.toFixed(2, Decimal.ROUND_HALF_EVEN),
      knownHighValue: knownHighValue.toFixed(2, Decimal.ROUND_HALF_EVEN),
      basicPrecision: basicPrecision.toFixed(2, Decimal.ROUND_HALF_EVEN),
      incrementalAllowance: incremental.toFixed(2, Decimal.ROUND_HALF_EVEN),
      upperLimit: '0.00',
    }
    result.upperLimit = computeUpperMisstatementLimit(result)
    return result
  }

  // 经典（比率估计）：projected = (Σ错报 / Σ金额) × 总体金额
  let sumError = new Decimal(0)
  let sumBook = new Decimal(0)
  let knownHighValue = new Decimal(0)
  for (const v of list) {
    sumError = sumError.plus(toDecimal(v.actualMisstatement))
    sumBook = sumBook.plus(voucherBookAmount(v))
    if (v.isHighValue) {
      knownHighValue = knownHighValue.plus(Decimal.max(toDecimal(v.actualMisstatement), new Decimal(0)))
    }
  }
  const pop = toDecimal(populationAmount)
  const ratioProjected = sumBook.gt(0) ? sumError.div(sumBook).times(pop) : new Decimal(0)
  const projected = Decimal.max(ratioProjected, new Decimal(0))

  // 抽样风险余量：按可信赖度系数相对 95% 基准缩放的余量比例
  const rf95 = new Decimal(reliabilityFactor(0.95, 0))
  const marginRatio = rf95.gt(0)
    ? rfBase.div(rf95).times(CLASSIC_BASE_MARGIN)
    : new Decimal(CLASSIC_BASE_MARGIN)
  const incremental = projected.times(marginRatio)

  const result: MisstatementResult = {
    projected: projected.toFixed(2, Decimal.ROUND_HALF_EVEN),
    knownHighValue: knownHighValue.toFixed(2, Decimal.ROUND_HALF_EVEN),
    basicPrecision: (0).toFixed(2),
    incrementalAllowance: incremental.toFixed(2, Decimal.ROUND_HALF_EVEN),
    upperLimit: '0.00',
  }
  result.upperLimit = computeUpperMisstatementLimit(result)
  return result
}

/**
 * R18.4 错报上限 UML = projected + basicPrecision + incrementalAllowance。
 *
 * 由于 basicPrecision 与 incrementalAllowance 恒 ≥ 0，UML ≥ projected ≥ 0。
 * 兜底再做一次 max(projected) 钳制，消除浮点/舍入噪声导致的下溢。
 *
 * @returns 错报上限（Decimal 字符串，2 位小数）
 */
export function computeUpperMisstatementLimit(r: MisstatementResult): string {
  const projected = toDecimal(r.projected)
  const uml = projected
    .plus(Decimal.max(toDecimal(r.basicPrecision), new Decimal(0)))
    .plus(Decimal.max(toDecimal(r.incrementalAllowance), new Decimal(0)))
  return Decimal.max(uml, projected, new Decimal(0)).toFixed(2, Decimal.ROUND_HALF_EVEN)
}

/**
 * R18.5/18.6 抽样结论
 *
 * UML ≤ 可容忍错报 → accepted=true（边界 UML == tolerable 视为可接受）；
 * UML > 可容忍错报 → accepted=false，建议扩大样本/替代程序/提请调整。
 *
 * @param uml 错报上限（Decimal 字符串）
 * @param tolerable 可容忍错报（Decimal 字符串）
 */
export function deriveSamplingConclusion(uml: string, tolerable: string): SamplingConclusion {
  const u = toDecimal(uml)
  const t = toDecimal(tolerable)
  const accepted = u.lte(t)
  return {
    accepted,
    message: accepted
      ? '总体可接受：错报上限未超过可容忍错报'
      : '总体可能存在重大错报，建议扩大样本、执行替代程序或提请调整',
  }
}

/**
 * R19 总体完整性校验
 *
 * diff = |抽样总体金额 − 账面金额|；
 * withinThreshold = diff ≤ 账面金额 × thresholdPct。
 *
 * @param samplingPopAmount 抽样总体金额（Decimal 字符串）
 * @param bookAmount 账面金额（序时账/明细/审定，Decimal 字符串）
 * @param thresholdPct 可容忍差异比例（小数，如 0.05 = 5%）
 */
export function reconcilePopulation(
  samplingPopAmount: string,
  bookAmount: string,
  thresholdPct: number,
): PopulationReconcile {
  const sp = toDecimal(samplingPopAmount)
  const book = toDecimal(bookAmount)
  const diff = sp.minus(book).abs()
  const threshold = book.times(toDecimal(thresholdPct))
  const withinThreshold = diff.lte(threshold)
  return {
    samplingPopulationAmount: sp.toFixed(2, Decimal.ROUND_HALF_EVEN),
    bookAmount: book.toFixed(2, Decimal.ROUND_HALF_EVEN),
    diff: diff.toFixed(2, Decimal.ROUND_HALF_EVEN),
    withinThreshold,
  }
}

/**
 * 取与目标置信度最近邻表行的可信赖度增量因子（用于 MUS 增量准备）。
 */
function nearestReliabilityIncrement(confidenceLevel: number): number {
  let best = CAS1314_RELIABILITY_TABLE[0]
  let bestDist = Math.abs(best.confidence - confidenceLevel)
  for (const row of CAS1314_RELIABILITY_TABLE) {
    const dist = Math.abs(row.confidence - confidenceLevel)
    if (dist < bestDist) {
      best = row
      bestDist = dist
    }
  }
  return best.increment
}

// ─── 抽样计划与结论备忘（Sampling_Memo）导出 ─────────────────────────────────
//
// spec: voucher-check-sampling-integration, Task 13（可选）
// Requirements: 21.1, 21.2
//
// 纯函数：以当前抽样批次的实际数据（R21.2）组装 Sampling_Memo 文本，内容涵盖
// 抽样方法、抽样参数、样本量推导依据、覆盖率统计、错报推断与 Sampling_Conclusion（R21.1）。
// 金额一律以“元”呈现；缺失的可选段落以“—”占位，不臆造数据。

/** 抽样方法中文标签（与配置/历史抽屉展示一致） */
export const SAMPLING_METHOD_LABELS: Record<SamplingMethod, string> = {
  random: '随机抽样',
  stratified: '金额分层抽样',
  specific_item: '特定项目选取',
  systematic: '系统抽样（等距）',
  mus: '货币单元抽样（MUS）',
}

/** 借贷方向中文标签 */
const DIRECTION_LABELS: Record<'debit' | 'credit' | 'all', string> = {
  debit: '仅借方',
  credit: '仅贷方',
  all: '不限',
}

/**
 * Sampling_Memo 组装入参（以当前抽样批次的实际状态传入，R21.2）。
 */
export interface SamplingMemoInput {
  /** 当前抽样配置（方法/参数/过滤条件/建议样本量留痕等） */
  config: SamplingConfig
  /** 覆盖率统计（笔数/金额覆盖率、样本量、总体金额），无抽样批次时为 null */
  coverageStats: CoverageStats | null
  /** MUS 抽样间隔（Decimal 字符串），非 MUS 或未推导时为 null */
  samplingInterval: string | null
  /** 系统建议样本量（R15 留痕），未推导时为 null */
  suggestedSampleSize: number | null
  /** 错报推断结果（R18），未推断时为 null */
  misstatementResult: MisstatementResult | null
  /** 抽样结论（R18.5/18.6），可容忍错报缺失时为 null */
  samplingConclusion: SamplingConclusion | null
  /** 本批次随机种子（R22.2 可复现），无则 null */
  seedUsed: number | null
  /** 已回填/勾选的样本笔数 */
  sampleCount: number
  /** 备忘生成时间（ISO 字符串）；缺省时由函数内取当前时间 */
  generatedAt?: string
}

/** 内部：金额展示（附“元”单位），空值回退占位符 */
function fmtAmountYuan(value: string | null | undefined, placeholder = '—'): string {
  if (value == null || value === '') return placeholder
  return `${value} 元`
}

/** 内部：百分比展示，空值回退占位符 */
function fmtPercent(value: string | null | undefined, placeholder = '—'): string {
  if (value == null || value === '') return placeholder
  return `${value}%`
}

/**
 * 构建 Sampling_Memo 文本（Markdown）。
 *
 * 恒定包含以下六大段落（R21.1）：抽样方法、抽样参数、样本量推导依据、覆盖率统计、
 * 错报推断、抽样结论；并附随机种子与重抽原因。所有金额以“元”呈现。
 *
 * @param input 当前抽样批次的实际状态（R21.2）
 * @returns Markdown 文本
 */
export function buildSamplingMemo(input: SamplingMemoInput): string {
  const {
    config,
    coverageStats,
    samplingInterval,
    suggestedSampleSize,
    misstatementResult,
    samplingConclusion,
    seedUsed,
    sampleCount,
  } = input

  const generatedAt = input.generatedAt ?? new Date().toISOString()
  const methodLabel = SAMPLING_METHOD_LABELS[config.samplingMethod] ?? config.samplingMethod
  const accounts = config.accountCodes && config.accountCodes.length > 0
    ? config.accountCodes.join('、')
    : '—'
  const confidenceText = config.confidenceLevel != null
    ? `${(config.confidenceLevel * 100).toFixed(0)}%`
    : '—'

  const lines: string[] = []

  lines.push('# 抽样计划与结论备忘（Sampling Memo）')
  lines.push('')
  lines.push(`生成时间：${generatedAt}`)
  lines.push('')

  // 一、抽样方法（R21.1）
  lines.push('## 一、抽样方法')
  lines.push(`- 抽样方法：${methodLabel}`)
  lines.push(`- 抽样科目：${accounts}`)
  lines.push(`- 凭证方向：${DIRECTION_LABELS[config.directionFilter] ?? '不限'}`)
  lines.push('')

  // 二、抽样参数（R21.1）
  lines.push('## 二、抽样参数')
  lines.push(`- 置信度（信赖水平）：${confidenceText}`)
  lines.push(`- 可容忍错报：${fmtAmountYuan(config.tolerableMisstatement)}`)
  lines.push(`- 预期错报：${fmtAmountYuan(config.expectedMisstatement)}`)
  lines.push('')

  // 三、样本量推导依据（R21.1）
  lines.push('## 三、样本量推导依据')
  lines.push(`- 系统建议样本量：${suggestedSampleSize != null && suggestedSampleSize > 0 ? `${suggestedSampleSize} 笔` : '—'}`)
  lines.push(`- 实际样本量：${sampleCount} 笔`)
  lines.push(`- MUS 抽样间隔：${fmtAmountYuan(samplingInterval)}`)
  lines.push('')

  // 四、覆盖率统计（R21.1）
  lines.push('## 四、覆盖率统计')
  if (coverageStats) {
    lines.push(`- 总体笔数：${coverageStats.populationCount} 笔`)
    lines.push(`- 总体金额：${fmtAmountYuan(coverageStats.populationAmount)}`)
    lines.push(`- 样本笔数：${coverageStats.sampleCount} 笔`)
    lines.push(`- 样本金额：${fmtAmountYuan(coverageStats.sampleAmount)}`)
    lines.push(`- 笔数覆盖率：${fmtPercent(coverageStats.countCoverageRate)}`)
    lines.push(`- 金额覆盖率：${fmtPercent(coverageStats.amountCoverageRate)}`)
  } else {
    lines.push('- 暂无覆盖率数据（尚未执行抽样）')
  }
  lines.push('')

  // 五、错报推断（R21.1）
  lines.push('## 五、错报推断')
  if (misstatementResult) {
    lines.push(`- 推断错报：${fmtAmountYuan(misstatementResult.projected)}`)
    lines.push(`- 高值层已知错报：${fmtAmountYuan(misstatementResult.knownHighValue)}`)
    lines.push(`- 基本准备：${fmtAmountYuan(misstatementResult.basicPrecision)}`)
    lines.push(`- 增量准备：${fmtAmountYuan(misstatementResult.incrementalAllowance)}`)
    lines.push(`- 错报上限（UML）：${fmtAmountYuan(misstatementResult.upperLimit)}`)
  } else {
    lines.push('- 暂无错报推断数据（尚未录入样本实际错报）')
  }
  lines.push('')

  // 六、抽样结论 Sampling_Conclusion（R21.1）
  lines.push('## 六、抽样结论（Sampling Conclusion）')
  if (samplingConclusion) {
    lines.push(`- 结论：${samplingConclusion.accepted ? '总体可接受' : '总体不可接受，需扩大样本或提请调整'}`)
    lines.push(`- 说明：${samplingConclusion.message}`)
  } else {
    lines.push('- 暂无结论（请先填写可容忍错报并完成错报推断）')
  }
  lines.push('')

  // 附：可复现与重抽治理（R22 留痕）
  lines.push('## 附：可复现与重抽治理')
  lines.push(`- 随机种子：${seedUsed != null ? String(seedUsed) : '—'}`)
  lines.push(`- 重抽原因：${config.resampleReason && config.resampleReason !== '' ? config.resampleReason : '—'}`)
  lines.push('')

  return lines.join('\n')
}

// ─── 方法学增强：属性抽样（控制测试）纯函数 ─────────────────────────────────
//
// spec: voucher-check-sampling-integration, Task 14（可选/后续，design B.2）
// Requirements: 23.1, 23.2, 23.3
//
// 属性抽样用于控制测试（评价控制运行有效性），以「偏差率」而非「金额」为度量，
// 复用与 MUS 同源的 CAS 1314 泊松可信赖度系数表（reliabilityFactor）。
//
// R23.3：本模块为可选/后续能力，纯附加，不改动既有金额法（MUS/随机/系统/分层/
// 特定项目）的任何函数与数据结构；金额法流程完全不受影响。

/** 属性抽样默认可容忍偏差率（5%），仅用于 evaluateDeviationRate 未显式传入时的兜底。 */
export const DEFAULT_TOLERABLE_DEVIATION_RATE = 0.05

/** 将比率钳制到 [0, 1]；非有限值回退为 0。 */
function clampRate(rate: number): number {
  if (!Number.isFinite(rate)) return 0
  if (rate < 0) return 0
  if (rate > 1) return 1
  return rate
}

/**
 * R23.1 属性抽样样本量推导（控制测试）
 *
 * 经典属性抽样样本量公式（泊松近似）：
 *
 *   n = ceil( R(置信度, 0) / (可容忍偏差率 − 预期偏差率) )
 *
 * 其中 `R(置信度, 0)` 为 0 偏差基准下的可信赖度系数（复用 `reliabilityFactor`，
 * 即与 MUS 同源的 CAS 1314 泊松表）。分母 `(可容忍 − 预期)` 为精度余量：
 * 余量越大所需样本越少；置信度越高可信赖度系数越大所需样本越多。
 *
 * 单调性（供属性测试）：
 * - 可容忍偏差率 ↑ → 分母 ↑ → 样本量不增（更小/相等）。
 * - 置信度 ↑ → 可信赖度系数不减 → 样本量不减（更大/相等）。
 *
 * 边界处理：
 * - 偏差率钳制到 [0, 1]。
 * - 精度余量 `(可容忍 − 预期) ≤ 0`（含预期 ≥ 可容忍的非法配置）→ 返回 0（无法推导）。
 *
 * @param expectedDevRate 预期总体偏差率（0~1）
 * @param tolerableDevRate 可容忍偏差率（0~1）
 * @param confidenceLevel 置信度/信赖水平，如 0.95（取最近邻表行）
 * @returns 建议样本量（非负整数）；精度余量 ≤ 0 时返回 0
 */
export function computeAttributeSampleSize(
  expectedDevRate: number,
  tolerableDevRate: number,
  confidenceLevel: number,
): number {
  const expected = clampRate(expectedDevRate)
  const tolerable = clampRate(tolerableDevRate)
  const precisionGap = tolerable - expected
  if (precisionGap <= 0) return 0

  const rf = reliabilityFactor(confidenceLevel, 0)
  if (rf <= 0) return 0

  return Math.ceil(rf / precisionGap)
}

/**
 * R23.2 偏差率评价（控制测试结论）
 *
 * 依据观察到的偏差数推导「偏差率上限」（CUDR，泊松近似）并与可容忍偏差率比较：
 *
 *   偏差率上限 = R(置信度, 偏差数) / 样本量
 *   有效 = 偏差率上限 ≤ 可容忍偏差率
 *
 * 其中 `R(置信度, 偏差数)` 复用 `reliabilityFactor`（随偏差数线性外推的泊松系数）。
 * 由于 `R(置信度, k) ≥ k`（base ≥ 0.7、increment ≥ 1.14），
 * 恒有 `偏差率上限 ≥ 实测偏差率(=偏差数/样本量)`——即上限不会低于样本实测。
 *
 * @param sampleSize 样本量（> 0；≤ 0 时返回上限 1、无效）
 * @param deviations 观察到的偏差数（非负；自动钳制到 [0, sampleSize]）
 * @param confidenceLevel 置信度，如 0.95
 * @param tolerableDevRate 可容忍偏差率（0~1）；缺省用 DEFAULT_TOLERABLE_DEVIATION_RATE。
 *   注：design B.2 的三参签名为本函数的严格子集（第四参可选，向后兼容）。
 * @returns `{ upperDevRate, effective }`：upperDevRate 保留 6 位小数消除浮点噪声
 */
export function evaluateDeviationRate(
  sampleSize: number,
  deviations: number,
  confidenceLevel: number,
  tolerableDevRate: number = DEFAULT_TOLERABLE_DEVIATION_RATE,
): { upperDevRate: number; effective: boolean } {
  const tolerable = clampRate(tolerableDevRate)

  // 样本量非法：无法评价，保守返回上限 1、无效
  if (!Number.isFinite(sampleSize) || sampleSize <= 0) {
    return { upperDevRate: 1, effective: false }
  }

  const n = Math.floor(sampleSize)
  const devs = Number.isFinite(deviations) && deviations > 0
    ? Math.min(Math.floor(deviations), n)
    : 0

  const rf = reliabilityFactor(confidenceLevel, devs)
  const rawUpper = rf / n
  const upperDevRate = Math.round(clampRate(rawUpper) * 1e6) / 1e6

  return {
    upperDevRate,
    effective: upperDevRate <= tolerable,
  }
}
