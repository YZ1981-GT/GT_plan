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
 */

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

  return errors
}

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
