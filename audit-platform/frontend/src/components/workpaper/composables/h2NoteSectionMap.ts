/**
 * H2 在建工程披露表 ↔ 附注章节冻结映射
 *
 * 权威来源：
 * - 源 xlsx「23、在建工程」上市表 → note_template_listed「五、23」
 * - note_template_soe.json → section_number「八、23」在建工程
 */
export type H2DisclosureVariant = 'listed' | 'soe'

export const H2_NOTE_SECTION = {
  listed: '五、23',
  soe: '八、23',
} as const satisfies Record<H2DisclosureVariant, string>

export const H2_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国有企业）',
} as const satisfies Record<H2DisclosureVariant, string>

/** 与 note_template_listed tables[].name 一致 */
export const H2_LISTED_SUBTABLE = {
  summary: '在建工程',
  detail: '在建工程明细',
  projectMovement: '重要在建工程项目变动情况',
  projectCont: '重要在建工程项目变动情况（续）：',
  impairment: '在建工程减值准备情况',
  materials: '项  目',
  /** 所有权受限 / 抵押担保（文本+明细，推送附注） */
  restricted: '所有权或使用权受限的在建工程',
} as const

/** 与 note_template_soe tables[].name 一致 */
export const H2_SOE_SUBTABLE = {
  summary: '在建工程',
  detail: '（1）在建工程情况',
  projectMovement: '（2）重要在建工程项目本期变动情况',
  impairment: '（3）本期计提在建工程减值准备情况',
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

export const isH2ListedStandard = isListedStandard
export const isH2SoeStandard = isSoeStandard

export function isH2DisclosureApplicable(
  variant: H2DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = (applicableStandards || []).map((s) => String(s).trim()).filter(Boolean)
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveH2CurrentStandard(
  variant: H2DisclosureVariant,
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

export function resolveH2NoteSectionTarget(
  variant: H2DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): { sectionId: string; sheetName: string; currentStandard: string; chipValue: string } | null {
  if (!isH2DisclosureApplicable(variant, applicableStandards)) return null
  const sectionId = H2_NOTE_SECTION[variant]
  return {
    sectionId,
    sheetName: H2_DISCLOSURE_SHEET_NAME[variant],
    currentStandard: resolveH2CurrentStandard(variant, applicableStandards),
    chipValue: `Note:${sectionId}`,
  }
}

export function isH2CipNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === H2_NOTE_SECTION.soe || s.startsWith('八、23')) return true
  if (s === H2_NOTE_SECTION.listed || s.startsWith('五、23')) return true
  if (s === '在建工程' || (s.includes('在建工程') && !s.includes('工程物资'))) return true
  return false
}
