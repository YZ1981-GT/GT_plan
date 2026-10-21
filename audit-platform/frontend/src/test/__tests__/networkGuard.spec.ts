/**
 * networkGuard.spec.ts — 单测网络隔离守卫
 *
 * spec: frontend-test-network-isolation-and-load-dedup（R1.4、R2；design §6）
 *
 * 判据看本地回环服务器**实际收到**的连接数，不看源码字符串：
 *   - 拦截开着：Node http 与 jsdom XHR（axios 走的那条）都以网络错误结束，服务器收到 0 次；
 *   - 变异反证：临时换回原始 connect，同样的请求服务器收到 1 次。
 * 本文件是故意连网的，所以每例结束清掉本文件的拦截记录，否则 setup 的 afterAll 会把它判成新泄漏。
 */
import { existsSync, readFileSync } from 'node:fs'
import http from 'node:http'
import { createServer, Socket, type AddressInfo, type Server } from 'node:net'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import axios from 'axios'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import {
  INVENTORY_PATH,
  decideNetworkVerdict,
  describeConnectTarget,
  installNetworkGuard,
} from '../networkGuard'

const guard = installNetworkGuard()
let server: Server
let port = 0
let accepted = 0

beforeAll(async () => {
  server = createServer((sock) => { accepted += 1; sock.destroy() })
  await new Promise<void>((resolve) => server.listen(0, '127.0.0.1', resolve))
  port = (server.address() as AddressInfo).port
})
afterAll(async () => {
  await new Promise<void>((resolve) => server.close(() => resolve()))
})
afterEach(() => {
  vi.useRealTimers()
  accepted = 0
  guard.attempts.length = 0
  guard.requests.length = 0
})

function nodeGet(): Promise<NodeJS.ErrnoException | 'response'> {
  return new Promise((resolve) => {
    const req = http.get({ host: '127.0.0.1', port, path: '/probe', agent: false }, () => resolve('response'))
    req.on('error', (e) => resolve(e as NodeJS.ErrnoException))
  })
}

describe('拦截：真实网络连接一律以连接失败结束', () => {
  it('Node http：以错误结束，回环服务器收到 0 次连接，拦截记录带原始目标', async () => {
    const result = await nodeGet()
    expect(result).not.toBe('response')
    expect(accepted).toBe(0)
    expect(guard.attempts).toHaveLength(1)
    expect(guard.attempts[0]).toMatchObject({ host: '127.0.0.1', port: String(port) })
  })

  it('jsdom XHR（axios 的传输层）：Network Error，回环服务器收到 0 次连接', async () => {
    await expect(axios.get(`http://127.0.0.1:${port}/api/probe`, { timeout: 5000 }))
      .rejects.toMatchObject({ code: 'ERR_NETWORK' })
    expect(accepted).toBe(0)
    expect(guard.requests).toContain(`GET http://127.0.0.1:${port}/api/probe`)
  })

  it('用例开着假定时器也照样失败（失败不依赖 setTimeout / setImmediate）', async () => {
    vi.useFakeTimers()
    await expect(axios.get(`http://127.0.0.1:${port}/api/probe`, { timeout: 5000 }))
      .rejects.toMatchObject({ code: 'ERR_NETWORK' })
    expect(accepted).toBe(0)
  })

  it('变异反证：临时换回原始 connect，同样的请求服务器收到 1 次连接', async () => {
    Socket.prototype.connect = guard.originalConnect
    try {
      await nodeGet()
      await vi.waitFor(() => expect(accepted).toBe(1))
    } finally {
      Socket.prototype.connect = guard.guardedConnect
    }
    expect(guard.attempts).toHaveLength(0)
  })

  it('安装幂等：再次安装返回同一份状态，connect 不被重复包裹', () => {
    expect(installNetworkGuard()).toBe(guard)
    expect(Socket.prototype.connect).toBe(guard.guardedConnect)
  })
})

describe('describeConnectTarget：各种 connect 调用形态', () => {
  it('options 对象 / normalizeArgs 后的数组 / (port, host)', () => {
    expect(describeConnectTarget([{ host: 'localhost', port: 3000 }])).toEqual({ host: 'localhost', port: '3000', path: null })
    expect(describeConnectTarget([[{ host: 'a', port: 1 }, () => undefined]])).toEqual({ host: 'a', port: '1', path: null })
    expect(describeConnectTarget([9980, '127.0.0.1'])).toEqual({ host: '127.0.0.1', port: '9980', path: null })
    expect(describeConnectTarget([{ path: '/tmp/x.sock' }])).toEqual({ host: null, port: null, path: '/tmp/x.sock' })
  })
})

