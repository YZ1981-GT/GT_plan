/**
 * 错报推断——未检查样本不参与（voucher-sampling-hardening Task 12 / P20）
 *
 * inferMisstatement 仅纳入 checkResult 非空样本；未检查样本不得按零错报计入，
 * 否则经典比率法的样本金额分母被撑大 → 系统性低估推断错报。
 *
 * Validates: Requirements 10.7
 * Properties: Property 20
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { useVoucherSampling } from '../composables/useVoucherSampling'
import type { SampledVoucher, Phase } from '../composables/useSamplingAlgorithms'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

function makeOptions() {
  return {
    projectId: ref('p1'),
    year: ref(2025),
    workpaperId: ref('wp1'),
    accountCode: '1122',
    phase: ref('final') as any,
  }
}

function makeVoucher(over: Partial<SampledVoucher>): SampledVoucher {
  return {
    voucherNo: 'V',
    voucherDate: '2025-01-01',
    summary: null,
    debitAmount: null,
    creditAmount: null,
    accountCode: '1122',
    accountName: null,
    counterpartAccount: null,
    voucherType: null,
    accountingPeriod: null,
    checkResult: 'Y',
    abnormal: false,
    remark: '',
    selected: true,
    phase: 'final' as Phase,
    editTrail: [],
    ...over,
  }
}

describe('inferMisstatement 未检查样本不参与推断（P20）', () => {
  it('仅已检查样本参与经典比率法推断', () => {
    const s = useVoucherSampling(makeOptions())
    s.coverageStats.value = {
      populationCount: 100,
      populationAmount: '100000',
      sampleCount: 2,
      sampleAmount: '2000',
      countCoverageRate: '2.00',
      amountCoverageRate: '2.00',
    }
    s.samplingInterval.value = '0' // 经典法
    s.config.value.samplingMethod = 'random'
    s.sampledVouchers.value = [
      makeVoucher({ voucherNo: 'A', checkResult: 'Y', debitAmount: '1000', actualMisstatement: '100' }),
      // 未检查样本：checkResult 为空、无实际错报 → 不应计入分母
      makeVoucher({ voucherNo: 'B', checkResult: '', debitAmount: '1000', actualMisstatement: '' }),
    ]
    const { result } = s.inferMisstatement()
    // 仅 A 参与：projected = 100/1000 × 100000 = 10000.00
    // 若 B 也计入：分母 2000 → projected = 5000.00（被低估）。10000 证明 B 被排除。
    expect(result.projected).toBe('10000.00')
  })

  it('uncheckedSampleCount 正确反映未检查数', () => {
    const s = useVoucherSampling(makeOptions())
    s.sampledVouchers.value = [
      makeVoucher({ checkResult: 'Y' }),
      makeVoucher({ checkResult: '' }),
      makeVoucher({ checkResult: '异常' }),
    ]
    expect(s.uncheckedSampleCount.value).toBe(1)
    expect(s.checkedSampleCount.value).toBe(2)
  })
})
