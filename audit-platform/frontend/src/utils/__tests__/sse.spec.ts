/**
 * SSE Canonical Parser — Vitest Guards
 *
 * Feature: dsh-agent-panel-integration / Task 8
 * Validates: Requirements 1.8, 4.1, 4.4, 4.8
 * **Properties: 9 (SSE 任意分片与续传等价)**
 *
 * 覆盖：
 * 1. Property 9：任意字节分片下解析结果与未分片基线完全一致
 * 2. CRLF/LF/CR 混合行尾
 * 3. 多行 data（多个 data: 行合并）
 * 4. id: 字段追踪与 lastEventId
 * 5. 心跳（注释帧）不 dispatch
 * 6. server_draining 帧识别
 * 7. 连续事件分离
 * 8. retry: 字段解析
 * 9. 空 data buffer 不 dispatch
 */

import { describe, it, expect } from 'vitest'
import {
  createParseState,
  feedChunk,
  flushState,
  DRAINING_EVENT_NAME,
  type SSEEvent,
} from '@/utils/sse'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** 构建完整 SSE 帧文本（LF 行尾） */
function frame(opts: { id?: string; event?: string; data: string; retry?: number }): string {
  let out = ''
  if (opts.id !== undefined) out += `id: ${opts.id}\n`
  if (opts.event !== undefined) out += `event: ${opts.event}\n`
  if (opts.retry !== undefined) out += `retry: ${opts.retry}\n`
  for (const line of opts.data.split('\n')) {
    out += `data: ${line}\n`
  }
  out += '\n'
  return out
}

/** 把完整流一次性解析（基线参考） */
function parseAll(stream: string): SSEEvent[] {
  const state = createParseState()
  const events = feedChunk(state, stream)
  events.push(...flushState(state))
  return events
}

/** 按给定切分点把字符串分成多段 */
function splitAt(str: string, positions: number[]): string[] {
  const parts: string[] = []
  let prev = 0
  for (const pos of positions) {
    parts.push(str.slice(prev, pos))
    prev = pos
  }
  parts.push(str.slice(prev))
  return parts
}

/** 按固定 chunk 大小分割 */
function splitBySize(str: string, size: number): string[] {
  const parts: string[] = []
  for (let i = 0; i < str.length; i += size) {
    parts.push(str.slice(i, i + size))
  }
  return parts
}

/** 分段灌入并收集结果 */
function parseInChunks(stream: string, chunks: string[]): SSEEvent[] {
  const state = createParseState()
  const events: SSEEvent[] = []
  for (const chunk of chunks) {
    events.push(...feedChunk(state, chunk))
  }
  events.push(...flushState(state))
  return events
}

// ---------------------------------------------------------------------------
// Property 9: 任意字节分片与续传等价
// ---------------------------------------------------------------------------

describe('Property 9: 任意分片等价', () => {
  const sampleStream =
    frame({ id: '000000000001', event: 'run_started', data: '{"event_id":"000000000001","type":"run_started"}' }) +
    frame({ id: '000000000002', event: 'delta', data: '{"event_id":"000000000002","type":"delta","payload":{"text":"Hello"}}' }) +
    frame({ id: '000000000003', event: 'done', data: '{"event_id":"000000000003","type":"done"}' })

  const baseline = parseAll(sampleStream)

  it('未分片基线包含 3 个事件', () => {
    expect(baseline).toHaveLength(3)
    expect(baseline[0].type).toBe('run_started')
    expect(baseline[1].type).toBe('delta')
    expect(baseline[2].type).toBe('done')
  })

  it('每字节分片结果与基线一致', () => {
    const chunks = splitBySize(sampleStream, 1)
    const result = parseInChunks(sampleStream, chunks)
    expect(result).toEqual(baseline)
  })

  it('2 字节分片结果与基线一致', () => {
    const chunks = splitBySize(sampleStream, 2)
    const result = parseInChunks(sampleStream, chunks)
    expect(result).toEqual(baseline)
  })

  it('7 字节分片结果与基线一致', () => {
    const chunks = splitBySize(sampleStream, 7)
    const result = parseInChunks(sampleStream, chunks)
    expect(result).toEqual(baseline)
  })

  it('在 data: 行中间切分仍一致', () => {
    // 找到 "data:" 出现的位置，在中间切
    const dataIdx = sampleStream.indexOf('data: {"event_id":"000000000002"')
    const midPoint = dataIdx + 10 // 在 JSON 中间
    const chunks = splitAt(sampleStream, [midPoint])
    const result = parseInChunks(sampleStream, chunks)
    expect(result).toEqual(baseline)
  })

  it('在空行（事件边界）处切分仍一致', () => {
    // 找到第一个 \n\n
    const boundary = sampleStream.indexOf('\n\n') + 1 // 切在两个 \n 之间
    const chunks = splitAt(sampleStream, [boundary])
    const result = parseInChunks(sampleStream, chunks)
    expect(result).toEqual(baseline)
  })

  it('随机切分点结果一致（10 组）', () => {
    for (let i = 0; i < 10; i++) {
      const numCuts = Math.floor(Math.random() * 8) + 1
      const positions = Array.from({ length: numCuts }, () =>
        Math.floor(Math.random() * sampleStream.length),
      ).sort((a, b) => a - b)
      const chunks = splitAt(sampleStream, positions)
      const result = parseInChunks(sampleStream, chunks)
      expect(result).toEqual(baseline)
    }
  })
})

