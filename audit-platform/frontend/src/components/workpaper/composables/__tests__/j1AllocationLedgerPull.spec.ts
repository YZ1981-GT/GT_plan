/**
 * j1AllocationLedgerPull — J1-7 从序时账按对方科目聚合薪酬分配 单测
 *
 * 口径：2211 贷方 = 本期计提；对方科目（借方）= 受益对象费用/成本科目。
 * 对方科目为空的分录不臆造分配，计入 unattributedAmount。
 */
import { describe, it, expect } from 'vitest'
import {
  tailSegment,
  bucketForCounterpart,
  aggregateJ1Allocation,
} from '../j1AllocationLedgerPull'

describe('tailSegment — 明细科目名末段', () => {
  it('取分隔符后的末段并去空白', () => {
    expect(tailSegment('应付职工薪酬_工资')).toBe('工资')
    expect(tailSegment('应付职工薪酬/社会保险费')).toBe('社会保险费')
    expect(tailSegment(' 住房公积金 ')).toBe('住房公积金')
    expect(tailSegment(null)).toBe('')
  })
})

describe('bucketForCounterpart — 对方科目→分配列', () => {
  it('按科目编码前缀判定（含小企业 4001/4101）', () => {
    expect(bucketForCounterpart('500101')).toBe('productionCost')
    expect(bucketForCounterpart('4001')).toBe('productionCost')
    expect(bucketForCounterpart('510102')).toBe('manufacturing')
    expect(bucketForCounterpart('4101')).toBe('manufacturing')
    expect(bucketForCounterpart('660201')).toBe('adminExpense')
    expect(bucketForCounterpart('6601')).toBe('sellingExpense')
    expect(bucketForCounterpart('160401')).toBe('otherExpense')
  })

  it('编码缺失时按名称关键词判定', () => {
    expect(bucketForCounterpart('', '管理费用-职工薪酬')).toBe('adminExpense')
    expect(bucketForCounterpart('', '销售费用')).toBe('sellingExpense')
    expect(bucketForCounterpart('', '营业费用')).toBe('sellingExpense')
    expect(bucketForCounterpart('', '生产成本')).toBe('productionCost')
    expect(bucketForCounterpart('', '制造费用')).toBe('manufacturing')
    expect(bucketForCounterpart('', '研发支出')).toBe('otherExpense')
  })
})

describe('aggregateJ1Allocation — 薪酬项目 × 分配列', () => {
  const items = [
    // 工资：管理费用 600 + 生产成本 400（贷方计提）
    { account_code: '221101', account_name: '应付职工薪酬_工资', credit_amount: 600, counterpart_account: '660201' },
    { account_code: '221101', account_name: '应付职工薪酬_工资', credit_amount: 400, counterpart_account: '500101' },
    // 工资：支付（借方）不计入
    { account_code: '221101', account_name: '应付职工薪酬_工资', debit_amount: 900, counterpart_account: '100201' },
    // 社保：对方科目缺失 → 无法归属
    { account_code: '221102', account_name: '应付职工薪酬_社会保险费', credit_amount: 150, counterpart_account: '' },
    // 非 2211 科目不计入
    { account_code: '660201', account_name: '管理费用_工资', credit_amount: 999, counterpart_account: '221101' },
  ]

  it('只取贷方、只取目标科目，按项目×对方科目归集', () => {
    const { rows, total } = aggregateJ1Allocation(items as any)
    expect(rows).toHaveLength(2)
    const wage = rows.find(r => r.label === '工资')!
    expect(wage.adminExpense).toBe(600)
    expect(wage.productionCost).toBe(400)
    expect(wage.actualAccrual).toBe(1000)
    expect(total).toBe(1150)
  })

  it('对方科目为空的金额计入 unattributedAmount，不臆造分配', () => {
    const { rows, unattributedAmount } = aggregateJ1Allocation(items as any)
    const social = rows.find(r => r.label === '社会保险费')!
    expect(unattributedAmount).toBe(150)
    expect(social.actualAccrual).toBe(150)
    expect(
      social.adminExpense + social.sellingExpense + social.productionCost +
      social.manufacturing + social.otherExpense,
    ).toBe(0)
  })

  it('全零/空输入返回空行不报错', () => {
    expect(aggregateJ1Allocation([]).rows).toEqual([])
    expect(aggregateJ1Allocation([{ account_code: '2211', credit_amount: 0 }] as any).rows).toEqual([])
  })
})
