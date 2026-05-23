/**
 * AdjustmentImpactPreview 组件测试
 *
 * Validates: proposal-remaining-18 §二 L-2，task 2.2
 *  - 500ms debounce 生效（连续修改 5 次只调一次 API）
 *  - 渲染受影响报表行（含正负样式）
 *  - 渲染受影响底稿 tag 列表
 *  - 渲染未映射科目警告
 *  - 空 lineItems 不调 API
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

import AdjustmentImpactPreview from '@/components/adjustment/AdjustmentImpactPreview.vue'
import { api } from '@/services/apiProxy'

const stubs = {
  'el-tag': { template: '<span class="el-tag" :class="$attrs.type"><slot /></span>' },
  'el-alert': {
    template:
      '<div class="el-alert" :data-type="$attrs.type"><slot name="title">{{ $attrs.title }}</slot><slot /></div>',
  },
}

const mockResponse = {
  affected_report_rows: [
    {
      report_type: 'balance_sheet',
      row_code: 'BS-005',
      row_name: '应收账款',
      field: '当期金额',
      delta: '100000',
    },
    {
      report_type: 'income_statement',
      row_code: 'IS-008',
      row_name: '营业收入',
      field: '当期金额',
      delta: '-100000',
    },
  ],
  affected_workpapers: ['D2', 'K8'],
  unmapped_accounts: ['9999'],
}

describe('AdjustmentImpactPreview', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    vi.mocked(api.post).mockResolvedValue(mockResponse)
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  function factory(props: Partial<{ projectId: string; lineItems: any[]; year: number | null }> = {}) {
    return mount(AdjustmentImpactPreview, {
      props: {
        projectId: 'proj-1',
        lineItems: [],
        year: 2025,
        ...props,
      },
      global: { stubs },
    })
  }

  it('does not call API when lineItems is empty', async () => {
    factory({ lineItems: [] })
    // 推进 1s（远超 500ms debounce）
    await vi.advanceTimersByTimeAsync(1000)
    expect(api.post).not.toHaveBeenCalled()
  })

  it('does not call API when lineItems has account but zero amounts', async () => {
    factory({
      lineItems: [{ account_code: '1122', debit: 0, credit: 0 }],
    })
    await vi.advanceTimersByTimeAsync(1000)
    expect(api.post).not.toHaveBeenCalled()
  })

  it('calls API once after 500ms debounce when lineItems are valid', async () => {
    const wrapper = factory({
      lineItems: [{ account_code: '1122', debit: 100000, credit: 0 }],
    })
    // 尚未到 500ms
    await vi.advanceTimersByTimeAsync(400)
    expect(api.post).not.toHaveBeenCalled()

    // 到达 500ms 触发
    await vi.advanceTimersByTimeAsync(150)
    await flushPromises()
    expect(api.post).toHaveBeenCalledTimes(1)
    expect(api.post).toHaveBeenCalledWith(
      '/api/projects/proj-1/adjustments/preview-impact',
      expect.objectContaining({
        year: 2025,
        line_items: [{ account_code: '1122', debit: 100000, credit: 0 }],
      }),
    )
    wrapper.unmount()
  })

  it('debounces 5 rapid lineItems mutations into a single API call', async () => {
    const wrapper = factory({
      lineItems: [{ account_code: '1122', debit: 1000, credit: 0 }],
    })

    // 连续 5 次修改 line_items（每次间隔 50ms，远小于 500ms debounce）
    for (let i = 1; i <= 5; i++) {
      await wrapper.setProps({
        lineItems: [{ account_code: '1122', debit: 1000 + i * 100, credit: 0 }],
      })
      await vi.advanceTimersByTimeAsync(50)
    }
    // 现在已过 50*5 + 初始 = 250ms，未到 debounce
    expect(api.post).not.toHaveBeenCalled()

    // 推进剩余时间触发
    await vi.advanceTimersByTimeAsync(600)
    await flushPromises()
    expect(api.post).toHaveBeenCalledTimes(1)
    // 最终请求应包含最新值（debit=1500）
    const call = vi.mocked(api.post).mock.calls[0]
    expect(call[1]).toMatchObject({
      line_items: [{ account_code: '1122', debit: 1500, credit: 0 }],
    })
    wrapper.unmount()
  })

  it('renders affected report rows with positive/negative delta styling', async () => {
    const wrapper = factory({
      lineItems: [{ account_code: '1122', debit: 100000, credit: 0 }],
    })
    await vi.advanceTimersByTimeAsync(600)
    await flushPromises()
    await nextTick()

    const text = wrapper.text()
    expect(text).toContain('BS-005')
    expect(text).toContain('IS-008')

    // 正数 delta 含 "+" 前缀，应用 gt-aip-delta-pos 样式
    const posCells = wrapper.findAll('.gt-aip-delta-pos')
    expect(posCells.length).toBeGreaterThan(0)
    expect(posCells[0].text()).toContain('+')

    // 负数 delta 应用 gt-aip-delta-neg 样式
    const negCells = wrapper.findAll('.gt-aip-delta-neg')
    expect(negCells.length).toBeGreaterThan(0)
    expect(negCells[0].text()).toContain('-')

    wrapper.unmount()
  })

  it('renders affected workpapers as tag list', async () => {
    const wrapper = factory({
      lineItems: [{ account_code: '1122', debit: 100000, credit: 0 }],
    })
    await vi.advanceTimersByTimeAsync(600)
    await flushPromises()
    await nextTick()

    const text = wrapper.text()
    expect(text).toContain('D2')
    expect(text).toContain('K8')
    expect(text).toContain('受影响底稿')
  })

  it('renders unmapped account warning', async () => {
    const wrapper = factory({
      lineItems: [{ account_code: '9999', debit: 100, credit: 0 }],
    })
    await vi.advanceTimersByTimeAsync(600)
    await flushPromises()
    await nextTick()

    const text = wrapper.text()
    expect(text).toContain('未映射科目')
    expect(text).toContain('9999')
    // 警告 alert 类型 = warning
    const alerts = wrapper.findAll('.el-alert')
    const hasWarning = alerts.some((a) => a.attributes('data-type') === 'warning')
    expect(hasWarning).toBe(true)
  })

  it('shows empty state hint when no lineItems are calculable', async () => {
    const wrapper = factory({ lineItems: [] })
    await flushPromises()
    expect(wrapper.text()).toContain('录入科目和金额后自动预览影响范围')
  })

  it('supports legacy field names (standard_account_code/debit_amount/credit_amount)', async () => {
    const wrapper = factory({
      lineItems: [
        { standard_account_code: '1122', debit_amount: 50000, credit_amount: 0 },
      ],
    })
    await vi.advanceTimersByTimeAsync(600)
    await flushPromises()

    expect(api.post).toHaveBeenCalledTimes(1)
    const call = vi.mocked(api.post).mock.calls[0]
    expect(call[1]).toMatchObject({
      line_items: [{ account_code: '1122', debit: 50000, credit: 0 }],
    })
    wrapper.unmount()
  })
})
