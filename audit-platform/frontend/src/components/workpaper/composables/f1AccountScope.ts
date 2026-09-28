/**
 * F1 预付账款 —— 科目口径**单一真源**（零 Vue 依赖）。
 *
 * spec: voucher-sampling-account-scope-and-attach-closure（字面量清理批次，任务 2）
 *
 * ## 为什么单独建，而不是挂进 `dCycleAccountScope`
 *
 * F1 宿主 `F1TabComprehensiveCheck.vue` 原硬编码 `account-code="1123"`，值是对的，
 * 但接线时实测 `dCycleScope('F1')` 返回 **null** —— F1 不在 D 循环（销售与收款）的
 * 登记表里，它属 F 循环（采购与付款）。若强行用 `dCycleScope` 会拿到 `NO_SCOPE`
 * 并退化成空科目，故按 spec R1.3「无真源先建真源」新建本模块。
 *
 * ## 取值实证（2026-09-28，DB 只读）
 *
 * | 判据源 | 结果 |
 * |---|---|
 * | `wp_index` 底稿名 | 预付账款 |
 * | `account_chart` 的 `1123` | **预付账款**（19 条定义全部一致，无歧义） |
 * | `report_config` | `BS-008 预付款项 = TB('1123','期末余额')` |
 *
 * 🔴 科目**定义**权威源是 `account_chart`，不是 `tb_balance`/`tb_ledger` 的
 * `MIN(account_name)` 聚合（本 spec 实施中曾因此误判 `6604`）。
 */
import { tbQueryCodes, type TbSourceCodes } from './shared/tbSourceCodes'

/** 报表行次（预付款项，上市/国企同号） */
export const F1_REPORT_ROW_CODE = { listed: 'BS-008', soe: 'BS-008' } as const

/** 兜底标准码：`1123` 预付账款 */
export const F1_FALLBACK_STANDARD = '1123'

/** 科目中文名（展示与提示文案用） */
export const F1_ACCOUNT_NAME = '预付账款'

/**
 * 查询口径（标准码集）。运行态取 `tb_source_codes.gross_standard`，缺失时退兜底。
 *
 * 预付账款的供应商明细挂在子科目上，`tb_ledger` 按前缀匹配 ⇒ 传 `1123` 即覆盖全部。
 */
export function f1QueryCodes(src?: TbSourceCodes | null): string[] {
  return tbQueryCodes(src?.gross_standard, F1_FALLBACK_STANDARD)
}

/** 单一科目码（回写 TB / EventBus 载荷用）；解析不出时退 `1123` */
export function f1AccountCode(src?: TbSourceCodes | null): string {
  return f1QueryCodes(src)[0] || F1_FALLBACK_STANDARD
}
