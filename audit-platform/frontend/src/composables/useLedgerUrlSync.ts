/**
 * useLedgerUrlSync — 查账穿透状态 ↔ URL query 双向同步
 *
 * 确保：
 * 1. 每次穿透（余额→序时账→凭证→辅助）都把当前 level/account/voucher 等写入 URL query
 * 2. 页面刷新或新窗口打开时从 URL query 恢复完整穿透现场
 *
 * spec: multi-window-ledger-workbench Phase 1 Task 5
 */
import { type Ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'

export interface LedgerUrlState {
  level: string
  account: string
  voucherNo: string
  voucherDate: string
  /**
   * 凭证字：同日同号可能是几张凭证（四川物流 2025-01-20 的 FY-0012 与 GZ-0012），只有号 + 日期恢复现场时
   * 后端只能列候选（spec voucher-identity-writeback-and-audit-phase 任务 14 实测）。
   * null / 缺省 = 不知道；'' = 凭证字为空的那张（URL 里写成 `voucherType=`）。🔴 '' 不能读回成「不知道」：
   * 每次写 URL 整页按 fullPath 重挂载、从 URL 恢复，选了凭证字为空的候选会又列候选、再选再列。
   */
  voucherType?: string | null
  /** 主体编码：一套账两个主体同日同号同凭证字时靠它区分（四表主体非空，没映射记 default）。'' / 缺省 = 不限 */
  voucherCompany?: string
  dateFrom: string
  dateTo: string
  auxType: string
  auxCode: string
  balanceTab: string
}

/**
 * 穿透状态 → 账簿查询页的 URL query（纯函数，唯一实现）。
 *
 * 页内同步（`syncToUrl`）与站外深链（高级查询结果行「打开」，`components/query/queryResultLinks.ts`）共用，
 * 两处写出的键与 `readFromUrl` 读回的键因此始终一致（advanced-query-linkage-closure 任务 27，ADR-AQL-01）。
 * 只写入非空值；`level = balance`、`balanceTab = account` 是默认值，不写。
 */
export function buildLedgerQuery(state: Partial<LedgerUrlState>, year?: string | number | null): Record<string, string> {
  const query: Record<string, string> = {}
  if (year !== undefined && year !== null && String(year)) query.year = String(year)
  if (state.level && state.level !== 'balance') query.level = state.level
  if (state.account) query.account = state.account
  if (state.voucherNo) query.voucher = state.voucherNo
  if (state.voucherDate) query.voucherDate = state.voucherDate
  if (state.voucherType != null) query.voucherType = state.voucherType // '' 也写：凭证字为空 ≠ 不知道
  if (state.voucherCompany) query.voucherCompany = state.voucherCompany
  if (state.dateFrom) query.dateFrom = state.dateFrom
  if (state.dateTo) query.dateTo = state.dateTo
  if (state.auxType) query.auxType = state.auxType
  if (state.auxCode) query.auxCode = state.auxCode
  if (state.balanceTab && state.balanceTab !== 'account') query.balanceTab = state.balanceTab
  return query
}

/**
 * 将穿透状态写入 URL query（不产生历史记录堆积）
 */
export function useLedgerUrlSync() {
  const router = useRouter()
  const route = useRoute()

  function syncToUrl(state: Partial<LedgerUrlState>) {
    // 保留现有的 year query；其余键只写入非空值
    router.replace({ query: buildLedgerQuery(state, route.query.year ? String(route.query.year) : undefined) })
  }

  function readFromUrl(): LedgerUrlState {
    return {
      level: (route.query.level as string) || 'balance',
      account: (route.query.account as string) || '',
      voucherNo: (route.query.voucher as string) || '',
      voucherDate: (route.query.voucherDate as string) || '',
      voucherType: typeof route.query.voucherType === 'string' ? route.query.voucherType : null,
      voucherCompany: (route.query.voucherCompany as string) || '',
      dateFrom: (route.query.dateFrom as string) || '',
      dateTo: (route.query.dateTo as string) || '',
      auxType: (route.query.auxType as string) || '',
      auxCode: (route.query.auxCode as string) || '',
      balanceTab: (route.query.balanceTab as string) || 'account',
    }
  }

  return { syncToUrl, readFromUrl }
}
