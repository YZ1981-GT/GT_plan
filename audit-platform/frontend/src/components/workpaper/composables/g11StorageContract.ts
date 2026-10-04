/**
 * g11StorageContract — G11 投资收益的 item_id **单一真源**
 *
 * spec: `g-cycle-single-region-detail-lanes` · Task 15（BP-10 的 G11 份额）
 * 照 G2 `g2StorageContract.ts` 范式。叶子模块，不得 import 其他模块。
 */

export const G11_ITEM_IDS = {
  /** 受管明细分析表 `明细分析表G11-2` 的行数组 */
  G11_DETAIL_ROWS: 'G11-detail-rows',
  /** 审定表 G11-1 的行数组 */
  G11_ADJ_ROWS: 'G11-adj-rows',
  /** 调整分录汇总 G11-3 */
  G11_3_ROWS: 'G11-3-rows',
  /** 收益率分析表 G11-4 */
  G11_4_ROWS: 'G11-4-rows',
} as const

export type G11ItemIdKey = keyof typeof G11_ITEM_IDS
