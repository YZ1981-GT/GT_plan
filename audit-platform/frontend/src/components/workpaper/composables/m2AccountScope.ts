/**
 * M2 实收资本（股本）—— 科目口径**单一真源**（零 Vue 依赖）。
 *
 * spec: voucher-sampling-account-scope-and-attach-closure（字面量清理批次，任务 2）
 *
 * ## 🔴 `4001` 在客户科目表里有**两种定义**，这是本模块最重要的信息
 *
 * `account_chart` 现算（2026-09-28）：
 *
 * | `4001` 的定义 | 条数 | 说明 |
 * |---|---|---|
 * | **实收资本** | **14** | 现行会计科目表（财会〔2006〕18 号）口径 |
 * | **生产成本** | **5** | 旧科目表遗留（2006 年前 `4001` 为生产成本） |
 *
 * ⇒ 在那 5 个项目里，以 `4001` 抽凭会抽到**生产成本**凭证，与实收资本毫无关系。
 * 这正是「运行态必须优先 `tb_source_codes`、兜底码只兜界面」这条纪律的价值所在：
 * 兜底码取多数口径（实收资本），但**不能假定它在每个项目都对**。
 *
 * `report_config` 三行一致指向 `4001` 为实收资本/股本：
 * - `BS-075 股本 = TB('4001','期末余额')`
 * - `BS-081 实收资本（或股本） = TB('4001','期末余额')`
 * - `BS-102 实收资本 = TB('4001','期末余额')`
 *
 * 🔴 科目**定义**权威源是 `account_chart`，不是 `tb_balance`/`tb_ledger` 的
 * `MIN(account_name)` 聚合（本 spec 实施中曾因此误判 `6604`）。
 */
import { tbQueryCodes, type TbSourceCodes } from './shared/tbSourceCodes'

/** 报表行次：上市用「股本」BS-075，国企用「实收资本」BS-081 */
export const M2_REPORT_ROW_CODE = { listed: 'BS-075', soe: 'BS-081' } as const

/**
 * 兜底标准码：`4001` 实收资本（**多数口径 14/19**）。
 *
 * 🔴 在把 `4001` 用作「生产成本」的那 5 个项目里本兜底码不适用 ——
 * 那些项目必须靠 render 下发 `tb_source_codes` 纠正。改动本常量前先查 `account_chart`。
 */
export const M2_FALLBACK_STANDARD = '4001'

/** 科目中文名（展示与提示文案用） */
export const M2_ACCOUNT_NAME = '实收资本'

/**
 * 曾被误用 / 易撞码的科目 —— 守卫与代码评审用。
 *
 * `4002` 是资本公积（M3 循环），不属本表；`4001` 在部分项目是生产成本（见文件头）。
 */
export const M2_AMBIGUOUS_ACCOUNTS = ['4002'] as const

/** 查询口径（标准码集）。运行态取解析值，缺失时退兜底。 */
export function m2QueryCodes(src?: TbSourceCodes | null): string[] {
  return tbQueryCodes(src?.gross_standard, M2_FALLBACK_STANDARD)
}

/** 单一科目码（回写 TB / EventBus 载荷用）；解析不出时退 `4001` */
export function m2AccountCode(src?: TbSourceCodes | null): string {
  return m2QueryCodes(src)[0] || M2_FALLBACK_STANDARD
}
