/**
 * F2 存货科目映射纯模型（对齐 CAS + 后端 _f2_inventory_main.F2_CATEGORIES）
 *
 * 约定：
 * - 1401~1411：存货原值类
 * - 1412：商品进销差价（非跌价）
 * - 1471：存货跌价准备
 */
export const F2_PRICE_DIFF_ACCOUNT = '1412'
export const F2_IMPAIRMENT_ACCOUNT = '1471'

/** 审定表 rowKey → 科目编码 */
export const F2_ROW_KEY_ACCOUNT: Record<string, string> = {
  'raw-materials': '1401',
  'material-in-transit': '1402',
  'revolving-materials': '1403',
  'semi-finished': '1404',
  'outsourced-processing': '1405',
  'finished-goods': '1406',
  'goods-in-transit': '1407',
  'dev-products': '1408',
  'dev-costs': '1409',
  'contract-performance': '1410',
  'consumable-bio': '1411',
  'price-difference': F2_PRICE_DIFF_ACCOUNT,
  'impairment-provision': F2_IMPAIRMENT_ACCOUNT,
}

/**
 * 科目编码 → 审定表 rowKey。
 * 1406 映射库存商品（进销差价用独立 1412，不与 1406 冲突）。
 */
export const F2_ACCOUNT_TO_ROW_KEY: Record<string, string> = {
  '1401': 'raw-materials',
  '1402': 'material-in-transit',
  '1403': 'revolving-materials',
  '1404': 'semi-finished',
  '1405': 'outsourced-processing',
  '1406': 'finished-goods',
  '1407': 'goods-in-transit',
  '1408': 'dev-products',
  '1409': 'dev-costs',
  '1410': 'contract-performance',
  '1411': 'consumable-bio',
  [F2_PRICE_DIFF_ACCOUNT]: 'price-difference',
  [F2_IMPAIRMENT_ACCOUNT]: 'impairment-provision',
}

/** 调整分录可选科目（含进销差价 1412、跌价准备 1471） */
export const F2_INVENTORY_ACCOUNTS = [
  { code: '1401', name: '原材料' },
  { code: '1402', name: '材料采购在途' },
  { code: '1403', name: '周转材料' },
  { code: '1404', name: '自制半成品' },
  { code: '1405', name: '委托加工物资' },
  { code: '1406', name: '库存商品' },
  { code: '1407', name: '发出商品' },
  { code: '1408', name: '开发产品' },
  { code: '1409', name: '开发成本' },
  { code: '1410', name: '合同履约成本' },
  { code: '1411', name: '消耗性生物资产' },
  { code: F2_PRICE_DIFF_ACCOUNT, name: '商品进销差价' },
  { code: F2_IMPAIRMENT_ACCOUNT, name: '存货跌价准备' },
  { code: '5001', name: '主营业务成本' },
  { code: '6401', name: '主营业务成本' },
  { code: '6001', name: '主营业务收入' },
] as const

export interface F2AjeLike {
  entryType: string
  accountCode: string
  debitAmount: number
  creditAmount: number
}

/** F2-14 AJE → 原值账项调整（按科目汇总；跌价准备单独处理） */
export function sumGrossAjeByRowKey(rows: F2AjeLike[]): Record<string, number> {
  const result: Record<string, number> = {}
  for (const row of rows) {
    if (row.entryType !== 'AJE') continue
    const rowKey = F2_ACCOUNT_TO_ROW_KEY[row.accountCode]
    if (!rowKey || rowKey === 'impairment-provision') continue
    const delta = row.debitAmount - row.creditAmount
    result[rowKey] = (result[rowKey] || 0) + delta
  }
  return result
}

/** F2-14 AJE → 跌价准备账项调整（科目 1471） */
export function sumImpairmentAjeByRowKey(rows: F2AjeLike[]): Record<string, number> {
  const result: Record<string, number> = {}
  for (const row of rows) {
    if (row.entryType !== 'AJE') continue
    if (row.accountCode !== F2_IMPAIRMENT_ACCOUNT) continue
    const delta = row.creditAmount - row.debitAmount
    result['impairment-provision'] = (result['impairment-provision'] || 0) + delta
  }
  return result
}
