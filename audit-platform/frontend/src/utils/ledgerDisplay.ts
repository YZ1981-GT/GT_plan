/**
 * 明细账展示构建 — 纯函数（组件与单测共用同一份，避免 copy 漂移）
 *
 * 输入：原始序时账/辅助明细账行（已按 voucher_date 升序）+ 期初余额
 * 输出：期初行 + 每笔业务行（含运行余额）+ 每月「本月合计」小计行
 *
 * 关键不变式（守护 off-by-one bug）：
 *  - 月小计必须在「月份边界结算之后、累加当前行之前」插入，
 *    否则上月小计会错误并入本月第一笔（借/贷/运行余额均偏移）。
 *  - 运行余额 = 期初 + Σ借 − Σ贷（逐行累计）。
 *  - 全部月小计的借/贷之和 = 全期借/贷总额（守恒）。
 */
import Decimal from 'decimal.js'

Decimal.set({ precision: 20, rounding: Decimal.ROUND_HALF_EVEN })

export interface LedgerRawItem {
  voucher_date?: string
  voucher_no?: string
  debit_amount?: number | string | null
  credit_amount?: number | string | null
  running_balance?: number | string | null
  counterpart_account?: string | null
  [k: string]: any
}

export interface LedgerDisplayRow {
  _type: 'opening' | 'normal' | 'subtotal' | 'view_subtotal'
  voucher_date: string
  voucher_no: string
  summary: string
  debit_amount: number | null
  credit_amount: number | null
  balance: number
  [k: string]: any
}

export interface BuildLedgerDisplayOptions {
  /** 合成行（期初/小计）上需要补齐的额外字段，如 { counterpart_account: '', account_code: '' } */
  syntheticExtra?: Record<string, any>
}

export interface LedgerViewFilterOptions {
  keyword?: string
  amountDir?: 'all' | 'debit' | 'credit'
  sort?: { key: string; order: 'asc' | 'desc' } | null
  syntheticExtra?: Record<string, any>
}

function toNum(v: unknown): number {
  return Number(v) || 0
}

/** 高精度加：返回 number（金额 2 位） */
function dAdd(a: number, b: number): number {
  return Number(new Decimal(a).plus(b).toFixed(2, Decimal.ROUND_HALF_EVEN))
}

/** 高精度减：返回 number（金额 2 位） */
function dSub(a: number, b: number): number {
  return Number(new Decimal(a).minus(b).toFixed(2, Decimal.ROUND_HALF_EVEN))
}

/**
 * 构建明细账展示行（期初 + 业务行 + 月小计）。
 *
 * @param items   原始行（按 voucher_date 升序）
 * @param opening 期初余额
 * @param options 合成行额外字段
 */
export function buildLedgerDisplay(
  items: LedgerRawItem[],
  opening: number,
  options: BuildLedgerDisplayOptions = {},
): LedgerDisplayRow[] {
  const extra = options.syntheticExtra ?? {}
  const rows: LedgerDisplayRow[] = []

  if (!items || items.length === 0) {
    rows.push({
      _type: 'opening', voucher_date: '', voucher_no: '',
      summary: '期初余额', debit_amount: null, credit_amount: null,
      balance: opening, ...extra,
    })
    return rows
  }

  let balance = opening
  let monthDebit = 0
  let monthCredit = 0
  let lastMonth = ''

  rows.push({
    _type: 'opening', voucher_date: '', voucher_no: '',
    summary: '期初余额', debit_amount: null, credit_amount: null,
    balance, ...extra,
  })

  for (const item of items) {
    const d = toNum(item.debit_amount)
    const c = toNum(item.credit_amount)
    const month = (item.voucher_date || '').substring(0, 7)
    if (!lastMonth) lastMonth = month

    if (month !== lastMonth) {
      rows.push({
        _type: 'subtotal', voucher_date: '', voucher_no: '',
        summary: `${lastMonth} 本月合计`,
        debit_amount: monthDebit, credit_amount: monthCredit,
        balance,
        ...extra,
      })
      monthDebit = 0
      monthCredit = 0
      lastMonth = month
    }

    if (item.running_balance != null && item.running_balance !== '') {
      balance = toNum(item.running_balance)
    } else {
      balance = dSub(dAdd(balance, d), c)
    }
    monthDebit = dAdd(monthDebit, d)
    monthCredit = dAdd(monthCredit, c)

    rows.push({ ...item, _type: 'normal', balance } as LedgerDisplayRow)
  }

  rows.push({
    _type: 'subtotal', voucher_date: '', voucher_no: '',
    summary: `${lastMonth} 本月合计`,
    debit_amount: monthDebit, credit_amount: monthCredit,
    balance, ...extra,
  })

  return rows
}

