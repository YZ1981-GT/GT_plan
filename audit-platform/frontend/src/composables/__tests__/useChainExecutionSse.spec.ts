/**
 * useChainExecution · 进度 SSE（真 composable，只替换 createSSE 与 apiProxy）
 *
 * 缺陷（2026-09-30 实测）：原生 EventSource + `?token=` —— 端点只认 Bearer 头（`?token=` 401）⇒ 从未连上；
 * 且后端按 `event: step_started` 等**具名事件**推送、载荷不带 `type`，`onmessage` 只收无名事件 ⇒
 * 即便连上，步骤状态与终止事件 `chain_completed` 也永远收不到。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

class FakeConn {
  static all: FakeConn[] = []
  msg: ((d: any, e?: string) => void) | null = null
  err: ((e: any) => void) | null = null
  closed = false
  constructor(public url: string, public opts: any) { FakeConn.all.push(this) }
  onMessage(h: (d: any, e?: string) => void) { this.msg = h }
  onError(h: (e: any) => void) { this.err = h }
  onOpen() {}
  onDraining() {}
  close() { this.closed = true }
  get isConnected() { return !this.closed }
  get lastEventId() { return undefined }
}
vi.mock('@/utils/sse', () => ({ createSSE: (url: string, opts: any) => new FakeConn(url, opts) }))

const post = vi.fn()
vi.mock('@/services/apiProxy', () => ({ api: { post: (...a: any[]) => post(...a), get: vi.fn(async () => []) } }))
vi.mock('element-plus', () => ({ ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn() } }))

import { ElMessage } from 'element-plus'
import { useChainExecution } from '../useChainExecution'

beforeEach(() => {
  FakeConn.all = []
  post.mockReset()
  post.mockResolvedValue({ execution_id: 'exec-1', status: 'running', steps: {} })
  vi.mocked(ElMessage.success).mockClear()
  vi.mocked(ElMessage.warning).mockClear()
  vi.mocked(ElMessage.error).mockClear()
})

/** 所有提示里以「生成底稿：」开头的那条（生成回执提示） */
function receiptToasts(): Array<{ level: string; message: string }> {
  const out: Array<{ level: string; message: string }> = []
  for (const level of ['success', 'warning', 'error'] as const) {
    for (const [arg] of vi.mocked(ElMessage[level]).mock.calls) {
      const message = typeof arg === 'string' ? arg : (arg as { message?: string })?.message ?? ''
      if (message.startsWith('生成底稿：')) out.push({ level, message })
    }
  }
  return out
}

describe('useChainExecution 进度流', () => {
  it('经 createSSE 订阅（不拼 ?token= 进 URL）', async () => {
    const c = useChainExecution(ref('p1'))
    await c.executeFullChain(2025)
    expect(FakeConn.all).toHaveLength(1)
    expect(FakeConn.all[0].url).toBe('/api/projects/p1/workflow/progress/exec-1')
    expect(FakeConn.all[0].url).not.toContain('token=')
  })

  it('具名事件按事件名更新步骤状态；chain_completed 结束执行并关流', async () => {
    const c = useChainExecution(ref('p1'))
    await c.executeFullChain(2025)
    const conn = FakeConn.all[0]
    conn.msg!({ step: 'recalc_tb', status: 'running' }, 'step_started')
    expect(c.stepStates.value.find((s) => s.key === 'recalc_tb')?.status).toBe('running')
    conn.msg!({ step: 'recalc_tb', status: 'completed', duration_ms: 12 }, 'step_completed')
    expect(c.stepStates.value.find((s) => s.key === 'recalc_tb')?.durationMs).toBe(12)
    expect(c.executing.value).toBe(true)
    conn.msg!({ status: 'completed', total_duration_ms: 99, results: {} }, 'chain_completed')
    expect(c.executing.value).toBe(false)
    expect(c.totalDurationMs.value).toBe(99)
    expect(conn.closed).toBe(true)
    expect(receiptToasts()).toEqual([])
  })

  it('「生成底稿」步的回执单独提示，失败的编码与原因写进提示（spec procedure-chain-hardening-and-java-contracts R11）', async () => {
    const c = useChainExecution(ref('p1'))
    await c.executeFullChain(2025)
    const summary = {
      created: 1,
      created_codes: ['E1'],
      failures: [{ wp_code: 'A1', error: '模板文件被占用' }],
      header_unfilled: 1,
    }
    FakeConn.all[0].msg!({ step: 'generate_workpapers', status: 'completed', summary }, 'step_completed')
    FakeConn.all[0].msg!({ status: 'completed', results: { generate_workpapers: { status: 'completed', summary } } },
      'chain_completed')
    const toasts = receiptToasts()
    expect(toasts).toHaveLength(1)
    expect(toasts[0].level).toBe('warning')
    expect(toasts[0].message).toContain('生成底稿：底稿生成完成，共创建 1 份底稿')
    expect(toasts[0].message).toContain('1 个编码生成失败：A1（模板文件被占用）')
    expect(toasts[0].message).toContain('1 份底稿生成时未写入表头')
  })

  it('「生成底稿」步失败或没跑：不提示生成回执（只报步骤结果）', async () => {
    const c = useChainExecution(ref('p1'))
    await c.executeFullChain(2025)
    FakeConn.all[0].msg!({ step: 'generate_workpapers', status: 'failed', error_message: '读取程序裁剪结果失败' },
      'step_failed')
    FakeConn.all[0].msg!({ status: 'completed', results: { generate_workpapers: { status: 'failed', error: 'x' } } },
      'chain_completed')
    expect(receiptToasts()).toEqual([])
    expect(ElMessage.error).toHaveBeenCalled()
  })
})
