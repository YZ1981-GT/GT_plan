/**
 * ReviewPanel + CompletionChecklistDialog + IndependenceSigning 前端单测
 * Task 5.5
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ReviewPanel from '@/components/workpaper/WorkpaperReviewPanel.vue'
import CompletionChecklistDialog from '@/components/workpaper/CompletionChecklistDialog.vue'
import IndependenceSigning from '@/components/workpaper/IndependenceSigning.vue'

vi.mock('@/utils/apiProxy', () => ({
  apiProxy: {
    get: vi.fn().mockResolvedValue({ title: '测试', items: [], status: 'draft', unlinked_conversations: [] }),
    post: vi.fn().mockResolvedValue({ success: true }),
  }
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

const elementPlusStubs = {
  'el-table': { template: '<div class="el-table"><slot /></div>', props: ['data'] },
  'el-table-column': {
    template: '<div class="el-table-column"><slot name="default" :row="row" /></div>',
    props: ['type', 'label', 'width', 'minWidth', 'align', 'prop'],
    data: () => ({ row: { auto_result: null, checked: false, remark: '', conversations: [] } }),
  },
  'el-tabs': { template: '<div class="el-tabs"><slot /></div>', props: ['modelValue'] },
  'el-tab-pane': { template: '<div class="el-tab-pane"><slot /></div>', props: ['label', 'name'] },
}

const mountOptions = { global: { stubs: elementPlusStubs } }

describe('ReviewPanel', () => {
  const props = { projectId: '00000000-0000-0000-0000-000000000001', year: 2025, role: 'manager' }

  it('renders without errors', () => {
    const wrapper = mount(ReviewPanel, { props, ...mountOptions })
    expect(wrapper.find('.review-panel').exists()).toBe(true)
  })

  it('has review-panel-header', () => {
    const wrapper = mount(ReviewPanel, { props, ...mountOptions })
    expect(wrapper.find('.review-panel-header').exists()).toBe(true)
  })
})

describe('CompletionChecklistDialog', () => {
  const props = { projectId: '00000000-0000-0000-0000-000000000001', year: 2025 }

  it('renders without errors', () => {
    const wrapper = mount(CompletionChecklistDialog, { props, ...mountOptions })
    expect(wrapper.exists()).toBe(true)
  })

  it('exposes open method', () => {
    const wrapper = mount(CompletionChecklistDialog, { props, ...mountOptions })
    expect(typeof wrapper.vm.open).toBe('function')
  })
})

describe('IndependenceSigning', () => {
  const props = { projectId: '00000000-0000-0000-0000-000000000001', year: 2025, userId: '00000000-0000-0000-0000-000000000002' }

  it('renders without errors', () => {
    const wrapper = mount(IndependenceSigning, { props, ...mountOptions })
    expect(wrapper.find('.independence-signing').exists()).toBe(true)
  })

  it('has el-tabs', () => {
    const wrapper = mount(IndependenceSigning, { props, ...mountOptions })
    expect(wrapper.html()).toContain('el-tabs')
  })
})
