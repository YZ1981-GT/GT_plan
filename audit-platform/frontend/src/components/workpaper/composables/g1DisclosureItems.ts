/**
 * G1 上市附注披露 — 分段行定义（对齐 Excel「附注披露信息（上市公司）」）
 * ①分类 ②衍生 ③FV层次 ④输入值 ⑤L3调节 ⑥非FV项目
 */

import { G1_GROSS_FALLBACK_STANDARD } from './g1AccountScope'

export const G1_ACCOUNT_CODE = G1_GROSS_FALLBACK_STANDARD

export type G1DisclosureTabKey =
  | 'classification'
  | 'derivative'
  | 'fvHierarchy'
  | 'inputs'
  | 'l3Rollforward'
  | 'amortizedCost'

export const G1_DISCLOSURE_TABS: { key: G1DisclosureTabKey; label: string; sourceChip: string }[] = [
  { key: 'classification', label: '① 分类披露', sourceChip: 'wp:G1-1' },
  { key: 'derivative', label: '② 衍生工具', sourceChip: 'wp:G1-14' },
  { key: 'fvHierarchy', label: '③ FV层次', sourceChip: 'wp:G1-6' },
  { key: 'inputs', label: '④ 输入值', sourceChip: 'wp:G1-6' },
  { key: 'l3Rollforward', label: '⑤ L3调节', sourceChip: 'wp:G1-7' },
  { key: 'amortizedCost', label: '⑥ 非FV披露', sourceChip: 'wp:G1-1' },
]

/** 估值技术 → 推荐不可观察/可观察输入值（编制人勾选） */
export const G1_VALUATION_TECHNIQUE_OPTIONS = [
  { value: 'market', label: '市场法（可比公司法等）' },
  { value: 'income', label: '收益法（现金流量折现）' },
  { value: 'nav', label: '净资产价值法' },
  { value: 'dcf_debt', label: '债务工具现金流量折现' },
  { value: 'option', label: '期权定价模型' },
] as const

export const G1_INPUT_CANDIDATES: Record<string, string[]> = {
  market: ['流动性折扣', '市盈率', '市净率', 'EV/EBITDA', '近期交易价格'],
  income: ['折现率', '长期收入增长率', '永续增长率', '预测期现金流'],
  nav: ['净资产价值', '单位净值', '资产减值调整'],
  dcf_debt: ['合同利率', '预期利率', '提前还款率', '违约率', '回收率'],
  option: ['期权波动率', '无风险利率', '标的资产价格', '自身信用风险'],
}

export interface G1DiscAmountRow {
  rowKey: string
  label: string
  kind: 'header' | 'leaf' | 'subtotal'
  indent?: number
  endAmount: number
  priorAmount: number
  remark?: string
  /** 对应 G1-1 carrying 叶子 key，便于从审定表带数 */
  adjKey?: string
  applicable?: boolean
}

export interface G1DiscHierarchyRow {
  rowKey: string
  label: string
  kind: 'header' | 'leaf' | 'subtotal'
  indent?: number
  l1: number
  l2: number
  l3: number
  priorL1?: number
  priorL2?: number
  priorL3?: number
  applicable?: boolean
}

export interface G1DiscInputRow {
  rowKey: string
  content: string
  endFv: number
  technique: string
  inputs: string
  range: string
  level: 2 | 3
  selectedIndicators: string[]
}

export interface G1DiscL3RollRow {
  rowKey: string
  label: string
  kind: 'header' | 'leaf' | 'subtotal'
  opening: number
  transferIn: number
  transferOut: number
  gainPl: number
  gainOci: number
  purchase: number
  issue: number
  sale: number
  settlement: number
  closing: number
  unrealizedHeld: number
}

export interface G1DiscAmortRow {
  rowKey: string
  label: string
  bookValue: number
  l1: number
  l2: number
  l3: number
  remark?: string
}

