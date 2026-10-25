/**
 * 宿主接线守卫（Feature: dsh-agent-panel-integration Task 2 → 迁移到统一内核面板）
 *
 * 前身是 `components/__tests__/DocAiChatPanel.host.spec.ts`：那份守卫挂的是旧组件
 * `DocAiChatPanel.vue`，而该组件自 Task 9 起已无任何生产引用（spec
 * knowledge-base-retrieval-and-authz-closure Task 11 删除）。守卫**意图**逐条迁到这里，
 * 断言对象换成真正在跑的 `PlatformAiChatPanel` + `usePlatformAiChat`（不 mock composable）。
 *
 * Requirements: 3.3, 3.4, 3.5；Property 5（宿主加载器唯一映射，前端一侧）。
 *
 * 两类判据，都不是「符号出现过」：
 * 1. **真实 mount + 真实网络调用计数**：不可用 / 全局模式 / 知识库无项目 / 底稿宿主分别挂上，
 *    断言 DOM（禁用态、中文原因）与 `fetch` 调用（宿主不可用时**一次都不发**；无项目时
 *    **不带** `project_id`）。以真实「打开面板」路径挂载（visible false → true），
 *    否则 open watcher 不触发，「零请求」会变成恒真的假绿 —— 底稿用例同时证明打开会发请求。
 * 2. **模板形态判据**：ReportView / DisclosureEditor / KnowledgeBase 依赖树太大、无法在 jsdom
 *    整页 mount，解析其 `<PlatformAiChatPanel>` 标签：只绑 `:host`，且被绑表达式在同文件由对应
 *    `buildXHost(...)` adapter 产生；旧的 `doc-type` / `doc-id` / `project-id` / `:year` 一个不剩。
 *    WorkpaperEditor 自 2026-09-09 起不再内嵌面板（由全局 DshPanel 承载，见
 *    PlatformAiChatPanel.spec.ts「宿主迁移完整性」），不在本表。
 */
import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 'test-token', user: { id: 'user-1', role: 'auditor' } }),
}))

// 运行状态 store 只关心「是否发起了 run」；transport 细节由 PlatformAiChatPanel.spec 覆盖
const runStore = vi.hoisted(() => ({
  startRun: vi.fn(),
  subscribe: vi.fn().mockResolvedValue(undefined),
}))
vi.mock('@/stores/chatRunState', () => ({
  useChatRunStateStore: () => ({
    phase: 'idle',
    runId: null,
    streamingDelta: '',
    displayError: null,
    isActive: false,
    isTerminal: false,
    startRun: runStore.startRun,
    subscribe: runStore.subscribe,
    cancel: vi.fn(),
    reset: vi.fn(),
    on: vi.fn().mockReturnValue(() => {}),
  }),
}))

import PlatformAiChatPanel from '../PlatformAiChatPanel.vue'
import {
  buildGlobalKnowledgeHost,
  buildKnowledgeFolderHost,
  buildReportHost,
  buildWorkpaperHost,
  type AiHostRequest,
} from '@/composables/useAiHostContext'

const PROJECT_ID = '22222222-2222-4222-8222-222222222222'
const WP_ID = '11111111-1111-4111-8111-111111111111'
const FOLDER_ID = '33333333-3333-4333-8333-333333333333'

const mockFetch = vi.fn()

/**
 * 输入框 / 按钮替身：透传 disabled / aria-label，让「禁用态」落在真实 DOM 属性上。
 * 只有 type=textarea 才渲染 <textarea>：面板里还有 mention 搜索框等其他 el-input，
 * 一律渲染成 textarea 会让 `find('textarea')` 命中错的输入框。
 */
const STUBS = {
  ElInput: {
    name: 'ElInput',
    props: ['modelValue', 'disabled', 'type', 'rows', 'placeholder', 'ariaLabel'],
    emits: ['update:modelValue'],
    template:
      '<textarea v-if="type === \'textarea\'" :disabled="disabled" :aria-label="ariaLabel" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)"></textarea>'
      + '<input v-else :disabled="disabled" :aria-label="ariaLabel" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  ElButton: {
    name: 'ElButton',
    props: ['disabled', 'loading', 'type', 'size', 'text', 'plain', 'icon'],
    emits: ['click'],
    template: '<button type="button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
}

async function openPanel(host: AiHostRequest) {
  const wrapper = mount(PlatformAiChatPanel, {
    props: { host, visible: false },
    global: { plugins: [createPinia()], stubs: STUBS },
  })
  await wrapper.setProps({ visible: true })
  await flushPromises()
  return wrapper
}

const fetchedUrls = () => mockFetch.mock.calls.map((c) => String(c[0]))
const sendButton = (w: ReturnType<typeof mount>) =>
  w.findAll('button').find((b) => b.text().includes('发送'))!
/** 主输入框（aria-label 以「AI 对话」开头：可用时「AI 对话输入框」，不可用时「AI 对话不可用：…」） */
const chatInput = (w: ReturnType<typeof mount>) => w.find('textarea[aria-label^="AI 对话"]')

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  mockFetch.mockReset()
  mockFetch.mockResolvedValue({ ok: true, json: async () => ({ messages: [] }) })
  globalThis.fetch = mockFetch as unknown as typeof fetch
})

