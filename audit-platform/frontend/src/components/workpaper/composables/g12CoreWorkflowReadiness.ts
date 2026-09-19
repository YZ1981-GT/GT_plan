/**
 * G12 主闭环就绪评估 — 纯函数，供 checklist / 流程条 / 目录进度共用
 */
import { G12_AUDIT_NOTE_REASON_THRESHOLD, G12_CORE_WORKFLOW_STEPS } from './g12Constants'
import { summarizeG12Adjustment, isG12AdjustmentBalanced } from './g12AdjStorage'
import { summarizeG12NetHedgeDetailRows } from './g12NetHedgeDetailCalc'
import { parseNum, calcAdjustedAmount, calcChangeRate, isChangeRateExceeding } from './useG12FormulaEngine'
import { G12_AJE_ADJ_OVERLAY_ID } from './useG12Adjustment'
import { calcG12DisclosureReconciliationDiff, migrateG12DisclosureRows } from './g12DisclosureSync'

const TOLERANCE = 0.01

export interface G12WorkflowCheckItem {
  key: string
  stepIndex: number
  label: string
  ok: boolean
  hint?: string
}

export interface G12WorkflowReadiness {
  items: G12WorkflowCheckItem[]
  completedStepIndices: number[]
  doneCount: number
  allOk: boolean
  pct: number
}

function parseJsonArray(raw?: string | null): unknown[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function parseOverlayNet(allResponses: Map<string, { remark?: string | null }>): number | null {
  const raw = allResponses.get(G12_AJE_ADJ_OVERLAY_ID)?.remark
  if (!raw) return null
  try {
    const o = JSON.parse(raw) as { net_hedge?: number }
    return parseNum(o.net_hedge)
  } catch {
    return null
  }
}

function hedgeDetailTotals(allResponses: Map<string, { remark?: string | null }>) {
  const rows = parseJsonArray(allResponses.get('G12-hedge-detail-rows')?.remark) as Array<{
    rowKind?: string
    instrumentFvCumulative?: number
    salesPortion?: number
    purchasePortion?: number
    hedgeAdjAmortization?: number
  }>
  if (!rows.length) return null
  return summarizeG12NetHedgeDetailRows(rows.map((r) => ({
    rowKind: (r.rowKind === 'amortization' ? 'amortization' : 'fv_allocation') as 'fv_allocation' | 'amortization',
    instrumentFvCumulative: parseNum(r.instrumentFvCumulative),
    salesPortion: parseNum(r.salesPortion),
    purchasePortion: parseNum(r.purchasePortion),
    hedgeAdjAmortization: parseNum(r.hedgeAdjAmortization),
  })))
}

function adjustmentSummary(allResponses: Map<string, { remark?: string | null }>) {
  const rows = parseJsonArray(allResponses.get('G12-aje-rows')?.remark)
  if (!rows.length) return null
  return summarizeG12Adjustment(rows as Parameters<typeof summarizeG12Adjustment>[0])
}

function isAdjSyncedToG12_1(allResponses: Map<string, { remark?: string | null }>): boolean {
  const summary = adjustmentSummary(allResponses)
  const currentNet = summary?.net6103 ?? 0
  const overlayNet = parseOverlayNet(allResponses)
  const hasRows = (summary?.rowCount ?? 0) > 0
  if (!hasRows && Math.abs(currentNet) <= TOLERANCE) {
    return overlayNet == null || Math.abs(overlayNet) <= TOLERANCE
  }
  if (!isG12AdjustmentBalanced(parseJsonArray(allResponses.get('G12-aje-rows')?.remark) as Parameters<typeof isG12AdjustmentBalanced>[0])) {
    return false
  }
  if (overlayNet == null) return Math.abs(currentNet) <= TOLERANCE
  return Math.abs(currentNet - overlayNet) <= TOLERANCE
}

function estimateCurrentAudited(allResponses: Map<string, { remark?: string | null }>): number {
  const hedge = hedgeDetailTotals(allResponses)
  const overlayNet = parseOverlayNet(allResponses) ?? 0
  const unadjusted = hedge?.netHedgePnl ?? 0
  return unadjusted + overlayNet
}

function disclosureTotal(allResponses: Map<string, { remark?: string | null }>, variant: 'listed' | 'soe'): number {
  const itemId = variant === 'listed' ? 'G12-disclosure-listed' : 'G12-disclosure-soe'
  const raw = allResponses.get(itemId)?.remark
  if (!raw) return 0
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return 0
    const rows = migrateG12DisclosureRows(parsed, variant)
    return rows.reduce((s, r) => s + parseNum(r.currentAmount), 0)
  } catch {
    return 0
  }
}

