/**
 * POST 去重键的**插入/删除对称性** —— 同 body 的 POST 不得被永久闸死。
 *
 * ═══ 这条判据挡的是什么 ═══
 *
 * `getRequestKey` 对 POST 把 body 指纹并进键。但 body 在两个时刻类型不同：
 *
 * * `addPending`（**请求**拦截器）：`config.data` 还是对象 → 键**带** body 指纹；
 * * `removePending`（**响应**拦截器）：axios 的 `transformRequest` 已在
 *   `dispatchRequest` 里把它换成 JSON 字符串 → `typeof config.data === 'object'`
 *   为假 → 键**不带** body 指纹。
 *
 * 两把键不相等 ⇒ 成功的 POST 把自己那把键永久留在 `pendingMap` 里（只能等 5 分钟
 * 兜底定时器）。此后 5 分钟内任何**同 body** 的 POST 在发出之前就被「防重复提交」
 * 分支 abort 掉。
 *
 * 真栈形态（2026-09-23）：D4-1「表格视图 ↔ 在线编辑」反复切换。内容未改时
 * `POST …/sync/entries/…/pending-mutations` 的 body 逐字节相同（实测 81244 字节全等），
 * 于是第二次切换被静默 abort —— 桥把 canceled 当「被后发请求作废」处理（刻意不记
 * lastError），用户只看到开关自己弹回「表格视图」，没有任何报错。
 *
 * 判据以**实际是否发出请求**为准（`started.length`），不是断言键的内部形状 ——
 * 后者会随 `getRequestKey` 的实现漂移，前者就是用户看到的那件事。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    token: 't',
    refreshToken: null,
    logout: vi.fn(),
    setTokens: vi.fn(),
  }),
}))

vi.mock('nprogress', () => ({
  default: { start: vi.fn(), done: vi.fn(), inc: vi.fn() },
}))

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
}))

vi.mock('@/composables/useVersionCheck', () => ({
  versionBridge: { check: vi.fn(), push: vi.fn() },
}))

/** 与真栈 pending-mutations 同形：前 100 字符恒等、总长恒等（键必然相同）。 */
const SAME_BODY = {
  entry_id: 'xlsx/gt-d4-operating-revenue',
  sheet_key: 'd41-managed',
  expected_revision: 122,
  projection: { values: { 'adjudication_main_rows/label': 'x' } },
  client_edit_epoch: 0,
}

describe('POST 去重键插入/删除对称', () => {
  let http: typeof import('@/utils/http').default
  let started: string[]
  let originalAdapter: any

  beforeEach(async () => {
    vi.resetModules()
    http = (await import('@/utils/http')).default
    started = []
    originalAdapter = http.defaults.adapter
    http.defaults.adapter = async (config: any) => {
      if (config.signal?.aborted) {
        const err: any = new Error('canceled')
        err.code = 'ERR_CANCELED'
        err.name = 'CanceledError'
        throw err
      }
      started.push(String(config.url))
      return {
        data: { code: 200, message: 'success', data: { ok: true } },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }
  })

  afterEach(() => {
    if (http) http.defaults.adapter = originalAdapter
  })

  it('同一份 body 串行连发 4 次，4 次都真的发出去了（键不泄漏）', async () => {
    for (let i = 0; i < 4; i++) {
      // 逐次 await：不存在任何在飞的同键请求，所以「防重复提交」不该介入。
      await http.post('/api/sync/pending-mutations', { ...SAME_BODY }, { _silent: true } as any)
    }
    expect(started.length).toBe(4)
  })

  it('body 只改一个字段也照样连发两次（对照组：键随 body 变）', async () => {
    await http.post('/api/sync/pending-mutations', { ...SAME_BODY }, { _silent: true } as any)
    await http.post(
      '/api/sync/pending-mutations',
      { ...SAME_BODY, expected_revision: 123 },
      { _silent: true } as any,
    )
    expect(started.length).toBe(2)
  })

  it('真正并发的同 body POST 仍被防重复提交挡住（去重语义未被放宽）', async () => {
    let release: (() => void) | null = null
    const gate = new Promise<void>((r) => { release = r })
    http.defaults.adapter = async (config: any) => {
      if (config.signal?.aborted) {
        const err: any = new Error('canceled')
        err.code = 'ERR_CANCELED'
        err.name = 'CanceledError'
        throw err
      }
      started.push(String(config.url))
      await gate
      return {
        data: { code: 200, message: 'success', data: { ok: true } },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }
    const p1 = http.post('/api/sync/pending-mutations', { ...SAME_BODY }, { _silent: true } as any)
    const p2 = http.post('/api/sync/pending-mutations', { ...SAME_BODY }, { _silent: true } as any)
    await expect(p2).rejects.toMatchObject({ code: 'ERR_CANCELED' })
    expect(started.length).toBe(1)
    release!()
    await expect(p1).resolves.toBeTruthy()
    // 先发请求落地后闸门必须放开：同 body 可以再发。
    await http.post('/api/sync/pending-mutations', { ...SAME_BODY }, { _silent: true } as any)
    expect(started.length).toBe(2)
  })

  it('被挡下的那一发不得释放先发请求占用的闸门', async () => {
    let release: (() => void) | null = null
    const gate = new Promise<void>((r) => { release = r })
    http.defaults.adapter = async (config: any) => {
      if (config.signal?.aborted) {
        const err: any = new Error('canceled')
        err.code = 'ERR_CANCELED'
        err.name = 'CanceledError'
        throw err
      }
      started.push(String(config.url))
      await gate
      return {
        data: { code: 200, message: 'success', data: { ok: true } },
        status: 200,
        statusText: 'OK',
        headers: {},
        config,
      }
    }
    const p1 = http.post('/api/sync/pending-mutations', { ...SAME_BODY }, { _silent: true } as any)
    await expect(
      http.post('/api/sync/pending-mutations', { ...SAME_BODY }, { _silent: true } as any),
    ).rejects.toMatchObject({ code: 'ERR_CANCELED' })
    // 第 2 发的错误路径若去删闸门键，第 3 发就会在 p1 还在飞的时候被放行。
    await expect(
      http.post('/api/sync/pending-mutations', { ...SAME_BODY }, { _silent: true } as any),
    ).rejects.toMatchObject({ code: 'ERR_CANCELED' })
    expect(started.length).toBe(1)
    release!()
    await expect(p1).resolves.toBeTruthy()
  })
})
