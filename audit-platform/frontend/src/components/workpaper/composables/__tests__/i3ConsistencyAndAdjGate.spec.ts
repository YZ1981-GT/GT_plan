/**
 * i3ConsistencyModel + adjudication AJE/闸门/发生额 回归
 */
import { describe, it, expect } from 'vitest'
import { buildI3ConsistencyDashboard } from '../i3ConsistencyModel'
import {
  applyAjeFromI33,
  validateI3AdjudicationSave,
  buildI3LayerSummary,
  emptyI3AdjudicationRow,
  seedI3AdjudicationFromDetail,
} from '../i3AdjudicationModel'
import { extractI3PeriodMovement } from '../i3TargetedCheckModel'

describe('i3ConsistencyModel', () => {
  it('明细空时告警；审定期末≠净额为 error', () => {
    const map = new Map<string, any>()
    let dash = buildI3ConsistencyDashboard(map)
    expect(dash.issues.some((i) => i.code === 'I3-2')).toBe(true)

    map.set('I3-2-rows', { remark: JSON.stringify([{ investee: 'A', goodwillOriginal: 100 }]) })
    map.set('I3-adj-rows', {
      remark: JSON.stringify([
        emptyI3AdjudicationRow({
          investee: 'A',
          beginBalance: 100,
          endBalance: 100,
          netValue: 80,
          initialRecognition: 100,
          accImpairment: 20,
          unadjusted: 100,
        }),
      ]),
    })
    dash = buildI3ConsistencyDashboard(map)
    expect(dash.errorCount).toBeGreaterThan(0)
    expect(dash.issues.some((i) => i.id === 'i31-end-net')).toBe(true)
  })

  it('I3-5 覆盖率低且无说明 → error', () => {
    const map = new Map<string, any>()
    map.set('I3-2-rows', { remark: JSON.stringify([{ investee: 'A' }]) })
    map.set('I3-5-rows', { remark: JSON.stringify([{ debitAmount: 50 }]) })
    map.set('I3-5-sample-meta', {
      remark: JSON.stringify({ populationAmount: 1000, coverageThreshold: 20 }),
    })
    map.set('I3-5-audit-note', { remark: '' })
    const dash = buildI3ConsistencyDashboard(map)
    expect(dash.issues.some((i) => i.id === 'i35-coverage')).toBe(true)
  })
})

describe('applyAjeFromI33', () => {
  it('按 investee 精确匹配不标近似；剩余分摊标近似', () => {
    const rows = [
      emptyI3AdjudicationRow({ investee: '甲', unadjusted: 70 }),
      emptyI3AdjudicationRow({ investee: '乙', unadjusted: 30 }),
    ]
    const result = applyAjeFromI33(rows, [
      { accountCode: '1711', investee: '甲', entryType: 'AJE', debitAmount: 40, creditAmount: 0 },
      { accountCode: '1711', entryType: 'AJE', debitAmount: 60, creditAmount: 0 }, // 无名 → 分摊
    ])
    expect(result.matchedByName).toBe(1)
    expect(result.approx).toBe(true)
    const jia = result.rows.find((r) => r.investee === '甲')!
    expect(jia.aje).toBeGreaterThanOrEqual(40)
    expect(result.rows.some((r) => r.ajeApprox)).toBe(true)
  })
})

describe('validateI3AdjudicationSave', () => {
  it('TB 差异或期末≠净额阻断', () => {
    const rows = [
      emptyI3AdjudicationRow({
        investee: 'A',
        beginBalance: 100,
        endBalance: 100,
        netValue: 90,
        initialRecognition: 100,
        accImpairment: 10,
      }),
    ]
    // recalc makes end=begin, net=90 → mismatch
    const bad = validateI3AdjudicationSave({ rows, tbDiff: 0 })
    expect(bad.ok).toBe(false)

    const okRows = [
      emptyI3AdjudicationRow({
        investee: 'A',
        beginBalance: 90,
        initialRecognition: 100,
        accImpairment: 10,
        unadjusted: 90,
      }),
    ]
    const ok = validateI3AdjudicationSave({ rows: okRows, tbDiff: 0 })
    expect(ok.ok).toBe(true)

    const tb = validateI3AdjudicationSave({ rows: okRows, tbDiff: 1 })
    expect(tb.ok).toBe(false)
  })
})

describe('buildI3LayerSummary', () => {
  it('输出原值/减值/净值三层', () => {
    const L = buildI3LayerSummary([
      emptyI3AdjudicationRow({
        investee: 'A',
        initialRecognition: 1000,
        newAcquisition: 200,
        beginBalance: 700,
        impairment: 50,
        accImpairment: 150,
        unadjusted: 850,
      }),
    ])
    expect(L.original.increase).toBe(200)
    expect(L.impairment.increase).toBe(50)
    expect(L.net.decrease).toBe(50)
  })
})

describe('extractI3PeriodMovement prefer roll fields', () => {
  it('优先 costIncrease / impIncrease', () => {
    const mv = extractI3PeriodMovement([
      {
        investee: 'A',
        costIncrease: 300,
        impIncrease: 40,
        costDecrease: 10,
        goodwillOriginal: 9999,
        mergerDate: '2020-01-01',
      },
    ], 2026)
    expect(mv.debitTotal).toBe(300)
    expect(mv.creditTotal).toBe(50)
    expect(mv.source).toContain('发生额')
  })
})

describe('seedI3AdjudicationFromDetail costIncrease', () => {
  it('有 costIncrease 时记本期增加', () => {
    const rows = seedI3AdjudicationFromDetail([
      {
        investee: '新',
        goodwillOriginal: 800,
        costIncrease: 800,
        costAudited: 800,
        accImpairmentBegin: 0,
        accImpairmentEnd: 0,
        currentImpairment: 0,
        goodwillNetValue: 800,
      },
    ], 2026)
    expect(rows[0].newAcquisition).toBe(800)
  })
})
