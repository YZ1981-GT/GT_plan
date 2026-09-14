/**
 * sendListScopeChecks.ts — E0-3 函证范围完整性红线（只读派生，不阻断保存）
 *
 * 源模板明文要求「所有银行账户全部函证（包括零余额账户和在本期内注销的账户）」
 * （E0A 程序 1 / E0-1!O28 / 回函情况汇编编制说明 2），未函证的必须记录理由。
 *
 * Property 26: skip-on-missing / 无 NaN/Infinity
 * Property 27: 阈值不写死，只从 ctx 取
 *
 * @module e0-send-list-dedicated-components / Wave 4 Task 18
 */

import type { SendListRow } from './useSendListData'
import type { ConsistencyItem } from './sendListConsistency'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface SendScopeContext {
  /** 审计期间起始 */
  periodStart: string
  /** 审计期间结束（报表截止日） */
  periodEnd: string
  /** 重要性水平（优先取 B15），缺省 → 「发生额大余额小」项 skip */
  materiality?: number | null
  /** 账号 → 本期发生额（来自 E1-3；取不到该账号即 undefined，绝不填 0） */
  turnoverByAccount?: Record<string, number>
}

// ─── 主入口 ──────────────────────────────────────────────────────────────────

/**
 * 三条红线（全部 skip-on-missing、只读、不阻断保存）：
 * 1. 零余额未函证且无理由 → error
 * 2. 本期内注销未函证且无理由 → error
 * 3. 发生额 ≥ 重要性水平 且 余额 < 重要性水平 且未函证 → warning
 */
export function checkSendScopeCompleteness(
  rows: readonly SendListRow[],
  ctx: SendScopeContext | null,
): ConsistencyItem[] {
  if (!ctx || !rows.length) {
    return [{ id: 'scope-skip', level: 'skip', rule: '完整性红线', label: '上下文不可得，跳过' }]
  }

  const items: ConsistencyItem[] = []
  const periodEnd = parseDate(ctx.periodEnd)
  const periodStart = parseDate(ctx.periodStart)

  for (const row of rows) {
    // 只检查未函证的行
    if (row.is_confirm === '是') continue

    const acct = String(row.bank_account || '').trim()
    const hasReason = Boolean(String(row.remark || '').trim())
    const balance = toFiniteNumber(row.balance_orig)

    // R1: 零余额未函证且无理由
    if (balance === 0 && !hasReason) {
      items.push({
        id: `scope-zero-${acct || row._row_id}`,
        level: 'error',
        rule: '零余额账户',
        label: `账号 ${acct || '(未填)'} 余额为零，未纳入函证且未记录理由`,
        bankAccount: acct || undefined,
        refs: ['E0A 程序 1', 'E0-1!O28'],
      })
    }

    // R2: 本期内注销（终止日期在期间内）
    const endDateStr = String(row.end_date || '').trim()
    if (endDateStr && periodStart && periodEnd) {
      const endDate = parseDate(endDateStr)
      if (endDate && endDate >= periodStart && endDate <= periodEnd && !hasReason) {
        items.push({
          id: `scope-closed-${acct || row._row_id}`,
          level: 'error',
          rule: '本期内注销账户',
          label: `账号 ${acct || '(未填)'} 终止日期 ${endDateStr} 在审计期间内，未函证且未记录理由`,
          bankAccount: acct || undefined,
          refs: ['E0A 程序 1', '回函情况汇编编制说明 2'],
        })
      }
    }

    // R3: 发生额大余额小
    if (ctx.materiality != null && ctx.turnoverByAccount && acct) {
      const turnover = ctx.turnoverByAccount[acct]
      if (turnover !== undefined) {
        if (
          turnover >= ctx.materiality &&
          balance !== null &&
          balance < ctx.materiality &&
          !hasReason
        ) {
          items.push({
            id: `scope-turnover-${acct}`,
            level: 'warning',
            rule: '发生额较大但余额较小',
            label: `账号 ${acct} 发生额 ${turnover.toFixed(2)} ≥ 重要性水平，余额 ${balance.toFixed(2)} 较小，建议纳入函证`,
            bankAccount: acct,
            refs: ['回函情况汇编编制说明 2'],
          })
        }
      }
      // turnover 不可得 → 该项 skip（不拿 0 当发生额）
    }
  }

  return items
}

/** 未函证账户清单（供跳转提示） */
export function unconfirmedAccounts(rows: readonly SendListRow[]): SendListRow[] {
  return rows.filter(r => r.is_confirm !== '是') as SendListRow[]
}

// ─── 工具 ────────────────────────────────────────────────────────────────────

function parseDate(s: string | null | undefined): Date | null {
  if (!s) return null
  const d = new Date(s)
  return isNaN(d.getTime()) ? null : d
}

function toFiniteNumber(v: any): number | null {
  if (v == null || v === '') return null
  const n = Number(String(v).replace(/,/g, ''))
  return Number.isFinite(n) ? n : null
}
