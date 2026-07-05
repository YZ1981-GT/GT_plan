/**
 * GtC1EntityControl.integration.spec.ts — C1 企业层面控制测试 端到端集成（Task 6.1）
 *
 * Spec: .kiro/specs/c1-entity-level-control/  Task 6.1
 * Validates: Requirements 2.1, 3.2, 4.4
 *
 * 与 GtC1EntityControl.spec.ts（27 个单元断言）互补：
 *   - 单元 spec 直接读 exposed vm.mode / vm.sampleBalance 等，验证纯逻辑；
 *   - 本文件挂载真实组件，**驱动 mock 的后端 API 流程**（render-config selfLoad +
 *     loadPrograms + checklist-responses GET/PUT），验证渲染层链路：
 *       1. 九段分组 rendering —— selfLoad 下发 section_groups + loadPrograms 下发
 *          带 section slug 的程序步骤 → 九段折叠面板渲染 + 分组透传 GtAProgramConsole
 *       2. applicability trimming —— 整段裁剪写回 checklist-responses（PUT），DOM 呈现
 *          裁剪态且进度排除
 *       3. C1-4-4 sample reconciliation recompute —— 从 responses 重建样本 → 编辑单元
 *          → 借贷勾稽在渲染层实时重算（tfoot 平衡标签变化）
 *       4. sheetName dispatch —— 各 sheet 挂载后渲染正确的顶层容器区块（DOM 级）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { nextTick } from 'vue'

const mockGet = vi.fn()
const mockPut = vi.fn()

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockGet(...args),
    put: (...args: any[]) => mockPut(...args),
  },
}))

const promptMock = vi.fn()
vi.mock('element-plus', () => ({
  ElMessage: { warning: vi.fn(), error: vi.fn(), success: vi.fn() },
  ElMessageBox: { prompt: (...a: any[]) => promptMock(...a), confirm: vi.fn() },
}))

// GtAProgramConsole stub：回显收到的分组程序数（data-programs），用于验证九段分组透传
vi.mock('../GtAProgramConsole.vue', () => ({
  __esModule: true,
  default: {
    name: 'GtAProgramConsole',
    props: ['wpId', 'sheetName', 'schema', 'htmlData', 'readonly', 'hideCategories'],
    template:
      '<div class="a-program-console-stub" :data-programs="(htmlData && htmlData.programs ? htmlData.programs.length : 0)" />',
  },
}))
vi.mock('../GtOnlyOfficeSheet.vue', () => ({
  __esModule: true,
  default: { name: 'GtOnlyOfficeSheet', template: '<div class="onlyoffice-stub" />' },
}))
vi.mock('../GtIndexChip.vue', () => ({
  __esModule: true,
  default: {
    name: 'GtIndexChip',
    props: ['value', 'contextProjectId'],
    template: '<span class="gt-index-chip-stub">{{ value }}</span>',
  },
}))

import GtC1EntityControl from '../GtC1EntityControl.vue'

// slot-rendering stubs：保留 DOM 结构以便端到端断言（区别于单元 spec 只读 vm）
const stubs = {
  'el-skeleton': true,
  'el-collapse': { template: '<div class="el-collapse"><slot /></div>' },
  'el-collapse-item': {
    props: ['name'],
    template: '<div class="el-collapse-item" :data-name="name"><slot name="title" /><slot /></div>',
  },
  'el-progress': {
    props: ['percentage'],
    template: '<span class="el-progress" :data-pct="percentage" />',
  },
  'el-tag': { template: '<span class="el-tag"><slot /></span>' },
  'el-switch': {
    props: ['modelValue'],
    template: '<button class="el-switch" @click="$emit(\'change\', !modelValue)" />',
  },
  'el-alert': {
    props: ['title', 'description'],
    template: '<div class="el-alert"><span class="el-alert__title">{{ title }}</span><slot name="title" /><span class="el-alert__desc">{{ description }}</span><slot /></div>',
  },
  'el-card': { template: '<div class="el-card"><slot name="header" /><slot /></div>' },
  'el-select': true,
  'el-option': true,
  'el-input': true,
  'el-checkbox-group': { template: '<div class="el-checkbox-group-stub"><slot /></div>' },
  'el-checkbox': { props: ['value', 'label'], template: '<label class="el-checkbox-stub">{{ label }}</label>' },
  'el-button': { template: '<button @click="$emit(\'click\')"><slot /></button>' },
  'el-tooltip': { template: '<span><slot /></span>' },
  'el-upload': { template: '<div class="el-upload-stub"><slot /></div>' },
  'el-icon': { template: '<i><slot /></i>' },
}

/** 标准九段 section_groups（后端 render-config 下发形态）；title 加后缀以证明来自后端 */
const BACKEND_SECTION_GROUPS = [
  { slug: 'ce', order: 1, title: '控制环境（后端）', default_applicable: true },
  { slug: 'ra', order: 2, title: '风险评估（后端）', default_applicable: true },
  { slug: 'mo', order: 3, title: '监督（后端）', default_applicable: true },
  { slug: 'bu', order: 4, title: '监控业务单元（后端）', default_applicable: false, note: '集团审计适用' },
  { slug: 'ic', order: 5, title: '信息与沟通（后端）', default_applicable: true },
  { slug: 'fr', order: 6, title: '财务报告（后端）', default_applicable: true },
  { slug: 'el', order: 7, title: '对业务层面控制的影响（后端）', default_applicable: true },
  { slug: 'ye', order: 8, title: '年终程序（后端）', default_applicable: true },
  { slug: 'rp', order: 9, title: '关联方相关内容（后端）', default_applicable: false, note: '有关联方交易适用' },
]

