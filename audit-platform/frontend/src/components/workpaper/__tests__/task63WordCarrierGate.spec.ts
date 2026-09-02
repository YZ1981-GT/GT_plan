/**
 * task63WordCarrierGate.spec.ts — 无 DOCX 载体底稿的编辑入口门控（真实 DOM 断言）
 *
 * spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 6 Task 63
 * Requirements: 7.7, 9.4, 9.5, 12.8
 *
 * ═══ 为什么必须落到 DOM ═══
 *
 * 本 spec 记过一类假绿：「模型/computed 声明了某能力，而任何模板零引用 ⇒ 结构性不可见
 * 的死代码，三层数据守卫全绿」。后端守卫只能检查 `.vue` 源码里有没有那几个 `v-if`
 * 字符串；那条判据在「v-if 写了但被外层另一个 v-if 挡住永不渲染」时仍绿。因此门控是否
 * 真生效，只能由**挂载后的 DOM** 回答。
 *
 * ═══ 三态而不是两态 ═══
 *
 * 门控判据是 `has_usable_carrier === false`（显式比较），故必须覆盖三种输入：
 *   ① false      ⇒ 不渲染任何编辑入口
 *   ② true       ⇒ 照常渲染
 *   ③ 字段缺失   ⇒ 照常渲染（老 render 路径 / A16 bundle 内嵌宿主）
 * 只测 ①② 的话，把判据改成 `!has_usable_carrier` 仍然全绿，而那个改法会让 ③ 也被
 * 误判成「无载体」，把 28 个 word-template 底稿的编辑入口全部藏掉。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { h } from 'vue'
import WorkpaperWordEditor from '../WorkpaperWordEditor.vue'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'proj-t63' }, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

const mockApiGet = vi.fn()
const mockApiPost = vi.fn().mockResolvedValue({})
const mockApiPut = vi.fn().mockResolvedValue({})
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: (...args: any[]) => mockApiGet(...args),
    post: (...args: any[]) => mockApiPost(...args),
    put: (...args: any[]) => mockApiPut(...args),
  },
}))

vi.mock('../OnlyOfficeWordDialog.vue', () => ({
  default: { name: 'OnlyOfficeWordDialog', template: '<div class="mock-oo" />', props: ['visible', 'documentUrl', 'documentKey', 'title', 'mode', 'callbackUrl'] },
}))

/** el-segmented 的可识别 stub —— 双模式切换器存在性的唯一 DOM 判据。 */
const elSegmentedStub = {
  name: 'ElSegmented',
  props: ['modelValue', 'options', 'size'],
  emits: ['update:modelValue', 'change'],
  setup(props: any) {
    return () =>
      h(
        'div',
        { class: 'el-segmented-stub', 'data-testid': 'dual-mode-switch' },
        (props.options || []).map((opt: string) => h('button', { class: 'el-segmented-item' }, opt)),
      )
  },
}

const stubs = {
  'el-segmented': elSegmentedStub,
  'el-tooltip': { template: '<div class="el-tooltip-stub"><slot /></div>', props: ['content', 'disabled', 'placement'] },
  'el-alert': {
    template: '<div class="el-alert" :data-type="type"><slot name="title" /><slot /></div>',
    props: ['type', 'closable', 'showIcon', 'title'],
  },
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>', props: ['type', 'size', 'loading', 'disabled', 'icon'] },
  'el-button-group': { template: '<div><slot /></div>' },
  'el-divider': { template: '<span />', props: ['direction'] },
  'el-tag': { template: '<span class="el-tag"><slot /></span>', props: ['type', 'size', 'effect'] },
  'el-skeleton': { template: '<div class="el-skeleton" />', props: ['rows', 'animated'] },
  'el-empty': { template: '<div class="el-empty" :data-desc="description" />', props: ['description'] },
  'el-dialog': { template: '<div v-if="modelValue"><slot /><slot name="footer" /></div>', props: ['modelValue', 'title', 'width', 'closeOnClickModal'], emits: ['update:modelValue'] },
  'el-upload': { template: '<div><slot /></div>', props: ['action', 'headers', 'onSuccess', 'accept', 'limit', 'drag'] },
  'el-radio-group': { template: '<div><slot /></div>', props: ['modelValue', 'size'], emits: ['update:modelValue', 'change'] },
  'el-radio-button': { template: '<label><slot /></label>', props: ['value'] },
  'el-switch': { template: '<input type="checkbox" />', props: ['modelValue', 'activeText'], emits: ['update:modelValue', 'change'] },
  'el-descriptions': { template: '<div><slot /></div>', props: ['column', 'border', 'size', 'title'] },
  'el-descriptions-item': { template: '<div><slot /></div>', props: ['label'] },
  'el-date-picker': { template: '<input />', props: ['modelValue', 'type', 'placeholder', 'valueFormat'], emits: ['update:modelValue'] },
  GtWordTemplateStructuredView: { template: '<div class="gt-structured-view-stub" />', props: ['templateStructure', 'fieldValues', 'readonly'] },
}

