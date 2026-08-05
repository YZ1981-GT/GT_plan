/**
 * blockColumnAmountRegistry.ts — 替代程序区块「非金额数值列」登记表（七枢纽单一真源）
 *
 * ## 为什么需要这张表
 *
 * `BlockColumnDef.type === 'number'` 同时承载**金额**与**非金额**两种语义：
 * 金额要走平台金额格式（千分符 + 单位偏好 + 2 位小数），数量/单价/比例不能做
 * 金额单位换算。区分这两者**不能用 label 关键字推断**，两个方向都会错：
 *
 * - 漏抓：H0-5 的 `cap_cost`（label「原值」）是金额，但不含「金额/余额」任何关键字；
 * - 误抓：G0-6 的 `trade_price`（「成交价」）与 `dividend_per_share`（「每股股利」）
 *   会被「价」「利」关键字抓成金额。
 *
 * 故按平台铁律「避免硬编码 = 单一真源 + 守卫与真源双向锁死」：金额列在配置里显式标
 * `render: 'amount'`，非金额列在本表显式登记并写明理由，两侧由守卫双向锁死 ——
 * 任何 `type:'number'` 非 `seq` 列**要么**标注**要么**在册，新增列漏表态即打红。
 *
 * ## 🔴 identity 是 (file, block, field)，不是 field 单独
 *
 * 同名 `field` 会合法地跨文件、甚至**同文件跨区块**复现（实测三组）：
 *   - `transport_qty`：blockColumnConfigsD06.ts 的 block1 与 block3 各一次
 *   - `inbound_qty`：blockColumnConfigsF05.ts 的 block1 / block4
 *   - `inbound_qty`：blockColumnConfigsF06.ts 的 block1 / block3
 * 以 field 为键的 Map 会静默吞掉条目（17 条塌成 14 条），故查找一律走
 * `isNonAmountNumberColumn(file, block, field)`，勿自建 field-keyed 索引。
 *
 * 实测规模（改动前，全 8 个区块配置文件）：
 *   125 个 `type:'number'` 列 = 32 个 `seq` + 76 个金额 + 17 个非金额（本表）
 * `seq` 不参与表态：`CheckBlock.vue` 的 `col.field === 'seq'` 分支早于 number 分支命中。
 */

/** 区块键（与各配置文件 `BLOCK_COLUMN_CONFIGS*` 的键、`BlockType` 一致） */
export type BlockKey = 'block1' | 'block2' | 'block3' | 'block4'

export interface NonAmountNumberCol {
  /** 配置文件名（不含路径），如 `blockColumnConfigsD06.ts` */
  file: string
  /** 所属区块键 —— identity 的一部分，同文件同 field 可跨区块复现 */
  block: BlockKey
  /** 列字段 key */
  field: string
  /** 列标题（与配置里的 label 逐字一致，供守卫交叉锁死） */
  label: string
  /** 为什么不是金额 —— 必填，≥8 字 */
  reason: string
}

/**
 * 17 条非金额数值列（实测明细）。
 *
 * 分三类：
 *   - 实物数量（数量 / 运输数量 / 卖出赎回数量）—— 单位是件/台/股，非货币；
 *   - 单价（成交价）—— 单价 × 数量才是金额，本身不按金额单位换算；
 *   - 每股指标（每股股利）—— 每股口径，乘持股数才是金额。
 */
