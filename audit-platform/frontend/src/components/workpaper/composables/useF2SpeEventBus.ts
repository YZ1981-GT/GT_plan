/**
 * F2 特殊组 EventBus — substantive:adjudicated / disclosure:note-text-updated
 * Spec: f2-inventory-special Task 17, Requirements 25.1~25.5
 */

const DEDUP_MS = 2000

let lastAdjudicatedKey = ''
let lastAdjudicatedAt = 0
let lastDisclosureKey = ''
let lastDisclosureAt = 0

export interface F2SpeSubstantivePayload {
  wpCode: 'F2-special'
  accountCode: '1405'
  auditedAmount?: number
  impairmentAmount?: number
}

export function publishF2SpeSubstantiveAdjudicated(detail: F2SpeSubstantivePayload): void {
  const key = JSON.stringify(detail)
  const now = Date.now()
  if (key === lastAdjudicatedKey && now - lastAdjudicatedAt < DEDUP_MS) return
  lastAdjudicatedKey = key
  lastAdjudicatedAt = now
  try {
    window.dispatchEvent(new CustomEvent('substantive:adjudicated', { detail }))
  } catch { /* silent */ }
}

let disclosureTimer: ReturnType<typeof setTimeout> | null = null

export function debouncedPublishF2SpeDisclosureNote(
  section: 'contract-cost' | 'impairment',
  text: string,
): void {
  if (disclosureTimer) clearTimeout(disclosureTimer)
  disclosureTimer = setTimeout(() => {
    disclosureTimer = null
    const detail = { wpCode: 'F2-special' as const, section, text }
    const key = JSON.stringify(detail)
    const now = Date.now()
    if (key === lastDisclosureKey && now - lastDisclosureAt < DEDUP_MS) return
    lastDisclosureKey = key
    lastDisclosureAt = now
    try {
      window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', { detail }))
    } catch { /* silent */ }
  }, DEDUP_MS)
}

/** @internal test helper */
export function resetF2SpeEventBusDedupState(): void {
  lastAdjudicatedKey = ''
  lastAdjudicatedAt = 0
  lastDisclosureKey = ''
  lastDisclosureAt = 0
  if (disclosureTimer) {
    clearTimeout(disclosureTimer)
    disclosureTimer = null
  }
}

export function is1405SubstantiveEvent(detail: Record<string, unknown> | undefined): boolean {
  if (!detail) return false
  if (detail.accountCode === '1405') return true
  const codes = detail.accountCodes
  if (Array.isArray(codes) && codes.includes('1405')) return true
  const amounts = detail.auditedAmounts
  if (amounts && typeof amounts === 'object' && '1405' in (amounts as object)) return true
  return false
}