function classLeaves(
  prefix: string,
  classLabel: string,
  assets: { key: string; label: string; adjKey: string }[],
): G1DiscAmountRow[] {
  const rows: G1DiscAmountRow[] = [
    { rowKey: `${prefix}__h`, label: classLabel, kind: 'header', indent: 0, endAmount: 0, priorAmount: 0 },
  ]
  for (const a of assets) {
    rows.push({
      rowKey: `${prefix}-${a.key}`,
      label: a.label,
      kind: 'leaf',
      indent: 1,
      endAmount: 0,
      priorAmount: 0,
      adjKey: a.adjKey,
      applicable: true,
    })
  }
  return rows
}

const ASSET_FULL = [
  { key: 'debt', label: '债务工具投资', adjSuffix: 'debt' },
  { key: 'equity', label: '权益工具投资', adjSuffix: 'equity' },
  { key: 'derivative', label: '衍生金融资产', adjSuffix: 'derivative' },
  { key: 'wealth', label: '理财产品', adjSuffix: 'wealth' },
  { key: 'structured', label: '结构性存款', adjSuffix: 'structured' },
  { key: 'fund', label: '基金', adjSuffix: 'fund' },
  { key: 'other', label: '其他', adjSuffix: 'other' },
]

/** ① 分类披露默认行（划分为 + 指定） */
export function defaultClassificationRows(): G1DiscAmountRow[] {
  const classified = classLeaves(
    'classified',
    '以公允价值计量且其变动计入当期损益的金融资产',
    ASSET_FULL.map((a) => ({
      key: a.key,
      label: a.label,
      adjKey: `carrying-classified-${a.adjSuffix}`,
    })),
  )
  const designated = classLeaves(
    'designated',
    '指定为以公允价值计量且其变动计入当期损益的金融资产',
    [
      { key: 'debt', label: '债务工具投资', adjKey: 'carrying-designated-debt' },
      { key: 'other', label: '其他', adjKey: 'carrying-designated-other' },
    ],
  )
  return [
    ...classified,
    ...designated,
    { rowKey: 'classification__total', label: '合计', kind: 'subtotal', indent: 0, endAmount: 0, priorAmount: 0 },
  ]
}

export function defaultDerivativeRows(): G1DiscAmountRow[] {
  return [
    { rowKey: 'deriv-interest', label: '利率衍生工具', kind: 'leaf', endAmount: 0, priorAmount: 0, applicable: true },
    { rowKey: 'deriv-fx', label: '汇率衍生工具', kind: 'leaf', endAmount: 0, priorAmount: 0, applicable: true },
    { rowKey: 'deriv-commodity', label: '商品衍生工具', kind: 'leaf', endAmount: 0, priorAmount: 0, applicable: true },
    { rowKey: 'deriv-other', label: '其他衍生工具', kind: 'leaf', endAmount: 0, priorAmount: 0, applicable: true },
    { rowKey: 'deriv__total', label: '合计', kind: 'subtotal', endAmount: 0, priorAmount: 0 },
  ]
}

export function defaultFvHierarchyRows(): G1DiscHierarchyRow[] {
  return [
    { rowKey: 'fv__h_asset', label: '一、持续的公允价值计量 — 资产', kind: 'header', l1: 0, l2: 0, l3: 0 },
    {
      rowKey: 'fv-trading',
      label: '交易性金融资产',
      kind: 'leaf',
      indent: 1,
      l1: 0,
      l2: 0,
      l3: 0,
      applicable: true,
    },
    {
      rowKey: 'fv-derivative',
      label: '衍生金融资产',
      kind: 'leaf',
      indent: 1,
      l1: 0,
      l2: 0,
      l3: 0,
      applicable: true,
    },
    { rowKey: 'fv__total', label: '合计', kind: 'subtotal', l1: 0, l2: 0, l3: 0 },
  ]
}

