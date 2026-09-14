/**
 * useH8LeaseModification — H8-7 扩展能力单测
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useH8LeaseModification } from '../useH8LeaseModification'
import {
  validateModificationRow,
  buildH82ModificationPatch,
  buildSeparateLeaseH82Draft,
  mapH82ToSeeds,
} from '../h8LeaseModificationModel'

function setup(opts?: { modRows?: any[]; h82?: any[]; h86?: any }) {
  const map = new Map<string, any>()
  if (opts?.modRows) map.set('H8-7-rows', { remark: JSON.stringify(opts.modRows) })
  if (opts?.h82) map.set('H8-2-rows', { remark: JSON.stringify(opts.h82) })
  if (opts?.h86) map.set('H8-6-params', { remark: JSON.stringify(opts.h86) })
  const allResponses = ref(map)
  const saved: Array<{ id: string; value: any }> = []
  const api = useH8LeaseModification({
    wpId: ref('wp1'),
    projectId: ref('p1'),
    allResponses,
    onSave: (id, value) => {
      saved.push({ id, value })
      map.set(id, { remark: typeof value === 'string' ? value : JSON.stringify(value) })
    },
  })
  return { api, saved, allResponses, map }
}

describe('useH8LeaseModification 扩展', () => {
  it('单独租赁互斥并清零调整额', () => {
    const { api } = setup()
    api.addRow('ZL-001')
    const id = api.rows.value[0].rowId
    api.updateCell(id, 'scopeReduction', '是')
    api.updateCell(id, 'expandsScope', '是')
    api.updateCell(id, 'standalonePrice', '是')
    expect(api.rows.value[0].modificationType).toBe('单独租赁')
    expect(api.rows.value[0].scopeReduction).not.toBe('是')
    expect(api.rows.value[0].adjustmentAmount).toBe(0)
  })

  it('其他变更自动调整额 + 期初年金大于期末', () => {
    const { api } = setup()
    api.addRow('ZL-002')
    const id = api.rows.value[0].rowId
    api.updateCell(id, 'scopeReduction', '否')
    api.updateCell(id, 'carryingLiability', 350_000)
    api.updateCell(id, 'carryingROU', 340_000)
    api.updateCell(id, 'revisedDiscountRate', 0.05)
    api.updateCell(id, 'remainingAnnualPayment', 50_000)
    api.updateCell(id, 'remainingPeriods', 9)
    api.updateCell(id, 'paymentTiming', '期末')
    const endPv = api.rows.value[0].newLiabilityPV
    api.updateCell(id, 'paymentTiming', '期初')
    expect(api.rows.value[0].newLiabilityPV).toBeGreaterThan(endPv)
    expect(api.rows.value[0].adjustmentAmount).toBeCloseTo(
      api.rows.value[0].newLiabilityPV - 350_000,
      2,
    )
  })

  it('范围减少按比例计算终止损益与剩余 ROU', () => {
    const { api } = setup()
    api.addRow('ZL-003')
    const id = api.rows.value[0].rowId
    api.updateCell(id, 'scopeReduction', '是')
    api.updateCell(id, 'carryingLiability', 100_000)
    api.updateCell(id, 'carryingROU', 80_000)
    api.updateCell(id, 'reductionRatio', 0.25)
    const row = api.rows.value[0]
    expect(row.modificationType).toBe('范围减少')
    expect(row.scopeGainLoss).toBeCloseTo(5_000, 2)
    expect(row.remeasuredROUAmount).toBeCloseTo(60_000, 2)
    expect(row.adjustmentAmount).toBeCloseTo(-20_000, 2)
  })

  it('从 H8-2 带入净值，并用 H8-6 估算负债', () => {
    const { api } = setup({
      h82: [{
        contractNo: 'C-1',
        assetName: '设备A',
        startDate: '2021-01-01',
        endDate: '2030-12-31',
        netValue: 300_000,
        initialAmount: 420_000,
        h9InitialAmount: 355_000,
      }],
      h86: {
        leaseLiabilityInitial: 355_000,
        discountRate: 5,
        rentalPerPeriod: 50_000,
        leaseTermMonths: 120,
        paymentTiming: '期末',
      },
    })
    api.addRow('C-1')
    const id = api.rows.value[0].rowId
    api.updateCell(id, 'modificationDate', '2025-01-01')
    const pull = api.pullFromH82(id, 'C-1')
    expect(pull.ok).toBe(true)
    expect(api.rows.value[0].carryingROU).toBe(300_000)
    expect(api.rows.value[0].assetName).toBe('设备A')
    expect(api.rows.value[0].carryingLiability).toBeGreaterThan(0)
  })

  it('回写 H8-2 变更调整额', () => {
    const { api, saved } = setup({
      h82: [{ contractNo: 'C-2', modificationAmount: 0, remark: '' }],
    })
    api.addRow('C-2')
    const id = api.rows.value[0].rowId
    api.updateCell(id, 'scopeReduction', '否')
    api.updateCell(id, 'carryingLiability', 100)
    api.updateCell(id, 'newLiabilityPV', 150)
    const res = api.syncAdjustmentsToH82()
    expect(res.updated).toBe(1)
    const h82Save = saved.filter(s => s.id === 'H8-2-rows').pop()
    expect(h82Save?.value[0].modificationAmount).toBeCloseTo(50, 2)
  })

  it('单独租赁生成 H8-2 新合同行', () => {
    const { api, saved } = setup({ h82: [] })
    api.addRow('OLD')
    const id = api.rows.value[0].rowId
    api.updateCell(id, 'expandsScope', '是')
    api.updateCell(id, 'standalonePrice', '是')
    api.updateCell(id, 'newLiabilityPV', 88_000)
    const res = api.createSeparateLeaseOnH82(id)
    expect(res.ok).toBe(true)
    expect(res.contractNo).toBe('OLD-SEP')
    const h82Save = saved.filter(s => s.id === 'H8-2-rows').pop()
    expect(h82Save?.value.some((r: any) => r.contractNo === 'OLD-SEP')).toBe(true)
  })

  it('自定义付款流折现合计写入新负债 PV', () => {
    const { api } = setup()
    api.addRow('ZL-CF')
    const id = api.rows.value[0].rowId
    api.updateCell(id, 'scopeReduction', '否')
    api.updateCell(id, 'revisedDiscountRate', 0.06)
    api.updateCell(id, 'customPayments', [
      { amount: 50_000, periods: 0 },
      { amount: 50_000, periods: 1 },
      { amount: 55_000, periods: 2 },
    ])
    const sched = api.getPaymentSchedule(id)
    expect(sched.rows).toHaveLength(3)
    expect(api.rows.value[0].newLiabilityPV).toBeCloseTo(sched.totalPV, 2)
  })

  it('校验：其他变更缺账面给出 warning', () => {
    const issues = validateModificationRow({
      contractNo: 'X',
      modificationDate: '2024-01-01',
      modificationType: '其他变更',
      expandsScope: '否',
      standalonePrice: '否',
      scopeReduction: '否',
      carryingLiability: 0,
      carryingROU: 0,
      newLiabilityPV: 0,
      remainingPeriods: 0,
      reductionRatio: 0,
      rouAmortYears: 0,
    })
    expect(issues.some(i => i.code === 'no-carrying')).toBe(true)
  })

  it('model: H8-2 seed / patch / separate draft', () => {
    const seeds = mapH82ToSeeds([{ contractNo: 'A', netValue: 1, initialAmount: 2, h9InitialAmount: 3 }])
    expect(seeds[0].contractNo).toBe('A')
    const patches = buildH82ModificationPatch(
      [{ contractNo: 'A', adjustmentAmount: 10, modificationType: '其他变更', modificationDate: '2024-01-01' }],
      [{ contractNo: 'A' }],
    )
    expect(patches[0].modificationAmount).toBe(10)
    expect(buildSeparateLeaseH82Draft({
      modificationType: '单独租赁',
      contractNo: 'A',
      assetName: 'X',
      modificationDate: '2024-01-01',
      newLiabilityPV: 9,
      modificationDesc: '',
      newTerms: '',
    })?.contractNo).toBe('A-SEP')
  })
})
