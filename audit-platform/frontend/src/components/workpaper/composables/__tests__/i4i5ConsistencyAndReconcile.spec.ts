/**
 * I4/I5 目录校验 + 附注↔审定勾稽 + 审定/抽凭冒烟
 */
import { describe, it, expect } from 'vitest'
import { buildI4ConsistencyDashboard } from '../i4ConsistencyModel'
import { buildI5ConsistencyDashboard } from '../i5ConsistencyModel'
import {
  reconcileDisclosureVsAdjudication,
  reconcileI4DisclosureVsAdj,
  reconcileI5DisclosureVsAdj,
  reconcileI3DisclosureVsAdj,
} from '../wpDisclosureAdjReconcile'
import {
  emptyI4AdjudicationRow,
  seedI4AdjudicationFromDetail,
  validateI4AdjudicationSave,
} from '../i4AdjudicationModel'
import {
  emptyI5AdjudicationRow,
  seedI5AdjudicationFromDetail,
  validateI5AdjudicationSave,
} from '../i5AdjudicationModel'
import {
  emptyI4TargetedRow,
  summarizeI4Targeted,
  formatCoverageLabel,
} from '../i4TargetedCheckModel'
import {
  emptyI5TargetedRow,
  summarizeI5Targeted,
  formatCoverageLabel as formatI5CoverageLabel,
} from '../i5TargetedCheckModel'

describe('wpDisclosureAdjReconcile', () => {
  it('matched within tolerance; mismatch when both sides present', () => {
    expect(reconcileDisclosureVsAdjudication(100, 100.005).matched).toBe(true)
    const bad = reconcileDisclosureVsAdjudication(120, 100)
    expect(bad.hasBoth).toBe(true)
    expect(bad.matched).toBe(false)
    expect(bad.diff).toBe(20)
  })

  it('I4/I5/I3 map helpers detect disc vs adj gap', () => {
    const i4 = new Map<string, any>([
      ['I4-adj-rows', { remark: JSON.stringify([{ audited: 100 }]) }],
      ['I4-disc-listed-rows', { remark: JSON.stringify([{ endBalance: 90 }]) }],
    ])
    expect(reconcileI4DisclosureVsAdj(i4).matched).toBe(false)

    const i5 = new Map<string, any>([
      ['I5-adj-rows', { remark: JSON.stringify([{ audited: 50 }]) }],
      ['I5-disc-listed-rows', { remark: JSON.stringify([{ endBookValue: 50 }]) }],
    ])
    expect(reconcileI5DisclosureVsAdj(i5).matched).toBe(true)

    const i3 = new Map<string, any>([
      ['I3-adj-rows', { remark: JSON.stringify([{ audited: 200 }]) }],
      ['I3-disc-listed-rows', { remark: JSON.stringify([{ netValue: 180 }]) }],
    ])
    expect(reconcileI3DisclosureVsAdj(i3).matched).toBe(false)
  })
})

describe('i4ConsistencyModel', () => {
  it('明细空告警；附注≠审定 → error', () => {
    let dash = buildI4ConsistencyDashboard(new Map())
    expect(dash.issues.some((i) => i.id === 'i42-empty')).toBe(true)

    const map = new Map<string, any>([
      ['I4-2-rows', { remark: JSON.stringify([{ projectName: '装修', endBalance: 100 }]) }],
      ['I4-adj-rows', {
        remark: JSON.stringify([
          emptyI4AdjudicationRow({
            projectName: '装修',
            beginBalance: 100,
            endBalance: 100,
            unadjusted: 100,
            audited: 100,
          }),
        ]),
      }],
      ['I4-disc-listed-rows', { remark: JSON.stringify([{ endBalance: 80 }]) }],
    ])
    dash = buildI4ConsistencyDashboard(map)
    expect(dash.issues.some((i) => i.id === 'i4-disc-vs-adj')).toBe(true)
  })

  it('I4-5 覆盖率低且无说明 → error', () => {
    const map = new Map<string, any>([
      ['I4-2-rows', { remark: JSON.stringify([{ projectName: 'A' }]) }],
      ['I4-5-rows', { remark: JSON.stringify([{ debitAmount: 50 }]) }],
      ['I4-5-sample-meta', {
        remark: JSON.stringify({ populationAmount: 1000, coverageThreshold: 20 }),
      }],
      ['I4-5-audit-note', { remark: '' }],
    ])
    const dash = buildI4ConsistencyDashboard(map)
    expect(dash.issues.some((i) => i.id === 'i45-coverage')).toBe(true)
  })
})

describe('i5ConsistencyModel', () => {
  it('三角不平 → error；附注勾稽', () => {
    const map = new Map<string, any>([
      ['I5-2-rows', { remark: JSON.stringify([{ projectName: '预付', endBalance: 100 }]) }],
      ['I5-adj-rows', {
        remark: JSON.stringify([
          {
            projectName: '预付',
            beginBalance: 100,
            increase: 0,
            decrease: 0,
            endBalance: 90,
            triangleDiff: 10,
            hasError: true,
            unadjusted: 90,
            audited: 90,
          },
        ]),
      }],
      ['I5-disc-movement-rows', { remark: JSON.stringify([{ endBalance: 70 }]) }],
    ])
    const dash = buildI5ConsistencyDashboard(map)
    expect(dash.issues.some((i) => i.id === 'i51-triangle')).toBe(true)
    expect(dash.issues.some((i) => i.id === 'i5-disc-vs-adj')).toBe(true)
  })
})

describe('I4/I5 adjudication & targeted smoke', () => {
  it('seed + validate 冒烟（无 TB 阻断时可过）', () => {
    const i4Seed = seedI4AdjudicationFromDetail([
      { projectName: '装修', beginBalance: 100, increase: 20, amortization: 10, decrease: 0, endBalance: 110 },
    ])
    expect(i4Seed.length).toBeGreaterThan(0)
    const i4Gate = validateI4AdjudicationSave({ rows: i4Seed, tbDiff: 0 })
    expect(i4Gate.ok).toBe(true)

    const i5Seed = seedI5AdjudicationFromDetail([
      { projectName: '预付', beginBalance: 50, increase: 10, decrease: 5, endBalance: 55 },
    ])
    expect(i5Seed.length).toBeGreaterThan(0)
    const i5Gate = validateI5AdjudicationSave({ rows: i5Seed, tbDiff: 0 })
    expect(i5Gate.ok).toBe(true)
  })

  it('抽凭 summarize / coverage 标签冒烟', () => {
    const i4Rows = [emptyI4TargetedRow({ debitAmount: 100, isSpecific: true })]
    const i4Sum = summarizeI4Targeted(i4Rows, 500)
    expect(formatCoverageLabel(i4Sum.coverageRate)).not.toBe('')

    const i5Rows = [emptyI5TargetedRow({ debitAmount: 80, isSpecific: false })]
    const i5Sum = summarizeI5Targeted(i5Rows, 400)
    expect(formatI5CoverageLabel(i5Sum.coverageRate)).not.toBe('')
  })
})
