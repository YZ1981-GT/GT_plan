/**
 * consolRequestGuard 纯逻辑守卫（spec consol-note-node-refresh-and-formula-orchestration）。
 *
 * 覆盖：
 * - 序号递增与过期判定
 * - 上下文快照深拷贝（修改源对象不影响票据）
 * - 多维上下文（projectId/year/nodeKey/sectionId）比较
 * - 快速切换两次，第一次请求返回时应判定过期
 */
import { describe, expect, it } from 'vitest'
import { createConsolRequestGuard } from '../composables/consolRequestGuard'

describe('createConsolRequestGuard', () => {
  it('首次请求非过期', () => {
    const ctx = { projectId: 'p1', year: 2025, nodeKey: 'root:consol', sectionId: '五-1' }
    const guard = createConsolRequestGuard(() => ctx)
    const ticket = guard.startRequest()
    expect(guard.isStale(ticket)).toBe(false)
  })

  it('发出第二个请求后，第一个票据过期', () => {
    const ctx = { projectId: 'p1', year: 2025, nodeKey: 'root:consol', sectionId: '五-1' }
    const guard = createConsolRequestGuard(() => ctx)
    const t1 = guard.startRequest()
    const t2 = guard.startRequest()
    expect(guard.isStale(t1)).toBe(true)
    expect(guard.isStale(t2)).toBe(false)
  })

  it('上下文变化导致当前票据过期', () => {
    let nodeKey = 'A:parent'
    const guard = createConsolRequestGuard(() => ({
      projectId: 'p1', year: 2025, nodeKey, sectionId: '五-1',
    }))
    const ticket = guard.startRequest()
    // 切换节点
    nodeKey = 'B:subsidiary'
    expect(guard.isStale(ticket)).toBe(true)
  })

  it('sectionId 变化也导致过期', () => {
    let sectionId = '五-1'
    const guard = createConsolRequestGuard(() => ({
      projectId: 'p1', year: 2025, nodeKey: 'root:consol', sectionId,
    }))
    const ticket = guard.startRequest()
    sectionId = '五-2'
    expect(guard.isStale(ticket)).toBe(true)
  })

  it('快照是深拷贝，修改源对象不影响票据上下文', () => {
    const ctx = { projectId: 'p1', year: 2025, nodeKey: 'root:consol', sectionId: '五-1' }
    const guard = createConsolRequestGuard(() => ctx)
    const ticket = guard.startRequest()
    // 票据中的 context 是冻结快照
    expect(ticket.context.projectId).toBe('p1')
    expect(ticket.context.sectionId).toBe('五-1')
    // 因为 getContext 返回新引用（展开对象），修改原 ctx 引用不影响已发票据
    // 但 guard 的 isStale 会重新调用 getContext
    ctx.projectId = 'p2'
    // 票据的 sequence 没变但上下文变了
    expect(guard.isStale(ticket)).toBe(true)
  })

  it('年度变化导致过期', () => {
    let year = 2025
    const guard = createConsolRequestGuard(() => ({
      projectId: 'p1', year, nodeKey: 'root:consol', sectionId: '五-1',
    }))
    const ticket = guard.startRequest()
    year = 2024
    expect(guard.isStale(ticket)).toBe(true)
  })

  it('所有维度不变时票据不过期', () => {
    const guard = createConsolRequestGuard(() => ({
      projectId: 'p1', year: 2025, nodeKey: 'root:consol', sectionId: '五-1',
    }))
    const ticket = guard.startRequest()
    // 再次调用 isStale，上下文相同
    expect(guard.isStale(ticket)).toBe(false)
    expect(guard.isStale(ticket)).toBe(false)
  })

  it('A 节点五-1 → B 节点五-1：nodeKey 不同 → 过期', () => {
    let nodeKey = 'A:parent'
    const guard = createConsolRequestGuard(() => ({
      projectId: 'p1', year: 2025, nodeKey, sectionId: '五-1',
    }))
    const ticketA = guard.startRequest()
    nodeKey = 'B:subsidiary'
    guard.startRequest()
    expect(guard.isStale(ticketA)).toBe(true)
  })

  it('三次快速切换：只有最后一个票据不过期', () => {
    let section = '五-1'
    const guard = createConsolRequestGuard(() => ({
      projectId: 'p1', year: 2025, nodeKey: 'root:consol', sectionId: section,
    }))
    const t1 = guard.startRequest()
    section = '五-2'
    const t2 = guard.startRequest()
    section = '五-3'
    const t3 = guard.startRequest()
    expect(guard.isStale(t1)).toBe(true)
    expect(guard.isStale(t2)).toBe(true)
    expect(guard.isStale(t3)).toBe(false)
  })
})

// ─── 2026-10-09：AbortController 集成测试 ─────────────────────────────────────

import { isAborted } from '../composables/consolRequestGuard'

describe('AbortController 集成', () => {
  it('startRequest 返回的 ticket 包含 signal', () => {
    const guard = createConsolRequestGuard(() => ({ x: 1 }))
    const ticket = guard.startRequest()
    expect(ticket.signal).toBeInstanceOf(AbortSignal)
    expect(ticket.signal.aborted).toBe(false)
  })

  it('第二次 startRequest 自动 abort 第一次的 signal', () => {
    const guard = createConsolRequestGuard(() => ({ x: 1 }))
    const t1 = guard.startRequest()
    expect(t1.signal.aborted).toBe(false)
    const t2 = guard.startRequest()
    expect(t1.signal.aborted).toBe(true) // 第一次被 abort
    expect(t2.signal.aborted).toBe(false) // 第二次仍活跃
  })

  it('三次快速切换：前两个都被 abort', () => {
    const guard = createConsolRequestGuard(() => ({ x: 1 }))
    const t1 = guard.startRequest()
    const t2 = guard.startRequest()
    const t3 = guard.startRequest()
    expect(t1.signal.aborted).toBe(true)
    expect(t2.signal.aborted).toBe(true)
    expect(t3.signal.aborted).toBe(false)
  })

  it('abort() 取消当前飞行中的请求', () => {
    const guard = createConsolRequestGuard(() => ({ x: 1 }))
    const ticket = guard.startRequest()
    expect(ticket.signal.aborted).toBe(false)
    guard.abort()
    expect(ticket.signal.aborted).toBe(true)
  })

  it('abort() 后再 startRequest 正常工作', () => {
    const guard = createConsolRequestGuard(() => ({ x: 1 }))
    const t1 = guard.startRequest()
    guard.abort()
    expect(t1.signal.aborted).toBe(true)
    const t2 = guard.startRequest()
    expect(t2.signal.aborted).toBe(false)
  })
})

describe('isAborted 辅助函数', () => {
  it('axios ERR_CANCELED 识别为 abort', () => {
    expect(isAborted({ code: 'ERR_CANCELED' })).toBe(true)
  })

  it('fetch AbortError 识别为 abort', () => {
    expect(isAborted({ name: 'AbortError' })).toBe(true)
  })

  it('普通错误不是 abort', () => {
    expect(isAborted(new Error('网络失败'))).toBe(false)
  })

  it('null/undefined 不是 abort', () => {
    expect(isAborted(null)).toBe(false)
    expect(isAborted(undefined)).toBe(false)
  })

  it('非对象不是 abort', () => {
    expect(isAborted('ERR_CANCELED')).toBe(false)
    expect(isAborted(42)).toBe(false)
  })
})
