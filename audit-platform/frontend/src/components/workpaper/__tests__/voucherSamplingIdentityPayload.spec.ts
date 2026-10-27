/**
 * 抽凭 / 截止测试回填留痕带样本身份（spec voucher-identity-writeback-and-audit-phase 任务 5，需求 2.4 / 2.6）
 *
 * - 抽凭引擎：样本带后端给的 voucher_key / line_fp，回填日志写 filled_line_fps / filled_voucher_keys；
 *   有一行缺指纹就整批不发指纹（后端退回按凭证键整张排除）；
 * - 跨底稿重复按凭证键剔除：别的底稿抽的是 2 月的 ZZ-0003，1 月的 FY-0003 不能跟着被剔；
 * - 旧记录按凭证号排除、已抽分录找不到时提示；抽凭历史标「旧记录按凭证号排除」；
 * - 截止测试：cutoff-fill 顶层带 filled_voucher_keys / filled_line_fps。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { post: vi.fn(), get: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))
vi.mock('@/utils/eventBus', () => ({ eventBus: { emit: vi.fn(), on: vi.fn(), off: vi.fn() } }))

import http from '@/utils/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useVoucherSampling, type VoucherSamplingOptions } from '../composables/useVoucherSampling'
import { useCutoffAutoSampling } from '../composables/useCutoffAutoSampling'
import type { Phase } from '../composables/useSamplingAlgorithms'

const mockHttp = http as unknown as { post: ReturnType<typeof vi.fn>; get: ReturnType<typeof vi.fn> }
const mockMsg = ElMessage as unknown as Record<string, ReturnType<typeof vi.fn>>
const mockBox = ElMessageBox as unknown as { confirm: ReturnType<typeof vi.fn> }

const VK_FY = '["2025","001","2025-01-07","FY","0003"]'
const VK_ZZ = '["2025","001","2025-02-07","ZZ","0003"]'
const FP_FY = '["2025","001","2025-01-07","FY","0003","1122","D","100.00",0]'
const FP_ZZ = '["2025","001","2025-02-07","ZZ","0003","1122","D","50.00",0]'

function options(over?: Partial<VoucherSamplingOptions>): VoucherSamplingOptions {
  return {
    projectId: ref('proj-1'), year: ref(2025), workpaperId: ref('wp-1'), accountCode: '1122',
    phase: ref<Phase>('final'), defaultMethod: 'random', wpCode: 'D2', ...over,
  }
}

function item(vk: string, fp: string | null, date: string, type: string, amount: string) {
  return { id: `id-${type}`, voucher_key: vk, line_fp: fp, voucher_no: '0003', voucher_date: date,
    voucher_type: type, account_code: '1122', debit_amount: amount }
}

function extractResponse(items: any[], stats: Record<string, unknown> = {}, dups: any[] = []) {
  return {
    data: {
      items,
      stats: { population_count: 10, population_amount: '1000', sample_count: items.length, sample_amount: '150',
        count_coverage_rate: '20.00', amount_coverage_rate: '15.00', dataset_id: 'ds-1', ...stats },
      seed_used: 7,
      cross_workpaper_duplicates: dups,
    },
  }
}

function fillCall() {
  return mockHttp.post.mock.calls.find((c) => String(c[0]).includes('/sampling/cutoff-fill'))!
}

beforeEach(() => {
  vi.clearAllMocks()
  mockHttp.post.mockReset()
  mockHttp.get.mockReset()
  mockHttp.post.mockResolvedValue({ data: { success: true } })
})

describe('抽凭引擎回填留痕', () => {
  it('样本带凭证键与分录指纹，回填日志写 filled_line_fps / filled_voucher_keys（凭证号照发给旧后端）', async () => {
    const s = useVoucherSampling(options())
    mockHttp.post.mockResolvedValueOnce(extractResponse([
      item(VK_FY, FP_FY, '2025-01-07', 'FY', '100.00'), item(VK_ZZ, FP_ZZ, '2025-02-07', 'ZZ', '50.00'),
    ]))
    await s.triggerSampling()
    expect(s.sampledVouchers.value.map((v) => [v.voucherKey, v.lineFp])).toEqual([[VK_FY, FP_FY], [VK_ZZ, FP_ZZ]])
    await s.confirmFill([])
    const crit = fillCall()[1].extraction_criteria
    expect(crit.filled_line_fps).toEqual([FP_FY, FP_ZZ])
    expect(crit.filled_voucher_keys).toEqual([VK_FY, VK_ZZ])
    expect(crit.filled_voucher_nos).toEqual(['0003'])
  })

  it('有一行缺指纹（后端补全失败）就整批不发指纹，凭证键照发', async () => {
    const s = useVoucherSampling(options())
    mockHttp.post.mockResolvedValueOnce(extractResponse([
      item(VK_FY, FP_FY, '2025-01-07', 'FY', '100.00'), item(VK_ZZ, null, '2025-02-07', 'ZZ', '50.00'),
    ]))
    await s.triggerSampling()
    await s.confirmFill([])
    const crit = fillCall()[1].extraction_criteria
    expect(crit.filled_line_fps).toEqual([])
    expect(crit.filled_voucher_keys).toEqual([VK_FY, VK_ZZ])
  })

  it('跨底稿重复按凭证键剔除：同号的另一张凭证保留', async () => {
    const s = useVoucherSampling(options())
    mockHttp.post.mockResolvedValueOnce(extractResponse(
      [item(VK_FY, FP_FY, '2025-01-07', 'FY', '100.00'), item(VK_ZZ, FP_ZZ, '2025-02-07', 'ZZ', '50.00')],
      {},
      [{ voucher_key: VK_ZZ, voucher_no: '0003', voucher_date: '2025-02-07', voucher_type: 'ZZ', wp_codes: ['K1'],
        batch_count: 1, legacy: false }],
    ))
    mockBox.confirm.mockRejectedValueOnce('cancel') // 剔除重复项
    await s.triggerSampling()
    expect(s.sampledVouchers.value.map((v) => v.voucherKey)).toEqual([VK_FY])
    expect(String(mockBox.confirm.mock.calls[0][0])).toContain('2025-02-07 ZZ-0003（已被 K1 抽取）')
    await s.confirmFill([])
    expect(fillCall()[1].extraction_criteria.duplicate_voucher_keys).toEqual([VK_ZZ])
  })

  it('旧登记只有凭证号的重复项如实说明', () => {
    const s = useVoucherSampling(options())
    const text = s.buildDuplicateSummary([{ voucherNo: '0003', voucherKey: VK_FY, voucherDate: '2025-01-07',
      voucherType: 'FY', legacy: true, wpCodes: ['D3'], batchCount: 1 }])
    expect(text).toBe('2025-01-07 FY-0003（已被 D3 抽取；对方是只记凭证号的旧登记，可能是同号的另一张）')
  })

  it('旧记录按凭证号排除、已抽分录找不到：抽样后各提示一次', async () => {
    const s = useVoucherSampling(options())
    mockHttp.post.mockResolvedValueOnce(extractResponse(
      [item(VK_FY, FP_FY, '2025-01-07', 'FY', '100.00')], { legacy_exclusion: true, unresolved_excluded_lines: 2 },
    ))
    await s.triggerSampling()
    const warned = mockMsg.warning.mock.calls.map((c) => String(c[0]))
    expect(warned.some((m) => m.includes('按凭证号整张排除'))).toBe(true)
    expect(warned.some((m) => m.includes('有 2 笔已抽分录在当前账套里找不到'))).toBe(true)
  })

  it('抽凭历史标出旧记录', async () => {
    const s = useVoucherSampling(options())
    mockHttp.get.mockResolvedValueOnce({ data: [
      { id: 'a', extraction_criteria: { phase: 'final' }, legacy_exclusion: true },
      { id: 'b', extraction_criteria: { phase: 'final' }, legacy_exclusion: false },
    ] })
    await s.loadHistory()
    expect(s.historyList.value.map((h) => h.legacyExclusion)).toEqual([true, false])
  })
})

describe('截止测试回填留痕', () => {
  it('cutoff-fill 顶层带凭证键与分录指纹', async () => {
    const c = useCutoffAutoSampling({ projectId: ref('proj-1'), year: ref(2025), workpaperId: ref('wp-1'),
      accountCode: '1122', cutoffDirection: 'post_cutoff' })
    mockHttp.post.mockResolvedValueOnce({ data: { items: [
      item(VK_FY, FP_FY, '2025-12-30', 'FY', '100.00'), item(VK_ZZ, FP_ZZ, '2026-01-03', 'ZZ', '50.00'),
    ], stats: { total_count: 2 } } })
    await c.triggerExtraction()
    expect(c.extractedVouchers.value.map((v) => v.voucherKey)).toEqual([VK_FY, VK_ZZ])
    await c.confirmFill()
    const body = fillCall()[1]
    expect(body.filled_voucher_keys).toEqual([VK_FY, VK_ZZ])
    expect(body.filled_line_fps).toEqual([FP_FY, FP_ZZ])
    expect(body.filled_voucher_nos).toEqual(['0003', '0003'])
  })
})
