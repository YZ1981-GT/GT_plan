/**
 * g10StorageContract — G10 交易性金融负债的 item_id **单一真源**
 *
 * spec: `g-cycle-single-region-detail-lanes` · Task 15（BP-10 的 G10 份额）
 * 照 G2 `g2StorageContract.ts` 范式。叶子模块，不得 import 其他模块。
 */

export const G10_ITEM_IDS = {
  /** 受管明细表 `明细表G10-2` 的行数组 */
  G10_DETAIL_ROWS: 'G10-detail-rows',
  /** 审定表 G10-1 */
  G10_1_ROWS: 'G10-1-rows',
  /** 调整分录汇总 G10-3 */
  G10_3_ROWS: 'G10-3-rows',
} as const

export type G10ItemIdKey = keyof typeof G10_ITEM_IDS