function adjudicatedAmount(allResponses: Map<string, { remark?: string | null; conclusion?: string | null }>): number | null {
  const raw = allResponses.get('G12-1-adjudicated-amount')?.conclusion
  if (raw == null || raw === '') return null
  return parseNum(raw)
}

function auditNoteReady(allResponses: Map<string, { conclusion?: string | null }>): boolean {
  const priorRaw = allResponses.get('G12-adj-prior')?.remark
  let priorAudited = 0
  let currentAudited = 0
  try {
    if (priorRaw) {
      const store = JSON.parse(priorRaw) as Record<string, { priorUnadjusted?: number; priorAdjustment?: number }>
      const net = store.net_hedge
      if (net) priorAudited = calcAdjustedAmount(parseNum(net.priorUnadjusted), parseNum(net.priorAdjustment))
    }
  } catch { /* ignore */ }
  currentAudited = estimateCurrentAudited(allResponses)
  const changeRate = calcChangeRate(priorAudited, currentAudited)
  const mainReasonRequired = isChangeRateExceeding(changeRate, G12_AUDIT_NOTE_REASON_THRESHOLD)
  const mainReason = (allResponses.get('G12-adj-main-reason')?.conclusion ?? '').trim()
  const auditNote = (allResponses.get('G12-adj-note')?.conclusion ?? '').trim()
  if (mainReasonRequired) return mainReason.length > 0
  return auditNote.length > 0 || mainReason.length > 0
}

