/**
 * 浏览器标签页唯一实例 ID（窗口编号）
 *
 * 需求：
 * - 同一标签页内（包括页面刷新）返回同一个 ID → 编辑锁 heartbeat 不断裂
 * - 另一个标签页必须拿到不同的 ID → 编辑锁隔离（同一底稿第二窗只读）
 *
 * ID 存 sessionStorage（刷新后保留）。但浏览器会把 sessionStorage 原样复制给新标签页：
 * - `window.open` 打开的标签页（有 opener）
 * - 浏览器「复制标签页」（没有 opener）—— 原先只认 opener，复制出来的标签页沿用原编号，
 *   编辑锁把两个窗口当成一个、两边都能编辑同一张底稿（spec workpaper-multi-window-lock-gaps，2026-10-31 实测）
 *
 * 认领（{@link claimClientInstanceId}）：用 Web Locks 对编号加锁 `gt-client-instance:<id>`，持有到本页卸载。
 * 拿不到 ⇒ 另一个活着的标签页正在用这个编号 ⇒ 换新编号。刷新时旧文档卸载即释放，新文档认领回原编号。
 *
 * 认领标记（R4）：本版代码定下的编号另记 `gt-client-instance-claimed`。升级前打开、没刷新过的标签页不认领也不登记，
 * 从它复制出来的标签页会认领到同一编号 ⇒ 读到没有标记的编号一律换一次号。
 *
 * 浏览器不提供 Web Locks 时（用 http + 内网地址访问不是安全上下文，`navigator.locks` 与 `crypto.randomUUID` 都没有，
 * 2026-10-31 实测）：打开着的标签页把编号登记在 localStorage（带本文档标识），页面隐藏时注销本文档的登记。
 * 读到自己的编号被别的文档登记着 ⇒ 先在 BroadcastChannel 上问有没有标签页在用：有回答（或登记标着被浏览器冻结）⇒ 换号；
 * 1.5 秒没人回答 ⇒ 登记是崩溃前的本页留下的，认回原编号（R5，原先一律换号，崩溃前的编辑锁让本页只读最长 5 分钟）。
 * 另外仍按原先的 opener 判断。被浏览器丢弃（省内存）后重新加载时登记是本页自己的，直接认回；
 * 同一文档里重新加载本模块（开发热更新 / 单测）时登记是本文档先前的实例写的，也直接认回。
 *
 * 编号定下来之前，写请求 / 编辑锁请求 / 取 OnlyOffice 配置的请求先等认领（`utils/http.ts`，R5.4）。
 *
 * spec: multi-window-ledger-workbench Phase 2 Task 8 + 复盘 P0-1 修复；workpaper-multi-window-lock-gaps R1 / R4 / R5
 */
import { newUuid } from './uuid'

const STORAGE_KEY = 'gt-client-instance-id'
/** 本版代码定下的编号（值 = 编号）；读到的编号没有对应标记 ⇒ 升级前的页面写的 */
const CLAIMED_KEY = 'gt-client-instance-claimed'
const LOCK_PREFIX = 'gt-client-instance:'
/** 不支持 Web Locks 时打开着的标签页的编号登记（localStorage，值 `{"n":文档标识,"t":登记时间,"f":1=冻结}`） */
const OPEN_PREFIX = 'gt-client-instance-open:'
/** 不支持 Web Locks 时问「谁在用这个编号」的频道 */
const PROBE_CHANNEL = 'gt-client-instance-probe'
/** 问答等多久：打开着的标签页几毫秒内就回答，超过即认为登记是崩溃前的本页留下的 */
export const PROBE_TIMEOUT_MS = 1500
/** Web Locks 兜底：超时按「不可用」保留当前编号，写请求不至于一直等认领 */
const LOCK_TIMEOUT_MS = 3000

/** 本文档标识：分得清登记是本文档写的，还是别的标签页 / 崩溃前的本页写的（只需在本浏览器内不重复） */
const DOC_NONCE = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
/**
 * 同一文档里先后加载过的本模块实例的文档标识（开发热更新、单测重载模块时一个文档里会有多个实例；不同文档全局对象不同）。
 * 登记是它们写的 ⇒ 就是本文档自己的，不用问；本文档发的询问也不答 —— 否则重载模块后第一个写请求要等一轮问答，
 * 旧实例还会以同号作答、让新实例误以为被别的标签页占着而换号。
 */
const SAME_DOCUMENT: Set<string> = (() => {
  const g = globalThis as typeof globalThis & { [k: symbol]: Set<string> | undefined }
  const key = Symbol.for('gt-client-instance-docs')
  const set = g[key] ?? new Set<string>()
  g[key] = set
  set.add(DOC_NONCE)
  return set
})()

