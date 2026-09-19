/**
 * sendListE05Checks.ts — E0-5 专属红线与一函多票分组（只读派生）
 *
 * Property 21: 三方勾稽在数据缺失时全 skip
 * Property 22: 一函多票分组是展示层派生
 * Property 23: 期限阈值可配置且无硬编码月数
 *
 * @module e0-send-list-dedicated-components / Wave 4 Task 16
 */

import type { SendListRow } from './useSendListData'
import type { ConsistencyItem, ConsistencyLevel } from './sendListConsistency'

// ─── 一函多票分组 ────────────────────────────────────────────────────────────

export interface E05IndexGroup {
  indexNo: string
  rows: SendListRow[]
  subtotal: number
}

/**
 * 按索引号分组 + 组内票面金额小计。
 * 展示层派生：buildPayload().rows 仍是扁平数组。
 */
export function groupByIndexNo(rows: SendListRow[]): E05IndexGroup[] {
  const map = new Map<string, SendListRow[]>()
  for (const row of rows) {
    const idx = String(row.index_no || '').trim() || '(未填索引号)'
    if (!map.has(idx)) map.set(idx, [])
    map.get(idx)!.push(row)
  }
  const groups: E05IndexGroup[] = []
  for (const [indexNo, groupRows] of map) {
    const subtotal = groupRows.reduce((sum, r) => {
      const v = Number(r.face_amount)
      return sum + (Number.isFinite(v) ? v : 0)
    }, 0)
    groups.push({ indexNo, rows: groupRows, subtotal })
  }
  return groups
}

// ─── 发函完整性三方勾稽 ──────────────────────────────────────────────────────

export interface E05Prefill {
  rows: any[]
  tb_2201: number | null
  bank_unconfirmed_count?: number
  hints?: string[]
}

/**
 * 三方勾稽：Σ(E0-5 票面) ↔ Σ(F3-2 银承待函证审定数) ↔ trial_balance 2201。
 * 任一不可得 → 该项 skip。
 */
export function checkE05Completeness(
  rows: SendListRow[],
  f3Prefill: E05Prefill | null,
  tb2201: number | null,
): ConsistencyItem[] {
  const items: ConsistencyItem[] = []

  // E0-5 票面金额合计
  const e05Total = rows.reduce((sum, r) => {
    const v = Number(r.face_amount)
    return sum + (Number.isFinite(v) ? v : 0)
  }, 0)

  // F3-2 银承待函证审定数合计
  const f3Total = f3Prefill?.rows?.reduce((sum: number, r: any) => {
    const v = Number(r.audited_amount ?? r.face_amount)
    return sum + (Number.isFinite(v) ? v : 0)
  }, 0) ?? null

  // 勾稽 1: E0-5 ↔ F3-2
  if (f3Total === null) {
    items.push({ id: 'e05-vs-f3-skip', level: 'skip', rule: '三方勾稽', label: 'F3-2 数据不可得，跳过比对' })
  } else if (Math.abs(e05Total - f3Total) > 0.01) {
    items.push({
      id: 'e05-vs-f3-error',
      level: 'error',
      rule: 'Σ(E0-5 票面) ↔ Σ(F3-2 银承待函证审定数)',
      label: `E0-5 合计 ${e05Total.toFixed(2)} ≠ F3-2 合计 ${f3Total.toFixed(2)}，差异 ${(e05Total - f3Total).toFixed(2)}`,
    })
  } else {
    items.push({ id: 'e05-vs-f3-ok', level: 'ok', rule: '三方勾稽', label: 'E0-5 合计 = F3-2 合计' })
  }

  // 勾稽 2: E0-5 ↔ 2201
  if (tb2201 === null || tb2201 === undefined) {
    items.push({ id: 'e05-vs-2201-skip', level: 'skip', rule: '三方勾稽', label: 'trial_balance 2201 不可得，跳过' })
  } else if (Math.abs(e05Total - tb2201) > 0.01) {
    items.push({
      id: 'e05-vs-2201-warning',
      level: 'warning',
      rule: 'Σ(E0-5 票面) ↔ trial_balance 2201',
      label: `E0-5 合计 ${e05Total.toFixed(2)} ≠ 2201 余额 ${tb2201.toFixed(2)}（差异可能含商承/供应链票据）`,
    })
  } else {
    items.push({ id: 'e05-vs-2201-ok', level: 'ok', rule: '三方勾稽', label: 'E0-5 合计 ≈ 2201 余额' })
  }

  return items
}

