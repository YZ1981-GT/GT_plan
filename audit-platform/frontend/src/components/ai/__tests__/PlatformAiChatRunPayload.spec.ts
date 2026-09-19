/**
 * 接线闭环守卫 —— 已选 mention 必须真的进入 `POST /api/ai-chat/runs` 载荷
 *
 * ## 为什么单独一条
 *
 * 「组件被挂载了」只解决一半。另一半是**提交**：把 picker 渲染出来、tag 也显示了，
 * 但请求体里没有 `mentions`，用户选的引用照样等于空气 —— 这是死代码的变体
 * 「被消费了但没人检查消费到了什么」。
 *
 * 实测（2026-08-16）：`sendMessageNewApi` 的 body 只有
 * `{host, query, idempotency_key}`，而后端 `ChatRunRequest` 早已声明
 * `mentions` / `attachment_ids` / `review_mode` / `sheet_name` 四个字段。
 * 面板把 `pendingAttachmentIds` / `reviewModeEnabled` 收集得整整齐齐，然后丢在本地。
 *
 * ## 判据形态
 *
 * 真实 mount 面板 → 真实在输入框打 `@` → 真实从 picker 触发 change →
 * 真实点发送 → **读被拦截的 fetch 请求体**。不查源码字符串、不查「函数被调用过」。
 *
 * Feature: dsh-agent-panel-integration / Task 15 接线补口
 * Validates: Requirements 5.1, 5.5
 * Properties: 12, 13
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import type { AiHostRequest } from '@/composables/useAiHostContext'
import type { MentionItem } from '@/composables/useAiMention'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 'test-token' }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
  ElMessageBox: { prompt: vi.fn() },
}))

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
  useRoute: () => ({ params: {}, query: {} }),
}))

/** run 状态 store 替身：不真起 SSE（本条只关心 POST /runs 的请求体）。 */
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
    startRun: vi.fn(),
    subscribe: vi.fn().mockResolvedValue(undefined),
    cancel: vi.fn(),
    reset: vi.fn(),
    on: vi.fn().mockReturnValue(() => {}),
    setQuota: vi.fn(),
  }),
}))

// ---------------------------------------------------------------------------
// Element Plus 替身（未全局注册；用原生元素暴露 v-model / click / close）
// ---------------------------------------------------------------------------

