/** G10-4 分类适当性检查 — 共享数据模型 */
export type G10Yn = 'yes' | 'no' | 'na' | ''

export interface G10ClassificationRow {
  id: string
  seq: number
  liabilityName: string
  closingBookValue: number
  tradingNearTermSale: G10Yn
  tradingPortfolioShortTerm: G10Yn
  tradingDerivative: G10Yn
  designatedMismatch: G10Yn
  designatedFvManagement: G10Yn
  indexRef: string
  liabilityCategory?: string
  detailRowId?: string
}

export const G10_YN_OPTIONS = [
  { value: 'yes', label: '是 / √' },
  { value: 'no', label: '否' },
  { value: 'na', label: '不适用' },
] as const

export function emptyClassificationRow(id: string, seq: number): G10ClassificationRow {
  return {
    id,
    seq,
    liabilityName: '',
    closingBookValue: 0,
    tradingNearTermSale: '',
    tradingPortfolioShortTerm: '',
    tradingDerivative: '',
    designatedMismatch: '',
    designatedFvManagement: '',
    indexRef: '',
  }
}

export function hasClassificationBasis(row: G10ClassificationRow): boolean {
  return (
    row.tradingNearTermSale === 'yes'
    || row.tradingPortfolioShortTerm === 'yes'
    || row.tradingDerivative === 'yes'
    || row.designatedMismatch === 'yes'
    || row.designatedFvManagement === 'yes'
  )
}

export function classifyBasisLabel(row: G10ClassificationRow): string {
  const parts: string[] = []
  if (row.tradingNearTermSale === 'yes' || row.tradingPortfolioShortTerm === 'yes' || row.tradingDerivative === 'yes') {
    const t: string[] = []
    if (row.tradingNearTermSale === 'yes') t.push('近期出售/回购')
    if (row.tradingPortfolioShortTerm === 'yes') t.push('组合短期获利')
    if (row.tradingDerivative === 'yes') t.push('衍生金融负债')
    parts.push(`交易性（${t.join('、')}）`)
  }
  if (row.designatedMismatch === 'yes') parts.push('初始指定消除会计错配')
  if (row.designatedFvManagement === 'yes') parts.push('初始指定公允价值管理')
  return parts.length ? parts.join('；') : '未勾选分类依据'
}