/** 无载体底稿的 render-config 载荷（形态逐字对齐后端 `_carrier_absence_payload`）。 */
function absentCarrierHtmlData(wpCode: string, verdict: string) {
  return {
    template_structure: null,
    filled_responses: {},
    sign_status: null,
    word_carrier: { wp_code: wpCode, verdict, has_usable_carrier: false },
  }
}

function mountEditor(wpCode: string, htmlData?: any) {
  return mount(WorkpaperWordEditor, {
    props: { wpId: `wp-t63-${wpCode}`, wpCode, projectId: 'proj-t63', htmlData },
    global: { stubs },
  })
}

describe('Task 63: 无 DOCX 载体底稿的编辑入口门控', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockApiGet.mockImplementation((url: string) => {
      if (url.includes('/onlyoffice/health')) return Promise.resolve({ healthy: true, available: true })
      if (url.includes('/projects/')) return Promise.resolve({ client_name: '测试', audit_year: '2025' })
      if (url.includes('/template-structure')) {
        return Promise.resolve({ placeholders: [], paragraphs: [], tables: [], metadata: {} })
      }
      return Promise.resolve({})
    })
  })

  // ── ① has_usable_carrier === false ⇒ 入口全部不渲染 ────────────────────

  it('template_missing：不渲染双模式切换器、结构化视图与在线编辑区', async () => {
    const w = mountEditor('S33-REV', absentCarrierHtmlData('S33-REV', 'template_missing'))
    await flushPromises()

    expect(w.find('[data-testid="dual-mode-switch"]').exists()).toBe(false)
    expect(w.find('.gt-wp-word-editor__structured-area').exists()).toBe(false)
    expect(w.find('.gt-wp-word-editor__editor-area').exists()).toBe(false)
    // 缺失说明必须真出现 —— 否则页面就是一片空白，比误导文案更糟
    expect(w.find('.gt-wp-word-editor__no-carrier').exists()).toBe(true)
    expect(w.text()).toContain('本底稿暂无 Word 模板')
  })

  it('template_missing：不显示「请使用在线编辑模式」这类把人指向死路的文案', async () => {
    const w = mountEditor('S33-REV', absentCarrierHtmlData('S33-REV', 'template_missing'))
    await flushPromises()

    // 原实现的 el-empty description 正是这句；它对零载体底稿是错的引导。
    expect(w.text()).not.toContain('请使用在线编辑模式')
    const empties = w.findAll('.el-empty')
    for (const e of empties) {
      expect(e.attributes('data-desc') || '').not.toContain('在线编辑')
    }
  })

  it('template_missing：不发起结构化取数与 onlyoffice-config 请求', async () => {
    const w = mountEditor('S33-REV', absentCarrierHtmlData('S33-REV', 'template_missing'))
    await flushPromises()

    const urls = mockApiGet.mock.calls.map((c) => String(c[0]))
    // 🔴 URL 必须与实现逐字对齐：`useWordTemplateStructured.loadStructure()` 请求的是
    //    `render-config?force_component_type=word-template`，**不是** `/template-structure`。
    //    首版断言写成后者 ⇒ 该 URL 从不出现 ⇒ 断言恒真，变异检验判 GREEN（M11）后才发现
    //    这是一条重言式。断言外部依赖的 URL 时必须回到调用点核对。
    expect(urls.some((u) => u.includes('force_component_type=word-template'))).toBe(false)
    expect(urls.some((u) => u.includes('/onlyoffice-config'))).toBe(false)
    expect(w.exists()).toBe(true)
  })

  it('有载体时这两个请求确实会发出 ⇒ 上一条断言不是重言式', async () => {
    const w = mountEditor('B2-1', {
      template_structure: { placeholders: [], paragraphs: [], tables: [], metadata: {} },
      word_carrier: { wp_code: 'B2-1', verdict: 'resolved_docx', has_usable_carrier: true },
    })
    await flushPromises()

    const urls = mockApiGet.mock.calls.map((c) => String(c[0]))
    expect(urls.some((u) => u.includes('force_component_type=word-template'))).toBe(true)
    expect(w.exists()).toBe(true)
  })

  it('document_type_mismatch：同样门控，且文案指出只有工作簿载体', async () => {
    const w = mountEditor('B99-XLSX-ONLY', absentCarrierHtmlData('B99-XLSX-ONLY', 'document_type_mismatch'))
    await flushPromises()

    expect(w.find('[data-testid="dual-mode-switch"]').exists()).toBe(false)
    expect(w.text()).toContain('只有工作簿')
  })

  // ── ② has_usable_carrier === true ⇒ 原行为不变 ─────────────────────────

  it('有载体（has_usable_carrier=true）：照常渲染双模式切换器', async () => {
    const w = mountEditor('B2-1', {
      template_structure: { placeholders: [], paragraphs: [], tables: [], metadata: {} },
      filled_responses: {},
      word_carrier: { wp_code: 'B2-1', verdict: 'resolved_docx', has_usable_carrier: true },
    })
    await flushPromises()

    expect(w.find('[data-testid="dual-mode-switch"]').exists()).toBe(true)
    expect(w.find('.gt-wp-word-editor__no-carrier').exists()).toBe(false)
  })

  // ── ③ 字段缺失 ⇒ 原行为不变（这条是判据形态的关键） ────────────────────

  it('htmlData 未提供 word_carrier：保持原行为，仍渲染切换器', async () => {
    const w = mountEditor('B40-1')
    await flushPromises()

    expect(w.find('[data-testid="dual-mode-switch"]').exists()).toBe(true)
    expect(w.find('.gt-wp-word-editor__no-carrier').exists()).toBe(false)
  })

  it('word_carrier 存在但 has_usable_carrier 缺失：按原行为处理，不误藏入口', async () => {
    const w = mountEditor('B2-6', { word_carrier: { wp_code: 'B2-6', verdict: 'resolved_docx' } })
    await flushPromises()

    expect(w.find('[data-testid="dual-mode-switch"]').exists()).toBe(true)
  })

  // ── ④ 判据来源：不得按 wp_code 字面量判 ───────────────────────────────

  it('同一个 wp_code 在两种载荷下表现相反 ⇒ 判据来自后端而非 wp_code', async () => {
    const gated = mountEditor('S33-REV', absentCarrierHtmlData('S33-REV', 'template_missing'))
    await flushPromises()
    expect(gated.find('[data-testid="dual-mode-switch"]').exists()).toBe(false)

    // 同一个 wp_code，后端说有载体 ⇒ 必须渲染。若组件按 wp_code 字面量判，这条会红。
    const open = mountEditor('S33-REV', {
      template_structure: { placeholders: [], paragraphs: [], tables: [], metadata: {} },
      word_carrier: { wp_code: 'S33-REV', verdict: 'resolved_docx', has_usable_carrier: true },
    })
    await flushPromises()
    expect(open.find('[data-testid="dual-mode-switch"]').exists()).toBe(true)
  })
})