const EL_STUBS = {
  'el-input': {
    name: 'ElInputStub',
    props: ['modelValue', 'disabled', 'placeholder', 'rows', 'type'],
    template:
      '<textarea class="stub-input" :disabled="disabled" :value="modelValue"'
      + ' @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
  'el-button': {
    name: 'ElButtonStub',
    props: ['disabled', 'loading', 'type', 'size', 'plain', 'text', 'icon'],
    template:
      '<button class="stub-button" type="button" :disabled="disabled"'
      + ' @click="$emit(\'click\')"><slot /></button>',
  },
  'el-tag': {
    name: 'ElTagStub',
    // closable 必须声明成 Boolean：模板里写的是无值简写 `closable`，
    // 用数组式 props 会拿到 `""`（falsy），移除按钮就永远不渲染。
    props: {
      type: { type: String, default: '' },
      size: { type: String, default: '' },
      effect: { type: String, default: '' },
      closable: { type: Boolean, default: false },
    },
    template:
      '<span class="stub-tag"><slot />'
      + '<button v-if="closable" class="stub-tag-close" type="button"'
      + ' @click="$emit(\'close\')">x</button></span>',
  },
  'el-icon': { template: '<i class="stub-icon"><slot /></i>' },
  'el-empty': { props: ['description'], template: '<div class="stub-empty">{{ description }}</div>' },
  'el-upload': { template: '<div class="stub-upload"><slot /></div>' },
  'el-progress': { template: '<div class="stub-progress" />' },
  'el-switch': {
    props: ['modelValue', 'disabled', 'activeText', 'size'],
    template: '<button class="stub-switch" type="button" :disabled="disabled" />',
  },
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeHost(): AiHostRequest {
  return {
    host: {
      type: 'workpaper',
      id: '11111111-1111-1111-1111-111111111111',
      projectId: '22222222-2222-2222-2222-222222222222',
      year: 2025,
    },
    available: true,
    unavailableReason: null,
    projectToolsEnabled: true,
    label: '底稿',
  }
}

function makeMention(overrides: Partial<MentionItem> = {}): MentionItem {
  return {
    type: 'workpaper',
    id: 'wp-0001',
    label: '应收账款审定表 D2-1',
    sublabel: '2025 年度',
    jump_route: '/workpaper/wp-0001',
    ...overrides,
  }
}

/** 拦截 fetch，返回可用的 run 创建响应，并记录全部调用。 */
function installFetchSpy() {
  const calls: Array<{ url: string; init: RequestInit | undefined }> = []
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
function readRunRequestBody(
  calls: Array<{ url: string; init: RequestInit | undefined }>,
): Record<string, any> | null {
  const call = calls.find(
    (c) => c.url.includes('/api/ai-chat/runs') && (c.init?.method ?? '').toUpperCase() === 'POST',
  )
  if (!call || typeof call.init?.body !== 'string') return null
  return JSON.parse(call.init.body)
}

async function mountPanel(
  props: Record<string, unknown> = {},
  extra: Record<string, unknown> = {},
) {
  const { default: PlatformAiChatPanel } = await import('../PlatformAiChatPanel.vue')
  return mount(PlatformAiChatPanel, {
    props: { host: makeHost(), visible: false, ...props },
    global: { plugins: [createPinia()], stubs: EL_STUBS },
    ...extra,
  })
}

/**
 * 提问输入框。
 *
 * 🔴 不能用 `.platform-ai-chat-panel__input .stub-input` —— mention picker 的搜索框
 * 也在输入区容器内且**排在前面**，`find` 会命中它，于是 setValue 打进了搜索框、
 * `draft` 一直是空的（首轮实跑就踩到：picker 不弹、发送按钮 disabled、POST 从未发出）。
 * 用面板自己给 textarea 的 `aria-describedby` 唯一定位。
 */
function findComposerTextarea(wrapper: any) {
  const el = wrapper.find('textarea[aria-describedby="chat-input-status"]')
  expect(el.exists(), '找不到提问输入框（aria-describedby="chat-input-status"）').toBe(true)
  return el
}

async function typeDraft(wrapper: any, text: string) {
  const textarea = findComposerTextarea(wrapper)
  await textarea.setValue(text)
  await nextTick()
}

/**
 * picker 是否展开。
 *
 * 🔴 **不能用 `isVisible()`**：jsdom 的 `getComputedStyle` 按元素缓存且不随
 * inline style 变化失效（VTU 挂载的节点还是 detached），于是同一个元素上
 * `isVisible()` 永远返回**第一次调用时**的结论 —— 实测两个方向都会错：
 * 先在隐藏态调过一次，之后 v-show 打开仍报 false；先在展开态调过一次，
 * 之后 Escape 关闭仍报 true。首轮实跑这两条都被它坑到。
 * `v-show` 的效果就是 inline `display: none`，直接断言它，确定且无缓存。
 */
function pickerOpen(wrapper: any): boolean {
  const el = wrapper.find('.chat-mention-picker')
  if (!el.exists()) return false
  return !(el.attributes('style') ?? '').includes('display: none')
}

async function clickSend(wrapper: any) {
  const btn = wrapper.find('button[aria-label="发送问题"]')
  expect(btn.exists(), '找不到发送按钮（aria-label="发送问题"）').toBe(true)
  await btn.trigger('click')
  await flushPromises()
}

// ===========================================================================
// Tests
// ===========================================================================

describe('@ 触发链（Req 5.1）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    installFetchSpy()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('输入 @ 唤出 mention picker；清掉 @ 后自动关闭', async () => {
    const wrapper = await mountPanel()

    expect(wrapper.find('.chat-mention-picker').exists(), 'picker 未被面板挂载').toBe(true)
    expect(pickerOpen(wrapper)).toBe(false)

    await typeDraft(wrapper, '@')
    expect(pickerOpen(wrapper)).toBe(true)

    // `@` 后接空白 ⇒ 引用词写完了，picker 该收起
    await typeDraft(wrapper, '@ 请核对')
    expect(pickerOpen(wrapper)).toBe(false)
  })

  it('@ 词中间带关键词时保持打开（用户正在挑资源）', async () => {
    const wrapper = await mountPanel()
    await typeDraft(wrapper, '请核对 @应收账款')
    expect(pickerOpen(wrapper)).toBe(true)
  })

  it('Escape 关闭 picker 且不冒泡（否则 DshPanel 会把整个面板关掉）', async () => {
    const wrapper = await mountPanel()
    await typeDraft(wrapper, '@')
    expect(pickerOpen(wrapper)).toBe(true)

    let bubbled = false
    wrapper.element.addEventListener('keydown', () => { bubbled = true })

    await findComposerTextarea(wrapper).trigger('keydown', { key: 'Escape' })
    await nextTick()

    expect(pickerOpen(wrapper)).toBe(false)
    expect(bubbled, 'Escape 冒泡到了面板根 ⇒ DshPanel 会连带关闭整个面板').toBe(false)
  })

  it('点击输入区之外关闭 picker，点 picker 内部不关', async () => {
    // 必须 attachTo：mousedown 要真的冒泡到 document 上的监听器
    const wrapper = await mountPanel({}, { attachTo: document.body })
    try {
      await typeDraft(wrapper, '@')
      expect(pickerOpen(wrapper)).toBe(true)

      // 点 picker 内部：不关（否则用户一点候选项面板就消失）
      wrapper.find('.chat-mention-picker').element
        .dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      await nextTick()
      expect(pickerOpen(wrapper)).toBe(true)

      // 点输入区之外（消息列表区）：关
      wrapper.find('.platform-ai-chat-panel__messages').element
        .dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
      await nextTick()
      expect(pickerOpen(wrapper)).toBe(false)
    } finally {
      wrapper.unmount()
    }
  })

  it('宿主不可用时不弹 picker', async () => {
    const wrapper = await mountPanel({
      host: {
        host: null,
        available: false,
        unavailableReason: '当前页面未解析到项目',
        projectToolsEnabled: false,
        label: '底稿',
      } satisfies AiHostRequest,
    })
    await typeDraft(wrapper, '@')
    expect(pickerOpen(wrapper)).toBe(false)
  })
})

