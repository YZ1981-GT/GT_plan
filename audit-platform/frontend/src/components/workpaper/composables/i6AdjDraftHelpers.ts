/**
 * I6-3 调整分录行 — 跨底稿草稿写入共用工具
 * 对齐 useI6Adjustment / I6TabAdjustment：账项调整·报表调整 + accountCode + debitAmount/creditAmount
 * 兼容旧存档（category=AJE/RJE, debit/credit）
 */
import { categoryFromLegacy, entryTypeFromCategory } from './i6AdjustmentModel'

export interface I6AdjRow {
  rowId: string
  description: string
  category: string
  entryType: 'AJE' | 'RJE'
  reportItem: string
  accountCode: string
  accountName: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
  /** 兼容旧字段 */
  debit?: number
  credit?: number
}

export const I63_ROWS_KEY = 'I6-3-rows'

const ACCOUNT_CODE_BY_NAME: Record<string, string> = {
  研发费用: '6602',
  开发支出: '1717',
  其他应付款: '2241',
  应付账款: '2202',
  银行存款: '1002',
}

export function parseI63Rows(raw: unknown): I6AdjRow[] {
  if (Array.isArray(raw)) return raw.map(normalizeI63Row)
  if (typeof raw === 'string' && raw) {
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p.map(normalizeI63Row) : []
    } catch { return [] }
  }
  if (raw && typeof raw === 'object') {
    const obj = raw as any
    const remark = obj.remark ?? obj.conclusion
    if (remark != null) return parseI63Rows(remark)
  }
  return []
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _str(v: unknown): string {
  return v == null ? '' : String(v)
}

function _resolveAccountCode(raw: any, accountName: string): string {
  const code = _str(raw?.accountCode)
  if (code) return code
  return ACCOUNT_CODE_BY_NAME[accountName] || '6602'
}

/** 兼容 I6-4 草稿、截止测试等历史字段 debit/credit、category=AJE */
export function normalizeI63Row(raw: any): I6AdjRow {
  const category = categoryFromLegacy(raw)
  const entryType = entryTypeFromCategory(category)
  const accountName = _str(raw?.accountName) || '研发费用'
  const accountCode = _resolveAccountCode(raw, accountName)
  const debitAmount = _num(raw?.debitAmount ?? raw?.debit)
  const creditAmount = _num(raw?.creditAmount ?? raw?.credit)
  return {
    rowId: _str(raw?.rowId) || `i63-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    description: _str(raw?.description || raw?.summary),
    category,
    entryType,
    reportItem: _str(raw?.reportItem) || (accountCode.startsWith('1717') ? '开发支出' : '研发费用'),
    accountCode,
    accountName,
    noteItem: _str(raw?.noteItem),
    debitAmount,
    creditAmount,
    debit: debitAmount,
    credit: creditAmount,
    indexRef: _str(raw?.indexRef),
    remark: _str(raw?.remark),
  }
}

export function mergeI63LinesSkippingExisting(
  existing: any[],
  incoming: I6AdjRow[],
): { merged: I6AdjRow[]; added: number } {
  const keys = new Set(
    (existing || []).map((r) => {
      const desc = _str(r?.description).trim()
      const acct = _str(r?.accountName || r?.accountCode).trim()
      const side = _num(r?.debitAmount ?? r?.debit) > 0 ? 'D' : 'C'
      return `${desc}||${acct}||${side}`
    }).filter((k) => !k.startsWith('||')),
  )
  const toAdd: I6AdjRow[] = []
  for (const line of incoming) {
    const side = line.debitAmount > 0 ? 'D' : 'C'
    const key = `${line.description}||${line.accountName}||${side}`
    if (keys.has(key)) continue
    toAdd.push({
      ...line,
      rowId: line.rowId || `i63-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    })
    keys.add(key)
  }
  return { merged: [...(existing || []).map(normalizeI63Row), ...toAdd], added: toAdd.length }
}
