export type F2DetailIdentityMode = 'inventory' | 'inTransit' | 'dispatched'
export type F2DetailNoteProfile = 'standard' | 'inTransit' | 'dispatched'

export interface F2DetailSheetConfig {
  sheetCode: string
  categoryLabel: string
  accountCode: string
  hasQuantity: boolean
  extraColumnLabel?: string
  /** 身份列：存货编码/名称/规格 vs 对方单位/名称及规格 */
  identityMode?: F2DetailIdentityMode
  /** 对方单位列标题（在途=供货单位，发出=购货单位） */
  partyColumnLabel?: string
  /** 对方模式下名称列标题 */
  materialNameLabel?: string
  /** 名称列标题，默认「存货名称」；F2-6 为「自制半成品名称」 */
  itemNameLabel?: string
  /** 增加列组名，默认「本期购进」 */
  increaseGroupLabel?: string
  /** 期后结转（数量/单价/金额）— F2-4 / F2-9 */
  hasPostPeriod?: boolean
  /** 减少列组名：本期发出 / 本期转出 */
  decreaseGroupLabel?: string
  /** F2-8：在手订单 / 订单编号 / 销售单价 */
  hasSalesOrderCols?: boolean
  /** F2-8 / F2-9：销售台账出库数量与差异勾稽 */
  hasSalesLedgerRecon?: boolean
  /** 审计说明四问文案档案 */
  noteProfile?: F2DetailNoteProfile
}

export const F2_DETAIL_SHEET_CONFIGS: Record<string, F2DetailSheetConfig> = {
  'F2-3': { sheetCode: 'F2-3', categoryLabel: '原材料', accountCode: '1401', hasQuantity: true },
  'F2-4': {
    sheetCode: 'F2-4',
    categoryLabel: '材料采购/在途物资',
    accountCode: '1402',
    hasQuantity: true,
    identityMode: 'inTransit',
    partyColumnLabel: '供货单位',
    materialNameLabel: '采购物资名称及规格',
    hasPostPeriod: true,
    decreaseGroupLabel: '本期转出',
    noteProfile: 'inTransit',
  },
  'F2-5': { sheetCode: 'F2-5', categoryLabel: '周转材料', accountCode: '1403', hasQuantity: true },
  'F2-6': {
    sheetCode: 'F2-6',
    categoryLabel: '自制半成品',
    accountCode: '1404',
    hasQuantity: true,
    itemNameLabel: '自制半成品名称',
  },
  'F2-7': { sheetCode: 'F2-7', categoryLabel: '委托加工物资', accountCode: '1405', hasQuantity: true },
  'F2-8': {
    sheetCode: 'F2-8',
    categoryLabel: '库存商品',
    accountCode: '1406',
    hasQuantity: true,
    hasSalesOrderCols: true,
    hasSalesLedgerRecon: true,
  },
  'F2-9': {
    sheetCode: 'F2-9',
    categoryLabel: '发出商品',
    accountCode: '1407',
    hasQuantity: true,
    identityMode: 'dispatched',
    partyColumnLabel: '购货单位',
    materialNameLabel: '发出商品名称及规格',
    increaseGroupLabel: '本期转入',
    decreaseGroupLabel: '本期转出',
    hasPostPeriod: true,
    hasSalesLedgerRecon: true,
    noteProfile: 'dispatched',
  },
  'F2-10': { sheetCode: 'F2-10', categoryLabel: '开发产品', accountCode: '1408', hasQuantity: true },
  'F2-11': { sheetCode: 'F2-11', categoryLabel: '开发成本', accountCode: '1409', hasQuantity: true },
  'F2-12': { sheetCode: 'F2-12', categoryLabel: '合同履约成本', accountCode: '1410', hasQuantity: false },
  'F2-13': { sheetCode: 'F2-13', categoryLabel: '消耗性生物资产', accountCode: '1411', hasQuantity: true },
}

export function getF2DetailConfig(sheetCode: string): F2DetailSheetConfig | undefined {
  // 专用表：周转/委托加工/开发产品/开发成本/合同履约/消耗性生物资产
  if (
    sheetCode === 'F2-5'
    || sheetCode === 'F2-7'
    || sheetCode === 'F2-10'
    || sheetCode === 'F2-11'
    || sheetCode === 'F2-12'
    || sheetCode === 'F2-13'
  ) {
    return undefined
  }
  return F2_DETAIL_SHEET_CONFIGS[sheetCode]
}
