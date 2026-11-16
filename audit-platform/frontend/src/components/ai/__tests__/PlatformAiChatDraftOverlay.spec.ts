/**
 * 「纳入当前未保存草稿」开关与消息标注守卫（spec chat-host-draft-overlay / Task 5）
 *
 * Requirements:
 *   - 4.4：开关**默认关闭**，用户显式开启才把未保存草稿送进本轮上下文。
 *   - 5.2：**不改既有「提示未纳入」文案** —— 关闭时范围文案与 `hostScopeHint()` **逐字相同**。
 *   - 6.1：默认关闭时行为与现状完全一致。
 *   - 2.5：manifest 区分「已保存内容」与「未保存草稿」，前端在消息上标注。
 *
 * ## 为什么每条判据都在真实 DOM / 真实请求体上
 *
 * 「开关渲染了」「文案里有那两个字」都不算交付：
 * ① 开关默认 `true` 也能通过"存在"类断言；
 * ② 文案用 `toContain` 断言时，"不会纳入本轮"与"将纳入"可以同时出现；
 * ③ 面板把草稿读在开关回调里、提交时用旧快照，单测全绿而用户点了开关后改的那格永远丢。
 *
 * 所以这里：真实 mount → 点真实开关（stub 只是把 el-switch 换成原生 button）→
 * 点发送 → **读被拦截的 fetch 请求体**；denied / included 走真实的 `context_ready` 事件链
 * （经 `usePlatformAiChat` 的 runStore handler，不是直接改 messages）。
 *
 * 🔴 不弹窗：需求 4.4 与 design §5.5 都要求 `denied` 只是消息下方的内联提示。
 * 因此每条涉及 denied 的用例都断言 ElMessage / ElMessageBox / window.alert **未被调用**。
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick, ref, type Ref } from 'vue'

import type { AiHostRequest } from '@/composables/useAiHostContext'
import {
  buildGlobalKnowledgeHost,
  buildWorkpaperHost,
  hostScopeHint,
} from '@/composables/useAiHostContext'
import {
  clearWorkpaperDraftAccessors,
  registerWorkpaperDraftAccessor,
  type WorkpaperDraftAccessor,
} from '@/composables/workpaper/workpaperDraftOverlay'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 'test-token' }),
}))

/**
 * element-plus 只提供面板与子组件用到的**函数**（组件走 `global.stubs`）。
 * `ElMessageBox` 的存在本身是判据的一部分：denied 不许走它。
 */
const elMessage = vi.hoisted(() => ({
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
}))
const elMessageBox = vi.hoisted(() => ({
  prompt: vi.fn(),
  confirm: vi.fn(),
  alert: vi.fn(),
}))
vi.mock('element-plus', () => ({
  ElMessage: elMessage,
  ElMessageBox: elMessageBox,
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ params: {}, query: {} }),
}))

/**
 * run 状态 store 替身。
 *
 * 🔴 `on()` 必须**真的登记 handler** 并能在 `subscribe()` 期间派发事件 ——
 * 面板的「本轮草稿纳入结果」正是从 `context_ready` 的 manifest 来的；
 * 若像既有 `PlatformAiChatPanel.spec.ts` 那样把 `on` 写成恒返回空函数，
 * 这条链路就永远测不到（断言只能看源码字符串）。
 */
const runStoreState = vi.hoisted(() => {
  const handlers = new Map<string, Set<(e: any) => void>>()
  return {
    handlers,
    on(type: string, handler: (e: any) => void) {
      if (!handlers.has(type)) handlers.set(type, new Set())
      handlers.get(type)!.add(handler)
      return () => { handlers.get(type)?.delete(handler) }
    },
    emit(type: string, payload: Record<string, any> = {}, messageId: string | null = 'srv-msg-1') {
      const event = {
        event_id: 'evt-1',
        run_id: 'run-abc',
        session_id: 'sess-xyz',
        request_id: 'req-1',
        type,
        timestamp: '2026-11-15T10:00:00+00:00',
        message_id: messageId,
        payload,
      }
      for (const handler of handlers.get(type) ?? []) handler(event)
    },
    clear() {
      handlers.clear()
    },
  }
})

