/**
 * F5 营业成本 — 科目码单一真源（K2 范式）。
 *
 * 运行态一律取 render 下发的 `tb_source_codes.gross_standard`，
 * 常量只作兜底与展示。
 *
 * 注意：F5 的兜底码是区间表达式 `6401~6499`，不是单个前缀。
 * `f5GrossQueryCodes` 在无 render 数据时返回 `['6401~6499']`。
 *
 * spec: f-cycle-four-table-extraction-and-disclosure-completion R1
 */

import type { TbSourceCodes } from './shared/tbSourceCodes'

/** 报表行编码（report_config 权威） */
export const F5_REPORT_ROW_CODE = 'IS-002'

/** 兜底标准科目码（区间口径，仅 report_config 解析失败时用） */
export const F5_GROSS_FALLBACK_STANDARD = '6401~6499'

/** 从 render 下发的 tb_source_codes 取运行态科目码（展示 / 请求用） */
export function f5AccountCode(src?: TbSourceCodes | null): string {
  return src?.gross_standard?.[0] ?? F5_GROSS_FALLBACK_STANDARD
}

/** 从 render 下发取查询科目码集（前缀匹配用） */
export function f5GrossQueryCodes(src?: TbSourceCodes | null): string[] {
  const codes = src?.gross
  if (codes && codes.length > 0) return codes
  return [F5_GROSS_FALLBACK_STANDARD]
}
