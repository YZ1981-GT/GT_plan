/**
 * F1 预付款项披露 ↔ 附注章节映射
 * 权威：note_template_variant_matrix.json → yu_fu_kuan_xiang
 *   listed_* → 五、7
 *   soe_*    → 八、7
 */
export type F1DisclosureVariant = 'listed' | 'soe'

export const F1_NOTE_SECTION = {
  listed: '五、7',
  soe: '八、7',
} as const satisfies Record<F1DisclosureVariant, string>

export const F1_DISCLOSURE_SHEET_NAME = {
  listed: 'F1-note-listed',
  soe: 'F1-note-soe',
} as const satisfies Record<F1DisclosureVariant, string>

export function isF1ListedStandard(s: string): boolean {
  const x = String(s).toLowerCase()
  return x.includes('listed') || x.includes('上市') || x === 'listed_standalone' || x === 'listed_consolidated'
}

export function isF1SoeStandard(s: string): boolean {
  const x = String(s).toLowerCase()
  return (
    x.includes('soe')
    || x.includes('state_owned')
    || x.includes('国企')
    || x.includes('国有')
    || x === 'soe_standalone'
    || x === 'soe_consolidated'
  )
}

export function isF1DisclosureApplicable(
  variant: F1DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = applicableStandards ?? []
  if (list.length === 0) return true
  if (variant === 'listed') return list.some(isF1ListedStandard)
  return list.some(isF1SoeStandard)
}

export function resolveF1CurrentStandard(
  variant: F1DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): string {
  const list = (applicableStandards || []).map((s) => String(s).toLowerCase())
  if (variant === 'listed') {
    if (list.some((s) => s === 'listed_consolidated' || (s.includes('listed') && s.includes('consol')))) {
      return 'listed_consolidated'
    }
    return 'listed_standalone'
  }
  if (list.some((s) => s === 'soe_consolidated' || (s.includes('soe') && s.includes('consol')))) {
    return 'soe_consolidated'
  }
  return 'soe_standalone'
}
