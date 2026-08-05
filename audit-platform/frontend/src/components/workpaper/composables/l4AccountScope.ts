/**
 * L4 应付债券 —— 科目口径**单一真源**（零 Vue 依赖）。
 *
 * report_config 实证（四准则一致）::
 *
 *     BS-062 / BS-086 应付债券 = TB('2502','期末余额')
 *
 * 🔴 L4 需拆分「一年内到期」部分（`2502` 子科目按名称识别），
 * 后端 render 输出 `current_portion_codes` 供前端消费。
 *
 * 🔴 `BS-057/BS-080 一年内到期的非流动负债 = TB('2502')` 与应付债券撞码，
 * 本 spec 改从子科目按名称识别而非引用该报表行。
 *
 * spec: .kiro/specs/l-cycle-four-table-extraction-and-disclosure-alignment/ R1, R3, R4
 */
import { tbQueryCodes, type TbSourceCodes } from './shared/tbSourceCodes'

/** 报表行次（上市 BS-062 / 国企 BS-086） */
export const L4_REPORT_ROW_CODE = 'BS-062'

/** 原值兜底标准码 */
export const L4_GROSS_FALLBACK_STANDARD = '2502'

/** 科目中文名 */
export const L4_ACCOUNT_NAME = '应付债券'

/** 试算平衡表 / 余额表查询口径 */
export function l4GrossQueryCodes(src: TbSourceCodes | null | undefined): string[] {
  return tbQueryCodes(src?.gross_standard, L4_GROSS_FALLBACK_STANDARD)
}

/** 单一科目码 */
export function l4AccountCode(src?: TbSourceCodes | null): string {
  return l4GrossQueryCodes(src)[0]
}