// ─── 票号唯一性 ──────────────────────────────────────────────────────────────

export function checkE05TicketNo(
  rows: SendListRow[],
  f3Prefill: E05Prefill | null,
): ConsistencyItem[] {
  const items: ConsistencyItem[] = []

  // 票号重复检测
  const seen = new Map<string, number>()
  for (const row of rows) {
    const no = String(row.bill_no || '').trim()
    if (!no) continue
    seen.set(no, (seen.get(no) || 0) + 1)
  }
  for (const [no, count] of seen) {
    if (count > 1) {
      items.push({
        id: `dup-ticket-${no}`,
        level: 'error',
        rule: '票据号唯一性',
        label: `票据号 ${no} 出现 ${count} 次（电子票号全局唯一，重复即重复登记）`,
      })
    }
  }

  // 与 F3-2 一致性
  if (f3Prefill?.rows) {
    const f3Nos = new Set(f3Prefill.rows.map((r: any) => String(r.bill_no || '').trim()).filter(Boolean))
    const e05Nos = new Set(rows.map(r => String(r.bill_no || '').trim()).filter(Boolean))

    for (const no of e05Nos) {
      if (!f3Nos.has(no)) {
        items.push({
          id: `e05-only-${no}`,
          level: 'warning',
          rule: '票号一致性',
          label: `票据号 ${no} 在 E0-5 但 F3-2 无记录（账面未登记？）`,
        })
      }
    }
    for (const no of f3Nos) {
      if (!e05Nos.has(no)) {
        items.push({
          id: `f3-only-${no}`,
          level: 'warning',
          rule: '票号一致性',
          label: `票据号 ${no} 在 F3-2 待函证但 E0-5 未列（可能漏函）`,
        })
      }
    }
  }

  return items
}

// ─── 到期日风险 ──────────────────────────────────────────────────────────────

export interface TenorPolicy {
  /** 最大期限天数（按会计期间可配置，禁写死月数） */
  maxTenorDays: number
}

export function checkE05Tenor(
  rows: SendListRow[],
  cutoffDate: string,
  policy: TenorPolicy,
): ConsistencyItem[] {
  const items: ConsistencyItem[] = []
  if (!cutoffDate) return items

  const cutoff = new Date(cutoffDate)
  if (isNaN(cutoff.getTime())) return items

  for (const row of rows) {
    const dueStr = String(row.maturity_date || '').trim()
    const issueStr = String(row.issue_date || '').trim()
    if (!dueStr) continue

    const dueDate = new Date(dueStr)
    if (isNaN(dueDate.getTime())) continue

    const billNo = String(row.bill_no || row._row_id || '')

    // 已到期未兑付
    if (dueDate <= cutoff) {
      items.push({
        id: `matured-${billNo}`,
        level: 'warning',
        rule: '到期日风险',
        label: `票据 ${billNo} 到期日 ${dueStr} ≤ 报表截止日，属已到期未兑付`,
      })
    }

    // 期限异常
    if (issueStr) {
      const issueDate = new Date(issueStr)
      if (!isNaN(issueDate.getTime())) {
        const tenorDays = Math.round((dueDate.getTime() - issueDate.getTime()) / 86400000)
        if (tenorDays > policy.maxTenorDays) {
          items.push({
            id: `tenor-${billNo}`,
            level: 'info',
            rule: '期限异常',
            label: `票据 ${billNo} 期限 ${tenorDays} 天超过阈值 ${policy.maxTenorDays} 天`,
          })
        }
      }
    }
  }

  return items
}
