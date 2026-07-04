export interface F2CutoffSheetConfig {
  sheetCode: string
  title: string
  direction: 'inbound' | 'outbound'
  testType: 'forward' | 'backward'
}

/** 存货科目组（1401~1411，不含1412跌价准备） */
export const F2_INVENTORY_ACCOUNT_CODES = '1401,1402,1403,1404,1405,1406,1407,1408,1409,1410,1411'

export function getF2CutoffSamplingParams(config: F2CutoffSheetConfig): {
  cutoffDirection: 'post_cutoff' | 'pre_cutoff'
  directionFilter: 'debit' | 'credit'
} {
  const directionFilter = config.direction === 'inbound' ? 'debit' : 'credit'
  return {
    cutoffDirection: config.testType === 'forward' ? 'post_cutoff' : 'pre_cutoff',
    directionFilter,
  }
}

export const F2_CUTOFF_CONFIGS: Record<string, F2CutoffSheetConfig> = {
  'F2-29': { sheetCode: 'F2-29', title: '截止测试-入库(正向)', direction: 'inbound', testType: 'forward' },
  'F2-30': { sheetCode: 'F2-30', title: '截止测试-入库(反向)', direction: 'inbound', testType: 'backward' },
  'F2-31': { sheetCode: 'F2-31', title: '截止测试-出库(正向)', direction: 'outbound', testType: 'forward' },
  'F2-32': { sheetCode: 'F2-32', title: '截止测试-出库(反向)', direction: 'outbound', testType: 'backward' },
}

export function getF2CutoffConfig(code: string): F2CutoffSheetConfig | undefined {
  return F2_CUTOFF_CONFIGS[code]
}