export function defaultInputRows(): G1DiscInputRow[] {
  return [
    {
      rowKey: 'in-l2-deriv',
      content: '衍生工具',
      endFv: 0,
      technique: 'option',
      inputs: '',
      range: '',
      level: 2,
      selectedIndicators: [],
    },
    {
      rowKey: 'in-l2-debt',
      content: '债务工具投资',
      endFv: 0,
      technique: 'dcf_debt',
      inputs: '',
      range: '',
      level: 2,
      selectedIndicators: [],
    },
    {
      rowKey: 'in-l3-equity',
      content: '权益工具投资',
      endFv: 0,
      technique: 'market',
      inputs: '',
      range: '',
      level: 3,
      selectedIndicators: [],
    },
    {
      rowKey: 'in-l3-fund',
      content: '私募基金',
      endFv: 0,
      technique: 'nav',
      inputs: '',
      range: '',
      level: 3,
      selectedIndicators: [],
    },
  ]
}

export function defaultL3RollRows(): G1DiscL3RollRow[] {
  const leaf = (key: string, label: string): G1DiscL3RollRow => ({
    rowKey: key,
    label,
    kind: 'leaf',
    opening: 0,
    transferIn: 0,
    transferOut: 0,
    gainPl: 0,
    gainOci: 0,
    purchase: 0,
    issue: 0,
    sale: 0,
    settlement: 0,
    closing: 0,
    unrealizedHeld: 0,
  })
  return [
    { ...leaf('l3__h', '持续以公允价值计量的第三层次项目'), kind: 'header' },
    leaf('l3-trading-debt', '交易性金融资产 — 债务工具'),
    leaf('l3-trading-equity', '交易性金融资产 — 权益工具'),
    leaf('l3-derivative', '衍生金融资产'),
    { ...leaf('l3__total', '合计'), kind: 'subtotal' },
  ]
}

export function defaultAmortRows(): G1DiscAmortRow[] {
  return [
    { rowKey: 'ac-fa', label: '金融资产（摊余成本近似公允价值）', bookValue: 0, l1: 0, l2: 0, l3: 0, remark: '现金/应收等通常近似账面' },
    { rowKey: 'ac-debt-inv', label: '债权投资', bookValue: 0, l1: 0, l2: 0, l3: 0 },
    { rowKey: 'ac-lt-recv', label: '长期应收款', bookValue: 0, l1: 0, l2: 0, l3: 0 },
    { rowKey: 'ac-fl', label: '金融负债（摊余成本）', bookValue: 0, l1: 0, l2: 0, l3: 0 },
    { rowKey: 'ac-lt-loan', label: '长期借款', bookValue: 0, l1: 0, l2: 0, l3: 0, remark: '无活跃市场时常用折现→L3' },
    { rowKey: 'ac-bond', label: '应付债券', bookValue: 0, l1: 0, l2: 0, l3: 0 },
  ]
}

export function sumAmountLeaves(rows: G1DiscAmountRow[]): { end: number; prior: number } {
  const leaves = rows.filter((r) => r.kind === 'leaf' && r.applicable !== false)
  return {
    end: leaves.reduce((s, r) => s + (Number(r.endAmount) || 0), 0),
    prior: leaves.reduce((s, r) => s + (Number(r.priorAmount) || 0), 0),
  }
}

export function hierarchyTotal(rows: G1DiscHierarchyRow[]): { l1: number; l2: number; l3: number; total: number } {
  const leaves = rows.filter((r) => r.kind === 'leaf' && r.applicable !== false)
  const l1 = leaves.reduce((s, r) => s + (Number(r.l1) || 0), 0)
  const l2 = leaves.reduce((s, r) => s + (Number(r.l2) || 0), 0)
  const l3 = leaves.reduce((s, r) => s + (Number(r.l3) || 0), 0)
  return { l1, l2, l3, total: l1 + l2 + l3 }
}

export function calcL3Closing(r: G1DiscL3RollRow): number {
  return (
    (Number(r.opening) || 0)
    + (Number(r.transferIn) || 0)
    - (Number(r.transferOut) || 0)
    + (Number(r.gainPl) || 0)
    + (Number(r.gainOci) || 0)
    + (Number(r.purchase) || 0)
    + (Number(r.issue) || 0)
    - (Number(r.sale) || 0)
    - (Number(r.settlement) || 0)
  )
}
