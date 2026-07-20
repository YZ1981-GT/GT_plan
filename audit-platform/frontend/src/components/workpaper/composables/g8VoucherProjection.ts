/**
 * G8-6 错报推断（复用 useSamplingAlgorithms，不重写 UML 数学）
 *
 * MVP：经典比率估计为主；method 含 mus 时走 MUS 路径（需抽样间隔）。
 * 仅金额类 / 混合异常进入推断样本；实际错报优先用行上 actualMisstatement。
 */
import {
  projectMisstatement,
  computeUpperMisstatementLimit,
  deriveSamplingConclusion,
  type MisstatementResult,
  type SamplingConclusion,
  type SamplingMethod,
  type SampledVoucher,
  type Phase,
} from './useSamplingAlgorithms'
import { parseNum } from './useG8FormulaEngine'
import type { G8VoucherRow } from './useG8VoucherCheck'
import type { G8SamplingParams } from './useG8VoucherCheck'

export interface G8ProjectionInput {
  rows: G8VoucherRow[]
  params: G8SamplingParams
  /** 未填实际错报时，是否用账面发生额预填（仅 quantitative/mixed） */
  useSuggestedWhenEmpty?: boolean
}

export interface G8ProjectionView {
  canProject: boolean
  reason: string
  method: SamplingMethod
  sampleCount: number
  withMisstatementCount: number
  missingMisstatementCount: number
  populationAmount: string
  tolerableMisstatement: string
  result: MisstatementResult | null
  uml: string
  conclusion: SamplingConclusion | null
}

/** 金额类异常建议的实际错报：取借贷发生额较大者 */
export function suggestG8ActualMisstatement(row: G8VoucherRow): number {
  if (!row.isAbnormal) return 0
  if (row.abnormalType !== 'quantitative' && row.abnormalType !== 'mixed') return 0
  return Math.max(Math.abs(parseNum(row.debitAmount)), Math.abs(parseNum(row.creditAmount)))
}

export function resolveG8ProjectionMethod(raw: string | undefined): SamplingMethod {
  const s = String(raw || '').trim().toLowerCase()
  if (s === 'mus' || s.includes('货币') || s.includes('mus')) return 'mus'
  if (s === 'systematic' || s.includes('系统')) return 'systematic'
  if (s === 'stratified' || s.includes('分层')) return 'stratified'
  if (s === 'specific' || s.includes('特定')) return 'specific'
  return 'random'
}

function emptySampled(overrides: Partial<SampledVoucher>): SampledVoucher {
  return {
    voucherNo: '',
    voucherDate: '',
    summary: null,
    debitAmount: null,
    creditAmount: null,
    accountCode: '1503',
    accountName: '其他权益工具投资',
    counterpartAccount: null,
    voucherType: null,
    accountingPeriod: null,
    checkResult: '',
    abnormal: false,
    remark: '',
    selected: true,
    phase: 'final' as Phase,
    editTrail: [],
    ...overrides,
  }
}

/** 解析行上实际错报；可选回退到建议值 */
export function resolveG8RowActualMisstatement(
  row: G8VoucherRow,
  useSuggestedWhenEmpty = false,
): number {
  const explicit = parseNum(row.actualMisstatement)
  if (explicit > 0) return explicit
  if (useSuggestedWhenEmpty) return suggestG8ActualMisstatement(row)
  return 0
}

export function mapG8RowsToProjectionSamples(
  rows: G8VoucherRow[],
  useSuggestedWhenEmpty = false,
): SampledVoucher[] {
  return rows
    .filter((r) => r.isAbnormal && (r.abnormalType === 'quantitative' || r.abnormalType === 'mixed'))
    .map((r) => {
      const err = resolveG8RowActualMisstatement(r, useSuggestedWhenEmpty)
      return emptySampled({
        voucherNo: r.voucherNo || r.rowId,
        voucherDate: r.voucherDate || '',
        summary: r.businessContent || null,
        debitAmount: String(r.debitAmount ?? 0),
        creditAmount: String(r.creditAmount ?? 0),
        counterpartAccount: r.counterAccount || null,
        abnormal: true,
        isHighValue: !!r.isHighValue || r.riskLevel === 'high',
        actualMisstatement: String(err),
        remark: r.remark || '',
      })
    })
}

