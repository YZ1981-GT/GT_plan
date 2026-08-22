/**
 * Phase B Gate Guards — Task 24 综合前端行为守卫
 *
 * 本文件是 Phase B 的**门**：只断言跨组件的门控不变量，全部落到真实调用 /
 * 真实 mount / 真实 DOM。不做 `toBeDefined()` 式 import 检查 —— "文件能 import"
 * 不是任何 Property 的证据。
 *
 * 覆盖：
 * - (Property 23) 复核模式宿主门控：workpaper 可启用并真的取模板；非 workpaper
 *   禁用且给出**逐类型可区分**的中文原因；宿主切走后自动关闭。
 * - (Property 21) 笔记幂等：失败后重试复用同一 idempotency_key；新的选择意图
 *   换新 key；名称必须经确认对话框。
 * - (Property 12) Context Manifest 真被消费：四态各自渲染 + 中文摘要计数。
 * - (Property 34) 不可信 HTML 走真实 sanitizer：净化后无 script/on*，安全正文保留。
 *
 * 单组件细节行为不在此重复，见：
 * - mention 搜索 error/empty/unavailable DOM → `ChatMentionPicker.spec.ts`
 * - 附件上传与 OCR 五态 / 清理重试 → `ChatAttachmentPicker.spec.ts`
 * - manifest 展示细节（version/stale/jump/预算条）→ `ChatContextInspector.spec.ts`
 * - 五类来源 XSS 攻击向量矩阵 → `PlatformAiChatXss.spec.ts`
 *
 * Feature: dsh-agent-panel-integration / Task 24
 * Validates: Requirements 14.2, 14.4
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { marked } from 'marked'
import { sanitizeHtml } from '@/composables/useSanitize'
import type { AiHostRequest, AiHostType } from '@/composables/useAiHostContext'
import type { ContextManifestItem } from '@/components/ai/ChatContextInspector.vue'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 'test-token' }),
}))

const mockPrompt = vi.fn()
const mockMessageSuccess = vi.fn()
const mockMessageError = vi.fn()
vi.mock('element-plus', () => ({
  ElMessageBox: {
    prompt: (...args: unknown[]) => mockPrompt(...args),
  },
  ElMessage: {
    success: (...args: unknown[]) => mockMessageSuccess(...args),
    error: (...args: unknown[]) => mockMessageError(...args),
    warning: vi.fn(),
    info: vi.fn(),
  },
}))

const mockFetch = vi.fn()

const mockRouterPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockRouterPush }),
  useRoute: () => ({ params: {} }),
}))

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Element Plus 未全局注册；用可观测的原生元素替身暴露 disabled / change 绑定。 */
const EL_STUBS = {
  'el-switch': {
    name: 'ElSwitchStub',
    props: ['modelValue', 'disabled', 'activeText', 'size'],
    emits: ['update:modelValue', 'change'],
    template:
      '<button class="stub-switch" type="button" :disabled="disabled"' +
      ' @click="$emit(\'change\', !modelValue)">{{ activeText }}</button>',
  },
  'el-icon': { template: '<i class="stub-icon"><slot /></i>' },
  'el-tag': { template: '<span class="stub-tag"><slot /></span>' },
  'el-button': {
    template: '<button class="stub-button" type="button" @click="$emit(\'click\')"><slot /></button>',
  },
}

function mountOptions() {
  return { global: { plugins: [createPinia()], stubs: EL_STUBS } }
}

function makeHostRequest(
  type: AiHostType,
  overrides: Partial<AiHostRequest> = {},
): AiHostRequest {
  return {
    host: {
      type,
      id: type === 'global_knowledge' ? 'global-knowledge' : `${type}-id-1`,
      projectId: '11111111-1111-4111-8111-111111111111',
      year: 2025,
    },
    available: true,
    unavailableReason: null,
    projectToolsEnabled: true,
    label: type,
    ...overrides,
  }
}

function reviewPreviewResponse() {
  return {
    ok: true,
    status: 200,
    json: async () => ({
      data: {
        enabled: true,
        source_level: 'sheet',
        tips: ['关注账龄划分'],
        checklist: ['复核坏账计提比例'],
        risk_areas: [{ level: 'high', text: '关联方往来' }],
        version: '3',
        wp_code: 'D2-1',
        sheet_name: 'Sheet1',
      },
    }),
  }
}

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

