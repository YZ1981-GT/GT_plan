/**
 * useAuditData — 统一取数 SDK composable
 *
 * Feature: platform-global-hardening
 *
 * 收敛「审定数/未审数/科目余额/账龄/序时账/上年数」取数，
 * 内置 year 解析、字段归一化、口径决策、缓存复用、错误降级。
 *
 * 设计要点：
 * - year 未传时从 useAuditContext 解析，调用方无需手传（杜绝漏 year → 422）
 * - 字段归一化层集中一处（debit_amount ?? debitAmount ?? debit 范式）
 * - 三口径按数据域返回（resolveKoujing），不强制统一
 * - getLedgerEntries 委托 useLedgerCache，命中缓存不重复拉取
 * - 所有方法 try/catch，失败返回降级值 + 置 error，绝不抛未捕获异常
 * - 请求带 {_silent:true} 抑制全局 404 弹窗
 *
 * Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
 */
import { ref, computed, type Ref, isRef } from 'vue'
import { api } from '@/services/apiProxy'
import { fetchTrialBalanceRows, tbSumUnder } from '@/services/trialBalanceRows'
import { useLedgerCache, type LedgerCacheEntry } from '@/composables/useLedgerCache'
import type { AgingBand } from '@/composables/useAgingConfig'

// ─── Types ─────────────────────────────────────────────────────────────────────

export type AmountBasis = 'audited' | 'unadjusted'

/**
 * 三种取数口径：
 * - v1_debit_positive: 借正贷负（tb_balance 原始口径）
 * - v2_positive: 正数口径（trial_balance 审定汇总）
 * - pl_occurrence: 损益发生额（从序时账/tb_ledger 取）
 */
export type Koujing = 'v1_debit_positive' | 'v2_positive' | 'pl_occurrence'

/** 科目数据域 */
export type AccountDomain = 'asset' | 'liability' | 'equity' | 'income_expense'

export interface UseAuditDataReturn {
  getTbAmount(accountCode: string, opts?: { basis?: AmountBasis }): Promise<number>
  getAging(subject: string): Promise<AgingBand[]>
  getLedgerEntries(opts?: { accountCode?: string }): Promise<LedgerCacheEntry[]>
  getPrevYear(accountCode: string, opts?: { basis?: AmountBasis }): Promise<number>
  loading: Ref<boolean>
  error: Ref<string>
}

// ─── 字段归一化层（Task 7.2） ──────────────────────────────────────────────────

/**
 * 归一化试算表行数据，屏蔽后端字段名差异。
 * 集中一处别名归一：debit_amount ?? debitAmount ?? debit 等。
 *
 * Requirements: 5.3
 */
export interface NormalizedTbRow {
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  balance: number
  unadjustedAmount: number
  auditedAmount: number
  ajeAdjustment: number
  direction: string
}

export function normalizeTbRow(raw: Record<string, any>): NormalizedTbRow {
  return {
    accountCode: raw.account_code ?? raw.accountCode ?? raw.standard_account_code ?? raw.code ?? '',
    accountName: raw.account_name ?? raw.accountName ?? raw.name ?? '',
    debitAmount: Number(raw.debit_amount ?? raw.debitAmount ?? raw.debit ?? 0),
    creditAmount: Number(raw.credit_amount ?? raw.creditAmount ?? raw.credit ?? 0),
    balance: Number(raw.balance ?? raw.ending_balance ?? raw.endingBalance ?? 0),
    unadjustedAmount: Number(raw.unadjusted_amount ?? raw.unadjustedAmount ?? raw.unadjusted ?? 0),
    auditedAmount: Number(raw.audited_amount ?? raw.auditedAmount ?? raw.audited ?? 0),
    ajeAdjustment: Number(raw.aje_adjustment ?? raw.ajeAdjustment ?? raw.aje ?? 0),
    direction: raw.direction ?? raw.debit_credit ?? '',
  }
}

/**
 * 归一化序时账分录行。
 * 复用 useLedgerCache 已有的归一化，此处作为 SDK 统一出口保证稳定语义字段。
 */
export interface NormalizedLedgerEntry {
  voucherDate: string
  voucherNo: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  balance: number
  summary: string
  preparer: string
}

export function normalizeLedgerEntry(raw: Record<string, any>): NormalizedLedgerEntry {
  return {
    voucherDate: raw.voucher_date ?? raw.voucherDate ?? raw.date ?? '',
    voucherNo: raw.voucher_no ?? raw.voucherNo ?? raw.no ?? '',
    accountCode: raw.account_code ?? raw.accountCode ?? raw.code ?? '',
    accountName: raw.account_name ?? raw.accountName ?? raw.name ?? '',
    debitAmount: Number(raw.debit_amount ?? raw.debitAmount ?? raw.debit ?? 0),
    creditAmount: Number(raw.credit_amount ?? raw.creditAmount ?? raw.credit ?? 0),
    balance: Number(raw.balance ?? raw.ending_balance ?? 0),
    summary: raw.summary ?? raw.abstract ?? raw.description ?? '',
    preparer: raw.preparer ?? raw.maker ?? '',
  }
}

