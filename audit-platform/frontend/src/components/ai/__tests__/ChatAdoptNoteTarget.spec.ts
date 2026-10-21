/**
 * 「采纳」「转存笔记」选择目标位置与文件 —— 前端守卫
 *
 * spec: ai-chat-adopt-and-note-target-picker（R1 / R3 / R4.1 / R5.2）
 *
 * 2026-10-20 浏览器复现：项目列表页（全局知识模式）点「采纳」恒「资源不存在或不可访问」，
 * 「转存笔记」提示「当前页面无项目上下文」；且笔记请求体（嵌套 host、无 session_id）与后端
 * `NoteSaveRequestBody`（extra=forbid）不一致，任何页面都恒 422 —— 唯一的前端守卫不看请求体
 * 形状、后端测试又直接调端点函数，两边都绿。本文件：
 *
 * 1. 请求体与后端 pydantic 模型**逐字段对账**（解析 `backend/app/routers/doc_ai_chat.py`）；
 * 2. 失败信封按平台真实形状取中文原因（外层 code 是 HTTP 状态数字）；
 * 3. 两个对话框的选择 → 提交载荷；
 * 4. 面板分流：底稿 / 附注直接采纳，其余宿主先选目标。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { existsSync, readFileSync } from 'fs'
import { dirname, join } from 'path'
import { fileURLToPath } from 'url'
import type { AiHostRef, AiHostRequest } from '@/composables/useAiHostContext'

const mocks = vi.hoisted(() => ({
  listProjects: vi.fn(),
  getDisclosureNoteTree: vi.fn(),
  listWorkpapers: vi.fn(),
  apiGet: vi.fn(),
  msgSuccess: vi.fn(),
  msgError: vi.fn(),
}))

vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ token: 'test-token' }) }))
vi.mock('element-plus', () => ({
  ElMessage: { success: mocks.msgSuccess, error: mocks.msgError, warning: vi.fn(), info: vi.fn() },
  ElMessageBox: { prompt: vi.fn() },
}))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ params: {}, query: {} }),
}))
vi.mock('@/stores/chatRunState', () => ({
  useChatRunStateStore: () => ({
    phase: 'idle', runId: null, errorCode: null, retryAfter: null, streamingDelta: '',
    displayError: null, contextManifest: null, isActive: false, isTerminal: false,
    startRun: vi.fn(), subscribe: vi.fn().mockResolvedValue(undefined), cancel: vi.fn(),
    reset: vi.fn(), on: vi.fn().mockReturnValue(() => {}), setQuota: vi.fn(),
  }),
}))
vi.mock('@/services/auditPlatformApi', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  listProjects: mocks.listProjects,
  getDisclosureNoteTree: mocks.getDisclosureNoteTree,
}))
vi.mock('@/services/workpaperApi', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  listWorkpapers: mocks.listWorkpapers,
}))
vi.mock('@/services/apiProxy', async (orig) => {
  const actual = await orig<Record<string, any>>()
  return { ...actual, api: { ...actual.api, get: mocks.apiGet } }
})

// ---------------------------------------------------------------------------
// 夹具
// ---------------------------------------------------------------------------

const P1 = '11111111-1111-4111-8111-111111111111'
const P2 = '22222222-2222-4222-8222-222222222222'
const WP1 = '33333333-3333-4333-8333-333333333331'
const WP2 = '33333333-3333-4333-8333-333333333332'
const NOTE1 = '44444444-4444-4444-8444-444444444441'
const MSG = '55555555-5555-4555-8555-555555555551'
const FOLDER_OK = '66666666-6666-4666-8666-666666666661'
const FOLDER_RO = '66666666-6666-4666-8666-666666666662'
const FOLDER_CHILD = '66666666-6666-4666-8666-666666666663'

const GLOBAL_REF: AiHostRef = { type: 'global_knowledge', id: 'global-knowledge', projectId: null, year: null }
const WP_REF: AiHostRef = { type: 'workpaper', id: WP1, projectId: P1, year: 2025 }
const REPORT_REF: AiHostRef = { type: 'report', id: 'balance_sheet', projectId: P1, year: 2025 }

function hostRequest(host: AiHostRef): AiHostRequest {
  return {
    host,
    available: true,
    unavailableReason: null,
    projectToolsEnabled: host.projectId !== null,
    label: host.type,
  }
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** 仓库根（哨兵是具体文件：目录名多层同名时会停错层） */
function repoRoot(): string {
  let dir = dirname(fileURLToPath(import.meta.url))
  for (let i = 0; i < 12; i += 1) {
    if (existsSync(join(dir, 'backend', 'app', 'routers', 'doc_ai_chat.py'))
      && existsSync(join(dir, 'audit-platform', 'frontend', 'package.json'))) return dir
    dir = dirname(dir)
  }
  throw new Error('未找到仓库根（哨兵 backend/app/routers/doc_ai_chat.py）')
}

