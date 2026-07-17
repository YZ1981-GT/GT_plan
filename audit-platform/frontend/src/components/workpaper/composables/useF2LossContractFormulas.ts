/**
 * F2-58 亏损合同预计损失测算表（对齐致同源模板）
 *
 * ④=③−② 合同预计损失；⑤=④×① 已在损益反映；⑥=④−⑤ 本期应确认；⑧=⑥−⑦
 */
import {
  calcSubtotal,
  isLossContract,
} from './useF2SpecialFormulaEngine'

export type YesNo = '是' | '否' | ''

export interface LossContractProject {
  id: string
  projectCode: string
  projectName: string
  /** ① 完工进度（0~1）；若填写已确认收入则优先按收入占比计算 */
  completionRate: number
  recognizedRevenue: number
  /** ② 预计总收入 */
  estimatedTotalRevenue: number
  /** ③ 预计总成本 */
  estimatedTotalCost: number
  /** ⑤ 已在损益反映的亏损（0 时自动=④×①） */
  priorRecognizedLoss: number
  /** ⑦ 本期账面已确认合同亏损金额 */
  bookRecognizedLoss: number
  remark: string
}

export interface LossContractSheet {
  projects: LossContractProject[]
}

export interface EnrichedLossContract extends LossContractProject {
  effectiveCompletionRate: number
  isLoss: YesNo
  contractEstimatedLoss: number
  recognizedLossInPl: number
  currentPeriodLoss: number
  difference: number
  hasDifference: boolean
  highlight: boolean
}

export interface LossContractTotals {
  estimatedTotalRevenue: number
  estimatedTotalCost: number
  contractEstimatedLoss: number
  recognizedLossInPl: number
  currentPeriodLoss: number
  bookRecognizedLoss: number
  difference: number
}

export const F2_58_OBJECTIVE =
  '识别亏损合同并复核预计损失计提的完整性与准确性，将预计总成本与预计总收入比较并测算本期应确认预计负债。'

export const F2_58_TIPS = [
  '亏损判定：预计总成本 > 预计总收入；合同预计损失 = 预计总成本 − 预计总收入。',
  '完工进度可按已确认收入÷预计总收入计算，或直接录入进度（0~100%）。',
  '已在损益反映的亏损 = 合同预计损失 × 完工进度；本期应确认 = 合同预计损失 − 已在损益反映。',
  '差异 = 本期应确认 − 企业账面已确认；差异行须在审计说明中解释并考虑调整。',
  '与 F2-55/F2-57 项目编码、总收入/总成本数据应勾稽一致。',
]

