/**
 * G1 交易性金融资产 — 科目码单一真源
 *
 * 运行态优先取 render 下发的 `tb_source_codes`，本文件的常量仅作兜底与展示。
 *
 * report_config 实证（DB 四准则一致）：
 *   BS-003 交易性金融资产 = TB('1101','期末余额')
 *   BS-004 衍生金融资产   = TB('1102','期末余额')
 *
 * 交易性金融资产无备抵（以公允价值计量，不计提减值准备）。
 */

/** 报表行次编码 — 交易性金融资产 */
export const G1_REPORT_ROW_CODE = 'BS-003'

/** 报表行次编码 — 衍生金融资产 */
export const G1_DERIVATIVE_ROW_CODE = 'BS-004'

/** 兜底标准码 — 交易性金融资产（仅在 render 未下发 tb_source_codes 时用） */
export const G1_GROSS_FALLBACK_STANDARD = '1101'

/** 兜底标准码 — 衍生金融资产 */
export const G1_DERIVATIVE_FALLBACK_STANDARD = '1102'

/**
 * tb_source_codes 溯源视图模型（render 下发的 project_context.tb_source_codes）
 */
export interface G1TbSourceCodes {
  report_row?: string
  gross_standard?: string[]
  gross?: string[]
  formula?: string | null
  resolved_from?: string
  parent_check?: { leaf_sum: number; parent: number; diff: number } | null
  [key: string]: unknown
}

/**
 * 取原值查询用的科目码集合。
 * 优先从 render 下发的 tb_source_codes 取，回退到兜底常量。
 */
export function g1GrossQueryCodes(src?: G1TbSourceCodes | null): string[] {
  if (src?.gross_standard?.length) return src.gross_standard
  return [G1_GROSS_FALLBACK_STANDARD]
}

/**
 * 用于 EventBus 事件 / writebackTB 的交易性金融资产科目码。
 */
export function g1AccountCode(src?: G1TbSourceCodes | null): string {
  const codes = g1GrossQueryCodes(src)
  return codes[0] || G1_GROSS_FALLBACK_STANDARD
}

/**
 * 衍生金融资产科目码（BS-004）。
 */
export function g1DerivativeCode(_src?: G1TbSourceCodes | null): string {
  return G1_DERIVATIVE_FALLBACK_STANDARD
}