function makeManifest(): ContextManifestItem[] {
  return [
    {
      source_type: 'workpaper',
      source_id: 'wp1',
      label: '审定表 D2-1',
      decision: 'included',
      reason_code: null,
      token_estimate: 500,
      version: '3',
      is_stale: false,
      jump_route: '/workpaper/wp1',
    },
    {
      source_type: 'note',
      source_id: 'n1',
      label: '应收账款附注',
      decision: 'trimmed',
      reason_code: 'budget_exceeded',
      token_estimate: 300,
      version: '2',
      is_stale: false,
      jump_route: null,
    },
    {
      source_type: 'knowledge_doc',
      source_id: 'kd1',
      label: '审计准则汇编',
      decision: 'denied',
      reason_code: 'access_denied',
      token_estimate: 0,
      version: null,
      is_stale: false,
      jump_route: null,
    },
    {
      source_type: 'address',
      source_id: 'addr1',
      label: '应收账款/坏账准备',
      decision: 'unavailable',
      reason_code: 'embedding_unavailable',
      token_estimate: 0,
      version: '1',
      is_stale: true,
      jump_route: null,
    },
  ]
}

function requestBodies(): any[] {
  return mockFetch.mock.calls.map(([, init]) => JSON.parse((init as any).body))
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('Phase B Gate Guards', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockFetch.mockReset()
    mockRouterPush.mockReset()
    mockPrompt.mockReset()
    mockMessageSuccess.mockReset()
    mockMessageError.mockReset()
    vi.stubGlobal('fetch', mockFetch)
  })

  // =========================================================================
  // Property 23 — 复核模式宿主门控（真 mount + 真 DOM）
  // =========================================================================

  describe('Property 23: 复核模式只在 workpaper 宿主可用', () => {
    it('knowledge_doc 宿主：开关 disabled 且 DOM 给出中文原因', async () => {
      /**
       * MUTATION ANCHOR FE-P23-A: canEnable 去掉 host.type === 'workpaper' 判定
       * （任何宿主都能启用复核）→ 打红。
       *
       * Validates: Requirements 9.1
       */
      const ChatReviewModeBar = (
        await import('@/components/ai/ChatReviewModeBar.vue')
      ).default

      const wrapper = mount(ChatReviewModeBar, {
        props: { host: makeHostRequest('knowledge_doc') },
        ...mountOptions(),
      })

      const toggle = wrapper.find('.stub-switch')
      expect(toggle.exists()).toBe(true)
      expect(toggle.attributes('disabled')).toBeDefined()
      expect(wrapper.classes()).toContain('chat-review-mode-bar--disabled')

      const reason = wrapper.find('.chat-review-mode-bar__reason')
      expect(reason.exists()).toBe(true)
      expect(reason.text()).toContain('底稿')
      expect(reason.text()).toContain('知识库')
      // 全中文（NFR-5）：原因里不出现裸英文宿主类型
      expect(reason.text()).not.toMatch(/knowledge_doc|workpaper/)
    })

    it('workpaper 宿主：开关可用，切换后真的去取复核模板', async () => {
      /**
       * MUTATION ANCHOR FE-P23-B: 切换不触发 fetchPreview（复核模板成为死代码）
       * 或不 emit update:reviewMode → 打红。
       *
       * Validates: Requirements 9.1, 9.4
       */
      const ChatReviewModeBar = (
        await import('@/components/ai/ChatReviewModeBar.vue')
      ).default
      mockFetch.mockResolvedValue(reviewPreviewResponse())

      const wrapper = mount(ChatReviewModeBar, {
        props: { host: makeHostRequest('workpaper'), sheetName: 'Sheet1' },
        ...mountOptions(),
      })

      const toggle = wrapper.find('.stub-switch')
      expect(toggle.attributes('disabled')).toBeUndefined()
      expect(wrapper.find('.chat-review-mode-bar__reason').exists()).toBe(false)

      await toggle.trigger('click')
      await flushPromises()

      expect(wrapper.emitted('update:reviewMode')).toEqual([[true]])
      expect(mockFetch).toHaveBeenCalledTimes(1)
      const url = String(mockFetch.mock.calls[0][0])
      expect(url).toContain('/api/ai-chat/review-prompt')
      expect(url).toContain('host_type=workpaper')
      expect(url).toContain('sheet_name=Sheet1')

      // 取回的模板真的渲染出来（不是取了不用的死数据）
      expect(wrapper.text()).toContain('Sheet 级')
      expect(wrapper.text()).toContain('关注账龄划分')
    })

    it('宿主从 workpaper 切到非 workpaper：复核模式自动关闭', async () => {
      /**
       * MUTATION ANCHOR FE-P23-C: 删除 canEnable 的自动关闭 watcher
       * （切页后复核模式残留在非底稿宿主上）→ 打红。
       *
       * Validates: Requirements 9.1
       */
      const ChatReviewModeBar = (
        await import('@/components/ai/ChatReviewModeBar.vue')
      ).default
      mockFetch.mockResolvedValue(reviewPreviewResponse())

      const wrapper = mount(ChatReviewModeBar, {
        props: { host: makeHostRequest('workpaper') },
        ...mountOptions(),
      })
      await wrapper.find('.stub-switch').trigger('click')
      await flushPromises()
      expect(wrapper.emitted('update:reviewMode')).toEqual([[true]])

      await wrapper.setProps({ host: makeHostRequest('report') })
      await flushPromises()

      expect(wrapper.emitted('update:reviewMode')).toEqual([[true], [false]])
      expect(wrapper.find('.stub-switch').attributes('disabled')).toBeDefined()
      expect(wrapper.text()).toContain('报表')
    })

    it('每种非 workpaper 宿主给出各自可区分的中文原因', async () => {
      /**
       * MUTATION ANCHOR FE-P23-D: disabledReason 的 switch 塌缩为单一兜底文案
       * （用户分不清为什么不能用）→ 打红。
       *
       * Validates: Requirements 9.1（Property 24 中文原因）
       */
      const ChatReviewModeBar = (
        await import('@/components/ai/ChatReviewModeBar.vue')
      ).default

      const expectations: Array<[AiHostType, string]> = [
        ['note', '附注'],
        ['report', '报表'],
        ['knowledge_doc', '知识库'],
        ['knowledge_folder', '知识库'],
        ['global_knowledge', '全局知识'],
      ]
      const seen = new Set<string>()

      for (const [type, keyword] of expectations) {
        const wrapper = mount(ChatReviewModeBar, {
          props: { host: makeHostRequest(type) },
          ...mountOptions(),
        })
        const text = wrapper.find('.chat-review-mode-bar__reason').text()
        expect(text, `${type} 缺少中文原因`).toContain(keyword)
        expect(text, `${type} 原因非中文`).toMatch(/[\u4e00-\u9fa5]/)
        seen.add(text)
      }

      // 至少 4 种不同文案（knowledge_doc / knowledge_folder 共用一条）
      expect(seen.size).toBeGreaterThanOrEqual(4)

      // 宿主本身不可用时给出的是宿主原因，而不是"仅在底稿页面可用"
      const unavailable = mount(ChatReviewModeBar, {
        props: {
          host: makeHostRequest('workpaper', {
            available: false,
            unavailableReason: '未解析到项目上下文',
          }),
        },
        ...mountOptions(),
      })
      expect(unavailable.find('.chat-review-mode-bar__reason').text()).toBe(
        '未解析到项目上下文',
      )
    })
  })

  // =========================================================================
  // Property 21 — 笔记幂等（真调 composable + 真检查请求体）
  // =========================================================================

  describe('Property 21: 笔记转存幂等键', () => {
    it('失败后重试复用同一 idempotency_key；新的选择意图换新 key', async () => {
      /**
       * MUTATION ANCHOR FE-P21-A: 每次 saveAsNote 都新生成 key（重试产生双文档）
       * 或干脆不发 idempotency_key → 打红。
       * MUTATION ANCHOR FE-P21-B: 选择变化后不重置 key（不同意图复用同一 key，
       * 第二篇笔记被幂等吞掉）→ 打红。
       *
       * Validates: Requirements 8.2
       */
      const { useAiNoteCapture } = await import('@/composables/useAiNoteCapture')

      const messages = [
        {
          id: '22222222-2222-4222-8222-222222222222',
          role: 'assistant',
          status: 'completed',
          text: '第一条结论',
        },
        {
          id: '33333333-3333-4333-8333-333333333333',
          role: 'assistant',
          status: 'completed',
          text: '第二条结论',
        },
      ] as any[]
      const host = {
        type: 'workpaper',
        id: 'wp-1',
        projectId: '11111111-1111-4111-8111-111111111111',
        year: 2025,
      }

      mockPrompt.mockResolvedValue({ value: '应收账款问答记录' })

      const capture = useAiNoteCapture({
        messages: () => messages,
        host: () => host as any,
      })

      const failure = () => ({
        ok: false,
        status: 500,
        json: async () => ({ detail: { code: 'internal_error', message: '服务异常' } }),
      })

      capture.toggleMessage(messages[0].id)
      expect(capture.selectedCount.value).toBe(1)

      // ① 第一次保存失败 → key 必须保留（成功会清空选择，那时无法再观察复用）
      mockFetch.mockResolvedValueOnce(failure())
      expect((await capture.saveAsNote()).success).toBe(false)

      // 名称必须经确认对话框（Req 8.2：不静默生成时间戳名）
      expect(mockPrompt).toHaveBeenCalledTimes(1)

      // ② 选择集变了 = 新的保存意图 → 必须换新 key（此时旧 key 仍存活）
      capture.toggleMessage(messages[1].id)
      expect(capture.selectedCount.value).toBe(2)
      mockFetch.mockResolvedValueOnce(failure())
      expect((await capture.saveAsNote()).success).toBe(false)

      // ③ 选择没变的重试 → 复用同一 key
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ data: { jump_route: '/knowledge/doc/1' } }),
      })
      expect((await capture.retrySaveAsNote()).success).toBe(true)

      const bodies = requestBodies()
      expect(bodies).toHaveLength(3)
      for (const body of bodies) {
        expect(body.idempotency_key, '未提交 idempotency_key').toMatch(UUID_RE)
      }
      expect(bodies[1].idempotency_key, '选择集变化后仍复用旧 key').not.toBe(
        bodies[0].idempotency_key,
      )
      expect(bodies[2].idempotency_key, '重试未复用同一 key').toBe(
        bodies[1].idempotency_key,
      )
      expect(bodies[0].message_ids).toEqual([messages[0].id])
      expect(bodies[2].message_ids).toEqual([messages[0].id, messages[1].id])
      expect(bodies[0].name).toBe('应收账款问答记录')
    })
  })

  // =========================================================================
  // Property 34 — 真实 sanitizer（不是断言输入字面量）
  // =========================================================================

  describe('Property 34: 不可信 HTML 走真实 sanitizer', () => {
    it('事件属性挂在**允许标签**上时仍被剥离，安全正文与 href 保留', () => {
      /**
       * MUTATION ANCHOR FE-P34-A: useSanitize 的 ALLOWED_ATTR 放宽任一 on*
       * （onclick / onmouseover / onerror / onfocus）→ 打红。
       *
       * 载体标签刻意选 ALLOWED_TAGS 里的 a/p/strong/blockquote —— 用 img/script
       * 这类本就被整体删除的标签当载体，测到的只是"标签白名单"，放宽
       * ALLOWED_ATTR 打不红（本条最初就是这么写的，变异检验时才暴露）。
       *
       * Validates: Requirements 13.2
       */
      const payloads: Array<[string, string]> = [
        ['a/onclick', '<a href="https://example.com/doc" onclick="alert(1)">底稿链接</a>'],
        ['p/onmouseover', '<p onmouseover="alert(1)">段落正文</p>'],
        ['strong/onerror', '<strong onerror="alert(1)">金额 1,000.00 元</strong>'],
        ['blockquote/onfocus', '<blockquote onfocus="alert(1)">引用正文</blockquote>'],
      ]

      for (const [name, raw] of payloads) {
        const cleaned = sanitizeHtml(raw)
        expect(cleaned, `${name} 残留 on* 属性`).not.toMatch(/\bon\w+\s*=/i)

        const holder = document.createElement('div')
        holder.innerHTML = cleaned
        for (const el of Array.from(holder.querySelectorAll('*'))) {
          const handlers = el.getAttributeNames().filter((a) => a.startsWith('on'))
          expect(handlers, `${name} DOM 残留 ${handlers.join(',')}`).toEqual([])
        }
      }

      // 净化不等于清空：允许标签、正文与安全 href 都保留
      const link = sanitizeHtml(payloads[0][1])
      expect(link).toContain('<a')
      expect(link).toContain('href="https://example.com/doc"')
      expect(link).toContain('底稿链接')

      // 不在白名单的载体标签整体删除，其后的正文仍保留
      const dropped = sanitizeHtml('<img src=x onerror="alert(1)">识别金额 1,000.00 元')
      expect(dropped).not.toContain('<img')
      expect(dropped).not.toMatch(/onerror/i)
      expect(dropped).toContain('识别金额 1,000.00 元')
    })

    it('mention label 与 OCR 文本走 marked → sanitizeHtml 同一管道后无 script', () => {
      /**
       * MUTATION ANCHOR FE-P34-B: 任一来源绕过 sanitizeHtml 直接 v-html → 打红。
       *
       * Validates: Requirements 13.1, 13.2
       */
      const sources = {
        'mention label': '**底稿-A1** <script>alert("xss")</script>',
        'OCR 文本': '<iframe src="evil.com"></iframe>识别结果：<svg onload="alert(1)"></svg>',
        'manifest 文案': '已纳入：<a href="javascript:void(0)">知识文档</a>（裁剪）',
      }

      for (const [name, raw] of Object.entries(sources)) {
        const rendered = sanitizeHtml(marked.parse(raw, { async: false }) as string)
        expect(rendered, name).not.toContain('<script')
        expect(rendered, name).not.toContain('<iframe')
        expect(rendered, name).not.toMatch(/\bon\w+\s*=/i)
        expect(rendered, name).not.toMatch(/javascript:/i)
      }

      // 净化不等于清空：Markdown 加粗仍渲染
      const kept = sanitizeHtml(
        marked.parse(sources['mention label'], { async: false }) as string,
      )
      expect(kept).toContain('<strong>底稿-A1</strong>')
    })
  })

  // =========================================================================
  // Property 12 — Context Manifest 真被消费
  // =========================================================================

  describe('Property 12: Context Manifest 四态真渲染', () => {
    it('included/trimmed/denied/unavailable 各自渲染并计入中文摘要', async () => {
      /**
       * MUTATION ANCHOR FE-P12-A: manifest 只渲染 included（trimmed/denied 静默
       * 丢弃，用户以为"没有任何裁剪"）→ 打红。
       *
       * Validates: Requirements 5.7
       */
      const ChatContextInspector = (
        await import('@/components/ai/ChatContextInspector.vue')
      ).default

      const wrapper = mount(ChatContextInspector, {
        props: { manifest: makeManifest(), tokenBudget: 2000 },
        ...mountOptions(),
      })

      // 折叠态摘要即已按四态计数（用户不展开也看得到有东西被拒/被裁）
      const summary = wrapper.find('.chat-context-inspector__summary').text()
      expect(summary).toContain('1 项纳入')
      expect(summary).toContain('1 项裁剪')
      expect(summary).toContain('1 项拒绝')
      expect(summary).toContain('1 项不可用')

      await wrapper.find('.chat-context-inspector__toggle').trigger('click')

      const items = wrapper.findAll('.chat-context-inspector__item')
      expect(items).toHaveLength(4)
      expect(items[0].classes()).toContain('is-included')
      expect(items[1].classes()).toContain('is-trimmed')
      expect(items[2].classes()).toContain('is-denied')
      expect(items[3].classes()).toContain('is-unavailable')

      // 非 included 项必须有中文原因，否则用户只看到一个图标
      expect(items[1].find('.chat-context-inspector__item-reason').text()).toBe(
        'Token 预算不足',
      )
      expect(items[2].find('.chat-context-inspector__item-reason').text()).toBe(
        '无访问权限',
      )
      expect(items[3].find('.chat-context-inspector__item-reason').text()).toBe(
        '语义服务不可用',
      )

      // 每条 label 都渲染（manifest 不是取了不用的死数据）
      const text = wrapper.text()
      for (const item of makeManifest()) {
        expect(text).toContain(item.label)
      }
    })
  })
})
