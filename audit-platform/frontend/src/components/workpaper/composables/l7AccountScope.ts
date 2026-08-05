/**
 * L7 其他非流动负债 —— 科目口径**单一真源**（零 Vue 依赖）。
 *
 * 🔴 **宁缺勿造**：report_config `BS-071/BS-097 = TB('2901')` 与
 * `BS-070/BS-096 递延所得税负债` 撞码；`2801` 是预计负债；
 * 客户科目表无名称含「其他非流动负债」的科目。
 * → 不设兜底码、不预填，溯源面板显示「本项目无此科目」。
 *
 * 🔴 改造前硬编码 `2801`（预计负债），把 K5 预计负债循环的钱拿进来。
 *
 * spec: .kiro/specs/l-cycle-four-table-extraction-and-disclosure-alignment/ R2.2, R2.3
 */
import type { TbSourceCodes } from './shared/tbSourceCodes'

/** 报表行次（上市 BS-071 / 国企 BS-097） */
export const L7_REPORT_ROW_CODE = 'BS-071'

/**
 * 🔴 **故意不设兜底码** —— 宁缺勿造。
 * report_config 该行引用 `2901`（递延所得税负债），不是其他非流动负债。
 */
export const L7_GROSS_FALLBACK_STANDARD: null = null

/** 科目中文名 */
export const L7_ACCOUNT_NAME = '其他非流动负债'

/**
 * 🔴 曾被误当作其他非流动负债的科目 —— 守卫用。
 * `2801` = 预计负债（K5 循环）；`2901` = 递延所得税负债（N1/N3 循环）。
 */
export const L7_WRONG_LEGACY_ACCOUNTS = ['2801', '2901'] as const

/**
 * L7 不支持四表预填（宁缺勿造），该函数恒返空数组。
 * 前端据此显示「本项目无可映射科目」而非显示 0。
 */
export function l7GrossQueryCodes(_src?: TbSourceCodes | null): string[] {
  return []
}

/**
 * L7 是否支持预填。恒 false —— 后端 `prefill_supported=False`。
 */
export function isL7PrefillSupported(_src?: TbSourceCodes | null): boolean {
  return false
}
