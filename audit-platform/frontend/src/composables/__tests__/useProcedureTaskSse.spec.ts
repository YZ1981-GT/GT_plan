// Feature: procedure-delegation-notification — Task 11 前端 SSE event_id LRU 幂等
//
// Design F4 / 需求 10.6：SSE at-least-once，前端按 event_id LRU 去重，重复/乱序事件
// 至多触发一次刷新；新事件才触发注册的刷新回调（重新拉取任务列表/未读数收敛）。
import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  PROCEDURE_TASK_SSE_EVENT,
  isProcedureTaskSseEvent,
  ingestProcedureTaskEvent,
  onProcedureTaskRefresh,
  _resetProcedureTaskSse,
  _seenSize,
} from '../useProcedureTaskSse'

describe('useProcedureTaskSse — event_id LRU 幂等 (Task 11 / P30 前端)', () => {
  beforeEach(() => _resetProcedureTaskSse())

  it('识别程序行任务 SSE 事件类型', () => {
    expect(isProcedureTaskSseEvent({ event_type: PROCEDURE_TASK_SSE_EVENT })).toBe(true)
    expect(isProcedureTaskSseEvent({ event_type: 'other.event' })).toBe(false)
    expect(isProcedureTaskSseEvent(null)).toBe(false)
  })

  it('新 event_id 触发一次刷新；重复 event_id 不再触发（幂等收敛）', () => {
    const refresh = vi.fn()
    onProcedureTaskRefresh(refresh)

    const ev = { event_type: PROCEDURE_TASK_SSE_EVENT, extra: { event_id: 'e-1' } }
    expect(ingestProcedureTaskEvent(ev)).toBe(true)
    expect(refresh).toHaveBeenCalledTimes(1)

    // 重复同一 event_id（at-least-once 重投递）→ 不再刷新
    expect(ingestProcedureTaskEvent(ev)).toBe(false)
    expect(ingestProcedureTaskEvent({ ...ev })).toBe(false)
    expect(refresh).toHaveBeenCalledTimes(1)

    // 新的 event_id → 再触发一次
    expect(ingestProcedureTaskEvent({ event_type: PROCEDURE_TASK_SSE_EVENT, extra: { event_id: 'e-2' } })).toBe(true)
    expect(refresh).toHaveBeenCalledTimes(2)
  })

  it('兼容扁平 event_id 与 extra.event_id；缺 event_id 不触发', () => {
    const refresh = vi.fn()
    onProcedureTaskRefresh(refresh)
    expect(ingestProcedureTaskEvent({ event_id: 'flat-1' })).toBe(true)
    expect(ingestProcedureTaskEvent({ event_type: PROCEDURE_TASK_SSE_EVENT })).toBe(false) // 无 event_id
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it('多个刷新回调都被调用；取消注册后不再被调用', () => {
    const a = vi.fn()
    const b = vi.fn()
    const off = onProcedureTaskRefresh(a)
    onProcedureTaskRefresh(b)
    ingestProcedureTaskEvent({ extra: { event_id: 'e-x' } })
    expect(a).toHaveBeenCalledTimes(1)
    expect(b).toHaveBeenCalledTimes(1)
    off()
    ingestProcedureTaskEvent({ extra: { event_id: 'e-y' } })
    expect(a).toHaveBeenCalledTimes(1) // 已取消
    expect(b).toHaveBeenCalledTimes(2)
  })

  it('LRU 上限 200：超出后最旧 event_id 被淘汰（可被再次触发）', () => {
    const refresh = vi.fn()
    onProcedureTaskRefresh(refresh)
    for (let i = 0; i < 200; i++) {
      ingestProcedureTaskEvent({ extra: { event_id: `bulk-${i}` } })
    }
    expect(_seenSize()).toBe(200)
    // 再来 1 个新事件 → 淘汰最旧 bulk-0
    expect(ingestProcedureTaskEvent({ extra: { event_id: 'bulk-200' } })).toBe(true)
    expect(_seenSize()).toBe(200)
    // bulk-0 已被淘汰 → 再次出现视为新事件
    expect(ingestProcedureTaskEvent({ extra: { event_id: 'bulk-0' } })).toBe(true)
    // bulk-200 仍在窗口内 → 重复不触发
    expect(ingestProcedureTaskEvent({ extra: { event_id: 'bulk-200' } })).toBe(false)
  })
})
