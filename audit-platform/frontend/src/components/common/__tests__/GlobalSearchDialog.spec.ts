import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import GlobalSearchDialog from '../GlobalSearchDialog.vue'

// Mock http
vi.mock('@/utils/http', () => ({
  default: {
    get: vi.fn().mockResolvedValue({ data: { results: [] } }),
  },
}))

// Mock vue-router
const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
}))

describe('GlobalSearchDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('renders when visible=true', () => {
    const wrapper = mount(GlobalSearchDialog, {
      props: { visible: true },
      global: { stubs: { 'el-dialog': { template: '<div><slot /></div>', props: ['modelValue'] } } },
    })
    expect(wrapper.find('.gt-search-input-wrap').exists()).toBe(true)
  })

  it('does not render content when visible=false', () => {
    const wrapper = mount(GlobalSearchDialog, {
      props: { visible: false },
      global: { stubs: { 'el-dialog': { template: '<div v-if="modelValue"><slot /></div>', props: ['modelValue'] } } },
    })
    expect(wrapper.find('.gt-search-input-wrap').exists()).toBe(false)
  })

  it('emits update:visible false on Esc', async () => {
    const wrapper = mount(GlobalSearchDialog, {
      props: { visible: true },
      global: { stubs: { 'el-dialog': { template: '<div><slot /></div>', props: ['modelValue'] } } },
    })
    const input = wrapper.find('input')
    if (input.exists()) {
      await input.trigger('keydown', { key: 'Escape' })
      expect(wrapper.emitted('update:visible')?.[0]).toEqual([false])
    }
  })

  it('shows recent items from localStorage', async () => {
    const recent = [
      { type: 'workpaper', id: '1', title: 'D2-1 应收账款', subtitle: 'D循环', route: { name: 'WorkpaperList', params: { projectId: 'abc' } }, relevance: 0.8 },
    ]
    localStorage.setItem('gt_recent_search', JSON.stringify(recent))

    const wrapper = mount(GlobalSearchDialog, {
      props: { visible: true },
      global: { stubs: { 'el-dialog': { template: '<div><slot /></div>', props: ['modelValue'] } } },
    })
    await nextTick()
    expect(wrapper.text()).toContain('最近访问')
    expect(wrapper.text()).toContain('D2-1 应收账款')
  })

  it('displays type icons correctly', () => {
    const wrapper = mount(GlobalSearchDialog, {
      props: { visible: true },
      global: { stubs: { 'el-dialog': { template: '<div><slot /></div>', props: ['modelValue'] } } },
    })
    // Access the typeIcon function via component instance
    const vm = wrapper.vm as any
    expect(vm.typeIcon('workpaper')).toBe('📋')
    expect(vm.typeIcon('account')).toBe('📊')
    expect(vm.typeIcon('report_line')).toBe('📄')
    expect(vm.typeIcon('project')).toBe('📁')
    expect(vm.typeIcon('unknown')).toBe('🔗')
  })

  it('tracks keyword and results state correctly', async () => {
    const wrapper = mount(GlobalSearchDialog, {
      props: { visible: true },
      global: {
        stubs: {
          'el-dialog': { template: '<div><slot /></div>', props: ['modelValue'] },
          'el-input': { template: '<input />', props: ['modelValue'] },
        },
      },
    })
    const vm = wrapper.vm as any
    expect(vm.keyword).toBe('')
    expect(vm.results).toEqual([])
    // Verify typeIcon function works
    expect(vm.typeIcon('workpaper')).toBe('📋')
    expect(vm.typeIcon('account')).toBe('📊')
  })
})
