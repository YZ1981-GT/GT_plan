/**
 * OnlyOfficeEditor — Task 21.2 vitest 单测
 * Spec: .kiro/specs/audit-report-deliverable-center/ Task 21.2
 *
 * 验证（需求 6.1, 6.5, 6.6, 28.1）：
 * 1. OnlyOffice 可用时渲染 iframe 编辑器
 * 2. OnlyOffice 不可用（health check 失败）时降级为预览提示
 * 3. fetchOnlyOfficeConfig 异常时降级为预览提示
 * 4. 降级时显示下载链接
 *
 * **Validates: Requirements 6.1, 6.5, 6.6, 28.1**
 */
import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const { mockFetchHealth, mockFetchConfig } = vi.hoisted(() => ({
  mockFetchHealth: vi.fn(),
  mockFetchConfig: vi.fn(),
}))

vi.mock('@/services/deliverableApi', () => ({
  fetchOnlyOfficeHealth: (...args: any[]) => mockFetchHealth(...args),
  fetchOnlyOfficeConfig: (...args: any[]) => mockFetchConfig(...args),
}))

import OnlyOfficeEditor from '../OnlyOfficeEditor.vue'

const baseProps = {
  projectId: 'proj-123',
  taskId: 'task-abc',
  versionNo: 1,
  year: 2024,
  title: '在线编辑',
  previewType: 'docx' as const,
  previewUrl: '/download/test.docx',
}

const stubDialog = {
  template: '<div class="el-dialog-stub" v-if="modelValue"><slot /></div>',
  props: ['modelValue', 'title', 'width', 'top'],
  emits: ['update:modelValue', 'close'],
}

const stubAlert = {
  template: '<div class="el-alert-stub" :data-type="type"><slot /></div>',
  props: ['type', 'closable', 'title', 'description'],
}

const stubSkeleton = {
  template: '<div class="el-skeleton-stub" />',
  props: ['rows', 'animated'],
}

const stubButton = {
  template: '<a class="el-button-stub" :href="href"><slot /></a>',
  props: ['type', 'href', 'target'],
}

const stubPreview = {
  template: '<div class="deliverable-preview-stub" :data-type="previewType" :data-url="url" />',
  props: ['title', 'previewType', 'url', 'showWatermark'],
  emits: ['close'],
}

function mountEditor(props: Record<string, any> = {}) {
  return mount(OnlyOfficeEditor, {
    props: { ...baseProps, ...props },
    global: {
      stubs: {
        'el-dialog': stubDialog,
        'el-alert': stubAlert,
        'el-skeleton': stubSkeleton,
        'el-button': stubButton,
        DeliverablePreview: stubPreview,
      },
    },
  })
}

describe('OnlyOfficeEditor — Task 21.2 降级行为', () => {
  beforeEach(() => {
    mockFetchHealth.mockReset()
    mockFetchConfig.mockReset()
  })

  it('OnlyOffice 可用时渲染 iframe（需求 6.1）', async () => {
    mockFetchHealth.mockResolvedValue({ available: true, enabled: true })
    mockFetchConfig.mockResolvedValue({
      config: {},
      token: 'jwt-token-123',
      mode: 'edit',
      documentType: 'word',
    })

    const wrapper = mountEditor()
    await flushPromises()

    const iframe = wrapper.find('.onlyoffice-editor__iframe')
    expect(iframe.exists()).toBe(true)
    expect(iframe.attributes('src')).toContain('documenteditor')
  })

  it('OnlyOffice 不可用时降级显示警告（需求 28.1）', async () => {
    mockFetchHealth.mockResolvedValue({ available: false, enabled: true })

    const wrapper = mountEditor()
    await flushPromises()

    const alert = wrapper.find('.el-alert-stub')
    expect(alert.exists()).toBe(true)
    // 降级模式，不应显示 iframe
    expect(wrapper.find('.onlyoffice-editor__iframe').exists()).toBe(false)
  })

  it('OnlyOffice 未启用时降级（需求 28.1）', async () => {
    mockFetchHealth.mockResolvedValue({ available: false, enabled: false })

    const wrapper = mountEditor()
    await flushPromises()

    expect(wrapper.find('.onlyoffice-editor__iframe').exists()).toBe(false)
    const fallback = wrapper.find('.onlyoffice-editor__fallback')
    expect(fallback.exists()).toBe(true)
  })

  it('fetchOnlyOfficeConfig 异常时降级（需求 28.1）', async () => {
    mockFetchHealth.mockResolvedValue({ available: true, enabled: true })
    mockFetchConfig.mockRejectedValue(new Error('503'))

    const wrapper = mountEditor()
    await flushPromises()

    expect(wrapper.find('.onlyoffice-editor__iframe').exists()).toBe(false)
    // 应降级
    const alert = wrapper.find('.el-alert-stub')
    expect(alert.exists()).toBe(true)
  })

  it('降级时使用 DeliverablePreview 组件（需求 28.1）', async () => {
    mockFetchHealth.mockResolvedValue({ available: false, enabled: true })

    const wrapper = mountEditor({ previewUrl: '/api/download/v1.docx' })
    await flushPromises()

    const preview = wrapper.find('.deliverable-preview-stub')
    expect(preview.exists()).toBe(true)
    expect(preview.attributes('data-url')).toBe('/api/download/v1.docx')
    expect(preview.attributes('data-type')).toBe('docx')
  })

  it('cell 类型（xlsx）使用 spreadsheet editor URL（需求 6.2）', async () => {
    mockFetchHealth.mockResolvedValue({ available: true, enabled: true })
    mockFetchConfig.mockResolvedValue({
      config: {},
      token: 'jwt-token-xlsx',
      mode: 'edit',
      documentType: 'cell',
    })

    const wrapper = mountEditor()
    await flushPromises()

    const iframe = wrapper.find('.onlyoffice-editor__iframe')
    expect(iframe.exists()).toBe(true)
    expect(iframe.attributes('src')).toContain('spreadsheet')
  })
})
