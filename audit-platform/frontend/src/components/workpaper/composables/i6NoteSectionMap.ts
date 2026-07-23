/**
 * I6 研发费用披露表 ↔ 附注章节冻结映射
 *
 * 权威来源：
 * - note_template_listed「五、66」研发费用（表名：研发费用（按费用性质列示））
 * - note_template_soe「八、67」研发费用（表名：研发费用）
 * - 源 xlsx「附注披露（上市公司/国有企业）」
 */
export type I6DisclosureVariant = 'listed' | 'soe'

export const I6_NOTE_SECTION = {
  listed: '五、66',
  soe: '八、67',
} as const satisfies Record<I6DisclosureVariant, string>

export const I6_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露（上市公司）',
  soe: '附注披露（国有企业）',
} as const satisfies Record<I6DisclosureVariant, string>

/** 与 note_template tables[].name 一致 */
export const I6_LISTED_SUBTABLE = {
  expenseByNature: '研发费用（按费用性质列示）',
} as const

export const I6_SOE_SUBTABLE = {
  expenseByNature: '研发费用',
} as const

/** 披露默认费用性质（对齐附注模板首行） */
export const I6_DEFAULT_DISCLOSURE_CATEGORIES = [
  '人工费',
  '材料费',
  '水电燃气费',
  '折旧费',
  '无形资产摊销',
  '设计费',
  '装备调试费',
  '委外研发费',
  '其他费用',
] as const

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

export function isI6DisclosureApplicable(
  variant: I6DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = (applicableStandards || []).map((s) => String(s).trim()).filter(Boolean)
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveI6CurrentStandard(
  variant: I6DisclosureVariant,
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

export function resolveI6NoteSectionTarget(variant: I6DisclosureVariant): {
  sectionId: string
  chipValue: string
} {
  const sectionId = I6_NOTE_SECTION[variant]
  return { sectionId, chipValue: `Note:${sectionId}` }
}

export function isI6RdExpenseNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、66' || s.startsWith('五、66')) return true
  if (s === '八、67' || s.startsWith('八、67')) return true
  if (s.includes('研发费用') && !s.includes('开发支出')) return true
  return false
}
