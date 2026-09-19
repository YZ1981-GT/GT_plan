/**
 * e1BankAccountPrefill — E1 货币资金「账户级取数」归一与种子构造（纯函数）
 *
 * 后端 `_e1_monetary_fund.py` 的 `_build_account_prefill` 输出
 * `html_data.account_prefill`（真源 = `tb_aux_balance` 的 `aux_type='银行账户'` 维度）：
 *
 *     {
 *       accounts: { bank: [...], other: [...], finance_co: [...], unassigned: [...] },
 *       reconcile: { bank: { account_sum, leaf_sum, diff, ok } },
 *       meta: { source, account_count, parsed_level_dist }
 *     }
 *
 * 为什么需要它（而不是复用 `e1FourTablePrefill` 的叶子口径）：客户的
 * `1002 银行存款` 在 `tb_balance` 里**不分户**（叶子恒 1 行），而 E1-3 要逐户列示、
 * E1-10 要做账户完整性核对 ⇒ 账户级明细的唯一来源是 aux 维度。
 *
 * ─── 三条硬约束（每条都对应一次实证）─────────────────────────────────────────
 *
 * 1. **行 id 与叶子口径不撞键**（Property 7）。叶子口径用 `-ft-{科目码}`，
 *    本模块一律用 `-acct-{账号}` / `acct-a-{账号}`。撞键会让两种口径的种子互相覆盖。
 *
 * 2. **原币金额与汇率不得由本位币反推**（Property 34）。`tb_aux_balance` 只有
 *    `opening_fc` 一列且 `aux_type='银行账户'` 下**全库为 NULL**，**无 `closing_fc`、
 *    无汇率列**。但要区分两种情形：
 *    - 币种为 CNY/RMB/空 ⇒ 「原币 == 本位币、汇率 = 1」是**恒等事实不是推断**，
 *      可以下发（见约束 3 为什么必须下发）；
 *    - 币种为非本位币 ⇒ 原币与汇率**留 0** 且在 `note` 里显式提示需手工录入。
 *
 * 3. 🔴 **`multi` 版必须下发原币列，否则金额被静默抹成 0**（本模块落地时实测）。
 *    `useE1BankDetail.recalcRow` 在 `variant === 'multi'` 下把
 *    `opening/increase/decrease/ending/adjustment/audited` **全部由
 *    `原币 × fxRate` 派生**；若原币列留空（0）而只给本位币列，recalc 会把我们从
 *    aux 取到的本位币金额覆盖成 0 —— 界面显示「有账户、金额全 0」，比取不到更坏。
 *    故 CNY 账户在 `multi` 版下发 `fxRate=1` + `openingFc=opening` 等恒等值；
 *    非 CNY 账户只能留 0（数据事实），但 `note` 会写明原因，不静默。
 *
 * ─── variant 分流 ───────────────────────────────────────────────────────────
 *
 * E1-3 有两张同名尾码的 sheet（`(仅人民币)E1-3` / `(人民币及外币)E1-3`），宿主按
 * `sheetName` 分流成 `rmb` / `multi`，**两版共用同一持久化键 `E1-bank-detail-rows`**
 * （行模型带 variant 相关字段区分）。故：
 * - 两版**账户条数必须相同**（外币账户在 rmb 版不丢弃，只是不带原币字段）；
 * - `rmb` 版不下发 `fxCurrency`（composable 缺字段时回落 `'人民币'`），也不下发原币列
 *   （rmb 版 recalcRow 不走 fx 分支，本位币列是权威）。
 *
 * spec: .kiro/specs/e-cycle-extraction-formula-and-disclosure-completion/ (Task 7)
 * Requirements: 1.7, 1.9, 1.10, 2.3, 2.4, 11.3
 */

/** 后端 `BankAccountRow.as_dict()` 的逐字契约（snake_case，勿改名）。 */
export interface E1AccountRow {
  account_code: string
  account_no: string
  bank_name: string
  currency: string
  opening: number
  debit: number
  credit: number
  closing: number
  slot: string | null
  source: string
  parsed_level: number
  row_count: number
}

