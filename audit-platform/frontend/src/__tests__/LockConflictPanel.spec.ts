/**
 * LockConflictPanel 组件测试
 * Validates: workpaper-collaboration-presence F1
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import LockConflictPanel from '@/components/workpaper/LockConflictPanel.vue'

const mockInfo = {
  locked_by: 'user-123',
  locked_by_name: '张三',
  acquired_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(), // 5 minutes ago
}

describe('LockConflictPanel', () => {
  const factory = (info = mockInfo) => mount(LockConflictPanel, {
    props: { info },
    global: {
      stubs: {
        'el-button': {
          template: '<button @click="$emit(\'click\')"><slot /></button>',
          inheritAttrs: false,
        },
      },
    },
  })

  it('renders lock holder name', () => {
    const wrapper = factory()
    expect(wrapper.text()).toContain('张三')
  })

  it('shows relative time', () => {
    const wrapper = factory()
    expect(wrapper.text()).toContain('5 分钟前开始编辑')
  })

  it('emits view-readonly on first button click', async () => {
    const wrapper = factory()
    const buttons = wrapper.findAll('button')
    await buttons[0]?.trigger('click')
    expect(wrapper.emitted('view-readonly')).toBeTruthy()
  })

  it('emits force-acquire on second button click', async () => {
    const wrapper = factory()
    const buttons = wrapper.findAll('button')
    await buttons[1]?.trigger('click')
    expect(wrapper.emitted('force-acquire')).toBeTruthy()
  })

  it('emits go-back on third button click', async () => {
    const wrapper = factory()
    const buttons = wrapper.findAll('button')
    await buttons[2]?.trigger('click')
    expect(wrapper.emitted('go-back')).toBeTruthy()
  })

  it('shows "刚刚开始编辑" for recent lock', () => {
    const recentInfo = { ...mockInfo, acquired_at: new Date().toISOString() }
    const wrapper = factory(recentInfo)
    expect(wrapper.text()).toContain('刚刚开始编辑')
  })
})
