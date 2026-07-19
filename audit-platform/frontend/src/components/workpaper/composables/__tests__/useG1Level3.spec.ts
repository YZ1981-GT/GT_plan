import { describe, it, expect } from 'vitest'
import {
  calcG1Level3Closing,
  migrateLegacyLevel3Row,
  summarizeLevel3ForDisclosure,
  summarizeLevel3ByDisclosureLeaf,
  checkUnrealizedHeld,
  mapInvestTypeToAssetClass,
  mapDetailRowToLevel3Patch,
  G1_LEVEL3_COLUMNS,
} from '../useG1Level3'

describe('useG1Level3 / CAS39 调节公式', () => {
  it('期末 = 期初 + 转入 − 转出 + 公允变动 + 投资收益 + 购买 + 发行 − 出售 − 结算', () => {
    expect(
      calcG1Level3Closing({
        openingBalance: 100,
        transferIn: 10,
        transferOut: 5,
        gainPl: 3,
        investmentIncome: 2,
        purchase: 20,
        issue: 0,
        sale: 8,
        settlement: 2,
      }),
    ).toBe(120)
  })

  it('列定义含品种与纸质底稿关键列', () => {
    const props = G1_LEVEL3_COLUMNS.map((c) => c.prop)
    expect(props).toContain('assetClass')
    expect(props).toContain('transferIn')
    expect(props).toContain('investmentIncome')
    expect(props).toContain('issue')
    expect(props).toContain('settlement')
    expect(props).toContain('unrealizedHeld')
  })
})

describe('migrateLegacyLevel3Row', () => {
  it('旧版增加/减少字段迁移到纸质底稿列', () => {
    const row = migrateLegacyLevel3Row(
      {
        id: 'legacy-1',
        itemName: '未上市股权',
        openingBalance: 1000,
        addNewRecognition: 200,
        addTransferIn: 50,
        reduceDerecognition: 80,
        reduceTransferOut: 30,
        fairValueChange: 40,
        valuationMethod: '收益法',
        keyAssumption: '折现率10%',
      },
      1,
    )
    expect(row.itemName).toBe('未上市股权')
    expect(row.assetClass).toBe('equity')
    expect(row.purchase).toBe(200)
    expect(row.transferIn).toBe(50)
    expect(row.sale).toBe(80)
    expect(row.transferOut).toBe(30)
    expect(row.gainPl).toBe(40)
    expect(row.closingBalance).toBe(1000 + 50 - 30 + 40 + 200 - 80)
    expect(row.remark).toContain('估值方法')
  })

  it('新版字段保留品种并重算期末与差异', () => {
    const row = migrateLegacyLevel3Row(
      {
        id: 'n1',
        itemName: '私募债',
        assetClass: 'debt',
        openingBalance: 500,
        transferIn: 0,
        transferOut: 0,
        gainPl: 10,
        investmentIncome: 5,
        purchase: 100,
        issue: 0,
        sale: 0,
        settlement: 0,
        unrealizedHeld: 8,
        reportedClosing: 610,
      },
      1,
    )
    expect(row.assetClass).toBe('debt')
    expect(row.closingBalance).toBe(615)
    expect(row.variance).toBe(5)
  })
})

