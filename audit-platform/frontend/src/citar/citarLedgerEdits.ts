/**
 * 科目余额表 / 序时账人工修改（spec citar-table-manual-edit R3~R5）。
 * 余额表改完后端随即重算试算表；序时账修改不回写余额表。所有请求带 _silent：错误由调用方提示一次。
 */
import { api } from '@/services/apiProxy'
import { ledger as P_ledger } from '@/services/apiPaths'

export type LedgerTable = 'balance' | 'ledger'

export interface ManualEditInfo {
  row_id: string
  /** 导入时的原值（存储字段） */
  original: Record<string, string | null>
  count: number
  edited_by: string | null
  edited_at: string | null
  reason: string | null
}

/** 余额表：opening / closing 为借正贷负，debit / credit 为发生额 */
export interface BalanceEditValues {
  opening?: number
  closing?: number
  debit?: number
  credit?: number
}

export interface LedgerEditValues {
  voucher_date?: string
  voucher_no?: string
  summary?: string | null
  account_code?: string
  account_name?: string | null
  debit_amount?: number | null
  credit_amount?: number | null
}

const opts = (year: number) => ({ params: { year }, _silent: true } as any)

export function editBalanceRow(projectId: string, year: number, rowId: string, values: BalanceEditValues, reason?: string) {
  return api.put(P_ledger.balanceRow(projectId, rowId), { values, reason }, { ...opts(year), timeout: 300000 })
}

export function editLedgerEntry(projectId: string, year: number, rowId: string, values: LedgerEditValues, reason?: string) {
  return api.put(P_ledger.entryRow(projectId, rowId), { values, reason }, opts(year))
}

export function restoreLedgerRow(projectId: string, year: number, table: LedgerTable, rowId: string) {
  return api.post(P_ledger.restoreRow(projectId, table, rowId), null, { ...opts(year), timeout: 300000 })
}

export async function fetchManualEdits(projectId: string, year: number, table: LedgerTable): Promise<ManualEditInfo[]> {
  const data = await api.get(P_ledger.manualEdits(projectId), { params: { year, table }, _silent: true } as any)
  return Array.isArray(data) ? (data as ManualEditInfo[]) : []
}

export async function fetchManualEditsSummary(projectId: string, year: number): Promise<{ balance: number; ledger: number }> {
  return api.get(P_ledger.manualEditsSummary(projectId), { params: { year }, _silent: true } as any) as Promise<{ balance: number; ledger: number }>
}

/** 输入框文字 → 数字（可带千分位）；空串按 0；非法返回 NaN */
export function parseMoneyInput(text: string): number {
  const t = text.replace(/,/g, '').trim()
  return t === '' ? 0 : Number(t)
}