/** 单槽勾稽结果（后端 `check_accounts_vs_leaves`）。 */
export interface E1AccountReconcile {
  account_sum: number
  leaf_sum: number
  diff: number
  ok: boolean
}

export interface E1AccountPrefill {
  accounts: {
    bank: E1AccountRow[]
    other: E1AccountRow[]
    finance_co: E1AccountRow[]
    unassigned: E1AccountRow[]
  }
  reconcile: Record<string, E1AccountReconcile>
  meta: {
    source: string
    account_count: number
    parsed_level_dist: Record<string, number>
  }
}

/** E1-3 的两个 variant（与宿主 `sheetName` 分流一致）。 */
export type E1BankVariant = 'rmb' | 'multi'

/**
 * 账户级槽 → E1-3 的 `group` 值。
 *
 * 🔴 `group` 取值域由 `useE1BankDetail.GROUPS` 定义 = `institution | finance | other`，
 * **不是** 槽名（槽名是 `bank`/`other`/`finance_co`）。`finance_co → finance`
 * 让存放财务公司款项自动归组，不要求审计师手工重分类（R2.3）。
 */
export const ACCOUNT_SLOT_TO_GROUP: Readonly<Record<string, string>> = Object.freeze({
  bank: 'institution',
  finance_co: 'finance',
  other: 'other',
})

/** 账户级槽的遍历顺序（决定种子行顺序，与后端 `_ACCOUNT_SLOT_KEYS` 同序）。 */
export const ACCOUNT_SLOT_ORDER: readonly string[] = Object.freeze([
  'bank',
  'other',
  'finance_co',
])

function num(v: unknown): number {
  const n = typeof v === 'number' ? v : parseFloat(String(v ?? ''))
  return Number.isFinite(n) ? n : 0
}

function str(v: unknown): string {
  return v == null ? '' : String(v)
}

function normalizeRow(raw: unknown): E1AccountRow {
  const r = (raw ?? {}) as Record<string, unknown>
  return {
    account_code: str(r.account_code),
    account_no: str(r.account_no),
    bank_name: str(r.bank_name),
    currency: str(r.currency),
    opening: num(r.opening),
    debit: num(r.debit),
    credit: num(r.credit),
    closing: num(r.closing),
    slot: r.slot == null ? null : String(r.slot),
    source: str(r.source),
    parsed_level: num(r.parsed_level) || 3,
    row_count: num(r.row_count) || 1,
  }
}

function normalizeReconcile(raw: unknown): Record<string, E1AccountReconcile> {
  const src = (raw ?? {}) as Record<string, unknown>
  const out: Record<string, E1AccountReconcile> = {}
  for (const [slot, v] of Object.entries(src)) {
    const o = (v ?? {}) as Record<string, unknown>
    out[slot] = {
      account_sum: num(o.account_sum),
      leaf_sum: num(o.leaf_sum),
      diff: num(o.diff),
      ok: o.ok === true,
    }
  }
  return out
}

/**
 * 归一 `html_data.account_prefill`。缺字段一律按空处理，**不抛**。
 *
 * 🔴 「后端整体未注入」与「aux 无数据」都归一成各槽 `[]` —— 判「能否用账户级口径」
 * 一律用 `hasAccountData()`，不要自己判 `undefined`（后端空态也给全键，见
 * `_empty_account_prefill` 的注释）。
 */
export function normalizeAccountPrefill(raw: unknown): E1AccountPrefill {
  const p = (raw ?? {}) as Record<string, unknown>
  const acc = (p.accounts ?? {}) as Record<string, unknown>
  const list = (v: unknown): E1AccountRow[] =>
    Array.isArray(v) ? v.map(normalizeRow) : []
  const meta = (p.meta ?? {}) as Record<string, unknown>
  const dist = (meta.parsed_level_dist ?? {}) as Record<string, unknown>
  const distOut: Record<string, number> = {}
  for (const [k, v] of Object.entries(dist)) distOut[k] = num(v)
  return {
    accounts: {
      bank: list(acc.bank),
      other: list(acc.other),
      finance_co: list(acc.finance_co),
      unassigned: list(acc.unassigned),
    },
    reconcile: normalizeReconcile(p.reconcile),
    meta: {
      source: str(meta.source),
      account_count: num(meta.account_count),
      parsed_level_dist: distOut,
    },
  }
}

