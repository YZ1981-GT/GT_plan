/**
 * Chat Run State Store — Vitest Guards
 *
 * Feature: dsh-agent-panel-integration / Task 8
 * Validates: Requirements 1.8, 4.1, 4.4, 4.8
 * **Properties: 9, 39**
 *
 * 覆盖：
 * 1. typed event dispatch per ChatEventType
 * 2. run 生命周期状态转换
 * 3. 错误事件显示中文消息
 * 4. quota 事件追踪
 * 5. cancel 终态
 * 6. event handler 注册与 wildcard
 * 7. reset 清理状态
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import {
  useChatRunStateStore,
  ERROR_MESSAGE_ZH,
  getErrorMessageZh,
  isTerminalEvent,
  type ChatEvent,
  type ChatErrorCode,
} from '@/stores/chatRunState'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeChatEvent(overrides: Partial<ChatEvent> = {}): ChatEvent {
  return {
    event_id: '000000000001',
    run_id: '550e8400-e29b-41d4-a716-446655440000',
    session_id: '660e8400-e29b-41d4-a716-446655440000',
    request_id: '770e8400-e29b-41d4-a716-446655440000',
    type: 'run_started',
    timestamp: '2025-01-01T00:00:00Z',
    message_id: null,
    payload: {},
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('chatRunState store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  describe('typed event dispatch', () => {
    it('run_started → phase = running', () => {
      const store = useChatRunStateStore()
      store.startRun({ runId: 'r1', sessionId: 's1', eventsUrl: '/events' })
      store.dispatch(makeChatEvent({ type: 'run_started' }))
      expect(store.phase).toBe('running')
    })

    it('delta → 累加 streamingDelta', () => {
      const store = useChatRunStateStore()
      store.startRun({ runId: 'r1', sessionId: 's1', eventsUrl: '/events' })
      store.dispatch(makeChatEvent({ type: 'run_started' }))
      store.dispatch(makeChatEvent({
        event_id: '000000000002',
        type: 'delta',
        message_id: 'msg1',
        payload: { text: 'Hello' },
      }))
      store.dispatch(makeChatEvent({
        event_id: '000000000003',
        type: 'delta',
        message_id: 'msg1',
        payload: { text: ' World' },
      }))
      expect(store.streamingDelta).toBe('Hello World')
    })

    it('context_ready → 更新 contextManifest', () => {
      const store = useChatRunStateStore()
      store.startRun({ runId: 'r1', sessionId: 's1', eventsUrl: '/events' })
      const manifest = [{ source_type: 'workpaper', decision: 'included' }]
      store.dispatch(makeChatEvent({
        type: 'context_ready',
        payload: { manifest },
      }))
      expect(store.contextManifest).toEqual(manifest)
    })

    it('done → phase = done (terminal)', () => {
      const store = useChatRunStateStore()
      store.startRun({ runId: 'r1', sessionId: 's1', eventsUrl: '/events' })
      store.dispatch(makeChatEvent({ type: 'run_started' }))
      store.dispatch(makeChatEvent({ event_id: '000000000099', type: 'done' }))
      expect(store.phase).toBe('done')
      expect(store.isTerminal).toBe(true)
    })

    it('cancelled → phase = cancelled (terminal)', () => {
      const store = useChatRunStateStore()
      store.startRun({ runId: 'r1', sessionId: 's1', eventsUrl: '/events' })
      store.dispatch(makeChatEvent({ type: 'run_started' }))
      store.dispatch(makeChatEvent({ type: 'cancelled' }))
      expect(store.phase).toBe('cancelled')
      expect(store.isTerminal).toBe(true)
    })

    it('quota → 更新限流信息', () => {
      const store = useChatRunStateStore()
      store.startRun({ runId: 'r1', sessionId: 's1', eventsUrl: '/events' })
      store.dispatch(makeChatEvent({
        type: 'quota',
        payload: { remaining: 5, reset: 1700000000, retry_after: 30 },
      }))
      expect(store.quotaRemaining).toBe(5)
      expect(store.quotaReset).toBe(1700000000)
      expect(store.retryAfter).toBe(30)
    })

    it('lastEventId 随 dispatch 更新', () => {
      const store = useChatRunStateStore()
      store.startRun({ runId: 'r1', sessionId: 's1', eventsUrl: '/events' })
      store.dispatch(makeChatEvent({ event_id: '000000000010', type: 'run_started' }))
      expect(store.lastEventId).toBe('000000000010')
      store.dispatch(makeChatEvent({ event_id: '000000000011', type: 'delta', message_id: 'msg1', payload: { text: 'x' } }))
      expect(store.lastEventId).toBe('000000000011')
    })
  })

  describe('error 事件与中文消息', () => {
    it('error 事件 → phase=error + 中文消息', () => {
      const store = useChatRunStateStore()
      store.startRun({ runId: 'r1', sessionId: 's1', eventsUrl: '/events' })
      store.dispatch(makeChatEvent({ type: 'run_started' }))
      store.dispatch(makeChatEvent({
        type: 'error',
        payload: { code: 'rate_limited', message: '请求过于频繁，请稍候再试；您的输入已保留。' },
      }))
      expect(store.phase).toBe('error')
      expect(store.errorCode).toBe('rate_limited')
      expect(store.errorMessage).toContain('请求过于频繁')
      expect(store.displayError).toContain('请求过于频繁')
      expect(store.isTerminal).toBe(true)
    })

    it('error 事件无 message 时使用 ERROR_MESSAGE_ZH 默认', () => {
      const store = useChatRunStateStore()
      store.startRun({ runId: 'r1', sessionId: 's1', eventsUrl: '/events' })
      store.dispatch(makeChatEvent({ type: 'run_started' }))
      store.dispatch(makeChatEvent({
        type: 'error',
        payload: { code: 'engine_unavailable' },
      }))
      expect(store.errorMessage).toBe(ERROR_MESSAGE_ZH.engine_unavailable)
    })

    it('每个 ChatErrorCode 都有对应中文消息', () => {
      const codes: ChatErrorCode[] = [
        'access_denied', 'host_context_mismatch', 'context_build_failed',
        'semantic_unavailable', 'ocr_unavailable', 'engine_unavailable',
        'local_only_violation', 'rate_limited', 'tool_budget_exceeded',
        'attachment_invalid', 'run_cancelled', 'run_interrupted', 'adopt_log_failed',
      ]
      for (const code of codes) {
        const msg = getErrorMessageZh(code)
        expect(msg).toBeTruthy()
        expect(msg).not.toContain('undefined')
        // 确保是中文
        expect(/[\u4e00-\u9fa5]/.test(msg)).toBe(true)
      }
    })

    it('未知 error code 返回通用中文消息', () => {
      const msg = getErrorMessageZh('unknown_code_xyz')
      expect(msg).toContain('unknown_code_xyz')
      expect(msg).toContain('请稍后重试')
    })

    it('空 error code 返回通用中文消息', () => {
      const msg = getErrorMessageZh(null)
      expect(msg).toContain('未知错误')
    })
  })

  describe('run 生命周期', () => {
    it('初始 phase 为 idle', () => {
      const store = useChatRunStateStore()
      expect(store.phase).toBe('idle')
      expect(store.isActive).toBe(false)
    })

    it('startRun → creating', () => {
      const store = useChatRunStateStore()
      store.startRun({ runId: 'r1', sessionId: 's1', eventsUrl: '/api/events' })
      expect(store.phase).toBe('creating')
      expect(store.runId).toBe('r1')
      expect(store.sessionId).toBe('s1')
      expect(store.eventsUrl).toBe('/api/events')
      expect(store.isActive).toBe(true)
    })

    it('startRun 带 lastEventId', () => {
      const store = useChatRunStateStore()
      store.startRun({ runId: 'r1', sessionId: 's1', eventsUrl: '/e', lastEventId: '000000000005' })
      expect(store.lastEventId).toBe('000000000005')
    })

    it('cancel → phase=cancelled', () => {
      const store = useChatRunStateStore()
      store.startRun({ runId: 'r1', sessionId: 's1', eventsUrl: '/e' })
      store.dispatch(makeChatEvent({ type: 'run_started' }))
      store.cancel()
      expect(store.phase).toBe('cancelled')
      expect(store.isTerminal).toBe(true)
      expect(store.errorMessage).toBe(ERROR_MESSAGE_ZH.run_cancelled)
    })

    it('已终态后 cancel 不改变状态', () => {
      const store = useChatRunStateStore()
      store.startRun({ runId: 'r1', sessionId: 's1', eventsUrl: '/e' })
      store.dispatch(makeChatEvent({ type: 'run_started' }))
      store.dispatch(makeChatEvent({ type: 'done' }))
      expect(store.phase).toBe('done')
      store.cancel()
      expect(store.phase).toBe('done') // 不变
    })
  })

  describe('event handlers', () => {
    it('on(type) 注册并触发', () => {
      const store = useChatRunStateStore()
      store.startRun({ runId: 'r1', sessionId: 's1', eventsUrl: '/e' })
      const received: ChatEvent[] = []
      store.on('delta', (e) => received.push(e))
      const evt = makeChatEvent({ type: 'delta', message_id: 'msg1', payload: { text: 'x' } })
      store.dispatch(evt)
      expect(received).toHaveLength(1)
      expect(received[0].type).toBe('delta')
    })

    it('on("*") wildcard 接收所有事件', () => {
      const store = useChatRunStateStore()
      store.startRun({ runId: 'r1', sessionId: 's1', eventsUrl: '/e' })
      const received: ChatEvent[] = []
      store.on('*', (e) => received.push(e))
      store.dispatch(makeChatEvent({ type: 'run_started' }))
      store.dispatch(makeChatEvent({ event_id: '2', type: 'delta', message_id: 'msg1', payload: { text: 'x' } }))
      store.dispatch(makeChatEvent({ event_id: '3', type: 'done' }))
      expect(received).toHaveLength(3)
    })

    it('unsubscribe 取消监听', () => {
      const store = useChatRunStateStore()
      store.startRun({ runId: 'r1', sessionId: 's1', eventsUrl: '/e' })
      const received: ChatEvent[] = []
      const unsub = store.on('delta', (e) => received.push(e))
      store.dispatch(makeChatEvent({ type: 'delta', message_id: 'msg1', payload: { text: 'a' } }))
      unsub()
      store.dispatch(makeChatEvent({ event_id: '2', type: 'delta', message_id: 'msg1', payload: { text: 'b' } }))
      expect(received).toHaveLength(1)
    })
  })

  describe('reset', () => {
    it('reset 恢复所有状态到初始', () => {
      const store = useChatRunStateStore()
      store.startRun({ runId: 'r1', sessionId: 's1', eventsUrl: '/e' })
      store.dispatch(makeChatEvent({ type: 'run_started' }))
      store.dispatch(makeChatEvent({ type: 'delta', message_id: 'msg1', payload: { text: 'hello' } }))
      store.reset()
      expect(store.phase).toBe('idle')
      expect(store.runId).toBeNull()
      expect(store.sessionId).toBeNull()
      expect(store.lastEventId).toBeUndefined()
      expect(store.streamingDelta).toBe('')
      expect(store.errorCode).toBeNull()
      expect(store.errorMessage).toBeNull()
      expect(store.contextManifest).toBeNull()
    })
  })
})

// ---------------------------------------------------------------------------
// Standalone helpers
// ---------------------------------------------------------------------------

describe('isTerminalEvent', () => {
  it('done/error/cancelled 是终态', () => {
    expect(isTerminalEvent('done')).toBe(true)
    expect(isTerminalEvent('error')).toBe(true)
    expect(isTerminalEvent('cancelled')).toBe(true)
  })

  it('其他类型不是终态', () => {
    expect(isTerminalEvent('delta')).toBe(false)
    expect(isTerminalEvent('run_started')).toBe(false)
    expect(isTerminalEvent('context_ready')).toBe(false)
    expect(isTerminalEvent('tool_started')).toBe(false)
  })
})
