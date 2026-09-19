/**
 * 跨底稿重复抽凭显式确认守卫（sampling-compliance-closure R8）
 *
 * 背景：`exclude_scope` 是二元开关 —— 开则静默剔除、关则完全不提示，两者都把本该由
 * 审计师做的判断交给了配置项。重复抽同一张凭证有时是**有意的**（不同循环从不同认定
 * 角度检查同一笔交易），有时是**样本浪费**（覆盖率虚高）→ 必须弹窗显式表态并留痕。
 *
 * Validates: Requirements 8.4, 8.5, 8.6, 8.7, 8.8
 * Properties: Property 20, Property 21
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { post: vi.fn(), get: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))
vi.mock('@/utils/eventBus', () => ({
  eventBus: { emit: vi.fn(), on: vi.fn(), off: vi.fn() },
}))

import http from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useVoucherSampling,
  type VoucherSamplingOptions,
} from '../composables/useVoucherSampling'
import type { Phase } from '../composables/useSamplingAlgorithms'

const mockHttp = http as unknown as {
  post: ReturnType<typeof vi.fn>
  get: ReturnType<typeof vi.fn>
}
const mockMsg = ElMessage as unknown as Record<string, ReturnType<typeof vi.fn>>
const mockBox = ElMessageBox as unknown as { confirm: ReturnType<typeof vi.fn> }

function makeOptions(over?: Partial<VoucherSamplingOptions>): VoucherSamplingOptions {
  return {
    projectId: ref('proj-1'),
    year: ref(2025),
    workpaperId: ref('wp-1'),
    accountCode: '1122',
    phase: ref<Phase>('final'),
    defaultMethod: 'random',
    wpCode: 'D2',
    ...over,
  }
}

/** 抽样响应：3 笔样本，其中 V-001 / V-002 被别的底稿抽过 */
function extractResponse(dups: any[] = [
  { voucher_no: 'V-001', wp_codes: ['K1', 'D3'], batch_count: 2 },
  { voucher_no: 'V-002', wp_codes: ['K1'], batch_count: 1 },
]) {
  return {
    data: {
      items: [
        { voucher_no: 'V-001', voucher_date: '2025-03-01', debit_amount: '1000' },
        { voucher_no: 'V-002', voucher_date: '2025-04-01', debit_amount: '2000' },
        { voucher_no: 'V-003', voucher_date: '2025-05-01', debit_amount: '3000' },
      ],
      stats: {
        population_count: 100,
        population_amount: '100000',
        sample_count: 3,
        sample_amount: '6000',
        count_coverage_rate: '3.00',
        amount_coverage_rate: '6.00',
        dataset_id: 'ds-1',
      },
      seed_used: 7,
      cross_workpaper_duplicates: dups,
    },
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockHttp.post.mockResolvedValue({ data: { success: true } })
})

describe('R8.4 — 无重复项时不弹框', () => {
  it('cross_workpaper_duplicates 为空数组 → 直接打开预览', async () => {
    const s = useVoucherSampling(makeOptions())
    mockHttp.post.mockResolvedValueOnce(extractResponse([]))
    await s.triggerSampling()
    expect(mockBox.confirm).not.toHaveBeenCalled()
    expect(s.previewVisible.value).toBe(true)
    expect(s.crossWpDuplicates.value).toEqual([])
    expect(s.duplicateDecision.value).toBe('none')
  })

  it('后端未返回该字段（旧版本）→ 视为无重复，不弹框（向后兼容）', async () => {
    const s = useVoucherSampling(makeOptions())
    const resp = extractResponse()
    delete (resp.data as any).cross_workpaper_duplicates
    mockHttp.post.mockResolvedValueOnce(resp)
    await s.triggerSampling()
    expect(mockBox.confirm).not.toHaveBeenCalled()
    expect(s.previewVisible.value).toBe(true)
  })
})

