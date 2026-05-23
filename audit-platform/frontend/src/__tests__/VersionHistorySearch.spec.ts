/**
 * VersionHistorySearch 组件测试
 *
 * Validates: proposal-remaining-18 §三 S-4，task 5.4
 *  - 输入关键字 + 500ms debounce 调用 GET /api/working-papers/{wp_id}/versions/search
 *  - 短关键字（< minLength）不触发请求
 *  - 连续输入 5 次只触发 1 次请求
 *  - 渲染结果列表（trigger event tag + sheet!cellRef + value 截断）
 *  - 点击结果 emit `jump` 事件携带 versionId/sheet/cellRef
 *  - 切换 wpId 清空关键字与结果
 *  - clear 按钮清空状态且不再请求
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('@/utils/errorHandler', () => ({
  handleApiError: vi.fn(),
}))

import VersionHistorySearch from '@/components/workpaper/VersionHistorySearch.vue'
import { api } from '@/services/apiProxy'

const stubs = {
  'el-input': {
    props: ['modelValue', 'placeholder'],
    emits: ['update:modelValue', 'input', 'clear'],
    template: `
      <div class="el-input">
        <input
          :value="modelValue"
          :placeholder="placeholder"
          data-testid="vh-search-input"
          @input="$emit('update:modelValue', $event.target.value); $emit('input', $event.target.value)"
        />
        <button class="el-input__clear" @click="$emit('update:modelValue', ''); $emit('clear')">x</button>
      </div>
    `,
  },
  'el-empty': {
    props: ['description'],
    template: '<div class="el-empty" :data-desc="description">{{ description }}</div>',
  },
  'el-tag': {
    template: '<span class="el-tag" :class="$attrs.type"><slot /></span>',
  },
}

const sampleHits = [
  {
    version_id: 'snap-1',
    trigger_event: 'sign',
    snapshot_at: '2026-05-15T10:00:00',
    sheet: 'Sheet1',
    cell_ref: 'B12',
    value: '应收账款 1,234.56',
    field: 'formula_value',
  },
  {
    version_id: 'snap-2',
    trigger_event: 'review',
    snapshot_at: '2026-05-10T09:00:00',
    sheet: 'Sheet1',
    cell_ref: 'B12',
    value: '应收账款 1,000.00',
    field: 'formula_value',
  },
  {
    version_id: 'current',
    trigger_event: 'current',
    snapshot_at: '2026-05-20T15:00:00',
    sheet: 'Sheet1',
    cell_ref: 'B12',
    value: '应收账款 当前值',
    field: 'cell',
  },
]

describe('VersionHistorySearch', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.clearAllMocks()
    vi.mocked(api.get).mockResolvedValue({
      wp_id: 'wp-1',
      query: '应收账款',
      total: sampleHits.length,
      results: sampleHits,
    })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  function factory(props: Partial<{ wpId: string; debounceMs: number; minLength: number }> = {}) {
    return mount(VersionHistorySearch, {
      props: {
        wpId: 'wp-1',
        debounceMs: 500,
        minLength: 1,
        ...props,
      },
      global: { stubs },
    })
  }

  async function typeKeyword(wrapper: any, keyword: string) {
    const input = wrapper.find('input[data-testid="vh-search-input"]')
    await input.setValue(keyword)
  }

  it('does not call API when keyword is empty', async () => {
    factory()
    await vi.advanceTimersByTimeAsync(1000)
    expect(api.get).not.toHaveBeenCalled()
  })

  it('does not call API when keyword shorter than minLength', async () => {
    const wrapper = factory({ minLength: 3 })
    await typeKeyword(wrapper, 'ab')
    await vi.advanceTimersByTimeAsync(1000)
    expect(api.get).not.toHaveBeenCalled()
  })

  it('calls API once after 500ms debounce when keyword is valid', async () => {
    const wrapper = factory()
    await typeKeyword(wrapper, '应收账款')

    // 尚未到 500ms
    await vi.advanceTimersByTimeAsync(400)
    expect(api.get).not.toHaveBeenCalled()

    // 越过 500ms
    await vi.advanceTimersByTimeAsync(150)
    await flushPromises()

    expect(api.get).toHaveBeenCalledTimes(1)
    const [url, config] = vi.mocked(api.get).mock.calls[0]
    expect(url).toBe('/api/working-papers/wp-1/versions/search')
    expect(config?.params).toEqual({ q: '应收账款', limit: 100 })
  })

  it('debounces 5 rapid keystrokes into a single API call', async () => {
    const wrapper = factory()
    for (let i = 1; i <= 5; i++) {
      await typeKeyword(wrapper, '应收' + i)
      // 每次间隔 100ms（< 500ms debounce）
      await vi.advanceTimersByTimeAsync(100)
    }
    // 此时已过 500ms 但每次输入重置 timer，实际未触发
    expect(api.get).not.toHaveBeenCalled()

    // 静止越过 debounce
    await vi.advanceTimersByTimeAsync(500)
    await flushPromises()
    expect(api.get).toHaveBeenCalledTimes(1)
  })

  it('renders result rows with trigger label and sheet!cell address', async () => {
    const wrapper = factory()
    await typeKeyword(wrapper, '应收账款')
    await vi.advanceTimersByTimeAsync(550)
    await flushPromises()

    const items = wrapper.findAll('[data-testid="vh-search-item"]')
    expect(items).toHaveLength(3)

    const html = wrapper.html()
    // trigger_event 中文映射存在
    expect(html).toContain('签字')
    expect(html).toContain('提交复核')
    expect(html).toContain('当前')
    // 地址按 sheet!cell 拼接
    expect(html).toContain('Sheet1!B12')
    // value 内容渲染
    expect(html).toContain('应收账款 1,234.56')
  })

  it('emits jump event with versionId/sheet/cellRef when a result row is clicked', async () => {
    const wrapper = factory()
    await typeKeyword(wrapper, '应收账款')
    await vi.advanceTimersByTimeAsync(550)
    await flushPromises()

    const items = wrapper.findAll('[data-testid="vh-search-item"]')
    await items[0].trigger('click')

    const events = wrapper.emitted('jump')
    expect(events).toBeTruthy()
    const payload = events![0][0] as any
    expect(payload.versionId).toBe('snap-1')
    expect(payload.sheet).toBe('Sheet1')
    expect(payload.cellRef).toBe('B12')
    expect(payload.row.value).toContain('1,234.56')
  })

  it('emits results event after each successful search', async () => {
    const wrapper = factory()
    await typeKeyword(wrapper, '应收账款')
    await vi.advanceTimersByTimeAsync(550)
    await flushPromises()

    const events = wrapper.emitted('results')
    expect(events).toBeTruthy()
    const payload = events![0][0] as any
    expect(payload.total).toBe(3)
    expect(payload.results).toHaveLength(3)
  })

  it('shows empty state when no results returned', async () => {
    vi.mocked(api.get).mockResolvedValueOnce({
      wp_id: 'wp-1',
      query: 'xyz',
      total: 0,
      results: [],
    })
    const wrapper = factory()
    await typeKeyword(wrapper, 'xyz')
    await vi.advanceTimersByTimeAsync(550)
    await flushPromises()

    expect(wrapper.html()).toContain('未找到匹配结果')
    expect(wrapper.findAll('[data-testid="vh-search-item"]')).toHaveLength(0)
  })

  it('clears state when wpId changes', async () => {
    const wrapper = factory({ wpId: 'wp-1' })
    await typeKeyword(wrapper, '应收账款')
    await vi.advanceTimersByTimeAsync(550)
    await flushPromises()
    expect(wrapper.findAll('[data-testid="vh-search-item"]')).toHaveLength(3)

    // 切换底稿
    await wrapper.setProps({ wpId: 'wp-2' })
    await flushPromises()
    expect(wrapper.findAll('[data-testid="vh-search-item"]')).toHaveLength(0)
  })

  it('handles API error silently and clears results', async () => {
    vi.mocked(api.get).mockRejectedValueOnce(new Error('boom'))
    const wrapper = factory()
    await typeKeyword(wrapper, 'foo')
    await vi.advanceTimersByTimeAsync(550)
    await flushPromises()

    expect(api.get).toHaveBeenCalled()
    expect(wrapper.findAll('[data-testid="vh-search-item"]')).toHaveLength(0)
    // 默认空状态描述
    expect(wrapper.html()).toMatch(/未找到匹配结果|输入关键字搜索/)
  })
})
