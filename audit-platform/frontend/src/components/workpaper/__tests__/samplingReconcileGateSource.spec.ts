/**
 * 结论确认门控来源（conclusionBlockedSource）— 行为测试
 *
 * spec: voucher-sampling-reconcile-balance-source（R3.3）
 *
 * 真实实例化 useVoucherSampling，驱动样本 / 完整性核对 / 放行理由，断言：
 * - 来源与 conclusionBlockedReason 同链同序（未检查 → 偏差 → 完整性核对）；
 * - 来源为空 ⇔ 原因为空（两个 computed 不得各说各话）；
 * - 来源为 reconcile 时，原因以注入的核对问题原文开头（引擎据此改提示去向）。
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn(), post: vi.fn() } }))

import { useVoucherSampling } from '../composables/useVoucherSampling'
import type { SampledVoucher, Phase } from '../composables/useSamplingAlgorithms'

const RECONCILE_ISSUE = '未执行总体完整性核对：科目余额表中无所选科目（1122）的行，无法确认样本取自完整总体'

function make() {
  return useVoucherSampling({
    projectId: ref('p1'),
    year: ref(2025),
    workpaperId: ref('wp1'),
    accountCode: '1122',
    phase: ref<Phase>('final'),
  })
}

function voucher(no: string, checkResult: SampledVoucher['checkResult']): SampledVoucher {
  return {
    voucherNo: no,
    voucherDate: '2025-06-01',
    summary: null,
    debitAmount: '100.00',
    creditAmount: null,
    accountCode: '1122',
    accountName: null,
    counterpartAccount: null,
    voucherType: null,
    accountingPeriod: 6,
    checkResult,
    abnormal: false,
    remark: '',
    selected: true,
    phase: 'final',
    editTrail: [],
  }
}

function expectConsistent(s: ReturnType<typeof make>) {
  expect(s.conclusionBlockedSource.value === null).toBe(s.conclusionBlockedReason.value === null)
}

describe('conclusionBlockedSource 与 conclusionBlockedReason 同链', () => {
  it('全部已检查、无核对问题 ⇒ 来源与原因都为空', () => {
    const s = make()
    s.sampledVouchers.value = [voucher('A', 'Y'), voucher('B', 'Y')]
    expect(s.conclusionBlockedSource.value).toBeNull()
    expectConsistent(s)
  })

  it('有未检查样本 ⇒ unchecked', () => {
    const s = make()
    s.sampledVouchers.value = [voucher('A', 'Y'), voucher('B', '')]
    expect(s.conclusionBlockedSource.value).toBe('unchecked')
    expect(s.conclusionBlockedReason.value).toContain('未检查样本')
    expectConsistent(s)
  })

  it('有未标注性质的偏差 ⇒ deviation', () => {
    const s = make()
    s.sampledVouchers.value = [voucher('A', 'Y'), voucher('B', 'N')]
    expect(s.conclusionBlockedSource.value).toBe('deviation')
    expectConsistent(s)
  })

  it('只剩完整性核对问题 ⇒ reconcile，且原因以核对问题原文开头', () => {
    const s = make()
    s.sampledVouchers.value = [voucher('A', 'Y')]
    s.setReconcileBlockedReason(RECONCILE_ISSUE)
    expect(s.conclusionBlockedSource.value).toBe('reconcile')
    expect(s.conclusionBlockedReason.value?.startsWith(RECONCILE_ISSUE)).toBe(true)
    expectConsistent(s)
  })

  it('放行理由 9 字仍阻断，10 字解除', () => {
    const s = make()
    s.sampledVouchers.value = [voucher('A', 'Y')]
    s.setReconcileBlockedReason(RECONCILE_ISSUE)
    s.reconcileOverrideReason.value = '一二三四五六七八九'
    expect(s.conclusionBlockedSource.value).toBe('reconcile')
    s.reconcileOverrideReason.value = '一二三四五六七八九十'
    expect(s.conclusionBlockedSource.value).toBeNull()
    expect(s.conclusionBlockedReason.value).toBeNull()
  })

  it('未检查与核对问题同时存在 ⇒ 先报 unchecked（与原因链同序）', () => {
    const s = make()
    s.sampledVouchers.value = [voucher('A', '')]
    s.setReconcileBlockedReason(RECONCILE_ISSUE)
    expect(s.conclusionBlockedSource.value).toBe('unchecked')
    expect(s.conclusionBlockedReason.value?.startsWith(RECONCILE_ISSUE)).toBe(false)
    expectConsistent(s)
  })
})
