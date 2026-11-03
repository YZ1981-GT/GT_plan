/**
 * 年审抽样口径接进抽凭流程（spec voucher-identity-writeback-and-audit-phase 任务 15，需求 7.1~7.4）
 *
 * - 抽凭请求带所选口径；不须选（返回 null）时不发该字段；重抽沿用上次口径；
 * - 后端回的口径留痕（stats.final_population）回填时写进 extraction_criteria（口径也参与幂等键）；没有就不写；
 * - 抽凭历史读出口径；
 * - chooseFinalPopulationMode：不须选 → null、须选 → 交给弹窗、读上下文失败 → null（由后端判定）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { ref } from 'vue'

vi.mock('@/utils/http', () => ({ default: { post: vi.fn(), get: vi.fn() } }))
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
  ElMessageBox: { confirm: vi.fn() },
}))
vi.mock('@/utils/eventBus', () => ({ eventBus: { emit: vi.fn(), on: vi.fn(), off: vi.fn() } }))

import http from '@/utils/http'
import { ElMessage } from 'element-plus'
import { useVoucherSampling } from '../composables/useVoucherSampling'
import {
  chooseFinalPopulationMode,
  parsePhaseContext,
  type FinalPopulationModePicker,
} from '../composables/useFinalPopulationMode'
import type { Phase } from '../composables/useSamplingAlgorithms'

const mockHttp = http as unknown as { post: ReturnType<typeof vi.fn>; get: ReturnType<typeof vi.fn> }
const mockMsg = ElMessage as unknown as Record<string, ReturnType<typeof vi.fn>>

const TRACE_B = {
  mode: 'full_minus_interim', interim_cutoff_date: '2025-06-30', interim_cutoff_source: 'project',
  date_start: '2025-01-01', date_end: '2025-12-31', interim_batch_count: 1, interim_sample_count: 5,
  interim_batch_line_fps: 5, interim_attach_count: 2, excluded_attach_lines: 3, unresolved_attach_count: 0,
}

function sampling() {
  return useVoucherSampling({
    projectId: ref('proj-1'), year: ref(2025), workpaperId: ref('wp-1'), accountCode: '2241',
    phase: ref<Phase>('final'), defaultMethod: 'random', wpCode: 'K1',
  })
}

function extractResponse(stats: Record<string, unknown> = {}) {
  return {
    data: {
      items: [{ id: 'l1', voucher_key: 'vk', line_fp: 'fp', voucher_no: '0003', voucher_date: '2025-08-01',
        voucher_type: 'ZZ', account_code: '2241', credit_amount: '10.00' }],
      stats: { population_count: 100, population_amount: '1000', sample_count: 1, sample_amount: '10',
        count_coverage_rate: '1.00', amount_coverage_rate: '1.00', dataset_id: 'ds-1', ...stats },
      seed_used: 7,
      cross_workpaper_duplicates: [],
    },
  }
}

const extractBodies = () => mockHttp.post.mock.calls.filter((c) => String(c[0]).includes('/voucher-extract')).map((c) => c[1])
const fillCriteria = () => mockHttp.post.mock.calls.find((c) => String(c[0]).includes('/cutoff-fill'))![1].extraction_criteria

beforeEach(() => {
  vi.clearAllMocks()
  mockHttp.post.mockReset()
  mockHttp.get.mockReset()
  mockHttp.post.mockResolvedValue({ data: { success: true } })
})

describe('抽凭请求与回填留痕带年审口径', () => {
  it('请求带口径，回填写口径与留痕；重抽沿用上次口径', async () => {
    const s = sampling()
    mockHttp.post.mockResolvedValueOnce(extractResponse({ final_population: TRACE_B }))
    await s.triggerSampling({ finalPopulationMode: 'full_minus_interim' })
    expect(extractBodies()[0].final_population_mode).toBe('full_minus_interim')
    expect(s.finalPopulation.value?.excluded_attach_lines).toBe(3)
    await s.confirmFill()
    const crit = fillCriteria()
    expect(crit.final_population_mode).toBe('full_minus_interim')
    expect(crit.final_population).toEqual(TRACE_B)

    mockHttp.post.mockResolvedValueOnce(extractResponse({ final_population: TRACE_B }))
    expect(await s.resample('样本量不足')).toBe(true)
    expect(extractBodies()[1].final_population_mode).toBe('full_minus_interim')
  })

  it('不须选口径：请求不带该字段，回填不写口径', async () => {
    const s = sampling()
    mockHttp.post.mockResolvedValueOnce(extractResponse())
    await s.triggerSampling({ finalPopulationMode: null })
    expect('final_population_mode' in extractBodies()[0]).toBe(false)
    expect(s.finalPopulation.value).toBeNull()
    await s.confirmFill()
    const crit = fillCriteria()
    expect('final_population_mode' in crit).toBe(false)
    expect('final_population' in crit).toBe(false)
  })

  it('换成不须选的抽样后，上次的留痕不带进新批次', async () => {
    const s = sampling()
    mockHttp.post.mockResolvedValueOnce(extractResponse({ final_population: TRACE_B }))
    await s.triggerSampling({ finalPopulationMode: 'full_minus_interim' })
    mockHttp.post.mockResolvedValueOnce(extractResponse())
    await s.triggerSampling({ finalPopulationMode: null })
    await s.confirmFill()
    expect('final_population' in fillCriteria()).toBe(false)
  })

  it('抽凭历史读出口径，旧记录与非法值为 null', async () => {
    const s = sampling()
    mockHttp.get.mockResolvedValueOnce({ data: [
      { id: 'a', extraction_criteria: { phase: 'final', final_population_mode: 'remaining' } },
      { id: 'b', extraction_criteria: { phase: 'preliminary' } },
      { id: 'c', extraction_criteria: { phase: 'final', final_population_mode: 'remaining_period' } },
    ] })
    await s.loadHistory()
    expect(s.historyList.value.map((h) => h.finalPopulationMode)).toEqual(['remaining', null, null])
  })
})

describe('chooseFinalPopulationMode', () => {
  const ctxBody = (over: Record<string, unknown> = {}) => ({ data: {
    current_audit_phase: 'final', interim_cutoff_date: '2025-06-30', effective_cutoff_date: '2025-06-30',
    cutoff_source: 'project', audit_period_end: '2025-12-31', interim_batch_count: 1, interim_sample_count: 5,
    interim_line_count: 5, interim_attach_count: 2, last_final_population_mode: null,
    requires_final_population_mode: true, default_final_population_mode: 'full_minus_interim', ...over,
  } })
  const picker = (answer: 'remaining' | 'full_minus_interim' | false): FinalPopulationModePicker & { open: ReturnType<typeof vi.fn> } =>
    ({ open: vi.fn().mockResolvedValue(answer) })

  it('须选口径时交给弹窗，返回所选口径；请求带底稿与年度', async () => {
    mockHttp.get.mockResolvedValueOnce(ctxBody())
    const p = picker('remaining')
    expect(await chooseFinalPopulationMode('proj-1', 'wp-1', 2025, p)).toBe('remaining')
    expect(mockHttp.get.mock.calls[0][0]).toBe('/api/projects/proj-1/sampling/phase-context')
    expect(mockHttp.get.mock.calls[0][1].params).toEqual({ wp_id: 'wp-1', year: 2025 })
    expect(p.open.mock.calls[0][0]).toMatchObject({ interimAttachCount: 2, effectiveCutoffDate: '2025-06-30', requiresMode: true })
  })

  it('用户取消 → false；不须选 → null 且不弹窗', async () => {
    mockHttp.get.mockResolvedValueOnce(ctxBody())
    expect(await chooseFinalPopulationMode('proj-1', 'wp-1', 2025, picker(false))).toBe(false)
    mockHttp.get.mockResolvedValueOnce(ctxBody({ requires_final_population_mode: false }))
    const p = picker('remaining')
    expect(await chooseFinalPopulationMode('proj-1', 'wp-1', null, p)).toBeNull()
    expect(p.open).not.toHaveBeenCalled()
    expect(mockHttp.get.mock.calls[1][1].params).toEqual({ wp_id: 'wp-1' })
  })

  it('读上下文失败：提示后按 null 继续（须选时由后端 422 拦下）', async () => {
    mockHttp.get.mockRejectedValueOnce(new Error('network'))
    const p = picker('remaining')
    expect(await chooseFinalPopulationMode('proj-1', 'wp-1', 2025, p)).toBeNull()
    expect(p.open).not.toHaveBeenCalled()
    expect(mockMsg.warning).toHaveBeenCalled()
  })

  it('parsePhaseContext：信封与缺省值', () => {
    const ctx = parsePhaseContext({ current_audit_phase: 'final', requires_final_population_mode: true,
      last_final_population_mode: 'x', default_final_population_mode: 'remaining', interim_batch_count: '3' })
    expect(ctx).toMatchObject({ phase: 'final', requiresMode: true, lastMode: null, defaultMode: 'remaining',
      interimBatchCount: 3, interimAttachCount: 0, cutoffSource: null })
    expect(parsePhaseContext(null)).toMatchObject({ phase: 'final', requiresMode: false, defaultMode: 'full_minus_interim' })
  })
})

describe('引擎接线（源码）', () => {
  const src = readFileSync(resolve(process.cwd(), 'src/components/workpaper/voucher-sampling/GtVoucherSamplingEngine.vue'), 'utf-8')

  it('执行抽样先问口径：配置弹窗的执行走 runSampling，取消不抽；口径弹窗挂在引擎上', () => {
    expect(src).toContain('@execute="runSampling"')
    expect(src).not.toContain('@execute="triggerSampling"')
    expect(src).toMatch(/<FinalPopulationModeDialog ref="populationModeDialog"\s*\/>/)
    const start = src.indexOf('async function runSampling')
    const body = src.slice(start, src.indexOf('\n}\n', start))
    expect(body).toContain('chooseFinalPopulationMode(props.projectId, props.workpaperId, props.year, populationModeDialog.value)')
    expect(body).toContain('if (mode !== false) await triggerSampling({ finalPopulationMode: mode })')
  })
})
