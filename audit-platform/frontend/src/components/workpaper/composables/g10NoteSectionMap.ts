/**
 * G10 交易性金融负债披露表 ↔ 附注章节映射
 *
 * 权威：note_template_variant_matrix.json
 *   jiao_yi_xing_jin_rong_fu_zhai → listed 五、34 / soe 八、34
 *   yan_sheng_jin_rong_fu_zhai     → listed 五、35 / soe 八、35
 */
export type G10DisclosureVariant = 'listed' | 'soe'

export const G10_NOTE_SECTION = {
  listed: { trading: '五、34', derivative: '五、35' },
  soe: { trading: '八、34', derivative: '八、35' },
} as const satisfies Record<G10DisclosureVariant, { trading: string; derivative: string }>

export const G10_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<G10DisclosureVariant, string>

export { G10_ACCOUNT_CODE } from './g10Constants'

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

export function isG10DisclosureApplicable(
  variant: G10DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = applicableStandards ?? []
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveG10CurrentStandard(
  variant: G10DisclosureVariant,
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

export interface G10NoteSectionTarget {
  variant: G10DisclosureVariant
  tradingSectionId: string
  derivativeSectionId: string
  sheetName: string
  currentStandard: string
  chipValue: string
}

export function resolveG10NoteSectionTarget(
  variant: G10DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): G10NoteSectionTarget | null {
  if (!isG10DisclosureApplicable(variant, applicableStandards)) return null
  const sections = G10_NOTE_SECTION[variant]
  return {
    variant,
    tradingSectionId: sections.trading,
    derivativeSectionId: sections.derivative,
    sheetName: G10_DISCLOSURE_SHEET_NAME[variant],
    currentStandard: resolveG10CurrentStandard(variant, applicableStandards),
    chipValue: `Note:${sections.trading}`,
  }
}

/** 从中央附注模块读取 G10 主章节叙述文本（五、34 / 八、34） */
export async function fetchG10CentralNoteText(
  fetchFn: (url: string, config?: Record<string, unknown>) => Promise<unknown>,
  projectId: string,
  year: number,
  variant: G10DisclosureVariant,
): Promise<string | null> {
  const sectionId = G10_NOTE_SECTION[variant].trading
  const res = await fetchFn(
    `/api/disclosure-notes/${projectId}/${year}/${encodeURIComponent(sectionId)}`,
    { _silent: true },
  ) as { data?: { text_content?: string }; text_content?: string }
  const data = (res as { data?: { text_content?: string } })?.data ?? res
  const text = String((data as { text_content?: string })?.text_content ?? '').trim()
  return text || null
}
