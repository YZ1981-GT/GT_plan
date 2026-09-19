/**
 * G1 跨表共用：证券匹配键、明细解析、推送 G1-3 调整草稿
 */
import { parseNum } from './useG1TraFinFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import type { TradingDetailRow } from './useG1Detail'
import { createEmptyG1AdjustmentRow, type G1AdjustmentRow } from './useG1Adjustment'
import { G1_GROSS_FALLBACK_STANDARD } from './g1AccountScope'

export const G1_DETAIL_KEY = 'G1-2-rows'
export const G1_ADJ_KEY = 'G1-3-rows'

/** 优先 code，其次 name；可选 id */
export function matchSecurityKey(opts: {
  id?: string
  securityCode?: string
  securityName?: string
  code?: string
  name?: string
}): string {
  const id = (opts.id || '').trim().toLowerCase()
  const code = (opts.securityCode || opts.code || '').trim().toLowerCase()
  const name = (opts.securityName || opts.name || '').trim().toLowerCase()
  if (code) return `c:${code}`
  if (id) return `i:${id}`
  if (name) return `n:${name}`
  return ''
}

/** 多键索引：同一行可被 code / id / name 命中 */
export function indexBySecurityKeys<T extends {
  id?: string
  securityCode?: string
  securityName?: string
  cashAccountNo?: string
}>(rows: T[]): Map<string, T> {
  const map = new Map<string, T>()
  for (const r of rows) {
    const code = r.securityCode || r.cashAccountNo || ''
    for (const k of [
      matchSecurityKey({ id: r.id, securityCode: code, securityName: r.securityName }),
      matchSecurityKey({ securityCode: code }),
      matchSecurityKey({ securityName: r.securityName }),
      matchSecurityKey({ id: r.id }),
    ]) {
      if (k && !map.has(k)) map.set(k, r)
    }
  }
  return map
}

export function findBySecurityKeys<T>(
  map: Map<string, T>,
  opts: { id?: string; securityCode?: string; securityName?: string },
): T | undefined {
  const keys = [
    matchSecurityKey(opts),
    matchSecurityKey({ securityCode: opts.securityCode }),
    matchSecurityKey({ securityName: opts.securityName }),
    matchSecurityKey({ id: opts.id }),
  ]
  for (const k of keys) {
    if (k && map.has(k)) return map.get(k)
  }
  return undefined
}

export function loadDetailPartials(
  responses: Map<string, ChecklistResponse>,
): Partial<TradingDetailRow>[] {
  const raw = responses.get(G1_DETAIL_KEY)?.conclusion
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function dispatchG1DetailUpdated(source: string): void {
  try {
    window.dispatchEvent(
      new CustomEvent('g1:detail-updated', { detail: { source, timestamp: Date.now() } }),
    )
  } catch {
    /* ignore */
  }
}

export interface G1PushAdjItem {
  description: string
  amount: number
  /** 正数记借方（资产增加），负数记贷方 */
  indexRef: string
  remark?: string
  accountName?: string
}

/** 追加推送至 G1-3；返回新增条数 */
export function pushItemsToG1Adjustment(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  items: G1PushAdjItem[],
  source: string,
): number {
  if (!items.length) return 0

  let existing: G1AdjustmentRow[] = []
  const raw = responses.get(G1_ADJ_KEY)?.remark || responses.get(G1_ADJ_KEY)?.conclusion
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) existing = parsed
    } catch {
      existing = []
    }
  }

  const added: G1AdjustmentRow[] = items.map((it) => {
    const amt = Math.abs(parseNum(it.amount))
    const isDebit = parseNum(it.amount) > 0
    const row = createEmptyG1AdjustmentRow()
    return {
      ...row,
      description: it.description,
      category: '账项调整',
      reportItem: '交易性金融资产',
      accountName: it.accountName || '交易性金融资产',
      accountCode: G1_GROSS_FALLBACK_STANDARD,
      debitAmount: isDebit ? amt : 0,
      creditAmount: isDebit ? 0 : amt,
      indexRef: it.indexRef,
      remark: it.remark || '',
    }
  })

  const merged = [...existing, ...added]
  const json = JSON.stringify(merged)
  debouncedSave(G1_ADJ_KEY, { remark: json, conclusion: json })

  for (const row of added) {
    try {
      window.dispatchEvent(
        new CustomEvent('adjustment:created', {
          detail: {
            wpCode: 'G1',
            entryType: 'AJE',
            amount: Math.max(row.debitAmount, row.creditAmount),
            accountCode: G1_GROSS_FALLBACK_STANDARD,
            accountName: row.accountName,
            description: row.description,
            debitAmount: row.debitAmount,
            creditAmount: row.creditAmount,
            source,
            timestamp: Date.now(),
          },
        }),
      )
    } catch {
      /* silent */
    }
  }
  return added.length
}

/** 读取闸门 JSON */
export function loadGatesJson<T extends Record<string, unknown>>(
  responses: Map<string, ChecklistResponse>,
  key: string,
  defaults: T,
): T {
  const raw = responses.get(key)?.conclusion
  if (!raw) return { ...defaults }
  try {
    return { ...defaults, ...(JSON.parse(raw) as Partial<T>) }
  } catch {
    return { ...defaults }
  }
}
