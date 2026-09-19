/**
 * G9-4 公允价值测试跨表联动（纯函数）
 * G9-2 明细 ↔ G9-4 公允测试 ↔ G9-3 调整 / G9A 程序
 */
import { parseNum } from './useG9FormulaEngine'
import { G9_ACCOUNT_CODE } from './g9Constants'
import {
  aggregateG9AdjustmentAjeRje,
  applyG9AdjustmentWriteback,
  parseG9AdjStore,
} from './g9AdjStorage'
import { G9_DETAIL_KEY, G9_FV_KEY, matchG9AssetKey } from './g9VoucherCross'
import type { ChecklistResponse } from './useF1FormData'

export { matchG9AssetKey, G9_DETAIL_KEY, G9_FV_KEY }

export const G9_ADJ_KEY = 'G9-adjustment-rows'
export const G9_ADJ_ROWS_KEY = 'G9-adj-rows'
export const G9_AJE_ADJ_OVERLAY_ID = 'G9-aje-adj-overlay'

/** G9A seq8：公允价值计量 / L3 调节 */
export const G9A_FV_PROGRAM_NOS = [8] as const
export const G9A_FV_MARK_KEY = 'G9A-fv-complete'
/** G9A 凭证检查回填标记 */
export const G9A_VOUCHER_MARK_KEY = 'G9A-voucher-complete'
export const G9A_PROCEDURE_SHEET = '其他非流动金融资产实质性程序表G9A'

export const G9_FV_DIFF_THRESHOLD = 0.01

export interface G9FvPushDetailSource {
  assetName: string
  fairValueLevel: string
  valuationMethod: string
  closingAuditedQty: number
  closingAuditedPrice: number
  closingAuditedFV: number
}

export interface G9PushAdjItem {
  summary: string
  amount: number
  indexRef?: string
  remark?: string
}

/** 差异相对未审合计的预警；hardAbs 通常取 B15 */
export function calcG9FvDiffWarning(
  absDiff: number,
  unadjTotal: number,
  opts?: { softRatio?: number; hardRatio?: number; hardAbs?: number },
): 'none' | 'soft' | 'hard' {
  const softRatio = opts?.softRatio ?? 0.05
  const hardRatio = opts?.hardRatio ?? 0.2
  const hardAbs = opts?.hardAbs ?? 0
  if (Math.abs(absDiff) <= G9_FV_DIFF_THRESHOLD) return 'none'
  const base = Math.abs(unadjTotal)
  const ratio = base > G9_FV_DIFF_THRESHOLD ? Math.abs(absDiff) / base : 1
  if (ratio >= hardRatio || (hardAbs > 0 && Math.abs(absDiff) >= hardAbs)) return 'hard'
  if (ratio >= softRatio) return 'soft'
  return 'none'
}

export async function fetchG9PerformanceMateriality(projectId: string): Promise<number> {
  if (!projectId) return 0
  try {
    const { fetchPerformanceMateriality } = await import('./g6CrossHelpers')
    const pm = await fetchPerformanceMateriality(projectId)
    return pm && pm > 0 ? pm : 0
  } catch {
    return 0
  }
}

export interface G9FvDiffSelectInput {
  rows: Array<{
    assetName: string
    fairValueDiff: number
    closingAuditedFV: number
    closingUnadjustedFV: number
    diffReason?: string
  }>
  performanceMateriality: number
  onlyMaterial?: boolean
}

export function selectG9FvDiffTargets(input: G9FvDiffSelectInput): {
  targets: G9FvDiffSelectInput['rows']
  skipped: Array<{ assetName: string; diff: number; reason: string }>
  threshold: number
} {
  const onlyMaterial = input.onlyMaterial !== false
  const pm = parseNum(input.performanceMateriality)
  const threshold = onlyMaterial ? (pm > 0 ? pm : G9_FV_DIFF_THRESHOLD) : G9_FV_DIFF_THRESHOLD
  const targets: G9FvDiffSelectInput['rows'] = []
  const skipped: Array<{ assetName: string; diff: number; reason: string }> = []
  for (const r of input.rows) {
    const diff = parseNum(r.fairValueDiff)
    if (Math.abs(diff) <= G9_FV_DIFF_THRESHOLD) continue
    if (Math.abs(diff) > threshold) {
      targets.push(r)
    } else {
      skipped.push({
        assetName: r.assetName || '未命名',
        diff,
        reason: pm > 0
          ? `|差异| ${Math.abs(diff).toFixed(2)} ≤ B15 ${pm.toFixed(2)}`
          : '低于阈值',
      })
    }
  }
  return { targets, skipped, threshold }
}

/** 回写 G9-2：层次 / 估值方法 / 持有数量 */
export function pushG9FvToDetail(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  fvRows: G9FvPushDetailSource[],
): number {
  const raw = responses.get(G9_DETAIL_KEY)?.remark
  if (!raw) return 0
  let details: Record<string, unknown>[]
  try {
    details = JSON.parse(raw)
    if (!Array.isArray(details)) return 0
  } catch {
    return 0
  }

  const byKey = new Map(
    fvRows
      .filter((r) => r.assetName?.trim())
      .map((r) => [matchG9AssetKey(r.assetName), r]),
  )
  let n = 0
  const next = details.map((d) => {
    const hit = byKey.get(matchG9AssetKey(String(d.assetName ?? '')))
    if (!hit) return d
    n += 1
    return {
      ...d,
      fairValueLevel: hit.fairValueLevel || d.fairValueLevel,
      valuationMethod: hit.valuationMethod || d.valuationMethod,
      holdingQuantity: hit.closingAuditedQty || d.holdingQuantity,
    }
  })
  if (n) {
    debouncedSave(G9_DETAIL_KEY, { remark: JSON.stringify(next) })
    try {
      window.dispatchEvent(new CustomEvent('g9:fair-value-updated', {
        detail: { source: 'G9-4→G9-2', timestamp: Date.now() },
      }))
    } catch { /* silent */ }
  }
  return n
}

