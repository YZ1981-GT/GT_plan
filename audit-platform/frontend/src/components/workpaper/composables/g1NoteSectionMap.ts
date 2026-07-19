/**
 * G1 交易性金融资产披露表 ↔ 附注章节映射
 *
 * 权威：note_template_variant_matrix.json
 *   jiao_yi_xing_jin_rong_zi_chan → listed 五、2 / soe 八、2
 *   yan_sheng_jin_rong_zi_chan   → listed 五、3 / soe 八、3
 *
 * 国企披露页同时覆盖「交易性」与「衍生」两张表，同步时分别写入对应章节。
 */
export type G1DisclosureVariant = 'listed' | 'soe'

export const G1_NOTE_SECTION = {
  listed: { trading: '五、2', derivative: '五、3' },
  soe: { trading: '八、2', derivative: '八、3' },
} as const satisfies Record<G1DisclosureVariant, { trading: string; derivative: string }>

export const G1_DISCLOSURE_SHEET_NAME = {
  listed: 'G1-note-listed',
  soe: 'G1-note-soe',
} as const satisfies Record<G1DisclosureVariant, string>

export const G1_ACCOUNT_CODE = '1501'

export function isG1ListedStandard(s: string): boolean {
  const x = String(s).toLowerCase()
  return x.includes('listed') || x.includes('上市') || x === 'listed_standalone' || x === 'listed_consolidated'
}

export function isG1SoeStandard(s: string): boolean {
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

export function isG1DisclosureApplicable(
  variant: G1DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = applicableStandards ?? []
  if (list.length === 0) return true
  const hasListed = list.some(isG1ListedStandard)
  const hasSoe = list.some(isG1SoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveG1CurrentStandard(
  variant: G1DisclosureVariant,
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

export interface G1NoteSectionTarget {
  variant: G1DisclosureVariant
  tradingSectionId: string
  derivativeSectionId: string
  sheetName: string
  currentStandard: string
  chipValue: string
}

export function resolveG1NoteSectionTarget(
  variant: G1DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): G1NoteSectionTarget | null {
  if (!isG1DisclosureApplicable(variant, applicableStandards)) return null
  const sections = G1_NOTE_SECTION[variant]
  return {
    variant,
    tradingSectionId: sections.trading,
    derivativeSectionId: sections.derivative,
    sheetName: G1_DISCLOSURE_SHEET_NAME[variant],
    currentStandard: resolveG1CurrentStandard(variant, applicableStandards),
    chipValue: `Note:${sections.trading}`,
  }
}