describe('summarizeLevel3ByDisclosureLeaf', () => {
  it('按债务/权益/衍生拆分；other 归入权益', () => {
    const debt = migrateLegacyLevel3Row(
      { itemName: '债', assetClass: 'debt', openingBalance: 100, purchase: 10, gainPl: 1 },
      1,
    )
    const equity = migrateLegacyLevel3Row(
      { itemName: '股', assetClass: 'equity', openingBalance: 200, purchase: 20, gainPl: 2 },
      2,
    )
    const deriv = migrateLegacyLevel3Row(
      { itemName: '衍生', assetClass: 'derivative', openingBalance: 50, purchase: 5, gainPl: 3 },
      3,
    )
    const other = migrateLegacyLevel3Row(
      { itemName: '理财', assetClass: 'other', openingBalance: 30, purchase: 0, gainPl: 0 },
      4,
    )
    const byLeaf = summarizeLevel3ByDisclosureLeaf([debt, equity, deriv, other])
    expect(byLeaf['l3-trading-debt'].opening).toBe(100)
    expect(byLeaf['l3-trading-equity'].opening).toBe(230) // 200+30
    expect(byLeaf['l3-derivative'].opening).toBe(50)
    expect(byLeaf['l3-trading-debt'].purchase).toBe(10)
    expect(byLeaf['l3-trading-equity'].purchase).toBe(20)
  })

  it('计入损益 = 公允变动 + 投资收益；OCI 为 0', () => {
    const a = migrateLegacyLevel3Row(
      {
        openingBalance: 100,
        transferIn: 10,
        gainPl: 3,
        investmentIncome: 2,
        purchase: 20,
        sale: 5,
        unrealizedHeld: 1,
      },
      1,
    )
    const s = summarizeLevel3ForDisclosure([a])
    expect(s.gainPl).toBe(5)
    expect(s.gainOci).toBe(0)
  })
})

describe('mapInvestTypeToAssetClass / mapDetailRowToLevel3Patch', () => {
  it('investType 映射品种', () => {
    expect(mapInvestTypeToAssetClass('bond')).toBe('debt')
    expect(mapInvestTypeToAssetClass('stock')).toBe('equity')
    expect(mapInvestTypeToAssetClass('fund')).toBe('equity')
    expect(mapInvestTypeToAssetClass('derivative')).toBe('derivative')
    expect(mapInvestTypeToAssetClass('other')).toBe('other')
  })

  it('G1-2 Level3 行映射变动因子', () => {
    const patch = mapDetailRowToLevel3Patch({
      securityName: '未上市股',
      investType: 'stock',
      auditedOpeningFvTotal: 1000,
      addedCost: 200,
      reducedCost: 50,
      periodFvChange: 30,
      fvChangeInPL: 30,
      totalIncome: 12,
      auditedClosingFvTotal: 1180,
      closingQuantity: 1,
    })
    expect(patch.itemName).toBe('未上市股')
    expect(patch.assetClass).toBe('equity')
    expect(patch.openingBalance).toBe(1000)
    expect(patch.purchase).toBe(200)
    expect(patch.sale).toBe(50)
    expect(patch.gainPl).toBe(30)
    expect(patch.investmentIncome).toBe(12)
    expect(patch.reportedClosing).toBe(1180)
    expect(patch.unrealizedHeld).toBe(30)
  })
})

describe('checkUnrealizedHeld', () => {
  it('期末为0仍填未实现 → 警告', () => {
    const zeroClose = migrateLegacyLevel3Row(
      {
        openingBalance: 100,
        sale: 100,
        gainPl: 0,
        unrealizedHeld: 5,
        reportedClosing: 0,
      },
      1,
    )
    expect(zeroClose.closingBalance).toBe(0)
    expect(checkUnrealizedHeld(zeroClose)).toContain('期末余额为0')
  })

  it('|未实现| > |公允变动| → 警告', () => {
    const row = migrateLegacyLevel3Row(
      { openingBalance: 100, gainPl: 5, unrealizedHeld: 20, reportedClosing: 105 },
      1,
    )
    expect(checkUnrealizedHeld(row)).toContain('大于本期公允变动')
  })

  it('有期末及公允变动但未填未实现 → 提示', () => {
    const row = migrateLegacyLevel3Row(
      { openingBalance: 100, gainPl: 10, unrealizedHeld: 0, reportedClosing: 110 },
      1,
    )
    expect(checkUnrealizedHeld(row)).toContain('未填仍持有未实现')
  })

  it('合理填写 → null', () => {
    const row = migrateLegacyLevel3Row(
      { openingBalance: 100, gainPl: 10, unrealizedHeld: 8, reportedClosing: 110 },
      1,
    )
    expect(checkUnrealizedHeld(row)).toBeNull()
  })
})
