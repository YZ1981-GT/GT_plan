/**
 * G8 其他权益工具投资（报表科目 1503）↔ 附注章节映射
 *
 * 权威 note_template_variant_matrix.json · account_key=qi_ta_quan_yi_gong_ju_tou_zi：
 * - 上市 → 五、19
 * - 国企 → 八、19
 * 报表行：BS-034（cell_mapping / report_row_note_mapping / account_to_report_line_seed）
 */
export type G8DisclosureVariant = 'listed' | 'soe'

export const G8_SOE_NOTE_SECTION = '八、19'

export const G8_NOTE_SECTION = {
  listed: '五、19',
  soe: G8_SOE_NOTE_SECTION,
} as const satisfies Record<G8DisclosureVariant, string>

export const G8_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<G8DisclosureVariant, string>

export const G8_MAIN_SUBTABLE = {
  listed: '项  目',
  soe: '其他权益工具投资',
} as const satisfies Record<G8DisclosureVariant, string>

export { G8_ACCOUNT_CODE } from './g8Constants'

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

export function isG8DisclosureApplicable(
  variant: G8DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = applicableStandards ?? []
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveG8CurrentStandard(
  variant: G8DisclosureVariant,
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

export interface G8NoteSectionTarget {
  variant: G8DisclosureVariant
  sectionId: string
  sheetName: string
  currentStandard: string
  chipValue: string
}

export function resolveG8NoteSectionTarget(
  variant: G8DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): G8NoteSectionTarget | null {
  if (!isG8DisclosureApplicable(variant, applicableStandards)) return null
  const sectionId = G8_NOTE_SECTION[variant]
  return {
    variant,
    sectionId,
    sheetName: G8_DISCLOSURE_SHEET_NAME[variant],
    currentStandard: resolveG8CurrentStandard(variant, applicableStandards),
    chipValue: `Note:${sectionId}`,
  }
}

export function isG8OtherEquityInstrumentNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === G8_NOTE_SECTION.listed || s.startsWith('五、19')) return true
  if (s === G8_SOE_NOTE_SECTION || s.startsWith('八、19')) return true
  return false
}
