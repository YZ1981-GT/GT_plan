/**
 * H6 固定资产清理披露表 ↔ 附注章节映射
 *
 * H6 披露表是 H1「固定资产」附注中「固定资产清理」子表的编制桥：
 * - 上市 → 附注「五、15」子表「固定资产清理」
 * - 国企 → 附注「八、22」子表「固定资产清理」
 * 合计数（固定资产+清理）仍以 H1-1 / H1 附注汇总为准。
 */
import {
  H1_DISCLOSURE_SHEET_NAME,
  H1_LISTED_SUBTABLE,
  H1_NOTE_SECTION,
  isH1DisclosureApplicable,
  resolveH1CurrentStandard,
  type H1DisclosureVariant,
} from './h1NoteSectionMap'

export type H6DisclosureVariant = H1DisclosureVariant

export const H6_NOTE_SECTION = H1_NOTE_SECTION

export const H6_DISCLOSURE_SHEET_NAME = {
  listed: '附注披露信息（上市公司）',
  soe: '附注披露信息（国有企业）',
} as const satisfies Record<H6DisclosureVariant, string>

/** 推送至附注的子表名（与 note_template / H1 一致） */
export const H6_CLEARING_SUBTABLE = H1_LISTED_SUBTABLE.clearing // '固定资产清理'

/** 汇总表名（用于浅合并刷新「固定资产清理」行） */
export const H6_SUMMARY_SUBTABLE = H1_LISTED_SUBTABLE.summary // '固定资产'

export const isH6DisclosureApplicable = isH1DisclosureApplicable
export const resolveH6CurrentStandard = resolveH1CurrentStandard

export function resolveH6NoteSectionTarget(
  variant: H6DisclosureVariant,
  applicableStandards: readonly string[] | null | undefined,
): { sectionId: string; sheetName: string; currentStandard: string; chipValue: string } | null {
  if (!isH6DisclosureApplicable(variant, applicableStandards)) return null
  const sectionId = H6_NOTE_SECTION[variant]
  return {
    sectionId,
    sheetName: H6_DISCLOSURE_SHEET_NAME[variant],
    currentStandard: resolveH6CurrentStandard(variant, applicableStandards),
    chipValue: `Note:${sectionId}`,
  }
}

/** 编制提示：合计数详见 H1 */
export const H6_XREF_H1 = '【固定资产与固定资产清理的合计数披露详见H1-1】'

export const H6_CLEARING_PROGRESS_HINT =
  '（说明转入固定资产清理起始时间已超过1年的固定资产清理进展情况）'

/** H1 披露表 sheet 名（跨底稿芯片） */
export const H6_H1_DISCLOSURE_SHEET = H1_DISCLOSURE_SHEET_NAME