export function newLossContractId(): string {
  return `f2loss-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

export function emptyLossContractProject(): LossContractProject {
  return {
    id: newLossContractId(),
    projectCode: '',
    projectName: '',
    completionRate: 0,
    recognizedRevenue: 0,
    estimatedTotalRevenue: 0,
    estimatedTotalCost: 0,
    priorRecognizedLoss: 0,
    bookRecognizedLoss: 0,
    remark: '',
  }
}

export function defaultLossContractSheet(): LossContractSheet {
  return {
    projects: Array.from({ length: 8 }, () => emptyLossContractProject()),
  }
}

export function resolveCompletionRate(row: LossContractProject): number {
  if (row.estimatedTotalRevenue > 0 && row.recognizedRevenue > 0) {
    return Math.min(1, Math.max(0, row.recognizedRevenue / row.estimatedTotalRevenue))
  }
  return Math.min(1, Math.max(0, row.completionRate))
}

export function calcContractEstimatedLoss(
  estimatedTotalRevenue: number,
  estimatedTotalCost: number,
): number {
  return isLossContract(estimatedTotalRevenue, estimatedTotalCost)
    ? Math.max(0, estimatedTotalCost - estimatedTotalRevenue)
    : 0
}

export function calcRecognizedLossInPl(
  contractEstimatedLoss: number,
  completionRate: number,
  priorRecognizedLoss: number,
): number {
  if (priorRecognizedLoss > 0) return priorRecognizedLoss
  return contractEstimatedLoss * completionRate
}

export function enrichLossContractProject(row: LossContractProject): EnrichedLossContract {
  const effectiveCompletionRate = resolveCompletionRate(row)
  const loss = isLossContract(row.estimatedTotalRevenue, row.estimatedTotalCost)
  const contractEstimatedLoss = calcContractEstimatedLoss(
    row.estimatedTotalRevenue,
    row.estimatedTotalCost,
  )
  const recognizedLossInPl = calcRecognizedLossInPl(
    contractEstimatedLoss,
    effectiveCompletionRate,
    row.priorRecognizedLoss,
  )
  const currentPeriodLoss = loss
    ? Math.max(0, contractEstimatedLoss - recognizedLossInPl)
    : 0
  const difference = currentPeriodLoss - row.bookRecognizedLoss
  const hasDifference = Math.abs(difference) > 0.01
  return {
    ...row,
    effectiveCompletionRate,
    isLoss: loss ? '是' : '否',
    contractEstimatedLoss,
    recognizedLossInPl,
    currentPeriodLoss,
    difference,
    hasDifference,
    highlight: loss || hasDifference,
  }
}

export function enrichLossContractProjects(
  rows: LossContractProject[],
): EnrichedLossContract[] {
  return rows.map(enrichLossContractProject)
}

export function calcLossContractTotals(rows: EnrichedLossContract[]): LossContractTotals {
  return {
    estimatedTotalRevenue: calcSubtotal(rows.map((r) => r.estimatedTotalRevenue)),
    estimatedTotalCost: calcSubtotal(rows.map((r) => r.estimatedTotalCost)),
    contractEstimatedLoss: calcSubtotal(rows.map((r) => r.contractEstimatedLoss)),
    recognizedLossInPl: calcSubtotal(rows.map((r) => r.recognizedLossInPl)),
    currentPeriodLoss: calcSubtotal(rows.map((r) => r.currentPeriodLoss)),
    bookRecognizedLoss: calcSubtotal(rows.map((r) => r.bookRecognizedLoss)),
    difference: calcSubtotal(rows.map((r) => r.difference)),
  }
}

/** @deprecated 兼容旧引用 */
export type LossContractRow = LossContractProject & {
  managementProvision?: number
  expectedLoss?: number
  currentProvision?: number
}

export function migrateLossContractSheet(legacy: unknown): LossContractSheet | null {
  const sheet = defaultLossContractSheet()
  if (!legacy) return sheet

  if (typeof legacy === 'object' && legacy !== null && 'projects' in legacy) {
    const s = legacy as LossContractSheet
    return {
      projects: s.projects?.length ? s.projects : sheet.projects,
    }
  }

  if (Array.isArray(legacy) && legacy.length) {
    const first = legacy[0] as Record<string, unknown>
    if ('estimatedTotalRevenue' in first || 'estimatedTotalCost' in first) {
      sheet.projects = (legacy as Array<Record<string, unknown>>).map((r) => ({
        ...emptyLossContractProject(),
        id: String(r.id || newLossContractId()),
        projectCode: String(r.projectCode || ''),
        projectName: String(r.projectName || ''),
        completionRate: Number(r.completionRate ?? r.rateNum ?? 0),
        recognizedRevenue: Number(r.recognizedRevenue ?? 0),
        estimatedTotalRevenue: Number(r.estimatedTotalRevenue ?? 0),
        estimatedTotalCost: Number(r.estimatedTotalCost ?? 0),
        priorRecognizedLoss: Number(r.priorRecognizedLoss ?? r.recognizedLossInPl ?? 0),
        bookRecognizedLoss: Number(
          r.bookRecognizedLoss ?? r.managementProvision ?? 0,
        ),
        remark: String(r.remark || ''),
      }))
      return sheet
    }
  }

  return sheet
}
