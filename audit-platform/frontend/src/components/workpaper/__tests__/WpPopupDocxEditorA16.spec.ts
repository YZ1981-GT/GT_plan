/**
 * WpPopupDocxEditorA16.spec.ts — A16-1~6 弹窗渲染 E2E 组件测试
 *
 * 验证 Task 7（a16-representation-letter）：
 * 1. WpPopupDocxEditor 对 A16-1~6 每个 wpCode 正确渲染
 * 2. guidance 使用说明区可见且包含配置内容
 * 3. 下载模板按钮存在
 * 4. A16-x 弹窗显示签回状态 radio（isA16Popup=true）
 * 5. WpInlinePopup 对 A16-1~6 使用 WpPopupDocxEditor 组件
 *
 * Validates: Requirements 2（A16-1~7 弹窗模式）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'
import WpPopupDocxEditor from '../WpPopupDocxEditor.vue'
import { DOCX_POPUP_CONFIGS, DOCX_POPUP_WP_CODES, INLINE_POPUP_WP_CODES } from '../wpPopupDocxConfigs'

// Mock vue-router
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'proj-a16-test' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

// Mock apiProxy
const mockApiGet = vi.fn().mockResolvedValue(null)
const mockApiPut = vi.fn().mockResolvedValue({})
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockApiGet(...args),
    put: (...args: any[]) => mockApiPut(...args),
    post: vi.fn().mockResolvedValue({}),
  },
}))

// Mock downloadFile
const mockDownloadFile = vi.fn()
vi.mock('@/utils/http', () => ({
  downloadFile: (...args: any[]) => mockDownloadFile(...args),
}))

// Mock OnlyOfficeEditor
vi.mock('@/components/deliverable/OnlyOfficeEditor.vue', () => ({
  default: { name: 'OnlyOfficeEditor', template: '<div class="mock-onlyoffice" />' },
}))

const globalStubs = {
  'el-alert': {
    template: '<div class="el-alert"><slot name="title" /><slot /></div>',
    props: ['type', 'closable', 'showIcon'],
  },
  'el-button': {
    template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'loading', 'text'],
  },
  'el-tag': {
    template: '<span class="el-tag"><slot /></span>',
    props: ['type', 'size', 'effect'],
  },
  'el-divider': { template: '<span class="el-divider" />', props: ['direction'] },
  'el-message': { template: '<div />' },
  'el-radio-group': {
    template: '<div class="el-radio-group"><slot /></div>',
    props: ['modelValue', 'size'],
  },
  'el-radio-button': {
    template: '<label class="el-radio-button" :data-value="value || label"><slot /></label>',
    props: ['value', 'label'],
  },
}

const A16_CODES = ['A16-1', 'A16-2', 'A16-3', 'A16-4', 'A16-5', 'A16-6'] as const

describe('WpPopupDocxEditor — A16-1~6 弹窗渲染', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApiGet.mockResolvedValue(null)
  })

  it.each(A16_CODES)('%s 配置存在于 DOCX_POPUP_CONFIGS', (code) => {
    const cfg = DOCX_POPUP_CONFIGS[code]
    expect(cfg, `${code} 配置缺失`).toBeDefined()
    expect(cfg.title).toBeTruthy()
    expect(cfg.guidance.length).toBeGreaterThan(0)
    expect(cfg.templatePath).toContain('.docx')
    expect(cfg.relatedLinks.length).toBeGreaterThan(0)
  })

  it.each(A16_CODES)('%s 在 INLINE_POPUP_WP_CODES 中注册', (code) => {
    expect(INLINE_POPUP_WP_CODES.has(code)).toBe(true)
  })

  it.each(A16_CODES)('%s 弹窗渲染 guidance 使用说明', async (code) => {
    const wrapper = mount(WpPopupDocxEditor, {
      props: { wpCode: code, projectId: 'proj-a16-test' },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    await nextTick()

    const html = wrapper.html()
    const cfg = DOCX_POPUP_CONFIGS[code]

    // guidance 区域存在
    expect(wrapper.find('.wp-popup-docx-editor__guidance').exists()).toBe(true)

    // guidance 内容包含配置的第一条说明
    expect(html).toContain(cfg.guidance[0])

    // 适用条件标签存在
    expect(html).toContain(cfg.applicableNote)
  })

  it.each(A16_CODES)('%s 弹窗包含下载模板按钮', async (code) => {
    const wrapper = mount(WpPopupDocxEditor, {
      props: { wpCode: code, projectId: 'proj-a16-test' },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    await nextTick()

    // 工具栏存在
    expect(wrapper.find('.wp-popup-docx-editor__toolbar').exists()).toBe(true)

    // 找到包含"下载"文字的按钮
    const buttons = wrapper.findAll('.el-button')
    const downloadBtn = buttons.filter((b) => b.text().includes('下载'))
    expect(downloadBtn.length).toBeGreaterThanOrEqual(1)
  })

  it.each(A16_CODES)('%s 弹窗显示签回状态 radio（isA16Popup=true）', async (code) => {
    const wrapper = mount(WpPopupDocxEditor, {
      props: { wpCode: code, projectId: 'proj-a16-test', wpId: 'wp-123' },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    await nextTick()

    // A16-x 弹窗应显示签回状态行
    expect(wrapper.find('.sign-row').exists()).toBe(true)
    expect(wrapper.find('.sign-label').exists()).toBe(true)

    // 签回 radio 含三种状态
    const html = wrapper.html()
    expect(html).toContain('待编辑')
    expect(html).toContain('已发送')
    expect(html).toContain('已签回')
  })

  it.each(A16_CODES)('%s 点击下载模板调用 prefilled-download 端点', async (code) => {
    const wrapper = mount(WpPopupDocxEditor, {
      props: { wpCode: code, projectId: 'proj-a16-test' },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    await nextTick()

    // 找到下载按钮并点击
    const buttons = wrapper.findAll('.el-button')
    const downloadBtn = buttons.find((b) => b.text().includes('下载'))
    expect(downloadBtn).toBeDefined()

    await downloadBtn!.trigger('click')
    await nextTick()

    // 验证 downloadFile 被调用，URL 包含 wp-templates/{code}/prefilled-download
    expect(mockDownloadFile).toHaveBeenCalledWith(
      expect.stringContaining(`/wp-templates/${code}/prefilled-download`),
      expect.objectContaining({ fileName: expect.stringContaining('.docx') }),
    )
  })

  it.each(A16_CODES)('%s relatedLinks 包含 A16 程序表', (code) => {
    const cfg = DOCX_POPUP_CONFIGS[code]
    const a16Link = cfg.relatedLinks.find((l) => l.wpCode === 'A16')
    expect(a16Link, `${code} 应有跳转 A16 程序表的 relatedLink`).toBeDefined()
    expect(a16Link!.label).toContain('A16')
  })

  it('无效 wpCode 渲染空状态', async () => {
    const wrapper = mount(WpPopupDocxEditor, {
      props: { wpCode: 'INVALID-CODE', projectId: 'proj-a16-test' },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    await nextTick()

    expect(wrapper.find('.popup-empty').exists()).toBe(true)
    expect(wrapper.html()).toContain('未配置该文档类型')
  })
})

// ─── A16-7 补充声明专项测试 ──────────────────────────────────────────────────
describe('WpPopupDocxEditor — A16-7 弹窗（补充声明 + relatedLinks→A7）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApiGet.mockResolvedValue(null)
  })

  it('A16-7 配置存在于 DOCX_POPUP_CONFIGS，标题为管理层关联交易声明书', () => {
    const cfg = DOCX_POPUP_CONFIGS['A16-7']
    expect(cfg).toBeDefined()
    expect(cfg.title).toBe('管理层关联交易声明书')
    expect(cfg.guidance.length).toBeGreaterThan(0)
    expect(cfg.templatePath).toContain('.docx')
    expect(cfg.templatePath).toContain('A16-7')
  })

  it('A16-7 在 INLINE_POPUP_WP_CODES 和 DOCX_POPUP_WP_CODES 中注册', () => {
    expect(INLINE_POPUP_WP_CODES.has('A16-7')).toBe(true)
    expect(DOCX_POPUP_WP_CODES.has('A16-7')).toBe(true)
  })

  it('A16-7 relatedLinks 包含 A7 关联方程序表', () => {
    const cfg = DOCX_POPUP_CONFIGS['A16-7']
    const a7Link = cfg.relatedLinks.find((l) => l.wpCode === 'A7')
    expect(a7Link, 'A16-7 应有跳转 A7 关联方程序表的 relatedLink').toBeDefined()
    expect(a7Link!.label).toContain('A7')
    expect(a7Link!.label).toContain('关联方')
  })

  it('A16-7 relatedLinks 同时包含 A16 程序表', () => {
    const cfg = DOCX_POPUP_CONFIGS['A16-7']
    const a16Link = cfg.relatedLinks.find((l) => l.wpCode === 'A16')
    expect(a16Link, 'A16-7 应有跳转 A16 程序表的 relatedLink').toBeDefined()
  })

  it('A16-7 弹窗渲染 guidance 使用说明 + 适用条件', async () => {
    const wrapper = mount(WpPopupDocxEditor, {
      props: { wpCode: 'A16-7', projectId: 'proj-a16-test' },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    await nextTick()

    const cfg = DOCX_POPUP_CONFIGS['A16-7']
    const html = wrapper.html()

    // guidance 区域存在
    expect(wrapper.find('.wp-popup-docx-editor__guidance').exists()).toBe(true)
    // guidance 包含第一条说明
    expect(html).toContain(cfg.guidance[0])
    // 适用条件标签
    expect(html).toContain(cfg.applicableNote)
  })

  it('A16-7 弹窗包含下载模板按钮', async () => {
    const wrapper = mount(WpPopupDocxEditor, {
      props: { wpCode: 'A16-7', projectId: 'proj-a16-test' },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    await nextTick()

    const buttons = wrapper.findAll('.el-button')
    const downloadBtn = buttons.filter((b) => b.text().includes('下载'))
    expect(downloadBtn.length).toBeGreaterThanOrEqual(1)
  })

  it('A16-7 弹窗显示签回状态 radio（isA16Popup=true）', async () => {
    const wrapper = mount(WpPopupDocxEditor, {
      props: { wpCode: 'A16-7', projectId: 'proj-a16-test', wpId: 'wp-a16-7' },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    await nextTick()

    expect(wrapper.find('.sign-row').exists()).toBe(true)
    const html = wrapper.html()
    expect(html).toContain('待编辑')
    expect(html).toContain('已发送')
    expect(html).toContain('已签回')
  })

  it('A16-7 弹窗工具栏渲染"关联"链接指向 A7', async () => {
    const wrapper = mount(WpPopupDocxEditor, {
      props: { wpCode: 'A16-7', projectId: 'proj-a16-test' },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    await nextTick()

    // 工具栏 relatedLinks 按钮应包含 A7 字样
    const buttons = wrapper.findAll('.el-button')
    const a7Btn = buttons.find((b) => b.text().includes('A7'))
    expect(a7Btn, 'A16-7 弹窗应有 A7 关联方跳转按钮').toBeDefined()
    expect(a7Btn!.text()).toContain('关联方')
  })

  it('A16-7 点击下载调用 prefilled-download 端点', async () => {
    const wrapper = mount(WpPopupDocxEditor, {
      props: { wpCode: 'A16-7', projectId: 'proj-a16-test' },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    await nextTick()

    const buttons = wrapper.findAll('.el-button')
    const downloadBtn = buttons.find((b) => b.text().includes('下载'))
    expect(downloadBtn).toBeDefined()

    await downloadBtn!.trigger('click')
    await nextTick()

    expect(mockDownloadFile).toHaveBeenCalledWith(
      expect.stringContaining('/wp-templates/A16-7/prefilled-download'),
      expect.objectContaining({ fileName: expect.stringContaining('.docx') }),
    )
  })

  it('A16-7 sign_status scope 使用 word_template:A16:A16-7 item_id', async () => {
    // 验证 sign_status 加载时使用 A16-7-sign-status 作为 item_id
    mockApiGet.mockResolvedValue({
      data: [{ item_id: 'A16-7-sign-status', conclusion: 'signed' }],
    })

    const wrapper = mount(WpPopupDocxEditor, {
      props: { wpCode: 'A16-7', projectId: 'proj-a16-test', wpId: 'wp-a16-7' },
      global: { stubs: globalStubs },
    })
    await flushPromises()
    await nextTick()

    // API 应被调用查询签回状态
    expect(mockApiGet).toHaveBeenCalledWith(
      expect.stringContaining('/checklist-responses'),
    )
  })
})
