/**
 * PresenceAvatars 组件测试
 * Validates: workpaper-collaboration-presence F2 / enterprise-linkage 3.2
 *
 * 注（2026-06-06）：组件已重构为 props={projectId, viewName} + usePresence 组合式
 * 数据源（不再接受 users 数组 prop）。本测试相应重写：mock usePresence 注入在线成员，
 * 断言按 viewName 过滤后的头像渲染。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { mount } from '@vue/test-utils'

// usePresence mock：受测组件从此组合式取 onlineMembers
const onlineMembers = ref<any[]>([])
vi.mock('@/composables/usePresence', () => ({
  usePresence: () => ({ onlineMembers }),
}))

import PresenceAvatars from '@/components/PresenceAvatars.vue'

const stubs = {
  'el-tooltip': { template: '<div class="el-tooltip"><slot /></div>' },
  'el-avatar': {
    template: '<div class="el-avatar"><slot /></div>',
    props: ['size', 'src', 'style'],
  },
}

function mountWith(members: any[], viewName = 'workpapers') {
  onlineMembers.value = members
  return mount(PresenceAvatars, {
    props: { projectId: 'proj-001', viewName },
    global: { stubs },
  })
}

describe('PresenceAvatars', () => {
  beforeEach(() => {
    onlineMembers.value = []
  })

  it('在线成员为空时不渲染容器', () => {
    const wrapper = mountWith([])
    expect(wrapper.find('.presence-avatars').exists()).toBe(false)
  })

  it('按 viewName 过滤后为每个成员渲染头像', () => {
    const wrapper = mountWith([
      { user_id: '1', user_name: '张三', view: 'workpapers' },
      { user_id: '2', user_name: '李四', view: 'workpapers' },
      { user_id: '3', user_name: '王五', view: 'reports' }, // 不同视图，过滤掉
    ])
    expect(wrapper.findAll('.el-avatar').length).toBe(2)
  })

  it('头像显示姓名首字', () => {
    const wrapper = mountWith([
      { user_id: '1', user_name: '张三', view: 'workpapers' },
    ])
    expect(wrapper.find('.el-avatar').text()).toBe('张')
  })

  it('显示在线人数', () => {
    const wrapper = mountWith([
      { user_id: '1', user_name: '张三', view: 'workpapers' },
      { user_id: '2', user_name: '李四', view: 'workpapers' },
    ])
    expect(wrapper.find('.presence-count').text()).toContain('2 人在线')
  })

  it('其他视图成员不计入当前视图', () => {
    const wrapper = mountWith([
      { user_id: '1', user_name: '张三', view: 'reports' },
    ], 'workpapers')
    expect(wrapper.find('.presence-avatars').exists()).toBe(false)
  })
})
