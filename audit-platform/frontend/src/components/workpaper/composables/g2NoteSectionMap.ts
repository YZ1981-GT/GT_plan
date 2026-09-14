/**
 * G2 应收利息披露表 ↔ 附注章节映射
 *
 * 权威：note_template_variant_matrix.json → qi_ta_ying_shou_kuan
 *   国企：应收利息明细挂在「八、9 其他应收款」下（分类 / 逾期 / ECL）
 *   上市：挂在「五、8 其他应收款」下
 *
 * Excel 底稿提示「合计数披露详见 M1-1」：致同旧索引号，
 * 平台对应 wp:K1-1（其他应收款）+ Note:八、9（汇总表：应收利息+应收股利+其他应收款项）。
 */
export type G2DisclosureVariant = 'listed' | 'soe'

export const G2_NOTE_SECTION = {
  listed: '五、8',
  soe: '八、9',
} as const satisfies Record<G2DisclosureVariant, string>

export const G2_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<G2DisclosureVariant, string>

/** Excel 合计数索引（旧）→ 平台跳转目标 */
export const G2_COMBINED_DISCLOSURE_INDEX = {
  /** 模板原文索引号 */
  excelLegacy: 'M1-1',
  /** 其他应收款审定/合计数归集底稿 */
  wpCode: 'K1-1',
  /** 附注汇总章节（含应收利息行） */
  noteSectionSoe: '八、9',
  noteSectionListed: '五、8',
} as const

export const G2_ACCOUNT_CODE = '1132'

export function isG2ListedStandard(s: string): boolean {
  const x = String(s).toLowerCase()
  return x.includes('listed') || x.includes('上市') || x === 'listed_standalone' || x === 'listed_consolidated'
}

export function isG2SoeStandard(s: string): boolean {
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

export function isG2DisclosureApplicable(
  variant: G2DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = applicableStandards ?? []
  if (list.length === 0) return true
  const hasListed = list.some(isG2ListedStandard)
  const hasSoe = list.some(isG2SoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveG2CurrentStandard(
  variant: G2DisclosureVariant,
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

export interface G2NoteSectionTarget {
  variant: G2DisclosureVariant
  sectionId: string
  sheetName: string
  currentStandard: string
  chipValue: string
  combinedWpChip: string
  combinedNoteChip: string
}

export function resolveG2NoteSectionTarget(
  variant: G2DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): G2NoteSectionTarget | null {
  if (!isG2DisclosureApplicable(variant, applicableStandards)) return null
  const sectionId = G2_NOTE_SECTION[variant]
  return {
    variant,
    sectionId,
    sheetName: G2_DISCLOSURE_SHEET_NAME[variant],
    currentStandard: resolveG2CurrentStandard(variant, applicableStandards),
    chipValue: `Note:${sectionId}`,
    combinedWpChip: `wp:${G2_COMBINED_DISCLOSURE_INDEX.wpCode}`,
    combinedNoteChip: `Note:${sectionId}`,
  }
}
