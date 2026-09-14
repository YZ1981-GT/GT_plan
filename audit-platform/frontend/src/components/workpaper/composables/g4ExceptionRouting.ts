import type { ChecklistResponse } from './useF1FormData'
import {
  createEmptyEntry,
  mergeProvenanceDrafts,
  type AdjustmentEntry,
} from './useG4MainAdjustment'
import {
  G4_ITEM_IDS,
  buildCanonicalPayload,
  parseCanonicalArray,
  resolveCreditLossAccount,
} from './g4StorageContract'

type LooseRow = Record<string, any>
type ResponseMap = Map<string, ChecklistResponse>

export interface G4InterestVarianceOptions {
  id?: string
  description?: string
  allResponses?: ResponseMap | null
}

function numberValue(value: unknown): number {
  const parsed = Number(String(value ?? 0).replace(/,/g, ''))
  return Number.isFinite(parsed) ? parsed : 0
}

function rowId(row: LooseRow, index: number): string {
  return String(row.id ?? row.rowId ?? row.seq ?? index + 1)
}

function fingerprint(value: unknown): string {
  return JSON.stringify(value)
}

function draftBase(
  description: string,
  sourceSheet: string,
  sourceRowId: string,
  sourceKind: string,
  sourceKey: string,
): AdjustmentEntry {
  const entry = createEmptyEntry(1, description)
  return {
    ...entry,
    indexRef: sourceSheet,
    sourceSheet,
    sourceRowId,
    sourceKind,
    sourceKey,
    draftStatus: 'draft',
  }
}

function monetaryPair(
  amount: number,
  debit: { code: string; name: string },
  credit: { code: string; name: string },
  meta: {
    description: string
    sourceSheet: string
    sourceRowId: string
    sourceKind: string
    sourceKey: string
    remark?: string
  },
): AdjustmentEntry[] {
  const absolute = Math.abs(amount)
  if (absolute < 0.01) return []
  const debitEntry = draftBase(
    meta.description,
    meta.sourceSheet,
    meta.sourceRowId,
    meta.sourceKind,
    `${meta.sourceKey}:debit`,
  )
  const creditEntry = draftBase(
    meta.description,
    meta.sourceSheet,
    meta.sourceRowId,
    meta.sourceKind,
    `${meta.sourceKey}:credit`,
  )
  Object.assign(debitEntry, {
    accountCode: debit.code,
    accountName: debit.name,
    debitAmount: absolute,
    creditAmount: 0,
    sourceLine: 'debit',
    remark: meta.remark || '',
    sourceFingerprint: fingerprint({ amount, account: debit.code, line: 'debit', remark: meta.remark }),
  })
  Object.assign(creditEntry, {
    accountCode: credit.code,
    accountName: credit.name,
    debitAmount: 0,
    creditAmount: absolute,
    sourceLine: 'credit',
    remark: meta.remark || '',
    sourceFingerprint: fingerprint({ amount, account: credit.code, line: 'credit', remark: meta.remark }),
  })
  return [debitEntry, creditEntry]
}

function memo(
  description: string,
  sourceSheet: string,
  sourceRowId: string,
  sourceKind: string,
  sourceKey: string,
  remark: string,
): AdjustmentEntry {
  const entry = draftBase(description, sourceSheet, sourceRowId, sourceKind, sourceKey)
  return {
    ...entry,
    category: '其他',
    entryType: 'AJE',
    debitAmount: 0,
    creditAmount: 0,
    sourceLine: 'memo',
    remark,
    sourceFingerprint: fingerprint({ description, remark }),
  }
}

