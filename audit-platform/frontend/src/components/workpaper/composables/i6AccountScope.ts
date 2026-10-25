/**
 * I6 研发费用 —— 科目口径**单一真源**（零 Vue 依赖）。
 *
 * 报表行：IS-006（上市） / IS-024（国企）
 * 兜底标准码：6604 **研发费用**（`account_chart` 实证：7 条中 6 条为「研发费用」，
 * 另 1 条是某项目自定义的「勘探费用」—— 按 `account_chart` 多数口径与 `wp_index`
 * 的底稿名「研发费用」一致）。
 * 🔴 不是 6602（管理费用，那是 K9 循环的科目）。
 *
 * 🔴 文件头原标题误写作「I6 管理费用」（与下一行"不是 6602（管理费用）"自相矛盾），
 *    已更正为「研发费用」。该误写曾导致排查者按 `tb_balance` 的
 *    `MIN(account_name)` 聚合取样时误判 6604 为「勘探费用」 —— 科目**定义**的权威源
 *    是 `account_chart`，不是某个项目账套的 `tb_balance` 用法。
 *    spec: voucher-sampling-account-scope-and-attach-closure（阶段 3）
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
