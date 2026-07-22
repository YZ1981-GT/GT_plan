/**
 * G13 公允价值变动收益（报表科目 6101）↔ 附注章节映射
 *
 * 权威 note_template_variant_matrix.json · account_key=gong_yun_jia_zhi_bian_dong_shou_yi：
 * - 国企（报表项目附注）→ 八、72
 * - 上市 → 三、公允价值变动收益
 */
export type G13DisclosureVariant = 'listed' | 'soe'

/** 国企报表科目「公允价值变动收益」对应附注节 */
export const G13_SOE_NOTE_SECTION = '八、72'

export const G13_NOTE_SECTION = {
  listed: '三、公允价值变动收益',
  soe: G13_SOE_NOTE_SECTION,
} as const satisfies Record<G13DisclosureVariant, string>

export const G13_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<G13DisclosureVariant, string>

/** 附注模板子表名（与 note_template tables[].name 一致） */
export const G13_MAIN_SUBTABLE = '产生公允价值变动收益的来源'

export { G13_ACCOUNT_CODE } from './g13Constants'

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

export function isG13DisclosureApplicable(
  variant: G13DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = applicableStandards ?? []
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveG13CurrentStandard(
  variant: G13DisclosureVariant,
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

export interface G13NoteSectionTarget {
  variant: G13DisclosureVariant
  sectionId: string
  sheetName: string
  currentStandard: string
  chipValue: string
}

export function resolveG13NoteSectionTarget(
  variant: G13DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): G13NoteSectionTarget | null {
  if (!isG13DisclosureApplicable(variant, applicableStandards)) return null
  const sectionId = G13_NOTE_SECTION[variant]
  return {
    variant,
    sectionId,
    sheetName: G13_DISCLOSURE_SHEET_NAME[variant],
    currentStandard: resolveG13CurrentStandard(variant, applicableStandards),
    chipValue: `Note:${sectionId}`,
  }
}

export function isG13FairValueNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === G13_NOTE_SECTION.listed || s.startsWith('三、公允价值变动')) return true
  if (s === G13_SOE_NOTE_SECTION || s.startsWith('八、72')) return true
  return false
}

/** 从中央附注模块读取叙述文本 */
export async function fetchG13CentralNoteText(
  fetchFn: (url: string, config?: Record<string, unknown>) => Promise<unknown>,
  projectId: string,
  year: number,
  variant: G13DisclosureVariant,
): Promise<string | null> {
  const sectionId = G13_NOTE_SECTION[variant]
  const res = await fetchFn(
    `/api/disclosure-notes/${projectId}/${year}/${encodeURIComponent(sectionId)}`,
    { _silent: true },
  ) as { data?: { text_content?: string }; text_content?: string }
  const data = (res as { data?: { text_content?: string } })?.data ?? res
  const text = String((data as { text_content?: string })?.text_content ?? '').trim()
  return text || null
}
