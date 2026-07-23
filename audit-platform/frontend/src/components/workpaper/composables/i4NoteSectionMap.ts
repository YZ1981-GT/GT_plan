/**
 * I4 长期待摊费用披露表 ↔ 附注章节冻结映射
 *
 * 权威来源：
 * - note_template_listed「五、29」长期待摊费用（表名：长期待摊费用）
 * - note_template_soe「八、30」长期待摊费用（表名：长期待摊费用）
 * - 源 xlsx「附注披露（上市公司/国有企业）」
 */
export type I4DisclosureVariant = 'listed' | 'soe'

export const I4_NOTE_SECTION = {
  listed: '五、29',
  soe: '八、30',
} as const satisfies Record<I4DisclosureVariant, string>

export const I4_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露（上市公司）',
  soe: '附注披露（国有企业）',
} as const satisfies Record<I4DisclosureVariant, string>

/** 与 note_template tables[].name 一致 */
export const I4_LISTED_SUBTABLE = {
  movement: '长期待摊费用',
} as const

export const I4_SOE_SUBTABLE = {
  movement: '长期待摊费用',
} as const

/** 披露默认类别（对齐源表/附注模板首行） */
export const I4_DEFAULT_DISCLOSURE_CATEGORIES = [
  '使用权资产改良及维护支出',
] as const

export function isListedStandard(s: string): boolean {
  const x = String(s).toLowerCase()
  return x.includes('listed') || x.includes('上市') || x === 'listed_standalone' || x === 'listed_consolidated'
}

export function isSoeStandard(s: string): boolean {
  const x = String(s).toLowerCase()
  return (
    x.includes('soe')
    || x.includes('state_owned')
    || x.includes('国企')
    || x.includes('国有')
    || x === 'cass'
    || x === 'cas'
    || x === 'soe_standalone'
    || x === 'soe_consolidated'
  )
}

export function isI4DisclosureApplicable(
  variant: I4DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = (applicableStandards || []).map((s) => String(s).trim()).filter(Boolean)
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveI4CurrentStandard(
  variant: I4DisclosureVariant,
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

export function resolveI4NoteSectionTarget(variant: I4DisclosureVariant): {
  sectionId: string
  chipValue: string
} {
  const sectionId = I4_NOTE_SECTION[variant]
  return { sectionId, chipValue: `Note:${sectionId}` }
}

export function isI4PrepaidNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、29' || s.startsWith('五、29')) return true
  if (s === '八、30' || s.startsWith('八、30')) return true
  if (s.includes('长期待摊费用')) return true
  return false
}