interface MountOpts {
  sheetName: string
  responses?: any[]
  programs?: any[]
  sectionGroups?: any[] | null
  readonly?: boolean
}

/**
 * 挂载组件并按 URL 路由 mock 后端：
 *   - /checklist-responses → responses（C1- 前缀数组）
 *   - render-config?...c1-entity-level-control → { sheets:[{ html_data:{ section_groups } }] }
 *   - render-config?...a-program-console → { sheets:[{ html_data:{ programs } }] }
 *   - /feature-flags → 关闭 AI
 */
function mountC1(opts: MountOpts) {
  const { sheetName, responses = [], programs = [], sectionGroups = BACKEND_SECTION_GROUPS, readonly = false } = opts
  mockGet.mockImplementation((url: string) => {
    if (typeof url !== 'string') return Promise.resolve({})
    if (url.includes('/checklist-responses')) return Promise.resolve(responses)
    if (url.includes('force_component_type=c1-entity-level-control')) {
      return Promise.resolve({ sheets: [{ html_data: sectionGroups ? { section_groups: sectionGroups } : {} }] })
    }
    if (url.includes('force_component_type=a-program-console')) {
      return Promise.resolve({ sheets: [{ html_data: { programs } }] })
    }
    if (url.includes('/feature-flags')) return Promise.resolve({ flags: { WP_AI_SERVICE_ENABLED: false } })
    return Promise.resolve({})
  })
  return mount(GtC1EntityControl, {
    props: { wpId: 'wp-c1', projectId: 'proj-1', wpCode: 'C1', sheetName, readonly },
    global: { stubs },
  })
}

beforeEach(() => {
  mockGet.mockReset()
  mockPut.mockReset()
  mockPut.mockResolvedValue([])
  promptMock.mockReset()
})

// ─────────────────────────────────────────────────────────────────────────────
// 1. 九段分组 rendering（Req 2.1）
// ─────────────────────────────────────────────────────────────────────────────