// ---------------------------------------------------------------------------
// CRLF / LF / CR 混合行尾
// ---------------------------------------------------------------------------

describe('CRLF/LF/CR 混合行尾', () => {
  it('CRLF 行尾正确解析', () => {
    const stream = 'id: 001\r\nevent: delta\r\ndata: hello\r\n\r\n'
    const events = parseAll(stream)
    expect(events).toHaveLength(1)
    expect(events[0].type).toBe('delta')
    expect(events[0].data).toBe('hello')
    expect(events[0].id).toBe('001')
  })

  it('纯 LF 行尾正确解析', () => {
    const stream = 'event: done\ndata: {"ok":true}\n\n'
    const events = parseAll(stream)
    expect(events).toHaveLength(1)
    expect(events[0].type).toBe('done')
    expect(events[0].data).toBe('{"ok":true}')
  })

  it('混合 CRLF 和 LF 行尾', () => {
    const stream = 'id: 1\r\nevent: delta\ndata: mixed\r\n\n'
    const events = parseAll(stream)
    expect(events).toHaveLength(1)
    expect(events[0].data).toBe('mixed')
  })

  it('CRLF 跨 chunk 分片（CR 在前一 chunk 末尾）', () => {
    const stream = 'event: delta\r\ndata: test\r\n\r\n'
    // 在 \r 和 \n 之间切
    const crlfIdx = stream.indexOf('\r\n')
    const chunks = splitAt(stream, [crlfIdx + 1]) // 切在 \r 之后
    const result = parseInChunks(stream, chunks)
    expect(result).toHaveLength(1)
    expect(result[0].data).toBe('test')
  })
})

// ---------------------------------------------------------------------------
// 多行 data
// ---------------------------------------------------------------------------

describe('多行 data', () => {
  it('两个 data: 行合并为一行（LF 拼接）', () => {
    const stream = 'data: line1\ndata: line2\n\n'
    const events = parseAll(stream)
    expect(events).toHaveLength(1)
    expect(events[0].data).toBe('line1\nline2')
  })

  it('三行 data + event + id', () => {
    const stream = 'id: 42\nevent: context_ready\ndata: a\ndata: b\ndata: c\n\n'
    const events = parseAll(stream)
    expect(events).toHaveLength(1)
    expect(events[0].data).toBe('a\nb\nc')
    expect(events[0].type).toBe('context_ready')
    expect(events[0].id).toBe('42')
  })

  it('分片在两个 data: 行之间不丢失', () => {
    const stream = 'data: first\ndata: second\n\n'
    const splitPoint = stream.indexOf('data: second')
    const chunks = splitAt(stream, [splitPoint])
    const result = parseInChunks(stream, chunks)
    expect(result).toHaveLength(1)
    expect(result[0].data).toBe('first\nsecond')
  })
})

// ---------------------------------------------------------------------------
// id: 字段与 lastEventId
// ---------------------------------------------------------------------------

describe('id: 字段与 lastEventId', () => {
  it('事件携带 id 字段', () => {
    const stream = 'id: 000000000005\nevent: delta\ndata: x\n\n'
    const events = parseAll(stream)
    expect(events[0].id).toBe('000000000005')
  })

  it('lastEventId 在 state 中更新', () => {
    const state = createParseState()
    feedChunk(state, 'id: ev1\ndata: a\n\n')
    expect(state.lastEventId).toBe('ev1')
    feedChunk(state, 'id: ev2\ndata: b\n\n')
    expect(state.lastEventId).toBe('ev2')
  })

  it('无 id 的帧不更新 lastEventId', () => {
    const state = createParseState('initial')
    feedChunk(state, 'data: no id\n\n')
    expect(state.lastEventId).toBe('initial')
  })

  it('含 NUL 的 id 被忽略（SSE 规范）', () => {
    const state = createParseState('old')
    feedChunk(state, 'id: has\x00nul\ndata: x\n\n')
    expect(state.lastEventId).toBe('old')
  })
})

// ---------------------------------------------------------------------------
// 心跳（注释帧）不 dispatch
// ---------------------------------------------------------------------------

