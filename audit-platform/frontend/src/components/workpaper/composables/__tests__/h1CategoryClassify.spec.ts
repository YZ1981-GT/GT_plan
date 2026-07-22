/**
 * h1CategoryClassify — TB 分类映射 / H1-3 分摊 单测
 */
import { describe, it, expect } from 'vitest'
import {
  classifyFaBlock,
  classifyFaCategory,
  classifyTbFaRow,
  aggregateTbRowsToCategoryPrefill,
  allocateH3AdjustmentsByAccount,
} from '../h1CategoryClassify'

describe('classifyFaBlock', () => {
  it('识别 1601/1602/1603 及子码', () => {
    expect(classifyFaBlock('1601')).toBe('cost')
    expect(classifyFaBlock('1601.01')).toBe('cost')
    expect(classifyFaBlock('160101')).toBe('cost')
    expect(classifyFaBlock('1602.02')).toBe('dep')
    expect(classifyFaBlock('1603')).toBe('impair')
    expect(classifyFaBlock('1002')).toBeNull()
  })
})

describe('classifyFaCategory / classifyTbFaRow', () => {
  it('按名称关键词分类', () => {
    expect(classifyFaCategory('房屋及建筑物')).toBe('房屋及建筑物')
    expect(classifyFaCategory('运输设备-货车')).toBe('运输设备')
    expect(classifyFaCategory('办公电子设备')).toBe('办公设备')
    expect(classifyFaCategory('机器设备')).toBe('机器设备')
  })

  it('名称缺失时按二级码启发式', () => {
    expect(classifyTbFaRow('1601.01', '')).toBe('房屋及建筑物')
    expect(classifyTbFaRow('1601.03', '')).toBe('运输设备')
    expect(classifyTbFaRow('1601.05', '')).toBe('其他设备')
  })
})

describe('aggregateTbRowsToCategoryPrefill', () => {
  it('按分类聚合原值/折旧/减值未审数', () => {
    const payload = aggregateTbRowsToCategoryPrefill([
      {
        account_code: '1601.01',
        account_name: '房屋及建筑物',
        opening_balance: 100,
        closing_balance: 120,
        debit_amount: 30,
        credit_amount: 10,
      },
      {
        account_code: '1602.01',
        account_name: '房屋及建筑物累计折旧',
        opening_balance: -20,
        closing_balance: -25,
        debit_amount: 0,
        credit_amount: 5,
      },
      {
        account_code: '1603.02',
        account_name: '机器设备减值准备',
        opening_balance: 0,
        closing_balance: 8,
        debit_amount: 0,
        credit_amount: 8,
      },
    ])
    const building = payload.categories.find((c) => c.category === '房屋及建筑物')!
    expect(building.cost.unadjusted).toBe(120)
    expect(building.cost.begin).toBe(100)
    expect(building.dep.unadjusted).toBe(25)
    const machine = payload.categories.find((c) => c.category === '机器设备')!
    expect(machine.impair.unadjusted).toBe(8)
    expect(payload.totals.cost1601).toBe(120)
  })
})

describe('allocateH3AdjustmentsByAccount', () => {
  it('按科目码分摊到分类，1601用借-贷，备抵用贷-借', () => {
    const alloc = allocateH3AdjustmentsByAccount([
      {
        accountCode: '1601.01',
        accountName: '房屋及建筑物',
        category: '账项调整',
        debitAmount: 1000,
        creditAmount: 0,
      },
      {
        accountCode: '1602',
        accountName: '累计折旧-机器设备',
        category: '账项调整',
        debitAmount: 0,
        creditAmount: 200,
      },
      {
        accountCode: '1603.03',
        accountName: '运输设备减值',
        category: '报表调整',
        debitAmount: 0,
        creditAmount: 50,
      },
      {
        accountCode: '1002',
        accountName: '银行存款',
        category: '账项调整',
        debitAmount: 0,
        creditAmount: 1000,
      },
    ])
    expect(alloc.cost['房屋及建筑物'].aje).toBe(1000)
    expect(alloc.dep['机器设备'].aje).toBe(200)
    expect(alloc.impair['运输设备'].rje).toBe(50)
    expect(alloc.applied).toBe(3)
    expect(alloc.skipped).toBe(1)
  })
})