interface OpenEntry {
  n: string
  t: number
  f?: 1
}

let _cached: string | null = null
let _claim: Promise<string> | null = null
let _settled = false
let _openListening = false
let _probeChannel: BroadcastChannel | null = null

function webLocks(): LockManager | null {
  try {
    const locks = typeof navigator !== 'undefined' ? navigator.locks : undefined
    return locks && typeof locks.request === 'function' ? locks : null
  } catch {
    return null
  }
}

function openRegistry(): Storage | null {
  try {
    return typeof localStorage !== 'undefined' ? localStorage : null
  } catch {
    return null
  }
}

/** 编号的登记；认不出写的人（第一轮的登记值是纯时间戳）按别的文档的登记算。 */
function readOpen(id: string): OpenEntry | null {
  let raw: string | null
  try {
    raw = openRegistry()?.getItem(OPEN_PREFIX + id) ?? null
  } catch {
    return null
  }
  if (raw == null) return null
  try {
    const v = JSON.parse(raw) as Partial<OpenEntry> | null
    if (v && typeof v === 'object' && typeof v.n === 'string') {
      return v.f === 1 ? { n: v.n, t: Number(v.t) || 0, f: 1 } : { n: v.n, t: Number(v.t) || 0 }
    }
  } catch {
    // 不是 JSON
  }
  return { n: '', t: Number(raw) || 0 }
}

function writeOpen(frozen = false): void {
  if (!_cached) return
  const entry: OpenEntry = frozen ? { n: DOC_NONCE, t: Date.now(), f: 1 } : { n: DOC_NONCE, t: Date.now() }
  try {
    openRegistry()?.setItem(OPEN_PREFIX + _cached, JSON.stringify(entry))
  } catch {
    // 写不进：只剩 opener 判断
  }
}

function removeOwnOpen(): void {
  if (!_cached || readOpen(_cached)?.n !== DOC_NONCE) return
  try {
    openRegistry()?.removeItem(OPEN_PREFIX + _cached)
  } catch {
    // ignore
  }
}

/** 登记本页编号；页面隐藏时注销本文档的登记，往返缓存恢复时重登，被浏览器冻结 / 解冻时改冻结标记。 */
function holdOpen(): void {
  writeOpen()
  if (_openListening || typeof window === 'undefined') return
  _openListening = true
  window.addEventListener('pagehide', () => removeOwnOpen())
  window.addEventListener('pageshow', (e) => {
    if (e.persisted) writeOpen()
  })
  if (typeof document !== 'undefined') {
    document.addEventListener('freeze', () => writeOpen(true))
    document.addEventListener('resume', () => writeOpen())
  }
}

/** 回答别的标签页「谁在用编号 X」：问的是本页当前编号就答（本文档发的问题不答）。 */
function answerProbes(): void {
  if (_probeChannel || typeof BroadcastChannel === 'undefined') return
  try {
    const channel = new BroadcastChannel(PROBE_CHANNEL)
    channel.onmessage = (ev: MessageEvent) => {
      const m = ev.data as { type?: string; id?: string; from?: string } | null
      if (m?.type === 'probe' && m.from && !SAME_DOCUMENT.has(m.from) && m.id && m.id === _cached) {
        channel.postMessage({ type: 'alive', id: m.id, to: m.from, from: DOC_NONCE })
      }
    }
    // 常驻监听不该拖住进程退出：浏览器里没有 unref；Node（单测环境）的 BroadcastChannel 有
    ;(channel as BroadcastChannel & { unref?: () => void }).unref?.()
    _probeChannel = channel
  } catch {
    _probeChannel = null
  }
}

/** 有没有打开着的标签页在用编号 id。浏览器不提供 BroadcastChannel ⇒ 问不了，按「有」算（换号，第一轮口径）。 */
function someoneUses(id: string): Promise<boolean> {
  if (typeof BroadcastChannel === 'undefined') return Promise.resolve(true)
  return new Promise<boolean>((resolve) => {
    let channel: BroadcastChannel
    try {
      channel = new BroadcastChannel(PROBE_CHANNEL)
    } catch {
      resolve(true)
      return
    }
    let timer: ReturnType<typeof setTimeout> | undefined
    const finish = (inUse: boolean) => {
      if (timer !== undefined) clearTimeout(timer)
      try {
        channel.close()
      } catch {
        // ignore
      }
      resolve(inUse)
    }
    timer = setTimeout(() => finish(false), PROBE_TIMEOUT_MS)
    channel.onmessage = (ev: MessageEvent) => {
      const m = ev.data as { type?: string; id?: string; to?: string } | null
      if (m?.type === 'alive' && m.id === id && m.to === DOC_NONCE) finish(true)
    }
    try {
      channel.postMessage({ type: 'probe', id, from: DOC_NONCE })
    } catch {
      finish(true)
    }
  })
}

