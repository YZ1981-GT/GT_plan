/**
 * G14 信用减值损失（报表科目 6702）↔ 附注章节映射
 *
 * 权威 note_template_variant_matrix.json · account_key=xin_yong_jian_zhi_sun_shi：
 * - 国企（报表项目附注）→ 八、73
 * - 上市 → 三、信用减值损失（note_template_listed section_title）
 */
export type G14DisclosureVariant = 'listed' | 'soe'

/** 国企报表科目「信用减值损失」对应附注节 */
export const G14_SOE_NOTE_SECTION = '八、73'

export const G14_NOTE_SECTION = {
  listed: '三、信用减值损失',
  soe: G14_SOE_NOTE_SECTION,
} as const satisfies Record<G14DisclosureVariant, string>

export const G14_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<G14DisclosureVariant, string>

/** 附注模板子表名（与 note_template tables[].name 一致） */
export const G14_MAIN_SUBTABLE = {
  listed: '项  目',
  soe: '信用减值损失',
} as const satisfies Record<G14DisclosureVariant, string>

export { G14_ACCOUNT_CODE } from './g14Constants'

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

export function isG14DisclosureApplicable(
  variant: G14DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = applicableStandards ?? []
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveG14CurrentStandard(
  variant: G14DisclosureVariant,
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

export interface G14NoteSectionTarget {
  variant: G14DisclosureVariant
  sectionId: string
  sheetName: string
  currentStandard: string
  chipValue: string
}

export function resolveG14NoteSectionTarget(
  variant: G14DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): G14NoteSectionTarget | null {
  if (!isG14DisclosureApplicable(variant, applicableStandards)) return null
  const sectionId = G14_NOTE_SECTION[variant]
  return {
    variant,
    sectionId,
    sheetName: G14_DISCLOSURE_SHEET_NAME[variant],
    currentStandard: resolveG14CurrentStandard(variant, applicableStandards),
    chipValue: `Note:${sectionId}`,
  }
}

export function isG14CreditImpairmentNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === G14_NOTE_SECTION.listed || s.startsWith('三、信用减值')) return true
  if (s === G14_SOE_NOTE_SECTION || s.startsWith('八、73')) return true
  return false
}
