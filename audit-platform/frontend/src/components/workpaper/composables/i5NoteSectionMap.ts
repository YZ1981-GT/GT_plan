/**
 * I5 其他非流动资产披露表 ↔ 附注章节冻结映射
 *
 * 权威来源：
 * - note_template_listed「五、31」其他非流动资产（表名：其他非流动资产）
 * - note_template_soe「八、32」其他非流动资产（表名：其他非流动资产）
 * - 源 xlsx「附注披露（上市公司/国有企业）」：上市 账面余额/减值/账面价值 对比表；国企 期末/年初
 */
export type I5DisclosureVariant = 'listed' | 'soe'

export const I5_NOTE_SECTION = {
  listed: '五、31',
  soe: '八、32',
} as const satisfies Record<I5DisclosureVariant, string>

export const I5_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露（上市公司）',
  soe: '附注披露（国有企业）',
} as const satisfies Record<I5DisclosureVariant, string>

/** 与 note_template tables[].name 一致 */
export const I5_LISTED_SUBTABLE = {
  main: '其他非流动资产',
} as const

export const I5_SOE_SUBTABLE = {
  main: '其他非流动资产',
} as const

/** I5 无旧名需清理（表名未变更） */
export const I5_LEGACY_OBSOLETE_TABLES: readonly string[] = []

/** 源表默认分类（注：不存在的项目请删除） */
export const I5_DEFAULT_DISCLOSURE_CATEGORIES = [
  '预付土地出让金',
  '预付工程款',
  '预付房屋、设备款',
  '无形资产预付款',
  '预付投资款',
  '委托贷款',
  '合同资产',
  '合同取得成本',
  '合同履约成本',
  '应收退货成本',
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

export function isI5DisclosureApplicable(
  variant: I5DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = (applicableStandards || []).map((s) => String(s).trim()).filter(Boolean)
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveI5CurrentStandard(
  variant: I5DisclosureVariant,
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

export function resolveI5NoteSectionTarget(variant: I5DisclosureVariant): {
  sectionId: string
  chipValue: string
} {
  const sectionId = I5_NOTE_SECTION[variant]
  return { sectionId, chipValue: `Note:${sectionId}` }
}

export function isI5OtherNoncurrentNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、31' || s.startsWith('五、31')) return true
  if (s === '八、32' || s.startsWith('八、32')) return true
  if (s === '其他非流动资产' || s.includes('其他非流动资产')) return true
  return false
}
