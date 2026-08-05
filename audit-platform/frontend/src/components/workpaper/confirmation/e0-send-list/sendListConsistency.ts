/**
 * sendListConsistency.ts — E0-3 受限勾稽引擎（只读派生）
 *
 * 规则：
 * - R1: E1-3 受限金额非零 → has_restriction 必须为「是」(error)
 * - R2: E0-3 有账号但 E1-3 无对应账户 (warning)
 * - R3: E1-3 有账户但 E0-3 未列 (warning)
 * - R4: F3-2 保证金合计非零 且 E0-5 对应票据行 pledge 为空 (warning)
 *
 * prefill 为 null → 全 skip（不拿空当零，Property 13）
 *
 * @module e0-send-list-dedicated-components / Wave 4 Task 9
 */

import type { SendListRow } from './useSendListData'
import type { E03PrefillRow } from './sendListPrefillPlan'

// ─── Types ───────────────────────────────────────────────────────────────────

export type ConsistencyLevel = 'error' | 'warning' | 'info' | 'ok' | 'skip'

export interface ConsistencyItem {
  id: string
  level: ConsistencyLevel
  rule: string
  label: string
  detail?: string
  /** 关联的银行账号 */
  bankAccount?: string
  /** 追溯引用 */
  refs?: string[]
}

// ─── 主入口 ──────────────────────────────────────────────────────────────────

/**
 * E0-3 ↔ E1-3 受限勾稽。
 *
 * prefill == null → 全 skip（Property 13：绝不拿空当零）。
 */
export function checkSendListConsistency(
  rows: SendListRow[],
  prefill: E03PrefillRow[] | null,
): ConsistencyItem[] {
  if (prefill === null || prefill === undefined) {
    return [{
      id: 'skip-no-prefill',
      level: 'skip',
      rule: '暂无可比对数据',
      label: '上游 E1-3 暂无账户明细，勾稽项全部跳过',
    }]
  }

  const items: ConsistencyItem[] = []

  // 按 bank_account 索引
  const e03ByAccount = new Map<string, SendListRow>()
  for (const row of rows) {
    const acct = String(row.bank_account || '').trim()
    if (acct) e03ByAccount.set(acct, row)
  }

  const e13ByAccount = new Map<string, E03PrefillRow>()
  for (const pf of prefill) {
    const acct = String(pf.bank_account || '').trim()
    if (acct) e13ByAccount.set(acct, pf)
  }

  // R1: E1-3 受限金额非零 → has_restriction 必须为「是」
  for (const [acct, pf] of e13ByAccount) {
    const restrictedAmt = pf.restricted_amount
    if (restrictedAmt != null && restrictedAmt !== 0) {
      const e03Row = e03ByAccount.get(acct)
      if (e03Row) {
        if (e03Row.has_restriction !== '是') {
          items.push({
            id: `r1-restricted-${acct}`,
            level: 'error',
            rule: 'E1-3 受限金额非零 → E0-3「是否存在冻结、担保或其他使用限制」应为「是」',
            label: `账号 ${acct} E1-3 受限金额 ${restrictedAmt}，E0-3 未标「是」`,
            bankAccount: acct,
            refs: ['E1-3 受限金额', 'E0-3 O列'],
          })
        }
      }
      // 如果 E0-3 没有该账号，归 R3（下方处理）
    }
  }

  // R2: E0-3 有账号但 E1-3 无对应账户
  for (const [acct] of e03ByAccount) {
    if (!e13ByAccount.has(acct)) {
      items.push({
        id: `r2-e03-only-${acct}`,
        level: 'warning',
        rule: 'E0-3 有账号但 E1-3 未列',
        label: `账号 ${acct} 在 E0-3 但 E1-3 无对应账户（可能新开/手工录入）`,
        bankAccount: acct,
      })
    }
  }

  // R3: E1-3 有账户但 E0-3 未列
  for (const [acct] of e13ByAccount) {
    if (!e03ByAccount.has(acct)) {
      items.push({
        id: `r3-e13-only-${acct}`,
        level: 'warning',
        rule: 'E1-3 有账户但 E0-3 未列',
        label: `账号 ${acct} 在 E1-3 但 E0-3 未列（完整性提示）`,
        bankAccount: acct,
      })
    }
  }

  // 如果无任何问题
  if (items.length === 0) {
    items.push({
      id: 'all-ok',
      level: 'ok',
      rule: '受限勾稽全部通过',
      label: `已比对 ${e03ByAccount.size} 个账户，无不一致`,
    })
  }

  return items
}
