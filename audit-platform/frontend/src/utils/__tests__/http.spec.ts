/**
 * Spec C R10 Sprint 1.3.2 — http.ts 5xx 环形缓冲单测
 *
 * 4 用例：
 * 1. 少于 10 次请求返回 0
 * 2. 5xx 阈值触发
 * 3. 1 分钟外被排除
 * 4. 缓冲区上限 100
 *
 * 注：直接通过 recent5xxRate / getRecentNetworkStats 测；
 * 用 _resetNetworkStats 清缓冲区；用 _trackResponseForTest 模拟请求记录。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// 测试需要直接操作内部缓冲区，所以引入完整 http 模块
import { recent5xxRate, getRecentNetworkStats, _resetNetworkStats } from '../http'

// 因为 http.ts 内部 _last100Requests 是模块级私有状态，这里手动模拟请求
// 通过启动 axios mock 触发 interceptor，但更简单直接：暴露一个 helper 通过 monkey-patch
// 简化方案：直接 import http 默认实例，调 http.interceptors.response.handlers[0]

import http from '../http'

function fakePush(status: number, tsOffset: number = 0) {
  const fakeResponse = {
    status,
    config: {
      url: '/test',
      method: 'get',
      _startTime: Date.now() - 100,
    },
    headers: {},
    data: null,
  } as any
  // 通过响应拦截器入队（仅触发 _trackResponse 和返回值，不需要 remove pending）
  // 因为 addPending 不会被触发（没走完整 axios 流程），这里手动调用 success handler
  const handlers = (http.interceptors.response as any).handlers
  if (handlers && handlers.length > 0) {
    try {
      handlers[0].fulfilled(fakeResponse)
    } catch {
      /* ignore */
    }
  }
  if (tsOffset !== 0) {
    // 通过修改时间来模拟历史请求 — 直接 mock Date.now
    // 暂不实现，由 vi.useFakeTimers 控制
  }
}

describe('http.ts 5xx 环形缓冲', () => {
  beforeEach(() => {
    _resetNetworkStats()
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-06-01T10:00:00Z'))
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('少于 10 次请求返回 0', () => {
    for (let i = 0; i < 5; i++) {
      fakePush(500)
    }
    expect(recent5xxRate()).toBe(0)
    expect(getRecentNetworkStats().xx5_rate).toBe(0)
  })

  it('5xx 阈值触发（>=10 次请求且全 5xx）', () => {
    for (let i = 0; i < 10; i++) {
      fakePush(500)
    }
    expect(recent5xxRate()).toBe(1.0)
    const stats = getRecentNetworkStats()
    expect(stats.xx5_count).toBe(10)
    expect(stats.total).toBe(10)
    expect(stats.last_5xx_at).not.toBeNull()
  })

  it('200 状态码不计入 5xx', () => {
    for (let i = 0; i < 9; i++) fakePush(200)
    fakePush(500)
    expect(recent5xxRate()).toBe(0.1)
  })

  it('1 分钟外的请求被排除', () => {
    // 推 5 个 5xx
    for (let i = 0; i < 5; i++) fakePush(500)
    // 时间快进 2 分钟
    vi.advanceTimersByTime(120_000)
    // 再推 5 个 200，最近窗口内只有这 5 个 200，但 < 10 阈值
    for (let i = 0; i < 5; i++) fakePush(200)
    expect(recent5xxRate()).toBe(0)
    // total 应该是 5（只算最近 1 分钟）
    expect(getRecentNetworkStats().total).toBe(5)
  })

  it('缓冲区上限 100', () => {
    for (let i = 0; i < 150; i++) fakePush(200)
    // 5xx 应该是 0
    expect(getRecentNetworkStats().total).toBeLessThanOrEqual(100)
  })
})
