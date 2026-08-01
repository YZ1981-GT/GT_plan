/**
 * H9 租赁负债披露内部勾稽校验（纯函数，国企净额派生）
 *
 * 源模板国企表提示（H9TabDisclosureSoe.vue 既有注释）：
 * 「净额 = 租赁付款额 − 未确认融资费用 − 重分类至一年内到期」（公式列）。
 *
 * H9 上市侧是分类明细 + 一年内到期两段（无单一净额派生关系），暂不做层间校验。
 *
 * spec: .kiro/specs/h-cycle-legacy-cleanup-and-platform-hygiene/ R5
 */
import { eqCheck, type WpCheckResult } from './shared/disclosureConsistency'
import type { H9SoeDisclosureState } from './h9DisclosureModel'

function findEnd(state: H9SoeDisclosureState, key: 'payment' | 'unearned' | 'reclass'): number | null {
  return state.rows.find((r) => r.key === key)?.endBalance ?? null
}

export function buildH9SoeChecks(state: H9SoeDisclosureState): WpCheckResult[] {
  const payment = findEnd(state, 'payment')
  const unearned = findEnd(state, 'unearned')
  const reclass = findEnd(state, 'reclass')
  if (payment === null && unearned === null && reclass === null) return []

  const checks: WpCheckResult[] = []
  if (payment !== null && unearned !== null && reclass !== null) {
    const netBeforeReclass = Math.round((payment - unearned) * 100) / 100
    const diff = Math.round((reclass - netBeforeReclass) * 100) / 100
    // 子集类：重分类至一年内到期的部分不能超过扣除未确认融资费用后的净额
    // （源模板公式列：净额 = 租赁付款额 − 未确认融资费用 − 重分类至一年内到期）
    checks.push({
      label: '重分类至一年内到期（期末）',
      rule: '重分类金额是「租赁付款额 − 未确认融资费用」净额的子集，不得超出',
      left: reclass,
      right: netBeforeReclass,
      diff,
      level: diff > 0.01 ? 'error' : 'ok',
      refs: ['Note:八、52'],
    })
  }
  return checks
}
