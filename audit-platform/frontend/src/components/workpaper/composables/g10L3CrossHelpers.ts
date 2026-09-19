/**
 * G10-6 L3 调节 ↔ G10-5 / G10-3 跨表
 */
import { matchG10LiabilityKey, inferG10AdjudicationRowKey } from './g10AccountMatch'
import { G10_ACCOUNT_CODE } from './g10Constants'
import { G10_CROSS_TOLERANCE } from './g10DisclosureFromAdj'
import { G10_L3_KEY, isG10Level3 } from './g10DisclosureCross'
import { commitG10AdjustmentWritebackFromRows } from './g10CrossHelpers'
import { G10_ADJ_KEY, G10_FV_DIFF_THRESHOLD, G10_FV_KEY } from './g10FvCrossHelpers'
import { aggregateG10AdjustmentAjeRjeByRow } from './g10AdjStorage'
import { parseNum } from './useG10FormulaEngine'
import type { G10L3Row } from './useG10L3Reconciliation'
import type { ChecklistResponse } from './useF1FormData'

export interface G10L3AssetMismatch {
  liabilityName: string
  fv5Audited: number
  g96Reported: number
  diff: number
}

export interface G10L3PushItem {
  liabilityName: string
  variance: number
  closingBalance: number
  reportedClosing: number
}

function parseJsonArray(raw: string | null | undefined): Record<string, unknown>[] {
  if (!raw) return []
  try {
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? arr : []
  } catch {
    return []
  }
}

/** 识别 G10-6 推送至 G10-3 的调整行 */
export function isFromG106(row: {
  summary?: string
  remark?: string
  indexRef?: string
}): boolean {
  const indexRef = String(row.indexRef || '')
  if (indexRef === 'G10-6' || indexRef.includes('G10-6')) return true
  if (/^G10-6\s*L3调节差异/.test(String(row.summary || ''))) return true
  if (/来自 G10-6/.test(String(row.remark || ''))) return true
  return false
}

/** 按负债名比对 G10-5 Level3 审定 FV 与 G10-6 企业报告期末 */
export function listG10Fv5VsG96AssetMismatches(
  responses: Map<string, ChecklistResponse>,
): G10L3AssetMismatch[] {
  const fvMap = new Map<string, { name: string; audited: number }>()
  for (const r of parseJsonArray(responses.get(G10_FV_KEY)?.remark)) {
    if (!isG10Level3(r.fairValueLevel)) continue
    const name = String(r.liabilityName ?? '').trim()
    if (!name) continue
    fvMap.set(matchG10LiabilityKey(name), { name, audited: parseNum(r.closingAuditedFV) })
  }

  const out: G10L3AssetMismatch[] = []
  const seen = new Set<string>()
  for (const r of parseJsonArray(responses.get(G10_L3_KEY)?.remark)) {
    const name = String(r.liabilityName ?? '').trim()
    if (!name) continue
    const key = matchG10LiabilityKey(name)
    seen.add(key)
    const fv = fvMap.get(key)
    if (!fv) continue
    const reported = parseNum(r.reportedClosing)
    const diff = fv.audited - reported
    if (Math.abs(diff) > G10_CROSS_TOLERANCE) {
      out.push({
        liabilityName: name,
        fv5Audited: fv.audited,
        g96Reported: reported,
        diff,
      })
    }
  }

  for (const [key, fv] of fvMap) {
    if (seen.has(key)) continue
    if (Math.abs(fv.audited) <= G10_CROSS_TOLERANCE) continue
    out.push({
      liabilityName: fv.name,
      fv5Audited: fv.audited,
      g96Reported: 0,
      diff: fv.audited,
    })
  }
  return out
}

/** 选取企业期末与公式期末存在差异的 L3 行 */
export function selectG10L3VarianceTargets(rows: G10L3Row[]): G10L3PushItem[] {
  return rows
    .filter((r) => r.liabilityName.trim() && Math.abs(r.variance) >= G10_FV_DIFF_THRESHOLD)
    .map((r) => ({
      liabilityName: r.liabilityName,
      variance: r.variance,
      closingBalance: r.closingBalance,
      reportedClosing: r.reportedClosing,
    }))
}

