/**
 * I6 管理费用 —— 科目口径**单一真源**（零 Vue 依赖）。
 *
 * 报表行：IS-006（上市） / IS-024（国企）
 * 兜底标准码：6604（account_chart 实证）
 * 🔴 不是 6602（管理费用）。
 * 🔴 运行态一律取 render 下发的 `tb_source_codes`，常量只作兜底+展示。
 */
import { tbQueryCodes, type TbSourceCodes } from './shared/tbSourceCodes'

export const I6_REPORT_ROW_CODE = { listed: 'IS-006', soe: 'IS-024' } as const

/** 原值兜底标准码 */
export const I6_GROSS_FALLBACK_STANDARD = '6604'

/**
 * 原值查询口径（标准码集）。
 * 运行态取 render 下发的 `tb_source_codes.gross`，常量只作兜底。
 */
export function i6GrossQueryCodes(src?: TbSourceCodes | null): string[] {
  return tbQueryCodes(src?.gross_standard, I6_GROSS_FALLBACK_STANDARD)
}

/** 单一科目码（回写 TB / EventBus 用）；溯源缺失时回退 6604 */
export function i6AccountCode(src?: TbSourceCodes | null): string {
  const codes = i6GrossQueryCodes(src)
  return codes[0] || I6_GROSS_FALLBACK_STANDARD
}
