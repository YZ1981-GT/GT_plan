/**
 * KnowledgeBase.vue —— 深链 + 写按钮门控（spec knowledge-base-retrieval-and-authz-closure Task 10）
 *
 * Req 5.10：`/knowledge?folder_id=…&doc_id=…` 选中文件夹并打开预览；只给 doc_id 时先调预览接口取
 *           folder_id；不可读 / 不存在 → 中文提示且不选中任何东西（与后端 404 同构，不区分两者）。
 * Req 6.8：写按钮按后端下发的 can_manage / can_create 与系统角色门控；readonly / 未知角色隐藏全部
 *           写按钮（即便后端标志为真，也按角色兜底）；批量删除对 403 / 404 单独计数提示。
 * 另：搜索结果视图显示所在文件夹路径与命中片段；无后缀文件名按 file_type 分流预览（AI 笔记）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { defineComponent, h, inject, provide, reactive, type PropType } from 'vue'

const state = vi.hoisted(() => ({
  route: null as any,
  role: 'auditor' as string | null,
  setCurrentKey: vi.fn(),
  message: { success: vi.fn(), warning: vi.fn(), info: vi.fn(), error: vi.fn() },
  notify: vi.fn(),
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}))

vi.mock('vue-router', () => ({
  useRoute: () => state.route,
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ user: state.role === null ? null : { role: state.role } }),
}))
vi.mock('@/services/apiProxy', () => ({ api: state.api, default: state.api }))
vi.mock('element-plus', () => ({
  ElMessage: state.message,
  ElMessageBox: { prompt: vi.fn() },
  ElNotification: (...args: any[]) => state.notify(...args),
}))
vi.mock('@/utils/confirm', () => ({
  confirmDelete: vi.fn().mockResolvedValue(undefined),
  confirmBatch: vi.fn().mockResolvedValue(undefined),
  confirmDangerous: vi.fn().mockResolvedValue(undefined),
}))
vi.mock('@/utils/errorHandler', () => ({ handleApiError: vi.fn() }))
vi.mock('@/utils/http', () => ({ downloadFile: vi.fn() }))
vi.mock('@/utils/authToken', () => ({ getAuthHeaders: () => ({}) }))
vi.mock('@/composables/useWorkflowGuide', () => ({ showGuide: vi.fn() }))
vi.mock('@/composables/useAiHostContext', () => ({ buildKnowledgeFolderHost: () => ({}) }))
vi.mock('@/components/ai/PlatformAiChatPanel.vue', async () => {
  const vue = await import('vue')
  return { default: vue.defineComponent({ name: 'PlatformAiChatPanel', render: () => null }) }
})
vi.mock('@/components/common/GtPageHeader.vue', async () => {
  const vue = await import('vue')
  return {
    default: vue.defineComponent({
      setup: (_p, { slots }) => () => vue.h('div', { class: 'page-header' }, slots.actions?.()),
    }),
  }
})
vi.mock('@/components/common/GtToolbar.vue', async () => {
  const vue = await import('vue')
  return {
    default: vue.defineComponent({
      setup: (_p, { slots }) => () => vue.h('div', { class: 'toolbar' }, [slots.left?.(), slots.right?.()]),
    }),
  }
})
vi.mock('@element-plus/icons-vue', () => ({ Upload: { render: () => null }, FolderOpened: { render: () => null } }))

import KnowledgeBase from '../KnowledgeBase.vue'

// ─── element-plus 替身：只保留本页逻辑依赖的行为（插槽 / v-model / 事件 / 可选列） ───
const ROW_KEY = Symbol('kb-row')
const TABLE_KEY = Symbol('kb-table')

const passthrough = (cls: string) =>
  defineComponent({ setup: (_p, { slots }) => () => h('div', { class: cls }, slots.default?.()) })

const RowProvider = defineComponent({
  props: { row: { type: Object, required: true } },
  setup(props, { slots }) {
    provide(ROW_KEY, () => props.row)
    return () => h('div', { class: 'kb-row', 'data-id': (props.row as any).id }, slots.default?.())
  },
})

const ElTableStub = defineComponent({
  name: 'ElTable',
  props: { data: { type: Array as PropType<any[]>, default: () => [] } },
  emits: ['selection-change', 'row-click'],
  setup(props, { slots, emit }) {
    const selected = new Set<any>()
    provide(TABLE_KEY, {
      toggle(row: any) {
        if (selected.has(row)) selected.delete(row)
        else selected.add(row)
        emit('selection-change', props.data.filter((r) => selected.has(r)))
      },
    })
    return () =>
      h('div', { class: 'el-table' },
        props.data.map((row) => h(RowProvider, { row, key: row.id }, () => slots.default?.())))
  },
})

const ElTableColumnStub = defineComponent({
  name: 'ElTableColumn',
  props: {
    type: String,
    prop: String,
    label: String,
    selectable: Function as PropType<(row: any) => boolean>,
  },
  setup(props, { slots }) {
    const getRow = inject<() => any>(ROW_KEY, () => ({}))
    const table = inject<any>(TABLE_KEY, null)
    return () => {
      const row = getRow()
      if (props.type === 'selection') {
        const enabled = props.selectable ? props.selectable(row) : true
        return h('input', {
          type: 'checkbox',
          class: 'kb-select',
          disabled: !enabled,
          onClick: () => enabled && table?.toggle(row),
        })
      }
      const content = slots.default ? slots.default({ row }) : String(row?.[props.prop ?? ''] ?? '')
      return h('span', { class: 'kb-cell', 'data-label': props.label }, content)
    }
  },
})

const ElTreeStub = defineComponent({
  name: 'ElTree',
  props: { data: { type: Array as PropType<any[]>, default: () => [] } },
  emits: ['node-click'],
  setup(props, { slots, emit, expose }) {
    expose({ setCurrentKey: state.setCurrentKey })
    const walk = (nodes: any[]): any[] =>
      nodes.flatMap((n) => [
        h('div', { class: 'kb-node', 'data-id': n.id, onClick: () => emit('node-click', n) },
          slots.default?.({ data: n })),
        ...walk(n.children ?? []),
      ])
    return () => h('div', { class: 'el-tree' }, walk(props.data))
  },
})

const ElButtonStub = defineComponent({
  name: 'ElButton',
  inheritAttrs: false,
  props: { disabled: Boolean, loading: Boolean },
  emits: ['click'],
  setup(props, { slots, emit, attrs }) {
    return () =>
      h('button', { class: 'el-button', title: attrs.title, disabled: props.disabled, onClick: (e: MouseEvent) => emit('click', e) },
        slots.default?.())
  },
})

const ElInputStub = defineComponent({
  name: 'ElInput',
  inheritAttrs: false,
  props: { modelValue: String },
  emits: ['update:modelValue', 'keyup'],
  setup(props, { emit }) {
    return () =>
      h('input', {
        class: 'el-input',
        value: props.modelValue,
        onInput: (e: Event) => emit('update:modelValue', (e.target as HTMLInputElement).value),
      })
  },
})

const STUBS = {
  'el-table': ElTableStub,
  'el-table-column': ElTableColumnStub,
  'el-tree': ElTreeStub,
  'el-button': ElButtonStub,
  'el-input': ElInputStub,
  'el-row': passthrough('el-row'),
  'el-col': passthrough('el-col'),
  'el-tag': passthrough('el-tag'),
  'el-empty': defineComponent({ props: { description: String }, setup: (p) => () => h('div', { class: 'el-empty' }, p.description) }),
  // 弹窗只在打开时渲染内容（本页的四个弹窗都不在断言范围内）
  'el-dialog': defineComponent({
    props: { modelValue: Boolean, title: String },
    setup: (p, { slots }) => () => (p.modelValue ? h('div', { class: 'el-dialog' }, [slots.default?.(), slots.footer?.()]) : null),
  }),
  'el-progress': true,
  'el-form': passthrough('el-form'),
  'el-form-item': passthrough('el-form-item'),
  'el-select': passthrough('el-select'),
  'el-option': true,
  'el-radio-group': passthrough('el-radio-group'),
  'el-radio': true,
  'el-radio-button': true,
  'el-upload': true,
  'el-icon': true,
  transition: passthrough('transition'),
}

// ─── 夹具：可管理 / 不可管理 / 系统文件夹 ─────────────────────────────────────
const TREE = [
  {
    id: 'f-own', name: '我的资料', access_level: 'public', doc_count: 2,
    can_manage: true, can_create: true, is_system: false,
    children: [
      { id: 'f-child', name: '子目录', access_level: 'public', doc_count: 0, can_manage: true, can_create: true, children: [] },
    ],
  },
  { id: 'f-other', name: '他人资料', access_level: 'public', doc_count: 1, can_manage: false, can_create: true, children: [] },
  { id: 'f-sys', name: '项目资料', access_level: 'project_group', doc_count: 1, can_manage: false, can_create: false, is_system: true, children: [] },
]

const DOCS: Record<string, any[]> = {
  'f-own': [
    { id: 'd-mine', name: '我的底稿说明.txt', file_type: 'txt', file_size: 12, can_manage: true, has_text: true },
    // 扫描件：已入库但无正文（后端 has_text=false）
    { id: 'd-theirs', name: '同事上传.pdf', file_type: 'pdf', file_size: 99, can_manage: false, has_text: false },
    // 空白文本：同样无正文，但不是扫描件（提示不得叫用户去开 OCR）
    { id: 'd-blank', name: '空白记录.txt', file_type: 'txt', file_size: 3, can_manage: false, has_text: false },
    // 批量删除用：列表时可管理，删除时服务端已变（被收权 → 403 / 被他人删除 → 404）
    { id: 'd-revoked', name: '被收权.txt', file_type: 'txt', file_size: 1, can_manage: true },
    { id: 'd-gone', name: '已被删.txt', file_type: 'txt', file_size: 1, can_manage: true },
  ],
  'f-other': [{ id: 'd-note', name: '项目讨论笔记', file_type: 'md', file_size: 30, can_manage: false }],
  'f-sys': [{ id: 'd-sys', name: '咨询附件.docx', file_type: 'docx', file_size: 40, can_manage: false }],
}

const PREVIEWS: Record<string, any> = {
  'd-mine': { id: 'd-mine', name: '我的底稿说明.txt', file_type: 'txt', folder_id: 'f-own', preview_type: 'text', content: '底稿正文' },
  'd-note': { id: 'd-note', name: '项目讨论笔记', file_type: 'md', folder_id: 'f-other', preview_type: 'text', content: '# 项目讨论笔记' },
  // 可读但所在文件夹不在目录树（如他人私有文件夹里单独公开的文档）
  'd-orphan': { id: 'd-orphan', name: '单独公开.txt', file_type: 'txt', folder_id: 'f-hidden', preview_type: 'text', content: '孤立文档' },
}

function httpError(status: number) {
  return Object.assign(new Error(`HTTP ${status}`), { response: { status, data: { detail: 'x' } } })
}

function routeApi() {
  state.api.get.mockImplementation(async (url: string) => {
    if (url === '/api/knowledge-library/tree') return TREE
    const docs = url.match(/^\/api\/knowledge-library\/folders\/([^/]+)\/documents$/)
    if (docs) return DOCS[docs[1]] ?? []
    const preview = url.match(/^\/api\/knowledge-library\/documents\/([^/]+)\/preview$/)
    if (preview) {
      if (PREVIEWS[preview[1]]) return PREVIEWS[preview[1]]
      throw httpError(404)
    }
    if (url === '/api/knowledge-library/search') {
      return [{
        id: 'd-mine', name: '我的底稿说明.txt', file_type: 'txt', file_size: 12,
        folder_id: 'f-own', folder_path: '/我的资料', snippet: '……应收账款函证差异已追查……', can_manage: true,
      }]
    }
    throw new Error(`unexpected GET ${url}`)
  })
}

async function mountPage(query: Record<string, string> = {}): Promise<VueWrapper> {
  state.route = reactive({ name: 'KnowledgeBase', query: { ...query } })
  const wrapper = mount(KnowledgeBase, { global: { stubs: STUBS } })
  await flushPromises()
  return wrapper
}

const buttons = (w: VueWrapper, text: string) => w.findAll('button').filter((b) => b.text().includes(text))
const docRow = (w: VueWrapper, id: string) => w.find(`.kb-row[data-id="${id}"]`)
const treeNode = (w: VueWrapper, id: string) => w.find(`.kb-node[data-id="${id}"]`)
const getCalls = (pattern: RegExp) => state.api.get.mock.calls.filter((c: any[]) => pattern.test(String(c[0])))

beforeEach(() => {
  vi.clearAllMocks()
  state.role = 'auditor'
  routeApi()
  state.api.delete.mockResolvedValue({})
})

describe('KnowledgeBase 深链（Req 5.10）', () => {
  it('folder_id + doc_id：选中文件夹、列目录、打开预览且复用深链的预览响应（不重复请求）', async () => {
    const w = await mountPage({ folder_id: 'f-own', doc_id: 'd-mine' })
    expect(getCalls(/\/folders\/f-own\/documents$/)).toHaveLength(1)
    expect(state.setCurrentKey).toHaveBeenCalledWith('f-own')
    expect(w.find('.gt-kb-preview-title').text()).toBe('我的底稿说明.txt')
    expect(w.find('.gt-kb-preview-text').text()).toBe('底稿正文')
    expect(getCalls(/\/documents\/d-mine\/preview$/)).toHaveLength(1)
    expect(state.message.warning).not.toHaveBeenCalled()
  })

  it('只有 doc_id：先调预览取 folder_id 再定位；无后缀文件名按 file_type=md 走文本预览（AI 笔记）', async () => {
    const w = await mountPage({ doc_id: 'd-note' })
    const previewCall = getCalls(/\/documents\/d-note\/preview$/)[0]
    // 404 由页面统一中文提示，不叠加全局 toast
    expect(previewCall[1]).toMatchObject({ _silent: true })
    expect(getCalls(/\/folders\/f-other\/documents$/)).toHaveLength(1)
    expect(state.setCurrentKey).toHaveBeenCalledWith('f-other')
    expect(w.find('.gt-kb-preview-text').text()).toBe('# 项目讨论笔记')
    expect(w.text()).not.toContain('不支持预览此文件类型')
  })

  it('只有 folder_id：选中文件夹，不调预览接口', async () => {
    await mountPage({ folder_id: 'f-child' })
    expect(getCalls(/\/folders\/f-child\/documents$/)).toHaveLength(1)
    expect(getCalls(/\/preview$/)).toHaveLength(0)
  })

  it('文件夹不在目录树（不存在或无权）→「文件夹不存在或无权访问」，不列任何目录', async () => {
    const w = await mountPage({ folder_id: 'f-nope' })
    expect(state.message.warning).toHaveBeenCalledWith('文件夹不存在或无权访问')
    expect(getCalls(/\/documents$/)).toHaveLength(0)
    expect(w.find('.gt-kb-preview-panel').exists()).toBe(false)
  })

  it('文档不可读（预览 404）→「文档不存在或无权访问」，不打开预览', async () => {
    const w = await mountPage({ doc_id: 'd-secret' })
    expect(state.message.warning).toHaveBeenCalledWith('文档不存在或无权访问')
    expect(getCalls(/\/documents$/)).toHaveLength(0)
    expect(w.find('.gt-kb-preview-panel').exists()).toBe(false)
  })

  it('文档可读但所在文件夹不在目录树 → 只打开预览并说明原因', async () => {
    const w = await mountPage({ doc_id: 'd-orphan' })
    expect(state.message.info).toHaveBeenCalledWith('文档所在文件夹不在你的目录中，已直接打开文档')
    expect(state.message.warning).not.toHaveBeenCalled()
    expect(w.find('.gt-kb-preview-text').text()).toBe('孤立文档')
  })

  it('同页内链接变化（再次点击笔记跳转）也会重新定位', async () => {
    const w = await mountPage({})
    expect(getCalls(/\/documents$/)).toHaveLength(0)
    state.route.query = { doc_id: 'd-mine' }
    await flushPromises()
    expect(getCalls(/\/folders\/f-own\/documents$/)).toHaveLength(1)
    expect(w.find('.gt-kb-preview-title').text()).toBe('我的底稿说明.txt')
  })
})

describe('KnowledgeBase 写按钮门控（Req 6.8）', () => {
  it('可写角色：文件夹改名/删除只对 can_manage 节点展示（系统文件夹、他人文件夹不展示）', async () => {
    const w = await mountPage()
    for (const title of ['重命名', '删除文件夹']) {
      expect(treeNode(w, 'f-own').find(`button[title="${title}"]`).exists()).toBe(true)
      expect(treeNode(w, 'f-other').find(`button[title="${title}"]`).exists()).toBe(false)
      expect(treeNode(w, 'f-sys').find(`button[title="${title}"]`).exists()).toBe(false)
    }
    expect(treeNode(w, 'f-sys').text()).toContain('系统')
    for (const label of ['新建文件夹', '上传文档', '上传文件夹']) {
      expect(buttons(w, label)).toHaveLength(1)
    }
  })

  it('可写角色：文档改名/删除只对 can_manage 行展示；不可管理行不能勾选批量删除', async () => {
    const w = await mountPage()
    await treeNode(w, 'f-own').trigger('click')
    await flushPromises()
    const mine = docRow(w, 'd-mine')
    const theirs = docRow(w, 'd-theirs')
    expect(mine.text()).toContain('重命名')
    expect(mine.text()).toContain('删除')
    expect(theirs.text()).toContain('预览')
    expect(theirs.text()).not.toContain('重命名')
    expect(theirs.text()).not.toContain('删除')
    expect((mine.find('input.kb-select').element as HTMLInputElement).disabled).toBe(false)
    expect((theirs.find('input.kb-select').element as HTMLInputElement).disabled).toBe(true)
  })

  it('「上传到此文件夹」只在有 can_create 的文件夹出现；无创建权时工具栏上传给出中文提示且不开弹窗', async () => {
    const w = await mountPage()
    await treeNode(w, 'f-own').trigger('click')
    await flushPromises()
    expect(buttons(w, '上传到此文件夹')).toHaveLength(1)

    await treeNode(w, 'f-sys').trigger('click')
    await flushPromises()
    expect(buttons(w, '上传到此文件夹')).toHaveLength(0)
    await buttons(w, '上传文档')[0].trigger('click')
    expect(state.message.warning).toHaveBeenCalledWith('你没有向该文件夹添加资料的权限')
    expect(w.find('.el-dialog').exists()).toBe(false)
  })

  it.each([
    ['readonly', 'readonly'],
    ['未知角色', 'guest'],
    ['用户信息缺失', null],
  ])('%s：即使后端标志为真也隐藏全部写按钮（fail-closed）', async (_label, role) => {
    state.role = role
    const w = await mountPage()
    for (const label of ['新建文件夹', '上传文档', '上传文件夹', '初始化预设文件夹']) {
      expect(buttons(w, label)).toHaveLength(0)
    }
    expect(treeNode(w, 'f-own').find('button[title="重命名"]').exists()).toBe(false)
    await treeNode(w, 'f-own').trigger('click')
    await flushPromises()
    const mine = docRow(w, 'd-mine')
    expect(mine.text()).toContain('预览')
    expect(mine.text()).not.toContain('重命名')
    expect(mine.find('input.kb-select').exists()).toBe(false)
    expect(buttons(w, '上传到此文件夹')).toHaveLength(0)
  })
})

describe('KnowledgeBase 批量删除与搜索视图', () => {
  async function selectAndBatchDelete(w: VueWrapper, ids: string[]) {
    for (const id of ids) await docRow(w, id).find('input.kb-select').trigger('click')
    await buttons(w, '删除选中')[0].trigger('click')
    await flushPromises()
  }

  it('403 / 404 / 其他失败分别计数提示，逐条请求不弹全局 toast', async () => {
    state.api.delete.mockImplementation(async (url: string) => {
      if (url.endsWith('/d-revoked')) throw httpError(403)
      if (url.endsWith('/d-gone')) throw httpError(404)
      return {}
    })
    const w = await mountPage()
    await treeNode(w, 'f-own').trigger('click')
    await flushPromises()
    await selectAndBatchDelete(w, ['d-mine', 'd-revoked', 'd-gone'])

    expect(state.api.delete).toHaveBeenCalledTimes(3)
    for (const call of state.api.delete.mock.calls) expect(call[1]).toMatchObject({ _silent: true })
    expect(state.message.success).not.toHaveBeenCalled()
    const msg = String(state.message.warning.mock.calls.at(-1)?.[0])
    expect(msg).toContain('已删除 1 个')
    expect(msg).toContain('1 个无权删除（仅创建者或系统管理员可删除）')
    expect(msg).toContain('1 个已不存在或无权访问')
    expect(msg).not.toContain('删除失败')
    // 删除后按 id 在新树里重新列目录（而不是拿旧节点对象）
    expect(getCalls(/\/folders\/f-own\/documents$/).length).toBeGreaterThanOrEqual(2)
  })

  it('全部成功 → 成功提示', async () => {
    const w = await mountPage()
    await treeNode(w, 'f-own').trigger('click')
    await flushPromises()
    await selectAndBatchDelete(w, ['d-mine', 'd-revoked'])
    expect(state.message.success).toHaveBeenCalledWith('已删除 2 个文档')
    expect(state.message.warning).not.toHaveBeenCalled()
  })

  it('搜索结果显示所在文件夹路径与命中片段；搜索视图不能作为上传目标', async () => {
    const w = await mountPage()
    await w.find('input.el-input').setValue('应收账款')
    await buttons(w, '搜索')[0].trigger('click')
    await flushPromises()
    const row = docRow(w, 'd-mine')
    expect(row.find('.gt-kb-doc-path').text()).toBe('📁 /我的资料')
    expect(row.find('.gt-kb-doc-snippet').text()).toBe('……应收账款函证差异已追查……')
    expect(w.find('.gt-kb-doc-header h4').text()).toContain('搜索结果')
    expect(buttons(w, '上传到此文件夹')).toHaveLength(0)
  })

  it('普通文件夹视图不显示路径与片段', async () => {
    const w = await mountPage()
    await treeNode(w, 'f-own').trigger('click')
    await flushPromises()
    expect(w.find('.gt-kb-doc-path').exists()).toBe(false)
    expect(w.find('.gt-kb-doc-snippet').exists()).toBe(false)
  })
})

// ─── 上传结果如实告知 + 拖拽文件夹（spec knowledge-upload-robustness-and-consumer-wiring R4 / R5） ───

/** XHR 替身：按文件名决定响应；记录每次上传的目标 URL 与文件名 */
class FakeXhr {
  static sent: Array<{ url: string; name: string }> = []
  static respond: (name: string) => { status: number; body: string } = () => ({ status: 200, body: '{}' })
  status = 0
  responseText = ''
  timeout = 0
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  ontimeout: (() => void) | null = null
  private url = ''
  open(_method: string, url: string) { this.url = url }
  setRequestHeader() {}
  send(form: FormData) {
    const file = form.get('files') as File
    FakeXhr.sent.push({ url: this.url, name: file.name })
    const r = FakeXhr.respond(file.name)
    this.status = r.status
    this.responseText = r.body
    queueMicrotask(() => (r.status === 0 ? this.ontimeout?.() : this.onload?.()))
  }
}