describe('心跳与注释帧', () => {
  it('注释帧不产生事件', () => {
    const stream = ': heartbeat\n\n'
    const events = parseAll(stream)
    expect(events).toHaveLength(0)
  })

  it('注释帧不推进 lastEventId', () => {
    const state = createParseState('prev')
    feedChunk(state, ': heartbeat\n\n')
    expect(state.lastEventId).toBe('prev')
  })

  it('注释帧穿插在业务帧之间不影响解析', () => {
    const stream =
      'id: 1\nevent: delta\ndata: a\n\n' +
      ': heartbeat\n\n' +
      'id: 2\nevent: done\ndata: b\n\n'
    const events = parseAll(stream)
    expect(events).toHaveLength(2)
    expect(events[0].id).toBe('1')
    expect(events[1].id).toBe('2')
  })

  it('注释帧分片不产生虚假事件', () => {
    const stream = ': keep-alive\n\n'
    const chunks = splitBySize(stream, 3)
    const result = parseInChunks(stream, chunks)
    expect(result).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// server_draining 帧
// ---------------------------------------------------------------------------

describe('server_draining 帧', () => {
  it('drain 帧被识别为 server_draining 事件', () => {
    const stream = `event: ${DRAINING_EVENT_NAME}\ndata: {"code":"server_draining","message":"服务端正在优雅关闭"}\n\n`
    const events = parseAll(stream)
    expect(events).toHaveLength(1)
    expect(events[0].type).toBe(DRAINING_EVENT_NAME)
    expect(events[0].id).toBeUndefined() // drain 帧刻意不带 id
  })

  it('drain 帧不推进 lastEventId', () => {
    const state = createParseState('ev3')
    feedChunk(state, `event: ${DRAINING_EVENT_NAME}\ndata: {"code":"server_draining"}\n\n`)
    expect(state.lastEventId).toBe('ev3') // 未变
  })

  it('drain 帧在分片下仍正确识别', () => {
    const stream = `event: ${DRAINING_EVENT_NAME}\ndata: {"code":"server_draining","message":"关闭中"}\n\n`
    const chunks = splitBySize(stream, 5)
    const result = parseInChunks(stream, chunks)
    expect(result).toHaveLength(1)
    expect(result[0].type).toBe(DRAINING_EVENT_NAME)
  })
})

// ---------------------------------------------------------------------------
// Last-Event-ID 续传等价（Property 9 后半句）
// ---------------------------------------------------------------------------

describe('Last-Event-ID 续传', () => {
  it('createParseState 可接收初始 lastEventId', () => {
    const state = createParseState('000000000005')
    expect(state.lastEventId).toBe('000000000005')
  })

  it('带初始 ID 后续事件正常累加', () => {
    const state = createParseState('000000000005')
    const events = feedChunk(state, 'id: 000000000006\nevent: delta\ndata: x\n\n')
    expect(events).toHaveLength(1)
    expect(events[0].id).toBe('000000000006')
    expect(state.lastEventId).toBe('000000000006')
  })
})

// ---------------------------------------------------------------------------
// retry: 字段
// ---------------------------------------------------------------------------

describe('retry: 字段', () => {
  it('合法 retry 被解析', () => {
    const stream = 'retry: 5000\ndata: test\n\n'
    const events = parseAll(stream)
    expect(events).toHaveLength(1)
    expect(events[0].retry).toBe(5000)
  })

  it('非数字 retry 被忽略', () => {
    const stream = 'retry: abc\ndata: test\n\n'
    const events = parseAll(stream)
    expect(events[0].retry).toBeUndefined()
  })
})

// ---------------------------------------------------------------------------
// 边界情况
// ---------------------------------------------------------------------------

describe('边界情况', () => {
  it('空 data buffer 不 dispatch', () => {
    // 只有 event: 行但没有 data: 行 → 不 dispatch
    const stream = 'event: delta\n\n'
    const events = parseAll(stream)
    expect(events).toHaveLength(0)
  })

  it('data: 后无值仍 dispatch（空字符串）', () => {
    const stream = 'data:\n\n'
    const events = parseAll(stream)
    expect(events).toHaveLength(1)
    expect(events[0].data).toBe('')
  })

  it('data: 后有空格但无值 dispatch 空串', () => {
    const stream = 'data: \n\n'
    const events = parseAll(stream)
    expect(events).toHaveLength(1)
    expect(events[0].data).toBe('')
  })

  it('多个连续空行只触发一次 dispatch（data buffer 已清空）', () => {
    const stream = 'data: one\n\n\n\ndata: two\n\n'
    const events = parseAll(stream)
    expect(events).toHaveLength(2)
    expect(events[0].data).toBe('one')
    expect(events[1].data).toBe('two')
  })

  it('无冒号的字段行作为 field name、value 为空', () => {
    const stream = 'data\n\n'
    const events = parseAll(stream)
    // "data" 无冒号 → field=data, value="" → dataLines=['']
    expect(events).toHaveLength(1)
    expect(events[0].data).toBe('')
  })

  it('flushState 处理流末尾无空行的事件', () => {
    const state = createParseState()
    const events1 = feedChunk(state, 'data: trailing')
    expect(events1).toHaveLength(0)
    const events2 = flushState(state)
    expect(events2).toHaveLength(1)
    expect(events2[0].data).toBe('trailing')
  })
})
