/**
 * I4 联动闭环：I4-2→I4-1 带入；I4-3→AJE；I4-6→摊销；I4-5→I4-3 推送；附注勾稽
 */
import { describe, it, expect } from 'vitest'
import {
  seedI4AdjudicationFromDetail,
  applyAjeFromI43,
  applyAmortFromI46,
  emptyI4AdjudicationRow,
} from '../i4AdjudicationModel'
import {
  emptyI4TargetedRow,
  buildI4TargetedAdjDrafts,
  buildI43LinesFromTargetedDrafts,
  mergeI43LinesSkippingExisting,
  summarizeI4Targeted,
} from '../i4TargetedCheckModel'
import { buildI4ConsistencyDashboard } from '../i4ConsistencyModel'
import { reconcileI4DisclosureVsAdj } from '../wpDisclosureAdjReconcile'
import { ref } from 'vue'
import { useI4CrossSheet } from '../useI4CrossSheet'

describe('i4LinkageClosure', () => {
  it('I4-2 → seed 审定行，三角勾稽可平', () => {
    const detail = [
      {
        projectName: '装修A',
        beginBalance: 100,
        currentIncrease: 50,
        currentAmortization: 20,
        currentDecrease: 0,
        endBalance: 130,
        originalAmount: 150,
      },
    ]
    const rows = seedI4AdjudicationFromDetail(detail)
    expect(rows.length).toBeGreaterThanOrEqual(1)
    expect(rows[0].projectName).toBe('装修A')
    expect(Number(rows[0].beginBalance ?? rows[0].unadjOpening)).toBeGreaterThan(0)
  })

  it('I4-3 AJE 净额写入审定行', () => {
    const base = [
      emptyI4AdjudicationRow({
        projectName: '装修A',
        beginBalance: 100,
        increase: 0,
        amortization: 0,
        decrease: 0,
        endBalance: 100,
        unadjusted: 100,
        audited: 100,
      }),
    ]
    const adj = [
      {
        description: '补提摊销',
        accountCode: '1801',
        projectName: '装修A',
        debitAmount: 0,
        creditAmount: 10,
        entryType: 'AJE',
      },
    ]
    const result = applyAjeFromI43(base, adj as any)
    expect(result.applied).toBeGreaterThan(0)
    expect(Math.abs(result.totalAje)).toBeGreaterThan(0)
    const row = result.rows.find((r) => r.projectName === '装修A') || result.rows[0]
    expect(row).toBeTruthy()
    expect(Math.abs(_num(row.aje))).toBeGreaterThan(0)
  })

  it('I4-6 测算摊销同步到审定', () => {
    const base = [
      emptyI4AdjudicationRow({
        projectName: '装修A',
        beginBalance: 120,
        increase: 0,
        amortization: 0,
        decrease: 0,
        endBalance: 120,
        unadjusted: 120,
        audited: 120,
      }),
    ]
    const amort = [{ name: '装修A', projectName: '装修A', yearTotal: 24 }]
    const next = applyAmortFromI46(base, amort as any)
    const row = next.find((r) => (r.projectName || '').includes('装修')) || next[0]
    expect(_num(row.amortization ?? row.auditedAmortization)).toBeGreaterThan(0)
  })

  it('I4-5 核对× → I4-3 分录推送去重', () => {
    const drafts = buildI4TargetedAdjDrafts([
      emptyI4TargetedRow({ voucherNo: '记-1', projectName: '装修A', debitAmount: 80, check3: '×' }),
    ])
    const lines = buildI43LinesFromTargetedDrafts(drafts)
    expect(lines.length).toBeGreaterThan(0)
    const { added, merged } = mergeI43LinesSkippingExisting([], lines)
    expect(added).toBe(lines.length)
    const again = mergeI43LinesSkippingExisting(merged, lines)
    expect(again.added).toBe(0)
  })

  it('CrossSheet 明细期末 = 附注/审定勾稽输入', () => {
    const map = new Map<string, any>([
      ['I4-2-rows', {
        remark: JSON.stringify([
          { projectName: 'A', auditedEnding: 200, originalAmount: 200 },
        ]),
      }],
      ['I4-adj-rows', {
        remark: JSON.stringify([
          emptyI4AdjudicationRow({ projectName: 'A', audited: 200, endBalance: 200, beginBalance: 200 }),
        ]),
      }],
      ['I4-disc-listed-rows', {
        remark: JSON.stringify([{ endBalance: 200 }]),
      }],
    ])
    const allResponses = ref(map)
    const { adjudicationFromDetail } = useI4CrossSheet(allResponses as any)
    expect(adjudicationFromDetail.value.audited).toBe(200)
    expect(reconcileI4DisclosureVsAdj(map).matched).toBe(true)

    const dash = buildI4ConsistencyDashboard(map)
    expect(dash.issues.some((i) => i.id === 'i4-disc-vs-adj')).toBe(false)
  })

  it('一致性：双填 I4-6+I4-7、贷方覆盖率、政策变更→抽凭提示', () => {
    const map = new Map<string, any>([
      ['I4-2-rows', { remark: JSON.stringify([{ projectName: 'A', endBalance: 100 }]) }],
      ['I4-6-rows', { remark: JSON.stringify([{ yearTotal: 10 }]) }],
      ['I4-7-rows', { remark: JSON.stringify([{ yearTotal: 20 }]) }],
      ['I4-4-policy-params', {
        remark: JSON.stringify([{ category: '装修费', hasChange: 'Y' }]),
      }],
      ['I4-5-rows', {
        remark: JSON.stringify([
          emptyI4TargetedRow({ debitAmount: 50, creditAmount: 10 }),
        ]),
      }],
      ['I4-5-sample-meta', {
        remark: JSON.stringify({
          populationAmount: 1000,
          populationCreditAmount: 200,
          coverageThreshold: 40,
          testReasons: ['大额'],
        }),
      }],
      ['I4-5-audit-note', { remark: '' }],
    ])
    const dash = buildI4ConsistencyDashboard(map)
    expect(dash.issues.some((i) => i.id === 'i46-i47-both')).toBe(true)
    expect(dash.issues.some((i) => i.id === 'i44-to-i45-change')).toBe(true)
    expect(dash.issues.some((i) => i.id === 'i45-coverage')).toBe(true)
    expect(dash.issues.some((i) => i.id === 'i45-credit-coverage')).toBe(true)

    const s = summarizeI4Targeted(
      [emptyI4TargetedRow({ debitAmount: 50, creditAmount: 10 })],
      1000,
      200,
    )
    expect(s.creditCoverageRate).toBe(5)
  })
})

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}