describe('已选 mention 在输入区上方以可移除 tag 展示', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    installFetchSpy()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('picker 的 change 事件 → tag 出现，带类型中文标签', async () => {
    const wrapper = await mountPanel()
    const { default: ChatMentionPicker } = await import('../ChatMentionPicker.vue')

    wrapper.findComponent(ChatMentionPicker).vm.$emit('change', [makeMention()])
    await nextTick()

    const tags = wrapper.find('.platform-ai-chat-panel__mention-tags')
    expect(tags.exists()).toBe(true)
    expect(tags.text()).toContain('底稿')
    expect(tags.text()).toContain('应收账款审定表 D2-1')
  })

  it('点 tag 上的移除按钮 → 该引用消失', async () => {
    const wrapper = await mountPanel()
    const { default: ChatMentionPicker } = await import('../ChatMentionPicker.vue')

    wrapper.findComponent(ChatMentionPicker).vm.$emit('change', [
      makeMention(),
      makeMention({ id: 'note-1', type: 'note', label: '应收账款附注' }),
    ])
    await nextTick()
    expect(wrapper.findAll('.platform-ai-chat-panel__mention-tags .stub-tag').length).toBe(2)

    await wrapper.findAll('.platform-ai-chat-panel__mention-tags .stub-tag-close')[0].trigger('click')
    await nextTick()

    const remaining = wrapper.find('.platform-ai-chat-panel__mention-tags')
    expect(remaining.findAll('.stub-tag').length).toBe(1)
    expect(remaining.text()).toContain('应收账款附注')
    expect(remaining.text()).not.toContain('应收账款审定表 D2-1')
  })
})

