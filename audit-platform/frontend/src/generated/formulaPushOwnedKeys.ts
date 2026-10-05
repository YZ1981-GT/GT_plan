// @generated DO NOT EDIT — 由 gen_formula_push_owned_keys.py 生成
// spec: formula-push-all-subjects-rollout · 需求 4.1

export const FORMULA_PUSH_OWNED: Record<string, { exact: readonly string[]; patterns: readonly string[] }> = {
  D1: { exact: ['D1-adj-tb-amount'], patterns: [] },
  D2: { exact: ['D2-adj-tb-amount'], patterns: [] },
  D3: { exact: ['D3-adj-trial-balance-amount'], patterns: [] },
  D4: { exact: ['D4-1-adj-tb-6001', 'D4-1-adj-tb-6051'], patterns: [] },
  D6: { exact: ['D6-1-tb-amount'], patterns: [] },
  D7: { exact: ['D7-1-adj-aging-trial-balance-currentAudited'], patterns: [] },
  E1: { exact: ['E1-adj-slot-accrued', 'E1-adj-slot-accrued-opening', 'E1-adj-slot-digital', 'E1-adj-slot-digital-opening', 'E1-adj-slot-finance_co', 'E1-adj-slot-finance_co-opening', 'E1-adj-tb-amount-ending', 'E1-adj-tb-amount-opening', 'E1-adj-total-1001', 'E1-adj-total-1001-opening', 'E1-adj-total-1002', 'E1-adj-total-1002-opening', 'E1-adj-total-1012', 'E1-adj-total-1012-opening', 'E1-bank-detail-finance-opening-unaudited', 'E1-bank-detail-finance-total-unaudited', 'E1-bank-detail-institution-opening-unaudited', 'E1-bank-detail-institution-total-unaudited', 'E1-bank-detail-other-opening-unaudited', 'E1-bank-detail-other-total-unaudited', 'E1-bank-detail-principal-opening-unaudited', 'E1-bank-detail-principal-total-unaudited', 'E1-cash-detail-opening-unaudited', 'E1-cash-detail-total-unaudited', 'E1-hall-adj-bank_principal-ending', 'E1-hall-adj-cash-ending', 'E1-hall-adj-other_mf-ending'], patterns: [] },
  H10: { exact: ['H10-1-tb-amount'], patterns: [] },
  H5: { exact: ['H5-1-tb-amount'], patterns: [] },
  H6: { exact: ['H6-1-tb-amount'], patterns: [] },
  H7: { exact: ['H7-1-tb-amount'], patterns: [] },
  H8: { exact: ['H8-1-tb-amount'], patterns: [] },
  H9: { exact: ['H9-1-tb-amount'], patterns: [] },
  I1: { exact: ['I1-1-tb-amort', 'I1-1-tb-cost', 'I1-1-tb-impair'], patterns: [] },
  I2: { exact: ['I2-1-tb-amount'], patterns: [] },
  I3: { exact: ['I3-1-tb-amount'], patterns: [] },
  I4: { exact: ['I4-1-tb-amount'], patterns: [] },
  I5: { exact: ['I5-1-tb-amount'], patterns: [] },
  I6: { exact: ['I6-1-tb-amount'], patterns: [] },
  K1: { exact: ['K1-1-audited-baddebt', 'K1-1-audited-net', 'K1-1-audited-receivable'], patterns: [] },
} as const

/** 判断 item_id 是否是指定主编码的后端独占键。 */
export function isOwnedKey(wpCode: string, itemId: string): boolean {
  const entry = FORMULA_PUSH_OWNED[wpCode]
  if (!entry) return false
  if (entry.exact.includes(itemId)) return true
  return entry.patterns.some((p) => new RegExp(p).test(itemId))
}
