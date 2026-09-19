/**
 * i3AdjudicationModel 单元测试 — 对齐 Excel I3-1
 */
import { describe, it, expect } from 'vitest'
import {
  emptyI3AdjudicationRow,
  normalizeI3AdjudicationRow,
  summarizeI3Adjudication,
  seedI3AdjudicationFromDetail,
  allocateI3Adjustments,
  applyI3ImpairmentFromTest,
  buildI3AdjudicationCrossCheck,
  buildI3AdjudicationConclusionDraft,
  recalcI3AdjudicationRow,
} from '../i3AdjudicationModel'

describe('i3AdjudicationModel', () => {
  it('期末 = 期初 + 新并购 − 减值；审定 = 未审 + AJE + RJE；净额 = 原值 − 累计减值', () => {
    const row = recalcI3AdjudicationRow(emptyI3AdjudicationRow({
      beginBalance: 1000,
      newAcquisition: 200,
      impairment: 50,
      unadjusted: 1150,
      aje: 10,
      rje: -5,
      initialRecognition: 1500,
      accImpairment: 350,
    }))
    expect(row.endBalance).toBe(1150)
    expect(row.audited).toBe(1155)
    expect(row.netValue).toBe(1150)
  })

  it('减值负数被钳制为 0（不可转回）', () => {
    const row = recalcI3AdjudicationRow(emptyI3AdjudicationRow({
      beginBalance: 100,
      impairment: -20,
    }))
    expect(row.impairment).toBe(0)
    expect(row.endBalance).toBe(100)
  })

  it('从 I3-2 带入：当年并购记本期增加，往年记期初', () => {
    const rows = seedI3AdjudicationFromDetail([
      {
        investee: '新并购子',
        goodwillOriginal: 800,
        accImpairmentBegin: 0,
        accImpairmentEnd: 0,
        currentImpairment: 0,
        goodwillNetValue: 800,
        mergerDate: '2026-06-01',
      },
      {
        investee: '旧子',
        goodwillOriginal: 1000,
        accImpairmentBegin: 100,
        accImpairmentEnd: 150,
        currentImpairment: 50,
        goodwillNetValue: 850,
        acquisitionDate: '2020-01-01',
      },
      { investee: '合计', goodwillOriginal: 9999 },
    ], 2026)

    expect(rows).toHaveLength(2)
    const neu = rows.find((r) => r.investee === '新并购子')!
    expect(neu.beginBalance).toBe(0)
    expect(neu.newAcquisition).toBe(800)
    expect(neu.fromDetail).toBe(true)

    const old = rows.find((r) => r.investee === '旧子')!
    expect(old.beginBalance).toBe(900)
    expect(old.newAcquisition).toBe(0)
    expect(old.impairment).toBe(50)
    expect(old.accImpairment).toBe(150)
    expect(old.endBalance).toBe(850)
    expect(old.netValue).toBe(850)
  })

  it('带入时保留已有 AJE/RJE', () => {
    const existing = [emptyI3AdjudicationRow({ investee: '旧子', aje: 12, rje: -3 })]
    const rows = seedI3AdjudicationFromDetail([
      {
        investee: '旧子',
        goodwillOriginal: 1000,
        accImpairmentBegin: 0,
        accImpairmentEnd: 0,
        currentImpairment: 0,
        goodwillNetValue: 1000,
        acquisitionDate: '2019-01-01',
      },
    ], 2026, existing)
    expect(rows[0].aje).toBe(12)
    expect(rows[0].rje).toBe(-3)
  })

  it('AJE/RJE 按未审占比分摊', () => {
    const rows = allocateI3Adjustments([
      emptyI3AdjudicationRow({ investee: 'A', unadjusted: 70 }),
      emptyI3AdjudicationRow({ investee: 'B', unadjusted: 30 }),
    ], 100, 0)
    expect(rows[0].aje).toBe(70)
    expect(rows[1].aje).toBe(30)
    expect(rows[0].audited).toBe(140) // 未审70 + AJE70
    expect(rows[1].audited).toBe(60)
  })

  it('I3-6 减值按名称匹配覆盖本期减少', () => {
    const rows = applyI3ImpairmentFromTest([
      emptyI3AdjudicationRow({ investee: 'CGU-A', beginBalance: 500, initialRecognition: 500 }),
      emptyI3AdjudicationRow({ investee: 'CGU-B', beginBalance: 300, initialRecognition: 300 }),
    ], { 'CGU-A': 40 }, 40)
    expect(rows[0].impairment).toBe(40)
    expect(rows[0].endBalance).toBe(460)
    expect(rows[1].impairment).toBe(0)
  })

  it('与 I3-2 勾稽差异检测', () => {
    const rows = [
      emptyI3AdjudicationRow({
        investee: 'A',
        initialRecognition: 1000,
        beginBalance: 900,
        impairment: 50,
        accImpairment: 150,
        unadjusted: 850,
      }),
    ]
    const cc = buildI3AdjudicationCrossCheck(rows, {
      goodwillOriginalTotal: 1000,
      accImpairmentTotal: 150,
      netValueTotal: 850,
      currentImpairmentTotal: 50,
    })
    expect(cc.hasWarning).toBe(false)
    expect(cc.endVsNetDiff).toBe(0)

    const bad = buildI3AdjudicationCrossCheck(rows, {
      goodwillOriginalTotal: 999,
      accImpairmentTotal: 150,
      netValueTotal: 800,
      currentImpairmentTotal: 10,
    })
    expect(bad.hasWarning).toBe(true)
  })

  it('结论草稿含并购/减值/TB 摘要', () => {
    const text = buildI3AdjudicationConclusionDraft({
      rowCount: 2,
      auditedTotal: 1000,
      netTotal: 980,
      newAcquisitionTotal: 100,
      impairmentTotal: 20,
      tbDiff: 0,
      crossCheck: null,
    })
    expect(text).toContain('2 个')
    expect(text).toContain('新增并购')
    expect(text).toContain('减值')
    expect(text).toContain('勾稽一致')
  })

  it('兼容旧字段 goodwillOriginal / currentImpairment', () => {
    const row = normalizeI3AdjudicationRow({
      investee: 'X',
      goodwillOriginal: 500,
      currentImpairment: 30,
      accImpairmentEnd: 80,
      beginBalance: 450,
    })
    expect(row.initialRecognition).toBe(500)
    expect(row.impairment).toBe(30)
    expect(row.accImpairment).toBe(80)
  })

  it('合计行汇总', () => {
    const sub = summarizeI3Adjudication([
      emptyI3AdjudicationRow({ investee: 'A', beginBalance: 10, unadjusted: 10 }),
      emptyI3AdjudicationRow({ investee: 'B', beginBalance: 20, unadjusted: 20 }),
    ])
    expect(sub.investee).toBe('合计')
    expect(sub.beginBalance).toBe(30)
    expect(sub.unadjusted).toBe(30)
  })
})
