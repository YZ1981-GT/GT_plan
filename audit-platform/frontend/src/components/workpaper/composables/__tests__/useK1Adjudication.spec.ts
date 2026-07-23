import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useK1Adjudication } from '../useK1Adjudication'
import { readK14AdjustmentNets } from '../useK1Adjustment'

function seedK11(map: Map<string, any>) {
  map.set('K1-1-receivable-count', { remark: '2' })
  map.set('K1-1-baddebt-count', { remark: '2' })
  for (let i = 0; i < 2; i++) {
    map.set(`K1-1-receivable-r${i}-unadj`, { remark: String((i + 1) * 1000) })
    map.set(`K1-1-baddebt-r${i}-unadj`, { remark: String((i + 1) * 200) })
    map.set(`K1-1-receivable-r${i}-aje`, { remark: '0' })
    map.set(`K1-1-receivable-r${i}-rje`, { remark: '0' })
    map.set(`K1-1-baddebt-r${i}-aje`, { remark: '0' })
    map.set(`K1-1-baddebt-r${i}-rje`, { remark: '0' })
  }
}

describe('readK14AdjustmentNets', () => {
  it('sums 1221/1231 nets from K1-4 rows', () => {
    const map = new Map<string, any>()
    map.set('K1-4-adj-entries', {
      remark: JSON.stringify([
        { category: '账项调整', accountCode: '1221', debitAmount: 3000, creditAmount: 0 },
        { category: '账项调整', accountCode: '1231', debitAmount: 0, creditAmount: 500 },
        { category: '报表调整', accountCode: '1221', debitAmount: 100, creditAmount: 0 },
      ]),
    })
    const nets = readK14AdjustmentNets(map)
    expect(nets.rowCount).toBe(3)
    expect(nets.receivableAjeNet).toBe(3000)
    expect(nets.receivableRjeNet).toBe(100)
    expect(nets.badDebtAjeNet).toBe(-500)
  })
})

describe('useK1Adjudication.syncEndAdjFromK14', () => {
  it('allocates 1221/1231 nets to rows by unadjusted weight', () => {
    const map = ref(new Map<string, any>())
    seedK11(map.value)
    map.value.set('K1-4-adj-entries', {
      remark: JSON.stringify([
        { category: '账项调整', accountCode: '1221', debitAmount: 3000, creditAmount: 0 },
        { category: '账项调整', accountCode: '1231', debitAmount: 0, creditAmount: 300 },
      ]),
    })

    const saved: string[] = []
    const { syncEndAdjFromK14 } = useK1Adjudication({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: map,
      onSave: (id) => saved.push(id),
    })

    const res = syncEndAdjFromK14()
    expect(res.applied).toBe(true)

    const r0Aje = Number(map.value.get('K1-1-receivable-r0-aje')?.remark)
    const r1Aje = Number(map.value.get('K1-1-receivable-r1-aje')?.remark)
    expect(r0Aje + r1Aje).toBeCloseTo(3000, 2)
    expect(r0Aje).toBeCloseTo(1000, 2)
    expect(r1Aje).toBeCloseTo(2000, 2)

    const bd0Aje = Number(map.value.get('K1-1-baddebt-r0-aje')?.remark)
    const bd1Aje = Number(map.value.get('K1-1-baddebt-r1-aje')?.remark)
    expect(bd0Aje + bd1Aje).toBeCloseTo(-300, 2)
  })
})

describe('useK1Adjudication variance & fs', () => {
  it('detects variance alerts and generates reason drafts', () => {
    const map = ref(new Map<string, any>())
    seedK11(map.value)
    map.value.set('K1-1-receivable-r0-prior-unadj', { remark: '100' })
    map.value.set('K1-1-receivable-r0-unadj', { remark: '1000' })

    const { varianceAlerts, generateVarianceReasonDrafts } = useK1Adjudication({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: map,
    })

    expect(varianceAlerts.value.length).toBeGreaterThan(0)
    const res = generateVarianceReasonDrafts()
    expect(res.filled).toBeGreaterThan(0)
    expect(map.value.get('K1-1-receivable-r0-remark')?.remark).toContain('须说明原因')
  })

  it('computes fs reconciliation diff', () => {
    const map = ref(new Map<string, any>())
    seedK11(map.value)
    map.value.set('K1-1-fs-other-total', { remark: '5000' })

    const { fsReconciliation } = useK1Adjudication({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: map,
    })

    expect(fsReconciliation.value.k11NetAudited).toBeGreaterThan(0)
    expect(fsReconciliation.value.fsDiff).toBe(fsReconciliation.value.k11NetAudited - 5000)
  })
})

describe('useK1Adjudication.applyAdjudicationPrefill', () => {
  it('writes portfolio aging begin/unadj from tb_balance prefill', () => {
    const map = ref(new Map<string, any>())
    const { applyAdjudicationPrefill, hasPersistedUnadj } = useK1Adjudication({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: map,
    })

    expect(hasPersistedUnadj()).toBe(false)
    const ok = applyAdjudicationPrefill({
      receivable_total: { opening: 100, closing: 500, debit: 400, credit: 0 },
      bad_debt_total: { opening: 10, closing: 50 },
      portfolio: { aging: { opening: 100, closing: 500 } },
      portfolio_provision: { aging: { opening: 10, closing: 50 } },
      nature: { margin: { opening: 20, closing: 80 } },
    })
    expect(ok).toBe(true)
    expect(Number(map.value.get('K1-1-receivable-r1-unadj')?.remark)).toBe(500)
    expect(Number(map.value.get('K1-1-receivable-r1-begin')?.remark)).toBe(100)
    expect(Number(map.value.get('K1-1-baddebt-r1-unadj')?.remark)).toBe(50)
    expect(Number(map.value.get('K1-1-nature-gross-n0-unadj')?.remark)).toBe(80)
  })

  it('skips when unadj already persisted', () => {
    const map = ref(new Map<string, any>())
    map.value.set('K1-1-receivable-r0-unadj', { remark: '999' })
    const { applyAdjudicationPrefill } = useK1Adjudication({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: map,
    })
    const ok = applyAdjudicationPrefill({
      portfolio: { aging: { opening: 1, closing: 2 } },
    })
    expect(ok).toBe(false)
    expect(map.value.get('K1-1-receivable-r1-unadj')).toBeUndefined()
  })
})
