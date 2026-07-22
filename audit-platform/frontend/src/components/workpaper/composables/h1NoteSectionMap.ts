/**
 * H1 固定资产披露表 ↔ 附注章节冻结映射
 *
 * 权威来源：
 * - 源 xlsx 上市表头「15、固定资产」→ 附注节「五、15」
 * - note_template_soe.json → section_number「八、22」固定资产
 * - note_template_listed 偶见「五、22」（历史编号），跳转时兼容识别
 */
export type H1DisclosureVariant = 'listed' | 'soe'

export const H1_NOTE_SECTION = {
  listed: '五、15',
  soe: '八、22',
} as const satisfies Record<H1DisclosureVariant, string>

export const H1_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国有企业）',
} as const satisfies Record<H1DisclosureVariant, string>

/** 与 note_template_listed tables[].name 一致 */
export const H1_LISTED_SUBTABLE = {
  summary: '固定资产',
  movement: '固定资产情况',
  idle: '暂时闲置的固定资产情况',
  leaseOut: '通过经营租赁租出的固定资产',
  titleCert: '未办妥产权证书的固定资产情况',
  clearing: '固定资产清理',
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

/** 别名：与 G14/F1 命名风格对齐 */
export const isH1ListedStandard = isListedStandard
export const isH1SoeStandard = isSoeStandard

export function isH1DisclosureApplicable(
  variant: H1DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = (applicableStandards || []).map((s) => String(s).trim()).filter(Boolean)
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveH1CurrentStandard(
  variant: H1DisclosureVariant,
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

export function resolveH1NoteSectionTarget(
  variant: H1DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): { sectionId: string; sheetName: string; currentStandard: string; chipValue: string } | null {
  if (!isH1DisclosureApplicable(variant, applicableStandards)) return null
  const sectionId = H1_NOTE_SECTION[variant]
  return {
    sectionId,
    sheetName: H1_DISCLOSURE_SHEET_NAME[variant],
    currentStandard: resolveH1CurrentStandard(variant, applicableStandards),
    chipValue: `Note:${sectionId}`,
  }
}

export function isH1FixedAssetNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === H1_NOTE_SECTION.soe || s.startsWith('八、22')) return true
  if (s === H1_NOTE_SECTION.listed || s.startsWith('五、15')) return true
  // 历史/模板编号兼容
  if (s === '五、22' || s.startsWith('五、22')) return true
  if (s === '固定资产' || (s.includes('固定资产') && !s.includes('清理') && !s.includes('在建'))) return true
  return false
}