describe('Property 20 — 三出口与后果', () => {
  it('保留全部：样本集合不变，decision = keep_all，预览打开', async () => {
    const s = useVoucherSampling(makeOptions())
    mockHttp.post.mockResolvedValueOnce(extractResponse())
    mockBox.confirm.mockResolvedValueOnce('confirm')
    await s.triggerSampling()

    expect(mockBox.confirm).toHaveBeenCalledTimes(1)
    expect(s.sampledVouchers.value.map((v) => v.voucherNo)).toEqual([
      'V-001', 'V-002', 'V-003',
    ])
    expect(s.duplicateDecision.value).toBe('keep_all')
    expect(s.previewVisible.value).toBe(true)
  })

  it('剔除重复项：恰好移除重复凭证、其余顺序不变，decision = removed', async () => {
    const s = useVoucherSampling(makeOptions())
    mockHttp.post.mockResolvedValueOnce(extractResponse())
    mockBox.confirm.mockRejectedValueOnce('cancel') // cancelButton = 剔除重复项
    await s.triggerSampling()

    expect(s.sampledVouchers.value.map((v) => v.voucherNo)).toEqual(['V-003'])
    expect(s.duplicateDecision.value).toBe('removed')
    expect(s.previewVisible.value).toBe(true)
    expect(mockMsg.warning).toHaveBeenCalled()
  })

  it('取消（关闭/ESC）：样本清空、不打开预览、decision = none', async () => {
    const s = useVoucherSampling(makeOptions())
    mockHttp.post.mockResolvedValueOnce(extractResponse())
    mockBox.confirm.mockRejectedValueOnce('close')
    await s.triggerSampling()

    expect(s.sampledVouchers.value).toEqual([])
    expect(s.coverageStats.value).toBeNull()
    expect(s.previewVisible.value).toBe(false)
    expect(s.duplicateDecision.value).toBe('none')
  })

  it('剔除后无剩余样本 → 不打开预览并提示重抽（不留半套空样本）', async () => {
    const s = useVoucherSampling(makeOptions())
    mockHttp.post.mockResolvedValueOnce(
      extractResponse([
        { voucher_no: 'V-001', wp_codes: ['K1'], batch_count: 1 },
        { voucher_no: 'V-002', wp_codes: ['K1'], batch_count: 1 },
        { voucher_no: 'V-003', wp_codes: ['K1'], batch_count: 1 },
      ]),
    )
    mockBox.confirm.mockRejectedValueOnce('cancel')
    await s.triggerSampling()

    expect(s.sampledVouchers.value).toEqual([])
    expect(s.previewVisible.value).toBe(false)
    expect(s.coverageStats.value).toBeNull()
  })
})

describe('R8.6 — 剔除后覆盖率重算（分母不得变小）', () => {
  it('分子按剩余样本重算，分母（总体）保持不变', async () => {
    const s = useVoucherSampling(makeOptions())
    mockHttp.post.mockResolvedValueOnce(extractResponse())
    mockBox.confirm.mockRejectedValueOnce('cancel')
    await s.triggerSampling()

    const cov = s.coverageStats.value!
    // 总体不变
    expect(cov.populationCount).toBe(100)
    expect(cov.populationAmount).toBe('100000')
    // 样本只剩 V-003（3000）
    expect(cov.sampleCount).toBe(1)
    expect(cov.sampleAmount).toBe('3000.00')
    expect(cov.countCoverageRate).toBe('1.00')   // 1/100
    expect(cov.amountCoverageRate).toBe('3.00')  // 3000/100000
  })

  it('🔴 反向自检：若用剩余样本当分母，覆盖率会虚高到 100%', async () => {
    const s = useVoucherSampling(makeOptions())
    mockHttp.post.mockResolvedValueOnce(extractResponse())
    mockBox.confirm.mockRejectedValueOnce('cancel')
    await s.triggerSampling()
    const cov = s.coverageStats.value!
    expect(cov.countCoverageRate).not.toBe('100.00')
  })
})

