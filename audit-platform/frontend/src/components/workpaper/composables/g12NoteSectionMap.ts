/**
 * G12 净敞口套期收益披露表 ↔ 附注章节映射
 *
 * 权威：`backend/data/note_template_variant_matrix.json`
 *   jing_chang_kou_tao_qi_shou_yi → listed 五、70 / soe 八、71
 *
 * 🔴 sheet 名常量必须是**源 xlsx 的中文 tab 名**（非 wp_code 形态的合成标识、非短名），
 *    否则附注侧「打开同步底稿」会落到底稿首个 sheet。G12 源模板用「（国企）」
 *    而非「（国有企业）」，已逐字核对 `G12 净敞口套期收益.xlsx`。
 *
 * spec: .kiro/specs/disclosure-sync-path-buildout/ Task 2.8
 */
export type G12DisclosureVariant = 'listed' | 'soe'

export const G12_NOTE_SECTION = {
  listed: '五、70',
  soe: '八、71',
} as const satisfies Record<G12DisclosureVariant, string>

export const G12_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<G12DisclosureVariant, string>

function isListedStandard(s: string): boolean {
  const x = String(s).toLowerCase()
  return x.includes('listed') || x.includes('上市')
}

function isSoeStandard(s: string): boolean {
  const x = String(s).toLowerCase()
  return (
    x.includes('soe')
    || x.includes('state_owned')
    || x.includes('国企')
    || x.includes('国有')
  )
}

/** 适用性：未声明适用准则时两个变体都放行（与 G11/G3 同口径） */
export function isG12DisclosureApplicable(
  variant: G12DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = applicableStandards ?? []
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveG12CurrentStandard(
  variant: G12DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): string {
  const list = (applicableStandards || []).map((s) => String(s).toLowerCase())
  if (variant === 'listed') {
    return list.some((s) => s.includes('listed') && s.includes('consol'))
      ? 'listed_consolidated'
      : 'listed_standalone'
  }
  return list.some((s) => s.includes('soe') && s.includes('consol'))
    ? 'soe_consolidated'
    : 'soe_standalone'
}

export interface G12NoteSectionTarget {
  variant: G12DisclosureVariant
  sectionId: string
  sheetName: string
  currentStandard: string
  chipValue: string
}

export function resolveG12NoteSectionTarget(
  variant: G12DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): G12NoteSectionTarget | null {
  if (!isG12DisclosureApplicable(variant, applicableStandards)) return null
  const sectionId = G12_NOTE_SECTION[variant]
  return {
    variant,
    sectionId,
    sheetName: G12_DISCLOSURE_SHEET_NAME[variant],
    currentStandard: resolveG12CurrentStandard(variant, applicableStandards),
    chipValue: `Note:${sectionId}`,
  }
}