function matchesKeyword(item: LedgerRawItem, kw: string): boolean {
  const summary = String(item.summary || '').toLowerCase()
  const voucherNo = String(item.voucher_no || '').toLowerCase()
  const counterpart = String(item.counterpart_account || '').toLowerCase()
  const vdate = String(item.voucher_date || '').toLowerCase()
  return summary.includes(kw) || voucherNo.includes(kw) || counterpart.includes(kw) || vdate.includes(kw)
}

function sortItems(items: LedgerRawItem[], sort: { key: string; order: 'asc' | 'desc' }): LedgerRawItem[] {
  const factor = sort.order === 'desc' ? -1 : 1
  return items.slice().sort((a, b) => {
    const av = a[sort.key]
    const bv = b[sort.key]
    const an = typeof av === 'number' ? av : parseFloat(String(av))
    const bn = typeof bv === 'number' ? bv : parseFloat(String(bv))
    if (Number.isFinite(an) && Number.isFinite(bn)) return (an - bn) * factor
    return String(av ?? '').localeCompare(String(bv ?? '')) * factor
  })
}

/**
 * 虚拟滚动视图：筛选/排序后的展示行。
 * - 仅筛选：对筛选子集重算月小计（语义正确）。
 * - 有排序：保留期初 + 排序行（余额取自全量序）+「当前视图合计」。
 */
export function buildLedgerFilteredDisplay(
  items: LedgerRawItem[],
  opening: number,
  options: LedgerViewFilterOptions = {},
): LedgerDisplayRow[] {
  const {
    keyword = '',
    amountDir = 'all',
    sort = null,
    syntheticExtra = {},
  } = options
  const kw = keyword.trim().toLowerCase()
  const extra = syntheticExtra

  if (!items?.length && !kw && amountDir === 'all' && !sort) {
    return buildLedgerDisplay(items, opening, { syntheticExtra: extra })
  }

  let filtered = items ?? []
  if (kw) filtered = filtered.filter((r) => matchesKeyword(r, kw))
  if (amountDir === 'debit') filtered = filtered.filter((r) => toNum(r.debit_amount) > 0)
  else if (amountDir === 'credit') filtered = filtered.filter((r) => toNum(r.credit_amount) > 0)

  const hasFilter = !!kw || amountDir !== 'all'

  if (!sort && !hasFilter) {
    return buildLedgerDisplay(items, opening, { syntheticExtra: extra })
  }

  if (!sort && hasFilter) {
    return buildLedgerDisplay(filtered, opening, { syntheticExtra: extra })
  }

  const fullDisplay = buildLedgerDisplay(items, opening, { syntheticExtra: extra })
  const openingRow = fullDisplay.find((r) => r._type === 'opening')
  const balanceById = new Map<string, number>()
  for (const row of fullDisplay) {
    if (row._type === 'normal' && row.id != null) {
      balanceById.set(String(row.id), row.balance)
    }
  }

  const sorted = sortItems(filtered, sort!)
  let sumD = 0
  let sumC = 0
  const rows: LedgerDisplayRow[] = openingRow ? [openingRow] : []

  for (const item of sorted) {
    const bal = item.id != null ? (balanceById.get(String(item.id)) ?? opening) : opening
    sumD = dAdd(sumD, toNum(item.debit_amount))
    sumC = dAdd(sumC, toNum(item.credit_amount))
    rows.push({ ...item, _type: 'normal', balance: bal } as LedgerDisplayRow)
  }

  const lastBal = sorted.length
    ? (sorted[sorted.length - 1].id != null
        ? balanceById.get(String(sorted[sorted.length - 1].id)) ?? opening
        : opening)
    : opening

  rows.push({
    _type: 'view_subtotal',
    voucher_date: '', voucher_no: '',
    summary: '当前视图合计',
    debit_amount: sumD,
    credit_amount: sumC,
    balance: lastBal,
    ...extra,
  })

  return rows
}
