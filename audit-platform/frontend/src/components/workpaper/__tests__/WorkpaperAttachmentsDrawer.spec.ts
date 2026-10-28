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

const mockHttpPost = vi.fn()
vi.mock('@/utils/http', () => ({
  default: { post: (...args: any[]) => mockHttpPost(...args), get: vi.fn(), delete: vi.fn() },
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
  'el-select': {
    template: '<select class="el-select" :data-value="modelValue" :data-testid="$attrs[\'data-testid\']"><slot /></select>',
    props: ['modelValue', 'size', 'clearable', 'placeholder'],
    inheritAttrs: false,
  },
  'el-option': { template: '<option :value="value">{{ label }}</option>', props: ['label', 'value'] },
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

  it('associated/referenced/行级证据可解除，纯函证不可', () => {
    expect(canUnlinkSources(['associated'])).toBe(true)
    expect(canUnlinkSources(['referenced'])).toBe(true)
    expect(canUnlinkSources(['evidence_link'])).toBe(true)
    expect(canUnlinkSources(['confirmation'])).toBe(false)
    expect(canUnlinkSources(['associated', 'confirmation'])).toBe(true)
  })
})

describe('SOURCE_LABEL', () => {
  it('覆盖各类来源文案', () => {
    expect(SOURCE_LABEL.associated.label).toBe('关联证据')
    expect(SOURCE_LABEL.referenced.label).toBe('底稿引用')
    expect(SOURCE_LABEL.confirmation.label).toBe('函证回函')
    expect(SOURCE_LABEL.evidence_link.label).toBe('行级证据')
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
    expect(wrapper.text()).toContain('行级证据')
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

  // ── spec attachment-evidence-intake 需求 5.2 / 5.3 ──

  async function chooseFile(wrapper: ReturnType<typeof mount>, name = '回函.pdf') {
    const input = wrapper.find('input[type="file"]')
    const file = new File(['%PDF-1.4'], name, { type: 'application/pdf' })
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    await flushPromises()
  }

  it('缺省预选第一类未满足的声明类型；「上传此类证据」按该类走证据入口', async () => {
    mockGet.mockResolvedValue({
      items: sampleItems,
      evidence_requirements: [
        { type: 'bank_statement', label: '银行对账单', satisfied: true },
        { type: 'confirmation', label: '银行询证函回函', satisfied: false },
      ],
    })
    mockHttpPost.mockResolvedValue({ data: { attachment: { id: 'new-1' }, evidence_link: null } })
    const wrapper = mount(WorkpaperAttachmentsDrawer, {
      props: { modelValue: true, wpId: 'wp-1', projectId: 'proj-1', canEdit: true },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="evidence-type-select"]').attributes('data-value')).toBe('confirmation')

    const quick = wrapper.findAll('.wp-att-evidence-req__upload')
    expect(quick.map((b) => b.attributes('data-type'))).toEqual(['confirmation'])
    await quick[0].trigger('click')
    await chooseFile(wrapper)

    expect(mockHttpPost).toHaveBeenCalledTimes(1)
    const [url, form] = mockHttpPost.mock.calls[0]
    expect(url).toBe('/api/projects/proj-1/workpapers/wp-1/evidence/upload')
    expect((form as FormData).get('evidence_type')).toBe('confirmation')
    expect((form as FormData).has('sheet_name')).toBe(false)
    expect((form as FormData).has('cell_ref')).toBe(false)
  })

  it('无声明时工具栏上传不带类型（交给后端按底稿缺省）', async () => {
    mockGet.mockResolvedValue({ items: sampleItems })
    mockHttpPost.mockResolvedValue({ data: { attachment: { id: 'new-2' }, evidence_link: null } })
    const wrapper = mount(WorkpaperAttachmentsDrawer, {
      props: { modelValue: true, wpId: 'wp-1', projectId: 'proj-1', canEdit: true },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="evidence-type-select"]').attributes('data-value')).toBe('')
    await wrapper.find('[data-testid="wp-att-upload"]').trigger('click')
    await chooseFile(wrapper, '凭证.pdf')
    const form = mockHttpPost.mock.calls[0][1] as FormData
    expect(form.has('evidence_type')).toBe(false)
    expect((form.get('file') as File).name).toBe('凭证.pdf')
  })

  it('行级证据显示来源与位置，可解除', async () => {
    mockGet.mockResolvedValue({
      items: [{
        id: 'r1', file_name: '行证据.pdf', file_type: 'pdf', file_size: 10, created_at: '2026-10-27T00:00:00Z',
        source: 'evidence_link', sources: ['evidence_link'], association_type: null,
        evidence_positions: [
          { link_id: 'l1', sheet_name: 'D2A', cell_ref: 'item:3', page_ref: null },
          { link_id: 'l2', sheet_name: 'D2A', cell_ref: 'B7', page_ref: '2' },
        ],
      }],
    })
    const wrapper = mount(WorkpaperAttachmentsDrawer, {
      props: { modelValue: true, wpId: 'wp-1', projectId: 'proj-1', canEdit: true },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    expect(wrapper.find('[data-source="evidence_link"]').text()).toBe('行级证据')
    expect(wrapper.find('[data-testid="evidence-positions"]').text()).toBe('行级位置：D2A · 第 3 项、D2A · B7 · 第 2 页')
    expect(wrapper.findAll('.wp-att-unlink-btn').length).toBe(1)
  })
})

describe('WorkpaperAttachmentsDrawer — 图标按钮可读名与空态（spec attachment-evidence-intake 走查补）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockDelete.mockResolvedValue({ ok: true })
  })

  it('行内图标按钮带含文件名的 aria-label（只有悬浮提示时读屏读不到）', async () => {
    mockGet.mockResolvedValue({ items: sampleItems })
    const wrapper = mount(WorkpaperAttachmentsDrawer, {
      props: { modelValue: true, wpId: 'wp-1', projectId: 'proj-1', canEdit: true },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    const labels = wrapper.findAll('button[aria-label]').map((b) => b.attributes('aria-label'))
    expect(labels).toEqual(expect.arrayContaining([
      '预览 回函.pdf', '下载 回函.pdf', '解除关联 回函.pdf', '在附件管理中查看 回函.pdf', '预览 纯函证.pdf',
    ]))
    // 纯函证不可解除 ⇒ 没有它的「解除关联」可读名
    expect(labels).not.toContain('解除关联 纯函证.pdf')
  })

  it('无附件：可编辑时提示在上方上传，只读时不提上传', async () => {
    mockGet.mockResolvedValue({ items: [] })
    const editable = mount(WorkpaperAttachmentsDrawer, {
      props: { modelValue: true, wpId: 'wp-1', projectId: 'proj-1', canEdit: true },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    expect(editable.find('.el-empty').text()).toBe('本底稿暂无关联附件，可在上方选择证据类型后上传')

    const readonly = mount(WorkpaperAttachmentsDrawer, {
      props: { modelValue: true, wpId: 'wp-1', projectId: 'proj-1', canEdit: false },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    expect(readonly.find('.el-empty').text()).toBe('本底稿暂无关联附件')
  })
})

describe('WorkpaperAttachmentsDrawer — 函证逐笔判定（spec attachment-confirmation-evidence-loop 需求 6.2）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockDelete.mockResolvedValue({ ok: true })
  })

  const breakdownReq = (missingItems: Array<{ confirmation_id: string; counterparty: string | null; reason: string }>, extra: Record<string, number>) => ({
    type: 'confirmation',
    label: '函证回函件',
    satisfied: missingItems.length === 0,
    breakdown: { missing: missingItems.length, missing_items: missingItems, ...extra },
  })

  it('有逐笔判定：显示汇总与缺证据清单，不给整稿「上传此类证据」，也不作缺省上传类型', async () => {
    mockGet.mockResolvedValue({
      items: sampleItems,
      evidence_requirements: [
        breakdownReq(
          [
            { confirmation_id: 'c3', counterparty: '乙公司', reason: '未回函且未做替代程序' },
            { confirmation_id: 'c4', counterparty: null, reason: '未发函' },
          ],
          { total: 4, replied: 1, alternative: 1 },
        ),
      ],
    })
    const wrapper = mount(WorkpaperAttachmentsDrawer, {
      props: { modelValue: true, wpId: 'wp-1', projectId: 'proj-1', wpCode: 'D0-5', canEdit: true },
      global: { stubs: globalStubs },
    })
    await flushPromises()

    const block = wrapper.find('[data-testid="confirmation-breakdown"]')
    expect(block.exists()).toBe(true)
    expect(block.find('.wp-att-breakdown__summary').text()).toBe('共 4 笔：已回函 1、替代程序 1、缺证据 2')
    expect(block.findAll('.wp-att-breakdown__missing li').map((li) => li.text())).toEqual([
      '乙公司：未回函且未做替代程序',
      '（未填函证对象）：未发函',
    ])
    expect(block.find('.wp-att-breakdown__hint').text()).toBe('请在函证中心上传回函，或在替代程序页对应行上传单据')
    expect(wrapper.text()).toContain('缺「函证回函件」证据')
    expect(wrapper.findAll('.wp-att-evidence-req__upload')).toHaveLength(0)
    expect(wrapper.find('[data-testid="evidence-type-select"]').attributes('data-value')).toBe('')
  })

  it('逐笔全部有证据：判满足，只显示汇总', async () => {
    mockGet.mockResolvedValue({
      items: sampleItems,
      evidence_requirements: [breakdownReq([], { total: 3, replied: 2, alternative: 1 })],
    })
    const wrapper = mount(WorkpaperAttachmentsDrawer, {
      props: { modelValue: true, wpId: 'wp-1', projectId: 'proj-1', wpCode: 'D0-1', canEdit: true },
      global: { stubs: globalStubs },
    })
    await flushPromises()

    const block = wrapper.find('[data-testid="confirmation-breakdown"]')
    expect(block.find('.wp-att-breakdown__summary').text()).toBe('共 3 笔：已回函 2、替代程序 1、缺证据 0')
    expect(block.find('.wp-att-breakdown__missing').exists()).toBe(false)
    expect(block.find('.wp-att-breakdown__hint').exists()).toBe(false)
    expect(wrapper.find('[data-testid="evidence-requirements"]').text()).toContain('✓ 函证回函件')
  })

  it('只缺律师函（A12-1）：提示到函证中心卡片上传，不提替代程序页', async () => {
    mockGet.mockResolvedValue({
      items: [],
      evidence_requirements: [{
        type: 'confirmation', label: '律师询证函回函', satisfied: false,
        breakdown: { total: 1, replied: 0, alternative: 0, missing: 1,
          missing_items: [{ confirmation_id: 'L1', counterparty: '某律师事务所', confirm_type: 'legal', reason: '未回函且未做替代程序' }] },
      }],
    })
    const wrapper = mount(WorkpaperAttachmentsDrawer, {
      props: { modelValue: true, wpId: 'wp-1', projectId: 'proj-1', wpCode: 'A12-1', canEdit: true },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    expect(wrapper.find('.wp-att-breakdown__hint').text()).toBe('请在本底稿「函证中心」卡片上传律师回函')
  })

  it('没有逐笔判定（工作簿未登记函证）时沿用原显示与整稿上传', async () => {
    mockGet.mockResolvedValue({
      items: sampleItems,
      evidence_requirements: [{ type: 'confirmation', label: '函证回函件', satisfied: false }],
    })
    const wrapper = mount(WorkpaperAttachmentsDrawer, {
      props: { modelValue: true, wpId: 'wp-1', projectId: 'proj-1', wpCode: 'D0', canEdit: true },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="confirmation-breakdown"]').exists()).toBe(false)
    expect(wrapper.findAll('.wp-att-evidence-req__upload').map((b) => b.attributes('data-type'))).toEqual(['confirmation'])
    expect(wrapper.find('[data-testid="evidence-type-select"]').attributes('data-value')).toBe('confirmation')
  })
})
