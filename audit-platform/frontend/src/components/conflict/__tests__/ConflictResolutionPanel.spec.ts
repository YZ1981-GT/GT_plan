/**
 * ConflictResolutionPanel — Task 7.4 vitest 单测
 *
 * 验证：
 * 1. mounts ok with 0 conflicts → 显示空态
 * 2. mounts ok with conflicts → 列表显示数量
 * 3. click "保留手动" → POST 调用且 resolution='keep_manual'
 * 4. click "合并" → 弹输入框 + 提交后 resolution='merge' + merge_value 透传
 * 5. API 错误时 ElMessage.error 显示
 * 6. 后端返回 422 时显示中文 error
 * 7. resolve 成功后 emit 'resolved' 事件
 */

import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { nextTick } from 'vue'

const { mockGet, mockPost, mockMessage, mockHandleApiError } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockMessage: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
  mockHandleApiError: vi.fn(),
}))

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
  },
}))

vi.mock('@/utils/errorHandler', () => ({
  handleApiError: (...args: any[]) => mockHandleApiError(...args),
}))

vi.mock('element-plus', async () => {
  const actual: any = await vi.importActual('element-plus')
  return {
    ...actual,
    ElMessage: mockMessage,
  }
})

import ConflictResolutionPanel from '../ConflictResolutionPanel.vue'

const SAMPLE_CONFLICT = {
  id: 'c-1',
  source_module: 'workpaper',
  source_id: 's-1',
  target_module: 'disclosure',
  target_id: 't-1',
  target_field: 'narrative_p3',
  upstream_value: '新值',
  manual_value: '原值',
  status: 'pending',
  created_at: '2026-05-27T10:00:00',
}

function makePanel(props: Record<string, any> = {}) {
  return mount(ConflictResolutionPanel, {
    props: { projectId: 'p1', modelValue: true, ...props },
    global: {
      stubs: {
        // 把 el-drawer 内容 inline 渲染（不走 teleport）
        'el-drawer': {
          template: '<div v-if="modelValue"><slot /></div>',
          props: ['modelValue', 'title', 'direction', 'size', 'appendToBody', 'beforeClose'],
        },
        'el-empty': {
          template: '<div class="el-empty"><slot /><span>{{ description }}</span></div>',
          props: ['description'],
        },
        'el-button': {
          template: '<button :disabled="loading" @click="$emit(\'click\', $event)"><slot /></button>',
          props: ['type', 'loading', 'size'],
          emits: ['click'],
        },
        'el-input': {
          template: '<textarea :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
          props: ['modelValue', 'type', 'rows', 'placeholder'],
          emits: ['update:modelValue'],
        },
      },
    },
  })
}

