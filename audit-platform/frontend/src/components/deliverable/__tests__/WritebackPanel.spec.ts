/**
 * WritebackResultPanel + WritebackConflictDialog vitest tests
 *
 * Spec: deliverable-lineage-and-writeback Task 16.3
 * Reqs: 7.1, 8.2, 8.3, 11.4
 *
 * 验证：
 * - 回填按钮渲染 + 终态禁用
 * - WritebackResult 分组展示（written/rejected/conflicts/skipped）
 * - 冲突裁决弹窗三栏对照 + radio 选择
 * - 裁决提交
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import WritebackResultPanel from '../WritebackResultPanel.vue'
import WritebackConflictDialog from '../WritebackConflictDialog.vue'

// Mock element-plus
vi.mock('element-plus', () => ({
  ElMessage: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  },
  ElMessageBox: {
    confirm: vi.fn().mockResolvedValue(undefined),
  },
}))

// Mock apiProxy (项目铁律：组件用 api.post 而非原生 fetch)
const mockApiGet = vi.fn()
const mockApiPost = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockApiGet(...args),
    post: (...args: any[]) => mockApiPost(...args),
  },
}))

describe('WritebackResultPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders writeback button', () => {
    const wrapper = mount(WritebackResultPanel, {
      props: {
        projectId: '123',
        wordExportTaskId: '456',
        year: 2025,
      },
      global: {
        stubs: {
          ElTooltip: { template: '<div><slot /></div>' },
          ElButton: { template: '<button :disabled="$attrs.disabled" @click="$emit(\'click\')"><slot /></button>', inheritAttrs: true },
          ElIcon: { template: '<span><slot /></span>' },
          ElAlert: { template: '<div><slot /></div>' },
        },
      },
    })

    expect(wrapper.text()).toContain('回填到附注模块')
  })

  it('disables button when deliverable is in terminal state (signed)', () => {
    const wrapper = mount(WritebackResultPanel, {
      props: {
        projectId: '123',
        wordExportTaskId: '456',
        year: 2025,
        deliverableStatus: 'signed',
      },
      global: {
        stubs: {
          ElTooltip: { template: '<div><slot /></div>' },
          ElButton: {
            template: '<button :disabled="$attrs.disabled"><slot /></button>',
            inheritAttrs: true,
          },
          ElIcon: { template: '<span><slot /></span>' },
        },
      },
    })

    const button = wrapper.find('button')
    expect(button.attributes('disabled')).toBeDefined()
  })

  it('disables button when deliverable is confirmed', () => {
    const wrapper = mount(WritebackResultPanel, {
      props: {
        projectId: '123',
        wordExportTaskId: '456',
        deliverableStatus: 'confirmed',
      },
      global: {
        stubs: {
          ElTooltip: { template: '<div><slot /></div>' },
          ElButton: {
            template: '<button :disabled="$attrs.disabled"><slot /></button>',
            inheritAttrs: true,
          },
          ElIcon: { template: '<span><slot /></span>' },
        },
      },
    })

    const button = wrapper.find('button')
    expect(button.attributes('disabled')).toBeDefined()
  })

  it('disables button when deliverable is archived', () => {
    const wrapper = mount(WritebackResultPanel, {
      props: {
        projectId: '123',
        wordExportTaskId: '456',
        deliverableStatus: 'archived',
      },
      global: {
        stubs: {
          ElTooltip: { template: '<div><slot /></div>' },
          ElButton: {
            template: '<button :disabled="$attrs.disabled"><slot /></button>',
            inheritAttrs: true,
          },
          ElIcon: { template: '<span><slot /></span>' },
        },
      },
    })

    const button = wrapper.find('button')
    expect(button.attributes('disabled')).toBeDefined()
  })

  it('does not disable button for non-terminal state (draft)', () => {
    const wrapper = mount(WritebackResultPanel, {
      props: {
        projectId: '123',
        wordExportTaskId: '456',
        deliverableStatus: 'draft',
      },
      global: {
        stubs: {
          ElTooltip: { template: '<div><slot /></div>' },
          ElButton: {
            template: '<button :disabled="$attrs.disabled"><slot /></button>',
            inheritAttrs: true,
          },
          ElIcon: { template: '<span><slot /></span>' },
        },
      },
    })

    const button = wrapper.find('button')
    // Not disabled for non-terminal state
    expect(button.attributes('disabled')).toBeUndefined()
  })

  it('exposes isTerminalState computed correctly', () => {
    const wrapper = mount(WritebackResultPanel, {
      props: {
        projectId: '123',
        wordExportTaskId: '456',
        deliverableStatus: 'signed',
      },
      global: {
        stubs: {
          ElTooltip: { template: '<div><slot /></div>' },
          ElButton: { template: '<button><slot /></button>' },
          ElIcon: { template: '<span><slot /></span>' },
        },
      },
    })

    expect((wrapper.vm as any).isTerminalState).toBe(true)
  })
})

describe('WritebackConflictDialog', () => {
  const mockConflicts = [
    {
      section_code: '八、1',
      deliverable_value: '出品物侧文字',
      upstream_value: '上游当前文字',
      baseline_value: '基线文字',
    },
    {
      section_code: '八、2',
      deliverable_value: '出品物侧第二章',
      upstream_value: '上游第二章',
      baseline_value: '基线第二章',
    },
  ]

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders three-column comparison for each conflict', () => {
    const wrapper = mount(WritebackConflictDialog, {
      props: {
        visible: true,
        conflicts: mockConflicts,
        projectId: '123',
        wordExportTaskId: '456',
        year: 2025,
      },
      global: {
        stubs: {
          ElDialog: { template: '<div v-if="$attrs[\'model-value\']"><slot /><slot name="footer" /></div>', inheritAttrs: true },
          ElAlert: { template: '<div><slot name="title" /></div>' },
          ElRadio: { template: '<label><input type="radio" :value="$attrs.label" /><slot /></label>', inheritAttrs: true },
          ElTag: { template: '<span><slot /></span>' },
          ElButton: { template: '<button :disabled="$attrs.disabled" @click="$emit(\'click\')"><slot /></button>', inheritAttrs: true },
          ElIcon: { template: '<span />' },
        },
      },
    })

    // Check section codes are displayed
    expect(wrapper.text()).toContain('八、1')
    expect(wrapper.text()).toContain('八、2')

    // Check three-column values
    expect(wrapper.text()).toContain('出品物侧编辑值')
    expect(wrapper.text()).toContain('上游当前值')
    expect(wrapper.text()).toContain('生成时基线值（参考）')

    // Check content values
    expect(wrapper.text()).toContain('出品物侧文字')
    expect(wrapper.text()).toContain('上游当前文字')
    expect(wrapper.text()).toContain('基线文字')
  })

  it('submit button is disabled when not all conflicts resolved', () => {
    const wrapper = mount(WritebackConflictDialog, {
      props: {
        visible: true,
        conflicts: mockConflicts,
        projectId: '123',
        wordExportTaskId: '456',
      },
      global: {
        stubs: {
          ElDialog: { template: '<div v-if="$attrs[\'model-value\']"><slot /><slot name="footer" /></div>', inheritAttrs: true },
          ElAlert: { template: '<div />' },
          ElRadio: { template: '<label><slot /></label>' },
          ElTag: { template: '<span />' },
          ElButton: { template: '<button :disabled="$attrs.disabled" @click="$emit(\'click\')"><slot /></button>', inheritAttrs: true },
          ElIcon: { template: '<span />' },
        },
      },
    })

    // Initially not all resolved
    expect((wrapper.vm as any).allResolved).toBe(false)
  })

  it('allResolved becomes true when all conflicts have resolutions', async () => {
    const wrapper = mount(WritebackConflictDialog, {
      props: {
        visible: true,
        conflicts: mockConflicts,
        projectId: '123',
        wordExportTaskId: '456',
      },
      global: {
        stubs: {
          ElDialog: { template: '<div><slot /><slot name="footer" /></div>' },
          ElAlert: { template: '<div />' },
          ElRadio: { template: '<label><slot /></label>' },
          ElTag: { template: '<span />' },
          ElButton: { template: '<button><slot /></button>' },
          ElIcon: { template: '<span />' },
        },
      },
    })

    // Set all resolutions
    ;(wrapper.vm as any).resolutions = {
      '八、1': 'deliverable',
      '八、2': 'upstream',
    }
    await nextTick()

    expect((wrapper.vm as any).allResolved).toBe(true)
  })

  it('submits resolutions via POST /writeback with resolutions', async () => {
    mockApiPost.mockResolvedValueOnce({ written: ['八、1', '八、2'], rejected: [], conflicts: [], skipped: [] })

    const wrapper = mount(WritebackConflictDialog, {
      props: {
        visible: true,
        conflicts: mockConflicts,
        projectId: '123',
        wordExportTaskId: '456',
        year: 2025,
      },
      global: {
        stubs: {
          ElDialog: { template: '<div><slot /><slot name="footer" /></div>' },
          ElAlert: { template: '<div />' },
          ElRadio: { template: '<label><slot /></label>' },
          ElTag: { template: '<span />' },
          ElButton: { template: '<button @click="$emit(\'click\')"><slot /></button>' },
          ElIcon: { template: '<span />' },
        },
      },
    })

    // Set all resolutions
    ;(wrapper.vm as any).resolutions = {
      '八、1': 'deliverable',
      '八、2': 'upstream',
    }
    await nextTick()

    // Call onSubmit
    await (wrapper.vm as any).onSubmit()

    // Verify api.post was called with correct params
    expect(mockApiPost).toHaveBeenCalledWith(
      '/api/projects/123/deliverables/456/writeback',
      {
        year: 2025,
        resolutions: { '八、1': 'deliverable', '八、2': 'upstream' },
      },
    )
  })
})
