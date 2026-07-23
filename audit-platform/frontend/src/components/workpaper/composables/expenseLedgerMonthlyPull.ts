/**
 * expenseLedgerMonthlyPull — 损益费用类底稿「从序时账按月取数」
 *
 * 从 `/api/projects/{pid}/ledger/entries/{accountCode}` 拉取明细分录（游标分页），
 * 按 明细科目名称 × 月份 聚合发生额（借方−贷方），供 K8-2/K9-2 明细表按月回填。
 *
 * 纯前端聚合，不新增后端 resolver（规避并发会话对 auto_data_resolvers 的改动）。
 * 源模板 K8-2/K9-2 审计过程要求「获取或编制各个月份期间费用主要构成情况」。
 */
import http from '@/utils/http'

export interface MonthlyByAccount {
  accountName: string
  /** 12 个月发生额（借方−贷方），index 0=1月 */
  months: number[]
}

export interface LedgerMonthlyPullResult {
  ok: boolean
  message: string
  rows: MonthlyByAccount[]
  /** 全部科目合计发生额 */
  total: number
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 从 voucher_date(YYYY-MM-DD) 取月份 index（0-11），非法返回 -1 */
function monthIndex(dateStr: unknown): number {
  const m = String(dateStr ?? '').match(/^\d{4}-(\d{2})/)
  if (!m) return -1
  const mm = Number(m[1])
  return mm >= 1 && mm <= 12 ? mm - 1 : -1
}

/**
 * 拉取并聚合某科目当年按明细科目×月的发生额。
 * @param projectId 项目 id
 * @param accountCode 科目编码（K8=6601 / K9=6602）
 * @param year 审计年度
 */
export async function pullExpenseLedgerMonthly(
  projectId: string,
  accountCode: string,
  year: number,
): Promise<LedgerMonthlyPullResult> {
  if (!projectId || !accountCode || !year) {
    return { ok: false, message: '缺少项目/科目/年度参数', rows: [], total: 0 }
  }

  const byAccount = new Map<string, number[]>()
  let total = 0
  let cursor: string | null = null
  let guard = 0

  try {
    // 游标分页拉全量（最多 20 页 × 1000 = 20000 条安全上限）
    do {
      const params: Record<string, any> = { year, limit: 1000 }
      if (cursor) params.cursor = cursor
      const res = await http.get(
        `/api/projects/${projectId}/ledger/entries/${encodeURIComponent(accountCode)}`,
        { params, _silent: true } as any,
      )
      const payload = res.data?.data ?? res.data ?? {}
      const items: any[] = Array.isArray(payload.items)
        ? payload.items
        : Array.isArray(payload)
          ? payload
          : []
      for (const it of items) {
        const code = String(it.account_code ?? it.standard_account_code ?? '')
        if (!code.startsWith(accountCode)) continue
        const mi = monthIndex(it.voucher_date ?? it.date)
        if (mi < 0) continue
        const name = String(it.account_name ?? it.accountName ?? '未命名').trim() || '未命名'
        const amt = num(it.debit_amount ?? it.debit) - num(it.credit_amount ?? it.credit)
        if (!byAccount.has(name)) byAccount.set(name, new Array(12).fill(0))
        byAccount.get(name)![mi] += amt
        total += amt
      }
      cursor = payload.next_cursor ?? payload.nextCursor ?? null
      guard += 1
    } while (cursor && guard < 20)
  } catch (e: any) {
    return {
      ok: false,
      message: e?.response?.data?.detail || e?.message || '序时账取数失败',
      rows: [],
      total: 0,
    }
  }

  const rows: MonthlyByAccount[] = [...byAccount.entries()]
    .map(([accountName, months]) => ({ accountName, months }))
    .filter((r) => r.months.some((m) => Math.abs(m) > 0.005))

  if (!rows.length) {
    return { ok: false, message: `未从序时账取到科目 ${accountCode} 的 ${year} 年度发生额`, rows: [], total: 0 }
  }
  return { ok: true, message: `已从序时账聚合 ${rows.length} 个明细科目的月度发生额`, rows, total }
}
