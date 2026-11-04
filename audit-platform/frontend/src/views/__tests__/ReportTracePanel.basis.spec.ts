/**
 * 报告复核溯源页（spec voucher-workflow-linkage-lineage-closure R8.2，design §10.2）
 *
 * - 写出取数口径（试算表 / 序时账两段，原因相同只写一次）；试算表带未审列，大额交易带科目列；
 * - 查询失败时不留上一个章节的结果：后端不再把失败说成空结果，前端也不能把旧章节的数当成这次的；
 * - 失败原因经 handleApiError 说清，错误不冒出页面（浏览器实测：原先整页被全局错误边界换成英文报错）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const api = vi.hoisted(() => ({ traceSection: vi.fn(), findingsSummary: vi.fn() }))
vi.mock('@/services/commonApi', () => api)
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { projectId: 'p1' } }) }))
const errors = vi.hoisted(() => ({ handleApiError: vi.fn() }))
vi.mock('@/utils/errorHandler', () => errors)

import ReportTracePanel from '../ReportTracePanel.vue'

/** 组件事件处理 / 生命周期里没接住的错误（真实应用里会冒到全局错误边界，整页换成报错页） */
const uncaught = vi.fn()

const RESULT = {
  year: 2025,
  account_codes: ['1001', '1002'],
  note_data: { wp_code: 'E1', wp_codes: ['E1'], note_title: '五、1' },
  workpaper_data: null,
  trial_balance_data: [{ account_code: '1002', account_name: '银行存款', opening: '10.00', unadjusted: '20.00', audited: '20.00' }],
  trial_balance_basis: '2025 年度试算表，科目 1001、1002',
  top_ledger_entries: [{ voucher_no: '0001', date: '2025-03-05', account_code: '1002', debit: '5.00', credit: '0.00', summary: '收款' }],
  ledger_basis: '2025 年度当前账套序时账，按借贷差额绝对值取前 10 笔',
}

function mountPanel() {
  return mount(ReportTracePanel, {
    global: {
      plugins: [ElementPlus],
      stubs: { GtPageHeader: { template: '<div><slot name="actions" /></div>' } },
      // 不吞错误：原先这里吞掉了事件处理抛出的错误，测不出真实页面上「查询失败 → 整页换成英文报错」
      config: { errorHandler: uncaught },
    },
  })
}

async function trace(w: VueWrapper, section: string) {
  await w.get('input').setValue(section)
  await w.findAll('button').find((b) => b.text() === '溯源查询')!.trigger('click')
  await flushPromises()
}

beforeEach(() => {
  api.traceSection.mockReset()
  api.findingsSummary.mockReset().mockResolvedValue(null)
  errors.handleApiError.mockReset()
  uncaught.mockReset()
})

describe('取数口径与列', () => {
  it('两段口径都写出；试算表有未审列，大额交易有科目列', async () => {
    api.traceSection.mockResolvedValue(RESULT)
    const w = mountPanel()
    await trace(w, '五、1')
    expect(api.traceSection).toHaveBeenCalledWith('p1', '五、1')
    const basis = w.get('[data-testid="report-trace-basis"]').text()
    expect(basis).toContain('取数口径：2025 年度试算表，科目 1001、1002；2025 年度当前账套序时账')
    const headers = w.findAll('th').map((th) => th.text().trim())
    expect(headers).toContain('未审')
    expect(headers).toContain('科目')
    expect(w.text()).toContain('银行存款')
  })

  it('两段原因相同只写一次；没有口径不出提示', async () => {
    const why = '项目未设置审计年度，未取试算表与序时账'
    api.traceSection.mockResolvedValueOnce({ ...RESULT, trial_balance_data: null, top_ledger_entries: [],
      trial_balance_basis: why, ledger_basis: why })
    const w = mountPanel()
    await trace(w, '五、1')
    expect(w.get('[data-testid="report-trace-basis"]').text().split(why)).toHaveLength(2)
    api.traceSection.mockResolvedValueOnce({ ...RESULT, trial_balance_basis: '', ledger_basis: '' })
    await trace(w, '五、2')
    expect(w.find('[data-testid="report-trace-basis"]').exists()).toBe(false)
  })
})

it('查询失败不留上一个章节的结果；原因经统一错误提示说清，错误不冒出页面', async () => {
  const failure = { response: { status: 500, data: { detail: '测试注入：溯源暂不可用' } } }
  api.traceSection.mockResolvedValueOnce(RESULT).mockRejectedValueOnce(failure)
  const w = mountPanel()
  await trace(w, '五、1')
  expect(w.text()).toContain('银行存款')
  await trace(w, '五、2')
  expect(api.traceSection).toHaveBeenLastCalledWith('p1', '五、2')
  expect(w.text()).not.toContain('银行存款')
  expect(w.find('[data-testid="report-trace-basis"]').exists()).toBe(false)
  expect(errors.handleApiError).toHaveBeenCalledWith(failure, '溯源查询')
  expect(uncaught).not.toHaveBeenCalled()
  // 页面还在，可以再查
  api.traceSection.mockResolvedValueOnce(RESULT)
  await trace(w, '五、1')
  expect(w.text()).toContain('银行存款')
})

it('统一发现汇总读取失败：提示原因，溯源查询照常可用', async () => {
  const failure = { response: { status: 500, data: {} } }
  api.findingsSummary.mockReset().mockRejectedValue(failure)
  api.traceSection.mockResolvedValue(RESULT)
  const w = mountPanel()
  await flushPromises()
  expect(errors.handleApiError).toHaveBeenCalledWith(failure, '读取统一发现汇总')
  expect(uncaught).not.toHaveBeenCalled()
  await trace(w, '五、1')
  expect(w.text()).toContain('银行存款')
})
