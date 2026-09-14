/** G12-5 风险净敞口检查 — 源模板对齐（头寸对账表） */

export const G12_NET_EXPOSURE_TEST_OBJECTIVE =
  '检查风险净敞口的支持性证据'

export const G12_NET_EXPOSURE_SAMPLE_CRITERIA =
  '运用风险净敞口套期的风险净敞口'

export interface G12NetExposureRowSeed {
  item: string
  currency: string
  position1Desc: string
  position1Amount: string
  position2Desc: string
  position2Amount: string
  netPosition: string
  evidenceType?: string
  supportingEvidence: string
  hedgingInstrument: string
  indexRef: string
}

/** 源模板示例行（红字指引） */
export const G12_NET_EXPOSURE_SEED: G12NetExposureRowSeed[] = [
  {
    item: '预期销售和预期采购的外汇净头寸',
    currency: 'USD',
    position1Desc: '预期外币销售收入',
    position1Amount: '1,000万美元',
    position2Desc: '预期外币固定资产采购',
    position2Amount: '1,200万美元',
    netPosition: '支付200万美元',
    evidenceType: 'sales_budget',
    supportingEvidence: '销售与采购预算表',
    hedgingInstrument: '',
    indexRef: '',
  },
]
