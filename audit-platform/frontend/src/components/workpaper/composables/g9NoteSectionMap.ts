/**
 * G9 其他非流动金融资产（报表科目 1519）↔ 附注章节映射
 *
 * 权威 note_template_variant_matrix.json · account_key=qi_ta_fei_liu_dong_jin_rong_zi_chan：
 * - 上市 → 五、20
 * - 国企 → 八、20
 * 报表行：BS-035（cell_mapping / report_row_note_mapping）
 */
export type G9DisclosureVariant = 'listed' | 'soe'

export const G9_SOE_NOTE_SECTION = '八、20'

export const G9_NOTE_SECTION = {
  listed: '五、20',
  soe: G9_SOE_NOTE_SECTION,
} as const satisfies Record<G9DisclosureVariant, string>

export const G9_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<G9DisclosureVariant, string>

/**
 * 子表名 —— 与 `note_template_*.json` `tables[].name` 逐字一致。
 *
 * 🔴 修正史：上市侧原写 `项  目`，而模板该表名是表头首格 `种  类`（两者都不对：
 * 前者压根不存在 → 孤儿子表；后者是列名当表名）。已由
 * `backend/scripts/fix/fix_note_g_cycle_structure.py` 把模板表名对齐为科目名。
 */
export const G9_MAIN_SUBTABLE = {
  listed: '其他非流动金融资产',
  soe: '其他非流动金融资产',
} as const satisfies Record<G9DisclosureVariant, string>

export { G9_ACCOUNT_CODE } from './g9Constants'

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

export function isG9DisclosureApplicable(
  variant: G9DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = applicableStandards ?? []
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveG9CurrentStandard(
  variant: G9DisclosureVariant,
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

export interface G9NoteSectionTarget {
  variant: G9DisclosureVariant
  sectionId: string
  sheetName: string
  currentStandard: string
  chipValue: string
}

export function resolveG9NoteSectionTarget(
  variant: G9DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): G9NoteSectionTarget | null {
  if (!isG9DisclosureApplicable(variant, applicableStandards)) return null
  const sectionId = G9_NOTE_SECTION[variant]
  return {
    variant,
    sectionId,
    sheetName: G9_DISCLOSURE_SHEET_NAME[variant],
    currentStandard: resolveG9CurrentStandard(variant, applicableStandards),
    chipValue: `Note:${sectionId}`,
  }
}

export function isG9OtherNoncurrentFinancialNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  if (s === G9_NOTE_SECTION.listed || s.startsWith('五、20')) return true
  if (s === G9_SOE_NOTE_SECTION || s.startsWith('八、20')) return true
  return false
}