export const NON_AMOUNT_NUMBER_COLUMNS: readonly NonAmountNumberCol[] = Object.freeze([
  // ── D0-5（共享基准 blockColumnConfigs.ts）3 条 ──────────────────────────
  {
    file: 'blockColumnConfigs.ts',
    block: 'block1',
    field: 'delivery_qty',
    label: '数量',
    reason: '客户验收单/出库单的实物交付数量，单位为件/台等计件单位，非货币金额',
  },
  {
    file: 'blockColumnConfigs.ts',
    block: 'block4',
    field: 'product_qty',
    label: '数量',
    reason: '记账凭证行的出库商品实物数量，与同行「金额」列相乘才是货币金额',
  },
  {
    file: 'blockColumnConfigs.ts',
    block: 'block4',
    field: 'transport_qty',
    label: '运输数量',
    reason: '运输单承运的实物件数，属物流数量口径，不做金额单位换算',
  },

  // ── D0-6 4 条（transport_qty 在 block1/block3 各一次）──────────────────
  {
    file: 'blockColumnConfigsD06.ts',
    block: 'block1',
    field: 'outbound_qty',
    label: '数量',
    reason: '出库单的实物出库数量，单位为件/台等计件单位，非货币金额',
  },
  {
    file: 'blockColumnConfigsD06.ts',
    block: 'block1',
    field: 'transport_qty',
    label: '运输数量',
    reason: '运输单承运的实物件数，属物流数量口径，不做金额单位换算',
  },
  {
    file: 'blockColumnConfigsD06.ts',
    block: 'block3',
    field: 'product_qty',
    label: '数量',
    reason: '记账凭证行的销售出库实物数量，与同行「金额」列相乘才是货币金额',
  },
  {
    file: 'blockColumnConfigsD06.ts',
    block: 'block3',
    field: 'transport_qty',
    label: '运输数量',
    reason: '运输单承运的实物件数，属物流数量口径，不做金额单位换算',
  },

  // ── F0-5 2 条（inbound_qty 在 block1/block4 各一次）────────────────────
  {
    file: 'blockColumnConfigsF05.ts',
    block: 'block1',
    field: 'inbound_qty',
    label: '数量',
    reason: '入库单的实物入库数量，单位为件/吨等计量单位，非货币金额',
  },
  {
    file: 'blockColumnConfigsF05.ts',
    block: 'block4',
    field: 'inbound_qty',
    label: '数量',
    reason: '入库单的实物入库数量，单位为件/吨等计量单位，非货币金额',
  },

  // ── F0-6 2 条（inbound_qty 在 block1/block3 各一次）────────────────────
  {
    file: 'blockColumnConfigsF06.ts',
    block: 'block1',
    field: 'inbound_qty',
    label: '数量',
    reason: '入库单的实物入库数量，单位为件/吨等计量单位，非货币金额',
  },
  {
    file: 'blockColumnConfigsF06.ts',
    block: 'block3',
    field: 'inbound_qty',
    label: '数量',
    reason: '入库单的实物入库数量，单位为件/吨等计量单位，非货币金额',
  },

  // ── H0-5 2 条 ──────────────────────────────────────────────────────────
  {
    file: 'blockColumnConfigsH05.ts',
    block: 'block1',
    field: 'asset_qty',
    label: '数量',
    reason: '固定资产验收单的实物台件数，与同区块「原值」列口径不同，非货币金额',
  },
  {
    file: 'blockColumnConfigsH05.ts',
    block: 'block3',
    field: 'recv_qty',
    label: '数量',
    reason: '到货验收环节的实物台件数，属实物数量口径，不做金额单位换算',
  },

  // ── G0-6 4 条 ──────────────────────────────────────────────────────────
  {
    file: 'blockColumnConfigsG06.ts',
    block: 'block3',
    field: 'sell_qty',
    label: '卖出/赎回数量',
    reason: '处置的证券份数或基金份额，单位为股/份，与「成交金额」是两个口径',
  },
  {
    file: 'blockColumnConfigsG06.ts',
    block: 'block3',
    field: 'trade_price',
    label: '成交价',
    reason: '每股/每份单价，单价乘以数量才是成交金额，本身不按金额格式化',
  },
  {
    file: 'blockColumnConfigsG06.ts',
    block: 'block4',
    field: 'holding_qty',
    label: '数量',
    reason: '持仓证明上的持有股数或份额，单位为股/份，非货币金额',
  },
  {
    file: 'blockColumnConfigsG06.ts',
    block: 'block4',
    field: 'dividend_per_share',
    label: '每股股利',
    reason: '每股口径的股利单价，乘以持股数才是应收股利金额，不做金额单位换算',
  },
])

/**
 * 判定某列是否为已登记的非金额数值列。
 *
 * identity = (file, block, field)；**不要**按 field 单独查（同文件同 field
 * 会跨区块复现，见文件头说明）。
 */
export function isNonAmountNumberColumn(
  file: string,
  block: BlockKey,
  field: string,
): boolean {
  return NON_AMOUNT_NUMBER_COLUMNS.some(
    (c) => c.file === file && c.block === block && c.field === field,
  )
}

/**
 * 取某列的非金额理由（未登记返回 undefined）。供守卫在打红时输出可读信息。
 */
export function nonAmountReason(
  file: string,
  block: BlockKey,
  field: string,
): string | undefined {
  return NON_AMOUNT_NUMBER_COLUMNS.find(
    (c) => c.file === file && c.block === block && c.field === field,
  )?.reason
}
