/**
 * g5AccountScope — G5 长期应收款科目映射单一真源
 *
 * 运行态优先取 render 下发的 `tb_source_codes.gross_standard`，
 * 常量只作兜底 + 展示。与 k1AccountScope / k2AccountScope / g7AccountScope 同范式。
 *
 * 科目映射真源 = report_config：
 *   BS-023 长期应收款 = TB('1531','期末余额')  四准则一致
 */

import { G5_ACCOUNT_CODE, G5_ACCOUNT_NAME } from './g5Constants'

/** 报表行编码（用于 render 解析） */
export const G5_REPORT_ROW_CODE = 'BS-023'

/** 兜底标准码（resolve 失败时用） */
export const G5_GROSS_FALLBACK_STANDARD = G5_ACCOUNT_CODE // '1531'

/** 科目中文名（展示用） */
export const G5_GROSS_LABEL = G5_ACCOUNT_NAME // '长期应收款'

/** tb_source_codes 类型 */
export interface G5TbSourceCodes {
  gross_standard: string
  resolved_from: 'report_config' | 'fallback' | string
  applicable_standard?: string
}

/**
 * 运行态查询科目码列表。
 * 前端请求（如 writebackTB、序时账查询）用此函数取科目码。
 */
export function g5GrossQueryCodes(tbSourceCodes?: G5TbSourceCodes | null): string[] {
  if (tbSourceCodes?.gross_standard) {
    return [tbSourceCodes.gross_standard]
  }
  return [G5_GROSS_FALLBACK_STANDARD]
}

/**
 * 获取 G5 科目码（单值版本，用于 EventBus / 请求参数）。
 */
export function g5AccountCode(tbSourceCodes?: G5TbSourceCodes | null): string {
  return tbSourceCodes?.gross_standard || G5_GROSS_FALLBACK_STANDARD
}

// Re-export for convenience
export { G5_ACCOUNT_CODE, G5_ACCOUNT_NAME }
