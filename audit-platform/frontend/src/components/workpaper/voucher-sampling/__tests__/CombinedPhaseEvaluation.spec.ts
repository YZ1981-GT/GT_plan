/**
 * 全年合并评价面板（spec voucher-identity-writeback-and-audit-phase 任务 16，需求 7.5）
 *
 * 口径 b / a 各显示对应分量与结论（数字取后端原样）；需要但算不出 → 显示原因；本来就不需要 → 不显示；
 * 没启用不发请求；批次 / 刷新键变化重读，晚到的旧响应不覆盖新的；读失败如实提示。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'

vi.mock('@/utils/http', () => ({ default: { get: vi.fn() } }))

import http from '@/utils/http'
import CombinedPhaseEvaluation from '../CombinedPhaseEvaluation.vue'

const mockGet = (http as unknown as { get: ReturnType<typeof vi.fn> }).get

const combined = (over: Record<string, unknown> = {}) => ({
  mode: 'full_minus_interim', interim_component: '80.00', interim_upper_component: '80.00',
  final_projected: '1000.00', final_upper_limit: '2500.00', projected: '1080.00', upper_limit: '2580.00',
  tolerable_misstatement: '5000.00', conclusion_code: 'acceptable', scope_consistent: true, notes: [],
  conclusion_message: '全年合并（口径 b 全年扣除预审已检样本）：…可以接受', ...over,
})
const body = (data: unknown) => ({ data: { code: 200, message: 'ok', data } })
const AVAILABLE_B = { available: true, applicable: true, mode: 'full_minus_interim', combined: combined(),
  interim: [{ seq: 1, projected: '5000.00', upper_limit: '9000.00', sample_error_total: '80.00' }] }

const mounted: VueWrapper[] = []
afterEach(() => { mounted.splice(0).forEach((w) => w.unmount()) })
beforeEach(() => { mockGet.mockReset() })

function mountPanel(props: Record<string, unknown> = {}) {
  const w = mount(CombinedPhaseEvaluation, {
    props: { projectId: 'proj-1', workpaperId: 'wp-1', logId: 'log-f', refreshKey: 'k1', enabled: true, ...props },
    global: { plugins: [ElementPlus] },
  })
  mounted.push(w)
  return w
}
const text = (w: VueWrapper, id: string) => w.find(`[data-testid="${id}"]`).text()
// 测试环境里 <transition> 被换成 stub，el-alert 的 data-testid 落在 stub 上，类名在里面那层 div
const alertClasses = (w: VueWrapper) => w.find('[data-testid="combined-conclusion"] .el-alert').classes()

describe('CombinedPhaseEvaluation', () => {
  it('口径 b：显示预审样本实际错报、全年推断错报与上限、结论（成功色）、预审批次明细', async () => {
    mockGet.mockResolvedValueOnce(body(AVAILABLE_B))
    const w = mountPanel()
    await flushPromises()
    expect(mockGet.mock.calls[0][1].params).toEqual({ wp_id: 'wp-1', log_id: 'log-f' })
    expect(w.text()).toContain('预审样本实际错报合计')
    expect(text(w, 'combined-interim')).toBe('80.00 元')
    expect(text(w, 'combined-projected')).toBe('1080.00 元')
    expect(text(w, 'combined-upper')).toBe('2580.00 元')
    expect(alertClasses(w)).toContain('el-alert--success')
    expect(text(w, 'combined-conclusion')).toContain('可以接受')
    const table = w.find('.cpe-table').text()
    expect(table).toContain('样本实际错报合计（元）')
    expect(table).toContain('第 1 个')
    expect(table).toContain('80.00')
    expect(table).not.toContain('5,000.00') // 口径 b 不列预审推断错报
    expect(w.text()).not.toContain('仅供参考')
  })

  it('口径 a 与科目范围不一致：显示预审推断错报 / 上限两列与「仅供参考」，不可接受用错误色', async () => {
    mockGet.mockResolvedValueOnce(body({ ...AVAILABLE_B, mode: 'remaining', combined: combined({
      mode: 'remaining', interim_component: '150.00', interim_upper_component: '450.00',
      conclusion_code: 'not_acceptable', scope_consistent: false }) }))
    const w = mountPanel()
    await flushPromises()
    expect(text(w, 'combined-interim')).toBe('150.00 / 450.00 元')
    const table = w.find('.cpe-table').text()
    expect(table).toContain('推断错报（元）')
    expect(table).toContain('错报上限（元）')
    expect(table).toContain('5,000.00')
    expect(table).toContain('9,000.00')
    expect(table).not.toContain('样本实际错报合计')
    expect(w.text()).toContain('仅供参考')
    expect(alertClasses(w)).toContain('el-alert--error')
  })

  it('需要但算不出：显示后端原因；本来就不需要：整块不显示', async () => {
    mockGet.mockResolvedValueOnce(body({ available: false, applicable: true, reason_code: 'missing_sample_error_total',
      reason: '第 1 个预审批次缺少实际错报合计，请在预审批次重新保存评价' }))
    const w = mountPanel()
    await flushPromises()
    expect(text(w, 'combined-unavailable')).toContain('第 1 个预审批次缺少实际错报合计')
    expect(w.find('[data-testid="combined-projected"]').exists()).toBe(false)

    mockGet.mockResolvedValueOnce(body({ available: false, applicable: false, reason: '该批次不是年审批次' }))
    await w.setProps({ refreshKey: 'k2' })
    await flushPromises()
    expect(w.find('[data-testid="combined-phase-evaluation"]').exists()).toBe(false)
    expect(w.text()).toBe('')
  })

  it('没启用不发请求、不显示；启用后读', async () => {
    const w = mountPanel({ enabled: false })
    await flushPromises()
    expect(mockGet).not.toHaveBeenCalled()
    expect(w.text()).toBe('')
    mockGet.mockResolvedValueOnce(body(AVAILABLE_B))
    await w.setProps({ enabled: true, logId: null })
    await flushPromises()
    expect(mockGet.mock.calls[0][1].params).toEqual({ wp_id: 'wp-1' })
    expect(w.find('[data-testid="combined-phase-evaluation"]').exists()).toBe(true)
  })

  it('刷新键变化重读；晚到的旧响应不覆盖新的', async () => {
    let releaseOld: (v: unknown) => void = () => {}
    mockGet.mockImplementationOnce(() => new Promise((r) => { releaseOld = r }))
    const w = mountPanel()
    mockGet.mockResolvedValueOnce(body({ ...AVAILABLE_B, combined: combined({ projected: '2222.00' }) }))
    await w.setProps({ refreshKey: 'k2' })
    await flushPromises()
    expect(text(w, 'combined-projected')).toBe('2222.00 元')
    releaseOld(body({ ...AVAILABLE_B, combined: combined({ projected: '1111.00' }) }))
    await flushPromises()
    expect(text(w, 'combined-projected')).toBe('2222.00 元')
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  it('读失败如实提示，不当成「没有合并评价」', async () => {
    mockGet.mockRejectedValueOnce(new Error('network'))
    const w = mountPanel()
    await flushPromises()
    expect(w.find('[data-testid="combined-load-failed"]').exists()).toBe(true)
  })
})