describe('Req 5.5 / Property 12：mention 真的进入 POST /runs 请求体', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('已选引用出现在 mentions 里，且只含 type + 稳定 ID', async () => {
    const calls = installFetchSpy()
    const wrapper = await mountPanel()
    const { default: ChatMentionPicker } = await import('../ChatMentionPicker.vue')

    wrapper.findComponent(ChatMentionPicker).vm.$emit('change', [
      makeMention(),
      makeMention({ id: 'addr-9', type: 'address', label: '应收账款/坏账准备' }),
    ])
    await nextTick()

    await typeDraft(wrapper, '请核对这两处')
    await clickSend(wrapper)

    const body = readRunRequestBody(calls)
    expect(body, '没有发出 POST /api/ai-chat/runs').not.toBeNull()

    expect(body!.mentions).toEqual([
      { type: 'workpaper', id: 'wp-0001' },
      { type: 'address', id: 'addr-9' },
    ])

    // Req 5.5：客户端不得提交 label / sublabel / jump_route
    // （后端 MentionRef 是 extra="forbid"，多一个键整条请求会被拒）
    for (const m of body!.mentions) {
      expect(Object.keys(m).sort()).toEqual(['id', 'type'])
    }
  })

  it('未选引用时不提交 mentions 键（"没提交"与"提交空列表"是两种语义）', async () => {
    const calls = installFetchSpy()
    const wrapper = await mountPanel()

    await typeDraft(wrapper, '不带引用的普通提问')
    await clickSend(wrapper)

    const body = readRunRequestBody(calls)
    expect(body).not.toBeNull()
    expect('mentions' in body!).toBe(false)
    expect('attachment_ids' in body!).toBe(false)
    expect('review_mode' in body!).toBe(false)
  })

  it('附件 ID 也进请求体（同一处接线断裂：收集了从不提交）', async () => {
    const calls = installFetchSpy()
    const wrapper = await mountPanel()
    const { default: ChatAttachmentPicker } = await import('../ChatAttachmentPicker.vue')

    wrapper.findComponent(ChatAttachmentPicker).vm.$emit('change', ['att-1', 'att-2'])
    await nextTick()

    await typeDraft(wrapper, '看下这两个附件')
    await clickSend(wrapper)

    const body = readRunRequestBody(calls)
    expect(body!.attachment_ids).toEqual(['att-1', 'att-2'])
  })

  it('复核模式开启时提交 review_mode + sheet_name', async () => {
    const calls = installFetchSpy()
    const wrapper = await mountPanel({ sheetName: 'D2-1 审定表' })
    const { default: ChatReviewModeBar } = await import('../ChatReviewModeBar.vue')

    wrapper.findComponent(ChatReviewModeBar).vm.$emit('update:reviewMode', true)
    await nextTick()

    await typeDraft(wrapper, '请按复核要点检查')
    await clickSend(wrapper)

    const body = readRunRequestBody(calls)
    expect(body!.review_mode).toBe(true)
    expect(body!.sheet_name).toBe('D2-1 审定表')
  })

  it('发送后本轮引用清空，不会悄悄跟到下一轮', async () => {
    const calls = installFetchSpy()
    const wrapper = await mountPanel()
    const { default: ChatMentionPicker } = await import('../ChatMentionPicker.vue')

    wrapper.findComponent(ChatMentionPicker).vm.$emit('change', [makeMention()])
    await nextTick()
    await typeDraft(wrapper, '第一轮')
    await clickSend(wrapper)
    expect(readRunRequestBody(calls)!.mentions).toHaveLength(1)

    // tag 行应已消失
    expect(wrapper.find('.platform-ai-chat-panel__mention-tags').exists()).toBe(false)

    // 第二轮：不重新选就不该再带引用
    const calls2 = installFetchSpy()
    await typeDraft(wrapper, '第二轮')
    await clickSend(wrapper)
    const body2 = readRunRequestBody(calls2)
    expect(body2).not.toBeNull()
    expect('mentions' in body2!).toBe(false)
  })
})

