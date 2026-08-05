/**
 * F3 应付票据 — 科目码单一真源（K2 范式）。
 *
 * 运行态一律取 render 下发的 `tb_source_codes.gross_standard`，
 * 常量只作兜底与展示。
 *
 * spec: f-cycle-four-table-extraction-and-disclosure-completion R1
 */

import type { TbSourceCodes } from './shared/tbSourceCodes'

/** 报表行编码（report_config 权威） */
export const F3_REPORT_ROW_CODE = 'BS-044'

/** 兜底标准科目码（仅 report_config 解析失败时用） */
export const F3_GROSS_FALLBACK_STANDARD = '2201'

/** 从 render 下发的 tb_source_codes 取运行态科目码（展示 / 请求用） */
export function f3AccountCode(src?: TbSourceCodes | null): string {
  return src?.gross_standard?.[0] ?? F3_GROSS_FALLBACK_STANDARD
}

/** 从 render 下发取查询科目码集（前缀匹配用） */
export function f3GrossQueryCodes(src?: TbSourceCodes | null): string[] {
  const codes = src?.gross
  if (codes && codes.length > 0) return codes
  return [F3_GROSS_FALLBACK_STANDARD]
}