const uploadOk = (name: string, textExtracted = true, ocrQueued = false) =>
  JSON.stringify({
    code: 200,
    data: { uploaded: 1, files: [{ id: `id-${name}`, name, text_extracted: textExtracted, ocr_queued: ocrQueued }], failed: [] },
  })
const uploadFailed = (name: string, reason: string) =>
  JSON.stringify({ code: 200, data: { uploaded: 0, files: [], failed: [{ filename: name, reason }] } })

/** 目录条目替身：readEntries 按 Chromium 行为每次最多 100 条 */
function fsFile(fullPath: string): any {
  const name = fullPath.split('/').pop()!
  return { isFile: true, isDirectory: false, name, fullPath, file: (ok: (f: File) => void) => ok(new File([name], name)) }
}
function fsDir(fullPath: string, children: any[]): any {
  return {
    isFile: false, isDirectory: true, name: fullPath.split('/').pop()!, fullPath,
    createReader: () => {
      let offset = 0
      return { readEntries: (ok: (e: any[]) => void) => { const b = children.slice(offset, offset + 100); offset += b.length; ok(b) } }
    },
  }
}

describe('KnowledgeBase 上传结果与拖拽文件夹', () => {
  beforeEach(() => {
    FakeXhr.sent = []
    FakeXhr.respond = (name) => ({ status: 200, body: uploadOk(name) })
    vi.stubGlobal('XMLHttpRequest', FakeXhr as any)
  })

  async function openFolderUpload(w: VueWrapper) {
    await treeNode(w, 'f-own').trigger('click')
    await flushPromises()
    await buttons(w, '上传文件夹')[0].trigger('click')
    await flushPromises()
  }

  it('无正文的文档在列表中标出「AI 无法引用」，扫描件 PDF 与其余原因分开提示', async () => {
    const w = await mountPage()
    await treeNode(w, 'f-own').trigger('click')
    await flushPromises()
    const scan = docRow(w, 'd-theirs').find('.gt-kb-doc-notext')
    const blank = docRow(w, 'd-blank').find('.gt-kb-doc-notext')
    // 存量扫描件（无识别记录）：指向「重新识别」，不再叫用户去「开启 OCR」（无处可开）
    expect(scan.text()).toBe('⚠ 未提取到正文（扫描件），AI 无法引用')
    expect(scan.attributes('title')).toContain('重新识别')
    expect(scan.attributes('title')).not.toContain('开启 OCR')
    expect(blank.text()).toBe('⚠ 未提取到正文，AI 无法引用')
    expect(`${blank.text()}${blank.attributes('title')}`).not.toMatch(/OCR|扫描件|识别/)
    expect(docRow(w, 'd-mine').find('.gt-kb-doc-notext').exists()).toBe(false)
    // 不可管理的行没有「重新识别」
    expect(docRow(w, 'd-theirs').findAll('button').map((b) => b.text())).not.toContain('重新识别')
  })

  it('拖入 250 个文件的嵌套文件夹：全部上传，子目录逐级建出，失败原因与无正文逐条汇总', async () => {
    let seq = 0
    state.api.post.mockImplementation(async () => ({ id: `new-${++seq}` }))
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init: any) => {
      const body = JSON.parse(init.body)
      return new Response(JSON.stringify({ code: 200, data: { id: `sub-${body.name}` } }), { status: 200 })
    }))
    FakeXhr.respond = (name) =>
      name === 'bad.txt' ? { status: 200, body: uploadFailed(name, '文件内容含无法存储的字符') }
        : name === 'scan.pdf' ? { status: 200, body: uploadOk(name, false, true) }
          : name === 'huge.pdf' ? { status: 413, body: JSON.stringify({ code: 413, message: '请求体过大，上限 850MB' }) }
            : { status: 200, body: uploadOk(name) }

    const bulk = Array.from({ length: 250 }, (_, i) => fsFile(`/资料/批量/f${i}.txt`))
    const root = fsDir('/资料', [
      fsFile('/资料/bad.txt'),
      fsFile('/资料/scan.pdf'),
      fsFile('/资料/huge.pdf'),
      fsFile('/资料/~$锁文件.docx'),
      fsDir('/资料/批量', bulk),
    ])

    const w = await mountPage()
    await openFolderUpload(w)
    await w.find('.gt-kb-folder-drop').trigger('drop', {
      dataTransfer: { items: [{ webkitGetAsEntry: () => root }] },
    })
    await flushPromises()
    expect(w.text()).toContain('253 个文件')
    expect(w.text()).toContain('已跳过 1 个系统临时文件')

    await buttons(w, '上传 (253 个文件)')[0].trigger('click')
    for (let i = 0; i < 20; i++) await flushPromises()

    expect(FakeXhr.sent).toHaveLength(253)
    // 结构保留：「资料」建在目标文件夹下，「批量」建在「资料」下，文件各进各的目录
    const fetchBodies = (globalThis.fetch as any).mock.calls.map((c: any[]) => JSON.parse(c[1].body))
    expect(fetchBodies.map((b: any) => [b.name, b.parent_id])).toEqual([['资料', 'f-own'], ['批量', 'sub-资料']])
    expect(FakeXhr.sent.filter((s) => s.url.includes('/folders/sub-批量/upload'))).toHaveLength(250)
    expect(FakeXhr.sent.find((s) => s.name === 'bad.txt')?.url).toContain('/folders/sub-资料/upload')

    expect(state.notify).toHaveBeenCalledTimes(1)
    const arg = state.notify.mock.calls[0][0]
    expect(arg.title).toBe('上传完成：251 成功，2 失败')
    expect(arg.type).toBe('warning')
    const text = JSON.stringify(arg.message)
    expect(text).toContain('资料/bad.txt：文件内容含无法存储的字符')
    expect(text).toContain('资料/huge.pdf：请求体过大，上限 850MB')
    expect(text).toContain('扫描件已交给后台识别文字，完成后 AI 即可引用（进度见文档列表）：资料/scan.pdf')
    expect(text).not.toContain('开启 OCR')
    // 通知挂在 body 下且 VNode 不带本组件 scopeId ⇒ 限高 / 滚动必须内联（scoped 样式匹配不到）
    expect(arg.message.props.style).toMatchObject({ maxHeight: '240px', overflowY: 'auto' })
    vi.unstubAllGlobals()
  })

  it('重新打开上传弹窗不残留上一次的「已跳过 N 个」', async () => {
    const junkOnly = fsDir('/杂', [fsFile('/杂/~$锁.docx'), fsFile('/杂/.DS_Store')])
    const w = await mountPage()
    await openFolderUpload(w)
    await w.find('.gt-kb-folder-drop').trigger('drop', { dataTransfer: { items: [{ webkitGetAsEntry: () => junkOnly }] } })
    await flushPromises()
    expect(w.text()).toContain('已跳过 2 个系统临时文件')

    await buttons(w, '取消')[0].trigger('click')
    await flushPromises()
    await buttons(w, '上传文件夹')[0].trigger('click')
    await flushPromises()
    expect(w.find('.el-dialog').exists()).toBe(true)
    expect(w.text()).not.toContain('已跳过')
  })

  it('上传超时不再卡死：该文件计为失败并给出原因，其余文件继续', async () => {
    FakeXhr.respond = (name) => (name === 'slow.pdf' ? { status: 0, body: '' } : { status: 200, body: uploadOk(name) })
    const root = fsDir('/t', [fsFile('/t/slow.pdf'), fsFile('/t/ok.txt')])
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ data: { id: 'sub-t' } }), { status: 200 })))

    const w = await mountPage()
    await openFolderUpload(w)
    await w.find('.gt-kb-folder-drop').trigger('drop', { dataTransfer: { items: [{ webkitGetAsEntry: () => root }] } })
    await flushPromises()
    await buttons(w, '上传 (2 个文件)')[0].trigger('click')
    for (let i = 0; i < 10; i++) await flushPromises()

    expect(FakeXhr.sent.map((s) => s.name)).toEqual(['slow.pdf', 'ok.txt'])
    const arg = state.notify.mock.calls[0][0]
    expect(arg.title).toBe('上传完成：1 成功，1 失败')
    expect(JSON.stringify(arg.message)).toContain('上传超时')
    vi.unstubAllGlobals()
  })
})