describe('Property 12：Context Inspector 消费 context_ready 的 manifest', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    installFetchSpy()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('store 无 manifest 时不渲染检视器空壳', async () => {
    const wrapper = await mountPanel()
    expect(wrapper.find('.chat-context-inspector').exists()).toBe(false)
  })

  it('服务端分组 manifest 被投影后逐条渲染（included/trimmed/denied/unavailable）', async () => {
    // 真实服务端形状（context_budget.ContextManifest.as_dict）
    const serverManifest = {
      manifest_version: '1',
      total_budget: 8000,
      total_used: 900,
      included: [
        { source_type: 'workpaper', source_id: 'wp1', status: 'included', label: '审定表 D2-1', used_tokens: 600, version: '3' },
      ],
      trimmed: [
        { source_type: 'note', source_id: 'n1', status: 'trimmed', label: '应收账款附注', used_tokens: 300, reason: 'budget_exceeded' },
      ],
      denied: [
        { source_type: 'knowledge_doc', source_id: 'kd1', status: 'denied', label: '准则汇编', reason: 'access_denied' },
      ],
      unavailable: [
        { source_type: 'address', source_id: 'a1', status: 'unavailable', label: '坏账准备', reason: 'embedding_unavailable', stale: true },
      ],
    }

    // 直接验证投影 + 组件渲染的组合（面板里 store 是替身，这里锁投影这一段）
    const { normalizeContextManifest, readContextTokenBudget } = await import('@/utils/chatContextManifest')
    const items = normalizeContextManifest(serverManifest)
    expect(items.map((i) => i.decision).sort()).toEqual(['denied', 'included', 'trimmed', 'unavailable'])
    expect(readContextTokenBudget(serverManifest)).toBe(8000)

    const { default: ChatContextInspector } = await import('../ChatContextInspector.vue')
    const inspector = mount(ChatContextInspector, {
      props: { manifest: items, tokenBudget: readContextTokenBudget(serverManifest) },
      global: { plugins: [createPinia()], stubs: EL_STUBS },
    })
    await inspector.find('button').trigger('click')

    const rows = inspector.findAll('.chat-context-inspector__item')
    expect(rows.length).toBe(4)
    expect(rows[1].text()).toContain('Token 预算不足')
    expect(rows[2].text()).toContain('无访问权限')
    expect(rows[3].text()).toContain('已过期')
    expect(inspector.find('.chat-context-inspector__budget').text()).toContain('8000')
  })

  it('投影不吞条目：未登记的分组键也落进结果（decision 退化为 unavailable）', async () => {
    const { normalizeContextManifest } = await import('@/utils/chatContextManifest')
    const items = normalizeContextManifest({
      manifest_version: '1',
      future_group: [{ source_type: 'workpaper', source_id: 'x', label: '将来新增的决策' }],
    })
    expect(items).toHaveLength(1)
    expect(items[0].decision).toBe('unavailable')
    expect(items[0].reason_code).toBe('future_group')
  })

  it('投影不发明 jump_route（服务端没给就是 null，前端不许自己拼路由 — Req 5.9）', async () => {
    const { normalizeContextManifest } = await import('@/utils/chatContextManifest')
    const items = normalizeContextManifest({
      included: [{ source_type: 'workpaper', source_id: 'wp1', status: 'included', label: 'x' }],
    })
    expect(items[0].jump_route).toBeNull()
  })

  it('native engine 的 char_estimate 口径也能读出（两套 engine 形状不同）', async () => {
    const { normalizeContextManifest, readContextTokenBudget } = await import('@/utils/chatContextManifest')
    const items = normalizeContextManifest({
      manifest_version: 'native-included-only-v1',
      token_estimate: 1200,
      citation_count: 2,
      included: [
        { source_type: 'workpaper', source_id: 'wp1', label: 'D2-1', decision: 'included', char_estimate: 480 },
      ],
    })
    expect(items).toHaveLength(1)
    expect(items[0].token_estimate).toBe(480)
    // native 不下发 total_budget ⇒ 预算条不画（不拿别的字段冒充分母）
    expect(readContextTokenBudget({ manifest_version: 'native-included-only-v1', token_estimate: 1200 })).toBe(0)
  })
})
