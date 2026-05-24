/**
 * TemplateLibraryButton.vue — 3 页面按钮存在性 e2e
 *
 * Task 7.6.3: 验证 TemplateLibraryButton 组件在 3 个模板页面中正确渲染
 * Feature: advanced-query-enhancements-p1p2, Property 28: Event-driven tree reveal
 * Validates: Requirements 14.1, 14.5
 */
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import TemplateLibraryButton from '../TemplateLibraryButton.vue'

// Mock eventBus
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
  },
}))

describe('TemplateLibraryButton', () => {
  it('renders the button with correct text', () => {
    const wrapper = mount(TemplateLibraryButton, {
      props: {
        source: 'workpaper:D2',
      },
      global: {
        stubs: {
          'el-button': {
            template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>',
            emits: ['click'],
          },
        },
      },
    })
    expect(wrapper.text()).toContain('📊 高级查询')
  })

  it('emits open-custom-query with correct payload on click (workpaper source)', async () => {
    const { eventBus } = await import('@/utils/eventBus')

    const wrapper = mount(TemplateLibraryButton, {
      props: {
        source: 'workpaper:D2|审定表D2-1',
        projectId: 'proj-123',
      },
      global: {
        stubs: {
          'el-button': {
            template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>',
            emits: ['click'],
          },
        },
      },
    })

    await wrapper.find('button').trigger('click')

    expect(eventBus.emit).toHaveBeenCalledWith('open-custom-query', {
      tab: 'basic',
      source: 'workpaper:D2|审定表D2-1',
      project_id: 'proj-123',
    })
  })

  it('emits open-custom-query with report source', async () => {
    const { eventBus } = await import('@/utils/eventBus')
    vi.mocked(eventBus.emit).mockClear()

    const wrapper = mount(TemplateLibraryButton, {
      props: {
        source: 'report:balance_sheet',
      },
      global: {
        stubs: {
          'el-button': {
            template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>',
            emits: ['click'],
          },
        },
      },
    })

    await wrapper.find('button').trigger('click')

    expect(eventBus.emit).toHaveBeenCalledWith('open-custom-query', {
      tab: 'basic',
      source: 'report:balance_sheet',
      project_id: undefined,
    })
  })

  it('emits open-custom-query with note source', async () => {
    const { eventBus } = await import('@/utils/eventBus')
    vi.mocked(eventBus.emit).mockClear()

    const wrapper = mount(TemplateLibraryButton, {
      props: {
        source: 'note:五-1-1',
      },
      global: {
        stubs: {
          'el-button': {
            template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>',
            emits: ['click'],
          },
        },
      },
    })

    await wrapper.find('button').trigger('click')

    expect(eventBus.emit).toHaveBeenCalledWith('open-custom-query', {
      tab: 'basic',
      source: 'note:五-1-1',
      project_id: undefined,
    })
  })
})
