/**
 * K2-1 审定表动态行 —— K2 的规格声明（薄壳）。
 *
 * 逻辑一律委托平台级共享件 `shared/dynamicAdjudicationRows.ts`，本文件只放
 * **K2 专属声明**：持久化前缀、历史固定行、金额字段集、外来行警示文案。
 *
 * **为什么 K2-1 必须是动态行**
 *
 * 源模板 `K2 其他流动资产.xlsx` 的上市披露 sheet A5 逐字写着「根据实际情况列示；
 * 不存在的项目请删除」，明细表 K2-2（同循环）本就是动态行 + `prompt` 命名。
 * 而 K2-1 审定表停在**硬编码 8 行**：既框住了客户实际有的项目（源模板另举了 7 个
 * 例子，与这 8 行并不重合），也让客户实际没有的项目占着空行。
 *
 * 历史那 8 行本身是 K2 的**二级子明细**（其他流动资产下的明细项目），不是别的循环的
 * 科目，故迁移时原样保留 —— 只把「固定枚举」换成「动态行」：有数据的行按旧 rowKey
 * 迁成动态行（金额零丢失），从未填过的行不再占位，其余由审计师按实际情况增删改名，
 * 或从四表库 / K2-2 明细一键带入。
 *
 * spec: .kiro/specs/k2-four-table-extraction-and-dynamic-rows/ Task 3.1
 *       Requirements 2.1, 2.4
 */
import type { DynamicRowsSpec, LegacyFixedRow } from './shared/dynamicAdjudicationRows'

/** 持久化键前缀 */
export const K2_ADJ_PREFIX = 'K2-1'

/** 金额字段集（用于「该历史行是否有数据」判定 + 合计口径） */
export const K2_ADJ_VALUE_FIELDS = [
  'begin',
  'debit',
  'credit',
  'unadj',
  'aje',
  'rje',
  'prior-audited',
] as const

/**
 * 历史固定行（迁移源）—— 其他流动资产的**二级子明细**项目。
 *
 * `key` 即旧 rowKey，迁移后作为 `rowId` 沿用，使 `K2-1-{key}-unadj` 等既有持久化键
 * 继续命中（零丢数）。迁移只保留**已有录入**的行，从未填过的不再占位。
 */
export const K2_LEGACY_ROWS: readonly LegacyFixedRow[] = [
  { key: 'contract-cost', label: '合同取得成本' },
  { key: 'prepayment', label: '预付款项' },
  { key: 'deferred-expense', label: '待摊费用' },
  { key: 'tax-deductible', label: '待抵扣税额' },
  { key: 'contract-asset', label: '合同资产' },
  { key: 'deposit', label: '押金保证金' },
  { key: 'receivable-transfer', label: '应收款项转让' },
  { key: 'other', label: '其他' },
]

/** K2-1 动态行规格（传给共享件的唯一入参） */
export const K2_ADJ_ROWS_SPEC: DynamicRowsSpec = {
  prefix: K2_ADJ_PREFIX,
  legacyRows: K2_LEGACY_ROWS,
  valueFields: [...K2_ADJ_VALUE_FIELDS],
}

/**
 * 源模板 `审定表K2-1` 的示例项目（**仅作新增行的输入提示**，不预置成固定行）。
 *
 * 源 xlsx 逐字：待摊费用 / 待抵扣进项税 / 房租物业费 / 预缴企业所得税 /
 * 委托贷款 / 预缴其他税费 / 应收退货成本 —— 与 `K2_LEGACY_ROWS` 一样都只是
 * 二级子明细的举例，实际列示以客户科目表与业务为准。
 */
export const K2_TEMPLATE_ROW_EXAMPLES: readonly string[] = [
  '待摊费用',
  '待抵扣进项税',
  '房租物业费',
  '预缴企业所得税',
  '委托贷款',
  '预缴其他税费',
  '应收退货成本',
]
