/**
 * g1StorageContract — G1 交易性金融资产的 `checklist_responses.item_id` **单一真源**
 *
 * spec: `g-cycle-single-region-detail-lanes` · Task 15（BP-10 / RG-9 的 G1 份额）
 *
 * 照 G2 的 `g2StorageContract.ts` 范式。
 *
 * ⚠️ **本模块是叶子模块：不得 import 任何其它模块**。
 */

/** G1 各受管/关联 sheet 的 `checklist_responses.item_id`（逐字按值取，禁推演）。 */
export const G1_ITEM_IDS = {
  /** 🔴 受管明细表 `明细表G1-2` 的行数组（sync 契约 `store_item_id`） */
  G1_2_ROWS: 'G1-2-rows',
  /** 调整分录汇总 G1-3 */
  G1_3_ROWS: 'G1-3-rows',
  /** 结存表 G1-4 */
  G1_4_ROWS: 'G1-4-rows',
  /** 收益测算表 G1-5 */
  G1_5_ROWS: 'G1-5-rows',
  /** 公允价值测试表 G1-6 */
  G1_6_ROWS: 'G1-6-rows',
  /** 第三层次调节表 G1-7 */
  G1_7_ROWS: 'G1-7-rows',
  /** 业务模式分析 G1-8 */
  G1_8_ROWS: 'G1-8-rows',
  /** 分类适当性检查 G1-9 */
  G1_9_ROWS: 'G1-9-rows',
  /** 合同现金流量特征分析 G1-10 */
  G1_10_ROWS: 'G1-10-rows',
  /** 有价证券监盘表 G1-11 */
  G1_11_ROWS: 'G1-11-rows',
  /** 有价证券盘点倒轧表 G1-12 */
  G1_12_ROWS: 'G1-12-rows',
} as const

export type G1ItemIdKey = keyof typeof G1_ITEM_IDS