// ─── 口径决策（Task 7.3） ───────────────────────────────────────────────────────

/**
 * 根据科目代码判定数据域（现行企业会计准则科目表编码，与试算表 `standard_account_code`、
 * 报表公式 `TB('4001')` 同一套）。
 *
 * 规则：
 * - 1xxx → 资产（asset）
 * - 2xxx → 负债（liability）
 * - 3xxx → 共同类（衍生工具 3101 / 套期工具 3201 …，余额方向不定）→ 按 asset 取借正贷负余额
 * - 4xxx → 所有者权益（equity），注：4201 库存股为权益备抵借方，域仍为 equity
 * - 5xxx → 成本类（生产成本 / 制造费用 / 研发支出，借方余额）→ 按 asset 取余额
 * - 6xxx → 损益（income_expense）
 * - 其他 → 默认 asset
 *
 * 🔴 2026-10-24 前按旧制科目表判（3xxx 权益、4xxx/5xxx 损益）⇒ 4001 实收资本被当成损益取发生额、
 * 3101（现行为衍生工具）被当成库存股（spec formula-fetch-followup-defect-closure R1.4 触类旁通）。
 */
export function detectAccountDomain(accountCode: string): AccountDomain {
  const code = String(accountCode).trim()
  if (!code) return 'asset'

  const firstChar = code.charAt(0)
  switch (firstChar) {
    case '1': return 'asset'
    case '2': return 'liability'
    case '3': return 'asset'
    case '4': return 'equity'
    case '5': return 'asset'
    case '6': return 'income_expense'
    default: return 'asset'
  }
}

/**
 * 按数据域解析取数口径。
 *
 * 铁律：
 * - 资产：期末=期初+借-贷，v1 借正贷负 源自 tb_balance
 * - 负债/权益：期末=期初+贷-借，v1 借正贷负 + 审定汇总 v2 正数
 * - 损益类：取发生额（pl_occurrence），不取余额
 *
 * 口径按数据域返回，不强制统一为单一口径。
 *
 * Requirements: 5.4
 */
export function resolveKoujing(accountCode: string): Koujing {
  const domain = detectAccountDomain(accountCode)
  switch (domain) {
    case 'asset':
      // 资产类余额: v1 借正贷负
      return 'v1_debit_positive'
    case 'liability':
    case 'equity':
      // 负债/权益类余额: v2 正数口径
      return 'v2_positive'
    case 'income_expense':
      // 损益类: 取发生额
      return 'pl_occurrence'
    default:
      return 'v1_debit_positive'
  }
}

/**
 * 判断是否为借方科目（余额方向为借方）。
 * 资产类 + 成本类（5xxx）+ 4201 库存股 = 借方科目。
 */
export function isDebitAccount(accountCode: string): boolean {
  const code = String(accountCode).trim()
  if (code.startsWith('1') || code.startsWith('5')) return true
  if (code.startsWith('4201')) return true // 库存股=权益备抵借方（含明细子目）
  return false
}

// ─── Composable 主体（Task 7.1 + 7.4） ─────────────────────────────────────────

/**
 * 统一取数 SDK。
 *
 * @param projectId - 项目 ID（响应式）
 * @param year - 审计年度（响应式，可选）。未传时从 route/projectStore 解析。
 *
 * Requirements: 5.1, 5.2, 5.5, 5.6
 */
