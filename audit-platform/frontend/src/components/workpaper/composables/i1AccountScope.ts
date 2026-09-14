/**
 * I1 无形资产 —— 科目口径**单一真源**（零 Vue 依赖）。
 *
 * 报表行：BS-033（上市） / BS-045（国企）
 * 兜底标准码：1701（account_chart 实证）
 * 三段：cost=1701, amort=1702, impair=1703
 * 🔴 运行态一律取 render 下发的 `tb_source_codes`，常量只作兜底+展示。
 */
import { tbQueryCodes, type TbSourceCodes } from './shared/tbSourceCodes'

export const I1_REPORT_ROW_CODE = { listed: 'BS-033', soe: 'BS-045' } as const

/** 原值兜底标准码 */
export const I1_GROSS_FALLBACK_STANDARD = '1701'

/** 累计摊销兜底标准码 */
export const I1_AMORT_FALLBACK = '1702'

/** 减值准备兜底标准码 */
export const I1_IMPAIR_FALLBACK = '1703'

/**
 * 原值查询口径（标准码集）。
 * 运行态取 render 下发的 `tb_source_codes.gross`，常量只作兜底。
 */
export function i1GrossQueryCodes(src?: TbSourceCodes | null): string[] {
  return tbQueryCodes(src?.gross_standard, I1_GROSS_FALLBACK_STANDARD)
}

/**
 * 累计摊销查询口径。
 * 运行态取 render 下发的 `tb_source_codes.segments` 中 segment='amortization' 的码。
 */
export function i1AmortQueryCodes(src?: TbSourceCodes | null): string[] {
  const seg = src?.segments?.find((s) => s.segment === 'amortization')
  const codes = seg?.standard?.filter(Boolean)
  return codes?.length ? codes : [I1_AMORT_FALLBACK]
}

/**
 * 减值准备查询口径。
 * 运行态取 render 下发的 `tb_source_codes.segments` 中 segment='impairment' 的码。
 */
export function i1ImpairQueryCodes(src?: TbSourceCodes | null): string[] {
  const seg = src?.segments?.find((s) => s.segment === 'impairment')
  const codes = seg?.standard?.filter(Boolean)
  return codes?.length ? codes : [I1_IMPAIR_FALLBACK]
}

/** 单一科目码（回写 TB / EventBus 用）；溯源缺失时回退 1701 */
export function i1AccountCode(src?: TbSourceCodes | null): string {
  const codes = i1GrossQueryCodes(src)
  return codes[0] || I1_GROSS_FALLBACK_STANDARD
}