describe('decideNetworkVerdict：跑完一个文件后的判定', () => {
  const inventory = { 'src/listed.spec.ts': ['GET /api/x'], 'src/flaky.spec.ts': ['GET /api/y'] }
  const intermittent = new Set(['src/flaky.spec.ts'])
  const base = { requests: [] as string[], inventory, intermittent, isolated: true, audit: false }

  it('不在清单里却连了网 → new-leak，信息列出请求与次数并说明清单只许删', () => {
    const v = decideNetworkVerdict({
      ...base, relFile: 'src/new.spec.ts', attempts: 3,
      requests: ['GET /api/a', 'GET /api/a', 'POST /api/b'],
    })
    expect(v.kind).toBe('new-leak')
    const msg = v.kind === 'new-leak' ? v.message : ''
    expect(msg).toContain('src/new.spec.ts')
    expect(msg).toContain('GET /api/a（×2）')
    expect(msg).toContain('POST /api/b')
    expect(msg).toContain('只许删除')
  })

  it('在清单里连了网 → ok；不在清单里也没连网 → ok', () => {
    expect(decideNetworkVerdict({ ...base, relFile: 'src/listed.spec.ts', attempts: 2 }).kind).toBe('ok')
    expect(decideNetworkVerdict({ ...base, relFile: 'src/clean.spec.ts', attempts: 0 }).kind).toBe('ok')
  })

  it('审计模式：在清单里却没连网 → stale；非审计模式不判 stale；间歇性条目不判 stale', () => {
    expect(decideNetworkVerdict({ ...base, relFile: 'src/listed.spec.ts', attempts: 0, audit: true }).kind).toBe('stale')
    expect(decideNetworkVerdict({ ...base, relFile: 'src/listed.spec.ts', attempts: 0 }).kind).toBe('ok')
    expect(decideNetworkVerdict({ ...base, relFile: 'src/flaky.spec.ts', attempts: 0, audit: true }).kind).toBe('ok')
  })

  it('共享模块图里第二个起的文件只拦不判（归因不可靠）', () => {
    expect(decideNetworkVerdict({ ...base, relFile: 'src/new.spec.ts', attempts: 5, isolated: false }).kind).toBe('ok')
  })
})

describe('泄漏清单：可伪证、只许删', () => {
  const FRONTEND_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
  const doc = JSON.parse(readFileSync(resolve(FRONTEND_ROOT, INVENTORY_PATH), 'utf-8')) as {
    files: Record<string, unknown>
    intermittent: Record<string, unknown>
  }
  const keys = Object.keys(doc.files)

  it('间歇性条目必须同时在 files 里，且写明原因', () => {
    for (const [k, why] of Object.entries(doc.intermittent)) {
      expect(keys, k).toContain(k)
      expect(typeof why === 'string' && why.length > 10, k).toBe(true)
    }
  })

  // 2026-10-19 探针现算的 25 个文件：清单只能是它们的子集（补 mock 后删条目；不许加新文件）。
  const BASELINE = new Set([
    'src/__tests__/AttachmentPreviewOfficeIframe.spec.ts',
    'src/__tests__/cfVerification.spec.ts',
    'src/__tests__/useWorkpaperNavigation.spec.ts',
    'src/components/deliverable/__tests__/DeliverableShortcut.spec.ts',
    'src/components/workpaper/GtDForm/__tests__/GtDFormQA.spec.ts',
    'src/components/workpaper/GtWpRenderer.runtime-boundary.test.ts',
    'src/components/workpaper/__tests__/F1DisclosureMount.spec.ts',
    'src/components/workpaper/__tests__/GtA121LegalConfirmation.pbt.spec.ts',
    'src/components/workpaper/__tests__/GtA1731ConsultationExecution.spec.ts',
    'src/components/workpaper/__tests__/GtA173ConsultationRecord.spec.ts',
    'src/components/workpaper/__tests__/GtA174DisagreementRecord.spec.ts',
    'src/components/workpaper/__tests__/GtA176ClosingMeeting.spec.ts',
    'src/components/workpaper/__tests__/GtA1Dashboard.spec.ts',
    'src/components/workpaper/__tests__/GtA271ItAuditMemo.spec.ts',
    'src/components/workpaper/__tests__/GtAProgramConsole.spec.ts',
    'src/components/workpaper/__tests__/GtAProgramConsoleA16Seq2.spec.ts',
    'src/components/workpaper/__tests__/GtAProgramConsoleChipDisabled.spec.ts',
    'src/components/workpaper/__tests__/GtEControlTest.spec.ts',
    'src/components/workpaper/__tests__/b22bControlMatrix.spec.ts',
    'src/components/workpaper/__tests__/c23c24PersistReadonly.spec.ts',
    'src/components/workpaper/__tests__/useB22BControlMatrix.spec.ts',
    'src/components/workpaper/composables/__tests__/tabIndexAcnrCatalog.pbt.spec.ts',
    'src/components/workpaper/d3/__tests__/D3TabIndex.spec.ts',
    'src/views/eqcr/EqcrProjectView.spec.ts',
    'src/views/workpaper-list/__tests__/WorkpaperListShell.spec.ts',
  ])

  it('只能是 2026-10-19 基线的子集（不许新增条目）', () => {
    expect(keys.filter((k) => !BASELINE.has(k))).toEqual([])
  })

  it('每条路径真实存在、证据为非空字符串数组、键按字母排序', () => {
    for (const k of keys) {
      expect(existsSync(resolve(FRONTEND_ROOT, k)), k).toBe(true)
      const ev = doc.files[k]
      expect(Array.isArray(ev) && ev.length > 0 && ev.every((e) => typeof e === 'string' && e.length > 0), k).toBe(true)
    }
    expect(keys).toEqual([...keys].sort())
  })
})
