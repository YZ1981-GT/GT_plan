/**
 * useFraudFlagDetect — 反舞弊检测 composable
 *
 * 行内一致性比对 (5 CONSISTENCY_RULES) + 跨行红旗检测
 */
import { type Ref } from 'vue'
import type { EntityVerifyRow } from '../entityVerifyTypes'

export interface FraudRule {
  id: string
  label: string
  check: (row: EntityVerifyRow) => boolean
}

/** 行内一致性规则 */
export const CONSISTENCY_RULES: FraudRule[] = [
  { id: 'name_mismatch', label: '单位名称不一致', check: (r) => r.name_match === 'inconsistent' },
  { id: 'address_mismatch', label: '地址不一致', check: (r) => r.address_match === 'inconsistent' },
  { id: 'contact_mismatch', label: '联系人不一致', check: (r) => r.contact_match === 'inconsistent' },
  { id: 'phone_mismatch', label: '电话不一致', check: (r) => r.phone_match === 'inconsistent' },
  { id: 'unreasonable_return', label: '退回原因不合理', check: (r) => r.reason_reasonable === '不合理' },
]

export interface CrossRowFlag {
  type: string
  label: string
  affectedRowIds: string[]
  detail: string
}

export function useFraudFlagDetect(rows: Ref<EntityVerifyRow[]>) {
  /** 行内规则检测 */
  function checkRowConsistency(row: EntityVerifyRow): string[] {
    if (row._overridden) return row.fraud_flags ?? []
    return CONSISTENCY_RULES.filter((rule) => rule.check(row)).map((r) => r.id)
  }

  /** 跨行检测：地址聚类（3+ 家注册于同一地址） */
  function detectAddressClustering(): CrossRowFlag[] {
    const addressMap = new Map<string, string[]>()
    for (const row of rows.value) {
      const addr = normalizeAddress(row.entity_address)
      if (!addr) continue
      if (!addressMap.has(addr)) addressMap.set(addr, [])
      addressMap.get(addr)!.push(row._row_id!)
    }
    const flags: CrossRowFlag[] = []
    for (const [addr, ids] of addressMap) {
      if (ids.length >= 3) {
        flags.push({
          type: 'address_cluster',
          label: '地址聚类',
          affectedRowIds: ids,
          detail: `${ids.length}家单位注册于同一地址: ${addr}`,
        })
      }
    }
    return flags
  }

  /** 跨行检测：电话号段相邻 */
  function detectPhoneAdjacent(): CrossRowFlag[] {
    const phones = rows.value
      .filter((r) => r.contact_phone)
      .map((r) => ({ id: r._row_id!, phone: r.contact_phone! }))
    const flags: CrossRowFlag[] = []
    for (let i = 0; i < phones.length - 1; i++) {
      for (let j = i + 1; j < phones.length; j++) {
        if (areAdjacent(phones[i].phone, phones[j].phone)) {
          flags.push({
            type: 'phone_adjacent',
            label: '电话号段相邻',
            affectedRowIds: [phones[i].id, phones[j].id],
            detail: `${phones[i].phone} 与 ${phones[j].phone} 号段相邻`,
          })
        }
      }
    }
    return flags
  }

  /** 一键筛查 */
  function runScreening(): { rowFlags: Map<string, string[]>; crossFlags: CrossRowFlag[] } {
    const rowFlags = new Map<string, string[]>()
    for (const row of rows.value) {
      const flags = checkRowConsistency(row)
      if (flags.length > 0) rowFlags.set(row._row_id!, flags)
    }
    const crossFlags = [...detectAddressClustering(), ...detectPhoneAdjacent()]
    return { rowFlags, crossFlags }
  }

  /** Derive row_status from flags */
  function deriveRowStatus(
    flagCount: number,
    hasCrossFlag: boolean,
  ): EntityVerifyRow['row_status'] {
    if (flagCount >= 2 || hasCrossFlag) return 'fraud_flag'
    if (flagCount === 1) return 'suspect'
    return 'ok'
  }

  return {
    checkRowConsistency,
    detectAddressClustering,
    detectPhoneAdjacent,
    runScreening,
    deriveRowStatus,
    CONSISTENCY_RULES,
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function normalizeAddress(addr?: string): string {
  if (!addr) return ''
  return addr.replace(/\s+/g, '').replace(/[（）()]/g, '').toLowerCase()
}

function areAdjacent(phone1: string, phone2: string): boolean {
  const digits1 = phone1.replace(/\D/g, '')
  const digits2 = phone2.replace(/\D/g, '')
  if (digits1.length < 7 || digits2.length < 7) return false
  // Compare last 4 digits
  const last4_1 = parseInt(digits1.slice(-4))
  const last4_2 = parseInt(digits2.slice(-4))
  return Math.abs(last4_1 - last4_2) <= 2 && last4_1 !== last4_2
}

// Export helpers for testing
export { normalizeAddress, areAdjacent }
