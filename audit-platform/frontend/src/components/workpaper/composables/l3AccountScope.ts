/**
 * L3 长期借款 —— 科目口径**单一真源**（零 Vue 依赖）。
 *
 * report_config 实证（四准则一致）::
 *
 *     BS-061 / BS-085 长期借款 = TB('2501','期末余额')
 *
 * 🔴 L3 需拆分「一年内到期」部分（`2501.02` 一年内到期的长期借款），
 * 后端 render 输出 `current_portion_codes` 供前端消费。
 *
 * spec: .kiro/specs/l-cycle-four-table-extraction-and-disclosure-alignment/ R1, R3, R4
 */
import { tbQueryCodes, type TbSourceCodes } from './shared/tbSourceCodes'

/** 报表行次（上市 BS-061 / 国企 BS-085） */
export const L3_REPORT_ROW_CODE = 'BS-061'

/** 原值兜底标准码 */
export const L3_GROSS_FALLBACK_STANDARD = '2501'

/** 科目中文名 */
export const L3_ACCOUNT_NAME = '长期借款'

/** 试算平衡表 / 余额表查询口径 */
export function l3GrossQueryCodes(src: TbSourceCodes | null | undefined): string[] {
  return tbQueryCodes(src?.gross_standard, L3_GROSS_FALLBACK_STANDARD)
}

/** 单一科目码 */
export function l3AccountCode(src?: TbSourceCodes | null): string {
  return l3GrossQueryCodes(src)[0]
}
