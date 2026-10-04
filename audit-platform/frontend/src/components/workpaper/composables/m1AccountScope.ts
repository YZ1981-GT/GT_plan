/**
 * M1 应付股利（利润）—— 科目口径**单一真源**（零 Vue 依赖）。
 *
 * spec: voucher-sampling-account-scope-and-attach-closure（字面量清理批次，任务 2）
 *
 * ## 取值实证（2026-09-28，DB 只读）
 *
 * | 判据源 | 结果 |
 * |---|---|
 * | `wp_index` 底稿名 | 应付股利（利润） |
 * | `account_chart` 的 `2232` | **应付股利**（19 个项目中 16 条定义一致，无歧义） |
 * | `report_config` | `BS-055 应付股利 = TB('2232','期末余额')`；`BS-076 其中：应付股利 = TB('2232')` |
 *
 * 🔴 科目**定义**的权威源是 `account_chart`，不是 `tb_balance` / `tb_ledger` 的
 * `MIN(account_name)` 聚合 —— 后者是各项目账套的实际用法，同一码在不同项目可挂不同名称，
 * 聚合会随机取到其中一个（本 spec 实施中曾因此误判 `6604`）。
 *
 * ## 运行态优先级
 *
 * 一律优先 render 下发的 `tb_source_codes`，本文件常量只作兜底与展示。
 */
import { tbQueryCodes, type TbSourceCodes } from './shared/tbSourceCodes'

/** 报表行次（上市/国企同号） */
export const M1_REPORT_ROW_CODE = { listed: 'BS-055', soe: 'BS-055' } as const

/** 兜底标准码：`2232` 应付股利 */
export const M1_FALLBACK_STANDARD = '2232'

/** 科目中文名（展示与提示文案用） */
export const M1_ACCOUNT_NAME = '应付股利'

/**
 * 查询口径（标准码集）。运行态取 `tb_source_codes.gross_standard`，缺失时退兜底。
 *
 * 🔴 M1 是**单科目**循环（不像 E1 的货币资金三科目族），故全集 == 单值，
 * 抽凭与回写都可用本函数；保留数组形态是为与其他循环签名一致。
 */
export function m1QueryCodes(src?: TbSourceCodes | null): string[] {
  return tbQueryCodes(src?.gross_standard, M1_FALLBACK_STANDARD)
}

/** 单一科目码（回写 TB / EventBus 载荷用）；解析不出时退 `2232` */
export function m1AccountCode(src?: TbSourceCodes | null): string {
  return m1QueryCodes(src)[0] || M1_FALLBACK_STANDARD
}