describe('ConflictResolutionPanel', () => {
  beforeEach(() => {
    mockGet.mockReset()
    mockPost.mockReset()
    mockMessage.error.mockReset()
    mockMessage.success.mockReset()
    mockMessage.warning.mockReset()
    mockHandleApiError.mockReset()
  })

  it('0 conflicts → 显示空态', async () => {
    mockGet.mockResolvedValue({ count: 0, items: [] })
    const wrapper = makePanel()
    await flushPromises()

    expect(mockGet).toHaveBeenCalledWith('/api/projects/p1/conflicts/pending')
    expect(wrapper.find('.gt-conflict-panel__empty').exists()).toBe(true)
    expect(wrapper.find('.gt-conflict-panel__list').exists()).toBe(false)
  })

  it('mounts ok with conflicts → 列表显示数量', async () => {
    mockGet.mockResolvedValue({
      count: 2,
      items: [SAMPLE_CONFLICT, { ...SAMPLE_CONFLICT, id: 'c-2', target_field: 'amount' }],
    })
    const wrapper = makePanel()
    await flushPromises()

    expect(wrapper.find('.gt-conflict-panel__list').exists()).toBe(true)
    expect(wrapper.findAll('.gt-conflict-panel__item').length).toBe(2)
    // 列表标题包含计数
    expect(wrapper.find('.gt-conflict-panel__list-title').text()).toContain('2')
    // 默认选中第一条
    expect(wrapper.find('.gt-conflict-panel__detail').exists()).toBe(true)
  })

  it('click "保留手动" → POST resolve 并传 keep_manual', async () => {
    mockGet.mockResolvedValue({ count: 1, items: [SAMPLE_CONFLICT] })
    mockPost.mockResolvedValue({ status: 'resolved', resolution: 'keep_manual' })
    const wrapper = makePanel()
    await flushPromises()

    const buttons = wrapper.findAll('.gt-conflict-panel__actions button')
    expect(buttons.length).toBeGreaterThan(0)
    // 第 1 个按钮即「保留手动」
    await buttons[0].trigger('click')
    await flushPromises()

    expect(mockPost).toHaveBeenCalledWith('/api/conflicts/c-1/resolve', {
      resolution: 'keep_manual',
    })
    expect(mockMessage.success).toHaveBeenCalled()
    // emit 'resolved'
    expect(wrapper.emitted('resolved')).toBeTruthy()
    expect(wrapper.emitted('resolved')![0]).toEqual(['c-1', 'keep_manual'])
  })

  it('click "接受新值" → POST resolve accept_new', async () => {
    mockGet.mockResolvedValue({ count: 1, items: [SAMPLE_CONFLICT] })
    mockPost.mockResolvedValue({ status: 'resolved' })
    const wrapper = makePanel()
    await flushPromises()

    const buttons = wrapper.findAll('.gt-conflict-panel__actions button')
    await buttons[1].trigger('click')
    await flushPromises()

    expect(mockPost).toHaveBeenCalledWith('/api/conflicts/c-1/resolve', {
      resolution: 'accept_new',
    })
  })

  it('click "合并" → 弹输入框 + 提交后 merge_value 透传', async () => {
    mockGet.mockResolvedValue({ count: 1, items: [SAMPLE_CONFLICT] })
    mockPost.mockResolvedValue({ status: 'resolved' })
    const wrapper = makePanel()
    await flushPromises()

    const buttons = wrapper.findAll('.gt-conflict-panel__actions button')
    await buttons[2].trigger('click') // 「合并」
    await flushPromises()

    // 显示 merge 输入框
    expect(wrapper.find('.gt-conflict-panel__merge').exists()).toBe(true)

    // 输入合并值
    const textarea = wrapper.find('.gt-conflict-panel__merge textarea')
    expect(textarea.exists()).toBe(true)
    await textarea.setValue('合并后的新值')
    await nextTick()

    // 点击「确认合并」
    const mergeButtons = wrapper.findAll('.gt-conflict-panel__merge-actions button')
    await mergeButtons[0].trigger('click')
    await flushPromises()

    expect(mockPost).toHaveBeenCalledWith('/api/conflicts/c-1/resolve', {
      resolution: 'merge',
      merge_value: '合并后的新值',
    })
    expect(wrapper.emitted('resolved')).toBeTruthy()
  })

  it('合并 - 空值时 warning 不发请求', async () => {
    mockGet.mockResolvedValue({ count: 1, items: [SAMPLE_CONFLICT] })
    const wrapper = makePanel()
    await flushPromises()

    const buttons = wrapper.findAll('.gt-conflict-panel__actions button')
    await buttons[2].trigger('click') // 「合并」
    await nextTick()

    // 不输入直接确认
    const mergeButtons = wrapper.findAll('.gt-conflict-panel__merge-actions button')
    await mergeButtons[0].trigger('click')
    await flushPromises()

    expect(mockMessage.warning).toHaveBeenCalled()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('API 错误时 handleApiError 处理加载错误', async () => {
    mockGet.mockRejectedValue({
      response: { data: { detail: '加载失败：网络错误' } },
    })
    makePanel()
    await flushPromises()

    expect(mockHandleApiError).toHaveBeenCalledWith(expect.anything(), '加载冲突列表')
  })

  it('后端返回 422 时 handleApiError 处理调解错误', async () => {
    mockGet.mockResolvedValue({ count: 1, items: [SAMPLE_CONFLICT] })
    mockPost.mockRejectedValue({
      response: { status: 422, data: { detail: '冲突已调解过，不可重复操作' } },
    })
    const wrapper = makePanel()
    await flushPromises()

    const buttons = wrapper.findAll('.gt-conflict-panel__actions button')
    await buttons[0].trigger('click')
    await flushPromises()

    expect(mockHandleApiError).toHaveBeenCalledWith(expect.anything(), '调解')
    // 不 emit resolved
    expect(wrapper.emitted('resolved')).toBeFalsy()
  })

  it('expose refresh() 主动刷新', async () => {
    mockGet.mockResolvedValue({ count: 0, items: [] })
    const wrapper = makePanel()
    await flushPromises()
    expect(mockGet).toHaveBeenCalledTimes(1)

    mockGet.mockResolvedValueOnce({ count: 1, items: [SAMPLE_CONFLICT] })
    await (wrapper.vm as any).refresh()
    await flushPromises()
    expect(mockGet).toHaveBeenCalledTimes(2)
    expect(wrapper.findAll('.gt-conflict-panel__item').length).toBe(1)
  })

  it('点击列表项 → emit view-detail + 切换选中', async () => {
    const second = { ...SAMPLE_CONFLICT, id: 'c-2', target_field: 'amount' }
    mockGet.mockResolvedValue({ count: 2, items: [SAMPLE_CONFLICT, second] })
    const wrapper = makePanel()
    await flushPromises()

    const items = wrapper.findAll('.gt-conflict-panel__item')
    await items[1].trigger('click')
    await nextTick()

    expect(wrapper.emitted('view-detail')).toBeTruthy()
    expect(wrapper.emitted('view-detail')![0][0]).toMatchObject({ id: 'c-2' })
  })
})