/**
 * 推送 G10-6 L3 调节差异至 G10-3（负债 FV 上升 Dr6101/Cr2101），并回写 G10-1。
 * variance = 企业期末 − 公式期末；正数表示企业列报负债高于调节表计算值。
 */
export function pushG10L3VarianceToAdjustment(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  items: G10L3PushItem[],
): number {
  if (!items.length) return 0

  let existing: Record<string, unknown>[] = []
  const raw = responses.get(G10_ADJ_KEY)?.remark
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) existing = parsed
    } catch { /* ignore */ }
  }

  const existingSummaries = new Set(
    existing.map((r) => String(r.summary ?? '').trim()).filter(Boolean),
  )

  const added: Record<string, unknown>[] = []
  let seqBase = existing.length

  items.forEach((it, i) => {
    const amt = Math.abs(parseNum(it.variance))
    if (amt < G10_FV_DIFF_THRESHOLD) return

    const summary = `G10-6 L3调节差异：${it.liabilityName || '未命名'}`
    if (existingSummaries.has(summary)) return

    const isIncrease = parseNum(it.variance) > 0
    const rowKey = inferG10AdjudicationRowKey({
      liabilityName: it.liabilityName,
      summary,
    })
    const base = {
      date: new Date().toISOString().slice(0, 10),
      entryType: 'AJE',
      preparedBy: '',
      indexRef: 'G10-6',
      liabilityType: '',
      adjudicationRowKey: rowKey,
      remark: [
        '来自 G10-6',
        `公式期末 ${it.closingBalance}`,
        `企业期末 ${it.reportedClosing}`,
        `差异 ${it.variance}`,
      ].join('；'),
    }

    added.push({
      ...base,
      rowId: `g10l3-adj-${Date.now().toString(36)}-${i}a`,
      seq: seqBase + added.length + 1,
      summary,
      accountCode: '6101',
      accountName: '公允价值变动损益',
      debitAmount: isIncrease ? amt : 0,
      creditAmount: isIncrease ? 0 : amt,
    })
    added.push({
      ...base,
      rowId: `g10l3-adj-${Date.now().toString(36)}-${i}b`,
      seq: seqBase + added.length + 1,
      summary: `${summary}（公允变动）`,
      accountCode: G10_ACCOUNT_CODE,
      accountName: '交易性金融负债',
      debitAmount: isIncrease ? 0 : amt,
      creditAmount: isIncrease ? amt : 0,
    })
  })

  if (!added.length) return 0

  const merged = [...existing, ...added]
  debouncedSave(G10_ADJ_KEY, { remark: JSON.stringify(merged) })

  const pushedCount = items.filter((it) => {
    const summary = `G10-6 L3调节差异：${it.liabilityName || '未命名'}`
    return Math.abs(parseNum(it.variance)) >= G10_FV_DIFF_THRESHOLD && !existingSummaries.has(summary)
  }).length

  commitG10AdjustmentWritebackFromRows(
    responses,
    debouncedSave,
    merged as Parameters<typeof aggregateG10AdjustmentAjeRjeByRow>[0],
    { source: 'G10-6', offerDisclosurePull: pushedCount > 0 },
  )

  return pushedCount
}

export function buildG10L3ProcedureSummary(input: {
  rowCount: number
  varianceRows: number
  fvCrossVariance: number
  assetMismatchCount: number
}): string {
  return [
    `G10-6 L3调节：${input.rowCount} 行`,
    input.varianceRows ? `调节差异 ${input.varianceRows} 行` : '调节一致',
    Math.abs(input.fvCrossVariance) > G10_FV_DIFF_THRESHOLD
      ? `与 G10-5 L3 差 ${input.fvCrossVariance.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`
      : '',
    input.assetMismatchCount ? `逐笔勾稽差异 ${input.assetMismatchCount} 项` : '',
  ].filter(Boolean).join('；')
}
