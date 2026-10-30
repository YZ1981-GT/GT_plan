// NotificationCenter 首屏只取未读数、列表首开才取、轮询不重叠
// （spec runtime-performance-and-reload-hardening-followup R6.3）。
//
// 🔴 原实现：onMounted 串行 await fetchNotifications() + fetchUnreadCount()（首屏 2 条请求，
// 而列表只在 popover 打开后才显示），随后 setInterval(30s) 固定轮询未读数 —— 请求慢于 30 秒时
// interval 会重叠发请求，页面隐藏也照发。
//
// 这里挂真实组件（不复刻逻辑），用挂起的响应数判请求形态。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const list = vi.fn()
const unreadCount = vi.fn()

vi.mock('@/services/collaborationApi', () => ({
  notificationApi: {
    list: (...args: unknown[]) => list(...args),
    unreadCount: (...args: unknown[]) => unreadCount(...args),
    markRead: vi.fn().mockResolvedValue({ data: {} }),
    markAllRead: vi.fn().mockResolvedValue({ data: {} }),
  },
}))
vi.mock('@/stores/collaboration', () => ({
  useCollaborationStore: () => ({ unreadCount: 0 }),
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/services/notificationTypes', () => ({ getNotificationJumpRoute: () => null }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

import NotificationCenter from '../NotificationCenter.vue'

const STUBS = {
  'el-popover': { template: '<div><slot name="reference" /><slot /></div>', props: ['visible'] },
  'el-tooltip': { template: '<div><slot /></div>' },
  'el-badge': { template: '<div><slot /></div>', props: ['value', 'hidden', 'max'] },
  'el-icon': { template: '<i @click="$emit(\'click\')"><slot /></i>' },
  'el-button': { template: '<button><slot /></button>' },
  'el-tabs': { template: '<div><slot /></div>' },
  'el-tab-pane': { template: '<div><slot /></div>' },
  'el-empty': { template: '<div />' },
  'el-tag': { template: '<span><slot /></span>' },
  Bell: { template: '<span />' },
  Warning: { template: '<span />' },
  CircleCheckFilled: { template: '<span />' },
  InfoFilled: { template: '<span />' },
}

function mountCenter() {
  return mount(NotificationCenter, { global: { stubs: STUBS } })
}

beforeEach(() => {
  list.mockReset()
  unreadCount.mockReset()
  list.mockResolvedValue({ data: { items: [{ id: 'n1', notification_type: 'SYSTEM', is_read: false }] } })
  unreadCount.mockResolvedValue({ data: { count: 3 } })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('NotificationCenter 首屏与轮询', () => {
  it('挂载只取未读数，不取列表', async () => {
    const wrapper = mountCenter()
    await flushPromises()
    expect(unreadCount).toHaveBeenCalledTimes(1)
    expect(list).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('首次打开才取列表；第二次打开不再取', async () => {
    const wrapper = mountCenter()
    await flushPromises()
    ;(wrapper.vm as any).popoverVisible = true
    await flushPromises()
    expect(list).toHaveBeenCalledTimes(1)
    ;(wrapper.vm as any).popoverVisible = false
    await flushPromises()
    ;(wrapper.vm as any).popoverVisible = true
    await flushPromises()
    expect(list).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('列表取失败时下次打开重试（不把失败当已加载）', async () => {
    list.mockRejectedValueOnce(new Error('500'))
    const wrapper = mountCenter()
    await flushPromises()
    ;(wrapper.vm as any).popoverVisible = true
    await flushPromises()
    expect(list).toHaveBeenCalledTimes(1)
    ;(wrapper.vm as any).popoverVisible = false
    await flushPromises()
    ;(wrapper.vm as any).popoverVisible = true
    await flushPromises()
    expect(list).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('卸载后不再轮询未读数', async () => {
    vi.useFakeTimers()
    const wrapper = mountCenter()
    await flushPromises()
    expect(unreadCount).toHaveBeenCalledTimes(1)
    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(90_000)
    expect(unreadCount).toHaveBeenCalledTimes(1)
    vi.useRealTimers()
  })

  it('源码判据：不再用 setInterval，改走 useAdaptivePoll', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const source = fs.readFileSync(path.resolve(__dirname, '../NotificationCenter.vue'), 'utf-8')
    const code = source
      .split('\n')
      .filter((line) => !line.trim().startsWith('//') && !line.trim().startsWith('*'))
      .join('\n')
    expect(code).not.toContain('setInterval')
    expect(code).toContain('useAdaptivePoll')
    // 挂载钩子里不得再取列表
    const mounted = code.slice(code.indexOf('onMounted('), code.indexOf('onUnmounted('))
    expect(mounted).not.toContain('fetchNotifications')
  })
})
