/**
 * useI6Cutoff / useCycleCutoff — I6 截止测试单元测试
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useI6Cutoff } from '../useI6Cutoff'
import { buildCutoffCrossCheck } from '../cutoffCrossCheck'
import { amountMismatch } from '../cutoffRowHelpers'

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('@/utils/http', () => ({
  default: { post: vi.fn(), get: vi.fn() },
}))

describe('useI6Cutoff', () => {
  const allResponses = ref(new Map<string, any>())
  const projectId = ref('proj-i6')
  const saveResponses = vi.fn(async () => {})

  beforeEach(() => {
    allResponses.value = new Map()
    saveResponses.mockClear()
  })

  function setup() {
    return useI6Cutoff({ allResponses, saveResponses, projectId, autoSaveMs: 0 })
  }

  it('跨期多记：账在截止前、单据在截止后', () => {
    const api = setup()
    api.updateForwardCriteria({ cutoffDate: '2025-12-31' })
    api.addForwardRow({
      recordDate: '2025-12-30', documentDate: '2026-01-03', amount: 5000, documentAmount: 5000, voucherNo: 'J-001',
    })
    expect(api.forwardRows.value[0].isCrossPeriod).toBe(true)
    expect(api.forwardRows.value[0].conclusion).toBe('跨期多记')
  })

  it('importExtractedVouchers 默认不预填单据日期', () => {
    const api = setup()
    api.updateForwardCriteria({ cutoffDate: '2025-12-31' })
    api.importExtractedVouchers('forward', [{
      voucher_date: '2025-12-28', voucher_no: 'J-002', amount: 1000, summary: '材料',
    }], { fillDocumentDate: false })
    expect(api.forwardRows.value[0].recordDate).toBe('2025-12-28')
    expect(api.forwardRows.value[0].documentDate).toBe('')
    expect(api.forwardRows.value[0].documentAmount).toBe(0)
  })

  it('updateForwardCriteria 同步至 backward criteria', () => {
    const api = setup()
    api.updateForwardCriteria({ cutoffDate: '2025-12-31', daysBefore: 10, amountThreshold: 5000 })
    expect(api.backwardCriteria.value.cutoffDate).toBe('2025-12-31')
    expect(api.backwardCriteria.value.daysBefore).toBe(10)
    expect(api.backwardCriteria.value.amountThreshold).toBe(5000)
  })

  it('loadFromAutoSampling 调用 6602 截止测试 API', async () => {
    const http = (await import('@/utils/http')).default
    vi.mocked(http.post).mockResolvedValueOnce({
      data: { entries: [{ voucher_date: '2025-12-28', voucher_no: 'J-1', debit_amount: 1 }] },
    })
    const api = setup()
    api.updateForwardCriteria({ cutoffDate: '2025-12-31' })
    await api.loadFromAutoSampling('forward')
    // 真实端点 /sampling/cutoff-test，account_codes 数组；方向由客户端分段
    expect(http.post).toHaveBeenCalledWith(
      '/api/projects/proj-i6/sampling/cutoff-test',
      expect.objectContaining({ account_codes: ['6602'], year: 2025 }),
    )
    expect(api.forwardRows.value.length).toBe(1)
    expect(api.forwardRows.value[0].recordDate).toBe('2025-12-28')
  })
})

describe('cutoffCrossCheck', () => {
  it('同凭证号两表结论一致', () => {
    const summary = buildCutoffCrossCheck(
      [{ voucherNo: 'J-1', amount: 100, isCrossPeriod: true, conclusion: '跨期多记' } as any],
      [{ voucherNo: 'J-1', amount: 100, isCrossPeriod: true, conclusion: '跨期' } as any],
    )
    expect(summary.matchedCount).toBe(1)
    expect(summary.consistentCount).toBe(1)
  })

  it('同凭证号结论不一致', () => {
    const summary = buildCutoffCrossCheck(
      [{ voucherNo: 'J-2', amount: 100, isCrossPeriod: true, conclusion: '跨期' } as any],
      [{ voucherNo: 'J-2', amount: 100, isCrossPeriod: false, conclusion: '正常' } as any],
    )
    expect(summary.mismatchCount).toBe(1)
  })
})

describe('amountMismatch', () => {
  it('记账与单据金额差异≥0.02', () => {
    expect(amountMismatch({ amount: 100, documentAmount: 99 } as any)).toBe(true)
    expect(amountMismatch({ amount: 100, documentAmount: 100 } as any)).toBe(false)
  })
})
