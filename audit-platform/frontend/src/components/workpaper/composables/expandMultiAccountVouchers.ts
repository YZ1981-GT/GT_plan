/**
 * expandMultiAccountVouchers — 多科目凭证展开为多行
 *
 * 抽凭引擎返回的样本中，1对多/多对多凭证标记为 isMultiAccount=true 并附带
 * voucherEntries 完整分录列表。本函数将这些样本按对方分录展开为多行，
 * 每行带具体的对方科目代码、名称和金额。
 *
 * 展开策略：
 * - 当前行是借方（debitAmount > 0）→ 对方取贷方分录
 * - 当前行是贷方（creditAmount > 0）→ 对方取借方分录
 * - 展开后每行保留原样本的公共字段（凭证号/日期/异常标记等）
 *
 * 非多科目样本原样返回。
 */

export interface VoucherEntry {
  account_code: string
  account_name: string
  debit_amount: string | null
  credit_amount: string | null
  summary: string
}

export interface ExpandableSample {
  counterpartAccount?: string | null
  counterpartAccountName?: string | null
  isMultiAccount?: boolean
  voucherEntries?: VoucherEntry[]
  debitAmount?: string | number | null
  creditAmount?: string | number | null
  summary?: string | null
  [key: string]: unknown
}

/**
 * 从 voucherEntries 中筛选对方方向的分录
 */
function filterCounterEntries(entries: VoucherEntry[], sDebit: number): VoucherEntry[] {
  const counter = entries.filter(e =>
    sDebit > 0
      ? (e.credit_amount && Number(e.credit_amount) > 0)
      : (e.debit_amount && Number(e.debit_amount) > 0),
  )
  return counter.length > 0 ? counter : entries
}

/**
 * 展开多科目凭证为多行。
 *
 * @param samples 抽凭样本数组
 * @returns 展开后的样本数组（非多科目原样返回）
 */
export function expandMultiAccountVouchers<T extends ExpandableSample>(samples: T[]): T[] {
  const result: T[] = []
  for (const s of samples) {
    const entries = s.voucherEntries || []
    const isMulti = (s.isMultiAccount === true || s.counterpartAccount === '多科目') && entries.length > 0

    if (!isMulti) {
      result.push(s)
      continue
    }

    const sDebit = Number(s.debitAmount ?? 0)
    const counterEntries = filterCounterEntries(entries, sDebit)

    for (const e of counterEntries) {
      result.push({
        ...s,
        counterpartAccount: e.account_code || '',
        counterpartAccountName: e.account_name || '',
        isMultiAccount: false, // 展开后的每行都是单科目
        debitAmount: e.debit_amount != null ? String(Number(e.debit_amount) || 0) : null,
        creditAmount: e.credit_amount != null ? String(Number(e.credit_amount) || 0) : null,
        summary: e.summary || s.summary || null,
      } as T)
    }
  }
  return result
}

/**
 * 多科目拼接模式（适用于资产类底稿：一行=一个资产项，不宜展开为多行）。
 * 将所有对方科目的代码和名称用 / 拼接返回。
 *
 * @returns { account: string, detail: string } 拼接后的科目代码和名称
 */
export function joinMultiAccountNames(s: ExpandableSample): { account: string; detail: string } {
  const entries = s.voucherEntries || []
  const isMulti = (s.isMultiAccount === true || s.counterpartAccount === '多科目') && entries.length > 0
  if (!isMulti) {
    return {
      account: String(s.counterpartAccount || ''),
      detail: String(s.counterpartAccountName || ''),
    }
  }
  const sDebit = Number(s.debitAmount ?? 0)
  const counterEntries = filterCounterEntries(entries, sDebit)
  return {
    account: counterEntries.map(e => e.account_code).filter(Boolean).join('/'),
    detail: counterEntries.map(e => e.account_name).filter(Boolean).join('/'),
  }
}
