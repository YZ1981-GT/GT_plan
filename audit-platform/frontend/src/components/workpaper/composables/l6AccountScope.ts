/**
 * L6 专项应付款 —— 科目口径**单一真源**（零 Vue 依赖）。
 *
 * 🔴 改造前硬编码 `2601`（租赁负债，H 循环），`tb_balance` 该前缀 **0 行** → 取数恒空。
 * account_chart 实证 `2711 专项应付款`（3 个项目有该科目）。
 * report_config 无「专项应付款」独立报表行（并入长期应付款 BS-066/BS-092 披露）。
 *
 * spec: .kiro/specs/l-cycle-four-table-extraction-and-disclosure-alignment/ R2.1
 */
import { tbQueryCodes, type TbSourceCodes } from './shared/tbSourceCodes'

/** L6 无独立报表行 → 不设报表行常量 */
export const L6_REPORT_ROW_CODE: null = null

/** 原值兜底标准码（纠正 2601→2711） */
export const L6_GROSS_FALLBACK_STANDARD = '2711'

/** 科目中文名 */
export const L6_ACCOUNT_NAME = '专项应付款'

/**
 * 🔴 曾被误当作专项应付款的科目 —— 守卫用（源码不得再出现该字面量作 L6 科目码）。
 * `2601` = 租赁负债（H8 使用权资产 / H9 租赁负债循环）。
 */
export const L6_WRONG_LEGACY_ACCOUNT = '2601'

/** 试算平衡表 / 余额表查询口径 */
export function l6GrossQueryCodes(src: TbSourceCodes | null | undefined): string[] {
  return tbQueryCodes(src?.gross_standard, L6_GROSS_FALLBACK_STANDARD)
}

/** 单一科目码 */
export function l6AccountCode(src?: TbSourceCodes | null): string {
  return l6GrossQueryCodes(src)[0]
}
