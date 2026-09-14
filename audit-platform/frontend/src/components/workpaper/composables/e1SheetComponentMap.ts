/**
 * E1 sheet 分发真源表 — 宿主 GtE1MonetaryFund.vue 按 currentSheet 的返回值
 * 渲染对应组件。守卫 `e1SheetDispatch.spec.ts` 读宿主源码比对此表，
 * 防止再出现「E1-19 指错组件」的静默失效。
 *
 * @spec e1-orphan-components-wiring — Task 3
 */

/** sheetCode → 期望渲染的组件名 */
export const E1_SHEET_COMPONENT: Record<string, string> = {
  'E1-18': 'E1TabCreditReport',
  'E1-19': 'E1TabCreditCheck',
  'E1-26': 'E1TabCashTxnAnalysis',
  'E1-27': 'E1TabIpoSpecial',
  'E1-28': 'E1TabIpoSpecial',
  'E1-29': 'E1TabBankAccountAnalysis',
  'E1-30': 'E1TabDepositInterestDaily',
  'E1-31': 'E1TabBankFlowReconcile',
  'E1-32': 'E1TabKeyPersonFlow',
}

/** ipoSheetCode 正则只应匹配这些 sheet（无专属组件的通用表） */
export const E1_IPO_GENERIC_SHEETS = ['E1-27', 'E1-28'] as const