/**
 * 解析后端 pydantic 模型字段：`name -> required`。
 * 必填 = 无默认值，或默认是 `Field(...`（含跨行写法 `Field(\n    ...,`）。
 */
function backendModelFields(cls: string): Map<string, boolean> {
  const src = readFileSync(join(repoRoot(), 'backend', 'app', 'routers', 'doc_ai_chat.py'), 'utf-8')
  const lines = src.replace(/\r\n/g, '\n').split('\n')
  const start = lines.findIndex((l) => l.startsWith(`class ${cls}(`))
  if (start < 0) throw new Error(`doc_ai_chat.py 中找不到 class ${cls}`)
  const fields = new Map<string, boolean>()
  for (let i = start + 1; i < lines.length; i += 1) {
    const line = lines[i]
    if (line.trim() && !line.startsWith(' ')) break // 类体结束
    const m = /^ {4}([a-z_][a-z0-9_]*)\s*:[^=]+?(?:=\s*(.*))?$/.exec(line)
    if (!m) continue
    const dflt = (m[2] ?? '').trim()
    const next = (lines[i + 1] ?? '').trim()
    const required = dflt === ''
      || /^Field\(\s*\.\.\./.test(dflt)
      || (dflt === 'Field(' && next.startsWith('...'))
    fields.set(m[1], required)
  }
  return fields
}

function requiredOf(fields: Map<string, boolean>): string[] {
  return [...fields].filter(([, r]) => r).map(([k]) => k).sort()
}

/** 在组件 setup 上下文里调用 composable（避免生命周期钩子告警） */
function withSetup<T>(fn: () => T): T {
  let result!: T
  mount(defineComponent({ setup() { result = fn(); return () => h('div') } }), {
    global: { plugins: [createPinia()] },
  })
  return result
}

function okJson(data: unknown) {
  return { ok: true, status: 200, json: async () => ({ code: 200, message: 'ok', data }) }
}

function failJson(status: number, body: unknown) {
  return { ok: false, status, json: async () => body }
}

const fetchMock = vi.fn()
function bodiesTo(path: string): Record<string, any>[] {
  return fetchMock.mock.calls
    .filter(([url, init]) => String(url).includes(path) && (init as any)?.method === 'POST')
    .map(([, init]) => JSON.parse((init as any).body))
}

beforeEach(() => {
  setActivePinia(createPinia())
  Object.values(mocks).forEach((m) => m.mockReset())
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

// ===========================================================================
// 1. 失败信封与纯映射
// ===========================================================================

describe('readAiChatError：按平台真实信封取业务码与中文原因', () => {
  it('四种真实形状 + 垃圾输入', async () => {
    const { readAiChatError } = await import('@/composables/aiChatWireError')
    // 业务 HTTPException(detail={code,message}) → 外层 code 是 HTTP 状态数字
    expect(readAiChatError({ code: 422, message: { code: 'no_target', message: '请选择笔记保存位置' } }))
      .toEqual({ code: 'no_target', message: '请选择笔记保存位置' })
    // 不可枚举 404
    expect(readAiChatError({ code: 404, message: '资源不存在或不可访问' }))
      .toEqual({ message: '资源不存在或不可访问' })
    // 请求体校验失败（detail 是字段错误数组）
    expect(readAiChatError({ code: 422, message: '请求参数校验失败', detail: [{ loc: ['body'] }] }))
      .toEqual({ message: '请求参数校验失败' })
    // FastAPI 默认形状
    expect(readAiChatError({ detail: { code: 'adopt_in_progress', message: '采纳正在处理中' } }))
      .toEqual({ code: 'adopt_in_progress', message: '采纳正在处理中' })
    expect(readAiChatError(null)).toEqual({})
    expect(readAiChatError('oops')).toEqual({})
  })
})

describe('chatTargetOptions 纯映射', () => {
  it('文件夹树：无新建权限的节点禁选，路径按层级拼接', async () => {
    const { toFolderOptions, isCreatableFolder, findFolderPath } = await import('../chatTargetOptions')
    const tree = toFolderOptions([
      { id: FOLDER_RO, name: '只读根', can_create: false, children: [
        { id: FOLDER_CHILD, name: '可写子级', can_create: true, children: [] },
      ] },
      { id: FOLDER_OK, name: '公共资料', can_create: true },
    ])
    expect(tree[0].disabled).toBe(true)
    expect(tree[0].children[0].disabled).toBe(false)
    expect(isCreatableFolder(tree, FOLDER_RO)).toBe(false)
    expect(isCreatableFolder(tree, FOLDER_CHILD)).toBe(true)
    expect(isCreatableFolder(tree, 'nope')).toBe(false)
    expect(findFolderPath(tree, FOLDER_CHILD)).toEqual(['只读根', '可写子级'])
  })

  it('底稿按编码排序；非 UUID 目标不构造宿主', async () => {
    const { toWorkpaperOptions, buildAdoptTargetHost } = await import('../chatTargetOptions')
    const opts = toWorkpaperOptions([
      { id: WP2, wp_code: 'D10', wp_name: '合同负债' } as any,
      { id: WP1, wp_code: 'D2', wp_name: '应收账款' } as any,
    ])
    expect(opts.map((o) => o.label)).toEqual(['D2 应收账款', 'D10 合同负债'])
    expect(buildAdoptTargetHost('workpaper', WP1, P1))
      .toEqual({ type: 'workpaper', id: WP1, projectId: P1, year: null })
    expect(buildAdoptTargetHost('note', NOTE1, P1))
      .toEqual({ type: 'note', id: NOTE1, projectId: P1, year: null })
    expect(buildAdoptTargetHost('workpaper', 'not-a-uuid', P1)).toBeNull()
  })
})

// ===========================================================================
// 2. 请求体 ↔ 后端 pydantic 模型逐字段对账（跨语言契约）
// ===========================================================================

describe('请求体与后端模型对账（extra=forbid：多一个键或少一个必填键都是 422）', () => {
  it('解析器本身不空转：已知必填字段都能解析出来', () => {
    expect(requiredOf(backendModelFields('AdoptRequest')))
      .toEqual(['host', 'idempotency_key', 'message_id'])
    expect(requiredOf(backendModelFields('AdoptHostRef'))).toEqual(['id', 'type'])
    expect(requiredOf(backendModelFields('NoteSaveRequestBody')))
      .toEqual(['host_id', 'host_type', 'idempotency_key', 'message_ids', 'name'])
    // 旧前端的嵌套 host 形状在后端模型里根本没有 —— 这就是恒 422 的原因
    expect(backendModelFields('NoteSaveRequestBody').has('host')).toBe(false)
  })

  it('全局知识模式采纳到选定底稿：host = 目标、source_host = 当前宿主', async () => {
    const { usePlatformAiChat } = await import('@/composables/usePlatformAiChat')
    const chat = withSetup(() => usePlatformAiChat({ host: hostRequest(GLOBAL_REF) }))

    // 不给目标：不发注定 404 的请求
    const noTarget = await chat.adoptContent(MSG)
    expect(noTarget.code).toBe('adopt_target_required')
    expect(fetchMock).not.toHaveBeenCalled()

    fetchMock.mockResolvedValueOnce(okJson({ success: true }))
    const res = await chat.adoptContent(MSG, {
      host: { type: 'workpaper', id: WP1, projectId: P1, year: null },
      targetCell: '  D12 ',
    })
    expect(res.success).toBe(true)
    const [body] = bodiesTo('/api/ai-chat/adopt')
    expect(body.host).toEqual({ type: 'workpaper', id: WP1, project_id: P1, year: null })
    expect(body.source_host).toEqual({ type: 'global_knowledge', id: 'global-knowledge', project_id: null, year: null })
    expect(body.target_cell).toBe('D12')
    expect(body.idempotency_key).toMatch(UUID_RE)

    const adoptFields = backendModelFields('AdoptRequest')
    const hostFields = backendModelFields('AdoptHostRef')
    for (const key of Object.keys(body)) expect(adoptFields.has(key), `后端无字段 ${key}`).toBe(true)
    for (const req of requiredOf(adoptFields)) expect(body, `缺必填 ${req}`).toHaveProperty(req)
    for (const ref of [body.host, body.source_host]) {
      for (const key of Object.keys(ref)) expect(hostFields.has(key), `AdoptHostRef 无字段 ${key}`).toBe(true)
    }
  })

  it('底稿宿主直接采纳：不带 source_host；失败按信封取中文原因', async () => {
    const { usePlatformAiChat } = await import('@/composables/usePlatformAiChat')
    const chat = withSetup(() => usePlatformAiChat({ host: hostRequest(WP_REF) }))
    fetchMock.mockResolvedValueOnce(failJson(503, {
      code: 503,
      message: { code: 'adopt_log_failed', message: '采纳未生效：AI 内容确认记录写入失败，本次操作已回滚，请稍后重试' },
    }))
    const res = await chat.adoptContent(MSG)
    expect(res).toEqual({
      success: false,
      code: 'adopt_log_failed',
      message: '采纳未生效：AI 内容确认记录写入失败，本次操作已回滚，请稍后重试',
    })
    const [body] = bodiesTo('/api/ai-chat/adopt')
    expect(body.host).toEqual({ type: 'workpaper', id: WP1, project_id: P1, year: 2025 })
    expect('source_host' in body).toBe(false)
    expect('target_cell' in body).toBe(false)
  })

  it('笔记三种保存位置的请求体都与 NoteSaveRequestBody 一致（不发 session_id / 嵌套 host）', async () => {
    const { useAiNoteCapture } = await import('@/composables/useAiNoteCapture')
    const fields = backendModelFields('NoteSaveRequestBody')
    const cases: Array<{ host: AiHostRef; target: any; expect: Record<string, unknown> }> = [
      { host: WP_REF, target: { kind: 'host_project' }, expect: {} },
      { host: GLOBAL_REF, target: { kind: 'project', projectId: P2 }, expect: { target_project_id: P2 } },
      { host: GLOBAL_REF, target: { kind: 'folder', folderId: FOLDER_OK }, expect: { target_folder_id: FOLDER_OK } },
    ]
    for (const c of cases) {
      fetchMock.mockReset()
      const messages = [{ id: MSG, role: 'assistant', status: 'completed', text: '回复' }] as any[]
      const capture = useAiNoteCapture({ messages: () => messages, host: () => c.host })
      capture.toggleMessage(MSG)
      fetchMock.mockResolvedValueOnce(okJson({ document_id: 'd', jump_route: '/knowledge?doc_id=d' }))
      expect((await capture.saveAsNote({ name: '存货监盘要点', target: c.target })).success).toBe(true)
      const [body] = bodiesTo('/api/ai-chat/notes')
      expect(body).toMatchObject({
        message_ids: [MSG], name: '存货监盘要点', host_type: c.host.type, host_id: c.host.id,
        project_id: c.host.projectId, year: c.host.year, ...c.expect,
      })
      expect('session_id' in body || 'host' in body).toBe(false)
      for (const key of Object.keys(body)) expect(fields.has(key), `后端无字段 ${key}`).toBe(true)
      for (const req of requiredOf(fields)) expect(body, `缺必填 ${req}`).toHaveProperty(req)
    }
  })

  it('无项目宿主选「本项目」位置：前端直接拒绝，不发请求', async () => {
    const { useAiNoteCapture } = await import('@/composables/useAiNoteCapture')
    const messages = [{ id: MSG, role: 'assistant', status: 'completed', text: '回复' }] as any[]
    const capture = useAiNoteCapture({ messages: () => messages, host: () => GLOBAL_REF })
    capture.toggleMessage(MSG)
    const res = await capture.saveAsNote({ name: '笔记', target: { kind: 'host_project' } })
    expect(res.errorCode).toBe('no_target')
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

// ===========================================================================
// 3. 对话框（Element Plus 未全局注册：用可观测的原生元素替身）
// ===========================================================================

const DIALOG_STUBS = {
  'el-dialog': {
    props: ['modelValue', 'title'],
    emits: ['open', 'update:modelValue'],
    watch: {
      modelValue: { immediate: true, handler(this: any, v: boolean) { if (v) this.$emit('open') } },
    },
    template: '<div v-if="modelValue" class="stub-dialog"><slot /><slot name="footer" /></div>',
  },
  'el-alert': {
    props: ['title', 'type'],
    template: '<div class="stub-alert" :data-type="type">{{ title }}<slot /></div>',
  },
  'el-form': {
    template: '<form class="stub-form" @submit.prevent><slot /></form>',
    methods: { validate: () => Promise.resolve(true), clearValidate: () => undefined },
  },
  'el-form-item': { props: ['label'], template: '<div class="stub-item"><span>{{ label }}</span><slot /></div>' },
  'el-select': {
    props: ['modelValue', 'disabled'],
    emits: ['update:modelValue', 'change'],
    template:
      '<select :disabled="disabled" :value="modelValue"'
      + ' @change="$emit(\'update:modelValue\', $event.target.value); $emit(\'change\', $event.target.value)">'
      + '<option value=""></option><slot /></select>',
  },
  'el-option': { props: ['label', 'value'], template: '<option :value="value">{{ label }}</option>' },
  'el-tree-select': {
    props: ['modelValue', 'data'],
    emits: ['update:modelValue'],
    computed: {
      flat(this: any) {
        const out: Array<{ id: string; name: string; disabled: boolean }> = []
        const walk = (nodes: any[]) => (nodes || []).forEach((n) => { out.push(n); walk(n.children) })
        walk(this.data)
        return out
      },
    },
    template:
      '<select class="stub-tree" :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)">'
      + '<option value=""></option>'
      + '<option v-for="o in flat" :key="o.id" :value="o.id" :disabled="o.disabled">{{ o.name }}</option></select>',
  },
  'el-radio-group': {
    props: ['modelValue'],
    emits: ['update:modelValue', 'change'],
    provide(this: any) { return { stubRadioGroup: this } },
    template: '<div class="stub-radio-group"><slot /></div>',
  },
  'el-radio-button': {
    props: ['value'],
    inject: ['stubRadioGroup'],
    template:
      '<button type="button" class="stub-radio" :data-value="value"'
      + ' @click="stubRadioGroup.$emit(\'update:modelValue\', value); stubRadioGroup.$emit(\'change\', value)">'
      + '<slot /></button>',
  },
  'el-input': {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  'el-button': {
    props: ['disabled', 'loading', 'type'],
    emits: ['click'],
    template: '<button type="button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
}

const PROJECTS = [
  { id: P1, name: '甲公司_2025', audit_year: 2025 },
  { id: P2, name: '乙公司', audit_year: null, audit_period_end: null },
]

describe('ChatAdoptTargetDialog：项目 → 底稿 / 附注 → 可选位置', () => {
  async function mountAdopt(sourceHost: AiHostRef, submit = vi.fn().mockResolvedValue({ success: true })) {
    const { default: Dialog } = await import('../ChatAdoptTargetDialog.vue')
    const wrapper = mount(Dialog, {
      props: { modelValue: true, sourceHost, submit },
      global: { stubs: DIALOG_STUBS },
    })
    await flushPromises()
    return { wrapper, submit }
  }

  beforeEach(() => {
    mocks.listProjects.mockResolvedValue(PROJECTS)
    mocks.listWorkpapers.mockResolvedValue([
      { id: WP2, wp_code: 'D2', wp_name: '应收账款' },
      { id: WP1, wp_code: 'D1', wp_name: '应收票据' },
    ])
    mocks.getDisclosureNoteTree.mockResolvedValue([
      { id: NOTE1, note_section: '五、4', section_title: '应收账款', sort_order: 4 },
    ])
  })

  it('全局会话：选项目和底稿后提交目标宿主与位置，成功回报「项目 / 底稿」', async () => {
    const { wrapper, submit } = await mountAdopt(GLOBAL_REF)
    expect(wrapper.text()).toContain('在目标页面确认后才生效')
    const submitBtn = () => wrapper.find('[data-testid="adopt-submit"]')
    expect(submitBtn().attributes('disabled')).toBeDefined()

    await wrapper.find('[data-testid="adopt-project"]').setValue(P1)
    await flushPromises()
    expect(mocks.listWorkpapers).toHaveBeenCalledWith(P1)
    const labels = wrapper.find('[data-testid="adopt-file"]').findAll('option').map((o) => o.text())
    expect(labels).toEqual(['', 'D1 应收票据', 'D2 应收账款'])

    await wrapper.find('[data-testid="adopt-file"]').setValue(WP1)
    await wrapper.find('[data-testid="adopt-cell"]').setValue('  D12 ')
    await submitBtn().trigger('click')
    await flushPromises()
    expect(submit).toHaveBeenCalledWith({
      host: { type: 'workpaper', id: WP1, projectId: P1, year: null },
      targetCell: 'D12',
    })
    expect(wrapper.emitted('done')?.[0]).toEqual(['甲公司_2025 / D1 应收票据'])
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([false])
  })

  it('附注章节按项目年度取目录；项目无年度时给出原因且不请求', async () => {
    const { wrapper, submit } = await mountAdopt(GLOBAL_REF)
    await wrapper.find('[data-testid="adopt-project"]').setValue(P2)
    await flushPromises()
    await wrapper.find('.stub-radio[data-value="note"]').trigger('click')
    await flushPromises()
    expect(mocks.getDisclosureNoteTree).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('该项目未设置审计年度，无法列出附注章节')

    await wrapper.find('[data-testid="adopt-project"]').setValue(P1)
    await flushPromises()
    // 静默请求：附注未生成的 404 是正常空态，不能弹全局错误
    expect(mocks.getDisclosureNoteTree).toHaveBeenCalledWith(P1, 2025, expect.objectContaining({ _silent: true }))
    await wrapper.find('[data-testid="adopt-file"]').setValue(NOTE1)
    await wrapper.find('[data-testid="adopt-submit"]').trigger('click')
    await flushPromises()
    expect(submit).toHaveBeenCalledWith({
      host: { type: 'note', id: NOTE1, projectId: P1, year: null },
      targetCell: null,
    })
  })

  it('附注尚未生成（后端 404）：显示「尚未生成附注」而不是「加载失败」', async () => {
    mocks.getDisclosureNoteTree.mockRejectedValue({ response: { status: 404 } })
    const { wrapper } = await mountAdopt(GLOBAL_REF)
    await wrapper.find('[data-testid="adopt-project"]').setValue(P1)
    await flushPromises()
    await wrapper.find('.stub-radio[data-value="note"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('该项目 2025 年度尚未生成附注')
    expect(wrapper.text()).not.toContain('加载失败')

    mocks.getDisclosureNoteTree.mockRejectedValue({ response: { status: 500 } })
    await wrapper.find('.stub-radio[data-value="workpaper"]').trigger('click')
    await flushPromises()
    await wrapper.find('.stub-radio[data-value="note"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('附注目录加载失败，请稍后重试')
  })

  it('报表会话：项目锁定为本项目并直接列出底稿；提交失败留在对话框显示原因', async () => {
    const submit = vi.fn().mockResolvedValue({ success: false, message: '资源不存在或不可访问' })
    const { wrapper } = await mountAdopt(REPORT_REF, submit)
    const projectSelect = wrapper.find('[data-testid="adopt-project"]')
    expect(projectSelect.attributes('disabled')).toBeDefined()
    expect((projectSelect.element as HTMLSelectElement).value).toBe(P1)
    expect(wrapper.text()).toContain('只能采纳到本项目')
    expect(mocks.listWorkpapers).toHaveBeenCalledWith(P1)

    await wrapper.find('[data-testid="adopt-file"]').setValue(WP2)
    await wrapper.find('[data-testid="adopt-submit"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('.stub-alert[data-type="error"]').text()).toBe('资源不存在或不可访问')
    expect(wrapper.emitted('done')).toBeUndefined()
  })
})

describe('ChatNoteSaveDialog：确认名称与保存位置', () => {
  const FOLDER_TREE = [
    { id: FOLDER_RO, name: '只读根', can_create: false, children: [
      { id: FOLDER_CHILD, name: '可写子级', can_create: true, children: [] },
    ] },
    { id: FOLDER_OK, name: '公共资料', can_create: true, children: [] },
  ]

  async function mountNote(props: Record<string, unknown>) {
    const submit = (props.submit as any) ?? vi.fn().mockResolvedValue({
      success: true,
      name: '存货监盘要点',
      location: '甲公司_2025（项目资料） / AI 对话笔记',
      jumpRoute: '/knowledge?folder_id=f&doc_id=d',
    })
    const { default: Dialog } = await import('../ChatNoteSaveDialog.vue')
    const wrapper = mount(Dialog, {
      // host 由各用例传入（Record 展开后 TS 推不出必填的 host），这里放宽到组件 props 本身校验
      props: { modelValue: true, count: 2, initial: null, ...props, submit } as any,
      global: { stubs: DIALOG_STUBS },
    })
    await flushPromises()
    return { wrapper, submit }
  }

  beforeEach(() => {
    mocks.listProjects.mockResolvedValue(PROJECTS)
    mocks.apiGet.mockResolvedValue(FOLDER_TREE)
  })

  it('有项目宿主：位置固定为本项目，不加载列表；保存后显示实际位置与查看入口', async () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null)
    const { wrapper, submit } = await mountNote({ host: WP_REF })
    expect(wrapper.find('[data-testid="note-fixed-location"]').text()).toContain('本项目的「AI 对话笔记」文件夹')
    expect(mocks.listProjects).not.toHaveBeenCalled()
    expect(mocks.apiGet).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('将选中的 2 条 AI 回复')

    const submitBtn = wrapper.find('[data-testid="note-submit"]')
    expect(submitBtn.attributes('disabled'), '未填名称不能保存').toBeDefined()
    await wrapper.find('[data-testid="note-name"]').setValue('  存货监盘要点 ')
    await submitBtn.trigger('click')
    await flushPromises()
    expect(submit).toHaveBeenCalledWith({ name: '存货监盘要点', target: { kind: 'host_project' } })

    const done = wrapper.find('[data-testid="note-saved"]')
    expect(done.text()).toContain('甲公司_2025（项目资料） / AI 对话笔记')
    expect(done.text()).toContain('存货监盘要点')
    expect(wrapper.emitted('saved')).toHaveLength(1)
    await wrapper.find('[data-testid="note-open"]').trigger('click')
    // 不带 noopener：令牌在 sessionStorage，noopener 的新标签拿不到 ⇒ 跳登录页（浏览器实测）
    expect(open).toHaveBeenCalledWith('/knowledge?folder_id=f&doc_id=d', '_blank')
    open.mockRestore()
  })

  it('全局宿主：默认「项目笔记」，选项目后提交项目位置', async () => {
    const { wrapper, submit } = await mountNote({ host: GLOBAL_REF })
    expect(mocks.listProjects).toHaveBeenCalledTimes(1)
    expect(mocks.apiGet).toHaveBeenCalledTimes(1)
    await wrapper.find('[data-testid="note-name"]').setValue('存货监盘要点')
    expect(wrapper.find('[data-testid="note-submit"]').attributes('disabled'), '未选位置不能保存').toBeDefined()
    await wrapper.find('[data-testid="note-project"]').setValue(P2)
    await wrapper.find('[data-testid="note-submit"]').trigger('click')
    await flushPromises()
    expect(submit).toHaveBeenCalledWith({ name: '存货监盘要点', target: { kind: 'project', projectId: P2 } })
  })

  it('知识库文件夹：没有新建权限的文件夹不能作为保存位置', async () => {
    const { wrapper, submit } = await mountNote({ host: GLOBAL_REF })
    await wrapper.find('[data-testid="note-name"]').setValue('存货监盘要点')
    await wrapper.find('.stub-radio[data-value="folder"]').trigger('click')
    const tree = wrapper.find('[data-testid="note-folder"]')
    const disabled = tree.findAll('option').filter((o) => o.attributes('disabled') !== undefined)
    expect(disabled.map((o) => o.text())).toEqual(['只读根'])

    await tree.setValue(FOLDER_RO)
    expect(wrapper.find('[data-testid="note-submit"]').attributes('disabled')).toBeDefined()
    await tree.setValue(FOLDER_CHILD)
    await wrapper.find('[data-testid="note-submit"]').trigger('click')
    await flushPromises()
    expect(submit).toHaveBeenCalledWith({ name: '存货监盘要点', target: { kind: 'folder', folderId: FOLDER_CHILD } })
  })

  it('知识库文件夹页面：默认选中当前文件夹；失败留在对话框显示原因', async () => {
    const submit = vi.fn().mockResolvedValue({ success: false, errorMessage: '所选保存位置不存在或无权访问' })
    const host: AiHostRef = { type: 'knowledge_folder', id: FOLDER_OK, projectId: null, year: null }
    const { wrapper } = await mountNote({ host, submit })
    expect((wrapper.find('[data-testid="note-folder"]').element as HTMLSelectElement).value).toBe(FOLDER_OK)
    await wrapper.find('[data-testid="note-name"]').setValue('准则摘录')
    await wrapper.find('[data-testid="note-submit"]').trigger('click')
    await flushPromises()
    expect(submit).toHaveBeenCalledWith({ name: '准则摘录', target: { kind: 'folder', folderId: FOLDER_OK } })
    expect(wrapper.find('.stub-alert[data-type="error"]').text()).toBe('所选保存位置不存在或无权访问')
    expect(wrapper.find('[data-testid="note-saved"]').exists()).toBe(false)
  })

  it('「在知识库中查看」只打开站内相对路径', async () => {
    const open = vi.spyOn(window, 'open').mockImplementation(() => null)
    const submit = vi.fn().mockResolvedValue({ success: true, name: 'x', jumpRoute: '//evil.example/k' })
    const { wrapper } = await mountNote({ host: WP_REF, submit })
    await wrapper.find('[data-testid="note-name"]').setValue('x')
    await wrapper.find('[data-testid="note-submit"]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-testid="note-open"]').trigger('click')
    expect(open).not.toHaveBeenCalled()
    open.mockRestore()
  })

  it('重试：预填上次的名称与位置', async () => {
    const { wrapper } = await mountNote({
      host: GLOBAL_REF,
      initial: { name: '上次的名称', target: { kind: 'project', projectId: P1 } },
    })
    expect((wrapper.find('[data-testid="note-name"]').element as HTMLInputElement).value).toBe('上次的名称')
    expect((wrapper.find('[data-testid="note-project"]').element as HTMLSelectElement).value).toBe(P1)
  })
})

// ===========================================================================
// 4. 面板分流：底稿 / 附注直接采纳，其余宿主先选目标；转存笔记先开对话框
// ===========================================================================

describe('PlatformAiChatPanel：采纳与转存笔记的入口分流', () => {
  const PANEL_STUBS = {
    'el-button': {
      props: ['disabled', 'loading', 'type', 'size', 'plain', 'text', 'icon'],
      emits: ['click'],
      template: '<button type="button" class="stub-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    },
    'el-tag': { template: '<span class="stub-tag"><slot /></span>' },
    'el-icon': { template: '<i class="stub-icon"><slot /></i>' },
    'el-empty': { props: ['description'], template: '<div class="stub-empty">{{ description }}</div>' },
    'el-input': { props: ['modelValue'], template: '<textarea class="stub-input" />' },
    'el-switch': { props: ['modelValue', 'disabled'], template: '<button class="stub-switch" type="button" />' },
    'el-progress': { template: '<div />' },
    // ChatMentionPicker 用到；只渲染被包裹的内容，避免「Failed to resolve component」告警
    'el-tooltip': { template: '<span class="stub-tooltip"><slot /></span>' },
    ChatAdoptTargetDialog: {
      name: 'ChatAdoptTargetDialogStub',
      props: ['modelValue', 'sourceHost', 'submit'],
      template: '<div class="stub-adopt-dialog" :data-open="String(modelValue)" />',
    },
    ChatNoteSaveDialog: {
      name: 'ChatNoteSaveDialogStub',
      props: ['modelValue', 'host', 'count', 'initial', 'submit'],
      template: '<div class="stub-note-dialog" :data-open="String(modelValue)" :data-count="count" />',
    },
  }

  function routeFetch() {
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
      const u = String(url)
      if (u.includes('/history')) {
        return okJson({ messages: [{ message_id: MSG, role: 'assistant', content: 'AI 结论', status: 'completed' }] })
      }
      if (u.includes('/review-prompt')) return okJson({ enabled: false })
      if ((init?.method ?? 'GET') === 'POST') return okJson({ success: true, jump_route: '/knowledge?doc_id=d' })
      return okJson({})
    })
  }

  async function mountPanel(host: AiHostRef) {
    routeFetch()
    const { default: Panel } = await import('../PlatformAiChatPanel.vue')
    const wrapper = mount(Panel, {
      props: { host: hostRequest(host), visible: true },
      global: { plugins: [createPinia()], stubs: PANEL_STUBS },
    })
    await flushPromises()
    return wrapper
  }

  function adoptButton(wrapper: any) {
    const btn = wrapper.findAll('button.stub-button').find((b: any) => b.text() === '采纳')
    expect(btn, '历史回复下没有「采纳」按钮').toBeTruthy()
    return btn
  }

  it('全局知识模式：点「采纳」打开选择目标，不发注定 404 的请求；选定后带 source_host 提交', async () => {
    const wrapper = await mountPanel(GLOBAL_REF)
    await adoptButton(wrapper).trigger('click')
    await flushPromises()
    expect(wrapper.find('.stub-adopt-dialog').attributes('data-open')).toBe('true')
    expect(bodiesTo('/api/ai-chat/adopt')).toHaveLength(0)

    const dialog = wrapper.findComponent({ name: 'ChatAdoptTargetDialogStub' })
    expect(dialog.props('sourceHost')).toEqual(GLOBAL_REF)
    const res = await dialog.props('submit')({ host: { type: 'workpaper', id: WP1, projectId: P1, year: null } })
    expect(res.success).toBe(true)
    const [body] = bodiesTo('/api/ai-chat/adopt')
    expect(body.message_id).toBe(MSG)
    expect(body.host.type).toBe('workpaper')
    expect(body.source_host.type).toBe('global_knowledge')
  })

  it('底稿宿主：点「采纳」直接提交当前底稿，不弹选择框', async () => {
    const wrapper = await mountPanel(WP_REF)
    await adoptButton(wrapper).trigger('click')
    await flushPromises()
    expect(wrapper.find('.stub-adopt-dialog').attributes('data-open')).toBe('false')
    const [body] = bodiesTo('/api/ai-chat/adopt')
    expect(body.host).toEqual({ type: 'workpaper', id: WP1, project_id: P1, year: 2025 })
    expect('source_host' in body).toBe(false)
    expect(mocks.msgSuccess).toHaveBeenCalledWith(expect.stringContaining('AI 生成内容待确认'))
  })

  it('转存笔记：先打开对话框（带选中条数），对话框提交走扁平请求体', async () => {
    const wrapper = await mountPanel(GLOBAL_REF)
    await wrapper.find('[aria-label="选择消息（可复制或转存为笔记）"]').trigger('click')
    await wrapper.find('.platform-ai-chat-panel__msg.assistant').trigger('click')
    const saveBtn = wrapper.findAll('button.stub-button').find((b: any) => b.text() === '转存笔记')
    await saveBtn!.trigger('click')
    expect(bodiesTo('/api/ai-chat/notes'), '点按钮不应直接提交').toHaveLength(0)
    const note = wrapper.find('.stub-note-dialog')
    expect(note.attributes('data-open')).toBe('true')
    expect(note.attributes('data-count')).toBe('1')

    const dialog = wrapper.findComponent({ name: 'ChatNoteSaveDialogStub' })
    const res = await dialog.props('submit')({ name: '审计问答', target: { kind: 'project', projectId: P1 } })
    expect(res.success).toBe(true)
    const [body] = bodiesTo('/api/ai-chat/notes')
    expect(body).toMatchObject({
      message_ids: [MSG], name: '审计问答', host_type: 'global_knowledge',
      host_id: 'global-knowledge', target_project_id: P1,
    })
  })
})
