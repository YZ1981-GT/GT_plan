/**
 * I5 其他非流动资产 —— 科目口径**单一真源**（零 Vue 依赖）。
 *
 * 报表行：BS-040（上市） / BS-050（国企）
 * 兜底标准码：（空）—— 🔴 无标准科目
 * 🔴 运行态一律取 render 下发的 `tb_source_codes`，常量只作兜底+展示。
 */
import type { TbSourceCodes } from './shared/tbSourceCodes'

export const I5_REPORT_ROW_CODE = { listed: 'BS-040', soe: 'BS-050' } as const

/** 原值兜底标准码：空串（无标准科目） */
export const I5_GROSS_FALLBACK_STANDARD = ''

/**
 * 原值查询口径（标准码集）。
 * 运行态取 render 下发的 `tb_source_codes.gross`；无溯源且无兜底码时返回空数组。
 */
export function i5GrossQueryCodes(src?: TbSourceCodes | null): string[] {
  const codes = (src?.gross_standard || []).filter(Boolean)
  return codes.length ? codes : []
}

/** 单一科目码（回写 TB / EventBus 用）；无溯源时返回空串 */
export function i5AccountCode(src?: TbSourceCodes | null): string {
  const codes = i5GrossQueryCodes(src)
  return codes[0] || ''
}
