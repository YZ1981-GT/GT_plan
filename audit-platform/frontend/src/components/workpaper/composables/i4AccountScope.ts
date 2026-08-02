/**
 * I4 长期待摊费用 —— 科目口径**单一真源**（零 Vue 依赖）。
 *
 * 报表行：BS-038（上市） / BS-048（国企）
 * 兜底标准码：1801（account_chart 实证）
 * 🔴 运行态一律取 render 下发的 `tb_source_codes`，常量只作兜底+展示。
 */
import { tbQueryCodes, type TbSourceCodes } from './shared/tbSourceCodes'

export const I4_REPORT_ROW_CODE = { listed: 'BS-038', soe: 'BS-048' } as const

/** 原值兜底标准码 */
export const I4_GROSS_FALLBACK_STANDARD = '1801'

/**
 * 原值查询口径（标准码集）。
 * 运行态取 render 下发的 `tb_source_codes.gross`，常量只作兜底。
 */
export function i4GrossQueryCodes(src?: TbSourceCodes | null): string[] {
  return tbQueryCodes(src?.gross_standard, I4_GROSS_FALLBACK_STANDARD)
}

/** 单一科目码（回写 TB / EventBus 用）；溯源缺失时回退 1801 */
export function i4AccountCode(src?: TbSourceCodes | null): string {
  const codes = i4GrossQueryCodes(src)
  return codes[0] || I4_GROSS_FALLBACK_STANDARD
}
