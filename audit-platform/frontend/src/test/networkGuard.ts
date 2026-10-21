/**
 * networkGuard.ts — 单测网络隔离（只给 `src/test/setup.ts` 和它的守卫测试用，生产代码不得 import）。
 *
 * spec: frontend-test-network-isolation-and-load-dedup（design §1、§2）
 *
 * 拦截点是 `net.Socket.prototype.connect`：jsdom 的 XHR、WebSocket、Node http 最终都落到这里。
 * 被拦下的连接不直接报错，而是改连一个不存在的本地管道，让 libuv 异步返回 ENOENT
 * （jsdom 会把它打到 stderr：`connect ENOENT …unit-test-real-network-blocked-see-src-test-networkGuard`）：
 *   - 错误走 Node 正常的异步路径，ClientRequest 已经挂好 error 监听；
 *   - 不依赖 setTimeout / setImmediate，用例开了假定时器也照样失败。
 * 对 axios 而言这和 CI 上「端口无服务」的 ECONNREFUSED 一样，都是 Network Error。
 */
import net from 'node:net'

export interface BlockedAttempt {
  host: string | null
  port: string | null
  path: string | null
  test: string | null
}

export interface NetworkGuardState {
  /** 本文件被拦下的连接 */
  attempts: BlockedAttempt[]
  /** 本文件 jsdom XHR 打开过的请求（method + URL），只用于报错信息 */
  requests: string[]
  /** 本 worker 已执行 setup 的文件数；1 表示本文件是这个 worker 跑的第一个文件 */
  fileOrdinal: number
  /** 拦截被改连到的目标：一个不存在的本地管道 */
  deadEndPath: string
  /** 原始 connect / 拦截后的 connect（守卫测试做变异反证时用来临时换回） */
  originalConnect: net.Socket['connect']
  guardedConnect: net.Socket['connect']
}

const KEY = Symbol.for('gt.test.networkGuard')

type Tagged = Record<PropertyKey, unknown>

function currentTestName(): string | null {
  const st = (globalThis as Tagged).expect as { getState?: () => { currentTestName?: string } } | undefined
  try {
    return st?.getState?.().currentTestName ?? null
  } catch {
    return null
  }
}

/** 从 connect 的各种调用形态里取出原始目标（只用于记录）。 */
export function describeConnectTarget(args: readonly unknown[]): Omit<BlockedAttempt, 'test'> {
  const first = Array.isArray(args[0]) ? (args[0] as unknown[])[0] : args[0]
  if (first && typeof first === 'object') {
    const o = first as Record<string, unknown>
    const str = (v: unknown) => (v == null ? null : String(v))
    return { host: str(o.host), port: str(o.port), path: str(o.path) }
  }
  if (typeof first === 'number' || /^\d+$/.test(String(first))) {
    return { host: typeof args[1] === 'string' ? args[1] : null, port: String(first), path: null }
  }
  return { host: null, port: null, path: first == null ? null : String(first) }
}

/** 安装拦截（幂等：同一 worker 只包裹一次），返回本 worker 共享的状态对象。 */
export function installNetworkGuard(): NetworkGuardState {
  const g = globalThis as Tagged
  const existing = g[KEY] as NetworkGuardState | undefined
  if (existing) return existing

  const proto = net.Socket.prototype
  const originalConnect = proto.connect
  // 名字本身就是说明：jsdom 会把网络错误打到 stderr，看到这个路径即知是测试基座拦的。
  const deadEndPath = process.platform === 'win32'
    ? '\\\\.\\pipe\\unit-test-real-network-blocked-see-src-test-networkGuard'
    : '/nonexistent/unit-test-real-network-blocked-see-src-test-networkGuard.sock'
  const state = {
    attempts: [],
    requests: [],
    fileOrdinal: 0,
    deadEndPath,
    originalConnect,
  } as unknown as NetworkGuardState
  const guardedConnect = function guardedConnect(this: net.Socket, ...args: unknown[]) {
    state.attempts.push({ ...describeConnectTarget(args), test: currentTestName() })
    return originalConnect.call(this, { path: state.deadEndPath })
  } as net.Socket['connect']
  state.guardedConnect = guardedConnect
  proto.connect = guardedConnect
  ;(proto as unknown as Tagged)[KEY] = true
  g[KEY] = state
  return state
}

