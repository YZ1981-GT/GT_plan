/**
 * 报表分析「审定」未读完就切「对比」：旧请求被 GET 去重取消后晚到的错误不得盖住对比表
 * （spec citar-cell-source-hover 批 5 浏览器实测抓到：页面停在「读取报表失败」）。
 */
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const api = vi.hoisted(() => ({ fetchStatement: vi.fn() }))

vi.mock('../useCitarReportAnalysis', async (orig) => {
  const real = await orig<typeof import('../useCitarReportAnalysis')>()
  return { ...real, fetchStatement: api.fetchStatement }
})
vi.mock('../useCitarReportGenerate', async () => {
  const { ref } = await import('vue')
  return { useCitarReportGenerate: () => ({ generating: ref(false), prerequisite: ref(null), generate: vi.fn() }) }
})
vi.mock('../useCitarProject', () => ({ fmtMoney: (v: unknown) => (v == null ? '' : String(v)) }))
vi.mock('../useCitarSourceCard', async () => {
  const { ref } = await import('vue')
  return {
    useCitarSourceCard: () => ({
      card: ref({ visible: false }), cardLabel: ref(''), open: vi.fn(), onCardEnter: vi.fn(), onCardLeave: vi.fn(), invalidate: vi.fn(),
    }),
  }
})
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn().mockResolvedValue({ cells: {} }) } }))

import CitarStatementView from '../components/CitarStatementView.vue'

const ROW = {
  row_code: 'BS-002', row_name: '货币资金', indent_level: 1, is_total_row: false,
  current_period_amount: '100', prior_period_amount: '80', source_accounts: { generated: true },
} as any

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

describe('CitarStatementView 读取时序', () => {
  it('旧「审定」请求在切「对比」后才失败：不显示「读取报表失败」，对比表照常出现', async () => {
    const first = deferred<any[]>()
    api.fetchStatement.mockReset()
    api.fetchStatement
      .mockImplementationOnce(() => first.promise) // 首次进入：审定
      .mockResolvedValueOnce([ROW]) // 对比：审定
      .mockResolvedValueOnce([{ ...ROW, current_period_amount: '90' }]) // 对比：未审

    const w = mount(CitarStatementView, {
      props: { kind: 'balance_sheet', projectId: 'p1', year: 2025, entityName: '甲公司' },
      global: { stubs: { CitarReportTable: true, CitarEquityMatrix: true, CitarSourceCard: true } },
    })
    await flushPromises()

    await w.findAll('.ra-seg__btn').find(b => b.text() === '对比')!.trigger('click')
    await flushPromises()
    expect(w.findAll('tbody tr')).toHaveLength(1)

    // 旧请求此刻才因被取消而失败
    first.reject(Object.assign(new Error('canceled'), { code: 'ERR_CANCELED' }))
    await flushPromises()

    expect(w.text()).not.toContain('读取报表失败')
    expect(w.text()).not.toContain('正在读取报表')
    expect(w.findAll('tbody tr')).toHaveLength(1)
    expect(w.find('[data-src="adj|BS-002"]').text()).toBe('10')
  })
})
