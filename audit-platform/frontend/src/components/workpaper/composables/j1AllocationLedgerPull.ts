/**
 * j1AllocationLedgerPull — J1-7 分配情况检查表「从序时账取数」
 *
 * 从 `/api/projects/{pid}/ledger/entries/2211` 拉取应付职工薪酬明细分录（游标分页），
 * 取 **贷方发生额（计提）** 按「薪酬项目（2211 明细科目名）× 对方科目归属」聚合，
 * 直接映射 J1-7 的行 × 分配列（生产成本/制造费用/管理费用/销售费用/其他）。
 *
 * 口径：负债贷方 = 本期计提；对方科目（借方）即受益对象费用/成本科目。
 * 复用 K8/K9 的「纯前端游标分页聚合」范式（expenseLedgerMonthlyPull），不新增后端 resolver。
 *
 * 🔴 对方科目（counterpart_account）在部分账套填充率低（合并记账时为空），
 *    无法归属的贷方金额计入 `unattributedAmount` 并如实提示，不臆造分配。
 */
import http from '@/utils/http'

export type J1AllocBucket =
  | 'productionCost'
  | 'manufacturing'
  | 'adminExpense'
  | 'sellingExpense'
  | 'otherExpense'

export interface J1AllocPullRow {
  /** 薪酬项目（2211 明细科目名末段） */
  label: string
  productionCost: number
  manufacturing: number
  adminExpense: number
  sellingExpense: number
  otherExpense: number
  /** 本期实际计提数（该薪酬项目贷方发生额合计） */
  actualAccrual: number
}

export interface J1AllocPullResult {
  ok: boolean
  message: string
  rows: J1AllocPullRow[]
  /** 对方科目为空、无法归属分配列的贷方金额 */
  unattributedAmount: number
  /** 贷方发生额总计 */
  total: number
}

function num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

/** 取科目名末段（'应付职工薪酬_工资' → '工资'），并去空白 */
export function tailSegment(raw: unknown): string {
  const s = String(raw ?? '').replace(/[\s\u3000]/g, '')
  if (!s) return ''
  const parts = s.split(/[_\-—/／、:：|]/).filter(Boolean)
  return parts.length ? parts[parts.length - 1] : s
}

/**
 * 对方科目 → J1-7 分配列
 * 生产成本 5001/4001、制造费用 5101/4101、管理费用 6602、销售费用 6601，其余归「其他」
 * （对方科目编码缺失时按名称关键词判定）
 */
export function bucketForCounterpart(code: unknown, name?: unknown): J1AllocBucket {
  const c = String(code ?? '').replace(/[\s\u3000]/g, '')
  if (c.startsWith('5001') || c.startsWith('4001')) return 'productionCost'
  if (c.startsWith('5101') || c.startsWith('4101')) return 'manufacturing'
  if (c.startsWith('6602')) return 'adminExpense'
  if (c.startsWith('6601')) return 'sellingExpense'
  const n = String(name ?? c)
  if (n.includes('生产成本') || n.includes('劳务成本')) return 'productionCost'
  if (n.includes('制造费用')) return 'manufacturing'
  if (n.includes('管理费用')) return 'adminExpense'
  if (n.includes('销售费用') || n.includes('营业费用')) return 'sellingExpense'
  return 'otherExpense'
}

/** 是否携带可用的对方科目信息 */
function hasCounterpart(v: unknown): boolean {
  return String(v ?? '').replace(/[\s\u3000]/g, '').length > 0
}

/** 聚合序时账分录 → J1-7 行（纯函数，便于单测） */
export function aggregateJ1Allocation(
  items: Array<Record<string, unknown>>,
  accountCode = '2211',
): { rows: J1AllocPullRow[]; unattributedAmount: number; total: number } {
  const byLabel = new Map<string, J1AllocPullRow>()
  let unattributed = 0
  let total = 0

  for (const it of items) {
    const code = String(it.account_code ?? it.standard_account_code ?? '')
    if (accountCode && !code.startsWith(accountCode)) continue
    const credit = num(it.credit_amount ?? it.credit)
    if (credit <= 0) continue // 只取贷方（计提）
    const label = tailSegment(it.account_name ?? it.accountName) || '未命名'
    if (!byLabel.has(label)) {
      byLabel.set(label, {
        label,
        productionCost: 0,
        manufacturing: 0,
        adminExpense: 0,
        sellingExpense: 0,
        otherExpense: 0,
        actualAccrual: 0,
      })
    }
    const row = byLabel.get(label)!
    row.actualAccrual += credit
    total += credit
    const cp = it.counterpart_account ?? it.counterpartAccount
    if (hasCounterpart(cp)) {
      row[bucketForCounterpart(cp, cp)] += credit
    } else {
      unattributed += credit
    }
  }

  const rows = [...byLabel.values()].filter((r) => Math.abs(r.actualAccrual) > 0.005)
  return { rows, unattributedAmount: unattributed, total }
}

/**
 * 拉取并聚合某年度应付职工薪酬（2211）贷方发生额的费用分配情况
 */
export async function pullJ1AllocationFromLedger(
  projectId: string,
  year: number,
  accountCode = '2211',
): Promise<J1AllocPullResult> {
  if (!projectId || !year) {
    return { ok: false, message: '缺少项目/年度参数', rows: [], unattributedAmount: 0, total: 0 }
  }
  const collected: Array<Record<string, unknown>> = []
  let cursor: string | null = null
  let guard = 0
  try {
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
      collected.push(...items)
      cursor = payload.next_cursor ?? payload.nextCursor ?? null
      guard += 1
    } while (cursor && guard < 20)
  } catch (e: any) {
    return {
      ok: false,
      message: e?.response?.data?.detail || e?.message || '序时账取数失败',
      rows: [],
      unattributedAmount: 0,
      total: 0,
    }
  }

  const { rows, unattributedAmount, total } = aggregateJ1Allocation(collected, accountCode)
  if (!rows.length) {
    return {
      ok: false,
      message: `未从序时账取到科目 ${accountCode} 的 ${year} 年度贷方发生额`,
      rows: [],
      unattributedAmount: 0,
      total: 0,
    }
  }
  const tip =
    unattributedAmount > 0
      ? `；其中 ${unattributedAmount.toLocaleString('zh-CN', { maximumFractionDigits: 2 })} 元因对方科目为空未能归属分配列，请手工补录`
      : ''
  return {
    ok: true,
    message: `已聚合 ${rows.length} 个薪酬项目的分配情况${tip}`,
    rows,
    unattributedAmount,
    total,
  }
}
