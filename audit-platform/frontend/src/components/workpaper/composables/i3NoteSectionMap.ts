/**
 * I3 商誉披露表 ↔ 附注章节冻结映射
 *
 * 权威来源：
 * - note_template_listed「五、28」商誉（表名：商誉账面原值 / 商誉减值准备）
 * - note_template_soe「八、29」商誉（表名：（1）商誉账面原值 / （2）商誉减值准备）
 * - 源 xlsx「附注披露（上市公司/国有企业）」
 */
export type I3DisclosureVariant = 'listed' | 'soe'

export const I3_NOTE_SECTION = {
  listed: '五、28',
  soe: '八、29',
} as const satisfies Record<I3DisclosureVariant, string>

export const I3_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露（上市公司）',
  soe: '附注披露（国有企业）',
} as const satisfies Record<I3DisclosureVariant, string>

/** 与 note_template tables[].name 一致 */
export const I3_LISTED_SUBTABLE = {
  bookValue: '商誉账面原值',
  impairment: '商誉减值准备',
  assumptions: '资产组的可收回金额是依据管理层编制的五年期预测，采用未来现金流量折合现值计算。超过该五年期的现金流量采用以下所述的估计增长率作出推算。采用未来现金流量折现方法所运用的假设主要包括：',
  performance: '业绩承诺完成及对应商誉减值情况如下：',
} as const

export const I3_SOE_SUBTABLE = {
  bookValue: '（1）商誉账面原值',
  impairment: '（2）商誉减值准备',
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

export function isI3DisclosureApplicable(
  variant: I3DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = (applicableStandards || []).map((s) => String(s).trim()).filter(Boolean)
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveI3CurrentStandard(
  variant: I3DisclosureVariant,
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

export function resolveI3NoteSectionTarget(variant: I3DisclosureVariant): {
  sectionId: string
  chipValue: string
} {
  const sectionId = I3_NOTE_SECTION[variant]
  return { sectionId, chipValue: `Note:${sectionId}` }
}

export function isI3GoodwillNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、28' || s.startsWith('五、28')) return true
  if (s === '八、29' || s.startsWith('八、29')) return true
  if (s === '商誉' || (s.includes('商誉') && !s.includes('减值损失'))) return true
  return false
}
