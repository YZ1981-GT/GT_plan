/**
 * Task 2 宿主接线守卫（Feature: dsh-agent-panel-integration）
 *
 * Requirements: 3.3, 3.4, 3.5, 3.6
 * Properties:
 *   - **Property 5（宿主加载器唯一映射）** 前端一侧：空 project ID 不会被构造成有效项目
 *     HostContext；六个宿主页面通过各自 adapter 构造同一 HostContext 请求。
 *     **Validates: Requirements 3.1, 3.2, 3.4, 3.7**
 *
 * 两类判据，都不是"符号出现过"：
 *
 * 1. **真实 mount + 真实网络调用计数**：把不可用 / 全局模式 / 正常宿主分别挂到
 *    `DocAiChatPanel`，断言 DOM（禁用态、中文原因）与 `fetch` 调用（宿主不可用时
 *    **一次都不发**，避免旧实现那种 `doc_id=''` 的必然失败请求）。
 * 2. **模板形态判据**：四个宿主页面（WorkpaperEditor / ReportView / DisclosureEditor /
 *    KnowledgeBase）依赖树太大、无法在 jsdom 里整页 mount，改为解析其 SFC 模板中
 *    `<PlatformAiChatPanel>` 标签（Task 9 起统一内核面板）的**绑定形态**：必须只绑
 *    `:host`，且被绑表达式在同文件里由
 *    对应的 `buildXHost(...)` adapter 产生；旧的 `:doc-type` / `:doc-id` / `:project-id` /
 *    `:year` 绑定一个都不能剩。这条判据能抓住"改回把 projectId 当 docId"的回退
 *    （见 Task 2 变异脚本 M2x）。
 */

import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: {}, query: {} }),
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 'test-token', user: { id: 'user-1', role: 'auditor' } }),
}))

const mockFetch = vi.fn()
global.fetch = mockFetch as unknown as typeof fetch

import DocAiChatPanel from '../DocAiChatPanel.vue'
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

/**
 * 以**真实"打开面板"路径**挂载：先 visible=false 再切 true，触发面板的 open watcher。
 * 直接 mount 成 visible=true 不会触发 watcher，历史/知识范围请求也就不会发出，
 * 那样"零请求"断言会变成恒真的假绿。
 */
async function openPanel(host: AiHostRequest) {
  const wrapper = mount(DocAiChatPanel, {
    props: { host, visible: false },
    global: {
      plugins: [ElementPlus, createPinia()],
      stubs: {
        'el-drawer': {
          template: '<div class="mock-drawer" v-if="modelValue"><slot /></div>',
          props: ['modelValue', 'title', 'direction', 'size', 'destroyOnClose'],
        },
      },
    },
  })
  await wrapper.setProps({ visible: true })
  await flushPromises()
  return wrapper
}

/** 空的 SSE 响应体（避免 sendMessage 因 body 缺失走异常分支产生噪声）。 */
function emptyStreamResponse() {
  return {
    ok: true,
    body: {
      getReader: () => ({
        read: async () => ({ done: true, value: undefined }),
      }),
    },
    json: async () => ({ messages: [] }),
  }
}

