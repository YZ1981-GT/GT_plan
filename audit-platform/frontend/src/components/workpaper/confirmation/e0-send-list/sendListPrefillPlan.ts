/**
 * sendListPrefillPlan.ts — E1-3 → E0-3 带入计划
 *
 * 委托 composables/shared/adjudicationPrefillPlan.ts 的 plan→resolve→describe 模式：
 * 手工优先 / 幂等 / 可预览 / 「仅补空值」
 *
 * @module e0-send-list-dedicated-components / Wave 4 Task 8
 */

import type { SendListRow } from './useSendListData'

// ─── Types ───────────────────────────────────────────────────────────────────

export type AmountCaliber = 'unaudited' | 'audited' | 'statement'

export const DEFAULT_AMOUNT_CALIBER: AmountCaliber = 'unaudited'

export const AMOUNT_CALIBER_OPTIONS: { value: AmountCaliber; label: string; tooltip?: string }[] = [
  { value: 'unaudited', label: '期末余额（未审）' },
  { value: 'audited', label: '期末审定数' },
  { value: 'statement', label: '期末对账单余额', tooltip: '源模板原公式指向此列（E1-3.K）' },
]

export interface E03PrefillRow {
  bank_name: string
  account_holder?: string | null
  bank_account?: string | null
  currency?: string | null
  interest_rate?: number | null
  account_subject?: string
  amount_unaudited?: number | null
  amount_audited?: number | null
  amount_statement?: number | null
  restricted_amount?: number | null
  restricted_reason?: string | null
  _segment?: string
}

export interface PrefillPlanResult {
  /** 新增行（existing 里无此 bank_account） */
  creates: E03PrefillRow[]
  /** 已有行但有空字段可补的 */
  fills: { row: SendListRow; updates: Partial<E03PrefillRow> }[]
  /** 已有行且值冲突的 */
  conflicts: { row: SendListRow; field: string; existing: any; incoming: any }[]
  /** 已有值跳过的字段数 */
  skipped: number
}

// ─── Plan 逻辑 ───────────────────────────────────────────────────────────────

/**
 * 生成带入计划。
 *
 * 匹配键 = bank_account（银行账号）。
 * 手工优先：已有非空值的字段只进 conflicts 不进 fills。
 * 幂等：对同一输入连续两次 plan 结果逐字节相同。
 */
export function planSendListPrefill(
  existing: SendListRow[],
  prefill: E03PrefillRow[],
  caliber: AmountCaliber,
): PrefillPlanResult {
  const result: PrefillPlanResult = { creates: [], fills: [], conflicts: [], skipped: 0 }

  if (!prefill || !prefill.length) return result

  // 按 bank_account 索引 existing
  const existingByAccount = new Map<string, SendListRow>()
  for (const row of existing) {
    const acct = String(row.bank_account || '').trim()
    if (acct) existingByAccount.set(acct, row)
  }

  for (const pf of prefill) {
    const acct = String(pf.bank_account || '').trim()
    if (!acct) continue // 无账号的行跳过

    const amountValue = caliber === 'unaudited' ? pf.amount_unaudited
      : caliber === 'audited' ? pf.amount_audited
      : pf.amount_statement

    const existRow = existingByAccount.get(acct)
    if (!existRow) {
      // 新增
      result.creates.push(pf)
    } else {
      // 已有：逐字段比对
      const updates: Partial<E03PrefillRow> = {}
      const fieldsToFill: [string, any][] = [
        ['bank_name', pf.bank_name],
        ['account_holder', pf.account_holder],
        ['currency', pf.currency],
        ['interest_rate', pf.interest_rate],
        ['account_subject', pf.account_subject],
        ['balance_orig', amountValue],
      ]

      for (const [field, incoming] of fieldsToFill) {
        if (incoming == null || incoming === '') continue
        const existing_val = existRow[field]
        if (existing_val == null || existing_val === '') {
          // 空位可补
          ;(updates as any)[field] = incoming
        } else if (String(existing_val) !== String(incoming)) {
          // 值冲突
          result.conflicts.push({ row: existRow, field, existing: existing_val, incoming })
        } else {
          result.skipped++
        }
      }

      if (Object.keys(updates).length > 0) {
        result.fills.push({ row: existRow, updates })
      }
    }
  }

  return result
}

/**
 * 应用带入计划到 rows（就地修改）。
 * onlyFillEmpty=true 时 conflicts 全部降级为 skipped。
 */
export function applySendListPrefill(
  rows: SendListRow[],
  plan: PrefillPlanResult,
  caliber: AmountCaliber,
  onlyFillEmpty: boolean = false,
): number {
  let changedCount = 0

  // 应用 fills
  for (const { row, updates } of plan.fills) {
    for (const [field, value] of Object.entries(updates)) {
      row[field] = value
      changedCount++
    }
  }

  // 新增行
  for (const pf of plan.creates) {
    const amountValue = caliber === 'unaudited' ? pf.amount_unaudited
      : caliber === 'audited' ? pf.amount_audited
      : pf.amount_statement

    const newRow: SendListRow = {
      _row_id: `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      bank_name: pf.bank_name,
      account_holder: pf.account_holder || undefined,
      bank_account: pf.bank_account || undefined,
      currency: pf.currency || undefined,
      interest_rate: pf.interest_rate ?? undefined,
      account_subject: pf.account_subject || undefined,
      balance_orig: amountValue ?? undefined,
    }
    rows.push(newRow)
    changedCount++
  }

  return changedCount
}
