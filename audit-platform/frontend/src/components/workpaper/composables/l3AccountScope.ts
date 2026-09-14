/**
 * L3 长期借款 —— 科目口径**单一真源**（零 Vue 依赖）。
 *
 * report_config 实证（四准则一致）::
 *
 *     BS-061 长期借款 = TB('2501','期末余额')
 *
 * 🔴 2026-08-05 更正注释：原写「BS-061 / BS-085」，而 `BS-085` 实为**其他综合收益**
 * `TB('4003')`（M9 的行）。长期借款在两套准则下**共用 BS-061**，soe 侧没有独立行号。
 * 后端 `l_cycle_extraction/account_scope.py` 的 `row_code_soe` 已同步改正为 BS-061；
 * 本文件导出的常量一直是 BS-061（值本就对，错的只是注释）—— 这类「结论错、取值对」
 * 的注释最危险，会诱导下个会话把后端「改回」BS-085。
 *
 * 🔴 L3 需拆分「一年内到期」部分（`2501.02` 一年内到期的长期借款），
 * 后端 render 输出 `current_portion_codes` 供前端消费。
 *
 * spec: .kiro/specs/l-cycle-four-table-extraction-and-disclosure-alignment/ R1, R3, R4
 */
import { tbQueryCodes, type TbSourceCodes } from './shared/tbSourceCodes'

/** 报表行次（上市与国企共用 BS-061） */
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