export function buildG410ImpairmentDrafts(
  rows: LooseRow[],
  allResponses?: ResponseMap | null,
): AdjustmentEntry[] {
  const loss = resolveCreditLossAccount(allResponses)
  return (rows || []).flatMap((row, index) => {
    const amount = numberValue(row.impairmentAdjustment)
    if (Math.abs(amount) < 0.01) return []
    const id = rowId(row, index)
    const lossAccount = { code: loss.code, name: loss.name }
    const allowance = { code: '1502', name: '债权投资减值准备' }
    return monetaryPair(
      amount,
      amount > 0 ? lossAccount : allowance,
      amount > 0 ? allowance : lossAccount,
      {
        description: `G4-10 减值测算差异：${row.investProject || id}`,
        sourceSheet: 'G4-10',
        sourceRowId: id,
        sourceKind: 'impairment-adjustment',
        sourceKey: `G4-10:item:${id}:impairment-adjustment`,
        remark: String(row.differenceNote || ''),
      },
    )
  })
}

export function buildG48VarianceMemos(items: LooseRow[]): AdjustmentEntry[] {
  return (items || []).flatMap((item, index) => {
    const hasVariance =
      Math.abs(numberValue(item.variance)) >= 0.01 ||
      Math.abs(numberValue(item.varianceQuantity)) >= 0.01
    const explanation = String(item.remark ?? item.varianceNote ?? item.explanation ?? '').trim()
    const explicitlyUnexplained = item.unexplained === true || item.isExplained === false
    if (!hasVariance || (!explicitlyUnexplained && explanation)) return []
    const id = rowId(item, index)
    return [
      memo(
        `G4-8 未解释盘点倒轧差异：${item.securitiesName || id}`,
        'G4-8',
        id,
        'inventory-difference',
        `G4-8:item:${id}:inventory-difference`,
        '数量或面值差异尚未解释；仅作例外备忘，不据凭证金额认定错报。',
      ),
    ]
  })
}

export function buildG412ExceptionDrafts(
  reversals: LooseRow[],
  writeOffs: LooseRow[],
  allResponses?: ResponseMap | null,
): AdjustmentEntry[] {
  const loss = resolveCreditLossAccount(allResponses)
  const lossAccount = { code: loss.code, name: loss.name }
  const allowance = { code: '1502', name: '债权投资减值准备' }
  const drafts: AdjustmentEntry[] = []

  ;(reversals || []).forEach((row, index) => {
    const id = rowId(row, index)
    const excess = numberValue(row.reversalAmount) - numberValue(row.accumulatedProvision)
    if (excess >= 0.01) {
      drafts.push(...monetaryPair(excess, lossAccount, allowance, {
        description: `G4-12 转回超过累计计提上限：${row.unitName || id}`,
        sourceSheet: 'G4-12',
        sourceRowId: id,
        sourceKind: 'over-limit-reversal',
        sourceKey: `G4-12:reversal:${id}:over-limit`,
        remark: '按超出累计计提部分生成纠正草稿。',
      }))
    }
    if (row.isReasonable === '不合理' || row.isReasonable === false) {
      drafts.push(memo(
        `G4-12 不合理转回候选：${row.unitName || id}`,
        'G4-12',
        id,
        'unreasonable-reversal',
        `G4-12:reversal:${id}:unreasonable`,
        '候选例外：请确认事实、金额及会计方向后再转为调整分录。',
      ))
    }
  })

  ;(writeOffs || []).forEach((row, index) => {
    const id = rowId(row, index)
    if (row.isReasonable === '不合理' || row.isReasonable === false) {
      drafts.push(memo(
        `G4-12 不合理核销候选：${row.unitName || id}`,
        'G4-12',
        id,
        'unreasonable-writeoff',
        `G4-12:writeoff:${id}:unreasonable`,
        '候选例外：请确认事实、金额及会计方向后再转为调整分录。',
      ))
    }
    if (row.isRelatedParty && !String(row.reasonAnalysis || '').trim()) {
      drafts.push(memo(
        `G4-12 关联方核销缺少合理性分析：${row.unitName || id}`,
        'G4-12',
        id,
        'related-party-analysis-missing',
        `G4-12:writeoff:${id}:related-party-analysis-missing`,
        '关联方核销尚未填写合理性分析。',
      ))
    }
  })
  return drafts
}

