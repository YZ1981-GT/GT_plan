/**
 * H1-12 含减值分支：行上的「减值后月折旧」取引擎结果 postImpairmentMonthly。
 * 原先读不存在的 postImpairmentMonthlyDep ⇒ 该列恒为 undefined（界面空白）。
 */
import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import { useH1Depreciation } from '../useH1Depreciation'

describe('useH1Depreciation — 减值后月折旧', () => {
  it('B 分支重算后 postImpairmentMonthlyDep 为正且小于减值前月折旧', () => {
    const row = {
      rowId: 'r1', assetName: '设备', originalCost: 120000, salvageRate: 0, usefulLife: 10,
      startDate: '2020-01-01', impairmentAmount: 30000, impairmentDate: '2025-06-30',
    }
    const allResponses = ref(new Map<string, any>([
      ['H1-12-branch', { item_id: 'H1-12-branch', remark: 'B' }],
      ['H1-12-B-rows', { item_id: 'H1-12-B-rows', remark: JSON.stringify([row]) }],
    ]))
    const dep = useH1Depreciation(ref('wp'), ref('p'), allResponses, { periodEnd: ref('2025-12-31') })
    expect(dep.branch.value).toBe('B')
    const r = dep.rows.value[0]
    dep.recalcRow(r)
    expect(r.postImpairmentMonthlyDep).toBeGreaterThan(0)
    expect(r.postImpairmentMonthlyDep).toBeLessThan(120000 / 120)
  })
})