/** 已归属到槽的账户（不含 `unassigned`），按 `ACCOUNT_SLOT_ORDER` 展开。 */
export function assignedAccounts(
  p: E1AccountPrefill,
): Array<{ slot: string; row: E1AccountRow }> {
  const out: Array<{ slot: string; row: E1AccountRow }> = []
  for (const slot of ACCOUNT_SLOT_ORDER) {
    const rows = (p.accounts as Record<string, E1AccountRow[]>)[slot] || []
    for (const row of rows) out.push({ slot, row })
  }
  return out
}

/** 是否有可用的账户级数据（决定「账户级优先 or 退回叶子口径」）。 */
export function hasAccountData(p: E1AccountPrefill): boolean {
  return assignedAccounts(p).length > 0 || p.accounts.unassigned.length > 0
}

/** 币种是否本位币（空串按本位币处理 —— aux 侧 `currency_code` 默认 `CNY`）。 */
export function isBaseCurrency(currency: string): boolean {
  const c = (currency || '').trim().toUpperCase()
  return c === '' || c === 'CNY' || c === 'RMB' || currency.trim() === '人民币'
}

/** 币种展示标签（与 `e1FourTablePrefill.currencyLabel` 同口径）。 */
export function currencyLabelOf(currency: string): string {
  return isBaseCurrency(currency) ? '人民币' : currency.trim()
}

/** 非本位币账户在 `multi` 版的提示（不静默留 0）。 */
export const FOREIGN_FC_HINT = '原币金额与汇率需手工录入（四表无原币数据）'

function seedNote(row: E1AccountRow, foreign: boolean): string {
  const base = `账户级取数 ${row.account_no || row.account_code}`
  const parts = [base]
  if (row.row_count > 1) parts.push(`同账号 ${row.row_count} 笔已合并`)
  if (row.parsed_level >= 3) parts.push('账号取自辅助项名称（未解析出银行名）')
  if (foreign) parts.push(FOREIGN_FC_HINT)
  return parts.join('；')
}

/** 行 id 去重（同一账号在不同槽/重复出现时补序号，保证 seed 内唯一）。 */
function uniqueId(base: string, used: Set<string>): string {
  if (!used.has(base)) {
    used.add(base)
    return base
  }
  let i = 2
  while (used.has(`${base}-${i}`)) i += 1
  const id = `${base}-${i}`
  used.add(id)
  return id
}

/**
 * 构造 E1-3 银行存款明细种子行（账户级口径）。
 *
 * 字段对齐 `useE1BankDetail.USER_FIELDS`；`section` 固定 `principal`（本金段）。
 * 账户为空时返 `null`（宿主据此退回叶子口径 `buildBankSeedRows`）。
 *
 * 🔴 `variant` 影响**字段集**不影响**条数** —— 两版账户条数必须相同。
 */
