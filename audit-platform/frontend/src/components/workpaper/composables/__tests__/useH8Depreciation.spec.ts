/**
 * useH8Depreciation / recalcH8DepRow 单元测试
 * 覆盖：不含减值直线法、含减值分段、CAS21折旧期、旧数据迁移、H8-2/H8-10 联动字段
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  migrateH8DepRaw,
  recalcH8DepRow,
  resolveH8DepPeriodMonths,
  useH8Depreciation,
  type H8DepreciationRowInput,
} from '../useH8Depreciation'

function baseInput(over: Partial<H8DepreciationRowInput> = {}): H8DepreciationRowInput {
  return {
    rowId: 'r1',
    contractNo: 'L-01',
    assetCategory: '房屋及建筑物',
    assetName: '办公楼租赁',
    originalCost: 120_000,
    bookAccDepEnd: 24_000,
    impairment: 0,
    startDate: '2023-01-01',
    usefulLife: 5,
    leaseTermMonths: 60,
    salvageRate: 0,
    bookMonthly: 2_000,
    bookDepreciation: 24_000,
    ...over,
  }
}

describe('resolveH8DepPeriodMonths', () => {
  it('取租赁期与使用寿命孰短', () => {
    expect(resolveH8DepPeriodMonths(baseInput({ usefulLife: 10, leaseTermMonths: 36 }))).toBe(36)
    expect(resolveH8DepPeriodMonths(baseInput({ usefulLife: 2, leaseTermMonths: 60 }))).toBe(24)
  })
})

describe('migrateH8DepRaw', () => {
  it('兼容旧字段 rouAmount / accumulatedDep / impairmentAmount / usefulLifeMonths', () => {
    const m = migrateH8DepRaw({
      rouAmount: 100,
      accumulatedDep: 20,
      impairmentAmount: 5,
      usefulLifeMonths: 36,
      leaseTermMonths: 48,
    })
    expect(m.originalCost).toBe(100)
    expect(m.bookAccDepEnd).toBe(20)
    expect(m.impairment).toBe(5)
    expect(m.usefulLife).toBe(3)
    expect(m.leaseTermMonths).toBe(48)
  })
})

describe('recalcH8DepRow — 不含减值', () => {
  it('直线法：月折旧=原值/月限，本期=月折旧×本期月数', () => {
    const r = recalcH8DepRow(
      baseInput(),
      '不含减值',
      '2025-01-01',
      '2025-12-31',
    )
    // 120000/60 = 2000
    expect(r.calcMonthly).toBe(2000)
    expect(r.periodMonths).toBeGreaterThan(0)
    expect(r.periodDep).toBe(roundish(r.calcMonthly * r.periodMonths))
    expect(r.monthlyDiff).toBe(0)
    expect(r.impairmentAmount).toBe(0)
    expect(r.currentPeriodDep).toBe(r.periodDep)
    expect(r.rouAmount).toBe(120_000)
  })

  it('残值率降低月折旧', () => {
    const r0 = recalcH8DepRow(baseInput({ salvageRate: 0 }), '不含减值', '2025-01-01', '2025-12-31')
    const r5 = recalcH8DepRow(baseInput({ salvageRate: 0.05 }), '不含减值', '2025-01-01', '2025-12-31')
    expect(r5.calcMonthly).toBeLessThan(r0.calcMonthly)
  })
})

describe('recalcH8DepRow — 含减值', () => {
  it('本期=减值前月数×原月折旧+减值后月数×新月折旧', () => {
    const r = recalcH8DepRow(
      baseInput({
        impairment: 30_000,
        impairmentDate: '2025-06-30',
        bookMonthly: 1_500,
      }),
      '含减值',
      '2025-01-01',
      '2025-12-31',
    )
    expect(r.preImpairmentMonthly).toBe(2000)
    expect(r.postImpairmentMonthly).toBeGreaterThan(0)
    expect(r.postImpairmentMonthly!).toBeLessThan(r.preImpairmentMonthly!)
    expect(r.monthsBeforeImpairment! + r.monthsAfterImpairment!).toBe(r.periodMonths)
    const expected = roundish(
      (r.preImpairmentMonthly || 0) * (r.monthsBeforeImpairment || 0)
      + (r.postImpairmentMonthly || 0) * (r.monthsAfterImpairment || 0),
    )
    expect(r.periodDep).toBeCloseTo(expected, 1)
    expect(r.impairmentAmount).toBe(30_000)
  })

  it('无减值金额时退化为不含减值', () => {
    const a = recalcH8DepRow(baseInput({ impairment: 0 }), '含减值', '2025-01-01', '2025-12-31')
    const b = recalcH8DepRow(baseInput(), '不含减值', '2025-01-01', '2025-12-31')
    expect(a.periodDep).toBe(b.periodDep)
    expect(a.calcMonthly).toBe(b.calcMonthly)
  })
})

describe('useH8Depreciation', () => {
  it('persist 写出 impairmentAmount 与 depreciation-total', () => {
    const saved: Record<string, any> = {}
    const map = new Map<string, any>()
    const api = useH8Depreciation({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: ref(map),
      onSave: (id, v) => { saved[id] = v },
      externalBranch: ref('含减值'),
    })
    api.addDepRow('L-01')
    api.updateDepCell(api.depRows.value[0].rowId, 'originalCost', 60_000)
    api.updateDepCell(api.depRows.value[0].rowId, 'usefulLife', 5)
    api.updateDepCell(api.depRows.value[0].rowId, 'leaseTermMonths', 60)
    api.updateDepCell(api.depRows.value[0].rowId, 'startDate', '2024-01-01')
    api.updateDepCell(api.depRows.value[0].rowId, 'impairment', 10_000)
    api.updateDepCell(api.depRows.value[0].rowId, 'impairmentDate', '2025-03-31')

    expect(saved['H8-8-branch']).toBe('含减值')
    expect(Array.isArray(saved['H8-8-dep-rows'])).toBe(true)
    expect(saved['H8-8-dep-rows'][0].impairmentAmount).toBe(10_000)
    expect(typeof saved['H8-8-depreciation-total']).toBe('number')
    expect(api.depreciationByCategory.value['其他设备'] ?? api.depreciationByCategory.value['房屋及建筑物']).toBeDefined()
  })

  it('从 H8-2 带入入账值与起止日', () => {
    const map = new Map<string, any>([
      ['H8-2-rows', {
        item_id: 'H8-2-rows',
        conclusion: null,
        remark: JSON.stringify([{
          rowId: 'd1',
          contractNo: 'C-9',
          assetName: '仓库',
          initialAmount: 240_000,
          accDepEnd: 40_000,
          depCurrentPeriod: 20_000,
          startDate: '2022-06-01',
          endDate: '2027-05-31',
        }]),
      }],
    ])
    const saved: Record<string, any> = {}
    const api = useH8Depreciation({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: ref(map),
      onSave: (id, v) => { saved[id] = v },
      externalBranch: ref('不含减值'),
    })
    const r = api.importFromH82(true)
    expect(r.imported).toBe(1)
    expect(api.depRows.value[0].originalCost).toBe(240_000)
    expect(api.depRows.value[0].contractNo).toBe('C-9')
    expect(api.depRows.value[0].startDate).toBe('2022-06-01')
  })

  it('从 H8-5 同步租赁期并重算；importFromH82 优先取 H8-5', () => {
    const map = new Map<string, any>([
      ['H8-5-records', {
        remark: JSON.stringify([{
          recordId: 't1',
          contractNo: 'C-9',
          determinedLeaseTermMonths: 48,
          commencementDate: '2022-01-01',
          conclusion: '是',
        }]),
      }],
      ['H8-8-dep-rows', {
        remark: JSON.stringify([{
          rowId: 'd1',
          contractNo: 'C-9',
          assetName: '仓库',
          originalCost: 120_000,
          leaseTermMonths: 24,
          usefulLife: 5,
          salvageRate: 0,
          startDate: '2022-01-01',
          bookAccDepEnd: 0,
          bookDepreciation: 0,
        }]),
      }],
      ['H8-2-rows', {
        remark: JSON.stringify([{
          rowId: 'h2',
          contractNo: 'C-9',
          assetName: '仓库',
          initialAmount: 100_000,
          startDate: '2022-01-01',
          endDate: '2024-01-01',
        }]),
      }],
    ])
    const api = useH8Depreciation({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: ref(map),
      onSave: () => {},
      externalBranch: ref('不含减值'),
    })
    expect(api.h85LeaseTermMismatches.value.length).toBe(1)
    const sync = api.syncLeaseTermFromH85()
    expect(sync.ok).toBe(true)
    expect(sync.updated).toBe(1)
    expect(api.depRows.value[0].leaseTermMonths).toBe(48)
    expect(api.h85LeaseTermMismatches.value.length).toBe(0)

    const imp = api.importFromH82(true)
    expect(imp.imported).toBe(1)
    expect(api.depRows.value[0].leaseTermMonths).toBe(48)
    expect(imp.message).toContain('H8-5')
  })
})

function roundish(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100
}
