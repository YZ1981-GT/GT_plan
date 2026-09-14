/**
 * L5 长期应付款 —— 科目口径**单一真源**（零 Vue 依赖）。
 *
 * report_config 实证（四准则一致）::
 *
 *     BS-066 / BS-092 长期应付款 = TB('2701','期末余额')
 *
 * 🔴 L5 需拆分「一年内到期」部分（`2701.99` 一年内到期的长期应付款），
 * 后端 render 输出 `current_portion_codes` 供前端消费。
 *
 * spec: .kiro/specs/l-cycle-four-table-extraction-and-disclosure-alignment/ R1, R3, R4
 */
import { tbQueryCodes, type TbSourceCodes } from './shared/tbSourceCodes'

/** 报表行次（上市 BS-066 / 国企 BS-092） */
export const L5_REPORT_ROW_CODE = 'BS-066'

/** 原值兜底标准码 */
export const L5_GROSS_FALLBACK_STANDARD = '2701'

/** 科目中文名 */
export const L5_ACCOUNT_NAME = '长期应付款'

/** 试算平衡表 / 余额表查询口径 */
export function l5GrossQueryCodes(src: TbSourceCodes | null | undefined): string[] {
  return tbQueryCodes(src?.gross_standard, L5_GROSS_FALLBACK_STANDARD)
}

/** 单一科目码 */
export function l5AccountCode(src?: TbSourceCodes | null): string {
  return l5GrossQueryCodes(src)[0]
}
