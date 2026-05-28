/**
 * PresenceAvatars 组件测试
 * Validates: workpaper-collaboration-presence F2
 *
 * 当前 API：组件通过 usePresence(projectIdRef, viewName) 获取在线成员，
 * 不再接受 users prop。测试通过 mock usePresence 注入数据。
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'

// 共享的 mock 在线成员（每个测试通过赋值修改）
const onlineMembers = ref<any[]>([])

vi.mock('@/composables/usePresence', () => ({
  usePresence: () => ({ onlineMembers }),
}))

// 必须在 mock 之后 import 组件
import PresenceAvatars from '@/components/PresenceAvatars.vue'

const mockMembers = [
  { user_id: '1', user_name: '张三', view: 'workpapers', mode: 'edit' as const },
  { user_id: '2', user_name: '李四', view: 'workpapers', mode: 'view' as const },
  { user_id: '3', user_name: '王五', view: 'workpapers', mode: 'view' as const },
]

const STUBS = {
  'el-tooltip': {
    template: '<div class="el-tooltip" :data-content="content"><slot /></div>',
    props: ['content', 'placement'],
  },
  'el-avatar': {
    template: '<span class="el-avatar"><slot /></span>',
    props: ['size', 'src'],
  },
}

describe('PresenceAvatars', () => {
  it('renders nothing when no online members', () => {
    onlineMembers.value = []
    const wrapper = mount(PresenceAvatars, {
      props: { projectId: 'proj-001', viewName: 'workpapers' },
      global: { stubs: STUBS },
    })
    expect(wrapper.find('.presence-avatars').exists()).toBe(false)
  })

  it('renders avatar for each member in current view', () => {
    onlineMembers.value = mockMembers
    const wrapper = mount(PresenceAvatars, {
      props: { projectId: 'proj-001', viewName: 'workpapers' },
      global: { stubs: STUBS },
    })
    const avatars = wrapper.findAll('.el-avatar')
    expect(avatars.length).toBe(3)
  })

  it('shows first character of user name as initials', () => {
    onlineMembers.value = mockMembers
    const wrapper = mount(PresenceAvatars, {
      props: { projectId: 'proj-001', viewName: 'workpapers' },
      global: { stubs: STUBS },
    })
    const avatars = wrapper.findAll('.el-avatar')
    expect(avatars[0].text()).toBe('张')
    expect(avatars[1].text()).toBe('李')
    expect(avatars[2].text()).toBe('王')
  })

  it('filters members to current view only', () => {
    onlineMembers.value = [
      ...mockMembers,
      { user_id: '4', user_name: '赵六', view: 'reports', mode: 'view' as const },
    ]
    const wrapper = mount(PresenceAvatars, {
      props: { projectId: 'proj-001', viewName: 'workpapers' },
      global: { stubs: STUBS },
    })
    // 只渲染 workpapers 视图的 3 人
    expect(wrapper.findAll('.el-avatar').length).toBe(3)
  })

  it('shows online count', () => {
    onlineMembers.value = mockMembers
    const wrapper = mount(PresenceAvatars, {
      props: { projectId: 'proj-001', viewName: 'workpapers' },
      global: { stubs: STUBS },
    })
    expect(wrapper.find('.presence-count').text()).toContain('3')
  })
})
