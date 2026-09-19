/**
 * L8 财务费用 —— 科目口径**单一真源**（零 Vue 依赖）。
 *
 * report_config 实证（四准则一致）::
 *
 *     IS-007 / IS-025 财务费用 = TB('6603','本期发生额')
 *
 * 🔴 **损益类**，取数口径 = `trial_balance` 本期发生额，
 * 兜底 `tb_balance.debit_amount`（不用 `debit - credit`，后者在含年末结转损益
 * 的全年账上结构性恒为 0）。
 *
 * spec: .kiro/specs/l-cycle-four-table-extraction-and-disclosure-alignment/ R2.4, R2.5
 */
import { tbQueryCodes, type TbSourceCodes } from './shared/tbSourceCodes'

/** 报表行次（上市 IS-007 / 国企 IS-025） */
export const L8_REPORT_ROW_CODE = 'IS-007'

/** 原值兜底标准码 */
export const L8_GROSS_FALLBACK_STANDARD = '6603'

/** 科目中文名 */
export const L8_ACCOUNT_NAME = '财务费用'

/** 损益类标识（取本期发生额而非余额） */
export const L8_IS_INCOME = true

/** 试算平衡表 / 余额表查询口径 */
export function l8GrossQueryCodes(src: TbSourceCodes | null | undefined): string[] {
  return tbQueryCodes(src?.gross_standard, L8_GROSS_FALLBACK_STANDARD)
}

/** 单一科目码 */
export function l8AccountCode(src?: TbSourceCodes | null): string {
  return l8GrossQueryCodes(src)[0]
}
