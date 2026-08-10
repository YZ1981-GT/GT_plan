/**
 * h3AccountScope — H3 投资性房地产科目定位的**前端单一真源**（per-cycle 薄壳）。
 *
 * **要修的缺陷（2026-08-06 实证，数字级 P0）**
 *
 * 后端 `four_table/h3_account_scope.py` 已于 2026-08-01 把 H3 的科目族从
 * `1503`/`1504` 纠正为 `1521`/`1525`/`1526`/`1527`（`1503` 实为**可供出售金融资产**
 * 属 G6 域、`1504` 实为**债权投资**属 G4 域），而**前端仍全线写死旧码**：
 *
 * | 落点 | 旧实现 | 后果 |
 * |------|--------|------|
 * | `H3TabAdjudicationCost.writebackTrialBalance()` | `account_code: '1503'` / `'1504'` | **往 G6/G4 的科目行写投资性房地产审定数** —— 与 H8/H9 那次「往 1901 写审定数污染 K2」同款 |
 * | `H3TabAdjudicationFair.writebackTrialBalance()` | `account_code: '1503'` | 同上 |
 * | `useAdjudicationBringIn({subjectPrefix})` ×4 | `'1503'`/`'1504'`/`'1505'` | 从集中登记拉**别的循环**的调整分录 |
 * | `GtVoucherSamplingEngine account-code` | `'1503'` | 抽的是可供出售金融资产的凭证 |
 * | `eventBus substantive:adjudicated` | `accountCode: '1503'` | 下游相关性判定挂错科目 |
 * | AI `related_data.accountCode` | `'1503'` | 给模型的上下文是错科目 |
 *
 * **口径优先级（与平台既有 `k2AccountScope` / `g6AccountScope` 一致）**
 *
 * 运行态一律取 render 下发的 `html_data.tb_source_codes`（后端逐项目按**科目名称**
 * 在该项目自己的 `account_chart` 里定位的结果）；本文件的常量**只作兜底与展示**。
 *
 * 🔴 为什么不能只把字面量从 1503 换成 1521：`account_mapping` 实证同一原始码在不同
 * 项目映射到**不同标准码**（`1525 投资性房地产累计折旧 → 1521` 1 个项目并入母科目 /
 * `→ 1525` 4 个项目独立），按标准码硬查会在部分项目取空。故必须走 render 下发值。
 *
 * spec: .kiro/specs/h-cycle-extraction-formula-and-disclosure-completion/
 *       Requirements 5.1~5.4（溯源面板）与 Task 19（前端旧码清零）
 */
import {
  createCycleAccountScope,
  type CycleAccountScopeSpec,
} from './shared/cycleAccountScope'

/** 后端槽键（须与 `h3_account_scope.py` 的 `H3_ACCOUNT_SPEC.slots` 逐字一致） */
export const H3_SLOT_GROSS = 'gross'
export const H3_SLOT_ACCUM_DEP = 'accum_dep'
export const H3_SLOT_ACCUM_AMORT = 'accum_amort'
export const H3_SLOT_IMPAIRMENT = 'impairment'

/**
 * 除主槽外要在溯源面板明细里展示的槽。
 *
 * 🔴 H3 是**四槽** spec 且**没有** `provision` 槽 ⇒
 * `SemanticAccountResult.as_dict()` 的扁平 `provision` 恒为空，
 * 不显式声明这三个槽键，累计折旧/累计摊销/减值准备的来源科目在面板里看不见。
 */
export const H3_EXTRA_SLOT_KEYS = [
  H3_SLOT_ACCUM_DEP,
  H3_SLOT_ACCUM_AMORT,
  H3_SLOT_IMPAIRMENT,
] as const

/** 报表行（`report_config` 实证：BS-027 投资性房地产 / IMP-010 减值准备） */
export const H3_REPORT_ROW_CODE = 'BS-027'
export const H3_IMPAIRMENT_REPORT_ROW_CODE = 'IMP-010'

export const H3_ACCOUNT_SCOPE_SPEC: CycleAccountScopeSpec = {
  cycle: 'H3',
  reportRowCode: H3_REPORT_ROW_CODE,
  slots: [
    { key: H3_SLOT_GROSS, label: '投资性房地产原值', fallback: '1521' },
    { key: H3_SLOT_ACCUM_DEP, label: '累计折旧', fallback: '1525', isProvision: true },
    { key: H3_SLOT_ACCUM_AMORT, label: '累计摊销', fallback: '1526', isProvision: true },
    { key: H3_SLOT_IMPAIRMENT, label: '减值准备', fallback: '1527', isProvision: true },
  ],
}

export const h3AccountScope = createCycleAccountScope(H3_ACCOUNT_SCOPE_SPEC)

/**
 * 兜底展示码（**仅**在 render 未下发时用于文案，勿作为查询口径）。
 *
 * 🔴 这些是「本循环正确的科目族」，与被替换掉的 `1503`/`1504`/`1505` 完全不同 ——
 * 后者分属 G6（可供出售金融资产）/ G4（债权投资）/（债权投资减值准备）三个别的循环。
 */
export const H3_FALLBACK_CODES = {
  gross: '1521',
  accumDep: '1525',
  accumAmort: '1526',
  impairment: '1527',
} as const

export type H3SlotKey =
  | typeof H3_SLOT_GROSS
  | typeof H3_SLOT_ACCUM_DEP
  | typeof H3_SLOT_ACCUM_AMORT
  | typeof H3_SLOT_IMPAIRMENT

/**
 * `html_data.tb_values` 的键前缀 —— **必须与后端 `H3_SLOT_KEY_PREFIX` 逐字一致**。
 *
 * 🔴 改造前 `useH3FormData` 读的是 `inv_prop_1503_unadjusted` / `dep_1504_unadjusted`，
 * 而后端 `build_h3_tb_values` 产出的是 `ip_*` / `dep_*` / `amort_*` / `impair_*`
 * ⇒ 那四个键是 **dead render key**，seed 分支永不命中、必然落到按 1503/1504 的
 * 错误 HTTP 兜底查询。守卫 `h3AccountScopeContract.spec.ts` 读后端 py 源码交叉锁死。
 */
export const H3_TB_PREFIX = {
  gross: 'ip',
  accumDep: 'dep',
  accumAmort: 'amort',
  impairment: 'impair',
} as const
