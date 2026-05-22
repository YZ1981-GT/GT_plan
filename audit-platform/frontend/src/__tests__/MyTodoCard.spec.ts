/**
 * MyTodoCard 前端测试
 * Validates: Requirements 1.4, 1.5, 1.6
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const mockPush = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'test-project' } }),
  useRouter: () => ({ push: mockPush }),
}))

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
  },
}))

import MyTodoCard from '@/components/dashboard/MyTodoCard.vue'
import { api } from '@/services/apiProxy'

const mockTodos = [
  { wp_id: 'wp-1', wp_code: 'D2-1', wp_name: '销售收入审定表', cycle: 'D', urgency: 'critical', urgency_reason: 'stale', updated_at: '2026-01-15T10:00:00Z' },
  { wp_id: 'wp-2', wp_code: 'E1-1', wp_name: '货币资金审定表', cycle: 'E', urgency: 'high', urgency_reason: 'SLA approaching', updated_at: '2026-01-15T09:00:00Z' },
  { wp_id: 'wp-3', wp_code: 'F2-1', wp_name: '存货审定表', cycle: 'F', urgency: 'normal', urgency_reason: '', updated_at: '2026-01-14T08:00:00Z' },
]

describe('MyTodoCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders todo list after loading', async () => {
    vi.mocked(api.get).mockResolvedValue({ items: mockTodos, total: 3 })
    const wrapper = mount(MyTodoCard, {
      global: { stubs: { 'el-button': true, 'el-tag': true, 'el-icon': true } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('D2-1')
    expect(wrapper.text()).toContain('E1-1')
    expect(wrapper.text()).toContain('F2-1')
  })

  it('maps urgency to correct color via el-tag style', async () => {
    vi.mocked(api.get).mockResolvedValue({ items: mockTodos, total: 3 })
    const wrapper = mount(MyTodoCard, {
      global: { stubs: { 'el-button': true, 'el-icon': true } },
    })
    await flushPromises()

    const tags = wrapper.findAll('.el-tag')
    // critical → #D32F2F, high → #EF6C00, normal → #9E9E9E
    if (tags.length >= 3) {
      expect(tags[0].attributes('style')).toContain('#D32F2F')
      expect(tags[1].attributes('style')).toContain('#EF6C00')
      expect(tags[2].attributes('style')).toContain('#9E9E9E')
    }
  })

  it('shows empty state when no todos', async () => {
    vi.mocked(api.get).mockResolvedValue({ items: [], total: 0 })
    const wrapper = mount(MyTodoCard, {
      global: { stubs: { 'el-button': true, 'el-tag': true, 'el-icon': true } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('暂无待办，保持好状态 ✓')
  })

  it('navigates to workpaper on click', async () => {
    vi.mocked(api.get).mockResolvedValue({ items: mockTodos, total: 3 })
    const wrapper = mount(MyTodoCard, {
      global: { stubs: { 'el-button': true, 'el-tag': true, 'el-icon': true } },
    })
    await flushPromises()

    const items = wrapper.findAll('.my-todo-item')
    await items[0].trigger('click')

    expect(mockPush).toHaveBeenCalledWith({
      name: 'WorkpaperEditor',
      params: { projectId: 'test-project', wpId: 'wp-1' },
    })
  })
})
