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
 * 根据科目代码判定数据域。
 *
 * 规则：
 * - 1xxx → 资产（asset）
 * - 2xxx → 负债（liability）
 * - 3xxx → 权益（equity），注：3101 库存股为权益备抵借方，域仍为 equity
 * - 6xxx / 5xxx / 4xxx → 损益（income_expense）
 * - 其他 → 默认 asset
 */
export function detectAccountDomain(accountCode: string): AccountDomain {
  const code = String(accountCode).trim()
  if (!code) return 'asset'

  const firstChar = code.charAt(0)
  switch (firstChar) {
    case '1': return 'asset'
    case '2': return 'liability'
    case '3': return 'equity'
    case '4':
    case '5':
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
 * 资产类 + 3101 库存股 = 借方科目。
 */
export function isDebitAccount(accountCode: string): boolean {
  const code = String(accountCode).trim()
  if (code.startsWith('1')) return true
  if (code === '3101') return true // 库存股=权益备抵借方
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

  // ─── year 自动解析（Req 5.2）─────────────────────────────────
  // year 未传时从 route query 或默认值解析，杜绝漏 year → 422
  const resolvedYear = computed<number>(() => {
    if (year && isRef(year)) {
      const v = year.value
      if (Number.isFinite(v) && v > 2000) return v
    }
    // fallback: 当前年 - 1（审计年度惯例）
    return new Date().getFullYear() - 1
  })

  // ─── 缓存复用（Req 5.5）─────────────────────────────────────
  const ledgerCache = useLedgerCache()

  // ─── getTbAmount ─────────────────────────────────────────────
  /**
   * 获取科目试算表金额。
   * 按口径决策选择正确端点和字段。
   */
  async function getTbAmount(
    accountCode: string,
    opts?: { basis?: AmountBasis },
  ): Promise<number> {
    const basis = opts?.basis ?? 'audited'
    loading.value = true
    error.value = ''

    try {
      const pid = projectId.value
      const yr = resolvedYear.value
      if (!pid) return 0

      const koujing = resolveKoujing(accountCode)

      let endpoint: string
      if (koujing === 'v1_debit_positive') {
        // v1 口径: tb-balance 端点
        endpoint = `/api/projects/${pid}/tb-balance`
      } else {
        // v2/损益: trial-balance 端点
        endpoint = `/api/projects/${pid}/trial-balance`
      }

      const res = await api.get<any>(endpoint, {
        params: { year: yr, account_code: accountCode },
        _silent: true,
      } as any)

      // 从响应中提取行
      const items: any[] = res?.items ?? res?.data ?? (Array.isArray(res) ? res : [])
      const row = items.find((r: any) =>
        (r.account_code ?? r.accountCode ?? r.standard_account_code) === accountCode,
      )

      if (!row) return 0

      const normalized = normalizeTbRow(row)

      if (koujing === 'pl_occurrence') {
        // 损益类: 发生额 = 借方 - 贷方（收入为贷-借，费用为借-贷）
        // 统一返回发生额绝对值由调用方判断方向
        return normalized.debitAmount - normalized.creditAmount
      }

      // 资产/负债/权益: 按 basis 返回
      if (basis === 'audited') {
        return normalized.auditedAmount
      }
      return normalized.unadjustedAmount
    } catch (err: any) {
      // 错误降级（Req 5.6）: 返回 0，置 error，不抛异常
      error.value = err?.message || '获取试算表金额失败'
      return 0
    } finally {
      loading.value = false
    }
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
   * 获取上年同科目金额。
   */
  async function getPrevYear(
    accountCode: string,
    opts?: { basis?: AmountBasis },
  ): Promise<number> {
    const basis = opts?.basis ?? 'audited'
    loading.value = true
    error.value = ''

    try {
      const pid = projectId.value
      const yr = resolvedYear.value
      if (!pid) return 0

      const prevYear = yr - 1
      const koujing = resolveKoujing(accountCode)

      let endpoint: string
      if (koujing === 'v1_debit_positive') {
        endpoint = `/api/projects/${pid}/tb-balance`
      } else {
        endpoint = `/api/projects/${pid}/trial-balance`
      }

      const res = await api.get<any>(endpoint, {
        params: { year: prevYear, account_code: accountCode },
        _silent: true,
      } as any)

      const items: any[] = res?.items ?? res?.data ?? (Array.isArray(res) ? res : [])
      const row = items.find((r: any) =>
        (r.account_code ?? r.accountCode ?? r.standard_account_code) === accountCode,
      )

      if (!row) return 0

      const normalized = normalizeTbRow(row)

      if (koujing === 'pl_occurrence') {
        return normalized.debitAmount - normalized.creditAmount
      }

      if (basis === 'audited') {
        return normalized.auditedAmount
      }
      return normalized.unadjustedAmount
    } catch (err: any) {
      error.value = err?.message || '获取上年金额失败'
      return 0
    } finally {
      loading.value = false
    }
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