/** 评估主闭环 9 步就绪状态 */
export function evaluateG12CoreWorkflowReadiness(
  allResponses: Map<string, { remark?: string | null; conclusion?: string | null }>,
): G12WorkflowReadiness {
  const hedge = hedgeDetailTotals(allResponses)
  const adjSummary = adjustmentSummary(allResponses)
  const tbAmount = allResponses.has('G12-adj-tb')
    ? parseNum(allResponses.get('G12-adj-tb')?.remark)
    : null
  const currentAudited = estimateCurrentAudited(allResponses)
  const published = adjudicatedAmount(allResponses)
  const listedTotal = disclosureTotal(allResponses, 'listed')
  const soeTotal = disclosureTotal(allResponses, 'soe')
  const disclosureTotalAmt = Math.max(listedTotal, soeTotal)
  const adjAmt = published ?? currentAudited
  const reconDiff = calcG12DisclosureReconciliationDiff(disclosureTotalAmt, published ?? (allResponses.has('G12-1-adjudicated-amount') ? adjAmt : null))
  const noteListed = (allResponses.get('G12-disclosure-listed-note')?.remark ?? '').trim()
  const noteSoe = (allResponses.get('G12-disclosure-soe-note')?.remark ?? '').trim()

  const stepOk: boolean[] = [
    // 0 G12-2 明细
    Boolean(hedge && hedge.netHedgePnl !== undefined && parseJsonArray(allResponses.get('G12-hedge-detail-rows')?.remark).length > 0
      && hedge.fvCheckFailCount === 0),
    // 1 G12-3 调整
    isAdjSyncedToG12_1(allResponses),
    // 2 从 TB 取数
    allResponses.has('G12-adj-tb'),
    // 3 核对差异
    tbAmount != null && Math.abs(currentAudited - tbAmount) <= TOLERANCE,
    // 4 填审计说明
    auditNoteReady(allResponses),
    // 5 发布审定数
    published != null,
    // 6 附注从 G12-1 同步
    disclosureTotalAmt !== 0 && (published == null || Math.abs(disclosureTotalAmt - published) <= TOLERANCE),
    // 7 勾稽绿条
    reconDiff != null && Math.abs(reconDiff) <= TOLERANCE,
    // 8 编写附注说明
    noteListed.length > 0 || noteSoe.length > 0,
  ]

  const hints: string[] = [
    hedge?.fvCheckFailCount ? `FV 拆分校验失败 ${hedge.fvCheckFailCount} 处` : '请先录入 G12-2 明细',
    !adjSummary?.rowCount
      ? '无调整分录视为已同步；有分录须点「同步至 G12-1」'
      : !isG12AdjustmentBalanced(parseJsonArray(allResponses.get('G12-aje-rows')?.remark) as Parameters<typeof isG12AdjustmentBalanced>[0])
        ? '调整分录借贷不平衡'
        : '调整数未同步至 G12-1，请点击「同步至审定表」',
    '在 G12-1 点击「从 TB 取数」',
    tbAmount == null ? '尚未取 TB 数' : `差异 ${(currentAudited - tbAmount).toFixed(2)}`,
    '填写审计说明（变动率超 30% 须填主要原因）',
    '在 G12-1 点击「发布审定数」',
    '在附注页点击「从 G12-1 同步」',
    reconDiff == null ? '须先发布审定数并同步附注' : `勾稽差异 ${reconDiff.toFixed(2)}`,
    '填写附注说明文本',
  ]

  const items: G12WorkflowCheckItem[] = G12_CORE_WORKFLOW_STEPS.map((label, stepIndex) => ({
    key: `step-${stepIndex}`,
    stepIndex,
    label,
    ok: stepOk[stepIndex] ?? false,
    hint: stepOk[stepIndex] ? undefined : hints[stepIndex],
  }))

  const completedStepIndices = stepOk.map((ok, i) => (ok ? i : -1)).filter((i) => i >= 0)
  const doneCount = completedStepIndices.length

  return {
    items,
    completedStepIndices,
    doneCount,
    allOk: doneCount === G12_CORE_WORKFLOW_STEPS.length,
    pct: Math.round((doneCount / G12_CORE_WORKFLOW_STEPS.length) * 100),
  }
}

/** 页面默认高亮步骤；G12-1 / 附注页按首个未完成步动态覆盖 */
export function resolveG12WorkflowActiveIndex(
  pageCode: string,
  readiness: G12WorkflowReadiness,
): number {
  const firstIncomplete = (from: number, to: number) => {
    for (let i = from; i <= to; i += 1) {
      if (!readiness.completedStepIndices.includes(i)) return i
    }
    return to
  }

  switch (pageCode) {
    case 'G12-2':
      return 0
    case 'G12-3':
      return 1
    case 'G12-1':
      return firstIncomplete(2, 5)
    case '附注上市':
    case '附注国企':
      return firstIncomplete(6, 8)
    default:
      return readiness.allOk ? G12_CORE_WORKFLOW_STEPS.length - 1 : firstIncomplete(0, G12_CORE_WORKFLOW_STEPS.length - 1)
  }
}

/** G12-3 是否需同步至 G12-1（供调整页强提醒） */
export function g12AdjustmentNeedsSync(allResponses: Map<string, { remark?: string | null }>): boolean {
  const rows = parseJsonArray(allResponses.get('G12-aje-rows')?.remark)
  if (!rows.length) return false
  if (!isG12AdjustmentBalanced(rows as Parameters<typeof isG12AdjustmentBalanced>[0])) return false
  return !isAdjSyncedToG12_1(allResponses)
}

export function g12AdjustmentPendingNet(allResponses: Map<string, { remark?: string | null }>): number {
  return adjustmentSummary(allResponses)?.net6103 ?? 0
}