export function useAuditData(
  projectId: Ref<string>,
  year?: Ref<number>,
): UseAuditDataReturn {
  const loading = ref(false)
  const error = ref('')

  // ─── year ───────────────────────────────────────────────────────
  // 传了合法年度就带上；没传 / 不合法 ⇒ 不带，后端按项目审计年度取（项目没填 ⇒ 422，按失败处理）。
  // 不按日历猜（原先兜底「今年 − 1」，2025 年度项目在 2027 年取的是 2026 的数）。
  const resolvedYear = computed<number | null>(() => {
    if (year && isRef(year)) {
      const v = Number(year.value)
      if (Number.isInteger(v) && v > 2000 && v <= 2100) return v
    }
    return null
  })

  // ─── 缓存复用（Req 5.5）─────────────────────────────────────
  const ledgerCache = useLedgerCache()

  /** 试算表某科目（含其下明细科目）金额；取不到 ⇒ 置 error 并返回 0。 */
  async function tbAmount(
    accountCode: string,
    field: 'audited_amount' | 'unadjusted_amount' | 'prior_audited_amount',
    failMessage: string,
  ): Promise<number> {
    loading.value = true
    error.value = ''
    try {
      const pid = projectId.value
      if (!pid) return 0
      const { rows } = await fetchTrialBalanceRows(pid, {
        year: resolvedYear.value,
        accountPrefix: accountCode,
        includePrior: field === 'prior_audited_amount',
      })
      // 与报表 TB('1002') 同口径：科目及其下明细科目之和（试算表每个余额表叶子只归一个标准科目，不重复）
      const amount = tbSumUnder(rows, accountCode, field)
      if (amount == null) {
        error.value = `试算表没有科目 ${accountCode} 的${field === 'prior_audited_amount' ? '上年审定数' : '金额'}`
        return 0
      }
      return amount
    } catch (err: any) {
      // 错误降级（Req 5.6）: 返回 0，置 error，不抛异常
      error.value = err?.message || failMessage
      return 0
    } finally {
      loading.value = false
    }
  }

  // ─── getTbAmount ─────────────────────────────────────────────
  /**
   * 获取科目试算表金额（正数口径，方向见试算表 direction）。
   * 损益类是单边发生额（收入取贷方、费用取借方，与试算表 / 报表同口径）；不再用「借 − 贷」——
   * 含年末结转分录时两侧相等，恒为 0（见 `services/trialBalanceRows.ts`）。
   */
  async function getTbAmount(
    accountCode: string,
    opts?: { basis?: AmountBasis },
  ): Promise<number> {
    const basis = opts?.basis ?? 'audited'
    return tbAmount(accountCode, basis === 'audited' ? 'audited_amount' : 'unadjusted_amount', '获取试算表金额失败')
  }

  // ─── getAging ────────────────────────────────────────────────
  /**
   * 获取账龄段配置。
   * 委托 useAgingConfig API 端点。
   */
  async function getAging(subject: string): Promise<AgingBand[]> {
    loading.value = true
    error.value = ''

    try {
      const pid = projectId.value
      if (!pid) return []

      const res = await api.get<any>(`/api/projects/${pid}/aging/config`, {
        _silent: true,
      } as any)

      const segments: any[] = res?.effective_segments ?? res?.segments ?? []
      // 转换 segments → bands（简化版，与 useAgingConfig.segmentsToBands 对齐）
      const THREE_PERIOD_SUBJECTS = new Set(['D2', 'K1', 'K3', 'G5'])
      const isThreePeriod = THREE_PERIOD_SUBJECTS.has(subject)

      return segments.map((seg: any) => ({
        key: seg.key,
        label: seg.label,
        priorField: `agingPrior.${seg.key}`,
        currentField: isThreePeriod ? `agingCurrent.${seg.key}` : '',
        auditedField: `agingAudited.${seg.key}`,
      }))
    } catch (err: any) {
      error.value = err?.message || '获取账龄配置失败'
      return []
    } finally {
      loading.value = false
    }
  }

  // ─── getLedgerEntries（缓存复用 Req 5.5）───────────────────────
  /**
   * 获取序时账分录。
   * 直接委托 useLedgerCache().getEntries 命中缓存不重复拉取。
   */
  async function getLedgerEntries(
    opts?: { accountCode?: string },
  ): Promise<LedgerCacheEntry[]> {
    loading.value = true
    error.value = ''

    try {
      const pid = projectId.value
      const yr = resolvedYear.value
      if (!pid) return []
      if (yr == null) {
        // 序时账按年度取，没有年度不猜（原先兜底「今年 − 1」）
        error.value = '未设置审计年度，请先在项目基本信息中填写'
        return []
      }

      // 委托 useLedgerCache，命中缓存不重复拉取
      const entries = await ledgerCache.getEntries(pid, yr)

      // 按 accountCode 过滤（如指定）
      if (opts?.accountCode) {
        return entries.filter((e) => e.accountCode === opts.accountCode)
      }
      return entries
    } catch (err: any) {
      error.value = err?.message || '获取序时账分录失败'
      return []
    } finally {
      loading.value = false
    }
  }

  // ─── getPrevYear ─────────────────────────────────────────────
  /**
   * 获取上年同科目审定数。上年来源与报表上期同一（同项目上年试算表，否则唯一认定的上年项目；
   * 后端 `prior_year_context`）——不再拿本项目的「年度 − 1」去取（每个项目只有本年试算表，恒取不到）。
   * 上年只有审定数，`basis` 不区分。
   */
  async function getPrevYear(
    accountCode: string,
    _opts?: { basis?: AmountBasis },
  ): Promise<number> {
    return tbAmount(accountCode, 'prior_audited_amount', '获取上年金额失败')
  }

  return {
    getTbAmount,
    getAging,
    getLedgerEntries,
    getPrevYear,
    loading,
    error,
  }
}