describe('R8.7 — 处置随回填留痕落库', () => {
  it('keep_all 与重复凭证清单进 extraction_criteria', async () => {
    const s = useVoucherSampling(makeOptions())
    mockHttp.post.mockResolvedValueOnce(extractResponse())
    mockBox.confirm.mockResolvedValueOnce('confirm')
    await s.triggerSampling()
    await s.confirmFill([])

    const fill = mockHttp.post.mock.calls.find((c) =>
      String(c[0]).includes('/sampling/cutoff-fill'),
    )!
    expect(fill[1].extraction_criteria.duplicate_decision).toBe('keep_all')
    expect(fill[1].extraction_criteria.duplicate_voucher_nos).toEqual(['V-001', 'V-002'])
  })

  it('removed 亦留痕（含被剔除的凭证号，便于复核追溯）', async () => {
    const s = useVoucherSampling(makeOptions())
    mockHttp.post.mockResolvedValueOnce(extractResponse())
    mockBox.confirm.mockRejectedValueOnce('cancel')
    await s.triggerSampling()
    await s.confirmFill([])

    const fill = mockHttp.post.mock.calls.find((c) =>
      String(c[0]).includes('/sampling/cutoff-fill'),
    )!
    expect(fill[1].extraction_criteria.duplicate_decision).toBe('removed')
    expect(fill[1].extraction_criteria.duplicate_voucher_nos).toEqual(['V-001', 'V-002'])
  })

  it('无重复时 decision = none', async () => {
    const s = useVoucherSampling(makeOptions())
    mockHttp.post.mockResolvedValueOnce(extractResponse([]))
    await s.triggerSampling()
    await s.confirmFill([])
    const fill = mockHttp.post.mock.calls.find((c) =>
      String(c[0]).includes('/sampling/cutoff-fill'),
    )!
    expect(fill[1].extraction_criteria.duplicate_decision).toBe('none')
  })
})

describe('R8.4 — 弹窗文案', () => {
  it('列出凭证号与抽过它的底稿编码', () => {
    const s = useVoucherSampling(makeOptions())
    const text = s.buildDuplicateSummary([
      { voucherNo: 'V-001', wpCodes: ['K1', 'D3'], batchCount: 2 },
    ])
    expect(text).toContain('V-001')
    expect(text).toContain('K1、D3')
  })

  it('wpCodes 为空时显示「未知底稿」而非空括号', () => {
    const s = useVoucherSampling(makeOptions())
    const text = s.buildDuplicateSummary([
      { voucherNo: 'V-9', wpCodes: [], batchCount: 1 },
    ])
    expect(text).toContain('未知底稿')
  })

  it('超过 10 条截断并给出总数（避免弹窗撑爆）', () => {
    const s = useVoucherSampling(makeOptions())
    const dups = Array.from({ length: 25 }, (_, i) => ({
      voucherNo: `V-${i}`, wpCodes: ['K1'], batchCount: 1,
    }))
    const text = s.buildDuplicateSummary(dups)
    expect(text).toContain('另有 15 张')
    expect(text).toContain('共 25 张')
    expect(text.split('<br/>').length).toBe(11) // 10 行 + 1 行汇总
  })
})

describe('Property 21 — 项目级排除下不重复提示', () => {
  it("exclude_scope='project' 时后端已排除 → 无重复项 → 不弹框", async () => {
    const s = useVoucherSampling(makeOptions())
    s.config.value.excludeScope = 'project'
    mockHttp.post.mockResolvedValueOnce(extractResponse([]))
    await s.triggerSampling()

    const [, body] = mockHttp.post.mock.calls[0]
    expect(body.filters.exclude_scope).toBe('project')
    expect(mockBox.confirm).not.toHaveBeenCalled()
  })

  it('缺省 exclude_scope 为 workpaper（零回归）', async () => {
    const s = useVoucherSampling(makeOptions())
    mockHttp.post.mockResolvedValueOnce(extractResponse([]))
    await s.triggerSampling()
    const [, body] = mockHttp.post.mock.calls[0]
    expect(body.filters.exclude_scope).toBe('workpaper')
  })
})

describe('R8.8 — 重抽后状态重置', () => {
  it('新一次抽样清空上一次的重复项与处置', async () => {
    const s = useVoucherSampling(makeOptions())
    mockHttp.post.mockResolvedValueOnce(extractResponse())
    mockBox.confirm.mockResolvedValueOnce('confirm')
    await s.triggerSampling()
    expect(s.duplicateDecision.value).toBe('keep_all')

    mockHttp.post.mockResolvedValueOnce(extractResponse([]))
    await s.triggerSampling()
    expect(s.crossWpDuplicates.value).toEqual([])
    expect(s.duplicateDecision.value).toBe('none')
  })
})
