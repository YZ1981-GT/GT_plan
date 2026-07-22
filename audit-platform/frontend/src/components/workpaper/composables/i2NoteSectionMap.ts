/**
 * I2 开发支出披露表 ↔ 附注章节冻结映射
 *
 * - note_template_listed「五、27」开发支出
 * - note_template_soe「八、28」开发支出
 */
export type I2DisclosureVariant = 'listed' | 'soe'

export const I2_NOTE_SECTION = {
  listed: '五、27',
  soe: '八、28',
} as const satisfies Record<I2DisclosureVariant, string>

export const I2_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国有企业）',
} as const satisfies Record<I2DisclosureVariant, string>

/** 与 note_template tables[].name 一致 */
export const I2_LISTED_SUBTABLE = {
  /** 研发投入按性质（费用化/资本化） */
  nature: '研发投入按性质',
  /** 开发支出项目滚动 */
  movement: '开发支出',
  important: '重要的资本化研发项目',
  impairment: '开发支出减值准备',
} as const

export const I2_SOE_SUBTABLE = {
  movement: '开发支出',
} as const

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

export function isI2DisclosureApplicable(
  variant: I2DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = applicableStandards ?? []
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveI2CurrentStandard(
  variant: I2DisclosureVariant,
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

export function resolveI2NoteSectionTarget(
  variant: I2DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): { sectionId: string; sheetName: string; currentStandard: string; chipValue: string } | null {
  if (!isI2DisclosureApplicable(variant, applicableStandards)) return null
  const sectionId = I2_NOTE_SECTION[variant]
  return {
    sectionId,
    sheetName: I2_DISCLOSURE_SHEET_NAME[variant],
    currentStandard: resolveI2CurrentStandard(variant, applicableStandards),
    chipValue: `note:${sectionId}`,
  }
}