// ─── 扫描件后台识别：状态标记 / 重新识别 / 自动刷新（spec dsh-kb-ocr-local-first-routing Req 5.6 / 5.7） ───

describe('KnowledgeBase 扫描件后台识别', () => {
  /** f-own 换成带识别状态的一组文档（每次 GET 返回新对象，模拟真实接口） */
  function withOcrDocs(rows: () => any[]) {
    const base = state.api.get.getMockImplementation()!
    state.api.get.mockImplementation(async (url: string, cfg?: any) =>
      url === '/api/knowledge-library/folders/f-own/documents' ? rows() : base(url, cfg))
  }
  const scan = (id: string, extra: Record<string, unknown>) => ({
    id, name: `${id}.pdf`, file_type: 'pdf', file_size: 9, can_manage: true, has_text: false, ...extra,
  })
  const docCalls = () => getCalls(/\/folders\/f-own\/documents$/)
  const rowButtons = (w: VueWrapper, id: string) => docRow(w, id).findAll('button').map((b) => b.text())

  async function openOwn() {
    const w = await mountPage()
    await treeNode(w, 'f-own').trigger('click')
    await flushPromises()
    return w
  }

  it('按状态标记：识别中是进度提示且不能重复发起；失败带原因、可管理才给「重新识别」', async () => {
    withOcrDocs(() => [
      scan('d-queued', { ocr_status: 'pending' }),
      scan('d-running', { ocr_status: 'running' }),
      scan('d-failed', { ocr_status: 'failed', ocr_error: '远程 OCR 认证失败，请检查 API Key' }),
      scan('d-failed-other', { ocr_status: 'failed', ocr_error: 'x', can_manage: false }),
      scan('d-empty', { ocr_status: 'empty' }),
    ])
    const w = await openOwn()
    const mark = (id: string) => docRow(w, id).find('.gt-kb-doc-notext')
    expect(mark('d-queued').text()).toBe('⏳ 排队识别中…')
    expect(mark('d-queued').classes()).toContain('gt-kb-doc-notext--progress')
    expect(mark('d-running').text()).toBe('⏳ 正在识别文字…')
    expect(mark('d-failed').text()).toBe('⚠ 识别失败，AI 无法引用')
    expect(mark('d-failed').attributes('title')).toContain('远程 OCR 认证失败，请检查 API Key')
    expect(mark('d-failed').classes()).not.toContain('gt-kb-doc-notext--progress')
    expect(mark('d-empty').text()).toBe('⚠ 未识别出文字，AI 无法引用')
    expect(rowButtons(w, 'd-queued')).not.toContain('重新识别')
    expect(rowButtons(w, 'd-running')).not.toContain('重新识别')
    expect(rowButtons(w, 'd-failed')).toContain('重新识别')
    expect(rowButtons(w, 'd-empty')).toContain('重新识别')
    expect(rowButtons(w, 'd-failed-other')).not.toContain('重新识别')
    w.unmount()
  })

  it('点「重新识别」：调重试端点（静默，错误由页面提示一次），该行转为排队中', async () => {
    withOcrDocs(() => [scan('d-failed', { ocr_status: 'failed', ocr_error: '多次识别失败' })])
    state.api.post.mockResolvedValueOnce({ id: 'd-failed', ocr_status: 'pending', message: '已加入识别队列' })
    const w = await openOwn()
    await docRow(w, 'd-failed').findAll('button').find((b) => b.text() === '重新识别')!.trigger('click')
    await flushPromises()
    expect(state.api.post).toHaveBeenCalledWith(
      '/api/knowledge-library/documents/d-failed/ocr-retry', null, expect.objectContaining({ _silent: true }),
    )
    expect(state.message.success).toHaveBeenCalledWith('已加入识别队列，完成后列表自动刷新')
    expect(docRow(w, 'd-failed').find('.gt-kb-doc-notext').text()).toBe('⏳ 排队识别中…')
    expect(rowButtons(w, 'd-failed')).not.toContain('重新识别')
    w.unmount()
  })

  it('重新识别被拒（409 已在识别）：交给 handleApiError 提示，状态不变', async () => {
    const { handleApiError } = await import('@/utils/errorHandler')
    withOcrDocs(() => [scan('d-failed', { ocr_status: 'failed', ocr_error: 'x' })])
    const conflict = httpError(409)
    state.api.post.mockRejectedValueOnce(conflict)
    const w = await openOwn()
    await docRow(w, 'd-failed').findAll('button').find((b) => b.text() === '重新识别')!.trigger('click')
    await flushPromises()
    expect(handleApiError).toHaveBeenCalledWith(conflict, '重新识别')
    expect(docRow(w, 'd-failed').find('.gt-kb-doc-notext').text()).toBe('⚠ 识别失败，AI 无法引用')
    w.unmount()
  })

  it('有排队 / 识别中的文档：每 5 秒静默刷新（不去重、不清勾选），识别完标记消失并停止刷新', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    try {
      let round = 0
      withOcrDocs(() => {
        round += 1
        return [
          scan('d-scan', round < 3 ? { ocr_status: round === 1 ? 'pending' : 'running' } : { ocr_status: 'done', has_text: true }),
          { id: 'd-note2', name: '说明.txt', file_type: 'txt', file_size: 1, can_manage: true, has_text: true },
        ]
      })
      const w = await openOwn()
      expect(docCalls()).toHaveLength(1)
      await w.find('.kb-row[data-id="d-note2"] .kb-select').trigger('click')  // 用户勾选了一行
      const rowBefore = (w.vm as any).documents[0]

      await vi.advanceTimersByTimeAsync(4999)
      expect(docCalls()).toHaveLength(1)
      await vi.advanceTimersByTimeAsync(1)
      await flushPromises()
      expect(docCalls()).toHaveLength(2)
      expect(docCalls()[1][1]).toMatchObject({ _silent: true, _dedupe: false })
      expect(docRow(w, 'd-scan').find('.gt-kb-doc-notext').text()).toBe('⏳ 正在识别文字…')

      await vi.advanceTimersByTimeAsync(5000)
      await flushPromises()
      expect(docCalls()).toHaveLength(3)
      expect(docRow(w, 'd-scan').find('.gt-kb-doc-notext').exists()).toBe(false)  // 识别完：AI 可引用
      // 原地更新同一行对象（整表替换会让 el-table 清掉勾选）；用户的勾选还在
      expect((w.vm as any).documents[0]).toBe(rowBefore)
      expect(buttons(w, '删除选中 (1)')).toHaveLength(1)

      await vi.advanceTimersByTimeAsync(15000)
      await flushPromises()
      expect(docCalls()).toHaveLength(3)  // 没有识别中的文档：停止刷新
      w.unmount()
    } finally {
      vi.useRealTimers()
    }
  })

  it('离开页面停止刷新', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    try {
      withOcrDocs(() => [scan('d-scan', { ocr_status: 'pending' })])
      const w = await openOwn()
      w.unmount()
      await vi.advanceTimersByTimeAsync(20000)
      await flushPromises()
      expect(docCalls()).toHaveLength(1)
    } finally {
      vi.useRealTimers()
    }
  })
})
