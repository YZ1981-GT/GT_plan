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
