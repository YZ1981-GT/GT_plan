/**
 * F2-57 合同履约成本减值准备测算表（对齐致同源模板）
 *
 * 账面价值 E = C − D；转让对价净额 H = F − G
 * 测算计提/转回 J = max(0, C − H) − D；差异 L = J − K
 */
import { calcSubtotal } from './useF2SpecialFormulaEngine'

export type YesNo = '是' | '否' | ''

export interface ContractCostImpairmentProject {
  id: string
  projectCode: string
  projectName: string
  bookBalance: number
  accumulatedProvision: number
  remainingConsideration: number
  estimatedFutureCosts: number
  companyRecordedProvision: number
  remark: string
}

export interface ContractCostImpairmentSheet {
  projects: ContractCostImpairmentProject[]
}

export interface EnrichedContractCostImpairment extends ContractCostImpairmentProject {
  bookValue: number
  netRealizableValue: number
  isImpaired: YesNo
  requiredProvision: number
  measuredProvision: number
  difference: number
  hasDifference: boolean
  highlight: boolean
}

export interface ContractCostImpairmentTotals {
  bookBalance: number
  accumulatedProvision: number
  bookValue: number
  remainingConsideration: number
  estimatedFutureCosts: number
  netRealizableValue: number
  measuredProvision: number
  companyRecordedProvision: number
  difference: number
}

export const F2_57_OBJECTIVE =
  '复核合同履约成本减值准备计提的充分性与准确性，将账面价值与预期转让相关商品可取得的剩余对价净额进行比较。'

export const F2_57_TIPS = [
  '合同履约成本减值测试：比较账面价值与「预期剩余对价 − 估计将发生成本」之净额。',
  '账面价值 = 账面余额 − 已计提减值准备；转让对价净额 = 剩余对价 − 估计将发生成本。',
  '是否发生减值：账面价值 > 转让对价净额；测算计提/转回 = max(0, 账面余额 − 净额) − 已计提准备。',
  '差异金额 = 测算金额 − 企业账面记录；差异行须在审计说明中解释并考虑调整。',
  '减值合计应与科目 1410 及相关减值损失勾稽一致。',
]

