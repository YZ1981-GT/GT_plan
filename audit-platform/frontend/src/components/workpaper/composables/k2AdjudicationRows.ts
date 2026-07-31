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
 * 而 K2-1 审定表停在**硬编码 8 行**，且这 8 行与源模板审定表的 7 行完全不同，
 * 还混入了三个**属于别的报表行**的项目 → 列在其他流动资产里会重复计入资产：
 *
 * | 历史固定行 | 真实归属 |
 * |---|---|
 * | 预付款项 | 报表行 `BS-008`，F1 循环 |
 * | 合同资产 | 独立报表行，D6 循环 |
 * | 押金保证金 | 其他应收款的款项性质，K1 循环 |
 *
 * 这三行**不静默删除**（既有项目可能已录数据），只在 UI 显示警示 tooltip，
 * 由审计师判断后自行删除。
 *
 * spec: .kiro/specs/k2-four-table-extraction-and-dynamic-rows/ Task 3.1
 *       Requirements 2.1, 2.4, 2.5
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
 * 属于**别的报表行**的历史固定行 → 警示文案。
 *
 * key 与 `K2_LEGACY_ROWS` 的 key 逐字对应（`foreignRowWarning` 按 `rowId` 命中）。
 */
export const K2_LEGACY_FOREIGN_WARNINGS: Readonly<Record<string, string>> = {
  prepayment:
    '「预付款项」属于报表行 BS-008（F1 循环），列在其他流动资产会重复计入资产。'
    + '如该行有数据请核实后删除。',
  'contract-asset':
    '「合同资产」有独立报表行（D6 循环），不应在其他流动资产列示。如该行有数据请核实后删除。',
  deposit:
    '「押金保证金」属于其他应收款的款项性质（K1 循环），不应在其他流动资产列示。'
    + '如该行有数据请核实后删除。',
}

/**
 * 历史固定行（迁移源）—— `key` 即旧 rowKey，迁移后作为 `rowId` 沿用，
 * 使 `K2-1-{key}-unadj` 等既有持久化键继续命中（零丢数）。
 */
export const K2_LEGACY_ROWS: readonly LegacyFixedRow[] = [
  { key: 'contract-cost', label: '合同取得成本' },
  { key: 'prepayment', label: '预付款项', foreignWarning: K2_LEGACY_FOREIGN_WARNINGS.prepayment },
  { key: 'deferred-expense', label: '待摊费用' },
  { key: 'tax-deductible', label: '待抵扣税额' },
  {
    key: 'contract-asset',
    label: '合同资产',
    foreignWarning: K2_LEGACY_FOREIGN_WARNINGS['contract-asset'],
  },
  { key: 'deposit', label: '押金保证金', foreignWarning: K2_LEGACY_FOREIGN_WARNINGS.deposit },
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
 * 委托贷款 / 预缴其他税费 / 应收退货成本。
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