const runStore = vi.hoisted(() => ({
  startRun: vi.fn(),
  subscribe: vi.fn(),
  cancel: vi.fn(),
  reset: vi.fn(),
  setQuota: vi.fn(),
}))

vi.mock('@/stores/chatRunState', () => ({
  useChatRunStateStore: () => ({
    phase: 'idle',
    runId: null,
    errorCode: null,
    retryAfter: null,
    streamingDelta: '',
    displayError: null,
    contextManifest: null,
    isActive: false,
    isTerminal: false,
    startRun: runStore.startRun,
    subscribe: runStore.subscribe,
    cancel: runStore.cancel,
    reset: () => {
      runStore.reset()
      // 真实 store 的 reset() 会清空 handler 表（新一轮重新登记）
      runStoreState.clear()
    },
    on: runStoreState.on,
    setQuota: runStore.setQuota,
  }),
}))

// ---------------------------------------------------------------------------
// Element Plus 替身
// ---------------------------------------------------------------------------

/**
 * el-switch 替身：原生 button + `aria-pressed`，点击即 `update:modelValue="!modelValue"`。
 *
 * 🔴 必须真的能切换：否则「默认关闭」与「开启后文案变化」两条判据都只能靠读源码。
 * `activeText` 透传成可见文字，让「开关的中文标签」也落在真实 DOM 上。
 */
const EL_STUBS = {
  'el-input': {
    name: 'ElInputStub',
    props: ['modelValue', 'disabled', 'placeholder', 'rows', 'type', 'ariaLabel'],
    emits: ['update:modelValue'],
    template:
      '<textarea class="stub-input" :disabled="disabled" :value="modelValue"'
      + ' @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  'el-button': {
    name: 'ElButtonStub',
    props: ['disabled', 'loading', 'type', 'size', 'plain', 'text', 'icon'],
    emits: ['click'],
    template:
      '<button class="stub-button" type="button" :disabled="disabled"'
      + ' @click="$emit(\'click\')"><slot /></button>',
  },
  'el-tag': {
    name: 'ElTagStub',
    props: {
      type: { type: String, default: '' },
      size: { type: String, default: '' },
      effect: { type: String, default: '' },
      closable: { type: Boolean, default: false },
    },
    template: '<span class="stub-tag"><slot /></span>',
  },
  'el-switch': {
    name: 'ElSwitchStub',
    props: {
      modelValue: { type: Boolean, default: false },
      disabled: { type: Boolean, default: false },
      activeText: { type: String, default: '' },
      size: { type: String, default: '' },
      ariaLabel: { type: String, default: '' },
    },
    emits: ['update:modelValue', 'change'],
    template:
      '<button class="stub-switch" type="button"'
      + ' :aria-pressed="modelValue ? \'true\' : \'false\'"'
      + ' :aria-label="ariaLabel" :disabled="disabled"'
      + ' @click="$emit(\'update:modelValue\', !modelValue)">{{ activeText }}</button>',
  },
  'el-icon': { template: '<i class="stub-icon"><slot /></i>' },
  'el-empty': { props: ['description'], template: '<div class="stub-empty">{{ description }}</div>' },
  'el-upload': { template: '<div class="stub-upload"><slot /></div>' },
  'el-progress': { template: '<div class="stub-progress" />' },
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const PROJECT_ID = '22222222-2222-4222-8222-222222222222'
const WP_ID = '11111111-1111-4111-8111-111111111111'
const BASELINE = '2026-11-15T10:00:00+00:00'
const CJK_RE = /[\u4e00-\u9fff]/

function workpaperHost(): AiHostRequest {
  return buildWorkpaperHost({ wpId: WP_ID, projectId: PROJECT_ID, auditYear: 2025 })
}

/** 登记一个可控的编辑器访问器（dirty / content 都是 ref，改了就影响面板）。 */
function registerAccessor(options: {
  dirty: Ref<boolean>
  content: Ref<string>
  baseline?: string | null
  wpId?: string
}): WorkpaperDraftAccessor {
  const accessor: WorkpaperDraftAccessor = {
    wpId: () => options.wpId ?? WP_ID,
    hasUnsaved: () => options.dirty.value,
    currentDraftContent: () => (options.dirty.value ? options.content.value : null),
    openedBaselineVersion: () =>
      options.baseline === undefined ? BASELINE : options.baseline,
  }
  registerWorkpaperDraftAccessor(accessor)
  return accessor
}

interface FetchCall { url: string; init: RequestInit | undefined }

/** 拦截 fetch：返回可用的 run 创建响应，并记录全部调用。 */
function installFetchSpy(): FetchCall[] {
  const calls: FetchCall[] = []
  const spy = vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url: String(url), init })
    return {
      ok: true,
      status: 200,
      json: async () => ({
        data: {
          run_id: 'run-abc',
          session_id: 'sess-xyz',
          events_url: '/api/ai-chat/runs/run-abc/events',
        },
      }),
    } as unknown as Response
  })
  vi.stubGlobal('fetch', spy)
  return calls
}

