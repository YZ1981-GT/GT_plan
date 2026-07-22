/**
 * G12 净敞口套期收益披露表 ↔ 附注章节映射
 *
 * 权威：note_template_variant_matrix.json
 *   jing_chang_kou_tao_qi_shou_yi → listed 五、70 / soe 八、71
 */
export type G12DisclosureVariant = 'listed' | 'soe'

export const G12_NOTE_SECTION = {
  listed: '五、70',
  soe: '八、71',
} as const satisfies Record<G12DisclosureVariant, string>

export const G12_DISCLOSURE_SHEET_NAME = {
  listed: '附注上市',
  soe: '附注国企',
} as const satisfies Record<G12DisclosureVariant, string>

export { G12_ACCOUNT_CODE } from './g12Constants'

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

export function isG12DisclosureApplicable(
  variant: G12DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = applicableStandards ?? []
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveG12CurrentStandard(
  variant: G12DisclosureVariant,
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

export interface G12NoteSectionTarget {
  variant: G12DisclosureVariant
  sectionId: string
  sheetName: string
  currentStandard: string
  chipValue: string
}

export function resolveG12NoteSectionTarget(
  variant: G12DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): G12NoteSectionTarget | null {
  if (!isG12DisclosureApplicable(variant, applicableStandards)) return null
  const sectionId = G12_NOTE_SECTION[variant]
  return {
    variant,
    sectionId,
    sheetName: G12_DISCLOSURE_SHEET_NAME[variant],
    currentStandard: resolveG12CurrentStandard(variant, applicableStandards),
    chipValue: `Note:${sectionId}`,
  }
}
