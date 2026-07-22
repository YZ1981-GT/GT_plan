/**
 * I1 无形资产披露表 ↔ 附注章节冻结映射
 *
 * 权威来源：
 * - note_template_listed「五、26」无形资产（表名：无形资产情况）
 * - note_template_soe「八、27」无形资产（表名：无形资产情况）
 * - 源 xlsx「附注披露信息（上市公司/国有企业）」
 */
export type I1DisclosureVariant = 'listed' | 'soe'

export const I1_NOTE_SECTION = {
  listed: '五、26',
  soe: '八、27',
} as const satisfies Record<I1DisclosureVariant, string>

export const I1_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国有企业）',
} as const satisfies Record<I1DisclosureVariant, string>

/** 与 note_template tables[].name 一致 */
export const I1_LISTED_SUBTABLE = {
  movement: '无形资产情况',
} as const

export const I1_SOE_SUBTABLE = {
  movement: '无形资产情况',
} as const

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

export function isI1DisclosureApplicable(
  variant: I1DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = (applicableStandards || []).map((s) => String(s).trim()).filter(Boolean)
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveI1CurrentStandard(
  variant: I1DisclosureVariant,
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

export function resolveI1NoteSectionTarget(variant: I1DisclosureVariant): {
  sectionId: string
  chipValue: string
} {
  const sectionId = I1_NOTE_SECTION[variant]
  return { sectionId, chipValue: `Note:${sectionId}` }
}

export function isI1IntangibleNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、26' || s.startsWith('五、26')) return true
  if (s === '八、27' || s.startsWith('八、27')) return true
  if (s === '三、无形资产' || s.startsWith('三、无形资产')) return true
  if (s === '四、无形资产' || s.startsWith('四、无形资产')) return true
  if (s === '无形资产' || (s.includes('无形资产') && !s.includes('研发'))) return true
  return false
}