export function buildG413AbnormalMemos(rows: LooseRow[]): AdjustmentEntry[] {
  return (rows || []).flatMap((row, index) => {
    if (!row.isAbnormal) return []
    const id = rowId(row, index)
    return [
      memo(
        `G4-13 异常凭证：${row.voucherNo || id}`,
        'G4-13',
        id,
        'abnormal-voucher',
        `G4-13:item:${id}:abnormal-voucher`,
        `${String(row.abnormalNote || row.remark || '异常原因待补充')}；仅作异常备忘，不复制凭证金额作为错报。`,
      ),
    ]
  })
}

export function buildG44InterestVarianceDraft(
  variance: number,
  opts: G4InterestVarianceOptions = {},
): AdjustmentEntry[] {
  const amount = numberValue(variance)
  if (Math.abs(amount) < 0.01) return []
  const id = String(opts.id || 'interest-variance')
  const interestAdjustment = { code: '150102', name: '债权投资——利息调整' }
  const interestIncome = { code: '6011', name: '利息收入' }
  return monetaryPair(
    amount,
    amount > 0 ? interestAdjustment : interestIncome,
    amount > 0 ? interestIncome : interestAdjustment,
    {
      description: opts.description || 'G4-4 实际利率测算差异',
      sourceSheet: 'G4-4',
      sourceRowId: id,
      sourceKind: 'interest-variance',
      sourceKey: `G4-4:item:${id}:interest-variance`,
    },
  )
}

export function mergeExceptionDraftsIntoResponses(
  allResponses: ResponseMap,
  drafts: AdjustmentEntry[],
): ChecklistResponse {
  const existing = parseCanonicalArray(allResponses.get(G4_ITEM_IDS.G4_3_ROWS)) as AdjustmentEntry[]
  const result = mergeProvenanceDrafts(existing, drafts)
  const payload = buildCanonicalPayload(G4_ITEM_IDS.G4_3_ROWS, result.entries)
  allResponses.set(G4_ITEM_IDS.G4_3_ROWS, payload)
  return payload
}

/**
 * 将异常草稿写入 G4 Main 工作底稿（跨 SPPI/ECL 实例时使用）。
 * 不写入当前非 Main 底稿，避免 G4-3 草稿落错 wp。
 */
export async function persistExceptionDraftsToMainWp(
  drafts: AdjustmentEntry[],
  opts: { projectId: string; fallbackWpId?: string },
): Promise<{ mainWpId: string; added: number; updated: number; skipped: number } | null> {
  if (!drafts.length) return null
  const { resolveG4MainWorkpaperId, fetchCanonicalRowsFromWorkpaper, saveCanonicalRowsToWorkpaper } =
    await import('./g4CrossHelpers')
  const mainWpId = await resolveG4MainWorkpaperId(opts.projectId, opts.fallbackWpId)
  if (!mainWpId) return null
  const existing = await fetchCanonicalRowsFromWorkpaper(mainWpId, G4_ITEM_IDS.G4_3_ROWS) as AdjustmentEntry[]
  const result = mergeProvenanceDrafts(existing || [], drafts)
  await saveCanonicalRowsToWorkpaper(
    mainWpId,
    opts.projectId,
    G4_ITEM_IDS.G4_3_ROWS,
    result.entries,
  )
  return {
    mainWpId,
    added: result.added,
    updated: result.updated,
    skipped: result.skipped,
  }
}

export function dispatchG4ExceptionDrafts(
  drafts: AdjustmentEntry[],
  allResponses?: ResponseMap | null,
): void {
  if (!drafts.length) return
  if (allResponses) mergeExceptionDraftsIntoResponses(allResponses, drafts)
  window.dispatchEvent(new CustomEvent('g4:exception-drafts', { detail: { drafts } }))
}