describe('DocAiChatPanel — 宿主上下文的真实 DOM 与网络行为', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockFetch.mockReset()
    mockFetch.mockResolvedValue({ ok: true, json: async () => ({ messages: [], items: [] }) })
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue(null)
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {})
  })

  it('面板只声明 host / visible 两个 prop（旧四标量已移除）', () => {
    const declared = Object.keys((DocAiChatPanel as any).props ?? {}).sort()
    expect(declared).toEqual(['host', 'visible'])
    // 旧 prop 若仍被声明，宿主页面就能继续传 project ID 当 doc ID
    for (const legacy of ['docType', 'docId', 'projectId', 'year']) {
      expect(declared).not.toContain(legacy)
    }
  })

  it('宿主不可用 → 禁用发送 + 展示中文原因 + 一次请求都不发', async () => {
    const host = buildReportHost({ reportType: 'cross_check', projectId: PROJECT_ID })
    expect(host.available).toBe(false)
    const wrapper = await openPanel(host)

    // 中文原因真的渲染在 DOM 里
    expect(wrapper.text()).toContain('不是单张报表')
    // 输入框与发送按钮禁用
    const textarea = wrapper.find('textarea')
    expect(textarea.attributes('disabled')).toBeDefined()
    const sendBtn = wrapper.findAll('button').find((b) => b.text().includes('发送'))
    expect(sendBtn?.attributes('disabled')).toBeDefined()

    // 打开面板时不拉历史、不拉知识范围（旧实现会用空 doc_id / 空 project_id 发请求）
    expect(mockFetch).not.toHaveBeenCalled()

    // 直接调用发送：不发请求，改为在会话里给出中文原因
    const vm = wrapper.vm as any
    vm.inputText = '这张报表有什么问题？'
    await vm.sendMessage()
    await flushPromises()
    expect(mockFetch).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('不是单张报表')
  })

  it('受限全局知识模式 → 项目工具（@ 知识范围）禁用且不发 project_id 查询', async () => {
    const wrapper = await openPanel(buildGlobalKnowledgeHost())

    expect(wrapper.text()).toContain('全局知识')
    expect(wrapper.text()).toContain('项目工具不可用')

    const mentionBtn = wrapper.findAll('button').find((b) => b.text().trim() === '@')
    expect(mentionBtn).toBeTruthy()
    expect(mentionBtn!.attributes('disabled')).toBeDefined()

    // 历史请求会发（全局会话有历史），但绝不能带 project_id
    const urls = mockFetch.mock.calls.map((c) => String(c[0]))
    expect(urls.some((u) => u.includes('/api/ai-chat/doc/global_knowledge/global-knowledge'))).toBe(
      true,
    )
    for (const url of urls) {
      expect(url).not.toContain('project_id=')
      expect(url).not.toContain('project_id=undefined')
    }
  })

  it('知识库无项目页面 → 走全局范围提示，不发空 project_id', async () => {
    const wrapper = await openPanel(
      buildKnowledgeFolderHost({ folderId: FOLDER_ID, projectId: '' }),
    )
    expect(wrapper.text()).toContain('知识库文件夹')
    const urls = mockFetch.mock.calls.map((c) => String(c[0]))
    expect(urls.length).toBeGreaterThan(0)
    for (const url of urls) {
      expect(url).not.toContain('project_id=')
    }
    // 文件夹已选定 → 输入内容后可发送（与"宿主不可用"用例形成对照）
    const vm = wrapper.vm as any
    vm.inputText = '这个文件夹里有哪些准则？'
    await flushPromises()
    const sendBtnDisabled = wrapper
      .findAll('button')
      .find((b) => b.text().includes('发送'))!
      .attributes('disabled')
    expect(sendBtnDisabled).toBeUndefined()
    // 但项目工具（@ 知识范围）因无项目绑定仍关闭
    expect(
      wrapper.findAll('button').find((b) => b.text().trim() === '@')!.attributes('disabled'),
    ).toBeDefined()
  })

  it('底稿宿主 → 请求路径用宿主稳定 ID，年度断言为 null 时不猜', async () => {
    const wrapper = await openPanel(
      buildWorkpaperHost({ wpId: WP_ID, projectId: PROJECT_ID, auditYear: null }),
    )
    // 打开时确实发过历史请求（证明"零请求"断言在其他用例里不是恒真）
    const openUrls = mockFetch.mock.calls.map((c) => String(c[0]))
    expect(
      openUrls.some((u) => u.startsWith(`/api/ai-chat/doc/workpaper/${WP_ID}/history`)),
    ).toBe(true)

    mockFetch.mockClear()
    mockFetch.mockResolvedValue(emptyStreamResponse())

    const vm = wrapper.vm as any
    vm.inputText = '这份底稿有什么风险？'
    await vm.sendMessage()
    await flushPromises()

    const post = mockFetch.mock.calls.find((c) => (c[1] as any)?.method === 'POST')
    expect(post).toBeTruthy()
    expect(String(post![0])).toBe(`/api/ai-chat/doc/workpaper/${WP_ID}`)
    const body = JSON.parse((post![1] as any).body)
    expect(body.project_id).toBe(PROJECT_ID)
    // 关键：取不到权威年度就传 null，不传「当前年份-1」（那会被服务端判 mismatch）
    expect(body.year).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 模板形态判据：四个宿主页面的输入契约
// ---------------------------------------------------------------------------

const VIEW_DIR = resolve(__dirname, '../../views')

interface HostWiring {
  file: string
  builder: string
  /** adapter 参数里必须出现的字段名（证明确实用了本页面自己的稳定标识） */
  mustBind: string[]
}

const HOST_VIEWS: HostWiring[] = [
  {
    file: 'WorkpaperEditor.vue',
    builder: 'buildWorkpaperHost',
    mustBind: ['wpId', 'projectId', 'auditYear'],
  },
  {
    file: 'ReportView.vue',
    builder: 'buildReportHost',
    mustBind: ['reportType', 'projectId', 'year'],
  },
  {
    file: 'DisclosureEditor.vue',
    builder: 'buildNoteHost',
    mustBind: ['projectId', 'year'],
  },
  {
    file: 'KnowledgeBase.vue',
    builder: 'buildKnowledgeFolderHost',
    mustBind: ['folderId', 'projectId'],
  },
]

/**
 * 抓出 `<PlatformAiChatPanel ... />` 标签体（含全部绑定）。
 *
 * Task 9 把四个宿主 view 从旧的 `<DocAiChatPanel>` 迁到统一内核
 * `<PlatformAiChatPanel>`，本判据锁的是**当前生产形态**。
 * 注意：这里断言失败发生在 `describe.each` 的同步 body 里 ⇒ 整个文件会
 * 零测试执行（collection error），所以标签名一旦漂移必须立刻改这里，
 * 不能靠"反正会报错"糊过去。
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
    // 绑定的表达式必须在同文件里由 adapter 定义
    const decl = new RegExp(`const\\s+${bound}\\s*=\\s*computed\\(\\(\\)\\s*=>\\s*\\n?\\s*${builder}\\(`)
    expect(source).toMatch(decl)
    // adapter 必须从本模块导入（不允许各页面自造同名函数）
    expect(source).toMatch(
      new RegExp(`import\\s*\\{[^}]*\\b${builder}\\b[^}]*\\}\\s*from\\s*'@/composables/useAiHostContext'`),
    )
  })

  it('adapter 入参用本页面自己的稳定标识（不把 projectId 塞进文档位）', () => {
    const call = source.slice(source.indexOf(`${builder}({`))
    const args = call.slice(0, call.indexOf('})') + 2)
    for (const field of mustBind) {
      expect(args).toContain(`${field}:`)
    }
    // 文档位字段（第一个参数键）绝不能直接是 projectId
    expect(args).not.toMatch(/\b(wpId|reportType|folderId|noteId|sectionId):\s*projectId\b/)
  })
})

// ---------------------------------------------------------------------------
// 全局面板 / 独立窗口
// ---------------------------------------------------------------------------

describe('全局 DshPanel 与独立聊天窗口的宿主契约（Req 3.4/3.5）', () => {
  const AMBIENT_VIEWS = [
    resolve(__dirname, '../ai/DshPanel.vue'),
    resolve(VIEW_DIR, 'ai/AIChatView.vue'),
  ]

  it.each(AMBIENT_VIEWS)('%s 通过 buildAmbientHost 构造宿主并渲染中文范围说明', (file) => {
    const source = readFileSync(file, 'utf-8')
    expect(source).toMatch(
      /import\s*\{[^}]*\bbuildAmbientHost\b[^}]*\}\s*from\s*'@\/composables\/useAiHostContext'/,
    )
    expect(source).toMatch(/const\s+aiHost\s*=\s*computed\(\(\)\s*=>\s*\n?\s*buildAmbientHost\(/)
    // 宿主提示必须真的渲染出来（有消费方，不是死代码）
    expect(source).toMatch(/const\s+hostHint\s*=\s*computed\(\(\)\s*=>\s*hostScopeHint\(/)
    expect(source).toMatch(/\{\{\s*hostHint\s*\}\}/)
  })

  it('独立窗口只把 adapter 反查过的项目 ID 传下去（不传空串）', () => {
    const source = readFileSync(resolve(VIEW_DIR, 'ai/AIChatView.vue'), 'utf-8')
    expect(source).toMatch(/:project-id="hostProjectId"/)
    expect(source).toMatch(/aiHost\.value\.host\?\.projectId \?\? null/)
    // 旧实现直接把 route.params.projectId 透给面板
    expect(source).not.toMatch(/:project-id="currentProjectId"/)
  })
})
