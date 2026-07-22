import { describe, it, expect } from 'vitest'
import { defaultG10AdjStore } from '../g10AdjStorage'
import { summarizeG10CrossChecks, worstG10CrossCheckStatus } from '../g10CrossChecks'

describe('g10CrossChecks', () => {
  it('试算表一致时 CHK-01 为 ok', () => {
    const store = defaultG10AdjStore()
    store.book_other = {
      openingUnadjusted: 0,
      closingUnadjusted: 100,
      closingAdjustment: 0,
    }
    const m = new Map<string, any>([
      ['G10-adj-rows', { remark: JSON.stringify(store) }],
      ['G10-adj-tb', { remark: '100' }],
      ['G10-1-adjudicated-amount', { conclusion: '100' }],
    ])
    const items = summarizeG10CrossChecks(m)
    const chk01 = items.find((i) => i.code === 'G10-CHK-01')
    expect(chk01?.status).toBe('ok')
    expect(worstG10CrossCheckStatus(items)).not.toBe('error')
  })

  it('三部分不一致时 CHK-02 warn', () => {
    const store = defaultG10AdjStore()
    store.init_other = { openingUnadjusted: 100, closingUnadjusted: 100 }
    store.fv_other = { openingUnadjusted: 10, closingUnadjusted: 10 }
    store.book_other = { openingUnadjusted: 50, closingUnadjusted: 50 }
    const m = new Map<string, any>([
      ['G10-adj-rows', { remark: JSON.stringify(store) }],
    ])
    const chk02 = summarizeG10CrossChecks(m).find((i) => i.code === 'G10-CHK-02')
    expect(chk02?.status).toBe('warn')
  })

  it('G10-5 与 G10-2 一致时 CHK-06 为 ok', () => {
    const m = new Map<string, any>([
      ['G10-fv-test-rows', { remark: JSON.stringify([{ closingAuditedFV: 100 }]) }],
      ['G10-detail-rows', { remark: JSON.stringify([{ rowId: 'd1', liabilityName: '测试', openingInitialAmount: 100 }]) }],
    ])
    const chk06 = summarizeG10CrossChecks(m).find((i) => i.code === 'G10-CHK-06')
    expect(chk06?.status).toBe('ok')
  })

  it('G10-7 检查比例低时 CHK-08 warn', () => {
    const m = new Map<string, any>([
      ['G10-vc-params', {
        remark: JSON.stringify({
          current: {
            testPopulation: '', specificSamples: '', samplingPopulation: '',
            samplingMethod: '', samplingProcess: '', targetSampleSize: 0,
            populationCount: 0, populationAmount: 10000, bookValue: 0,
            riskFactor: 1, tolerableMisstatement: 0, expectedMisstatement: 0,
            riskOfIncorrectAcceptance: 5,
          },
          subsequent: {
            testPopulation: '', specificSamples: '', samplingPopulation: '',
            samplingMethod: '', samplingProcess: '', targetSampleSize: 0,
            populationCount: 0, populationAmount: 0, bookValue: 0,
            riskFactor: 1, tolerableMisstatement: 0, expectedMisstatement: 0,
            riskOfIncorrectAcceptance: 5,
          },
        }),
      }],
      ['G10-voucher-rows', {
        remark: JSON.stringify({
          version: 2,
          rows: [{ periodScope: 'current', debitAmount: 100, creditAmount: 0, isAbnormal: false }],
        }),
      }],
    ])
    const chk08 = summarizeG10CrossChecks(m).find((i) => i.code === 'G10-CHK-08')
    expect(chk08?.status).toBe('warn')
    expect(chk08?.detail).toContain('30%')
  })

  it('G10-3 借贷平衡且含跨来源时 CHK-10 ok', () => {
    const m = new Map<string, any>([
      ['G10-aje-rows', {
        remark: JSON.stringify([
          { entryType: 'AJE', accountCode: '6101', debitAmount: 50, creditAmount: 0, summary: 'G10-5 公允测试差异：A', indexRef: 'G10-5' },
          { entryType: 'AJE', accountCode: '2101', debitAmount: 0, creditAmount: 50, summary: 'G10-5 公允测试差异：A（公允变动）', indexRef: 'G10-5' },
        ]),
      }],
    ])
    const chk10 = summarizeG10CrossChecks(m).find((i) => i.code === 'G10-CHK-10')
    expect(chk10?.status).toBe('ok')
    expect(chk10?.detail).toContain('G10-5')
  })

  it('G10-3 借贷不平衡时 CHK-10 error', () => {
    const m = new Map<string, any>([
      ['G10-aje-rows', {
        remark: JSON.stringify([
          { entryType: 'AJE', accountCode: '2101', debitAmount: 0, creditAmount: 100, summary: '手工' },
        ]),
      }],
    ])
    const chk10 = summarizeG10CrossChecks(m).find((i) => i.code === 'G10-CHK-10')
    expect(chk10?.status).toBe('error')
  })

  it('G10-3 零金额备忘 CHK-10 warn', () => {
    const m = new Map<string, any>([
      ['G10-aje-rows', {
        remark: JSON.stringify([
          { entryType: 'AJE', accountCode: '2101', debitAmount: 0, creditAmount: 0, summary: 'G10-8 衍生不合规：2 拆分', indexRef: 'G10-8', remark: '来自 G10-8' },
          { entryType: 'AJE', accountCode: '2501', debitAmount: 0, creditAmount: 0, summary: 'G10-8 衍生不合规：2 拆分（对方科目待复核）', indexRef: 'G10-8' },
        ]),
      }],
    ])
    const chk10 = summarizeG10CrossChecks(m).find((i) => i.code === 'G10-CHK-10')
    expect(chk10?.status).toBe('warn')
    expect(chk10?.detail).toContain('备忘待补金额')
  })

  it('G10-3 2101 净额与 G10-1 回写一致时 CHK-11 ok', () => {
    const wb = { book_other: { closingAJE: 50, closingRJE: 0 } }
    const m = new Map<string, any>([
      ['G10-aje-rows', {
        remark: JSON.stringify([
          { entryType: 'AJE', accountCode: '6101', debitAmount: 50, creditAmount: 0 },
          { entryType: 'AJE', accountCode: '2101', debitAmount: 0, creditAmount: 50 },
        ]),
      }],
      ['G10-adj-rows', { remark: JSON.stringify(wb) }],
    ])
    const chk11 = summarizeG10CrossChecks(m).find((i) => i.code === 'G10-CHK-11')
    expect(chk11?.status).toBe('ok')
  })

  it('G10-3 与 G10-1 回写不一致时 CHK-11 warn', () => {
    const m = new Map<string, any>([
      ['G10-aje-rows', {
        remark: JSON.stringify([
          { entryType: 'AJE', accountCode: '2101', debitAmount: 0, creditAmount: 100 },
        ]),
      }],
      ['G10-adj-rows', { remark: JSON.stringify({}) }],
    ])
    const chk11 = summarizeG10CrossChecks(m).find((i) => i.code === 'G10-CHK-11')
    expect(chk11?.status).toBe('warn')
    expect(chk11?.detail).toContain('差')
  })
})
