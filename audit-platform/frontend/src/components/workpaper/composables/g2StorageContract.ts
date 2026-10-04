/**
 * g2StorageContract — G2 应收利息的 `checklist_responses.item_id` **单一真源**
 *
 * spec: `g-cycle-sync-foundation-and-first-canary` · Task 13（BP-10 / RG-9 的 G2 份额）
 *
 * ═══ 为什么需要这个模块 ═══
 *
 * slice BP-10 实测：G 循环（除 G7）有 **80 个** item_id 字面量在两个以上模块各写一份声明，
 * 没有单一真源。G2 命中两条最严重的：
 *
 * | 键 | 改造前的声明处（逐处按值 grep）|
 * |---|---|
 * | `G2-2-detail-rows` | `g2CrossHelpers.G2_DETAIL_STORAGE_KEY` · `useG2Detail.STORAGE_KEY` · `useG2DisclosureListed.ITEM_DETAIL` · `useG2DisclosureSoe.ITEM_DETAIL` · `useG2InterestCalc.DETAIL_KEY` = **5 处** |
 * | `G2-1-rows` | `g2CrossHelpers.G2_ADJ_STORAGE_KEY` · `useG2DisclosureListed.ITEM_ADJ` · `useG2DisclosureSoe.ITEM_ADJ` · `useG2InterestCalc.ADJ_KEY` = **4 处** |
 *
 * 危害：契约要求「一个 stable_field_key ↔ 一处声明」。改其中一处没有守卫会红，
 * 契约的 `source_ref` 就指不准。
 * `must_fix_before` = **为任一 G entry 发布 per-entry contract（step 6）之前**。
 *
 * ═══ 范式照 G6（BP-10 的正面样本），不新造 ═══
 *
 * `g6StorageContract.G6_ITEM_IDS` + `g6CrossHelpers` 的**派生别名**
 * （`export const G6_11_ROWS_KEY = G6_ITEM_IDS.G6_11_ROWS`）。
 * 本模块同款：真源在此，各消费模块的原常量名**保留**并改为派生
 * —— 保留原名是为了不动调用方签名（零回归）。
 *
 * ═══ 🔴 键名一律「按值取」，不得按 sheet 号推演 ═══
 *
 * 反例（GC-6 / RG-9 登记的陷阱）：`明细表G2-2` 的键**不是** `G2-2-rows`，
 * 而是 `G2-2-detail-rows`；审定表 `G2-1` 的行键**不是** `G2-1-adj-rows`
 * （那是 legacy 回退键），而是 `G2-1-rows`。
 *
 * ⚠️ **本模块是叶子模块：不得 import 任何其它模块**。
 * 它被 `useG2Detail` / `g2CrossHelpers` / 两个披露 composable / `useG2InterestCalc` 共同消费，
 * 任何 import 都可能成环（`g2CrossHelpers` → `useG2IntRecFormulaEngine` 已是一条边）。
 */

/** G2 各受管/关联 sheet 的 `checklist_responses.item_id`（逐字按值取，禁推演）。 */
export const G2_ITEM_IDS = {
  /** 🔴 canary 受管表 `明细表G2-2` 的行数组（sync 契约 `store_item_id`） */
  G2_2_DETAIL_ROWS: 'G2-2-detail-rows',
  /** 审定表 G2-1 的行数组（**不是** `G2-1-adj-rows`，后者是 legacy 回退键） */
  G2_1_ROWS: 'G2-1-rows',
  /** 审定表 G2-1 的 legacy 行键 —— 只读回退，不得作为写入目标 */
  G2_1_ROWS_LEGACY: 'G2-1-adj-rows',
  /** 坏账准备明细表 G2-3 */
  G2_3_BAD_DEBT_ROWS: 'G2-3-bad-debt-rows',
  /** 利息测算表 G2-5 */
  G2_5_INTEREST_CALC_ROWS: 'G2-5-interest-calc-rows',
  /** 长期未收回款项检查表 G2-6 */
  G2_6_OVERDUE_ROWS: 'G2-6-overdue-rows',
} as const

export type G2ItemIdKey = keyof typeof G2_ITEM_IDS
