/**
 * G5 长期应收款披露表 ↔ 附注章节映射
 *
 * 权威：`backend/data/note_template_variant_matrix.json`
 *   chang_qi_ying_shou_kuan → listed 五、16 / soe 八、17
 *
 * 子表名与 `note_template_*.json` 逐字一致（由
 * `backend/scripts/fix/fix_note_g_cycle_structure.py` 按**权威模板**
 * `backend/wp_templates/G/G5 长期应收款.xlsx` 对齐后固定）。
 *
 * 🔴 两版表集合差异很大（不是简单的措辞不同）：
 * - 上市 8 张表（性质 / 坏账准备计提情况 / 按单项 + 续 / 组合计提项目 / 变动 / 核销 ×2）
 * - 国企只 3 张表（性质 / 终止确认 / 继续涉入）—— 「坏账准备计提情况」在国企附注模版里
 *   **只有交叉引用**（「披露格式参考附注八、5 应收账款 / 八、8（3）其他应收款」）、没有表，
 *   故底稿侧的坏账准备系列表不推附注（宁缺勿造）。
 *
 * spec: .kiro/specs/disclosure-sync-path-buildout/ Task 2.2
 */
export type G5DisclosureVariant = 'listed' | 'soe'

export const G5_NOTE_SECTION = {
  listed: '五、16',
  soe: '八、17',
} as const satisfies Record<G5DisclosureVariant, string>

/** 源 xlsx 真实 tab 名（非 wp_code 形态合成标识、非短名） */
export const G5_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<G5DisclosureVariant, string>

/** 上市子表名 */
export const G5_LISTED_SUBTABLE = {
  nature: '长期应收款按性质披露',
  provision: '坏账准备计提情况',
  individualEnd: '按单项计提坏账准备',
  individualPrior: '按单项计提坏账准备（续：上年年末余额）',
  /** 组合表骨架名；实际每个组合一张表，名为 `组合计提项目：{组合名}` */
  portfolioSeed: '组合计提项目：XXX',
  movement: '本期计提、收回或转回的坏账准备情况',
  writeoff: '本期实际核销的长期应收款',
  writeoffDetail: '重要的长期应收款核销情况（逐项披露）',
} as const

/** 国企子表名 */
export const G5_SOE_SUBTABLE = {
  nature: '长期应收款按性质披露',
  derecognition: '终止确认的长期应收款',
  continuing: '转移长期应收款且继续涉入形成的资产、负债的金额',
} as const

/** 动态组合表名前缀（与 D2 同款命名空间约定） */
export const G5_PORTFOLIO_PREFIX = '组合计提项目：'

export { G5_ACCOUNT_CODE } from './g5Constants'

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

/** 未声明适用准则时两个变体都放行（与 G3/G9/G11/G12 同口径） */
export function isG5DisclosureApplicable(
  variant: G5DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): boolean {
  const list = applicableStandards ?? []
  if (list.length === 0) return true
  const hasListed = list.some(isListedStandard)
  const hasSoe = list.some(isSoeStandard)
  if (!hasListed && !hasSoe) return true
  return variant === 'listed' ? hasListed : hasSoe
}

export function resolveG5CurrentStandard(
  variant: G5DisclosureVariant,
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

export interface G5NoteSectionTarget {
  variant: G5DisclosureVariant
  sectionId: string
  sheetName: string
  currentStandard: string
  chipValue: string
}

export function resolveG5NoteSectionTarget(
  variant: G5DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): G5NoteSectionTarget | null {
  if (!isG5DisclosureApplicable(variant, applicableStandards)) return null
  const sectionId = G5_NOTE_SECTION[variant]
  return {
    variant,
    sectionId,
    sheetName: G5_DISCLOSURE_SHEET_NAME[variant],
    currentStandard: resolveG5CurrentStandard(variant, applicableStandards),
    chipValue: `Note:${sectionId}`,
  }
}

export function isG5LongTermReceivableNoteSection(noteSection: string): boolean {
  const s = String(noteSection || '').trim()
  if (!s) return false
  return s.startsWith('五、16') || s.startsWith('八、17')
}