export function buildBankSeedRowsFromAccounts(
  p: E1AccountPrefill,
  variant: E1BankVariant = 'rmb',
): Record<string, unknown>[] | null {
  const items = assignedAccounts(p)
  if (!items.length) return null
  const used = new Set<string>()
  return items.map(({ slot, row }) => {
    const group = ACCOUNT_SLOT_TO_GROUP[slot] || 'other'
    const key = row.account_no || row.account_code
    const id = uniqueId(`bank-principal-${group}-acct-${key}`, used)
    const foreign = !isBaseCurrency(row.currency)
    const base: Record<string, unknown> = {
      id,
      section: 'principal',
      group,
      bankName: row.bank_name,
      totalLedgerBank: '',
      accountNo: row.account_no,
      accountType: '',
      opening: row.opening,
      increase: row.debit,
      decrease: row.credit,
      adjustment: 0,
      statementBalance: 0,
      confirmAmount: 0,
      confirmIndexNo: '',
      statementIndexNo: '',
      reconciliationIndexNo: '',
      restrictedAmount: 0,
      restrictedReason: '',
      interestRate: 0,
      note: seedNote(row, foreign && variant === 'multi'),
    }
    if (variant === 'rmb') {
      // rmb 版：composable 的 recalcRow 不走 fx 分支，本位币列即权威；
      // 不下发 fxCurrency（缺字段时回落 '人民币'）与任何原币列。
      return base
    }
    // multi 版：recalcRow 由「原币 × fxRate」派生本位币列 ⇒ 必须下发原币列，
    // 否则本位币金额被抹成 0（见模块 docstring 约束 3）。
    base.fxCurrency = currencyLabelOf(row.currency)
    if (foreign) {
      // 非本位币：原币与汇率是四表拿不到的数据 ⇒ 留 0，靠 note 提示手工录入。
      base.fxRate = 0
      base.openingFc = 0
      base.increaseFc = 0
      base.decreaseFc = 0
      base.adjustmentFc = 0
    } else {
      // 本位币：「原币 == 本位币、汇率 = 1」是恒等事实，不是反推。
      base.fxRate = 1
      base.openingFc = row.opening
      base.increaseFc = row.debit
      base.decreaseFc = row.credit
      base.adjustmentFc = 0
    }
    return base
  })
}

/**
 * 构造 E1-10 银行账户清单种子行（账户级口径）。
 *
 * 🔴 **保留零余额账户**（Property 6）—— E1-10 是账户完整性核对表，
 * 「本年新开立但期末为 0」的账户恰是体外账户/未入账账户的排查对象。
 * `unassigned` 账户也要进清单（aux 里有账户但科目定位未覆盖，正是要暴露的信号）。
 */
export function buildAccountListSeedRowsFromAccounts(
  p: E1AccountPrefill,
): Record<string, unknown>[] | null {
  const rows: E1AccountRow[] = [
    ...assignedAccounts(p).map(x => x.row),
    ...p.accounts.unassigned,
  ]
  if (!rows.length) return null
  const used = new Set<string>()
  return rows.map(row => {
    const key = row.account_no || row.account_code
    return {
      id: uniqueId(`acct-a-${key}`, used),
      bank: row.bank_name,
      accountNo: row.account_no,
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
    }
  })
}

/** `four_table_prefill.digital` 的源记录（与 `FourTableSourceRow` 同形，最小取用）。 */
export interface E1DigitalSourceRow {
  code: string
  name: string
  currency?: string
  opening: number
  increase: number
  decrease: number
  ending: number
}

/**
 * 构造 E1-4 数字货币明细种子行（叶子口径 —— 数字货币无账户维度）。
 *
 * 🔴 持久化键是 **`E1-digital-rows`**（`E1TabDigitalCurrency.vue` 的 `STORAGE_KEY`），
 * **不是** `E1-digital-detail-rows` —— 后者在全前端零消费方，写进去就是孤儿键。
 *
 * 字段对齐该 Tab 的 `USER_FIELDS`（14 个）；`seq` 由 composable 按下标重排，
 * 这里按 1 起顺序给以便未落库时也能正确显示。
 */
export function buildDigitalSeedRows(
  rows: readonly E1DigitalSourceRow[] | null | undefined,
): Record<string, unknown>[] | null {
  const src = Array.isArray(rows) ? rows : []
  if (!src.length) return null
  return src.map((r, i) => {
    const foreign = !isBaseCurrency(r.currency || '')
    return {
      id: `digi-ft-${r.code}`,
      seq: i + 1,
      bankName: r.name,
      currency: currencyLabelOf(r.currency || ''),
      // 非本位币的汇率四表拿不到 ⇒ 留 0 并在 note 提示（不臆造 1）
      fxRate: foreign ? 0 : 1,
      opening: r.opening,
      increase: r.increase,
      decrease: r.decrease,
      adjustment: 0,
      queryBalance: 0,
      diffReason: '',
      indexNo: '',
      confirmationIndexNo: '',
      note: foreign ? `四表取数 ${r.code}；${FOREIGN_FC_HINT}` : `四表取数 ${r.code}`,
    }
  })
}
