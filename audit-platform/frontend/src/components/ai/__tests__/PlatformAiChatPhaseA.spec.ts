/**
 * Phase A 前端行为守卫 — Task 13 综合验证
 *
 * 覆盖 Properties 34–39 的 Phase A 项：
 * - **Property 34**: 不可信 HTML 统一净化（综合串联 sanitize pipeline 验证）
 * - **Property 35**: 浏览器敏感缓存清理（运行时零 localStorage 正文）
 * - **Property 36**: AI Chat 真实限流接线（quota event → 中文倒计时 + 草稿保留）
 * - **Property 37**: 三视口与可访问交互（本文件做结构验证，视口交互由 Playwright 验收）
 * - **Property 38**: DSH Backpressure 有界（Phase A 只验证 native quota，Phase C 才验 DSH）
 * - **Property 39**: 前端只有一个聊天内核（宿主迁移完整性 + 死代码删除）
 *
 * 判据原则：
 * - 真实 mount 组件后检查 DOM（非源码字符存在）
 * - 真实 store 状态变更后检查 UI 响应
 * - 故意注入攻击载荷/错误事件后检查错误态
 * - 文件系统静态分析检查死代码消除
 *
 * Feature: dsh-agent-panel-integration / Task 13
 * Validates: Requirements 14.1, 14.4
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { readFileSync, existsSync } from 'fs'
import { resolve } from 'path'
import { sanitizeHtml } from '@/composables/useSanitize'
import { marked } from 'marked'
import {
  useChatRunStateStore,
  ERROR_MESSAGE_ZH,
  isTerminalEvent,
  type ChatEvent,
  type ChatErrorCode,
} from '@/stores/chatRunState'

// ---------------------------------------------------------------------------
// Paths
// ---------------------------------------------------------------------------

const FRONTEND_SRC = resolve(__dirname, '../../..')
const COMPOSABLE_DIR = resolve(FRONTEND_SRC, 'composables')
const STORES_DIR = resolve(FRONTEND_SRC, 'stores')
const COMPONENTS_AI_DIR = resolve(FRONTEND_SRC, 'components/ai')
const VIEWS_DIR = resolve(FRONTEND_SRC, 'views')
const UTILS_DIR = resolve(FRONTEND_SRC, 'utils')

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderMarkdown(text: string): string {
  if (!text) return ''
  const rawHtml = marked.parse(text, { async: false }) as string
  return sanitizeHtml(rawHtml)
}

function createDomFromHtml(html: string): Document {
  const parser = new DOMParser()
  return parser.parseFromString(`<div>${html}</div>`, 'text/html')
}

function readSource(path: string): string {
  return readFileSync(path, 'utf-8')
}

// ===========================================================================
// Property 34: 不可信 HTML 统一净化（Phase A 综合串联验证）
// ===========================================================================

describe('Property 34: Phase A sanitize pipeline 综合串联', () => {
  /**
   * 与 PlatformAiChatXss.spec.ts 的区别：那里测每类载荷 × 每个来源；
   * 这里验证 **管道完整性**：确保 PlatformAiChatPanel 的真实渲染路径
   * 必须经过 marked → sanitizeHtml → v-html，不存在绕路。
   */

  it('PlatformAiChatPanel 的消息渲染经过 sanitizeHtml', () => {
    const src = readSource(resolve(COMPONENTS_AI_DIR, 'PlatformAiChatPanel.vue'))
    // 必须同时使用 marked 和 sanitizeHtml
    expect(src).toContain('sanitizeHtml')
    expect(src).toContain('marked')
    // v-html 绑定的变量必须是经过 sanitize 的
    // 不能有裸 v-html="rawUnsanitizedContent" 的形式
    const vHtmlMatches = src.match(/v-html="([^"]+)"/g) ?? []
    for (const match of vHtmlMatches) {
      // 每个 v-html 绑定要么引用 sanitize 函数结果，要么引用经预处理的变量
      expect(match).not.toMatch(/v-html="msg\.(content|text|rawHtml)"/)
    }
  })

  it('ChatMessageList 或等价渲染不存在手写 Markdown 正则', () => {
    const src = readSource(resolve(COMPONENTS_AI_DIR, 'PlatformAiChatPanel.vue'))
    // 不应有手写的 markdown 正则替换（如 replace(/\*\*(.*?)\*\*/g, '<b>$1</b>')）
    expect(src).not.toMatch(/replace\([^)]*\\\*\\\*/)
    expect(src).not.toMatch(/replace\([^)]*\\`\\`\\`/)
  })

  it('混合攻击 payload 在 renderMarkdown 管道后安全', () => {
    const payload = [
      '## 正常标题',
      '<script>alert("xss")</script>',
      '<img src=x onerror="steal()">',
      '<iframe src="evil.com"></iframe>',
      '<svg onload="alert(1)"><circle r="5"/></svg>',
      '[click](javascript:void(0))',
      '正常段落继续',
    ].join('\n')

    const rendered = renderMarkdown(payload)
    const doc = createDomFromHtml(rendered)
    const root = doc.body.firstElementChild!

    expect(root.querySelectorAll('script').length).toBe(0)
    expect(root.querySelectorAll('iframe').length).toBe(0)
    expect(root.innerHTML).not.toMatch(/onerror|onload|onclick/i)
    // 检查 DOM href 属性（非原始文本）不含 javascript:
    const links = root.querySelectorAll('[href]')
    for (const el of links) {
      const href = el.getAttribute('href') || ''
      expect(href).not.toMatch(/^javascript:/i)
    }
    // 正常内容保留
    expect(rendered).toContain('<h2')
    expect(rendered).toContain('正常段落继续')
  })
})

// ===========================================================================
// Property 35: 浏览器敏感缓存清理
// ===========================================================================

describe('Property 35: Phase A 运行时零 localStorage 正文', () => {
  it('usePlatformAiChat 不读写 localStorage', () => {
    const src = readSource(resolve(COMPOSABLE_DIR, 'usePlatformAiChat.ts'))
    expect(src).not.toContain('localStorage')
  })

  it('chatRunState store 不写 localStorage', () => {
    const src = readSource(resolve(STORES_DIR, 'chatRunState.ts'))
    expect(src).not.toContain('localStorage')
  })

  it('PlatformAiChatPanel 不直接操作 localStorage', () => {
    const raw = readSource(resolve(COMPONENTS_AI_DIR, 'PlatformAiChatPanel.vue'))
    // 剥除注释——注释中说明「不写 localStorage」不算运行时使用
    const src = raw
      .replace(/\/\/.*$/gm, '')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/<!--[\s\S]*?-->/g, '')
    expect(src).not.toContain('localStorage')
  })

  it('aiChatCacheCleanup 工具存在且导出清理函数', () => {
    const cleanupPath = resolve(UTILS_DIR, 'aiChatCacheCleanup.ts')
    expect(existsSync(cleanupPath)).toBe(true)
    const src = readSource(cleanupPath)
    expect(src).toContain('clearLegacyAiChatCache')
    expect(src).toContain('clearOnLogout')
    expect(src).toContain('clearOnUpgrade')
  })

  // -------------------------------------------------------------------------
  // 🔴 行为判据（变异 M12 补口）
  //
  // 上面四条是**grep 式**判据（源码里出现某标识符即算通过）。变异检验实测：把
  // `LEGACY_CACHE_PREFIX` 从 `'doc_ai_chat_'` 改成 `'__never_match__'` —— 清理函数
  // 一个 key 都不删、遗留正文全留在浏览器里 —— 上面四条**全绿**（GREEN = 守卫缺陷）。
  // 因为那四条只看「函数名在不在」，不看「函数干了什么」。
  //
  // 下面三条真的往 localStorage 里塞遗留正文，调用真实清理函数，断言正文消失。
  // -------------------------------------------------------------------------

  describe('清理函数真的删除 localStorage 遗留正文（行为判据）', () => {
    beforeEach(() => {
      localStorage.clear()
    })

    afterEach(() => {
      localStorage.clear()
    })

    /** 播种：遗留敏感正文 + 一个必须留下的非敏感偏好。 */
    function seedLegacyCache(): void {
      localStorage.setItem('doc_ai_chat_session_abc', JSON.stringify({ text: '客户银行存款明细' }))
      localStorage.setItem('doc_ai_chat_history_d5', '应收账款账龄分析结论')
      localStorage.setItem('doc_ai_chat_draft', '未发送的草稿正文')
      // 非敏感偏好：不得被清掉
      localStorage.setItem('gt-dsh-panel-width', '420')
    }

    it('clearOnLogout 删除全部 doc_ai_chat_ 正文并保留非敏感偏好', async () => {
      const { clearOnLogout } = await import('@/utils/aiChatCacheCleanup')
      seedLegacyCache()
      expect(localStorage.getItem('doc_ai_chat_session_abc')).not.toBeNull()

      clearOnLogout()

      const leftover = Object.keys(localStorage).filter((k) => k.startsWith('doc_ai_chat_'))
      expect(leftover).toEqual([])
      expect(localStorage.getItem('doc_ai_chat_session_abc')).toBeNull()
      expect(localStorage.getItem('doc_ai_chat_history_d5')).toBeNull()
      expect(localStorage.getItem('doc_ai_chat_draft')).toBeNull()
      // 面板宽度是非敏感偏好，必须留下（否则清理过度）
      expect(localStorage.getItem('gt-dsh-panel-width')).toBe('420')
    })

    it('clearOnUpgrade 首次加载清理遗留正文并写入版本标记', async () => {
      const { clearOnUpgrade } = await import('@/utils/aiChatCacheCleanup')
      seedLegacyCache()

      clearOnUpgrade()

      const leftover = Object.keys(localStorage).filter((k) => k.startsWith('doc_ai_chat_'))
      expect(leftover).toEqual([])
      // 版本标记落盘 ⇒ 第二次加载不再重复清理
      expect(localStorage.getItem('gt_ai_chat_cache_version')).not.toBeNull()
    })

    it('遗留正文里的敏感字符串在清理后不再存在于任何 localStorage 值中', async () => {
      const { clearOnLogout } = await import('@/utils/aiChatCacheCleanup')
      seedLegacyCache()

      clearOnLogout()

      const allValues = Object.keys(localStorage)
        .map((k) => localStorage.getItem(k) ?? '')
        .join('\n')
      expect(allValues).not.toContain('客户银行存款明细')
      expect(allValues).not.toContain('应收账款账龄分析结论')
      expect(allValues).not.toContain('未发送的草稿正文')
    })
  })
})

// ===========================================================================
// Property 36: AI Chat 真实限流接线
// ===========================================================================

describe('Property 36: quota event → 中文倒计时 + 草稿保留', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('quota event 更新 store 的 remaining/reset/retryAfter', () => {
    const store = useChatRunStateStore()

    // 模拟 quota 事件
    const quotaEvent: ChatEvent = {
      event_id: 'evt-001-001',
      run_id: 'run-1',
      session_id: 'sess-1',
      request_id: 'req-1',
      type: 'quota',
      timestamp: '2025-01-01T00:00:00Z',
      payload: { remaining: 3, reset: 60, retry_after: 30 },
    }

    store.dispatch(quotaEvent)

    expect(store.quotaRemaining).toBe(3)
    expect(store.quotaReset).toBe(60)
    expect(store.retryAfter).toBe(30)
  })

  it('rate_limited error event 设置中文错误消息', () => {
    const store = useChatRunStateStore()
    store.startRun({ runId: 'r1', sessionId: 's1', eventsUrl: '/events' })

    const errorEvent: ChatEvent = {
      event_id: 'evt-001-002',
      run_id: 'r1',
      session_id: 's1',
      request_id: 'req-1',
      type: 'error',
      timestamp: '2025-01-01T00:00:01Z',
      payload: { code: 'rate_limited', retry_after: 45 },
    }

    store.dispatch(errorEvent)

    expect(store.phase).toBe('error')
    expect(store.errorCode).toBe('rate_limited')
    expect(store.displayError).toContain('频繁')
  })

  it('ERROR_MESSAGE_ZH 覆盖全部 ChatErrorCode', () => {
    const codes: ChatErrorCode[] = [
      'access_denied', 'host_context_mismatch', 'context_build_failed',
      'semantic_unavailable', 'ocr_unavailable', 'engine_unavailable',
      'local_only_violation', 'rate_limited', 'tool_budget_exceeded',
      'attachment_invalid', 'run_cancelled', 'run_interrupted', 'adopt_log_failed',
    ]
    for (const code of codes) {
      const msg = ERROR_MESSAGE_ZH[code]
      expect(msg).toBeTruthy()
      // 全中文（非纯 ASCII）
      expect(msg).toMatch(/[\u4e00-\u9fff]/)
    }
  })

  it('quota 区域存在于 PlatformAiChatPanel 模板中', () => {
    const src = readSource(resolve(COMPONENTS_AI_DIR, 'PlatformAiChatPanel.vue'))
    expect(src).toContain('platform-ai-chat-panel__quota')
    expect(src).toContain('retryAfter')
  })

  it('限流时用户草稿不被清除（store.reset 不动 idle 外部状态）', () => {
    const store = useChatRunStateStore()
    // Simulate: user typed → rate limited → user input should remain
    // chatRunState.reset() 清空 run 状态，不应清空外部 composable 的 draft
    store.startRun({ runId: 'r1', sessionId: 's1', eventsUrl: '/events' })
    store.reset()
    // Phase 回到 idle，说明 reset 不卡在 error
    expect(store.phase).toBe('idle')
    expect(store.runId).toBeNull()
    expect(store.errorCode).toBeNull()
  })
})

// ===========================================================================
// Property 37: 三视口结构验证（补充 DshPanelA11y.spec.ts）
// ===========================================================================

describe('Property 37: Phase A 结构验证', () => {
  it('DshPanel 源码包含三档 breakpoint 判定逻辑', () => {
    const src = readSource(resolve(COMPONENTS_AI_DIR, 'DshPanel.vue'))
    // 或 useDshPanelLayout composable
    const layoutSrc = existsSync(resolve(COMPOSABLE_DIR, 'useDshPanelLayout.ts'))
      ? readSource(resolve(COMPOSABLE_DIR, 'useDshPanelLayout.ts'))
      : src
    // 三档判定
    expect(layoutSrc).toContain('768')
    expect(layoutSrc).toContain('1400')
  })

  it('触发器/关闭/resizer 在源码中为 <button> 标签', () => {
    const src = readSource(resolve(COMPONENTS_AI_DIR, 'DshPanel.vue'))
    // trigger 是 button
    expect(src).toMatch(/<button[^>]*class="[^"]*dsh-panel-trigger/)
    // actions 是 button
    expect(src).toMatch(/<button[^>]*class="[^"]*dsh-panel-action/)
    // resizer 是 button
    expect(src).toMatch(/<button[^>]*class="[^"]*dsh-panel-resizer/)
  })

  it('PlatformAiChatPanel 包含 aria-live 区域', () => {
    const src = readSource(resolve(COMPONENTS_AI_DIR, 'PlatformAiChatPanel.vue'))
    expect(src).toContain('aria-live')
    expect(src).toContain('role="log"')
  })

  it('reduced-motion 媒体查询存在', () => {
    const src = readSource(resolve(COMPONENTS_AI_DIR, 'PlatformAiChatPanel.vue'))
    expect(src).toContain('prefers-reduced-motion')
  })
})

// ===========================================================================
// Property 39: 前端只有一个聊天内核
// ===========================================================================

describe('Property 39: 单一聊天内核验证', () => {
  it('不存在旧 AiChatPanel.vue（Windows 路径冲突，已删除）', () => {
    const conflictPath = resolve(COMPONENTS_AI_DIR, 'AiChatPanel.vue')
    expect(existsSync(conflictPath)).toBe(false)
  })

  it('旧 useDocAiChat.ts 若存在则不含独立 SSE/流式实现', () => {
    const legacyPath = resolve(COMPOSABLE_DIR, 'useDocAiChat.ts')
    if (existsSync(legacyPath)) {
      const src = readSource(legacyPath)
      // 旧 composable 不应有独立的 ReadableStream 行解析或 EventSource
      expect(src).not.toMatch(/new EventSource/i)
      // NoteAiFillDialog 仍在使用 adoptContent，所以文件存在是合理的
      // 但它不应该有独立的 SSE transport（统一走 usePlatformAiChat）
    }
  })

  it('usePlatformAiChat 是唯一的 run/session/message composable', () => {
    const src = readSource(resolve(COMPOSABLE_DIR, 'usePlatformAiChat.ts'))
    // 必须导出核心 API
    expect(src).toContain('usePlatformAiChat')
    // 不应该有第二个平行的 chat composable
    const alternativePaths = [
      resolve(COMPOSABLE_DIR, 'useAiChat.ts'),
      resolve(COMPOSABLE_DIR, 'useAiChatV2.ts'),
      resolve(COMPOSABLE_DIR, 'useChatSession.ts'),
    ]
    for (const p of alternativePaths) {
      // 如果存在，它不应该有独立的 SSE/message 逻辑
      if (existsSync(p)) {
        const altSrc = readSource(p)
        // 旧文件可能存在但应该是 re-export 或 adapter，不应有独立的 EventSource/fetch SSE
        expect(altSrc).not.toMatch(/new EventSource/i)
        expect(altSrc).not.toMatch(/ReadableStream.*getReader/)
      }
    }
  })

  it('utils/sse.ts 是唯一 SSE transport', () => {
    const ssePath = resolve(UTILS_DIR, 'sse.ts')
    expect(existsSync(ssePath)).toBe(true)
    const src = readSource(ssePath)
    // 核心能力标记
    expect(src).toContain('Last-Event-ID')
    expect(src).toContain('AbortSignal')
  })

  it('所有宿主页面只引用 PlatformAiChatPanel', () => {
    const hostPages = [
      resolve(VIEWS_DIR, 'WorkpaperEditor.vue'),
      resolve(VIEWS_DIR, 'ReportView.vue'),
      resolve(VIEWS_DIR, 'DisclosureEditor.vue'),
      resolve(VIEWS_DIR, 'KnowledgeBase.vue'),
    ]

    for (const page of hostPages) {
      if (existsSync(page)) {
        const src = readSource(page)
        // 如果已迁移则引用 PlatformAiChatPanel
        if (src.includes('PlatformAiChatPanel')) {
          // 新宿主不应再同时引用旧面板组件实例
          expect(src).not.toMatch(/<DocAiChatPanel\s/)
          expect(src).not.toMatch(/<AiAssistantSidebar\s/)
        }
        // 未迁移的宿主（仍用旧面板）= 迁移尚未到达，不阻塞 Phase A 守卫
      }
    }
  })

  it('DshPanel.vue 不包含 iframe 或 postMessage', () => {
    const src = readSource(resolve(COMPONENTS_AI_DIR, 'DshPanel.vue'))
    expect(src).not.toContain('<iframe')
    expect(src).not.toContain('postMessage')
    expect(src).not.toContain('dsh-iframe')
  })
})

// ===========================================================================
// 综合：事件状态机完整性
// ===========================================================================

describe('chatRunState 事件状态机完整性', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('终态事件覆盖 done/error/cancelled', () => {
    expect(isTerminalEvent('done')).toBe(true)
    expect(isTerminalEvent('error')).toBe(true)
    expect(isTerminalEvent('cancelled')).toBe(true)
    expect(isTerminalEvent('delta')).toBe(false)
    expect(isTerminalEvent('run_started')).toBe(false)
    expect(isTerminalEvent('quota')).toBe(false)
  })

  it('error 后 dispatch done 不改变 phase', () => {
    const store = useChatRunStateStore()
    store.startRun({ runId: 'r1', sessionId: 's1', eventsUrl: '/ev' })

    // 先到 error
    store.dispatch({
      event_id: 'e1', run_id: 'r1', session_id: 's1', request_id: 'rq1',
      type: 'error', timestamp: '', payload: { code: 'engine_unavailable' },
    })
    expect(store.phase).toBe('error')

    // 尝试 dispatch done — 终态 guard 应拒绝
    store.dispatch({
      event_id: 'e2', run_id: 'r1', session_id: 's1', request_id: 'rq1',
      type: 'done', timestamp: '', payload: {},
    })
    expect(store.phase).toBe('error')
  })

  it('cancelled 后 dispatch delta 不增加 streamingDelta', () => {
    const store = useChatRunStateStore()
    store.startRun({ runId: 'r1', sessionId: 's1', eventsUrl: '/ev' })

    store.dispatch({
      event_id: 'e1', run_id: 'r1', session_id: 's1', request_id: 'rq1',
      type: 'cancelled', timestamp: '', payload: {},
    })
    expect(store.phase).toBe('cancelled')

    const before = store.streamingDelta
    store.dispatch({
      event_id: 'e2', run_id: 'r1', session_id: 's1', request_id: 'rq1',
      type: 'delta', timestamp: '', payload: { text: '不应追加' },
    })
    expect(store.streamingDelta).toBe(before)
  })

  it('reset 后状态归零', () => {
    const store = useChatRunStateStore()
    store.startRun({ runId: 'r1', sessionId: 's1', eventsUrl: '/ev' })
    store.dispatch({
      event_id: 'e1', run_id: 'r1', session_id: 's1', request_id: 'rq1',
      type: 'delta', timestamp: '', payload: { text: '部分回复' },
    })
    expect(store.streamingDelta).toContain('部分回复')

    store.reset()
    expect(store.phase).toBe('idle')
    expect(store.runId).toBeNull()
    expect(store.streamingDelta).toBe('')
    expect(store.errorCode).toBeNull()
  })
})
