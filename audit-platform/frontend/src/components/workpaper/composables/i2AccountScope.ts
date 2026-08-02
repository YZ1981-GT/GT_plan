/**
 * I2 开发支出 —— 科目口径**单一真源**（零 Vue 依赖）。
 *
 * 报表行：BS-035（上市） / BS-046（国企）
 * 兜底标准码：1704（account_chart 实证）
 * 🔴 不是 1717（全库不存在）。
 * 🔴 运行态一律取 render 下发的 `tb_source_codes`，常量只作兜底+展示。
 */
import { tbQueryCodes, type TbSourceCodes } from './shared/tbSourceCodes'

export const I2_REPORT_ROW_CODE = { listed: 'BS-035', soe: 'BS-046' } as const

/** 原值兜底标准码 */
export const I2_GROSS_FALLBACK_STANDARD = '1704'

/**
 * 原值查询口径（标准码集）。
 * 运行态取 render 下发的 `tb_source_codes.gross`，常量只作兜底。
 */
export function i2GrossQueryCodes(src?: TbSourceCodes | null): string[] {
  return tbQueryCodes(src?.gross_standard, I2_GROSS_FALLBACK_STANDARD)
}

/** 单一科目码（回写 TB / EventBus 用）；溯源缺失时回退 1704 */
export function i2AccountCode(src?: TbSourceCodes | null): string {
  const codes = i2GrossQueryCodes(src)
  return codes[0] || I2_GROSS_FALLBACK_STANDARD
}