/** 取 POST /runs 的请求体（解析后的对象）。 */
function readRunRequestBody(calls: FetchCall[]): Record<string, any> | null {
  const call = calls.find(
    (c) => c.url.includes('/api/ai-chat/runs') && (c.init?.method ?? '').toUpperCase() === 'POST',
  )
  if (!call || typeof call.init?.body !== 'string') return null
  return JSON.parse(call.init.body)
}

async function mountPanel(host: AiHostRequest = workpaperHost()) {
  const { default: PlatformAiChatPanel } = await import('../PlatformAiChatPanel.vue')
  return mount(PlatformAiChatPanel, {
    props: { host, visible: false },
    global: { plugins: [createPinia()], stubs: EL_STUBS },
  })
}

/** 提问输入框（`aria-describedby` 唯一定位；mention picker 的搜索框也在输入区里）。 */
function composer(wrapper: any) {
  const el = wrapper.find('textarea[aria-describedby="chat-input-status"]')
  expect(el.exists(), '找不到提问输入框（aria-describedby="chat-input-status"）').toBe(true)
  return el
}

/** 草稿开关（限定在它自己的容器里，避免命中复核模式条那个 el-switch）。 */
function draftSwitch(wrapper: any) {
  return wrapper.find('.platform-ai-chat-panel__draft-overlay .stub-switch')
}

function scopeHintText(wrapper: any): string {
  return wrapper.find('.platform-ai-chat-panel__hint').text()
}

async function typeDraft(wrapper: any, text: string) {
  await composer(wrapper).setValue(text)
  await nextTick()
}

async function clickSend(wrapper: any) {
  const btn = wrapper.find('button[aria-label="发送问题"]')
  expect(btn.exists(), '找不到发送按钮（aria-label="发送问题"）').toBe(true)
  await btn.trigger('click')
  await flushPromises()
}

/** 断言本轮没有任何"弹窗/提示"通道被使用（需求 4.4：不弹窗、不阻断）。 */
function expectNoModalOrToast() {
  for (const fn of Object.values(elMessageBox)) {
    expect(fn, 'denied 时不许弹对话框').not.toHaveBeenCalled()
  }
  expect(elMessage.success).not.toHaveBeenCalled()
  expect(elMessage.error).not.toHaveBeenCalled()
  expect(window.alert as unknown as ReturnType<typeof vi.fn>).not.toHaveBeenCalled()
}

// ===========================================================================
// Tests
// ===========================================================================

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  clearWorkpaperDraftAccessors()
  runStoreState.clear()
  runStore.subscribe.mockResolvedValue(undefined)
  vi.spyOn(window, 'alert').mockImplementation(() => undefined)
  vi.spyOn(window, 'confirm').mockImplementation(() => true)
})