/** 给当前 jsdom 窗口的 XHR 补一层记录（每个测试文件都有新窗口，所以每个文件调一次）。 */
export function trackXhrRequests(state: NetworkGuardState): void {
  const X = (globalThis as Tagged).XMLHttpRequest as { prototype: Tagged } | undefined
  if (!X?.prototype || X.prototype[KEY]) return
  const open = X.prototype.open as (...a: unknown[]) => unknown
  X.prototype.open = function trackedOpen(this: unknown, ...args: unknown[]) {
    state.requests.push(`${String(args[0]).toUpperCase()} ${String(args[1])}`)
    return open.apply(this, args)
  }
  X.prototype[KEY] = true
}

/** 进入新的测试文件：清空本文件记录，文件序号 +1。 */
export function beginFile(state: NetworkGuardState): void {
  state.attempts = []
  state.requests = []
  state.fileOrdinal += 1
}

/** 清单：测试文件相对路径（相对 audit-platform/frontend，`/` 分隔）→ 观测到的端点证据。 */
export type NetworkLeakInventory = Readonly<Record<string, readonly string[]>>

export type NetworkVerdict =
  | { kind: 'ok' }
  | { kind: 'new-leak'; message: string }
  | { kind: 'stale'; message: string }

export const INVENTORY_PATH = 'src/test/networkLeakInventory.json'

/**
 * 一个测试文件跑完后的判定（纯函数）。
 *
 * - 非隔离（共享模块图里第二个起的文件）只拦不判：迟到的异步请求可能落到下一个文件，归因不可靠。
 * - 不在清单里却发生了连接 → new-leak（应 mock 掉对应请求，清单只许删不许加）。
 * - 审计模式下在清单里却没有发生连接 → stale（应从清单删掉这一条）；间歇性条目不判 stale。
 *
 * 是否让本文件失败由调用方按 audit 决定：泄漏可能是间歇性的（见清单 `intermittent` 说明），
 * 常规运行只告警，审计模式才失败。
 */
export function decideNetworkVerdict(input: {
  relFile: string
  attempts: number
  requests: readonly string[]
  inventory: NetworkLeakInventory
  intermittent: ReadonlySet<string>
  isolated: boolean
  audit: boolean
}): NetworkVerdict {
  if (!input.isolated) return { kind: 'ok' }
  const listed = Object.prototype.hasOwnProperty.call(input.inventory, input.relFile)
  if (input.attempts > 0 && !listed) {
    const counts = new Map<string, number>()
    for (const r of input.requests) counts.set(r, (counts.get(r) ?? 0) + 1)
    const detail = [...counts.entries()].map(([r, n]) => `  ${r}${n > 1 ? `（×${n}）` : ''}`).join('\n')
    return {
      kind: 'new-leak',
      message:
        `${input.relFile} 发起了 ${input.attempts} 次真实网络连接（已被测试基座拦截，与 CI 上连接被拒同语义）：\n`
        + `${detail || '  （非 XHR 连接，无请求明细）'}\n`
        + `请在用例里 mock 对应请求（注意：并发 await import 同一个被 vi.mock 的模块时，第二路会绕过 mock，`
        + `宜改为在用例里 mock 到真正发请求的那一层）；不要把本文件加进 ${INVENTORY_PATH}（该清单只许删除）。`,
    }
  }
  if (input.audit && listed && input.attempts === 0 && !input.intermittent.has(input.relFile)) {
    return {
      kind: 'stale',
      message: `${input.relFile} 在 ${INVENTORY_PATH} 里，但本次没有发生真实网络连接：请删除这一条。`,
    }
  }
  return { kind: 'ok' }
}
