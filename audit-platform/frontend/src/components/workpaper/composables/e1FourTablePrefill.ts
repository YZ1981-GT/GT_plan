/**
 * e1FourTablePrefill — E1 货币资金「四表取数」预填与种子构造（纯函数）
 *
 * 后端 `_e1_monetary_fund.py` render 策略输出 `html_data.four_table_prefill`：
 *   { cash: [...], bank: [...], other: [...], account_list: [...], meta: {...} }
 * 每条源记录：{ code, name, currency, opening, increase, decrease, ending,
 *              source, formula, formulaOpening }
 *
 * 本模块把四表源记录映射为各 E1 明细 composable 的行 JSON（对齐其 USER_FIELDS
 * 序列化契约），供 GtE1MonetaryFund 在**无持久化数据时**种子填充（persist-first：
 * 仅当对应 rows 键缺失才种子，用户编辑后由 composable 持久化真实数据，不覆盖）。
 *
 * 单一真源：四表库（tb_balance 叶子子科目）。可在「四表取数」公式管理面板查看
 * 每条取数的来源科目 + TB() 公式 + 金额，并可一键「重新取数」。
 */

export interface FourTableSourceRow {
  code: string
  name: string
  currency?: string
  opening: number
  increase: number
  decrease: number
  ending: number
  source: string
  formula: string
  formulaOpening: string
}

export interface FourTablePrefill {
  cash: FourTableSourceRow[]
  bank: FourTableSourceRow[]
  other: FourTableSourceRow[]
  account_list: Array<{ code: string; name: string; ending: number }>
  meta?: Record<string, unknown>
}

export function normalizePrefill(raw: unknown): FourTablePrefill {
  const p = (raw ?? {}) as Record<string, unknown>
  const arr = (v: unknown): FourTableSourceRow[] =>
    Array.isArray(v) ? (v as FourTableSourceRow[]) : []
  return {
    cash: arr(p.cash),
    bank: arr(p.bank),
    other: arr(p.other),
    account_list: Array.isArray(p.account_list)
      ? (p.account_list as Array<{ code: string; name: string; ending: number }>)
      : [],
    meta: (p.meta as Record<string, unknown>) ?? {},
  }
}

function currencyLabel(row: FourTableSourceRow): string {
  const c = (row.currency || '').toUpperCase()
  if (!c || c === 'CNY' || c === 'RMB') return '人民币'
  return row.currency || '人民币'
}

/** 构造 E1-2 现金明细行 JSON（USER_FIELDS: id/currency/opening/increase/decrease/fxRate/adjustment/note）。 */
export function buildCashSeedRows(prefill: FourTablePrefill): Record<string, unknown>[] | null {
  const src = prefill.cash
  if (!src.length) return null
  const rows: Record<string, unknown>[] = []
  let usedFixed = false
  for (const r of src) {
    const isCny = currencyLabel(r) === '人民币'
    // 首个人民币行占用 'fixed-rmb'（与 composable 默认行合并）
    const id = isCny && !usedFixed ? 'fixed-rmb' : `cash-ft-${r.code}`
    if (id === 'fixed-rmb') usedFixed = true
    rows.push({
      id,
      currency: currencyLabel(r),
      opening: r.opening,
      increase: r.increase,
      decrease: r.decrease,
      fxRate: isCny ? 1 : 0,
      adjustment: 0,
      note: `四表取数 ${r.code}`,
    })
  }
  return rows
}

/**
 * 构造 E1-3 银行存款明细行 JSON。
 * 1002 叶子 → group=institution（银行机构）；1012 叶子 → group=other（其他货币资金）。
 * section 固定 principal（本金）。财务公司(finance)需用户手工重分类。
 */
export function buildBankSeedRows(prefill: FourTablePrefill): Record<string, unknown>[] | null {
  const bank = prefill.bank
  const other = prefill.other
  if (!bank.length && !other.length) return null
  const mk = (r: FourTableSourceRow, group: string): Record<string, unknown> => ({
    id: `bank-principal-${group}-ft-${r.code}`,
    section: 'principal',
    group,
    bankName: r.name,
    totalLedgerBank: '',
    accountNo: r.code,
    accountType: '',
    opening: r.opening,
    increase: r.increase,
    decrease: r.decrease,
    adjustment: 0,
    statementBalance: 0,
    confirmAmount: 0,
    confirmIndexNo: '',
    statementIndexNo: '',
    reconciliationIndexNo: '',
    restrictedAmount: 0,
    restrictedReason: '',
    interestRate: 0,
    note: `四表取数 ${r.code}`,
    fxCurrency: '人民币',
    fxRate: 1,
    openingFc: 0,
    increaseFc: 0,
    decreaseFc: 0,
    adjustmentFc: 0,
  })
  return [
    ...bank.map(r => mk(r, 'institution')),
    ...other.map(r => mk(r, 'other')),
  ]
}

/** 构造 E1-10 银行账户清单行 JSON。 */
export function buildAccountListSeedRows(prefill: FourTablePrefill): Record<string, unknown>[] | null {
  const src = prefill.account_list
  if (!src.length) return null
  return src.map(r => ({
    id: `acct-ft-${r.code}`,
    bank: r.name,
    accountNo: r.code,
    accountType: '',
    openDate: '',
    accountStatus: '正常',
    closeDate: '',
    openReason: '',
    closeReason: '',
    companyInfoConsistent: '',
    inconsistencyReason: '',
    restrictionStatus: '无',
    openPurpose: '',
    isNewThisPeriod: '',
    isClosedThisPeriod: '',
    hasBookRecord: 'Y',
    checkResult: '',
    reason: '',
  }))
}

function sum(rows: FourTableSourceRow[], field: 'opening' | 'ending'): number {
  return rows.reduce((s, r) => s + (Number(r[field]) || 0), 0)
}

/**
 * 构造 E1 跨 sheet 聚合键种子（供 E1-1 审定表在未打开明细 tab 时也能显示提取数）。
 * 返回 [{ itemId, remark }]。
 */
export function buildCrossSheetSeeds(
  prefill: FourTablePrefill,
): Array<{ itemId: string; remark: string }> {
  const seeds: Array<{ itemId: string; remark: string }> = []
  const push = (itemId: string, val: number) =>
    seeds.push({ itemId, remark: String(val) })

  // 现金 1001
  push('E1-cash-detail-opening-unaudited', sum(prefill.cash, 'opening'))
  push('E1-cash-detail-total-unaudited', sum(prefill.cash, 'ending'))

  // 银行本金 1002（institution）
  const bankOpening = sum(prefill.bank, 'opening')
  const bankEnding = sum(prefill.bank, 'ending')
  push('E1-bank-detail-principal-opening-unaudited', bankOpening)
  push('E1-bank-detail-principal-total-unaudited', bankEnding)
  push('E1-bank-detail-institution-opening-unaudited', bankOpening)
  push('E1-bank-detail-institution-total-unaudited', bankEnding)

  // 其他货币资金 1012（other）
  push('E1-bank-detail-other-opening-unaudited', sum(prefill.other, 'opening'))
  push('E1-bank-detail-other-total-unaudited', sum(prefill.other, 'ending'))

  return seeds
}
