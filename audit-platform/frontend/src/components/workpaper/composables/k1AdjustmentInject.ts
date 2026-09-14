/**
 * k1AdjustmentInject — K1-12 等来源底稿向 K1-4 幂等注入调整分录行
 */
import type { K1AbnormalAdjDraft } from './useK1VoucherCheck'
import { normalizeK1AdjustmentRow, type K1AdjustmentRow } from './useK1Adjustment'

export const K1_4_ROWS_KEY = 'K1-4-adj-entries'

function genId(): string {
  return `k1a-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function parseExisting(raw: unknown): any[] {
  if (!raw) return []
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/**
 * 幂等注入 K1-4 调整分录。按 sourceKind 替换同来源旧行。
 */
export function injectK1Adjustments(
  allResponses: Map<string, any>,
  drafts: K1AbnormalAdjDraft[],
  sourceKind: string,
): K1AdjustmentRow[] {
  const saved = allResponses.get(K1_4_ROWS_KEY)
  const raw = saved?.remark ?? saved?.value
  const existing = parseExisting(raw)
  const kept = existing.filter((r) => r?.sourceKind !== sourceKind)

  const appended = drafts.map((d, i) =>
    normalizeK1AdjustmentRow(
      {
        rowId: genId(),
        seq: kept.length + i + 1,
        description: d.summary,
        category: '账项调整',
        entryType: 'AJE',
        reportItem: '其他应收款',
        accountCode: d.accountCode,
        accountName: d.accountName,
        noteItem: '其他应收款',
        debitAmount: d.debitAmount,
        creditAmount: d.creditAmount,
        indexRef: d.indexRef || 'K1-12',
        remark: d.remark,
        sourceKind,
      },
      kept.length + i,
    ),
  )

  const merged = [...kept, ...appended].map((r, i) => ({ ...r, seq: i + 1 }))
  allResponses.set(K1_4_ROWS_KEY, {
    item_id: K1_4_ROWS_KEY,
    conclusion: null,
    remark: JSON.stringify(merged),
  })
  return appended
}