/**
 * 表级错报推断视图。
 * - 无总体金额 / 无可容忍错报 → 不可推断
 * - 无金额类异常 → 可推断但结果为 0（总体可接受，需说明无发现）
 */
export function computeG8Projection(input: G8ProjectionInput): G8ProjectionView {
  const method = resolveG8ProjectionMethod(input.params.samplingMethod)
  const populationAmount = String(input.params.populationAmount || 0)
  const tolerable = String(input.params.tolerableMisstatement || 0)
  const confidence = input.params.confidenceLevel > 0 ? input.params.confidenceLevel : 0.95
  const useSuggested = !!input.useSuggestedWhenEmpty

  const quantRows = input.rows.filter(
    (r) => r.isAbnormal && (r.abnormalType === 'quantitative' || r.abnormalType === 'mixed'),
  )
  const samples = mapG8RowsToProjectionSamples(input.rows, useSuggested)
  const withMisstatementCount = samples.filter((s) => parseNum(s.actualMisstatement) > 0).length
  const missingMisstatementCount = quantRows.length - withMisstatementCount

  if (!(input.params.populationAmount > 0)) {
    return {
      canProject: false,
      reason: '请先填写抽样参数中的「总体金额」',
      method,
      sampleCount: samples.length,
      withMisstatementCount,
      missingMisstatementCount,
      populationAmount,
      tolerableMisstatement: tolerable,
      result: null,
      uml: '0.00',
      conclusion: null,
    }
  }
  if (!(input.params.tolerableMisstatement > 0)) {
    return {
      canProject: false,
      reason: '请先填写「可容忍错报」',
      method,
      sampleCount: samples.length,
      withMisstatementCount,
      missingMisstatementCount,
      populationAmount,
      tolerableMisstatement: tolerable,
      result: null,
      uml: '0.00',
      conclusion: null,
    }
  }

  // MUS 需要间隔：用 可容忍/可信赖系数 近似，或用 params 中已有目标推算
  let interval = '0'
  if (method === 'mus') {
    const n = input.params.targetSampleSize || input.params.currentSampleSize || samples.length || 1
    const pop = input.params.populationAmount
    interval = n > 0 ? (pop / n).toFixed(2) : '0'
  }

  const result = projectMisstatement(samples, method, interval, populationAmount, confidence)
  const uml = computeUpperMisstatementLimit(result)
  const conclusion = deriveSamplingConclusion(uml, tolerable)

  let reason = ''
  if (quantRows.length === 0) {
    reason = '当前无金额类异常；推断错报为 0'
  } else if (missingMisstatementCount > 0 && !useSuggested) {
    reason = `有 ${missingMisstatementCount} 笔金额异常未填实际错报，未计入推断（可点「预填建议错报」）`
  }

  return {
    canProject: true,
    reason,
    method,
    sampleCount: samples.length,
    withMisstatementCount,
    missingMisstatementCount,
    populationAmount,
    tolerableMisstatement: tolerable,
    result,
    uml,
    conclusion,
  }
}

/** 抽样备忘「错报推断」段落 */
export function formatG8ProjectionMemoSection(view: G8ProjectionView): string {
  const lines: string[] = []
  lines.push('## 六、错报推断')
  if (!view.canProject) {
    lines.push(`- 状态：未推断（${view.reason}）`)
    return lines.join('\n')
  }
  lines.push(`- 方法：${view.method}`)
  lines.push(`- 金额类样本：${view.sampleCount}（已填实际错报 ${view.withMisstatementCount}）`)
  lines.push(`- 总体金额：${view.populationAmount}`)
  lines.push(`- 可容忍错报：${view.tolerableMisstatement}`)
  if (view.result) {
    lines.push(`- 推断错报：${view.result.projected}`)
    lines.push(`- 高值层已知：${view.result.knownHighValue}`)
    lines.push(`- 基本准备：${view.result.basicPrecision}`)
    lines.push(`- 增量准备：${view.result.incrementalAllowance}`)
    lines.push(`- 错报上限 UML：${view.uml}`)
  }
  if (view.conclusion) {
    lines.push(`- 总体结论：${view.conclusion.accepted ? '可接受' : '不可接受'} — ${view.conclusion.message}`)
  }
  if (view.reason) lines.push(`- 备注：${view.reason}`)
  return lines.join('\n')
}
