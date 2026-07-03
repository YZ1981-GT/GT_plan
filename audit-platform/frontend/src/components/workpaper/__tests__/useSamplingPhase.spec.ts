/**
 * useSamplingPhase — 单元测试
 *
 * Spec: .kiro/specs/voucher-sampling-engine/
 * Task: 15.2
 *
 * 测试范围：
 * - viewMode 切换：preliminary/final/all 各返回正确子集
 * - isRowEditable：年审+预审行 → false；年审+年审行 → true
 * - isFillModeRestricted：phase=final → true
 * - getPreliminaryVoucherNos：正确提取
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'

import { useSamplingPhase, type PhaseOptions } from '../composables/useSamplingPhase'
import type { Phase, SampledVoucher } from '../composables/useSamplingAlgorithms'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeVoucher(partial: Partial<SampledVoucher> = {}): SampledVoucher {
  return {
    voucherNo: 'V-001',
    voucherDate: '2025-06-01',
    summary: '测试',
    debitAmount: '1000.00',
    creditAmount: null,
    accountCode: '1122',
    accountName: '应收账款',
    counterpartAccount: '6001',
    voucherType: '记',
    accountingPeriod: 6,
    checkResult: '',
    abnormal: false,
    remark: '',
    selected: true,
    phase: 'preliminary',
    editTrail: [],
    ...partial,
  }
}

function makePhaseOptions(
  phase: Phase,
  samples: SampledVoucher[],
): PhaseOptions {
  return {
    phase: ref(phase),
    samples: ref(samples),
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 1. viewMode 切换
// ═══════════════════════════════════════════════════════════════════════════════

describe('useSamplingPhase - viewMode 切换', () => {
  const mixedSamples = [
    makeVoucher({ voucherNo: 'P-001', phase: 'preliminary' }),
    makeVoucher({ voucherNo: 'P-002', phase: 'preliminary' }),
    makeVoucher({ voucherNo: 'F-001', phase: 'final' }),
    makeVoucher({ voucherNo: 'F-002', phase: 'final' }),
    makeVoucher({ voucherNo: 'F-003', phase: 'final' }),
  ]

  it('viewMode="all" → 返回全部样本', () => {
    const { viewMode, visibleSamples } = useSamplingPhase(makePhaseOptions('final', mixedSamples))
    viewMode.value = 'all'
    expect(visibleSamples.value).toHaveLength(5)
  })

  it('viewMode="preliminary" → 仅返回 phase=preliminary 的行', () => {
    const { viewMode, visibleSamples } = useSamplingPhase(makePhaseOptions('final', mixedSamples))
    viewMode.value = 'preliminary'
    expect(visibleSamples.value).toHaveLength(2)
    expect(visibleSamples.value.every(v => v.phase === 'preliminary')).toBe(true)
  })

  it('viewMode="final" → 仅返回 phase=final 的行', () => {
    const { viewMode, visibleSamples } = useSamplingPhase(makePhaseOptions('final', mixedSamples))
    viewMode.value = 'final'
    expect(visibleSamples.value).toHaveLength(3)
    expect(visibleSamples.value.every(v => v.phase === 'final')).toBe(true)
  })

  it('无 preliminary 行时 viewMode="preliminary" → 返回空', () => {
    const finalOnly = [
      makeVoucher({ voucherNo: 'F-001', phase: 'final' }),
    ]
    const { viewMode, visibleSamples } = useSamplingPhase(makePhaseOptions('final', finalOnly))
    viewMode.value = 'preliminary'
    expect(visibleSamples.value).toHaveLength(0)
  })

  it('空样本 → 所有 viewMode 返回空', () => {
    const { viewMode, visibleSamples } = useSamplingPhase(makePhaseOptions('preliminary', []))
    viewMode.value = 'all'
    expect(visibleSamples.value).toHaveLength(0)
    viewMode.value = 'preliminary'
    expect(visibleSamples.value).toHaveLength(0)
    viewMode.value = 'final'
    expect(visibleSamples.value).toHaveLength(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. isRowEditable
// ═══════════════════════════════════════════════════════════════════════════════

describe('useSamplingPhase - isRowEditable', () => {
  it('phase=final + row.phase=preliminary → false（不可编辑）', () => {
    const { isRowEditable } = useSamplingPhase(makePhaseOptions('final', []))
    const row = makeVoucher({ phase: 'preliminary' })
    expect(isRowEditable(row)).toBe(false)
  })

  it('phase=final + row.phase=final → true（可编辑）', () => {
    const { isRowEditable } = useSamplingPhase(makePhaseOptions('final', []))
    const row = makeVoucher({ phase: 'final' })
    expect(isRowEditable(row)).toBe(true)
  })

  it('phase=preliminary + row.phase=preliminary → true（可编辑）', () => {
    const { isRowEditable } = useSamplingPhase(makePhaseOptions('preliminary', []))
    const row = makeVoucher({ phase: 'preliminary' })
    expect(isRowEditable(row)).toBe(true)
  })

  it('phase=preliminary + row.phase=final → true（预审阶段不限制年审行）', () => {
    const { isRowEditable } = useSamplingPhase(makePhaseOptions('preliminary', []))
    const row = makeVoucher({ phase: 'final' })
    expect(isRowEditable(row)).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. isFillModeRestricted
// ═══════════════════════════════════════════════════════════════════════════════

describe('useSamplingPhase - isFillModeRestricted', () => {
  it('phase=final → isFillModeRestricted=true', () => {
    const { isFillModeRestricted } = useSamplingPhase(makePhaseOptions('final', []))
    expect(isFillModeRestricted.value).toBe(true)
  })

  it('phase=preliminary → isFillModeRestricted=false', () => {
    const { isFillModeRestricted } = useSamplingPhase(makePhaseOptions('preliminary', []))
    expect(isFillModeRestricted.value).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 4. getPreliminaryVoucherNos
// ═══════════════════════════════════════════════════════════════════════════════

describe('useSamplingPhase - getPreliminaryVoucherNos', () => {
  it('正确提取所有 phase=preliminary 的 voucherNo', () => {
    const samples = [
      makeVoucher({ voucherNo: 'P-001', phase: 'preliminary' }),
      makeVoucher({ voucherNo: 'P-002', phase: 'preliminary' }),
      makeVoucher({ voucherNo: 'F-001', phase: 'final' }),
    ]
    const { getPreliminaryVoucherNos } = useSamplingPhase(makePhaseOptions('final', samples))
    const nos = getPreliminaryVoucherNos()
    expect(nos).toEqual(['P-001', 'P-002'])
  })

  it('无 preliminary 行 → 返回空数组', () => {
    const samples = [
      makeVoucher({ voucherNo: 'F-001', phase: 'final' }),
    ]
    const { getPreliminaryVoucherNos } = useSamplingPhase(makePhaseOptions('final', samples))
    expect(getPreliminaryVoucherNos()).toHaveLength(0)
  })

  it('全部为 preliminary → 返回全部 voucherNo', () => {
    const samples = [
      makeVoucher({ voucherNo: 'P-001', phase: 'preliminary' }),
      makeVoucher({ voucherNo: 'P-002', phase: 'preliminary' }),
      makeVoucher({ voucherNo: 'P-003', phase: 'preliminary' }),
    ]
    const { getPreliminaryVoucherNos } = useSamplingPhase(makePhaseOptions('preliminary', samples))
    expect(getPreliminaryVoucherNos()).toEqual(['P-001', 'P-002', 'P-003'])
  })

  it('空样本 → 返回空数组', () => {
    const { getPreliminaryVoucherNos } = useSamplingPhase(makePhaseOptions('final', []))
    expect(getPreliminaryVoucherNos()).toHaveLength(0)
  })
})
