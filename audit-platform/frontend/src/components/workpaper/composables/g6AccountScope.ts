/**
 * G6 其他债权投资 — 科目映射单一真源
 *
 * 权威链路：report_config BS-022 四准则一致 = TB('1505','期末余额')
 * 无备抵科目（CAS22 FVOCI-Debt 减值在 OCI 确认，不冲减资产负债表账面价值）。
 *
 * 运行态一律取 render 下发的 `tb_source_codes.gross_standard`，
 * 常量只作兜底 + 展示（与 g7AccountScope.ts / k2AccountScope.ts 同范式）。
 *
 * 历史纠错（2026-08-01）：
 *   - 后端 render 原取 '1503'（旧准则"可供出售金融资产"已废止）
 *   - 公式预设审定表原取 '1510'（标准科目表无此码）
 *   - 公式预设明细表原取 '1531'（长期应收款，属 L 循环）
 *   三处互相矛盾且均非权威真源 report_config 的 1505。
 */

/** G6 对应的报表行编码 */
export const G6_REPORT_ROW_CODE = 'BS-022'

/** 原值兜底标准科目码（report_config 解析失败时回退） */
export const G6_GROSS_FALLBACK_STANDARD = '1505'

/** render 下发的科目溯源结构 */
export interface G6TbSourceCodes {
  gross_standard: string[]
  resolved_from: 'report_config' | 'fallback'
}

/**
 * 运行态获取 G6 原值查询科目码列表。
 * 优先取 render 下发的 tb_source_codes.gross_standard，缺失时回退常量。
 */
export function g6GrossQueryCodes(
  tbSourceCodes?: G6TbSourceCodes | null,
): string[] {
  if (tbSourceCodes?.gross_standard?.length) {
    return tbSourceCodes.gross_standard
  }
  return [G6_GROSS_FALLBACK_STANDARD]
}

/**
 * 获取首个科目码（展示 / 请求参数用）。
 */
export function g6AccountCode(
  tbSourceCodes?: G6TbSourceCodes | null,
): string {
  const codes = g6GrossQueryCodes(tbSourceCodes)
  return codes[0] || G6_GROSS_FALLBACK_STANDARD
}
