/**
 * G3 应收股利披露表 ↔ 附注章节映射
 *
 * 与 G2 共用合计数归集：Excel「详见 M1-1」→ wp:K1-1 + Note:五、8 / 八、9
 * （其他应收款汇总表含应收利息、应收股利、其他应收款项）
 */
import {
  G2_COMBINED_DISCLOSURE_INDEX,
  G2_NOTE_SECTION,
  isG2DisclosureApplicable,
  isG2ListedStandard,
  isG2SoeStandard,
  resolveG2CurrentStandard,
  resolveG2NoteSectionTarget,
  type G2DisclosureVariant,
  type G2NoteSectionTarget,
} from './g2NoteSectionMap'

export type G3DisclosureVariant = G2DisclosureVariant

export const G3_NOTE_SECTION = G2_NOTE_SECTION
export const G3_COMBINED_DISCLOSURE_INDEX = G2_COMBINED_DISCLOSURE_INDEX
export { G3_ACCOUNT_CODE } from './g3Constants'


export const G3_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国企）',
} as const satisfies Record<G3DisclosureVariant, string>

export const isG3ListedStandard = isG2ListedStandard
export const isG3SoeStandard = isG2SoeStandard
export const isG3DisclosureApplicable = isG2DisclosureApplicable
export const resolveG3CurrentStandard = resolveG2CurrentStandard

export function resolveG3NoteSectionTarget(
  variant: G3DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): G2NoteSectionTarget | null {
  const base = resolveG2NoteSectionTarget(variant, applicableStandards)
  if (!base) return null
  return {
    ...base,
    sheetName: G3_DISCLOSURE_SHEET_NAME[variant],
  }
}
