import { describe, it, expect } from 'vitest'
import {
  calcG11SuggestedSampleSize,
  defaultG11SamplingParams,
  g11VoucherInspectionRatio,
  parseG11SamplingParams,
  calcG11SampleAbsAmount,
  formatG11SamplingMethodLabel,
} from '../g11VoucherConstants'
import {
  buildG11VoucherPushItems,
  isG11QuantitativeVoucherAbnormal,
  pushG11VoucherAbnormalToAdjustment,
  describeG11FailedChecks,
} from '../g11VoucherCross'
import { calcG11AdjPopulationAmount } from '../g11AdjStorage'
import { enrichG11VoucherRow, buildG11VoucherSamplingMemo } from '../useG11VoucherCheck'
import { mapCutoffToG11Voucher } from '../gCycleCutoffFill'
import type { ChecklistResponse } from '../useF1FormData'

describe('g11VoucherConstants', () => {
  it('检查比例 = 已查 / 本期发生额', () => {
    expect(g11VoucherInspectionRatio(300, 1000)).toBeCloseTo(0.3)
    expect(g11VoucherInspectionRatio(100, 0)).toBeNull()
  })

  it('公式样本量在可容忍错报有效时给出正整数', () => {
    const n = calcG11SuggestedSampleSize({
      ...defaultG11SamplingParams(),
      bookValue: 1_000_000,
      tolerableMisstatement: 50_000,
      expectedMisstatement: 5_000,
      riskFactor: 1,
      riskOfIncorrectAcceptance: 5,
    })
    expect(n).toBeGreaterThan(0)
  })

  it('parseG11SamplingParams 兼容空与中文方法名', () => {
    expect(parseG11SamplingParams(null).targetSampleSize).toBe(0)
    const p = parseG11SamplingParams(JSON.stringify({
      samplingMethod: '货币单位抽样(MUS)',
      populationAmount: 12345,
    }))
    expect(p.samplingMethod).toBe('mus')
    expect(p.populationAmount).toBe(12345)
    expect(formatG11SamplingMethodLabel('mus')).toContain('MUS')
  })

  it('calcG11SampleAbsAmount 汇总贷方绝对值', () => {
    expect(calcG11SampleAbsAmount([{ creditAmount: 100 }, { creditAmount: -50 }])).toBe(150)
  })
})

describe('g11VoucherCross', () => {
  function row(patch: Record<string, unknown> = {}) {
    return enrichG11VoucherRow({
      voucherNo: '记-1',
      businessContent: '收到分红',
      creditAmount: 10000,
      check3: false,
      check5: true,
      ...patch,
    }, 1)
  }

  it('金额核对未通过且有金额 → 金额类异常', () => {
    const r = row()
    expect(r.isAbnormal).toBe(true)
    expect(isG11QuantitativeVoucherAbnormal(r)).toBe(true)
    expect(describeG11FailedChecks(r)).toContain('③金额')
  })

  it('仅授权未通过 → 定性异常不可推送', () => {
    const r = row({ check1: true, check2: false, check3: true, check4: true, check5: true })
    expect(r.isAbnormal).toBe(true)
    expect(isG11QuantitativeVoucherAbnormal(r)).toBe(false)
    expect(buildG11VoucherPushItems([r])).toHaveLength(0)
  })

  it('全部未测 → 非异常；forceAbnormal → 异常', () => {
    const untested = enrichG11VoucherRow({ creditAmount: 100 }, 1)
    expect(untested.check1).toBeNull()
    expect(untested.isAbnormal).toBe(false)
    const forced = enrichG11VoucherRow({ creditAmount: 100, forceAbnormal: true }, 1)
    expect(forced.isAbnormal).toBe(true)
    expect(isG11QuantitativeVoucherAbnormal(forced)).toBe(false)
  })

  it('calcG11AdjPopulationAmount 汇总未审本期', () => {
    expect(calcG11AdjPopulationAmount({
      a: { currentUnadjusted: 1000 },
      b: { currentUnadjusted: 2500 },
    })).toBe(3500)
  })

  it('pushG11VoucherAbnormalToAdjustment 写入借贷对并回写 G11-1', () => {
    const responses = new Map<string, ChecklistResponse>()
    const saved: Record<string, string> = {}
    const save = (id: string, d: Partial<ChecklistResponse>) => {
      saved[id] = String(d.remark ?? '')
      responses.set(id, { item_id: id, conclusion: null, remark: d.remark ?? null } as ChecklistResponse)
    }
    const { pushed } = pushG11VoucherAbnormalToAdjustment(responses, save, [row()])
    expect(pushed).toBe(1)
    const aje = JSON.parse(saved['G11-aje-rows'])
    expect(aje).toHaveLength(2)
    expect(aje[0].accountCode).toBe('6111')
    expect(aje[0].debitAmount).toBe(10000)
    expect(aje[1].creditAmount).toBe(10000)
    const adj = JSON.parse(saved['G11-adj-rows'])
    // 分项回写可能写入 other；兼容旧「整表净额」或新 aggregate
    const otherAdj = adj.other?.currentAdjustment
    expect(typeof otherAdj === 'number' || Object.values(adj).some((r: any) => r?.currentAdjustment !== 0)).toBe(true)
  })

  it('重复推送跳过', () => {
    const responses = new Map<string, ChecklistResponse>()
    const save = (id: string, d: Partial<ChecklistResponse>) => {
      responses.set(id, { item_id: id, conclusion: null, remark: d.remark ?? null } as ChecklistResponse)
    }
    const r = row()
    expect(pushG11VoucherAbnormalToAdjustment(responses, save, [r]).pushed).toBe(1)
    expect(pushG11VoucherAbnormalToAdjustment(responses, save, [r]).skipped).toBe(1)
  })
})

describe('buildG11VoucherSamplingMemo', () => {
  it('含样本参数与检查比例', () => {
    const md = buildG11VoucherSamplingMemo({
      params: {
        ...defaultG11SamplingParams(),
        testPopulation: '6111 共10笔',
        populationAmount: 100000,
        samplingMethod: 'mus',
      },
      rows: [enrichG11VoucherRow({ creditAmount: 30000, voucherNo: 'V1' }, 1)],
      conclusion: '未见异常',
    })
    expect(md).toContain('G11-5')
    expect(md).toContain('30.0%')
    expect(md).toContain('未见异常')
    expect(md).toContain('MUS')
  })
})

describe('mapCutoffToG11Voucher', () => {
  it('跨期强制异常且核对默认未测', () => {
    const r = mapCutoffToG11Voucher({
      voucherDate: '2025-01-02',
      voucherNo: '记-99',
      summary: '跨期收益',
      creditAmount: '5000',
      counterpartAccount: '1002',
      cutoffStatus: '可能跨期',
      remark: '资产负债表日后',
    } as any, 1)
    expect(r.forceAbnormal).toBe(true)
    expect(r.isAbnormal).toBe(true)
    expect(r.check1).toBeNull()
    expect(r.source).toBe('截止')
    expect(r.creditAmount).toBe(5000)
  })
})
