export interface F2DetailSheetConfig {
  sheetCode: string
  categoryLabel: string
  accountCode: string
  hasQuantity: boolean
  extraColumnLabel?: string
}

export const F2_DETAIL_SHEET_CONFIGS: Record<string, F2DetailSheetConfig> = {
  'F2-3': { sheetCode: 'F2-3', categoryLabel: '原材料', accountCode: '1401', hasQuantity: true },
  'F2-4': { sheetCode: 'F2-4', categoryLabel: '材料采购在途', accountCode: '1402', hasQuantity: true },
  'F2-5': { sheetCode: 'F2-5', categoryLabel: '周转材料', accountCode: '1403', hasQuantity: true },
  'F2-6': { sheetCode: 'F2-6', categoryLabel: '自制半成品', accountCode: '1404', hasQuantity: true },
  'F2-7': { sheetCode: 'F2-7', categoryLabel: '委托加工物资', accountCode: '1405', hasQuantity: true },
  'F2-8': { sheetCode: 'F2-8', categoryLabel: '库存商品', accountCode: '1406', hasQuantity: true, extraColumnLabel: '出库方式' },
  'F2-9': { sheetCode: 'F2-9', categoryLabel: '发出商品', accountCode: '1407', hasQuantity: true },
  'F2-10': { sheetCode: 'F2-10', categoryLabel: '开发产品', accountCode: '1408', hasQuantity: true },
  'F2-11': { sheetCode: 'F2-11', categoryLabel: '开发成本', accountCode: '1409', hasQuantity: true },
  'F2-12': { sheetCode: 'F2-12', categoryLabel: '合同履约成本', accountCode: '1410', hasQuantity: false },
  'F2-13': { sheetCode: 'F2-13', categoryLabel: '消耗性生物资产', accountCode: '1411', hasQuantity: true },
}

export function getF2DetailConfig(sheetCode: string): F2DetailSheetConfig | undefined {
  if (sheetCode === 'F2-10') return undefined
  return F2_DETAIL_SHEET_CONFIGS[sheetCode]
}
