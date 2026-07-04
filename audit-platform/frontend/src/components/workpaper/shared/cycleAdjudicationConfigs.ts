/**
 * 各循环审定表行配置 — F3~G14 及扩展
 */
export type AccountDirection = 'debit' | 'credit'

export interface CycleAdjudicationConfig {
  sheetCode: string
  accountCode: string
  accountLabel: string
  direction: AccountDirection
  rows: { rowKey: string; label: string }[]
}

export const CYCLE_ADJUDICATION_CONFIGS: Record<string, CycleAdjudicationConfig> = {
  'F3-1': {
    sheetCode: 'F3-1',
    accountCode: '2201',
    accountLabel: '应付票据',
    direction: 'credit',
    rows: [
      { rowKey: 'bank', label: '银行承兑汇票' },
      { rowKey: 'commercial', label: '商业承兑汇票' },
    ],
  },
  'F4-1': {
    sheetCode: 'F4-1',
    accountCode: '2202',
    accountLabel: '应付账款',
    direction: 'credit',
    rows: [
      { rowKey: 'goods', label: '应付货款' },
      { rowKey: 'services', label: '应付劳务款' },
      { rowKey: 'other', label: '其他' },
    ],
  },
  'F5-1': {
    sheetCode: 'F5-1',
    accountCode: '6401',
    accountLabel: '主营业务成本',
    direction: 'debit',
    rows: [
      { rowKey: 'main', label: '主营业务成本' },
      { rowKey: 'other', label: '其他业务成本' },
    ],
  },
  'G2-1': {
    sheetCode: 'G2-1',
    accountCode: '1132',
    accountLabel: '应收利息',
    direction: 'debit',
    rows: [
      { rowKey: 'bond', label: '债权投资利息' },
      { rowKey: 'other-bond', label: '其他债权投资利息' },
      { rowKey: 'deposit', label: '定期存款利息' },
      { rowKey: 'other', label: '其他' },
    ],
  },
  'G3-1': {
    sheetCode: 'G3-1',
    accountCode: '1131',
    accountLabel: '应收股利',
    direction: 'debit',
    rows: [
      { rowKey: 'listed', label: '上市公司股利' },
      { rowKey: 'unlisted', label: '非上市公司股利' },
      { rowKey: 'other', label: '其他' },
    ],
  },
  'G4-1': {
    sheetCode: 'G4-1',
    accountCode: '1503',
    accountLabel: '债权投资',
    direction: 'debit',
    rows: [
      { rowKey: 'gov', label: '国债' },
      { rowKey: 'corp', label: '企业债' },
      { rowKey: 'other', label: '其他' },
    ],
  },
  'G5-1': {
    sheetCode: 'G5-1',
    accountCode: '1531',
    accountLabel: '长期应收款',
    direction: 'debit',
    rows: [
      { rowKey: 'finance-lease', label: '融资租赁' },
      { rowKey: 'installment', label: '分期收款' },
      { rowKey: 'other', label: '其他' },
    ],
  },
  'G8-1': {
    sheetCode: 'G8-1',
    accountCode: '1504',
    accountLabel: '其他权益工具投资',
    direction: 'debit',
    rows: [
      { rowKey: 'listed', label: '上市公司' },
      { rowKey: 'unlisted', label: '非上市公司' },
    ],
  },
  'G9-1': {
    sheetCode: 'G9-1',
    accountCode: '1505',
    accountLabel: '其他非流动金融资产',
    direction: 'debit',
    rows: [{ rowKey: 'total', label: '合计' }],
  },
  'G10-1': {
    sheetCode: 'G10-1',
    accountCode: '2101',
    accountLabel: '交易性金融负债',
    direction: 'credit',
    rows: [
      { rowKey: 'derivative', label: '衍生工具' },
      { rowKey: 'other', label: '其他' },
    ],
  },
  'G11-1': {
    sheetCode: 'G11-1',
    accountCode: '6111',
    accountLabel: '投资收益',
    direction: 'credit',
    rows: [
      { rowKey: 'equity', label: '股权投资收益' },
      { rowKey: 'debt', label: '债权投资收益' },
      { rowKey: 'other', label: '其他' },
    ],
  },
  'G12-1': {
    sheetCode: 'G12-1',
    accountCode: '6101',
    accountLabel: '净敞口套期收益',
    direction: 'credit',
    rows: [{ rowKey: 'total', label: '合计' }],
  },
  'G13-1': {
    sheetCode: 'G13-1',
    accountCode: '6102',
    accountLabel: '公允价值变动损益',
    direction: 'credit',
    rows: [
      { rowKey: 'trading', label: '交易性金融资产' },
      { rowKey: 'derivative', label: '衍生工具' },
      { rowKey: 'other', label: '其他' },
    ],
  },
  'G14-1': {
    sheetCode: 'G14-1',
    accountCode: '6702',
    accountLabel: '信用减值损失',
    direction: 'debit',
    rows: [
      { rowKey: 'receivable', label: '应收款项' },
      { rowKey: 'debt', label: '债权投资' },
      { rowKey: 'other', label: '其他' },
    ],
  },
}

export function getAdjudicationConfig(sheetCode: string): CycleAdjudicationConfig | undefined {
  return CYCLE_ADJUDICATION_CONFIGS[sheetCode]
}

export function adjudicationSheetForPrefix(prefix: string): string {
  return `${prefix}-1`
}