describe('端到端：九段分组 rendering（Req 2.1）', () => {
  it('selfLoad 下发的 section_groups 驱动九段折叠面板渲染', async () => {
    const wrapper = mountC1({ sheetName: 'C1 企业层面控制测试程序表' })
    await flushPromises()

    const items = wrapper.findAll('.el-collapse-item')
    expect(items.length).toBe(9)
    // 标题来自后端下发（带「（后端）」后缀），证明 selfLoad → applyGroups 链路生效
    const text = wrapper.text()
    expect(text).toContain('控制环境（后端）')
    expect(text).toContain('关联方相关内容（后端）')
    // 九段 slug 全覆盖
    const names = items.map((i) => i.attributes('data-name'))
    expect(names).toEqual(['ce', 'ra', 'mo', 'bu', 'ic', 'fr', 'el', 'ye', 'rp'])
  })

  it('loadPrograms 下发带 section slug 的步骤 → 按九段分流透传 GtAProgramConsole', async () => {
    const programs = [
      { section: 'ce', row: 7, name: 'ce-1' },
      { section: 'ce', row: 11, name: 'ce-2' },
      { section: 'ce', row: 16, name: 'ce-3' },
      { section: 'fr', row: 95, name: 'fr-1' },
      { section: 'fr', row: 98, name: 'fr-2' },
    ]
    const wrapper = mountC1({ sheetName: 'C1 企业层面控制测试程序表', programs })
    await flushPromises()

    // 有分组数据时不渲染兜底单一控制台；每段一个分组控制台
    const consoles = wrapper.findAll('.a-program-console-stub')
    expect(consoles.length).toBe(9)
    const counts = consoles.map((c) => Number(c.attributes('data-programs')))
    // ce=3, fr=2, 其余 0；总数守恒 = 输入步骤数（无遗漏无重复，Property 2）
    expect(counts.reduce((a, b) => a + b, 0)).toBe(5)
    expect(counts).toContain(3)
    expect(counts).toContain(2)
  })

  it('无分组数据时回退单一程序中控台（GtAProgramConsole 内建 grid 兜底，Req 2.4）', async () => {
    const wrapper = mountC1({ sheetName: 'C1 企业层面控制测试程序表', programs: [] })
    await flushPromises()
    // 九段面板内 hint（无分组数据）+ 底部单一 console
    expect(wrapper.find('.c1-program-console').exists()).toBe(true)
  })

  it('selfLoad 失败时回退九段常量兜底仍渲染 9 段', async () => {
    mockGet.mockImplementation((url: string) => {
      if (url.includes('/checklist-responses')) return Promise.resolve([])
      if (url.includes('force_component_type=c1-entity-level-control')) return Promise.reject(new Error('render-config 500'))
      return Promise.resolve({})
    })
    const wrapper = mount(GtC1EntityControl, {
      props: { wpId: 'wp-c1', projectId: 'proj-1', wpCode: 'C1', sheetName: 'C1 企业层面控制测试程序表' },
      global: { stubs },
    })
    await flushPromises()
    expect(wrapper.findAll('.el-collapse-item').length).toBe(9)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 2. applicability trimming behavior（Req 3.2）
// ─────────────────────────────────────────────────────────────────────────────

describe('端到端：适用性裁剪（Req 3.2）', () => {
  it('已裁剪段（不适用）DOM 呈现裁剪提示且进度排除计为 100', async () => {
    const responses = [
      { item_id: 'C1-bu-section-applicable', conclusion: 'N', remark: '非集团审计', wp_ref: null },
    ]
    const wrapper = mountC1({ sheetName: 'C1 企业层面控制测试程序表', responses })
    await flushPromises()

    // bu 段渲染裁剪 alert + 理由
    const buItem = wrapper.findAll('.el-collapse-item').find((i) => i.attributes('data-name') === 'bu')!
    expect(buItem.text()).toContain('本段已标记「不适用」')
    expect(buItem.text()).toContain('非集团审计')
    // 进度条 100（裁剪段不拖累进度，Req 3.3）
    const pct = buItem.find('.el-progress').attributes('data-pct')
    expect(Number(pct)).toBe(100)
  })

  it('标记不适用：弹框收集理由 → PUT 写回 conclusion=N + remark=理由（Req 3.2 即时保存）', async () => {
    promptMock.mockResolvedValue({ value: '本项目无关联方交易' })
    const wrapper = mountC1({ sheetName: 'C1 企业层面控制测试程序表' })
    await flushPromises()

    await (wrapper.vm as any).onToggleSectionApplicable('rp', false)
    await flushPromises()

    expect(promptMock).toHaveBeenCalled()
    expect(mockPut).toHaveBeenCalledTimes(1)
    const body = mockPut.mock.calls[0][1]
    const item = body.items.find((it: any) => it.item_id === 'C1-rp-section-applicable')
    expect(item).toBeTruthy()
    expect(item.conclusion).toBe('N')
    expect(item.remark).toBe('本项目无关联方交易')
    // 裁剪态即时反映
    expect((wrapper.vm as any).isSectionApplicable('rp')).toBe(false)
  })

  it('标记不适用但未填理由（取消弹框）→ 不保存、维持适用', async () => {
    promptMock.mockRejectedValue(new Error('cancel'))
    const wrapper = mountC1({ sheetName: 'C1 企业层面控制测试程序表' })
    await flushPromises()

    await (wrapper.vm as any).onToggleSectionApplicable('rp', false)
    await flushPromises()

    expect(mockPut).not.toHaveBeenCalled()
    expect((wrapper.vm as any).isSectionApplicable('rp')).toBe(true)
  })

  it('恢复适用：PUT 写回 conclusion=Y 且清空理由', async () => {
    const responses = [
      { item_id: 'C1-bu-section-applicable', conclusion: 'N', remark: '非集团审计', wp_ref: null },
    ]
    const wrapper = mountC1({ sheetName: 'C1 企业层面控制测试程序表', responses })
    await flushPromises()

    await (wrapper.vm as any).onToggleSectionApplicable('bu', true)
    await flushPromises()

    expect(mockPut).toHaveBeenCalledTimes(1)
    const item = mockPut.mock.calls[0][1].items.find((it: any) => it.item_id === 'C1-bu-section-applicable')
    expect(item.conclusion).toBe('Y')
    expect(item.remark).toBeNull()
    expect((wrapper.vm as any).isSectionApplicable('bu')).toBe(true)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 3. C1-4-4 sample reconciliation recompute（Req 4.4）
// ─────────────────────────────────────────────────────────────────────────────

describe('端到端：C1-4-4 样本借贷勾稽实时重算（Req 4.4）', () => {
  it('从 checklist-responses 重建样本 → tfoot 渲染借贷平衡标签', async () => {
    const responses = [
      { item_id: 'C1-4-4-sample-0-debit', conclusion: null, remark: '100', wp_ref: null },
      { item_id: 'C1-4-4-sample-0-credit', conclusion: null, remark: '0', wp_ref: null },
      { item_id: 'C1-4-4-sample-1-debit', conclusion: null, remark: '0', wp_ref: null },
      { item_id: 'C1-4-4-sample-1-credit', conclusion: null, remark: '100', wp_ref: null },
    ]
    const wrapper = mountC1({ sheetName: 'C1-4-4企业层面内控测试示例4', responses })
    await flushPromises()

    expect(wrapper.find('.c1-process-sample').exists()).toBe(true)
    const foot = wrapper.find('.c1-sample-foot')
    expect(foot.exists()).toBe(true)
    expect(foot.text()).toContain('借贷平衡')
  })

  it('编辑样本单元 → 渲染层重算：借贷不平 → 平衡（Req 4.4）', async () => {
    const responses = [
      { item_id: 'C1-4-4-sample-0-debit', conclusion: null, remark: '100', wp_ref: null },
      { item_id: 'C1-4-4-sample-0-credit', conclusion: null, remark: '60', wp_ref: null },
    ]
    const wrapper = mountC1({ sheetName: 'C1-4-4企业层面内控测试示例4', responses })
    await flushPromises()

    // 初始 100 vs 60 → 借贷不平
    expect(wrapper.find('.c1-sample-foot').text()).toContain('借贷不平')

    // 编辑贷方 60 → 100，渲染层实时重算为平衡
    ;(wrapper.vm as any).onSampleCell(0, 'credit', '100')
    await nextTick()
    expect(wrapper.find('.c1-sample-foot').text()).toContain('借贷平衡')
  })

  it('新增样本行 + 录入金额 → tfoot 累计合计随之重算', async () => {
    const wrapper = mountC1({ sheetName: 'C1-4-4企业层面内控测试示例4', responses: [] })
    await flushPromises()

    const vm = wrapper.vm as any
    // 无样本行时无 tfoot
    expect(wrapper.find('.c1-sample-foot').exists()).toBe(false)

    vm.addSampleRow()
    vm.addSampleRow()
    vm.onSampleCell(0, 'debit', '250')
    vm.onSampleCell(1, 'credit', '250')
    await nextTick()

    const foot = wrapper.find('.c1-sample-foot')
    expect(foot.exists()).toBe(true)
    expect(foot.text()).toContain('借贷平衡')
    // 合计 250.00 出现在 tfoot（fmtAmount）
    expect(foot.text()).toContain('250.00')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 4. sheetName dispatch across sheets（Req 2.1 分发到位）
// ─────────────────────────────────────────────────────────────────────────────

describe('端到端：sheetName 分发渲染正确顶层区块', () => {
  it.each([
    ['C1 企业层面控制测试程序表', '.c1-program'],
    ['C1-1 企业层面控制测试示例1', '.c1-example'],
    ['C1-3企业层面控制测试示例3', '.c1-example'],
    ['C1-4企业层面内控测试示例4-财务报告内部控制', '.c1-fr-summary'],
    ['C1-4-1企业层面内控测试示例4', '.c1-process-record'],
    ['C1-4-4企业层面内控测试示例4', '.c1-process-sample'],
    ['', '.c1-program'],
    ['未知 sheet 名', '.c1-program'],
  ])('%s → 渲染 %s', async (sheetName, selector) => {
    const wrapper = mountC1({ sheetName })
    await flushPromises()
    expect(wrapper.find(selector).exists()).toBe(true)
  })

  it('示例 sheet 渲染「示例（供参考）」标注 + 只读 OnlyOffice（Req 5.2）', async () => {
    const wrapper = mountC1({ sheetName: 'C1-2 企业层面控制测试示例2' })
    await flushPromises()
    expect(wrapper.find('.c1-example').exists()).toBe(true)
    expect(wrapper.text()).toContain('示例（供参考）')
    expect(wrapper.find('.onlyoffice-stub').exists()).toBe(true)
  })
})
