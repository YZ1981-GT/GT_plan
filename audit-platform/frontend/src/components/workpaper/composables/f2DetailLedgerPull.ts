/**
 * f2DetailLedgerPull — F2-3~F2-13 存货明细表「从序时账取数」共享 helper
 *
 * 从 `/api/projects/{pid}/ledger/entries/{accountCode}` 拉取明细分录（游标分页），
 * 按 account_name 分组聚合 debit/credit，供 F2 各明细表按钮回填。
 *
 * 纯前端聚合，不新增后端 resolver。
 */
import { api } from '@/services/apiProxy'

/** F2 明细表编码 → 科目编码映射 */
export const F2_DETAIL_SHEET_ACCOUNT: Record<string, string> = {
  'F2-3': '1401',
  'F2-4': '1402',
  'F2-5': '1403',
  'F2-6': '1404',
  'F2-7': '1405',
  'F2-8': '1406',
  'F2-9': '1407',
  'F2-10': '1408',
  'F2-11': '1409',
  'F2-12': '1410',
  'F2-13': '1411',
}

export interface LedgerPullRow {
  /** 明细科目名（account_name） */
  name: string
  /** 子科目编码 */
  accountCode: string
  /** 本期增加 Σ debit_amount（资产借方=增加） */
  increase: number
  /** 本期减少 Σ credit_amount（资产贷方=减少） */
  decrease: number
}

export interface LedgerPullResult {
  rows: LedgerPullRow[]
  totalIncrease: number
  totalDecrease: number
  pagesFetched: number
}

const PAGE_SIZE = 200

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/**
 * 从序时账按明细科目名归集 F2 存货明细表取数。
 * 纯前端游标分页（复用 /ledger/entries/{code} 接口），
 * 按 account_name 分组聚合 debit/credit。
 */
export async function pullF2DetailFromLedger(
  projectId: string,
  accountCode: string,
  year: number | string,
): Promise<LedgerPullResult> {
  if (!projectId || !accountCode || !year) {
    return { rows: [], totalIncrease: 0, totalDecrease: 0, pagesFetched: 0 }
  }

  const byName = new Map<string, { accountCode: string; increase: number; decrease: number }>()
  let page = 1
  let pagesFetched = 0

  try {
    // eslint-disable-next-line no-constant-condition
    while (true) {
      const res = await api.get(
        `/api/projects/${projectId}/ledger/entries/${encodeURIComponent(accountCode)}`,
        { params: { year, page, page_size: PAGE_SIZE } },
      )

      const payload = res?.data ?? res ?? {}
      const items: any[] = Array.isArray(payload.items)
        ? payload.items
        : Array.isArray(payload)
          ? payload
          : []

      pagesFetched++

      for (const it of items) {
        const name = String(it.account_name ?? it.accountName ?? '').trim() || '未命名'
        const code = String(it.account_code ?? it.standard_account_code ?? '')
        const debit = num(it.debit_amount ?? it.debit)
        const credit = num(it.credit_amount ?? it.credit)

        if (!byName.has(name)) {
          byName.set(name, { accountCode: code, increase: 0, decrease: 0 })
        }
        const entry = byName.get(name)!
        entry.increase += debit
        entry.decrease += credit
        // 取最精确的科目码（可能有多条同名不同码，取最后一条）
        if (code) entry.accountCode = code
      }

      // 无 next_cursor 且本页条目数 < page_size → 已到末页
      const nextCursor = payload.next_cursor ?? payload.nextCursor ?? null
      if (items.length < PAGE_SIZE && !nextCursor) break
      if (!nextCursor && items.length === 0) break

      page++

      // 安全上限防无限循环
      if (pagesFetched >= 100) break
    }
  } catch {
    // 异常不抛，返回空结果
    return { rows: [], totalIncrease: 0, totalDecrease: 0, pagesFetched: 0 }
  }

  // 构建结果行，按 increase + decrease 降序排列
  const rows: LedgerPullRow[] = [...byName.entries()]
    .map(([name, data]) => ({
      name,
      accountCode: data.accountCode,
      increase: data.increase,
      decrease: data.decrease,
    }))
    .sort((a, b) => (b.increase + b.decrease) - (a.increase + a.decrease))

  const totalIncrease = rows.reduce((sum, r) => sum + r.increase, 0)
  const totalDecrease = rows.reduce((sum, r) => sum + r.decrease, 0)

  return { rows, totalIncrease, totalDecrease, pagesFetched }
}
