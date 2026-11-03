/**
 * 两阶段合并评价的前端部分（spec voucher-identity-writeback-and-audit-phase 任务 16，需求 7.5 / 7.6）
 *
 * - 样本实际错报合计 E：推断时与推断同一批样本算（未检查样本按处置改写：视同偏差按账面金额、已实施替代程序按
 *   录入值；未选处置的不计），取绝对值（低估不抵消高估），随评价载荷发出；
 * - 回读评价带回 E（确认结论等动作原样重存评价，漏了就把库里的 E 抹掉），旧评价没有 E 时发 null；
 * - parsePhaseEvaluation / loadPhaseEvaluation：只解析后端结果，不在前端算合并公式；
 * - 引擎在评价卡片里挂合并评价面板：批次取卡片显示的批次，年审阶段且有落库批次才读。
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
import { useVoucherSampling } from '../composables/useVoucherSampling'
import {
  computeSampleErrorTotal,
  loadPhaseEvaluation,
  parsePhaseEvaluation,
} from '../composables/samplingPhaseEvaluation'
import type { Phase, SampledVoucher } from '../composables/useSamplingAlgorithms'

const mockHttp = http as unknown as { post: ReturnType<typeof vi.fn>; get: ReturnType<typeof vi.fn> }

function sampling() {
  return useVoucherSampling({
    projectId: ref('proj-1'), year: ref(2025), workpaperId: ref('wp-1'), accountCode: '2241',
    phase: ref<Phase>('preliminary'), defaultMethod: 'random', wpCode: 'K1',
  })
}

function voucher(over: Partial<SampledVoucher>): SampledVoucher {
  return {
    voucherNo: 'V', voucherDate: '2025-03-01', summary: '', debitAmount: '1000.00', creditAmount: null,
    accountCode: '2241', accountName: '其他应付款', counterpartAccount: '', counterpartAccountName: null,
    isMultiAccount: false, voucherEntries: [], voucherType: 'ZZ', accountingPeriod: 3,
    checkResult: 'Y', abnormal: false, remark: '', selected: true, phase: 'preliminary', editTrail: [], ...over,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockHttp.post.mockReset()
  mockHttp.get.mockReset()
  mockHttp.post.mockResolvedValue({ data: { success: true } })
})

describe('样本实际错报合计 E', () => {
  it('computeSampleErrorTotal：绝对值之和，空与非法按 0，保留两位', () => {
    expect(computeSampleErrorTotal([
      voucher({ actualMisstatement: '300' }), voucher({ actualMisstatement: '-50.25' }),
      voucher({ actualMisstatement: '' }), voucher({}), voucher({ actualMisstatement: 'abc' }),
    ])).toBe('350.25')
    expect(computeSampleErrorTotal([])).toBe('0.00')
  })

  it('推断时与推断同一批样本算 E：视同偏差按账面、替代程序按录入值、未选处置不计；随载荷发出', () => {
    const s = sampling()
    s.sampledVouchers.value = [
      voucher({ voucherNo: 'A', checkResult: 'N', actualMisstatement: '300' }),
      voucher({ voucherNo: 'B', checkResult: 'N', actualMisstatement: '-50.25' }),
      voucher({ voucherNo: 'C', checkResult: '', debitAmount: '1000.00' }),
      voucher({ voucherNo: 'D', checkResult: '', debitAmount: '777.00', actualMisstatement: '777' }),
      voucher({ voucherNo: 'E', checkResult: '', debitAmount: '500.00', actualMisstatement: '9' }),
    ]
    s.setUncheckedDisposition('C', 'treated_as_deviation')
    s.setUncheckedDisposition('E', 'alternative_performed', '已核对银行流水')
    s.inferMisstatement()
    expect(s.misstatementResult.value?.sampleErrorTotal).toBe('1359.25')
    expect(s.buildEvaluationPayload()!.sample_error_total).toBe('1359.25')
  })

  it('回读评价带回 E，原样重存时仍发出；旧评价没有 E 发 null', async () => {
    const s = sampling()
    mockHttp.get.mockResolvedValueOnce({ data: [{ id: 'log-1', batch_id: 'b-1', evaluation: {
      projected: '100.00', upper_limit: '300.00', sample_error_total: '80.00', conclusion_code: 'undetermined' } }] })
    expect(await s.loadLatestEvaluation()).toBe(true)
    expect(s.misstatementResult.value?.sampleErrorTotal).toBe('80.00')
    await s.persistEvaluation()
    const body = mockHttp.post.mock.calls.find((c) => String(c[0]).includes('/voucher-evaluation'))![1]
    expect(body.evaluation.sample_error_total).toBe('80.00')
    expect(body.log_id).toBe('log-1')

    const old = sampling()
    mockHttp.get.mockResolvedValueOnce({ data: [{ id: 'log-0', evaluation: { projected: '1.00', upper_limit: '2.00' } }] })
    await old.loadLatestEvaluation()
    expect(old.misstatementResult.value).not.toHaveProperty('sampleErrorTotal')
    expect(old.buildEvaluationPayload()!.sample_error_total).toBeNull()
  })
})

describe('parsePhaseEvaluation / loadPhaseEvaluation', () => {
  const AVAILABLE = {
    available: true, applicable: true, mode: 'full_minus_interim', final_log_id: 'log-f',
    interim: [{ seq: 1, log_id: 'p1', projected: '5000.00', upper_limit: '9000.00', sample_error_total: '80.00' }],
    combined: {
      mode: 'full_minus_interim', interim_component: '80.00', interim_upper_component: '80.00',
      final_projected: '1000.00', final_upper_limit: '2500.00', projected: '1080.00', upper_limit: '2580.00',
      tolerable_misstatement: '5000.00', conclusion_code: 'acceptable', conclusion_message: '全年合并（…）可以接受',
      scope_consistent: false, notes: ['两阶段科目范围不一致，全年合并结果仅供参考'],
    },
  }

  it('可用：各分量原样取后端（不在前端重算）', () => {
    const v = parsePhaseEvaluation(AVAILABLE)
    expect(v).toMatchObject({ available: true, applicable: true, reason: '', mode: 'full_minus_interim' })
    expect(v.combined).toMatchObject({ interimComponent: '80.00', projected: '1080.00', upperLimit: '2580.00',
      conclusionCode: 'acceptable', conclusionMessage: '全年合并（…）可以接受', scopeConsistent: false })
    expect(v.interim).toEqual([{ seq: 1, projected: '5000.00', upperLimit: '9000.00', sampleErrorTotal: '80.00' }])
  })

  it('不可用分两种：需要但算不出（显示原因）/ 本来就不需要（不显示）；非法结论码按未定', () => {
    expect(parsePhaseEvaluation({ available: false, applicable: true, reason_code: 'missing_sample_error_total',
      reason: '第 1 个预审批次缺少实际错报合计' })).toMatchObject({ available: false, applicable: true,
      reason: '第 1 个预审批次缺少实际错报合计', combined: null, interim: [] })
    expect(parsePhaseEvaluation({ available: false, applicable: false, reason: '该批次不是年审批次' }))
      .toMatchObject({ available: false, applicable: false })
    expect(parsePhaseEvaluation(null)).toMatchObject({ available: false, applicable: false, combined: null })
    const bad = parsePhaseEvaluation({ ...AVAILABLE, combined: { ...AVAILABLE.combined, conclusion_code: 'ok' } })
    expect(bad.combined?.conclusionCode).toBe('undetermined')
    expect(parsePhaseEvaluation({ ...AVAILABLE, mode: 'x' }).available).toBe(false)
  })

  it('请求带底稿；给了批次才带 log_id；静默（错误由面板自己提示）', async () => {
    mockHttp.get.mockResolvedValue({ data: { data: AVAILABLE } })
    expect((await loadPhaseEvaluation('proj-1', 'wp-1', 'log-f')).available).toBe(true)
    expect(mockHttp.get.mock.calls[0][0]).toBe('/api/projects/proj-1/sampling/phase-evaluation')
    expect(mockHttp.get.mock.calls[0][1]).toMatchObject({ params: { wp_id: 'wp-1', log_id: 'log-f' }, _silent: true })
    await loadPhaseEvaluation('proj-1', 'wp-1', null)
    expect(mockHttp.get.mock.calls[1][1].params).toEqual({ wp_id: 'wp-1' })
  })
})

describe('引擎接线（源码）', () => {
  const src = readFileSync(resolve(process.cwd(), 'src/components/workpaper/voucher-sampling/GtVoucherSamplingEngine.vue'), 'utf-8')

  it('批量核查按钮零参数调用：不能把 PointerEvent 当核查结果写进每一行；表头 change 仍传选择值', () => {
    expect(src).toContain('@click="() => applyBatchCheckResult()"')
    expect(src).not.toContain('@click="applyBatchCheckResult"')
    expect(src).toContain('@change="(val: CheckResult) => { if (val) applyBatchCheckResult(val) }"')
  })

  it('合并评价面板挂在评价卡片里：批次取卡片显示的批次，年审阶段且有落库批次才读，评价保存 / 回填后重读', () => {
    const card = src.slice(src.indexOf('class="misstatement-card"'), src.indexOf('class="a13-push-bar"'))
    const tag = card.slice(card.indexOf('<CombinedPhaseEvaluation'), card.indexOf('/>', card.indexOf('<CombinedPhaseEvaluation')))
    expect(tag).toContain(':log-id="loadedFromBatch?.logId ?? null"')
    expect(tag).toContain(':enabled="projectPhase !== \'preliminary\' && !!(loadedFromBatch || filledBatchId)"')
    expect(tag).toContain(':refresh-key="`${filledBatchId ?? \'\'}|${loadedFromBatch?.evaluatedAt ?? \'\'}`"')
    expect(tag).toContain(':project-id="props.projectId"')
    expect(tag).toContain(':workpaper-id="props.workpaperId"')
  })
})
