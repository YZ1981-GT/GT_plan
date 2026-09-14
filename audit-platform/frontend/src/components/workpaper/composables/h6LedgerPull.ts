/**
 * h6LedgerPull — H6-2 从序时账(tb_ledger)拉取1606科目本期清理分录
 *
 * 纯前端游标分页拉取（复用 K8/K9 expenseLedgerMonthlyPull 范式）：
 * GET /api/projects/{pid}/ledger/entries/1606?year={year}&page=1&page_size=500
 * 按 account_name（明细科目名/资产名称）聚合借方(转入清理增加)和贷方(结转减少)。
 *
 * 科目 1606 固定资产清理：借方=转入清理(增加净值)，贷方=结转损益/冲减(减少)
 */
import { api } from '@/services/apiProxy'

export interface H6LedgerEntry {
  voucher_no?: string
  voucher_date?: string
  account_code: string
  account_name: string
  debit_amount: number
  credit_amount: number
  summary?: string
  counterpart_account?: string
}

export interface H6LedgerAggRow {
  /** 明细科目名（如 固定资产清理-XX设备） */
  accountName: string
  /** 本期借方合计（转入清理） */
  debitTotal: number
  /** 本期贷方合计（结转减少） */
  creditTotal: number
  /** 净额 = 借 - 贷（正=期末有余额未结转） */
  netBalance: number
  /** 笔数 */
  entryCount: number
  /** 来源标注 */
  source: string
}

/**
 * 从序时账拉取科目 1606 本期分录并按明细科目名聚合
 */
export async function pullH6LedgerEntries(
  projectId: string,
  year: number | string,
): Promise<{ rows: H6LedgerAggRow[]; totalEntries: number; error?: string }> {
  if (!projectId || !year) {
    return { rows: [], totalEntries: 0, error: '缺少项目ID或年度' }
  }

  const allEntries: H6LedgerEntry[] = []
  let page = 1
  const pageSize = 500
  const maxPages = 20 // 安全上限 10000 笔

  try {
    while (page <= maxPages) {
      const res: any = await api.get(
        `/api/projects/${projectId}/ledger/entries/1606`,
        { params: { year, page, page_size: pageSize }, _silent: true } as any,
      )
      const items: any[] = res?.items ?? res?.data?.items ?? res?.entries ?? []
      if (!items.length) break

      for (const item of items) {
        allEntries.push({
          voucher_no: item.voucher_no ?? '',
          voucher_date: item.voucher_date ?? '',
          account_code: item.account_code ?? '1606',
          account_name: item.account_name ?? '固定资产清理',
          debit_amount: Number(item.debit_amount) || 0,
          credit_amount: Number(item.credit_amount) || 0,
          summary: item.summary ?? '',
          counterpart_account: item.counterpart_account ?? '',
        })
      }

      if (items.length < pageSize) break
      page++
    }
  } catch (e: any) {
    return { rows: [], totalEntries: 0, error: e?.message || '序时账拉取失败' }
  }

  if (allEntries.length === 0) {
    return { rows: [], totalEntries: 0 }
  }

  // 按明细科目名聚合（去掉"固定资产清理"前缀如有）
  const grouped = new Map<string, { debit: number; credit: number; count: number }>()
  for (const entry of allEntries) {
    let name = entry.account_name || '固定资产清理'
    // 去掉常见前缀 "固定资产清理_" / "固定资产清理-"
    name = name.replace(/^固定资产清理[_\-—]/, '').trim() || name
    const existing = grouped.get(name) || { debit: 0, credit: 0, count: 0 }
    existing.debit += entry.debit_amount
    existing.credit += entry.credit_amount
    existing.count++
    grouped.set(name, existing)
  }

  const rows: H6LedgerAggRow[] = []
  for (const [name, agg] of grouped) {
    // 过滤借贷全零行
    if (Math.abs(agg.debit) < 0.005 && Math.abs(agg.credit) < 0.005) continue
    rows.push({
      accountName: name,
      debitTotal: Math.round(agg.debit * 100) / 100,
      creditTotal: Math.round(agg.credit * 100) / 100,
      netBalance: Math.round((agg.debit - agg.credit) * 100) / 100,
      entryCount: agg.count,
      source: '序时账导入',
    })
  }

  // 按净余额降序
  rows.sort((a, b) => Math.abs(b.netBalance) - Math.abs(a.netBalance))

  return { rows, totalEntries: allEntries.length }
}
