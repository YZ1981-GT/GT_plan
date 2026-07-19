/**
 * G2-5 利息测算 — 公式 / 取数 / 勾稽契约测试
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  extractCalcRowsFromDetail,
  sumDetailAccrued,
  inferEirInInstrument,
  parseEirFlag,
  buildG21CalcCrossRefNote,
  mergeG21CalcCrossRefNote,
  G21_CALC_CROSS_REF_START,
  G2_INTEREST_VARIANCE_THRESHOLD,
  useG2InterestCalc,
} from '../useG2InterestCalc'
import { calcInterest365, calcAccruedDays } from '../useG2IntRecFormulaEngine'

describe('G2-5 利息测算公式', () => {
  it('应计利息 = 面值 × 利率 × 天数 / 365', () => {
    const days = calcAccruedDays('2025-01-01', '2025-07-01')
    expect(days).toBe(181)
    const interest = calcInterest365(1_000_000, 4.5, days)
    expect(interest).toBeCloseTo((1_000_000 * 4.5 / 100 * 181) / 365, 5)
  })

  it('差异阈值默认 100', () => {
    expect(G2_INTEREST_VARIANCE_THRESHOLD).toBe(100)
  })

  it('EIR 推断：债权投资=是，定期存款=否', () => {
    expect(inferEirInInstrument('XX债权投资', '')).toBe(true)
    expect(inferEirInInstrument('其他债权投资A', '')).toBe(true)
    expect(inferEirInInstrument('银行定期存款', '')).toBe(false)
    expect(parseEirFlag('是')).toBe(true)
    expect(parseEirFlag('否')).toBe(false)
  })

  it('G2-1 对照块可生成并幂等替换', () => {
    const block1 = buildG21CalcCrossRefNote({
      maturedFor1132: 3100,
      adjGrossEnd: 3000,
      eirAccruedTotal: 0,
      eirRowCount: 0,
      calculatedInterest: 3100,
      companyAccrual: 3100,
      variance: 0,
    })
    expect(block1).toContain(G21_CALC_CROSS_REF_START)
    expect(block1).toContain('3,100.00')
    expect(block1).toContain('须核查')
    const merged1 = mergeG21CalcCrossRefNote('原有说明', block1)
    expect(merged1).toContain('原有说明')
    const block2 = buildG21CalcCrossRefNote({
      maturedFor1132: 9999,
      adjGrossEnd: 3000,
      eirAccruedTotal: 100,
      eirRowCount: 1,
      calculatedInterest: 10099,
      companyAccrual: 3100,
      variance: 6999,
    })
    const merged2 = mergeG21CalcCrossRefNote(merged1, block2)
    expect(merged2).toContain('9,999.00')
    expect(merged2).toContain('原有说明')
    expect((merged2.match(/【G2-5测算对照】/g) || []).length).toBe(1)
    expect((merged2.match(/【\/G2-5测算对照】/g) || []).length).toBe(1)
  })
})

describe('从 G2-2 提取测算行', () => {
  it('有计息基础的行被提取；定存进1132，债权投资标EIR', () => {
    const raw = JSON.stringify([
      {
        id: 'd1',
        investTarget: '定存A',
        investType: '定期存款',
        faceValue: 100000,
        couponRate: 3,
        accrualStart: '2025-01-01',
        accrualEnd: '2025-04-01',
        closingAudited: 700,
      },
      {
        id: 'd3',
        investTarget: '国债',
        investType: '债权投资',
        faceValue: 100000,
        couponRate: 3,
        accrualStart: '2025-01-01',
        accrualEnd: '2025-04-01',
        closingAudited: 700,
      },
      { id: 'd2', investTarget: '无计息', faceValue: 0, couponRate: 0 },
    ])
    const rows = extractCalcRowsFromDetail(raw)
    expect(rows).toHaveLength(2)
    const deposit = rows.find((r) => r.id && r.investTarget === '定存A')!
    expect(deposit.companyAccrual).toBe(700)
    expect(deposit.eirInInstrument).toBe(false)
    const days = calcAccruedDays('2025-01-01', '2025-04-01')
    expect(deposit.maturedCollectible).toBeCloseTo(calcInterest365(100000, 3, days), 5)
    const bond = rows.find((r) => r.investTarget === '国债')!
    expect(bond.eirInInstrument).toBe(true)
    expect(bond.maturedCollectible).toBe(0)
  })

  it('明细应计合计可汇总', () => {
    const raw = JSON.stringify([
      { faceValue: 100000, couponRate: 3.65, accrualStart: '2025-01-01', accrualEnd: '2025-02-01' },
      { faceValue: 200000, couponRate: 3.65, accrualStart: '2025-01-01', accrualEnd: '2025-02-01' },
    ])
    const { total, count } = sumDetailAccrued(raw)
    expect(count).toBe(2)
    const days = calcAccruedDays('2025-01-01', '2025-02-01')
    expect(total).toBeCloseTo(calcInterest365(300000, 3.65, days), 5)
  })
})

describe('useG2InterestCalc 运行时', () => {
  it('差异警告与已到期可收取超应计检测', () => {
    const allResponses = ref(new Map([
      ['G2-5-interest-calc-rows', {
        item_id: 'G2-5-interest-calc-rows',
        conclusion: null,
        remark: JSON.stringify([{
          id: 'r1',
          seq: 1,
          investTarget: 'X',
          faceValue: 365000,
          couponRate: 10,
          accrualStart: '2025-01-01',
          accrualEnd: '2025-02-01', // 31 days → interest = 365000*0.1*31/365 = 3100
          maturedCollectible: 5000,
          companyAccrual: 1000,
          varianceReason: '',
          remark: '',
          eirInInstrument: false,
        }]),
      }],
    ]))
    const calc = useG2InterestCalc({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses: allResponses as any,
      isReadonly: ref(false),
    })
    const row = calc.dataRows.value[0]
    expect(row.calculatedInterest).toBeCloseTo(3100, 5)
    expect(row.variance).toBeCloseTo(2100, 5)
    expect(calc.isVarianceWarning(row)).toBe(true)
    expect(calc.isVarianceReasonRequired(row)).toBe(true)
    expect(calc.isMaturedOverAccrued(row)).toBe(true)
  })

  it('实际利率法行：⑤清零且不计入1132勾稽', () => {
    const allResponses = ref(new Map([
      ['G2-5-interest-calc-rows', {
        item_id: 'G2-5-interest-calc-rows',
        conclusion: null,
        remark: JSON.stringify([
          {
            id: 'a',
            seq: 1,
            investTarget: '债券EIR',
            faceValue: 365000,
            couponRate: 10,
            accrualStart: '2025-01-01',
            accrualEnd: '2025-02-01',
            maturedCollectible: 3100,
            companyAccrual: 3100,
            varianceReason: '',
            remark: '',
            eirInInstrument: false,
          },
          {
            id: 'b',
            seq: 2,
            investTarget: '定存',
            faceValue: 365000,
            couponRate: 10,
            accrualStart: '2025-01-01',
            accrualEnd: '2025-02-01',
            maturedCollectible: 3100,
            companyAccrual: 3100,
            varianceReason: '',
            remark: '',
            eirInInstrument: false,
          },
        ]),
      }],
      ['G2-1-rows', {
        item_id: 'G2-1-rows',
        conclusion: null,
        remark: JSON.stringify({
          'gross-collective': {
            openingUnadjusted: 0,
            openingAdjustment: 0,
            closingUnadjusted: 3100,
            closingAdjustment: 0,
          },
          'gross-individual': {
            openingUnadjusted: 0,
            openingAdjustment: 0,
            closingUnadjusted: 0,
            closingAdjustment: 0,
          },
          'provision-collective': {
            openingUnadjusted: 0,
            openingAdjustment: 0,
            closingUnadjusted: 0,
            closingAdjustment: 0,
          },
          'provision-individual': {
            openingUnadjusted: 0,
            openingAdjustment: 0,
            closingUnadjusted: 0,
            closingAdjustment: 0,
          },
        }),
      }],
    ]))
    const calc = useG2InterestCalc({
      wpId: ref('wp'),
      projectId: ref('p'),
      allResponses: allResponses as any,
      isReadonly: ref(false),
    })
    // 两行均进 1132 → 6200 vs 审定 3100 → 不一致
    expect(calc.totals.value.maturedFor1132).toBeCloseTo(6200, 5)
    expect(calc.adjTieOut.value.hasAdjData).toBe(true)
    expect(calc.adjTieOut.value.matched).toBe(false)

    calc.setEirInInstrument('a', true)
    expect(calc.dataRows.value.find((r) => r.id === 'a')!.eirInInstrument).toBe(true)
    expect(calc.dataRows.value.find((r) => r.id === 'a')!.maturedCollectible).toBe(0)
    expect(calc.totals.value.maturedFor1132).toBeCloseTo(3100, 5)
    expect(calc.totals.value.eirRowCount).toBe(1)
    expect(calc.adjTieOut.value.matched).toBe(true)

    const pushed = calc.pushCrossRefToG21()
    expect(pushed.ok).toBe(true)
    expect(pushed.matched).toBe(true)
    const note = allResponses.value.get('G2-1-note')?.remark || ''
    expect(note).toContain(G21_CALC_CROSS_REF_START)
    expect(note).toContain('勾稽一致')
  })
})
