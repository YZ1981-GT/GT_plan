/**
 * H7 生产性生物资产（1621）披露表 ↔ 附注章节冻结映射
 *
 * 权威来源：
 * - note_template_listed「五、24」生产性生物资产
 * - note_template_soe「八、24」生产性生物资产
 * - note_template_variant_matrix.json `sheng_chan_xing_sheng_wu_zi_chan`
 * - 源 xlsx tab 名（🔴 国企是「国有企业」，与 H9/H10 的「国企」不同，禁套用）
 *
 * spec: h7-biological-assets-disclosure-rebuild (Task 4)
 */
export type H7DisclosureVariant = 'listed' | 'soe'

/*
 * 🔴 章节号字面量必须**内联**在下面的对象里，且对象体内**不要写注释**：
 * `backend/scripts/gen_note_wp_sync_registry.py` 用正则从对象体抽 `listed: '…'`，
 * 写成标识符引用会让 H7 整条从 registry 消失；对象体内的注释若含 `listed: '…'`
 * 字样会被优先抓到（H10 两种情况都实测踩过）。
 */
export const H7_NOTE_SECTION = {
  listed: '五、24',
  soe: '八、24',
} as const satisfies Record<H7DisclosureVariant, string>

/** 逐字等于源 xlsx tab 名 */
export const H7_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国有企业）',
} as const satisfies Record<H7DisclosureVariant, string>

/** 与 note_template tables[].name 逐字一致 */
export const H7_LISTED_SUBTABLE = {
  cost: '（1）以成本计量',
  fair: '（2）以公允价值计量',
} as const

export const H7_SOE_SUBTABLE = {
  cost: '以成本计量',
  fair: '以公允价值计量',
} as const

/**
 * 改版前的旧表名 —— 上市第 2 张表原名是表头首格泄漏 `项  目`。
 * 正名后须进 `_removed_table_keys`，防附注残留孤儿表。
 */
export const H7_LEGACY_OBSOLETE_TABLES: readonly string[] = ['项  目']

export function isListedStandard(s: string): boolean {
  const x = String(s).toLowerCase()
  return x.includes('listed') || x.includes('上市')
    || x === 'listed_standalone' || x === 'listed_consolidated'
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

export function isH7DisclosureApplicable(
  variant: H7DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = (applicableStandards || []).map((s) => String(s).trim()).filter(Boolean)
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveH7CurrentStandard(
  variant: H7DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): string {
  const list = (applicableStandards || []).map((s) => String(s).toLowerCase())
  if (variant === 'listed') {
    if (list.some((s) => s === 'listed_consolidated'
      || (s.includes('listed') && s.includes('consol')))) {
      return 'listed_consolidated'
    }
    return 'listed_standalone'
  }
  if (list.some((s) => s === 'soe_consolidated'
    || (s.includes('soe') && s.includes('consol')))) {
    return 'soe_consolidated'
  }
  return 'soe_standalone'
}

export function resolveH7NoteSectionTarget(variant: H7DisclosureVariant): {
  sectionId: string
  chipValue: string
} {
  const sectionId = H7_NOTE_SECTION[variant]
  return { sectionId, chipValue: `Note:${sectionId}` }
}

export function isH7BiologicalNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === '五、24' || s.startsWith('五、24')) return true
  if (s === '八、24' || s.startsWith('八、24')) return true
  if (s.includes('生产性生物资产')) return true
  return false
}
