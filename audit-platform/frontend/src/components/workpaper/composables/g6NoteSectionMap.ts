/**
 * G6 其他债权投资披露表 ↔ 附注章节映射
 *
 * 权威：`backend/data/note_template_variant_matrix.json`
 *   qi_ta_zhai_quan_tou_zi → listed 五、15 / soe 八、16
 *
 * 子表名与 `note_template_*.json` 逐字一致（由
 * `backend/scripts/fix/fix_note_g_cycle_structure.py` 按**权威模板**
 * `backend/wp_templates/G/G6 其他债权投资.xlsx` 对齐后固定）。
 *
 * 🔴 两版差异极大：上市 14 张表；**国企只 2 张**（其他债权投资情况 / 期末重要的其他债权投资），
 * 「减值准备计提情况」在国企附注模版里只有一句「参照附注八、15 债权投资（3）」的交叉引用、无表
 * → 国企侧不推三阶段系列表（宁缺勿造）。
 *
 * spec: .kiro/specs/disclosure-sync-path-buildout/ Task 2.3
 */
export type G6DisclosureVariant = 'listed' | 'soe'

export const G6_NOTE_SECTION = {
  listed: '五、15',
  soe: '八、16',
} as const satisfies Record<G6DisclosureVariant, string>

/** 源 xlsx 真实 tab 名（非 wp_code 形态合成标识、非短名） */
export const G6_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<G6DisclosureVariant, string>

/** 上市 14 张子表名 —— 逐字对齐 note_template §五、15 */
export const G6_LISTED_SUBTABLE = {
  balance: '其他债权投资',
  fairValue: '其他债权投资情况',
  provision: '其他债权投资减值准备本期变动情况',
  importantEnd: '期末重要的其他债权投资',
  importantPrior: '期末重要的其他债权投资（续：上年年末余额）',
  stageMove: '本期计提、收回或转回的减值准备情况',
  writeoff: '本期实际核销的其他债权投资',
  writeoffDetail: '重要的其他债权投资核销情况（逐项披露）',
} as const

/** 六张三阶段减值表名（顺序 = 源模板 R45/R62/R79/R98/R115/R132） */
export const G6_LISTED_STAGE_SUBTABLE: readonly string[] = [
  '期末处于第一阶段的其他债权投资的减值准备',
  '期末处于第二阶段的其他债权投资的减值准备',
  '期末处于第三阶段的其他债权投资的减值准备',
  '上年年末处于第一阶段的其他债权投资的减值准备',
  '上年年末处于第二阶段的其他债权投资的减值准备',
  '上年年末处于第三阶段的其他债权投资的减值准备',
]

/** 国企 2 张子表名 */
export const G6_SOE_SUBTABLE = {
  fairValue: '其他债权投资情况',
  important: '期末重要的其他债权投资',
} as const

function isListedStandard(s: string): boolean {
  const x = String(s).toLowerCase()
  return x.includes('listed') || x.includes('上市')
}

function isSoeStandard(s: string): boolean {
  const x = String(s).toLowerCase()
  return (
    x.includes('soe') || x.includes('state_owned') || x.includes('国企') || x.includes('国有')
  )
}

/** 未声明适用准则时两个变体都放行（与 G3/G5/G9/G11/G12 同口径） */
export function isG6DisclosureApplicable(
  variant: G6DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = applicableStandards ?? []
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveG6CurrentStandard(
  variant: G6DisclosureVariant,
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

export interface G6NoteSectionTarget {
  variant: G6DisclosureVariant
  sectionId: string
  sheetName: string
  currentStandard: string
  chipValue: string
}

export function resolveG6NoteSectionTarget(
  variant: G6DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): G6NoteSectionTarget | null {
  if (!isG6DisclosureApplicable(variant, applicableStandards)) return null
  const sectionId = G6_NOTE_SECTION[variant]
  return {
    variant,
    sectionId,
    sheetName: G6_DISCLOSURE_SHEET_NAME[variant],
    currentStandard: resolveG6CurrentStandard(variant, applicableStandards),
    chipValue: `Note:${sectionId}`,
  }
}