describe('PlatformAiChatPanel — 宿主上下文的真实 DOM 与网络行为', () => {
  it('面板只声明 host / visible / sheetName（旧四标量已移除）', () => {
    const declared = Object.keys((PlatformAiChatPanel as any).props ?? {}).sort()
    expect(declared).toEqual(['host', 'sheetName', 'visible'])
    // 旧 prop 若仍被声明，宿主页面就能继续传 project ID 当 doc ID
    for (const legacy of ['docType', 'docId', 'projectId', 'year']) {
      expect(declared).not.toContain(legacy)
    }
  })

  it('宿主不可用 → 禁用输入与发送 + 展示中文原因 + 一次请求都不发', async () => {
    const host = buildReportHost({ reportType: 'cross_check', projectId: PROJECT_ID })
    expect(host.available).toBe(false)
    const wrapper = await openPanel(host)

    expect(wrapper.text()).toContain('不是单张报表')
    expect(chatInput(wrapper).exists()).toBe(true)
    expect(chatInput(wrapper).attributes('disabled')).toBeDefined()
    expect(sendButton(wrapper).attributes('disabled')).toBeDefined()
    // 打开面板时不拉历史（旧实现会用空 doc_id / 空 project_id 发请求）
    expect(mockFetch).not.toHaveBeenCalled()

    // 绕过禁用态直接调发送处理器：仍不发请求，且会话里给出的是**宿主不可用的中文原因**
    // —— 不是用户消息 +「AI 服务暂不可用」（宿主为 null 时硬走请求路径会先抛 TypeError，
    // fetch 同样不会被调用，只看零请求测不出来）。
    // 🔴 草稿必须直接写 draft：输入框此时是 disabled，test-utils 对禁用元素的 setValue 不派发
    //    input 事件 ⇒ 草稿为空 ⇒ sendMessage 在「空文本」处提前返回，根本到不了宿主判定
    //    （首版就是这么假绿的：变异「宿主不可用照发请求」判 GREEN）。
    const vm = wrapper.vm as any
    vm.draft = '这张报表有什么问题？'
    await flushPromises()
    expect(vm.draft).toBe('这张报表有什么问题？')
    vm.handleSend()
    await flushPromises()
    expect(mockFetch).not.toHaveBeenCalled()
    expect(runStore.startRun).not.toHaveBeenCalled()
    const messages = vm.messages as Array<{ role: string; text: string; status?: string }>
    expect(messages.filter((m) => m.role === 'user')).toEqual([])
    expect(messages).toHaveLength(1)
    expect(messages[0]).toMatchObject({ role: 'assistant', status: 'failed' })
    expect(messages[0].text).toContain('不是单张报表')
  })

  it('全局知识模式 → 历史按全局宿主拉取、绝不带 project_id，并给出范围说明', async () => {
    const wrapper = await openPanel(buildGlobalKnowledgeHost())
    expect(wrapper.text()).toContain('全局知识模式')
    expect(wrapper.text()).toContain('项目工具不可用')
    const urls = fetchedUrls()
    expect(urls.some((u) => u.startsWith('/api/ai-chat/doc/global_knowledge/global-knowledge/history'))).toBe(true)
    for (const url of urls) expect(url).not.toContain('project_id=')
  })

  it('知识库无项目页面 → 文件夹宿主可发送，但请求不带空 project_id', async () => {
    const wrapper = await openPanel(buildKnowledgeFolderHost({ folderId: FOLDER_ID, projectId: '' }))
    const urls = fetchedUrls()
    expect(urls.some((u) => u.startsWith(`/api/ai-chat/doc/knowledge_folder/${FOLDER_ID}/history`))).toBe(true)
    for (const url of urls) expect(url).not.toContain('project_id=')
    // 与「宿主不可用」形成对照：输入内容后发送按钮可用
    expect(chatInput(wrapper).attributes('disabled')).toBeUndefined()
    await chatInput(wrapper).setValue('这个文件夹里有哪些准则？')
    expect(sendButton(wrapper).attributes('disabled')).toBeUndefined()
  })

  it('底稿宿主 → 打开即按宿主稳定 ID 拉历史，并带权威 project_id（证明零请求断言不是恒真）', async () => {
    await openPanel(buildWorkpaperHost({ wpId: WP_ID, projectId: PROJECT_ID, auditYear: null }))
    expect(fetchedUrls()).toContain(
      `/api/ai-chat/doc/workpaper/${WP_ID}/history?project_id=${PROJECT_ID}`,
    )
  })
})

// ---------------------------------------------------------------------------
// 模板形态判据：宿主页面的输入契约
// ---------------------------------------------------------------------------

const VIEW_DIR = resolve(__dirname, '../../../views')

interface HostWiring {
  file: string
  builder: string
  /** adapter 参数里必须出现的字段名（证明确实用了本页面自己的稳定标识） */
  mustBind: string[]
}

