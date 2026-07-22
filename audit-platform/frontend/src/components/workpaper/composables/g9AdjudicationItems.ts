/**
 * G9-1 审定表行定义 — 对齐 Excel「审定表G9-1」分类口径
 *
 * 编制逻辑（对照致同模板）：
 * 1. 按计量属性分组（FVTPL / FVOCI / 摊余成本），与 CAS 22 业务模式一致
 * 2. FVTPL 组内按附注披露四类展开：债务 / 权益 / 衍生·其他 / 指定
 * 3. 各组首行（*_1）承接 G9-2/G9-3 回写合计，明细行供分项分析与附注带入
 * 4. 投资成本 / 累计公允价值变动明细见 G9-2；本表列报账面余额（公允价值）审定过程
 */

export type G9MeasurementCategory = 'FVTPL' | 'FVOCI' | 'AmortizedCost'

/** 附注分项桶；undefined 表示不参与附注分项汇总（如组首行合计） */
export type G9DiscBucketHint = 'debt' | 'equity' | 'designated' | 'other'

export interface G9AdjudicationLineDef {
  rowKey: string
  label: string
  category: G9MeasurementCategory
  /** 组首行：承接明细/调整回写，不计入附注四类分项（避免与明细双计） */
  isGroupTotal?: boolean
  /** 显式指定附注分项；优先于标签正则 */
  discBucket?: G9DiscBucketHint
}

export const G9_GROUP_LABELS: Record<G9MeasurementCategory, string> = {
  FVTPL: '一、以公允价值计量且变动计入当期损益(FVTPL)',
  FVOCI: '二、以公允价值计量且变动计入其他综合收益(FVOCI)',
  AmortizedCost: '三、以摊余成本计量',
}

/**
 * FVTPL — 对齐 Excel：其他非流动金融资产 / 分类为FVTPL / 指定为FVTPL × 工具种类
 * 本表填列账面余额（公允价值）；成本与累计公允变动在 G9-2 展开
 */
const FVTPL_LINES: G9AdjudicationLineDef[] = [
  { rowKey: 'fvtpl_1', label: '其他非流动金融资产（合计）', category: 'FVTPL', isGroupTotal: true },
  { rowKey: 'fvtpl_2', label: '债务工具投资', category: 'FVTPL', discBucket: 'debt' },
  { rowKey: 'fvtpl_3', label: '权益工具投资', category: 'FVTPL', discBucket: 'equity' },
  { rowKey: 'fvtpl_4', label: '衍生金融资产', category: 'FVTPL', discBucket: 'other' },
  { rowKey: 'fvtpl_5', label: '其他', category: 'FVTPL', discBucket: 'other' },
  {
    rowKey: 'fvtpl_6',
    label: '指定为以公允价值计量且其变动计入当期损益的金融资产',
    category: 'FVTPL',
    discBucket: 'designated',
  },
  /** 指定项展开，仅审定分析用，不重复计入附注「指定」桶 */
  { rowKey: 'fvtpl_7', label: '其中：债务工具投资（指定）', category: 'FVTPL' },
  { rowKey: 'fvtpl_8', label: '其中：其他（指定）', category: 'FVTPL' },
]

const FVOCI_LINES: G9AdjudicationLineDef[] = [
  { rowKey: 'fvoci_1', label: 'FVOCI 金融资产（合计）', category: 'FVOCI', isGroupTotal: true },
  { rowKey: 'fvoci_2', label: '债务工具投资', category: 'FVOCI', discBucket: 'debt' },
  { rowKey: 'fvoci_3', label: '权益工具投资', category: 'FVOCI', discBucket: 'equity' },
  { rowKey: 'fvoci_4', label: '其他', category: 'FVOCI', discBucket: 'other' },
]

const AMORT_LINES: G9AdjudicationLineDef[] = [
  { rowKey: 'amort_1', label: '摊余成本计量金融资产（合计）', category: 'AmortizedCost', isGroupTotal: true },
  { rowKey: 'amort_2', label: '债务工具投资', category: 'AmortizedCost', discBucket: 'debt' },
  { rowKey: 'amort_3', label: '其他', category: 'AmortizedCost', discBucket: 'other' },
]

/** 15 行：FVTPL 8 + FVOCI 4 + 摊余成本 3（对齐 Excel 分类，去掉虚构产品种子行） */
export const G9_ADJUDICATION_ITEMS: G9AdjudicationLineDef[] = [
  ...FVTPL_LINES,
  ...FVOCI_LINES,
  ...AMORT_LINES,
]

export const G9_ADJUDICATION_ROW_COUNT = G9_ADJUDICATION_ITEMS.length
