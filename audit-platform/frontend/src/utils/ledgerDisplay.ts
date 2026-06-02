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
  [k: string]: any
}

export interface LedgerDisplayRow {
  _type: 'opening' | 'normal' | 'subtotal'
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
    // 仍返回期初行，保持与有数据时一致的结构
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
    const month = (item.voucher_date || '').substring(0, 7) // "2025-01"
    if (!lastMonth) lastMonth = month

    // 月份变化时先结算上月小计 —— 必须在累加当前行之前。
    if (month !== lastMonth) {
      rows.push({
        _type: 'subtotal', voucher_date: '', voucher_no: '',
        summary: `${lastMonth} 本月合计`,
        debit_amount: monthDebit, credit_amount: monthCredit,
        balance, // 上月末余额（尚未并入本月首笔）
        ...extra,
      })
      monthDebit = 0
      monthCredit = 0
      lastMonth = month
    }

    // 累加当前行：先更新运行余额，再累加本月借贷合计。
    balance = dSub(dAdd(balance, d), c)
    monthDebit = dAdd(monthDebit, d)
    monthCredit = dAdd(monthCredit, c)

    rows.push({ ...item, _type: 'normal', balance } as LedgerDisplayRow)
  }

  // 末月小计
  rows.push({
    _type: 'subtotal', voucher_date: '', voucher_no: '',
    summary: `${lastMonth} 本月合计`,
    debit_amount: monthDebit, credit_amount: monthCredit,
    balance, ...extra,
  })

  return rows
}
