/**
 * L2 应付利息 —— 科目口径**单一真源**（零 Vue 依赖）。
 *
 * report_config 实证::
 *
 *     BS-054「其中：应付利息」—— 仅 listed 两条，formula 均为 None → 必然回退兜底码。
 *     国企准则无此独立报表行。
 *
 * account_chart 实证 `2231 应付利息`。
 *
 * 🔴 L2 无独立附注章节 → 推 K3 §五、42 / §八、42 的子表「应付利息」。
 *
 * spec: .kiro/specs/l-cycle-four-table-extraction-and-disclosure-alignment/ R1
 */
import { tbQueryCodes, type TbSourceCodes } from './shared/tbSourceCodes'

/** 报表行次（仅 listed，formula=None → 兜底） */
export const L2_REPORT_ROW_CODE = 'BS-054'

/** 原值兜底标准码 */
export const L2_GROSS_FALLBACK_STANDARD = '2231'

/** 科目中文名 */
export const L2_ACCOUNT_NAME = '应付利息'

/** 试算平衡表 / 余额表查询口径 */
export function l2GrossQueryCodes(src: TbSourceCodes | null | undefined): string[] {
  return tbQueryCodes(src?.gross_standard, L2_GROSS_FALLBACK_STANDARD)
}

/** 单一科目码 */
export function l2AccountCode(src?: TbSourceCodes | null): string {
  return l2GrossQueryCodes(src)[0]
}