function wasDiscarded(): boolean {
  return typeof document !== 'undefined' && (document as Document & { wasDiscarded?: boolean }).wasDiscarded === true
}

function hasLiveOpener(): boolean {
  try {
    return typeof window !== 'undefined' && !!window.opener && !window.opener.closed
  } catch {
    return false
  }
}

/**
 * 当前窗口编号（同步）。认领完成前可能还是从别的标签页复制来的编号 ——
 * 用它取锁 / 写底稿的地方先等 {@link claimClientInstanceId}（`http.ts` 已统一处理，见 {@link isClientInstanceSettled}）。
 */
export function getClientInstanceId(): string {
  if (_cached) return _cached

  let existing: string | null = null
  let claimed: string | null = null
  try {
    existing = sessionStorage.getItem(STORAGE_KEY)
    claimed = sessionStorage.getItem(CLAIMED_KEY)
  } catch {
    // sessionStorage 不可用
  }

  const locks = webLocks()
  let id: string
  if (!existing || claimed !== existing) {
    // 全新标签页（手动输入 URL / sessionStorage 被清空），或编号没有本版认领标记：升级前打开的页面写的，
    // 可能和那个仍开着、没刷新过的旧标签页同号 ⇒ 换一次（R4）
    id = _generateAndStore()
  } else if (!locks && hasLiveOpener()) {
    // 不支持 Web Locks 且有活着的 opener（window.open 打开的新标签页复制了 sessionStorage）→ 新号
    id = _generateAndStore()
  } else {
    // 刷新 / 复制来的编号：支持 Web Locks 时由认领判定；不支持时看登记
    id = existing
  }
  _cached = id
  if (!locks) {
    answerProbes()
    const entry = wasDiscarded() ? null : readOpen(id)
    if (!entry || SAME_DOCUMENT.has(entry.n)) {
      holdOpen()
      _settled = true
    }
    // 否则登记是别的文档写的：先用着原编号、不登记，交给 claimClientInstanceId 去问
  }
  return id
}

/** 认领结果：held = 拿到并持有；taken = 另一个活着的标签页正持有；unavailable = Web Locks 出错 / 超时。 */
type HoldResult = 'held' | 'taken' | 'unavailable'

function hold(locks: LockManager, id: string): Promise<HoldResult> {
  return new Promise<HoldResult>((resolve) => {
    const timer = setTimeout(() => resolve('unavailable'), LOCK_TIMEOUT_MS)
    const settle = (result: HoldResult) => {
      clearTimeout(timer)
      resolve(result)
    }
    try {
      locks.request(`${LOCK_PREFIX}${id}`, { ifAvailable: true }, (lock) => {
        if (!lock) {
          settle('taken')
          return undefined
        }
        settle('held')
        // 回调返回的 Promise 不结束 ⇒ 锁一直持有到本页卸载（浏览器随文档销毁释放）
        return new Promise<void>(() => {})
      }).catch(() => settle('unavailable'))
    } catch {
      settle('unavailable')
    }
  })
}

/**
 * 认领本标签页的窗口编号（只做一次，之后返回同一结果）。
 * 编号被另一个活着的标签页占着（复制标签页 / window.open 复制了 sessionStorage）⇒ 换新编号再认领。
 */
export function claimClientInstanceId(): Promise<string> {
  if (_claim) return _claim
  _claim = (async () => {
    try {
      const id = getClientInstanceId()
      const locks = webLocks()
      if (!locks) {
        if (_settled) return id
        const entry = readOpen(id)
        if (entry && !SAME_DOCUMENT.has(entry.n) && (entry.f === 1 || (await someoneUses(id)))) {
          _cached = _generateAndStore()
        }
        holdOpen()
        return _cached as string
      }
      const result = await hold(locks, id)
      if (result !== 'taken') return id // held：本页独占；unavailable：保留当前编号，不误判成重复
      const fresh = _generateAndStore()
      _cached = fresh
      await hold(locks, fresh)
      return fresh
    } finally {
      _settled = true
    }
  })()
  return _claim
}

/** 编号定下来没有。没定下来时，要带编号的请求先等 {@link claimClientInstanceId}（`http.ts`，R5.4）。 */
export function isClientInstanceSettled(): boolean {
  return _settled
}

function _generateAndStore(): string {
  // crypto.randomUUID 只在安全上下文（https / localhost）有，http + 内网地址访问时没有 ⇒ 用 newUuid（自带回退）
  const id = newUuid()
  try {
    sessionStorage.setItem(STORAGE_KEY, id)
    sessionStorage.setItem(CLAIMED_KEY, id)
  } catch {
    // sessionStorage 不可用时仅在内存中保留
  }
  return id
}
