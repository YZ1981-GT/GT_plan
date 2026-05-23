/**
 * PresenceAvatars 组件测试
 * Validates: workpaper-collaboration-presence F2
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PresenceAvatars from '@/components/workpaper/PresenceAvatars.vue'

const mockUsers = [
  { user_id: '1', user_name: '张三', mode: 'edit' as const },
  { user_id: '2', user_name: '李四', mode: 'view' as const },
  { user_id: '3', user_name: '王五', mode: 'view' as const },
]

describe('PresenceAvatars', () => {
  it('renders nothing when users is empty', () => {
    const wrapper = mount(PresenceAvatars, { props: { users: [] } })
    expect(wrapper.find('.presence-avatars').exists()).toBe(false)
  })

  it('renders avatars for each user', () => {
    const wrapper = mount(PresenceAvatars, { props: { users: mockUsers } })
    const avatars = wrapper.findAll('.presence-avatar')
    expect(avatars.length).toBe(3)
  })

  it('shows first character of user name', () => {
    const wrapper = mount(PresenceAvatars, { props: { users: mockUsers } })
    const texts = wrapper.findAll('.presence-avatar-text')
    expect(texts[0].text()).toBe('张')
    expect(texts[1].text()).toBe('李')
  })

  it('applies is-editing class for edit mode', () => {
    const wrapper = mount(PresenceAvatars, { props: { users: mockUsers } })
    const avatars = wrapper.findAll('.presence-avatar')
    expect(avatars[0].classes()).toContain('is-editing')
    expect(avatars[1].classes()).toContain('is-viewing')
  })

  it('shows overflow count when exceeding maxVisible', () => {
    const manyUsers = Array.from({ length: 8 }, (_, i) => ({
      user_id: String(i),
      user_name: `用户${i}`,
      mode: 'view' as const,
    }))
    const wrapper = mount(PresenceAvatars, {
      props: { users: manyUsers, maxVisible: 5 },
    })
    expect(wrapper.find('.presence-overflow').text()).toBe('+3')
    expect(wrapper.findAll('.presence-avatar').length).toBe(5)
  })

  it('does not show overflow when within limit', () => {
    const wrapper = mount(PresenceAvatars, {
      props: { users: mockUsers, maxVisible: 5 },
    })
    expect(wrapper.find('.presence-overflow').exists()).toBe(false)
  })
})
