// Feature: procedure-delegation-notification — Task 11 已读深链组件测试
//
// 需求 10.8 / 9.6：通知点击按 metadata 驱动跳转（不解析中文 content）。
// 关键：**已读通知点击仍可跳转**（Design F4）；未读点击先标记已读再跳转。
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  unreadCount: vi.fn(),
  markRead: vi.fn(),
  markAllRead: vi.fn(),
  routerPush: vi.fn(),
}))

vi.mock('@/services/collaborationApi', () => ({
  notificationApi: {
    list: mocks.list,
    unreadCount: mocks.unreadCount,
    markRead: mocks.markRead,
    markAllRead: mocks.markAllRead,
  },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mocks.routerPush }),
}))

vi.mock('@/stores/collaboration', () => ({
  useCollaborationStore: () => ({ unreadCount: 0 }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}))

vi.mock('@element-plus/icons-vue', () => ({
  Bell: {}, Warning: {}, CircleCheckFilled: {}, InfoFilled: {},
}))

vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

import NotificationCenter from '../NotificationCenter.vue'

const READ_NOTIF = {
  id: 'n-read', notification_type: 'procedure_task.reviewed', title: '程序任务已复核',
  content: null, is_read: true, created_at: new Date().toISOString(),
  event_id: 'evt-1', metadata: { project_id: 'p1', wp_id: 'wp9', task_id: 't1', sheet_key: 's', definition_key: 'd' },
}
const UNREAD_NOTIF = {
  id: 'n-unread', notification_type: 'procedure_task.assigned', title: '程序任务已分配',
  content: null, is_read: false, created_at: new Date().toISOString(),
  event_id: 'evt-2', metadata: { project_id: 'p1', task_id: 't2' },
}

const stubs = {
  'el-popover': { template: '<div><slot name="reference" /><slot /></div>' },
  'el-tooltip': { template: '<span><slot /></span>' },
  'el-badge': { template: '<span><slot /></span>' },
  'el-icon': { template: '<i><slot /></i>' },
  'el-button': { template: '<button><slot /></button>' },
  'el-tabs': { template: '<div><slot /></div>' },
  'el-tab-pane': { template: '<div><slot /></div>' },
  'el-empty': { template: '<div class="el-empty" />' },
}

async function mountCenter() {
  mocks.list.mockResolvedValue({ data: { items: [READ_NOTIF, UNREAD_NOTIF], total: 2 } })
  mocks.unreadCount.mockResolvedValue({ data: { count: 1 } })
  mocks.markRead.mockResolvedValue({})
  const wrapper = mount(NotificationCenter, { global: { stubs } })
  await flushPromises()
  return wrapper
}

describe('NotificationCenter 已读深链跳转 (Task 11)', () => {
  beforeEach(() => vi.clearAllMocks())

  it('点击【已读】程序通知：不重复标记已读，但仍按 metadata 跳转底稿深链', async () => {
    const wrapper = await mountCenter()
    const items = wrapper.findAll('.notif-item')
    expect(items.length).toBe(2)
    // 第一条为已读通知
    await items[0].trigger('click')
    await flushPromises()
    expect(mocks.markRead).not.toHaveBeenCalled() // 已读不重复标记
    expect(mocks.routerPush).toHaveBeenCalledTimes(1)
    const route = mocks.routerPush.mock.calls[0][0]
    expect(route).toContain('/projects/p1/workpapers')
    expect(route).toContain('task_id=t1')
  })

  it('点击【未读】程序通知：先标记已读再按 metadata 跳转（无 wp_id → 我的程序任务页）', async () => {
    const wrapper = await mountCenter()
    const items = wrapper.findAll('.notif-item')
    await items[1].trigger('click')
    await flushPromises()
    expect(mocks.markRead).toHaveBeenCalledWith('n-unread')
    expect(mocks.routerPush).toHaveBeenCalledTimes(1)
    const route = mocks.routerPush.mock.calls[0][0]
    expect(route).toContain('/my-procedures')
    expect(route).toContain('project_id=p1')
  })
})
