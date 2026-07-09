/**
 * Unit Tests for useReviewDialog composable & GtReviewDialog component
 *
 * Tasks 7.1-7.4:
 * - 7.1 基础功能：openDialog / sendMessage / retryMessage
 * - 7.2 多选模式：进入/退出/全选/取消/选中计数/导出按钮禁用
 * - 7.3 关闭确认逻辑：有消息弹确认、无消息直接关、三按钮行为
 * - 7.4 GtReviewDialog 组件渲染测试
 */
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { createApp, defineComponent, nextTick } from 'vue'
import { mount } from '@vue/test-utils'

// jsdom doesn't implement scrollIntoView
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn()
})

// Mock http module
vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

// Mock eventBus
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    on: vi.fn(),
    off: vi.fn(),
  },
}))

// Mock element-plus
vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
  ElDrawer: { name: 'ElDrawer', template: '<div><slot /><slot name="header" /></div>' },
  ElDialog: { name: 'ElDialog', template: '<div><slot /><slot name="footer" /></div>' },
  ElBadge: { name: 'ElBadge', template: '<span><slot /></span>', props: ['value', 'type'] },
  ElButton: { name: 'ElButton', template: '<button><slot /></button>', props: ['disabled', 'icon', 'type', 'link', 'loading', 'circle', 'size'] },
  ElInput: { name: 'ElInput', template: '<textarea />', props: ['modelValue', 'type', 'rows', 'placeholder', 'resize'] },
  ElSelect: { name: 'ElSelect', template: '<select><slot /></select>', props: ['modelValue', 'clearable', 'filterable', 'placeholder'] },
  ElOption: { name: 'ElOption', template: '<option />', props: ['label', 'value'] },
}))

vi.mock('@element-plus/icons-vue', () => ({
  Close: { name: 'Close', template: '<i />' },
}))

import http from '@/utils/http'
import { useReviewDialog, type GtReviewDialogProps, type ReviewMessage } from '../useReviewDialog'

const DIALOG_STUBS = {
  'el-drawer': { template: '<div class="mock-drawer"><slot /><slot name="header" /></div>', props: ['modelValue', 'size', 'direction', 'beforeClose', 'showClose'] },
  'el-dialog': { template: '<div class="mock-dialog"><slot /><slot name="footer" /></div>', props: ['modelValue', 'width', 'title', 'closeOnClickModal'] },
  'el-button': { template: '<button :disabled="disabled"><slot /></button>', props: ['disabled', 'icon', 'type', 'link', 'loading', 'circle', 'size'] },
  'el-badge': { template: '<span><slot /></span>', props: ['value', 'type'] },
  'el-input': { template: '<textarea />', props: ['modelValue', 'type', 'rows', 'placeholder', 'resize'] },
  'el-select': { template: '<select><slot /></select>', props: ['modelValue', 'clearable', 'filterable', 'placeholder', 'multiple'] },
  'el-option': { template: '<option />', props: ['label', 'value'] },
  'el-switch': { template: '<input type="checkbox" />', props: ['modelValue', 'inlinePrompt', 'activeText', 'inactiveText'] },
}

// ── Helper: run composable in Vue app context ────────────────────────────────

function withSetup<T>(composable: () => T): { result: T; unmount: () => void } {
  let result!: T
  const app = createApp(defineComponent({
    setup() {
      result = composable()
      return () => null
    },
  }))
  const el = document.createElement('div')
  app.mount(el)
  return { result, unmount: () => app.unmount() }
}

// ── Fixtures ─────────────────────────────────────────────────────────────────

const baseProps: GtReviewDialogProps = {
  wpId: 'wp-001',
  sectionId: 'audit-note',
  sectionLabel: '审计说明',
  currentUser: { id: 'user-1', name: '张三', role: '审计助理' },
  relatedData: { wpCode: 'D1-1' },
}

const mockMessages: ReviewMessage[] = [
  {
    id: 'msg-1', thread_id: 'thread-1', sender_id: 'user-1',
    sender_name: '张三', sender_role: '审计助理', content: '请复核此调整',
    message_type: 'text', created_at: '2025-06-01T10:00:00.000Z',
  },
  {
    id: 'msg-2', thread_id: 'thread-1', sender_id: 'user-2',
    sender_name: '李四', sender_role: '现场经理', content: '已复核',
    message_type: 'text', created_at: '2025-06-01T10:05:00.000Z',
  },
]

// ══════════════════════════════════════════════════════════════════════════════
// 7.1 useReviewDialog 基础功能
// ══════════════════════════════════════════════════════════════════════════════

