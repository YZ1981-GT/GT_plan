// 通知中心弹层：用真实 Element Plus 挂载（不打桩 el-popover / el-tooltip），钉住两件事：
// ① reference 不再是无单一根元素的 ElTooltip —— 否则 Vue 报
//    "Runtime directive used on component with non-element root node"，Popover 的触发器指令失效；
// ② 弹层是非受控的 —— 受控 :visible 下 Element Plus 不处理点外关闭（浏览器实测点空白处关不掉）。
import { describe, it, expect, vi, afterEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  unreadCount: vi.fn(),
}))

vi.mock('@/services/collaborationApi', () => ({
  notificationApi: {
    list: mocks.list,
    unreadCount: mocks.unreadCount,
    markRead: vi.fn(),
    markAllRead: vi.fn(),
  },
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/stores/collaboration', () => ({ useCollaborationStore: () => ({ unreadCount: 0 }) }))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))

import NotificationCenter from '../NotificationCenter.vue'

async function mountReal() {
  mocks.list.mockResolvedValue({ data: { items: [], total: 0 } })
  mocks.unreadCount.mockResolvedValue({ data: { count: 3 } })
  const wrapper = mount(NotificationCenter, { attachTo: document.body, global: { plugins: [ElementPlus], stubs: { transition: false } },
  })
  await flushPromises()
  return wrapper
}

const vm = (w: ReturnType<typeof mount>) => w.vm as unknown as { popoverVisible: boolean }

afterEach(() => {
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

describe('NotificationCenter 弹层', () => {
  it('挂载不产生「非元素根节点上的运行时指令」警告', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const wrapper = await mountReal()
    const hits = warn.mock.calls.map(c => String(c[0])).filter(m => m.includes('non-element root node'))
    expect(hits).toEqual([])
    wrapper.unmount()
  })

  it('点铃铛打开、点页面其他位置关闭（非受控弹层处理点外关闭）', async () => {
    const outside = document.createElement('div')
    document.body.appendChild(outside)
    const wrapper = await mountReal()

    await wrapper.find('.notif-trigger').trigger('click')
    await vi.waitFor(() => expect(vm(wrapper).popoverVisible).toBe(true))
    // 打开即取列表
    await vi.waitFor(() => expect(mocks.list).toHaveBeenCalledTimes(1))

    // 按真实点击的事件序列派发（Element Plus 的点外检测基于 vueuse onClickOutside：pointerdown + click）
    for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
      outside.dispatchEvent(new MouseEvent(type, { bubbles: true }))
    }
    await vi.waitFor(() => expect(vm(wrapper).popoverVisible).toBe(false))
    wrapper.unmount()
  })
})
