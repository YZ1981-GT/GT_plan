/**
 * H10 资产处置损益（6115）↔ 附注章节映射
 *
 * note_template_listed：三、资产处置收益（chapter-03…zi-chan-chu-zhi-shou-yi）
 * note_template_soe / variant_matrix：八、75 资产处置收益
 */
export type H10DisclosureVariant = 'listed' | 'soe'

export const H10_SOE_NOTE_SECTION = '八、75'

export const H10_NOTE_SECTION = {
  listed: '三、资产处置收益',
  soe: H10_SOE_NOTE_SECTION,
} as const satisfies Record<H10DisclosureVariant, string>

export const H10_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国有企业）',
} as const satisfies Record<H10DisclosureVariant, string>

/** 附注模板主表名（与 note_template tables[].name 一致） */
export const H10_MAIN_SUBTABLE = {
  listed: '项  目',
  soe: '资产处置收益（损失以“-”号填列）',
} as const satisfies Record<H10DisclosureVariant, string>

/** 上市试运行销售明细子表名（第二张表，与模板 tables[1] 对齐） */
export const H10_TRIAL_SUBTABLE = '项  目'

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

export function isH10DisclosureApplicable(
  variant: H10DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = applicableStandards ?? []
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveH10CurrentStandard(
  variant: H10DisclosureVariant,
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

export function resolveH10NoteSectionTarget(
  variant: H10DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): { sectionId: string; sheetName: string; currentStandard: string; chipValue: string } | null {
  if (!isH10DisclosureApplicable(variant, applicableStandards)) return null
  const sectionId = H10_NOTE_SECTION[variant]
  return {
    sectionId,
    sheetName: H10_DISCLOSURE_SHEET_NAME[variant],
    currentStandard: resolveH10CurrentStandard(variant, applicableStandards),
    chipValue: `Note:${sectionId}`,
  }
}