/**
 * 推送公允差异至 G9-3（FVTPL 口径：Dr/Cr 1504 ↔ 6101 公允价值变动损益），并回写 G9-1。
 */
export function pushG9FvDiffToAdjustment(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  items: G9PushAdjItem[],
  source = 'G9-4',
): number {
  if (!items.length) return 0

  let existing: Record<string, unknown>[] = []
  const raw = responses.get(G9_ADJ_KEY)?.remark
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) existing = parsed
    } catch { /* ignore */ }
  }

  const seqBase = existing.length
  const added: Record<string, unknown>[] = []
  items.forEach((it, i) => {
    const amt = Math.abs(parseNum(it.amount))
    if (amt < G9_FV_DIFF_THRESHOLD) return
    const isIncrease = parseNum(it.amount) > 0
    const base = {
      date: new Date().toISOString().slice(0, 10),
      entryType: 'AJE',
      preparedBy: '',
      remark: it.remark || `来源 ${source}`,
    }
    added.push({
      ...base,
      rowId: `g9fv-adj-${Date.now().toString(36)}-${i}a`,
      seq: seqBase + added.length + 1,
      summary: it.summary,
      accountCode: G9_ACCOUNT_CODE,
      accountName: '其他非流动金融资产',
      debitAmount: isIncrease ? amt : 0,
      creditAmount: isIncrease ? 0 : amt,
    })
    added.push({
      ...base,
      rowId: `g9fv-adj-${Date.now().toString(36)}-${i}b`,
      seq: seqBase + added.length + 1,
      summary: `${it.summary}（公允变动）`,
      accountCode: '6101',
      accountName: '公允价值变动损益',
      debitAmount: isIncrease ? 0 : amt,
      creditAmount: isIncrease ? amt : 0,
    })
  })

  if (!added.length) return 0

  const merged = [...existing, ...added]
  debouncedSave(G9_ADJ_KEY, { remark: JSON.stringify(merged) })

  const wb = aggregateG9AdjustmentAjeRje(merged)
  debouncedSave(G9_AJE_ADJ_OVERLAY_ID, { remark: JSON.stringify(wb) })

  const store = parseG9AdjStore(responses.get(G9_ADJ_ROWS_KEY)?.remark)
  const patched = applyG9AdjustmentWriteback(store, wb)
  debouncedSave(G9_ADJ_ROWS_KEY, { remark: JSON.stringify(patched) })

  try {
    window.dispatchEvent(new CustomEvent('g9:adjustment-writeback', { detail: wb }))
  } catch { /* silent */ }

  return items.filter((it) => Math.abs(parseNum(it.amount)) >= G9_FV_DIFF_THRESHOLD).length
}

export function buildG9FvProcedureSummary(input: {
  rowCount: number
  diffCount: number
  level3Count: number
  auditedTotal: number
  validationErrors: number
}): string {
  return [
    `G9-4 公允价值测试已编制：${input.rowCount} 项`,
    `差异 ${input.diffCount} 项`,
    `Level3 ${input.level3Count} 项`,
    `审定合计 ${input.auditedTotal.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`,
    input.validationErrors ? `校验未通过 ${input.validationErrors} 项` : '校验通过',
  ].join('；')
}

export async function markG9AProcedureSteps(opts: {
  projectId: string
  year?: number
  programNos: readonly number[]
  status?: string
  linkedWorkpapers?: string
  executionSummary?: string
}): Promise<number> {
  if (!opts.projectId || !opts.programNos.length) return 0
  const { api } = await import('@/services/apiProxy')
  const year = opts.year || new Date().getFullYear()
  const scope = `procedure_table:${G9A_PROCEDURE_SHEET}`
  const status = opts.status || 'completed'
  let n = 0
  for (const programNo of opts.programNos) {
    const fields: Array<{ field: string; value: unknown }> = [
      { field: 'status', value: status },
    ]
    if (opts.linkedWorkpapers) fields.push({ field: 'linked_workpapers', value: opts.linkedWorkpapers })
    if (opts.executionSummary) fields.push({ field: 'execution_summary', value: opts.executionSummary })
    for (const f of fields) {
      try {
        await api.post('/api/workpapers/field-overrides', {
          project_id: opts.projectId,
          year,
          scope,
          item_key: String(programNo),
          field: f.field,
          value: f.value,
        }, { _silent: true } as any)
        if (f.field === 'status') n += 1
      } catch { /* silent */ }
    }
  }
  try {
    window.dispatchEvent(new CustomEvent('g9:procedure-marked', {
      detail: { programNos: [...opts.programNos], status, timestamp: Date.now() },
    }))
  } catch { /* silent */ }
  return n
}