export function newContractCostImpairmentId(): string {
  return `f2imp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

export function emptyImpairmentProject(): ContractCostImpairmentProject {
  return {
    id: newContractCostImpairmentId(),
    projectCode: '',
    projectName: '',
    bookBalance: 0,
    accumulatedProvision: 0,
    remainingConsideration: 0,
    estimatedFutureCosts: 0,
    companyRecordedProvision: 0,
    remark: '',
  }
}

export function defaultContractCostImpairmentSheet(): ContractCostImpairmentSheet {
  return {
    projects: Array.from({ length: 8 }, () => emptyImpairmentProject()),
  }
}

export function calcBookValue(bookBalance: number, accumulatedProvision: number): number {
  return bookBalance - accumulatedProvision
}

export function calcNetRealizableValue(
  remainingConsideration: number,
  estimatedFutureCosts: number,
): number {
  return remainingConsideration - estimatedFutureCosts
}

export function calcRequiredProvision(bookBalance: number, netRealizableValue: number): number {
  return Math.max(0, bookBalance - netRealizableValue)
}

export function calcMeasuredProvision(
  bookBalance: number,
  netRealizableValue: number,
  accumulatedProvision: number,
): number {
  return calcRequiredProvision(bookBalance, netRealizableValue) - accumulatedProvision
}

export function enrichImpairmentProject(
  row: ContractCostImpairmentProject,
): EnrichedContractCostImpairment {
  const bookValue = calcBookValue(row.bookBalance, row.accumulatedProvision)
  const netRealizableValue = calcNetRealizableValue(
    row.remainingConsideration,
    row.estimatedFutureCosts,
  )
  const isImpaired: YesNo = bookValue > netRealizableValue ? '是' : '否'
  const requiredProvision = calcRequiredProvision(row.bookBalance, netRealizableValue)
  const measuredProvision = requiredProvision - row.accumulatedProvision
  const difference = measuredProvision - row.companyRecordedProvision
  const hasDifference = Math.abs(difference) > 0.01
  return {
    ...row,
    bookValue,
    netRealizableValue,
    isImpaired,
    requiredProvision,
    measuredProvision,
    difference,
    hasDifference,
    highlight: isImpaired === '是' || hasDifference,
  }
}

export function enrichImpairmentProjects(
  rows: ContractCostImpairmentProject[],
): EnrichedContractCostImpairment[] {
  return rows.map(enrichImpairmentProject)
}

export function calcImpairmentTotals(
  rows: EnrichedContractCostImpairment[],
): ContractCostImpairmentTotals {
  return {
    bookBalance: calcSubtotal(rows.map((r) => r.bookBalance)),
    accumulatedProvision: calcSubtotal(rows.map((r) => r.accumulatedProvision)),
    bookValue: calcSubtotal(rows.map((r) => r.bookValue)),
    remainingConsideration: calcSubtotal(rows.map((r) => r.remainingConsideration)),
    estimatedFutureCosts: calcSubtotal(rows.map((r) => r.estimatedFutureCosts)),
    netRealizableValue: calcSubtotal(rows.map((r) => r.netRealizableValue)),
    measuredProvision: calcSubtotal(rows.map((r) => r.measuredProvision)),
    companyRecordedProvision: calcSubtotal(rows.map((r) => r.companyRecordedProvision)),
    difference: calcSubtotal(rows.map((r) => r.difference)),
  }
}

export function calcImpairmentAmountTotal(rows: EnrichedContractCostImpairment[]): number {
  return calcSubtotal(rows.map((r) => Math.max(0, r.bookValue - r.netRealizableValue)))
}

/** @deprecated 兼容旧引用 */
export type ImpairmentRow = ContractCostImpairmentProject & {
  estimatedTotalRevenue?: number
  recognizedRevenue?: number
  estimatedTotalCost?: number
  incurredCost?: number
  bookValue?: number
  managementProvision?: number
}

export function migrateContractCostImpairmentSheet(legacy: unknown): ContractCostImpairmentSheet | null {
  const sheet = defaultContractCostImpairmentSheet()
  if (!legacy) return sheet

  if (typeof legacy === 'object' && legacy !== null && 'projects' in legacy) {
    const s = legacy as ContractCostImpairmentSheet
    return {
      projects: s.projects?.length ? s.projects : sheet.projects,
    }
  }

  if (Array.isArray(legacy) && legacy.length) {
    const first = legacy[0] as Record<string, unknown>
    if ('bookBalance' in first || 'remainingConsideration' in first) {
      sheet.projects = (legacy as ContractCostImpairmentProject[]).map((r) => ({
        ...emptyImpairmentProject(),
        ...r,
        id: r.id || newContractCostImpairmentId(),
      }))
      return sheet
    }

    if ('estimatedTotalRevenue' in first || 'bookValue' in first) {
      sheet.projects = (legacy as Array<Record<string, unknown>>).map((r) => {
        const mgmt = Number(r.managementProvision ?? r.mgmtProvision ?? 0)
        const netBook = Number(r.bookValue ?? 0)
        const estRev = Number(r.estimatedTotalRevenue ?? r.totalRevenue ?? 0)
        const recRev = Number(r.recognizedRevenue ?? 0)
        const estCost = Number(r.estimatedTotalCost ?? r.totalCost ?? 0)
        const incCost = Number(r.incurredCost ?? 0)
        return {
          ...emptyImpairmentProject(),
          id: String(r.id || newContractCostImpairmentId()),
          projectCode: String(r.projectCode || ''),
          projectName: String(r.projectName || ''),
          bookBalance: netBook + mgmt,
          accumulatedProvision: mgmt,
          remainingConsideration: estRev - recRev,
          estimatedFutureCosts: estCost - incCost,
          companyRecordedProvision: mgmt,
          remark: String(r.remark || ''),
        }
      })
      return sheet
    }
  }

  return sheet
}