const HOST_VIEWS: HostWiring[] = [
  { file: 'ReportView.vue', builder: 'buildReportHost', mustBind: ['reportType', 'projectId', 'year'] },
  { file: 'DisclosureEditor.vue', builder: 'buildNoteHost', mustBind: ['projectId', 'year'] },
  { file: 'KnowledgeBase.vue', builder: 'buildKnowledgeFolderHost', mustBind: ['folderId', 'projectId'] },
]

/**
 * 抓出 `<PlatformAiChatPanel ... />` 标签体（含全部绑定）。
 * 断言失败发生在 `describe.each` 的同步 body 里 ⇒ 整个文件零测试执行（collection error），
 * 所以标签名一旦漂移必须立刻改这里，不能靠「反正会报错」糊过去。
 */
function panelTag(source: string): string {
  const match = source.match(/<PlatformAiChatPanel\b[\s\S]*?\/>/)
  expect(match, 'PlatformAiChatPanel 标签未找到（宿主页面是否被改名或删除？）').toBeTruthy()
  return match![0]
}

describe.each(HOST_VIEWS)('宿主页面输入契约 — $file', ({ file, builder, mustBind }) => {
  const source = readFileSync(resolve(VIEW_DIR, file), 'utf-8')
  const tag = panelTag(source)

  it('只绑 :host，旧的四个标量绑定全部移除（Req 3.5）', () => {
    expect(tag).toMatch(/:host="/)
    for (const legacy of ['doc-type', 'doc-id', 'project-id', ':year']) {
      expect(tag).not.toContain(legacy)
    }
  })

  it(`:host 由 ${builder} adapter 产生，而不是就地拼装`, () => {
    const bound = tag.match(/:host="([^"]+)"/)![1].trim()
    const decl = new RegExp(`const\\s+${bound}\\s*=\\s*computed\\(\\(\\)\\s*=>\\s*\\r?\\n?\\s*${builder}\\(`)
    expect(source).toMatch(decl)
    expect(source).toMatch(
      new RegExp(`import\\s*\\{[^}]*\\b${builder}\\b[^}]*\\}\\s*from\\s*'@/composables/useAiHostContext'`),
    )
  })

  it('adapter 入参用本页面自己的稳定标识（不把 projectId 塞进文档位）', () => {
    const call = source.slice(source.indexOf(`${builder}({`))
    const args = call.slice(0, call.indexOf('})') + 2)
    for (const field of mustBind) expect(args).toContain(`${field}:`)
    expect(args).not.toMatch(/\b(wpId|reportType|folderId|noteId|sectionId):\s*projectId\b/)
  })
})

// ---------------------------------------------------------------------------
// 全局面板 / 独立窗口
// ---------------------------------------------------------------------------

describe('全局 DshPanel 与独立聊天窗口的宿主契约（Req 3.4/3.5）', () => {
  const AMBIENT_VIEWS = [
    resolve(__dirname, '../DshPanel.vue'),
    resolve(VIEW_DIR, 'ai/AIChatView.vue'),
  ]

  // 迁移说明：旧守卫要求两处各自 `hostHint = computed(() => hostScopeHint(...))` 并渲染、独立窗口
  // 再传 `:project-id="hostProjectId"`。统一内核后范围说明由 PlatformAiChatPanel 自带的
  // `.platform-ai-chat-panel__scope` 渲染（同一个 hostScopeHint，上面「全局知识模式」用例在真实
  // DOM 上断言了它），面板也不再声明 projectId prop —— 旧判据描述的是已被取代的形态。
  // （旧文件因 describe.each 同步体抛错整体收集失败，这两条多日未执行，所以没人发现它们已过期。）
  // 意图保留：宿主只能由 buildAmbientHost 构造、只经 `:host` 传入，不另传项目 ID、不重复渲染说明。
  it.each(AMBIENT_VIEWS)('%s 通过 buildAmbientHost 构造宿主，只经 :host 交给统一面板', (file) => {
    const source = readFileSync(file, 'utf-8')
    expect(source).toMatch(
      /import\s*\{[^}]*\bbuildAmbientHost\b[^}]*\}\s*from\s*'@\/composables\/useAiHostContext'/,
    )
    expect(source).toMatch(/const\s+aiHost\s*=\s*computed\(\(\)\s*=>\s*\r?\n?\s*buildAmbientHost\(/)
    const tag = panelTag(source)
    expect(tag).toMatch(/:host="aiHost"/)
    for (const legacy of ['project-id', 'doc-id', 'doc-type', ':year']) {
      expect(tag).not.toContain(legacy)
    }
  })

  it('独立窗口不再自行渲染第二条范围说明（面板已渲染同一句）', () => {
    const source = readFileSync(resolve(VIEW_DIR, 'ai/AIChatView.vue'), 'utf-8')
    expect(source).not.toMatch(/\{\{\s*hostHint\s*\}\}/)
    // 旧实现直接把 route.params.projectId 透给面板
    expect(source).not.toMatch(/:project-id=/)
  })
})
