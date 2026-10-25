/**
 * N2 应交税费 —— 科目口径**单一真源**（零 Vue 依赖）。
 *
 * spec: voucher-sampling-account-scope-and-attach-closure（字面量清理批次，任务 2）
 *
 * ## 取值实证（2026-09-28，DB 只读）
 *
 * | 判据源 | 结果 |
 * |---|---|
 * | `wp_index` 底稿名 | 应交税费 |
 * | `account_chart` 的 `2221` | **应交税费**（19 条定义全部一致，无歧义） |
 * | `report_config` | `BS-049 应交税费 = TB('2221','期末余额')`（另 `BS-073` 同） |
 *
 * ## 🔴 子科目族：抽凭用前缀匹配，不要只取 `2221` 顶层
 *
 * 真实账套的税费明细挂在子科目上（如 `2221.01.02 应交增值税_进项税额`）。
 * `tb_ledger` 查询按**前缀**匹配，故传 `2221` 即可覆盖全部子科目；
 * 但若将来需要只查某个税种（如只查增值税），应由 render 下发更细的
 * `tb_source_codes`，而不是在宿主里拼子科目码。
 *
 * 🔴 科目**定义**权威源是 `account_chart`，不是 `tb_balance`/`tb_ledger` 的
 * `MIN(account_name)` 聚合（本 spec 实施中曾因此误判 `6604`）。
 */
import { tbQueryCodes, type TbSourceCodes } from './shared/tbSourceCodes'

/** 报表行次（上市 BS-049 / 国企 BS-073） */
export const N2_REPORT_ROW_CODE = { listed: 'BS-049', soe: 'BS-073' } as const

/** 兜底标准码：`2221` 应交税费（前缀匹配可覆盖全部税种子科目） */
export const N2_FALLBACK_STANDARD = '2221'

/** 科目中文名（展示与提示文案用） */
export const N2_ACCOUNT_NAME = '应交税费'

/** 查询口径（标准码集）。运行态取解析值，缺失时退兜底。 */
export function n2QueryCodes(src?: TbSourceCodes | null): string[] {
  return tbQueryCodes(src?.gross_standard, N2_FALLBACK_STANDARD)
}

/** 单一科目码（回写 TB / EventBus 载荷用）；解析不出时退 `2221` */
export function n2AccountCode(src?: TbSourceCodes | null): string {
  return n2QueryCodes(src)[0] || N2_FALLBACK_STANDARD
}
