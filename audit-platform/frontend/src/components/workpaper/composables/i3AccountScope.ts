/**
 * I3 商誉 —— 科目口径**单一真源**（零 Vue 依赖）。
 *
 * 报表行：BS-037（上市） / BS-047（国企）
 * 兜底标准码：1711（account_chart 实证）
 * + 减值 IMP-017（无标准科目）
 * 🔴 运行态一律取 render 下发的 `tb_source_codes`，常量只作兜底+展示。
 */
import { tbQueryCodes, type TbSourceCodes } from './shared/tbSourceCodes'

export const I3_REPORT_ROW_CODE = { listed: 'BS-037', soe: 'BS-047' } as const

/** 原值兜底标准码 */
export const I3_GROSS_FALLBACK_STANDARD = '1711'

/**
 * 原值查询口径（标准码集）。
 * 运行态取 render 下发的 `tb_source_codes.gross`，常量只作兜底。
 */
export function i3GrossQueryCodes(src?: TbSourceCodes | null): string[] {
  return tbQueryCodes(src?.gross_standard, I3_GROSS_FALLBACK_STANDARD)
}

/** 单一科目码（回写 TB / EventBus 用）；溯源缺失时回退 1711 */
export function i3AccountCode(src?: TbSourceCodes | null): string {
  const codes = i3GrossQueryCodes(src)
  return codes[0] || I3_GROSS_FALLBACK_STANDARD
}