describe('7.1 useReviewDialog 基础功能', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('openDialog 加载消息并设置状态', async () => {
    vi.mocked(http.get).mockResolvedValue({
      data: { id: 'thread-1', status: 'open', messages: mockMessages },
    })

    const { result, unmount } = withSetup(() => useReviewDialog(baseProps))
    await result.openDialog()

    expect(http.get).toHaveBeenCalledWith('/api/review-threads', {
      params: { wp_id: 'wp-001', section_id: 'audit-note' },
    })
    expect(result.isOpen.value).toBe(true)
    expect(result.threadId.value).toBe('thread-1')
    expect(result.messages.value).toHaveLength(2)
    expect(result.isLoading.value).toBe(false)
    unmount()
  })

  it('sendMessage 乐观更新：列表长度+1，_status=sending', async () => {
    vi.mocked(http.get).mockResolvedValue({
      data: { id: 'thread-1', status: 'open', messages: [] },
    })
    vi.mocked(http.post).mockResolvedValue({
      data: { id: 'msg-new', thread_id: 'thread-1', sender_id: 'user-1', sender_name: '张三', sender_role: '审计助理', content: '新消息', message_type: 'text', created_at: '2025-06-01T11:00:00.000Z' },
    })

    const { result, unmount } = withSetup(() => useReviewDialog(baseProps))
    await result.openDialog()
    expect(result.messages.value).toHaveLength(0)

    const sendPromise = result.sendMessage('新消息')
    // 乐观更新：立即出现
    expect(result.messages.value).toHaveLength(1)
    expect(result.messages.value[0].content).toBe('新消息')
    expect(result.messages.value[0]._status).toBe('sending')

    await sendPromise
    // 成功后 status 变 sent
    expect(result.messages.value[0]._status).toBe('sent')
    unmount()
  })

  it('sendMessage 失败时 _status 变 failed', async () => {
    vi.mocked(http.get).mockResolvedValue({
      data: { id: 'thread-1', status: 'open', messages: [] },
    })
    vi.mocked(http.post).mockRejectedValue(new Error('Network Error'))

    const { result, unmount } = withSetup(() => useReviewDialog(baseProps))
    await result.openDialog()
    await result.sendMessage('会失败的消息')

    expect(result.messages.value[0]._status).toBe('failed')
    unmount()
  })

  it('retryMessage 重发失败消息', async () => {
    vi.mocked(http.get).mockResolvedValue({
      data: { id: 'thread-1', status: 'open', messages: [] },
    })
    vi.mocked(http.post)
      .mockRejectedValueOnce(new Error('fail'))
      .mockResolvedValueOnce({
        data: { id: 'msg-retry', thread_id: 'thread-1', sender_id: 'user-1', sender_name: '张三', sender_role: '审计助理', content: '重发消息', message_type: 'text', created_at: '2025-06-01T12:00:00.000Z' },
      })

    const { result, unmount } = withSetup(() => useReviewDialog(baseProps))
    await result.openDialog()
    await result.sendMessage('重发消息')
    expect(result.messages.value[0]._status).toBe('failed')

    const tempId = result.messages.value[0]._tempId!
    await result.retryMessage(tempId)
    expect(result.messages.value[0]._status).toBe('sent')
    unmount()
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// 7.2 多选模式测试
// ══════════════════════════════════════════════════════════════════════════════

describe('7.2 多选模式', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(http.get).mockResolvedValue({
      data: { id: 'thread-1', status: 'open', messages: mockMessages },
    })
  })

  it('enterSelectMode 进入多选、exitSelectMode 退出', async () => {
    const { result, unmount } = withSetup(() => useReviewDialog(baseProps))
    await result.openDialog()

    result.enterSelectMode()
    expect(result.isMultiSelectMode.value).toBe(true)
    expect(result.selectedIds.value.size).toBe(0)

    result.exitSelectMode()
    expect(result.isMultiSelectMode.value).toBe(false)
    unmount()
  })

  it('toggleSelect 选中/取消', async () => {
    const { result, unmount } = withSetup(() => useReviewDialog(baseProps))
    await result.openDialog()
    result.enterSelectMode()

    result.toggleSelect('msg-1')
    expect(result.selectedIds.value.has('msg-1')).toBe(true)
    expect(result.selectedCount.value).toBe(1)

    result.toggleSelect('msg-1')
    expect(result.selectedIds.value.has('msg-1')).toBe(false)
    expect(result.selectedCount.value).toBe(0)
    unmount()
  })

  it('selectAll 全选所有消息', async () => {
    const { result, unmount } = withSetup(() => useReviewDialog(baseProps))
    await result.openDialog()
    result.enterSelectMode()
    result.selectAll()

    expect(result.selectedCount.value).toBe(2)
    expect(result.selectedIds.value.has('msg-1')).toBe(true)
    expect(result.selectedIds.value.has('msg-2')).toBe(true)
    unmount()
  })

  it('canExport 仅在选中>0时为 true', async () => {
    const { result, unmount } = withSetup(() => useReviewDialog(baseProps))
    await result.openDialog()
    result.enterSelectMode()

    expect(result.canExport.value).toBe(false)
    result.toggleSelect('msg-1')
    expect(result.canExport.value).toBe(true)
    unmount()
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// 7.3 关闭确认逻辑
// ══════════════════════════════════════════════════════════════════════════════

describe('7.3 关闭确认逻辑', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('无消息时直接关闭，不弹确认', async () => {
    vi.mocked(http.get).mockResolvedValue({
      data: { id: 'thread-1', status: 'open', messages: [] },
    })

    const { result, unmount } = withSetup(() => useReviewDialog(baseProps))
    await result.openDialog()
    result.handleClose()

    expect(result.isOpen.value).toBe(false)
    expect(result.isCloseConfirmOpen.value).toBe(false)
    unmount()
  })

  it('有消息时弹确认弹窗', async () => {
    vi.mocked(http.get).mockResolvedValue({
      data: { id: 'thread-1', status: 'open', messages: mockMessages },
    })

    const { result, unmount } = withSetup(() => useReviewDialog(baseProps))
    await result.openDialog()
    result.handleClose()

    expect(result.isOpen.value).toBe(true)
    expect(result.isCloseConfirmOpen.value).toBe(true)
    unmount()
  })

  it('confirmClose 关闭一切', async () => {
    vi.mocked(http.get).mockResolvedValue({
      data: { id: 'thread-1', status: 'open', messages: mockMessages },
    })

    const { result, unmount } = withSetup(() => useReviewDialog(baseProps))
    await result.openDialog()
    result.handleClose()
    result.confirmClose()

    expect(result.isCloseConfirmOpen.value).toBe(false)
    expect(result.isOpen.value).toBe(false)
    unmount()
  })

  it('confirmContinue 仅关闭确认弹窗', async () => {
    vi.mocked(http.get).mockResolvedValue({
      data: { id: 'thread-1', status: 'open', messages: mockMessages },
    })

    const { result, unmount } = withSetup(() => useReviewDialog(baseProps))
    await result.openDialog()
    result.handleClose()
    result.confirmContinue()

    expect(result.isCloseConfirmOpen.value).toBe(false)
    expect(result.isOpen.value).toBe(true)
    unmount()
  })

  it('confirmExport 进入多选模式', async () => {
    vi.mocked(http.get).mockResolvedValue({
      data: { id: 'thread-1', status: 'open', messages: mockMessages },
    })

    const { result, unmount } = withSetup(() => useReviewDialog(baseProps))
    await result.openDialog()
    result.handleClose()
    result.confirmExport()

    expect(result.isCloseConfirmOpen.value).toBe(false)
    expect(result.isMultiSelectMode.value).toBe(true)
    unmount()
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// 7.4 GtReviewDialog 组件渲染测试
// ══════════════════════════════════════════════════════════════════════════════

describe('7.4 GtReviewDialog 组件渲染', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(http.get).mockResolvedValue({
      data: { id: 'thread-1', status: 'open', messages: mockMessages },
    })
  })

  it('Props 传入并渲染 drawer', async () => {
    const GtReviewDialog = (await import('@/components/collaboration/GtReviewDialog.vue')).default
    const wrapper = mount(GtReviewDialog, {
      props: baseProps,
      global: {
        stubs: DIALOG_STUBS,
      },
    })
    await nextTick()
    await nextTick()

    expect(wrapper.find('.mock-drawer').exists()).toBe(true)
    wrapper.unmount()
  })

  it('只读模式（质量控制复核合伙人）不渲染输入区', async () => {
    const readOnlyProps: GtReviewDialogProps = {
      ...baseProps,
      currentUser: { id: 'user-qc', name: '王五', role: '质量控制复核合伙人' },
    }

    const GtReviewDialog = (await import('@/components/collaboration/GtReviewDialog.vue')).default
    const wrapper = mount(GtReviewDialog, {
      props: readOnlyProps,
      global: {
        stubs: DIALOG_STUBS,
      },
    })
    await nextTick()
    await nextTick()

    expect(wrapper.find('.input-area').exists()).toBe(false)
    wrapper.unmount()
  })

  it('自己的消息有 is-self class', async () => {
    const GtReviewDialog = (await import('@/components/collaboration/GtReviewDialog.vue')).default
    const wrapper = mount(GtReviewDialog, {
      props: baseProps,
      global: {
        stubs: DIALOG_STUBS,
      },
    })
    // Wait for openDialog in onMounted
    await nextTick()
    await nextTick()
    await nextTick()

    const selfRows = wrapper.findAll('.message-row.is-self')
    // msg-1 sender_id='user-1' matches currentUser.id='user-1' → is-self
    expect(selfRows.length).toBeGreaterThanOrEqual(1)
    wrapper.unmount()
  })
})
