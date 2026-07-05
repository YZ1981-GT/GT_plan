/** G9-1 审定表行定义 — 74 数据行 × 3 计量分组 */

export type G9MeasurementCategory = 'FVTPL' | 'FVOCI' | 'AmortizedCost'

export interface G9AdjudicationLineDef {
  rowKey: string
  label: string
  category: G9MeasurementCategory
}

const LINE_TEMPLATES = [
  '其他非流动金融资产',
  '其中：债券投资',
  '其中：基金投资',
  '其中：结构性存款',
  '其中：衍生金融工具',
  '其中：理财产品',
  '其中：信托计划',
  '其中：私募基金',
  '其中：可转债',
  '其中：资产支持证券',
  '其中：国债',
  '其中：公司债',
  '其中：金融债券',
  '其中：中期票据',
  '其中：超短期融资券',
  '其中：同业存单',
  '其中：外币债券',
  '其中：境外投资',
  '其中：嵌入衍生工具',
  '其中：混合工具',
  '其中：权益工具投资',
  '其中：债务工具投资',
  '其中：其他投资',
  '其中：其他',
] as const

const GROUP_CONFIG: Array<{ category: G9MeasurementCategory; prefix: string; count: number }> = [
  { category: 'FVTPL', prefix: 'fvtpl', count: 25 },
  { category: 'FVOCI', prefix: 'fvoci', count: 25 },
  { category: 'AmortizedCost', prefix: 'amort', count: 24 },
]

function buildGroupRows(
  category: G9MeasurementCategory,
  prefix: string,
  count: number,
): G9AdjudicationLineDef[] {
  return Array.from({ length: count }, (_, i) => ({
    rowKey: `${prefix}_${i + 1}`,
    label: LINE_TEMPLATES[i % LINE_TEMPLATES.length] + (i >= LINE_TEMPLATES.length ? `（${Math.floor(i / LINE_TEMPLATES.length) + 1}）` : ''),
    category,
  }))
}

export const G9_GROUP_LABELS: Record<G9MeasurementCategory, string> = {
  FVTPL: '一、以公允价值计量且变动计入当期损益(FVTPL)',
  FVOCI: '二、以公允价值计量且变动计入其他综合收益(FVOCI)',
  AmortizedCost: '三、以摊余成本计量',
}

/** 74 行：FVTPL 25 + FVOCI 25 + 摊余成本 24 */
export const G9_ADJUDICATION_ITEMS: G9AdjudicationLineDef[] = GROUP_CONFIG.flatMap((g) =>
  buildGroupRows(g.category, g.prefix, g.count),
)
