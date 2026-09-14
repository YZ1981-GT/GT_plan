/**
 * G11 投资收益披露表 ↔ 附注章节映射
 *
 * 权威：note_template_variant_matrix.json
 *   tou_zi_shou_yi              → listed 五、69
 *   tou_zi_shou_yi_xia_biao…    → soe 八、70
 */
export type G11DisclosureVariant = 'listed' | 'soe'

export const G11_NOTE_SECTION = {
  listed: '五、69',
  soe: '八、70',
} as const satisfies Record<G11DisclosureVariant, string>

export const G11_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<G11DisclosureVariant, string>

export { G11_ACCOUNT_CODE } from './g11Constants'

function isListedStandard(s: string): boolean {
  const x = String(s).toLowerCase()
  return x.includes('listed') || x.includes('上市') || x === 'listed_standalone' || x === 'listed_consolidated'
}

function isSoeStandard(s: string): boolean {
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

export function isG11DisclosureApplicable(
  variant: G11DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = applicableStandards ?? []
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveG11CurrentStandard(
  variant: G11DisclosureVariant,
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

export interface G11NoteSectionTarget {
  variant: G11DisclosureVariant
  sectionId: string
  sheetName: string
  currentStandard: string
  chipValue: string
}

export function resolveG11NoteSectionTarget(
  variant: G11DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): G11NoteSectionTarget | null {
  if (!isG11DisclosureApplicable(variant, applicableStandards)) return null
  const sectionId = G11_NOTE_SECTION[variant]
  return {
    variant,
    sectionId,
    sheetName: G11_DISCLOSURE_SHEET_NAME[variant],
    currentStandard: resolveG11CurrentStandard(variant, applicableStandards),
    chipValue: `Note:${sectionId}`,
  }
}