afterEach(() => {
  clearWorkpaperDraftAccessors()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('开关的显示条件（需求 4.4 / design §5.2）', () => {
  it('宿主没有未保存修改 → 不渲染开关，范围文案保持既有「未保存修改不会纳入本轮」', async () => {
    installFetchSpy()
    const host = workpaperHost()
    const wrapper = await mountPanel(host)

    expect(wrapper.find('.platform-ai-chat-panel__draft-overlay').exists()).toBe(false)
    // 需求 5.2 / 6.1：关闭态文案与既有函数**逐字相同**（不是 toContain）
    expect(scopeHintText(wrapper)).toBe(hostScopeHint(host))
    expect(scopeHintText(wrapper)).toContain('当前未保存修改不会纳入本轮')
  })

  it('宿主有未保存修改 → 开关出现，中文标签可读，且**默认关闭**', async () => {
    installFetchSpy()
    const dirty = ref(true)
    registerAccessor({ dirty, content: ref('未保存的一格') })
    const wrapper = await mountPanel()

    const toggle = draftSwitch(wrapper)
    expect(toggle.exists()).toBe(true)
    expect(toggle.text()).toContain('纳入当前未保存草稿')
    // 需求 4.4：默认关闭（避免误把半成品当权威数据）
    expect(toggle.attributes('aria-pressed')).toBe('false')
    expect((wrapper.vm as any).includeDraftOverlay).toBe(false)
    // 关闭态文案仍逐字是既有那句
    expect(scopeHintText(wrapper)).toBe(hostScopeHint(workpaperHost()))
  })

  it('非底稿宿主（全局知识模式）即便有登记也不显示开关', async () => {
    installFetchSpy()
    registerAccessor({ dirty: ref(true), content: ref('未保存的一格') })
    const wrapper = await mountPanel(buildGlobalKnowledgeHost())

    expect(wrapper.find('.platform-ai-chat-panel__draft-overlay').exists()).toBe(false)
  })

  it('保存后（未保存修改消失）→ 开关自动归零并隐藏，不会静默跟到下一轮', async () => {
    installFetchSpy()
    const dirty = ref(true)
    registerAccessor({ dirty, content: ref('未保存的一格') })
    const wrapper = await mountPanel()

    await draftSwitch(wrapper).trigger('click')
    await nextTick()
    expect((wrapper.vm as any).includeDraftOverlay).toBe(true)

    // 用户点了保存 ⇒ 没有未保存修改了
    dirty.value = false
    await nextTick()
    await flushPromises()

    expect(wrapper.find('.platform-ai-chat-panel__draft-overlay').exists()).toBe(false)
    expect((wrapper.vm as any).includeDraftOverlay).toBe(false)
  })
})

describe('范围文案随开关变化（需求 5.2 / design §5.3）', () => {
  it('开启 → 换成「将纳入当前未保存草稿（基于版本 v…）」，旧尾句消失', async () => {
    installFetchSpy()
    registerAccessor({ dirty: ref(true), content: ref('未保存的一格') })
    const wrapper = await mountPanel()

    await draftSwitch(wrapper).trigger('click')
    await nextTick()

    const text = scopeHintText(wrapper)
    expect(text).toContain('将纳入当前未保存草稿（基于版本 v')
    expect(text).toContain('2026-11-15 10:00:00 UTC')
    expect(text).not.toContain('当前未保存修改不会纳入本轮')
    // 前缀（宿主标签）没被重写
    expect(text.startsWith('当前范围：底稿；')).toBe(true)
  })

  it('关闭 → 文案回到既有那句（开关可来回切换，不是单向）', async () => {
    installFetchSpy()
    registerAccessor({ dirty: ref(true), content: ref('未保存的一格') })
    const wrapper = await mountPanel()

    await draftSwitch(wrapper).trigger('click')
    await nextTick()
    expect(scopeHintText(wrapper)).toContain('将纳入当前未保存草稿')

    await draftSwitch(wrapper).trigger('click')
    await nextTick()
    expect(scopeHintText(wrapper)).toBe(hostScopeHint(workpaperHost()))
  })
})

describe('提交载荷（design §5.4 / 需求 6.1）', () => {
  it('开关关闭 → 请求体里没有 draft_overlay 键（默认关闭时行为与现状完全一致）', async () => {
    const calls = installFetchSpy()
    registerAccessor({ dirty: ref(true), content: ref('未保存的一格') })
    const wrapper = await mountPanel()

    await typeDraft(wrapper, '这份底稿有什么问题？')
    await clickSend(wrapper)

    const body = readRunRequestBody(calls)
    expect(body, '没有发出 POST /api/ai-chat/runs').not.toBeNull()
    expect('draft_overlay' in body!).toBe(false)
  })

  it('开关打开 → draft_overlay 带齐五个字段，host_id 取宿主稳定 ID', async () => {
    const calls = installFetchSpy()
    registerAccessor({ dirty: ref(true), content: ref('未保存的一格') })
    const wrapper = await mountPanel()

    await draftSwitch(wrapper).trigger('click')
    await nextTick()
    await typeDraft(wrapper, '看看我改的这一格')
    await clickSend(wrapper)

    const body = readRunRequestBody(calls)
    expect(body!.draft_overlay).toEqual({
      host_type: 'workpaper',
      host_id: WP_ID,
      baseline_version: BASELINE,
      content: '未保存的一格',
      content_length: '未保存的一格'.length,
    })
  })

  it('开关打开但草稿在提交时已不可用（基线读不出来）→ 省略该键 + 一句中文提示，**不阻断发送**', async () => {
    const calls = installFetchSpy()
    // 有未保存修改（开关因此可见），但取不到打开时的基线版本 ——
    // `readWorkpaperDraftOverlay` 会 fail-closed 返回 null（后端对空基线判 denied，
    // 前端先挡住，免得用户看到「将纳入」却被服务端拒绝）。
    registerAccessor({ dirty: ref(true), content: ref('未保存的一格'), baseline: null })
    const wrapper = await mountPanel()

    await draftSwitch(wrapper).trigger('click')
    await nextTick()
    // 开关确实开着（否则本条测的是另一条路径）
    expect((wrapper.vm as any).includeDraftOverlay).toBe(true)

    await typeDraft(wrapper, '还是问一下')
    await clickSend(wrapper)

    const body = readRunRequestBody(calls)
    expect(body, '草稿不可用时也必须照常发出请求').not.toBeNull()
    expect('draft_overlay' in body!).toBe(false)
    // 明确告诉用户"这份草稿没带上"，避免他以为带上了
    expect(elMessage.warning).toHaveBeenCalledTimes(1)
    expect(elMessage.warning.mock.calls[0][0]).toMatch(CJK_RE)
  })

  it('开关打开但正文超过上限（20 万字符）→ 同样省略该键 + 中文提示，不阻断', async () => {
    const calls = installFetchSpy()
    // 后端对超限是**直接 422 不裁剪**，放行会让整轮对话失败，所以前端先不发。
    const huge = 'x'.repeat(200_001)
    registerAccessor({ dirty: ref(true), content: ref(huge) })
    const wrapper = await mountPanel()

    await draftSwitch(wrapper).trigger('click')
    await nextTick()
    await typeDraft(wrapper, '超长草稿怎么办')
    await clickSend(wrapper)

    const body = readRunRequestBody(calls)
    expect(body).not.toBeNull()
    expect('draft_overlay' in body!).toBe(false)
    expect(elMessage.warning).toHaveBeenCalledTimes(1)
    expect(elMessage.warning.mock.calls[0][0]).toMatch(CJK_RE)
  })

  it('草稿是在**提交那一刻**读取的：开了开关之后又改的内容也会带上', async () => {
    const calls = installFetchSpy()
    const content = ref('第一次改的内容')
    registerAccessor({ dirty: ref(true), content })
    const wrapper = await mountPanel()

    await draftSwitch(wrapper).trigger('click')
    await nextTick()

    // 用户点完开关又改了一格（这是最容易被"开关回调里取快照"写法漏掉的场景）
    content.value = '点了开关之后又改的内容'
    await nextTick()

    await typeDraft(wrapper, '看看最新这版')
    await clickSend(wrapper)

    const body = readRunRequestBody(calls)
    expect(body!.draft_overlay.content).toBe('点了开关之后又改的内容')
    expect(body!.draft_overlay.content_length).toBe('点了开关之后又改的内容'.length)
  })
})

describe('本轮草稿纳入结果标在消息上（需求 2.5 / design §5.5）', () => {
  /** 让 `subscribe()` 期间派发 context_ready → delta → done（真实 SSE 顺序）。 */
  function streamRun(manifest: Record<string, unknown>) {
    runStore.subscribe.mockImplementation(async () => {
      runStoreState.emit('context_ready', { manifest })
      runStoreState.emit('delta', { text: '这是 AI 的回答。' })
      runStoreState.emit('done')
    })
  }

  it('denied → 消息下方显示后端的中文原因，不弹窗、不阻断', async () => {
    installFetchSpy()
    registerAccessor({ dirty: ref(true), content: ref('未保存的一格') })
    const reason = '草稿基于旧版本 v2026-11-15T10:00:00+00:00，当前 v2026-11-15T12:00:00+00:00，请先保存或刷新'
    streamRun({
      manifest_version: 'context-plan-v1',
      draft_overlay_included: false,
      denied: [
        {
          source_type: 'draft_overlay:workpaper',
          source_id: WP_ID,
          status: 'denied',
          label: '当前未保存草稿（底稿 B1-1 货币资金）',
          reason,
          content_hash: 'sha256:abc123',
          baseline_version: BASELINE,
        },
      ],
    })
    const wrapper = await mountPanel()

    await draftSwitch(wrapper).trigger('click')
    await nextTick()
    await typeDraft(wrapper, '看看这一格')
    await clickSend(wrapper)
    await flushPromises()

    const notice = wrapper.find('.platform-ai-chat-panel__draft-notice')
    expect(notice.exists(), 'denied 时消息下方必须有一行说明').toBe(true)
    expect(notice.classes()).toContain('is-denied')
    expect(notice.text()).toContain('当前未保存草稿未纳入')
    expect(notice.text()).toContain('请先保存或刷新')
    expect(notice.text()).toMatch(CJK_RE)
    // 回答本身照常显示（不阻断）
    expect(wrapper.text()).toContain('这是 AI 的回答。')
    expectNoModalOrToast()
  })

  it('included → 消息被标注为"本轮纳入了未保存草稿"（与已保存内容区分）', async () => {
    installFetchSpy()
    registerAccessor({ dirty: ref(true), content: ref('未保存的一格') })
    streamRun({
      manifest_version: 'context-plan-v1',
      draft_overlay_included: true,
      included: [
        {
          source_type: 'draft_overlay:workpaper',
          source_id: WP_ID,
          status: 'included',
          label: '当前未保存草稿（底稿 B1-1 货币资金）',
          used_tokens: 128,
          content_hash: 'sha256:abc123',
          baseline_version: BASELINE,
        },
      ],
    })
    const wrapper = await mountPanel()

    await draftSwitch(wrapper).trigger('click')
    await nextTick()
    await typeDraft(wrapper, '看看我改的这一格')
    await clickSend(wrapper)
    await flushPromises()

    const notice = wrapper.find('.platform-ai-chat-panel__draft-notice')
    expect(notice.exists()).toBe(true)
    expect(notice.classes()).toContain('is-included')
    expect(notice.text()).toContain('已纳入当前未保存草稿')
    expect(notice.text()).toContain('2026-11-15 10:00:00 UTC')
    expectNoModalOrToast()
  })

  it('本轮没提交草稿（manifest 无 overlay 条目）→ 消息上不加任何标注', async () => {
    installFetchSpy()
    streamRun({
      manifest_version: 'context-plan-v1',
      included: [
        { source_type: 'workpaper', source_id: WP_ID, status: 'included', label: '审定表' },
      ],
    })
    const wrapper = await mountPanel()

    await typeDraft(wrapper, '普通提问')
    await clickSend(wrapper)
    await flushPromises()

    expect(wrapper.find('.platform-ai-chat-panel__draft-notice').exists()).toBe(false)
    expect(wrapper.text()).toContain('这是 AI 的回答。')
  })
})
