/**
 * H8 使用权资产披露表 ↔ 附注章节冻结映射
 *
 * 权威来源：
 * - note_template_listed「五、25」使用权资产（表名：使用权资产）
 * - note_template_soe「八、26」使用权资产（表名：使用权资产）
 * - 源 xlsx「附注披露信息（上市公司/国企）」
 */
export type H8DisclosureVariant = 'listed' | 'soe'

export const H8_NOTE_SECTION = {
  listed: '五、25',
  soe: '八、26',
} as const satisfies Record<H8DisclosureVariant, string>

/** 同步 payload / OO 源 tab 名 */
export const H8_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<H8DisclosureVariant, string>

/** 与 note_template tables[].name 一致 */
export const H8_LISTED_SUBTABLE = {
  /** 五、25 主变动表 */
  movement: '使用权资产',
} as const

export const H8_SOE_SUBTABLE = {
  movement: '使用权资产',
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

export function isH8DisclosureApplicable(
  variant: H8DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = (applicableStandards || []).map((s) => String(s).trim()).filter(Boolean)
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveH8CurrentStandard(
  variant: H8DisclosureVariant,
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

export function resolveH8NoteSectionTarget(variant: H8DisclosureVariant): {
  sectionId: string
  chipValue: string
} {
  const sectionId = H8_NOTE_SECTION[variant]
  return { sectionId, chipValue: `Note:${sectionId}` }
}

export function isH8RouNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、25' || s.startsWith('五、25')) return true
  if (s === '八、26' || s.startsWith('八、26')) return true
  if (s === '三、使用权资产' || s.startsWith('三、使用权')) return true
  if (s === '四、使用权资产' || s.startsWith('四、使用权')) return true
  if (s === '使用权资产' || (s.includes('使用权资产') && !s.includes('改良'))) return true
  return false
}
