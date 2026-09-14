/**
 * f2AccountModel — 科目映射与 AJE 汇总契约
 */
import { describe, it, expect } from 'vitest'
import {
  F2_PRICE_DIFF_ACCOUNT,
  F2_IMPAIRMENT_ACCOUNT,
  F2_ROW_KEY_ACCOUNT,
  F2_ACCOUNT_TO_ROW_KEY,
  F2_INVENTORY_ACCOUNTS,
  sumGrossAjeByRowKey,
  sumImpairmentAjeByRowKey,
  resolveF2InventoryAccounts,
  resolveF2AccountToRowKey,
  resolveF2RowKeyToAccounts,
  type F2InventoryAccountItem,
} from '../f2AccountModel'

describe('f2AccountModel', () => {
  it('maps 进销差价=1412 and 跌价准备=1471 (CAS / backend)', () => {
    expect(F2_PRICE_DIFF_ACCOUNT).toBe('1412')
    expect(F2_IMPAIRMENT_ACCOUNT).toBe('1471')
    expect(F2_ROW_KEY_ACCOUNT['price-difference']).toBe('1412')
    expect(F2_ROW_KEY_ACCOUNT['impairment-provision']).toBe('1471')
    expect(F2_ROW_KEY_ACCOUNT['finished-goods']).toBe('1406')
    expect(F2_ACCOUNT_TO_ROW_KEY['1406']).toBe('finished-goods')
    expect(F2_ACCOUNT_TO_ROW_KEY['1412']).toBe('price-difference')
    expect(F2_ACCOUNT_TO_ROW_KEY['1471']).toBe('impairment-provision')
  })

  it('adjustment account list uses 1412 for price-diff and 1471 for impairment', () => {
    const byCode = Object.fromEntries(F2_INVENTORY_ACCOUNTS.map((a) => [a.code, a.name]))
    expect(byCode['1412']).toBe('商品进销差价')
    expect(byCode['1471']).toBe('存货跌价准备')
    expect(byCode['1406']).toBe('库存商品')
  })

  it('sumGrossAjeByRowKey aggregates non-impairment AJE including 1412 price-diff', () => {
    const result = sumGrossAjeByRowKey([
      { entryType: 'AJE', accountCode: '1401', debitAmount: 100, creditAmount: 0 },
      { entryType: 'AJE', accountCode: '1412', debitAmount: 0, creditAmount: 30 },
      { entryType: 'AJE', accountCode: '1471', debitAmount: 0, creditAmount: 50 },
      { entryType: 'RJE', accountCode: '1401', debitAmount: 20, creditAmount: 0 },
    ])
    expect(result['raw-materials']).toBe(100)
    expect(result['price-difference']).toBe(-30)
    expect(result['impairment-provision']).toBeUndefined()
  })

  it('sumImpairmentAjeByRowKey only uses 1471 (not legacy 1412)', () => {
    const result = sumImpairmentAjeByRowKey([
      { entryType: 'AJE', accountCode: '1471', debitAmount: 10, creditAmount: 40 },
      { entryType: 'AJE', accountCode: '1412', debitAmount: 0, creditAmount: 99 },
      { entryType: 'RJE', accountCode: '1471', debitAmount: 0, creditAmount: 5 },
    ])
    expect(result['impairment-provision']).toBe(30)
  })
})

describe('resolveF2InventoryAccounts / resolveF2AccountToRowKey / resolveF2RowKeyToAccounts (Wave 3)', () => {
  // 变体 B 项目实证：1405=库存商品/1406=发出商品（与变体 A 完全相反）
  const variantBDynamic: F2InventoryAccountItem[] = [
    { code: '1405', name: '库存商品', row_key: 'finished-goods' },
    { code: '1406', name: '发出商品', row_key: 'goods-in-transit' },
    { code: '1461', name: '存货跌价准备', row_key: 'impairment-provision' },
  ]

  it('resolveF2InventoryAccounts prefers dynamic project chart over static fallback', () => {
    const resolved = resolveF2InventoryAccounts(variantBDynamic)
    expect(resolved).toEqual([
      { code: '1405', name: '库存商品' },
      { code: '1406', name: '发出商品' },
      { code: '1461', name: '存货跌价准备' },
    ])
    // 静态兜底在变体 B 下会把 1406 错标成「库存商品」——动态清单必须覆盖它
    expect(F2_INVENTORY_ACCOUNTS.find((a) => a.code === '1406')?.name).toBe('库存商品')
  })

  it('resolveF2InventoryAccounts falls back to static list when dynamic is empty/missing', () => {
    expect(resolveF2InventoryAccounts(null)).toEqual(
      F2_INVENTORY_ACCOUNTS.map((a) => ({ code: a.code, name: a.name })),
    )
    expect(resolveF2InventoryAccounts([])).toEqual(
      F2_INVENTORY_ACCOUNTS.map((a) => ({ code: a.code, name: a.name })),
    )
  })

  it('resolveF2AccountToRowKey uses dynamic row_key (variant-agnostic)', () => {
    const map = resolveF2AccountToRowKey(variantBDynamic)
    // 变体 B：1406 → goods-in-transit，与变体 A 假设（finished-goods）相反
    expect(map['1406']).toBe('goods-in-transit')
    expect(map['1405']).toBe('finished-goods')
  })

  it('resolveF2AccountToRowKey falls back to static map when dynamic missing', () => {
    expect(resolveF2AccountToRowKey(null)).toEqual(F2_ACCOUNT_TO_ROW_KEY)
  })

  it('resolveF2RowKeyToAccounts groups multiple codes under one rowKey (many-to-one)', () => {
    const dynamic: F2InventoryAccountItem[] = [
      { code: '1403', name: '周转材料', row_key: 'revolving-materials' },
      { code: '1451', name: '包装物', row_key: 'revolving-materials' },
      { code: '1452', name: '低值易耗品', row_key: 'revolving-materials' },
    ]
    const map = resolveF2RowKeyToAccounts(dynamic)
    expect(map['revolving-materials']).toEqual(['1403', '1451', '1452'])
  })

  it('resolveF2RowKeyToAccounts returns {} when dynamic missing (empty, not thrown)', () => {
    expect(resolveF2RowKeyToAccounts(null)).toEqual({})
    expect(resolveF2RowKeyToAccounts(undefined)).toEqual({})
  })
})
