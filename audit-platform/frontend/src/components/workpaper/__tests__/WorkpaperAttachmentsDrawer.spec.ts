/**
 * WorkpaperAttachmentsDrawer — Wave 2 来源 tag + Wave 3 解除关联
 * spec: attachment-workpaper-linkage-convergence Task 3.2 / 4.2
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import WorkpaperAttachmentsDrawer from '../WorkpaperAttachmentsDrawer.vue'
import {
  SOURCE_LABEL,
  resolveSourceKeys,
  canUnlinkSources,
} from '../workpaperAttachmentSources'

const mockGet = vi.fn()
const mockDelete = vi.fn()
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    delete: (...args: any[]) => mockDelete(...args),
  },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/utils/http', () => ({
  downloadFile: vi.fn(),
}))

vi.mock('@/utils/errorHandler', () => ({
  handleApiError: vi.fn(),
}))

vi.mock('element-plus', async () => {
  const actual = await vi.importActual<any>('element-plus')
  return {
    ...actual,
    ElMessage: { success: vi.fn(), error: vi.fn() },
    ElMessageBox: {
      confirm: vi.fn().mockResolvedValue(true),
    },
  }
})

vi.mock('@/components/extension/AttachmentPreview.vue', () => ({
  default: { template: '<div class="att-preview-stub" />', props: ['modelValue', 'fileUrl', 'fileName', 'fileType'] },
}))

const globalStubs = {
  'el-drawer': {
    template: '<div class="el-drawer"><slot /><slot name="footer" /></div>',
    props: ['modelValue', 'title', 'size'],
  },
  'el-tag': {
    template: '<span class="el-tag" :data-source="dataSource"><slot /></span>',
    props: ['type', 'size', 'effect', 'round', 'dataSource'],
  },
  'el-button': {
    template: '<button class="el-button" :class="$attrs.class" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'circle', 'size', 'loading'],
  },
  'el-empty': { template: '<div class="el-empty">{{ description }}</div>', props: ['description'] },
  'el-alert': {
    template: '<div class="el-alert" :data-testid="$attrs[\'data-testid\']"><div class="el-alert__title"><slot name="title" />{{ title }}</div><slot /></div>',
    props: ['type', 'title', 'closable', 'showIcon'],
    inheritAttrs: false,
  },
  'el-tooltip': { template: '<span><slot /></span>', props: ['content', 'placement'] },
  'el-icon': { template: '<i><slot /></i>' },
}

const sampleItems = [
  {
    id: 'a1',
    file_name: '回函.pdf',
    file_type: 'pdf',
    file_size: 1024,
    created_at: '2026-01-15T00:00:00Z',
    source: 'associated',
    sources: ['associated', 'confirmation'],
    association_type: 'evidence',
  },
  {
    id: 'a2',
    file_name: '引用件.pdf',
    file_type: 'pdf',
    file_size: 2048,
    created_at: '2026-01-16T00:00:00Z',
    source: 'referenced',
    sources: ['referenced'],
    association_type: null,
  },
  {
    id: 'a3',
    file_name: '纯函证.pdf',
    file_type: 'pdf',
    file_size: 512,
    created_at: '2026-01-17T00:00:00Z',
    source: 'confirmation',
    sources: ['confirmation'],
    association_type: null,
  },
]

describe('resolveSourceKeys / canUnlinkSources', () => {
  it('优先使用 sources 数组', () => {
    expect(resolveSourceKeys({ source: 'associated', sources: ['associated', 'confirmation'] })).toEqual([
      'associated',
      'confirmation',
    ])
  })

  it('无 sources 时回退 source', () => {
    expect(resolveSourceKeys({ source: 'referenced' })).toEqual(['referenced'])
  })

  it('空行返回空数组', () => {
    expect(resolveSourceKeys(null)).toEqual([])
    expect(resolveSourceKeys({})).toEqual([])
  })

  it('仅 associated/referenced 可解除', () => {
    expect(canUnlinkSources(['associated'])).toBe(true)
    expect(canUnlinkSources(['referenced'])).toBe(true)
    expect(canUnlinkSources(['confirmation'])).toBe(false)
    expect(canUnlinkSources(['associated', 'confirmation'])).toBe(true)
  })
})

describe('SOURCE_LABEL', () => {
  it('覆盖四类来源文案', () => {
    expect(SOURCE_LABEL.associated.label).toBe('关联证据')
    expect(SOURCE_LABEL.referenced.label).toBe('底稿引用')
    expect(SOURCE_LABEL.confirmation.label).toBe('函证回函')
    expect(SOURCE_LABEL.checklist.label).toBe('检查项证据')
  })
})

describe('WorkpaperAttachmentsDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGet.mockResolvedValue({ items: sampleItems })
    mockDelete.mockResolvedValue({ ok: true })
  })

  it('按 sources 渲染来源 tag', async () => {
    const wrapper = mount(WorkpaperAttachmentsDrawer, {
      props: {
        modelValue: true,
        wpId: 'wp-1',
        projectId: 'proj-1',
        wpCode: 'E1-1',
      },
      global: { stubs: globalStubs },
    })

    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('关联证据')
    expect(text).toContain('函证回函')
    expect(text).toContain('底稿引用')
    expect(text).toContain('回函.pdf')
    expect(wrapper.findAll('.wp-att-source-tag').length).toBeGreaterThanOrEqual(3)
  })

  it('canEdit=false 时不显示解除按钮', async () => {
    const wrapper = mount(WorkpaperAttachmentsDrawer, {
      props: {
        modelValue: true,
        wpId: 'wp-1',
        projectId: 'proj-1',
        canEdit: false,
      },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    expect(wrapper.findAll('.wp-att-unlink-btn').length).toBe(0)
  })

  it('canEdit=true 时仅对 associated/referenced 显示解除按钮', async () => {
    const wrapper = mount(WorkpaperAttachmentsDrawer, {
      props: {
        modelValue: true,
        wpId: 'wp-1',
        projectId: 'proj-1',
        canEdit: true,
      },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    // a1 associated + a2 referenced → 2；a3 confirmation-only → 无
    expect(wrapper.findAll('.wp-att-unlink-btn').length).toBe(2)
    expect(wrapper.find('[data-testid="confirmation-unlink-tip"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('检查项级证据')
    expect(wrapper.text()).toContain('上传并关联到本底稿')
  })

  it('解除关联成功后重新加载列表', async () => {
    mockGet
      .mockResolvedValueOnce({ items: sampleItems })
      .mockResolvedValueOnce({ items: sampleItems.slice(1) })

    const wrapper = mount(WorkpaperAttachmentsDrawer, {
      props: {
        modelValue: true,
        wpId: 'wp-1',
        projectId: 'proj-1',
        canEdit: true,
      },
      global: { stubs: globalStubs },
    })
    await flushPromises()

    const btn = wrapper.find('.wp-att-unlink-btn')
    await btn.trigger('click')
    await flushPromises()

    expect(mockDelete).toHaveBeenCalledWith(
      '/api/working-papers/wp-1/attachments/a1/link',
    )
    // immediate load + 解除后 reload（Vue watch 可能额外触发一次）
    expect(mockGet.mock.calls.length).toBeGreaterThanOrEqual(2)
  })

  it('有 evidence_requirements 时展示应收集清单与缺证据提示', async () => {
    mockGet.mockResolvedValue({
      items: sampleItems,
      evidence_requirements: [
        { type: 'bank_statement', label: '银行对账单', satisfied: true },
        { type: 'confirmation', label: '银行询证函回函', satisfied: false },
      ],
    })

    const wrapper = mount(WorkpaperAttachmentsDrawer, {
      props: {
        modelValue: true,
        wpId: 'wp-1',
        projectId: 'proj-1',
      },
      global: { stubs: globalStubs },
    })
    await flushPromises()

    const panel = wrapper.find('[data-testid="evidence-requirements"]')
    expect(panel.exists()).toBe(true)
    expect(panel.text()).toContain('银行对账单')
    expect(panel.text()).toContain('缺「银行询证函回函」证据')
    expect(panel.text()).toContain('尚缺 1 类证据')
  })

  it('无 evidence_requirements 时不展示应收集清单', async () => {
    mockGet.mockResolvedValue({ items: sampleItems })

    const wrapper = mount(WorkpaperAttachmentsDrawer, {
      props: {
        modelValue: true,
        wpId: 'wp-1',
        projectId: 'proj-1',
      },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="evidence-requirements"]').exists()).toBe(false)
  })

  it('stale_info.has_stale 时展示失效提示（分级）', async () => {
    mockGet.mockResolvedValue({
      items: sampleItems,
      stale_info: {
        has_stale: true,
        level: 'definite',
        items: [{ label: '证据引用已失效', reason: 'ref_inactive' }],
        project_id: 'proj-1',
      },
    })

    const wrapper = mount(WorkpaperAttachmentsDrawer, {
      props: {
        modelValue: true,
        wpId: 'wp-1',
        projectId: 'proj-1',
      },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    const tip = wrapper.find('[data-testid="stale-info"]')
    expect(tip.exists()).toBe(true)
    expect(tip.text()).toContain('明确失效')
    expect(tip.text()).toContain('治理中心')
  })

  it('无 stale 时不展示失效提示', async () => {
    mockGet.mockResolvedValue({
      items: sampleItems,
      stale_info: { has_stale: false, level: null, items: [] },
    })

    const wrapper = mount(WorkpaperAttachmentsDrawer, {
      props: {
        modelValue: true,
        wpId: 'wp-1',
        projectId: 'proj-1',
      },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="stale-info"]').exists()).toBe(false)
  })
})
