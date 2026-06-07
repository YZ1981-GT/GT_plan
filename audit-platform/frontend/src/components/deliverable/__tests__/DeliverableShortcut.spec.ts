import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import DeliverableShortcut from '../DeliverableShortcut.vue'

// Mock vue-router
const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
}))

// Mock apiProxy
vi.mock('@/utils/apiProxy', () => ({
  api: {
    get: vi.fn().mockResolvedValue(null),
  },
}))

// Mock element-plus icons
vi.mock('@element-plus/icons-vue', () => ({
  Document: defineComponent({ render: () => h('i', 'doc-icon') }),
  ArrowRight: defineComponent({ render: () => h('i', 'arrow-icon') }),
}))

describe('DeliverableShortcut', () => {
  beforeEach(() => {
    mockPush.mockClear()
  })

  it('renders with project title', () => {
    const wrapper = mount(DeliverableShortcut, {
      props: { projectId: 'test-project-123' },
      global: {
        stubs: { 'el-icon': true, 'el-tag': true },
      },
    })
    expect(wrapper.text()).toContain('交付物管理')
  })

  it('navigates to deliverable-center on header click', async () => {
    const wrapper = mount(DeliverableShortcut, {
      props: { projectId: 'proj-abc' },
      global: {
        stubs: { 'el-icon': true, 'el-tag': true },
      },
    })
    await wrapper.find('.deliverable-shortcut__header').trigger('click')
    expect(mockPush).toHaveBeenCalledWith({
      name: 'deliverable-center',
      params: { projectId: 'proj-abc' },
    })
  })

  it('emits status-change when completeness data loads', async () => {
    const { api } = await import('@/utils/apiProxy')
    ;(api.get as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      passed: true,
      warnings: [],
      missing_doc_types: [],
      has_confirmed: true,
    })

    const wrapper = mount(DeliverableShortcut, {
      props: { projectId: 'proj-xyz', year: 2024 },
      global: {
        stubs: { 'el-icon': true, 'el-tag': true },
      },
    })

    // Wait for onMounted async calls
    await new Promise((r) => setTimeout(r, 10))
    expect(wrapper.emitted('status-change')).toBeTruthy()
  })
})
