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
  dateFrom: string
  dateTo: string
  auxType: string
  auxCode: string
  balanceTab: string
}

/**
 * 将穿透状态写入 URL query（不产生历史记录堆积）
 */
export function useLedgerUrlSync() {
  const router = useRouter()
  const route = useRoute()

  function syncToUrl(state: Partial<LedgerUrlState>) {
    const query: Record<string, string> = {}

    // 保留现有的 year/import 等 query
    if (route.query.year) query.year = String(route.query.year)

    // 只写入非空值
    if (state.level && state.level !== 'balance') query.level = state.level
    if (state.account) query.account = state.account
    if (state.voucherNo) query.voucher = state.voucherNo
    if (state.voucherDate) query.voucherDate = state.voucherDate
    if (state.dateFrom) query.dateFrom = state.dateFrom
    if (state.dateTo) query.dateTo = state.dateTo
    if (state.auxType) query.auxType = state.auxType
    if (state.auxCode) query.auxCode = state.auxCode
    if (state.balanceTab && state.balanceTab !== 'account') query.balanceTab = state.balanceTab

    router.replace({ query })
  }

  function readFromUrl(): LedgerUrlState {
    return {
      level: (route.query.level as string) || 'balance',
      account: (route.query.account as string) || '',
      voucherNo: (route.query.voucher as string) || '',
      voucherDate: (route.query.voucherDate as string) || '',
      dateFrom: (route.query.dateFrom as string) || '',
      dateTo: (route.query.dateTo as string) || '',
      auxType: (route.query.auxType as string) || '',
      auxCode: (route.query.auxCode as string) || '',
      balanceTab: (route.query.balanceTab as string) || 'account',
    }
  }

  return { syncToUrl, readFromUrl }
}
