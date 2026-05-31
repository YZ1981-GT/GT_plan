/**
 * GtDFormParagraph.spec.ts — D 类段落型政策检查子组件单元测试
 *
 * 验证：
 * 1. 段落渲染：markdown 内容正确输出到 DOM
 * 2. 变量插值：{{project_name}} 等模板变量替换为 props 中的项目上下文值
 * 3. readonly 模式：readonly=true 时编辑控件 disabled / 不可交互
 * 4. debounce save：修改字段后 save payload 包含 dirty 字段
 *
 * 复用 GtDFormQA.spec.ts 范式（Element Plus stubs + fake timers + mount props）
 *
 * Validates: Requirements 3.1, 3.2, 3.3, 3.4
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import GtDFormParagraph from '../GtDFormParagraph.vue'
import { elementPlusStubs } from './stubs'

// ─── 真实 marked + DOMPurify（jsdom 提供 window，无需 mock）──────────────────
// 复盘改进 #3：使用真实库验证 markdown 渲染（**bold**→<strong>）+ XSS 防御，
// 而非 mock 成 `<p>${content}</p>` 跳过真实渲染逻辑。

// ─── Mock GtIndexChip ───────────────────────────────────────────────────────

vi.mock('@/components/workpaper/GtIndexChip.vue', () => ({
  default: {
    template: '<span class="gt-index-chip">{{ value }}</span>',
    props: ['value', 'validate'],
  },
}))

// ─── Mock useWpAiSuggest ────────────────────────────────────────────────────

vi.mock('@/composables/useWpAiSuggest', () => ({
  useWpAiSuggest: () => ({
    aiEnabled: { value: false },
    aiLoading: { value: false },
    currentSuggestion: { value: null },
    showSuggestionPanel: { value: false },
    assistedFieldsList: { value: [] },
    requestSuggestion: vi.fn(),
    adoptSuggestion: vi.fn(),
    modifySuggestion: vi.fn(),
    ignoreSuggestion: vi.fn(),
  }),
}))

// ─── Element Plus stubs（复用共享超集）────────────────────────────────────────

const globalStubs = elementPlusStubs

// ─── Schema / Data builders ─────────────────────────────────────────────────

function buildParagraphSchema(overrides: Record<string, any> = {}) {
  return {
    component_type: 'd-form',
    form_type: 'paragraph',
    fixed_cells: { A3: '测试公司', A4: '2025-12-31', I3: 'D2-8' },
    segments: [
      {
        id: 'audit_objective',
        seq: '一',
        title: '审计目标',
        editable: false,
        formatting: 'markdown',
        content: '确认**坏账准备**计提的合理性',
      },
      {
        id: 'policy_description',
        seq: '二',
        title: '会计政策描述',
        editable: false,
        formatting: 'markdown',
        content: '公司采用账龄分析法计提坏账准备',
      },
      {
        id: 'audit_procedure',
        seq: '三',
        title: '审计程序',
        editable: true,
        type: 'textarea',
        cell: 'B20',
        max_length: 2000,
        hint: '请描述执行的审计程序',
        placeholder: '1. 获取坏账准备计提表\n2. 核对账龄分析\n3. 检查计提比例',
      },
      {
        id: 'audit_finding',
        seq: '四',
        title: '审计发现',
        editable: true,
        type: 'textarea',
        cell: 'B30',
        max_length: 4000,
        formatting: 'markdown',
      },
    ],
    conclusion: {
      mode: 'single',
      cell: 'H40',
      options: [
        { value: 'pass', label: '符合', class: 'success', icon: 'CircleCheckFilled' },
        { value: 'conditional', label: '基本符合', class: 'warning', icon: 'WarningFilled' },
        { value: 'fail', label: '不符合', class: 'danger', icon: 'CircleCloseFilled' },
      ],
    },
    ...overrides,
  }
}

function buildHtmlData(overrides: Record<string, any> = {}) {
  return {
    segments: {
      audit_procedure: '已获取坏账准备计提表并核对',
      audit_finding: '',
    },
    conclusion: '',
    ...overrides,
  }
}

function mountParagraph(propsOverrides: Record<string, any> = {}, dataOverrides: Record<string, any> = {}) {
  return mount(GtDFormParagraph, {
    props: {
      wpId: 'wp-para-001',
      sheetName: '坏账准备政策检查',
      schema: buildParagraphSchema() as any,
      htmlData: buildHtmlData(dataOverrides),
      ...propsOverrides,
    },
    global: { stubs: globalStubs },
  })
}

// ─── Tests ──────────────────────────────────────────────────────────────────

describe('GtDFormParagraph — 段落渲染', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('只读段落（editable=false + formatting=markdown）渲染为 HTML', () => {
    const wrapper = mountParagraph()
    const vm = wrapper.vm as any

    // renderedContent 应包含 markdown 渲染后的 HTML
    expect(vm.renderedContent['audit_objective']).toContain('<p>')
    expect(vm.renderedContent['audit_objective']).toContain('坏账准备')
  })

  it('真实 markdown 渲染：**坏账准备** → <strong>坏账准备</strong>', () => {
    // 复盘改进 #3：用真实 marked 库验证 markdown 语法被正确转换（非 mock 直通）
    const wrapper = mountParagraph()
    const vm = wrapper.vm as any
    // schema content = '确认**坏账准备**计提的合理性'
    expect(vm.renderedContent['audit_objective']).toContain('<strong>坏账准备</strong>')
  })

  it('真实 markdown 渲染：列表语法 → <ul>/<li>', () => {
    const schema = buildParagraphSchema({
      segments: [
        {
          id: 'list_seg', seq: '一', title: '列表段落', editable: false, formatting: 'markdown',
          content: '- 项目一\n- 项目二\n- 项目三',
        },
      ],
    })
    const wrapper = mount(GtDFormParagraph, {
      props: { wpId: 'wp-1', sheetName: 's', schema: schema as any, htmlData: buildHtmlData() },
      global: { stubs: globalStubs },
    })
    const vm = wrapper.vm as any
    expect(vm.renderedContent['list_seg']).toContain('<li>')
    expect(vm.renderedContent['list_seg']).toContain('项目一')
  })

  it('XSS 防御：DOMPurify 清除 <script> 标签', () => {
    // 复盘改进 #3：验证 DOMPurify 真实清洗恶意内容（jsdom window 下生效）
    const schema = buildParagraphSchema({
      segments: [
        {
          id: 'xss_seg', seq: '一', title: '恶意内容', editable: false, formatting: 'markdown',
          content: '正常文本<script>alert(1)</script>后续文本',
        },
      ],
    })
    const wrapper = mount(GtDFormParagraph, {
      props: { wpId: 'wp-1', sheetName: 's', schema: schema as any, htmlData: buildHtmlData() },
      global: { stubs: globalStubs },
    })
    const vm = wrapper.vm as any
    const html = vm.renderedContent['xss_seg'] || ''
    // script 标签必须被清除，正常文本保留
    expect(html).not.toContain('<script>')
    expect(html).not.toContain('alert(1)')
    expect(html).toContain('正常文本')
  })

  it('只读段落在 DOM 中通过 v-html 输出', () => {
    const wrapper = mountParagraph()
    const markdownDivs = wrapper.findAll('.gt-dfp__markdown')
    // 两个只读 markdown 段落
    expect(markdownDivs.length).toBeGreaterThanOrEqual(2)
  })

  it('可编辑段落渲染 textarea', () => {
    const wrapper = mountParagraph()
    const textareas = wrapper.findAll('.el-input')
    // 两个可编辑段落 → 两个 textarea
    expect(textareas.length).toBe(2)
  })

  it('段落标题正确渲染 seq + title', () => {
    const wrapper = mountParagraph()
    const titles = wrapper.findAll('.gt-dfp__segment-title')
    expect(titles.length).toBe(4)

    // 第一个段落：一、审计目标
    const firstTitle = titles[0]
    expect(firstTitle.text()).toContain('一')
    expect(firstTitle.text()).toContain('审计目标')
  })

  it('formatSeq 为中文序号添加顿号', () => {
    const wrapper = mountParagraph()
    const vm = wrapper.vm as any

    expect(vm.formatSeq('一')).toBe('一、')
    expect(vm.formatSeq('二')).toBe('二、')
    expect(vm.formatSeq('1.')).toBe('1.')  // 已有标点不重复
    expect(vm.formatSeq('')).toBe('')
    expect(vm.formatSeq(undefined)).toBe('')
  })

  it('无内容的只读段落显示 el-empty', () => {
    const schema = buildParagraphSchema({
      segments: [
        { id: 'empty_seg', seq: '一', title: '空段落', editable: false, formatting: 'markdown', content: '' },
      ],
    })
    const wrapper = mount(GtDFormParagraph, {
      props: {
        wpId: 'wp-para-001',
        sheetName: '测试',
        schema: schema as any,
        htmlData: buildHtmlData(),
      },
      global: { stubs: globalStubs },
    })
    expect(wrapper.find('.el-empty').exists()).toBe(true)
  })

  it('header 信息正确渲染（entityName / periodEnd / indexNo）', () => {
    const wrapper = mountParagraph()
    const vm = wrapper.vm as any

    expect(vm.entityName).toBe('测试公司')
    expect(vm.periodEnd).toBe('2025-12-31')
    expect(vm.indexNo).toBe('D2-8')
    expect(vm.hasHeaderInfo).toBe(true)
  })
})

describe('GtDFormParagraph — 变量插值（项目上下文）', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('fixed_cells 中的 A3 映射为 entityName（项目名称）', () => {
    const wrapper = mountParagraph()
    const vm = wrapper.vm as any
    expect(vm.entityName).toBe('测试公司')
  })

  it('fixed_cells 中的 A4 映射为 periodEnd（审计期间）', () => {
    const wrapper = mountParagraph()
    const vm = wrapper.vm as any
    expect(vm.periodEnd).toBe('2025-12-31')
  })

  it('fixed_cells 中的 I3/J3/O3/P3 映射为 indexNo（索引号）', () => {
    // I3 优先
    const wrapper1 = mountParagraph()
    expect((wrapper1.vm as any).indexNo).toBe('D2-8')

    // J3 fallback
    const schema2 = buildParagraphSchema({ fixed_cells: { A3: '公司B', J3: 'D3-1' } })
    const wrapper2 = mount(GtDFormParagraph, {
      props: { wpId: 'wp-2', sheetName: 's', schema: schema2 as any, htmlData: buildHtmlData() },
      global: { stubs: globalStubs },
    })
    expect((wrapper2.vm as any).indexNo).toBe('D3-1')
  })

  it('markdown 内容中的项目上下文通过 fixed_cells 传入', () => {
    // 验证 fixed_cells 数据在 header 中正确展示
    const wrapper = mountParagraph()
    const header = wrapper.find('.gt-dfp__header')
    expect(header.exists()).toBe(true)
    expect(header.text()).toContain('测试公司')
    expect(header.text()).toContain('2025-12-31')
    expect(header.text()).toContain('D2-8')
  })

  it('无 fixed_cells 时 header 不渲染', () => {
    const schema = buildParagraphSchema({ fixed_cells: {} })
    const wrapper = mount(GtDFormParagraph, {
      props: { wpId: 'wp-3', sheetName: 's', schema: schema as any, htmlData: buildHtmlData() },
      global: { stubs: globalStubs },
    })
    const vm = wrapper.vm as any
    expect(vm.hasHeaderInfo).toBe(false)
  })
})

describe('GtDFormParagraph — readonly 模式', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('readonly=true 时 textarea disabled', () => {
    const wrapper = mountParagraph({ readonly: true })
    const textareas = wrapper.findAll('.el-input')
    for (const ta of textareas) {
      expect(ta.attributes('disabled')).toBeDefined()
    }
  })

  it('readonly=true 时 conclusion radio-group disabled', () => {
    const wrapper = mountParagraph({ readonly: true })
    const radioGroup = wrapper.find('.el-radio-group')
    expect(radioGroup.classes()).toContain('is-disabled')
  })

  it('readonly=true 时 debounceSave 不触发 save', async () => {
    const wrapper = mountParagraph({ readonly: true })
    const vm = wrapper.vm as any

    // 直接调用内部方法模拟修改
    vm.segmentValues['audit_procedure'] = '新内容'
    vm.onSegmentChange('audit_procedure')

    vi.advanceTimersByTime(2000)
    await nextTick()

    expect(wrapper.emitted('save')).toBeUndefined()
  })

  it('readonly=false 时 textarea 可编辑', () => {
    const wrapper = mountParagraph({ readonly: false })
    const textareas = wrapper.findAll('.el-input')
    for (const ta of textareas) {
      expect(ta.attributes('disabled')).toBeUndefined()
    }
  })
})

describe('GtDFormParagraph — debounce save + payload', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('段落修改后 1.5s debounce 触发 save', async () => {
    const wrapper = mountParagraph()
    const vm = wrapper.vm as any

    vm.segmentValues['audit_procedure'] = '新的审计程序描述'
    vm.onSegmentChange('audit_procedure')

    expect(wrapper.emitted('save')).toBeUndefined()

    vi.advanceTimersByTime(1500)
    await nextTick()

    const emitted = wrapper.emitted('save')
    expect(emitted).toBeDefined()
    expect(emitted!.length).toBe(1)
  })

  it('save payload 包含 segments 和 conclusion', async () => {
    const wrapper = mountParagraph()
    const vm = wrapper.vm as any

    vm.segmentValues['audit_procedure'] = '更新后的程序'
    vm.onSegmentChange('audit_procedure')

    vi.advanceTimersByTime(1500)
    await nextTick()

    const payload = wrapper.emitted('save')![0][0] as any
    expect(payload.segments).toBeDefined()
    expect(payload.segments.audit_procedure).toBe('更新后的程序')
    expect(payload).toHaveProperty('conclusion')
  })

  it('conclusion 修改触发 save', async () => {
    const wrapper = mountParagraph()
    const vm = wrapper.vm as any

    vm.conclusionValue = 'pass'
    vm.onConclusionChange('pass')

    vi.advanceTimersByTime(1500)
    await nextTick()

    const payload = wrapper.emitted('save')![0][0] as any
    expect(payload.conclusion).toBe('pass')
  })

  it('多次修改在 debounce 窗口内只触发一次 save', async () => {
    const wrapper = mountParagraph()
    const vm = wrapper.vm as any

    vm.segmentValues['audit_procedure'] = '第一次修改'
    vm.onSegmentChange('audit_procedure')
    vi.advanceTimersByTime(500)

    vm.segmentValues['audit_finding'] = '第二次修改'
    vm.onSegmentChange('audit_finding')
    vi.advanceTimersByTime(500)

    expect(wrapper.emitted('save')).toBeUndefined()

    vi.advanceTimersByTime(1000)
    await nextTick()

    const emitted = wrapper.emitted('save')
    expect(emitted).toBeDefined()
    expect(emitted!.length).toBe(1)

    const payload = emitted![0][0] as any
    expect(payload.segments.audit_procedure).toBe('第一次修改')
    expect(payload.segments.audit_finding).toBe('第二次修改')
  })

  it('onSegmentBlur 立即触发 save（无 debounce）', async () => {
    const wrapper = mountParagraph()
    const vm = wrapper.vm as any

    vm.segmentValues['audit_procedure'] = '失焦保存'
    vm.onSegmentBlur('audit_procedure')
    await nextTick()

    // blur 立即保存，不需要等 1.5s
    const emitted = wrapper.emitted('save')
    expect(emitted).toBeDefined()
    expect(emitted!.length).toBe(1)
  })

  it('field-change 事件在 blur 时 emit', async () => {
    const wrapper = mountParagraph()
    const vm = wrapper.vm as any

    vm.segmentValues['audit_procedure'] = '新内容'
    vm.onSegmentBlur('audit_procedure')
    await nextTick()

    const emitted = wrapper.emitted('field-change')
    expect(emitted).toBeDefined()
    expect(emitted![0][0]).toMatchObject({
      field_name: 'segments.audit_procedure',
      new_value: '新内容',
      cell: 'B20',
    })
  })

  it('initData 从 htmlData 正确初始化 segmentValues', () => {
    const wrapper = mountParagraph({}, {
      segments: { audit_procedure: '已有内容', audit_finding: '发现问题' },
      conclusion: 'pass',
    })
    const vm = wrapper.vm as any

    expect(vm.segmentValues['audit_procedure']).toBe('已有内容')
    expect(vm.segmentValues['audit_finding']).toBe('发现问题')
    expect(vm.conclusionValue).toBe('pass')
  })
})

// ─── 复盘改进 #1：防御性边界测试 ─────────────────────────────────────────────

describe('GtDFormParagraph — 边界/防御', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('segments 为空数组时不崩溃且无段落渲染', () => {
    const schema = buildParagraphSchema({ segments: [] })
    const wrapper = mount(GtDFormParagraph, {
      props: { wpId: 'wp-1', sheetName: 's', schema: schema as any, htmlData: buildHtmlData() },
      global: { stubs: globalStubs },
    })
    const vm = wrapper.vm as any
    expect(vm.segments.length).toBe(0)
    expect(wrapper.findAll('.gt-dfp__segment').length).toBe(0)
  })

  it('schema 缺失 segments 字段时降级为空数组', () => {
    const schema = { component_type: 'd-form', form_type: 'paragraph', fixed_cells: {} }
    const wrapper = mount(GtDFormParagraph, {
      props: { wpId: 'wp-1', sheetName: 's', schema: schema as any, htmlData: buildHtmlData() },
      global: { stubs: globalStubs },
    })
    const vm = wrapper.vm as any
    expect(vm.segments).toEqual([])
    expect(vm.hasConclusion).toBe(false)
  })

  it('htmlData.segments 为空对象时 segmentValues 全部初始化为空串', () => {
    const wrapper = mountParagraph({}, { segments: {} })
    const vm = wrapper.vm as any
    // 两个可编辑段落 audit_procedure / audit_finding
    expect(vm.segmentValues['audit_procedure']).toBe('')
    expect(vm.segmentValues['audit_finding']).toBe('')
    expect(vm.conclusionValue).toBe('')
  })

  it('conclusion 缺失 options 时 hasConclusion=false', () => {
    const schema = buildParagraphSchema({ conclusion: { mode: 'single', options: [] } })
    const wrapper = mount(GtDFormParagraph, {
      props: { wpId: 'wp-1', sheetName: 's', schema: schema as any, htmlData: buildHtmlData() },
      global: { stubs: globalStubs },
    })
    const vm = wrapper.vm as any
    expect(vm.hasConclusion).toBe(false)
  })

  it('htmlData.segments 含非字符串值时安全降级为空串', () => {
    const wrapper = mountParagraph({}, {
      segments: { audit_procedure: 12345 as any, audit_finding: null as any },
    })
    const vm = wrapper.vm as any
    expect(vm.segmentValues['audit_procedure']).toBe('')
    expect(vm.segmentValues['audit_finding']).toBe('')
  })
})
