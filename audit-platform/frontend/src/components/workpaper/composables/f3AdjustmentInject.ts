/**
 * f3AdjustmentInject — 将来源底稿（F3-5 逾期重分类 / F3-4 补提利息）生成的调整分录
 * 幂等写入 F3-3-rows，并派发 f3:save-items 持久化。
 *
 * Spec: f3-notes-payable 复盘改进 P0-2 / P1-5
 *
 * 幂等策略：按 sourceKind 先移除同来源旧行再追加，避免重复点击累积。
 * 注：useF3Adjustment 保留行内 sourceKind 字段，故用户在 F3-3 手工重存后仍可幂等替换。
 */
import type { ChecklistResponse } from './useF3FormData'
import { parseNum } from './useF3FormulaEngine'

export interface F3InjectAdjustmentRow {
  entryType: 'AJE' | 'RJE'
  date?: string
  summary: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  remark?: string
}

const F3_3_KEY = 'F3-3-rows'

function genId(): string {
  return `f3a-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

/**
 * 幂等注入调整分录到 F3-3-rows。返回本次写入的行数。
 * @param sourceKind 来源标识（如 'overdue-reclass' / 'interest-accrual'）
 */
export function injectF3Adjustments(
  allResponses: Map<string, ChecklistResponse>,
  rows: F3InjectAdjustmentRow[],
  sourceKind: string,
): number {
  let existing: any[] = []
  try {
    const raw = allResponses.get(F3_3_KEY)?.remark
    existing = raw ? JSON.parse(raw) : []
    if (!Array.isArray(existing)) existing = []
  } catch {
    existing = []
  }

  // 移除同来源旧行（幂等）
  const kept = existing.filter((r) => r?.sourceKind !== sourceKind)

  const appended = rows.map((r) => ({
    rowId: genId(),
    seq: 0,
    entryType: r.entryType === 'RJE' ? 'RJE' : 'AJE',
    date: r.date || '',
    summary: r.summary,
    accountCode: r.accountCode,
    accountName: r.accountName,
    debitAmount: parseNum(r.debitAmount),
    creditAmount: parseNum(r.creditAmount),
    preparer: '',
    remark: r.remark || '',
    sourceKind,
  }))

  const merged = [...kept, ...appended].map((r, i) => ({ ...r, seq: i + 1 }))
  allResponses.set(F3_3_KEY, { item_id: F3_3_KEY, conclusion: null, remark: JSON.stringify(merged) })
  try {
    const item = allResponses.get(F3_3_KEY)
    if (item) {
      window.dispatchEvent(new CustomEvent('f3:save-items', { detail: { items: [item] } }))
    }
  } catch {
    /* silent */
  }
  return appended.length
}
