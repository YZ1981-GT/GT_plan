/**
 * 窗口编号认领（spec workpaper-multi-window-lock-gaps R1 / R4 / R5）。
 *
 * 浏览器「复制标签页」把 sessionStorage 原样复制、且没有 opener：原先新标签页沿用原编号，
 * 编辑锁把两个窗口当成一个，同一底稿两边都能编辑。认领用 Web Locks：编号被另一个活着的标签页占着就换新号。
 * 假 LockManager 用一张共享锁表模拟同源的多个标签页；`vi.resetModules()` 后重新导入 = 新文档（新标签页 / 刷新后的页面）。
 * 编号没有本版认领标记 ⇒ 升级前的页面写的，换一次号（R4）。
 * 不支持 Web Locks（http + 内网地址访问不是安全上下文）一组：localStorage 登记打开着的编号；登记是别的文档写的就在
 * BroadcastChannel 上问（假频道：每个用例一条新总线，先前用例的模块实例收不到），1.5 秒没人答认回原编号（R5）。
 * 先前用例加载的模块实例还挂着页面隐藏 / 显示监听，各用例编号互不相同。
 */
import { webcrypto } from 'node:crypto'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const KEY = 'gt-client-instance-id'
const CLAIMED = 'gt-client-instance-claimed'
const LOCK = (id: string) => `gt-client-instance:${id}`
const OPEN = (id: string) => `gt-client-instance-open:${id}`
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

function fakeLocks(held: Set<string>, opts: { reject?: boolean; never?: boolean } = {}) {
  return {
    request: vi.fn((name: string, _options: unknown, cb: (lock: unknown) => unknown) => {
      if (opts.reject) return Promise.reject(new DOMException('denied', 'SecurityError'))
      if (opts.never) return new Promise(() => {})
      if (held.has(name)) return Promise.resolve(cb(null))
      held.add(name)
      return Promise.resolve(cb({ name, mode: 'exclusive' }))
    }),
  }
}

/** 同源标签页之间的广播：每个用例一条新总线；消息异步送达同名的其他频道（不送回发送方）。 */
class FakeBroadcastChannel {
  static bus = new Map<string, Set<FakeBroadcastChannel>>()
  static sent: unknown[] = []
  onmessage: ((ev: MessageEvent) => void) | null = null
  closed = false
  private readonly bus: Map<string, Set<FakeBroadcastChannel>>

  constructor(readonly name: string) {
    this.bus = FakeBroadcastChannel.bus
    if (!this.bus.has(name)) this.bus.set(name, new Set())
    this.bus.get(name)!.add(this)
  }

  postMessage(data: unknown) {
    if (this.closed) throw new DOMException('closed', 'InvalidStateError')
    FakeBroadcastChannel.sent.push(data)
    for (const other of this.bus.get(this.name) ?? []) {
      if (other !== this && !other.closed) queueMicrotask(() => other.onmessage?.({ data } as MessageEvent))
    }
  }

  close() {
    this.closed = true
    this.bus.get(this.name)?.delete(this)
  }
}

let uuidSeq = 0
/** 本模块在同一全局对象（= 同一文档）里加载过的实例登记在这里；删掉它 = 下一次加载是另一个文档 */
const SAME_DOCUMENT_KEY = Symbol.for('gt-client-instance-docs')

/** 新文档（新标签页 / 刷新后的页面）加载本模块 */
async function load() {
  delete (globalThis as Record<symbol, unknown>)[SAME_DOCUMENT_KEY]
  vi.resetModules()
  return import('@/utils/clientInstance')
}

/** 同一文档里重新加载本模块（开发热更新 / 单测重载模块） */
async function reloadModuleInSameDocument() {
  vi.resetModules()
  return import('@/utils/clientInstance')
}

/** 本版代码定下过编号的标签页（sessionStorage 有编号且有认领标记） */
function seedTab(id: string) {
  sessionStorage.setItem(KEY, id)
  sessionStorage.setItem(CLAIMED, id)
}

function setLocks(locks: unknown) {
  Object.defineProperty(navigator, 'locks', { value: locks, configurable: true })
}

function setOpener(opener: unknown) {
  Object.defineProperty(window, 'opener', { value: opener, configurable: true, writable: true })
}

function pageTransition(type: 'pagehide' | 'pageshow', persisted: boolean) {
  const e = new Event(type)
  Object.defineProperty(e, 'persisted', { value: persisted })
  window.dispatchEvent(e)
}

function openEntry(id: string): { n: string; t: number; f?: number } | null {
  const raw = localStorage.getItem(OPEN(id))
  return raw == null ? null : JSON.parse(raw)
}

beforeEach(() => {
  sessionStorage.clear()
  localStorage.clear()
  uuidSeq = 0
  FakeBroadcastChannel.bus = new Map()
  FakeBroadcastChannel.sent = []
  vi.stubGlobal('BroadcastChannel', FakeBroadcastChannel)
  vi.spyOn(crypto, 'randomUUID').mockImplementation(() => `fresh-${++uuidSeq}` as `${string}-${string}-${string}-${string}-${string}`)
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  setLocks(undefined)
  setOpener(null)
  delete (document as Document & { wasDiscarded?: boolean }).wasDiscarded
})

describe('claimClientInstanceId（支持 Web Locks）', () => {
  it('复制标签页：编号被原标签页占着 ⇒ 换新号并写回 sessionStorage（连同认领标记）', async () => {
    seedTab('copied')
    const held = new Set([LOCK('copied')]) // 原标签页持有
    setLocks(fakeLocks(held))
    const mod = await load()

    const id = await mod.claimClientInstanceId()

    expect(id).toBe('fresh-1')
    expect(mod.getClientInstanceId()).toBe('fresh-1')
    expect(sessionStorage.getItem(KEY)).toBe('fresh-1')
    expect(sessionStorage.getItem(CLAIMED)).toBe('fresh-1')
    expect(held.has(LOCK('fresh-1'))).toBe(true)
  })

  it('刷新：编号没被别人占着 ⇒ 认领回原编号（编辑锁心跳不断）', async () => {
    seedTab('mine')
    const held = new Set<string>()
    setLocks(fakeLocks(held))
    const mod = await load()

    expect(await mod.claimClientInstanceId()).toBe('mine')
    expect(held).toEqual(new Set([LOCK('mine')]))
    expect(sessionStorage.getItem(KEY)).toBe('mine')
  })

  it('升级前打开的页面写的编号（没有认领标记）：换一次新号，之后刷新保留（R4）', async () => {
    // 旧代码不认领 Web Lock：从没刷新过的旧标签页复制出来时，锁表里查不到旧标签页，只能靠标记分辨
    sessionStorage.setItem(KEY, 'from-old-tab')
    const held = new Set<string>()
    setLocks(fakeLocks(held))
    const first = await load()
    expect(await first.claimClientInstanceId()).toBe('fresh-1')
    expect(sessionStorage.getItem(CLAIMED)).toBe('fresh-1')
    expect(held.has(LOCK('from-old-tab'))).toBe(false)

    held.clear() // 刷新：旧文档卸载，锁随之释放
    expect(await (await load()).claimClientInstanceId()).toBe('fresh-1')
  })

  it('认领标记与编号对不上：同样按升级前的编号处理', async () => {
    sessionStorage.setItem(KEY, 'id-a')
    sessionStorage.setItem(CLAIMED, 'id-b')
    setLocks(fakeLocks(new Set()))
    expect(await (await load()).claimClientInstanceId()).toBe('fresh-1')
  })

  it('支持 Web Locks 时有 opener 也交给认领判定：opener 没占着就保留，占着才换', async () => {
    setOpener({ closed: false })
    seedTab('from-opener')
    setLocks(fakeLocks(new Set()))
    expect(await (await load()).claimClientInstanceId()).toBe('from-opener')

    seedTab('from-opener')
    setLocks(fakeLocks(new Set([LOCK('from-opener')])))
    expect(await (await load()).claimClientInstanceId()).toBe('fresh-1')
  })

  it('Web Locks 请求被拒：保留当前编号，不误判成复制', async () => {
    seedTab('mine')
    setLocks(fakeLocks(new Set(), { reject: true }))
    const mod = await load()
    expect(await mod.claimClientInstanceId()).toBe('mine')
  })

  it('Web Locks 迟迟不回调：3 秒后按不可用保留当前编号，写请求不会一直等', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    seedTab('slow')
    setLocks(fakeLocks(new Set(), { never: true }))
    const mod = await load()
    const claim = mod.claimClientInstanceId()
    expect(mod.isClientInstanceSettled()).toBe(false)
    await vi.advanceTimersByTimeAsync(3000)
    expect(await claim).toBe('slow')
    expect(mod.isClientInstanceSettled()).toBe(true)
  })

  it('只认领一次：多次调用同一个结果，锁只请求一次；认领前未定、认领后已定', async () => {
    seedTab('mine')
    const locks = fakeLocks(new Set())
    setLocks(locks)
    const mod = await load()
    expect(mod.isClientInstanceSettled()).toBe(false)
    const [a, b] = await Promise.all([mod.claimClientInstanceId(), mod.claimClientInstanceId()])
    expect(a).toBe('mine')
    expect(b).toBe('mine')
    expect(locks.request).toHaveBeenCalledTimes(1)
    expect(mod.isClientInstanceSettled()).toBe(true)
  })

  it('全新标签页（sessionStorage 为空）：生成编号并认领', async () => {
    const held = new Set<string>()
    setLocks(fakeLocks(held))
    const mod = await load()
    expect(await mod.claimClientInstanceId()).toBe('fresh-1')
    expect(held.has(LOCK('fresh-1'))).toBe(true)
  })
})

describe('不支持 Web Locks（http + 内网地址访问不是安全上下文）', () => {
  beforeEach(() => setLocks(undefined))

  it('生成编号不依赖 crypto.randomUUID：形如 UUID，写进 sessionStorage 并登记为本文档打开着', async () => {
    // 非安全上下文没有 crypto.randomUUID（只有 getRandomValues）：原先生成编号直接抛 TypeError，写请求全部发不出去
    vi.stubGlobal('crypto', { getRandomValues: <T extends ArrayBufferView>(a: T) => webcrypto.getRandomValues(a as any) as T })
    const mod = await load()

    const id = mod.getClientInstanceId()

    expect(id).toMatch(UUID_V4)
    expect(sessionStorage.getItem(KEY)).toBe(id)
    expect(openEntry(id)?.n).toBeTruthy()
    expect(mod.isClientInstanceSettled()).toBe(true) // 没人登记过：同步定下，请求不用等
    expect(await mod.claimClientInstanceId()).toBe(id)
  })

  it('复制标签页：原标签页打开着、回答询问 ⇒ 换新号，原标签页的登记不动', async () => {
    seedTab('ns-copied')
    const tabA = await load()
    expect(tabA.getClientInstanceId()).toBe('ns-copied')
    const entryA = openEntry('ns-copied')

    const tabB = await load() // 复制标签页：sessionStorage 原样复制过来
    expect(await tabB.claimClientInstanceId()).toBe('fresh-1')
    expect(sessionStorage.getItem(KEY)).toBe('fresh-1')
    expect(openEntry('ns-copied')).toEqual(entryA)
    expect(openEntry('fresh-1')?.n).toBeTruthy()
    expect(openEntry('fresh-1')?.n).not.toBe(entryA?.n)
  })

  it('崩溃后重开：登记是崩溃前的本页留下的，1.5 秒没人回答 ⇒ 认回原编号并改登记为本文档（R5）', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    seedTab('ns-crashed')
    localStorage.setItem(OPEN('ns-crashed'), JSON.stringify({ n: 'crashed-doc', t: 1 })) // 崩溃来不及注销
    const mod = await load()

    expect(mod.getClientInstanceId()).toBe('ns-crashed')
    expect(mod.isClientInstanceSettled()).toBe(false) // 还在问：写请求先等
    const claim = mod.claimClientInstanceId()
    await vi.advanceTimersByTimeAsync(1499)
    expect(mod.isClientInstanceSettled()).toBe(false)
    await vi.advanceTimersByTimeAsync(1)
    expect(await claim).toBe('ns-crashed')
    expect(mod.isClientInstanceSettled()).toBe(true)
    expect(openEntry('ns-crashed')?.n).not.toBe('crashed-doc')
    expect(FakeBroadcastChannel.sent).toContainEqual(expect.objectContaining({ type: 'probe', id: 'ns-crashed' }))
  })

  it('第一轮的纯时间戳登记：按别的文档的登记处理（问；没人答就认回）', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    seedTab('ns-legacy')
    localStorage.setItem(OPEN('ns-legacy'), '1730000000000')
    const mod = await load()
    const claim = mod.claimClientInstanceId()
    await vi.advanceTimersByTimeAsync(1500)
    expect(await claim).toBe('ns-legacy')
  })

  it('登记标着被浏览器冻结：冻结的标签页答不了询问 ⇒ 不问，直接换号', async () => {
    seedTab('ns-frozen')
    localStorage.setItem(OPEN('ns-frozen'), JSON.stringify({ n: 'frozen-doc', t: 1, f: 1 }))
    const mod = await load()
    expect(await mod.claimClientInstanceId()).toBe('fresh-1')
    expect(FakeBroadcastChannel.sent).toEqual([])
    expect(openEntry('ns-frozen')).toEqual({ n: 'frozen-doc', t: 1, f: 1 })
  })

  it('浏览器不提供 BroadcastChannel：问不了 ⇒ 按第一轮口径换号', async () => {
    vi.stubGlobal('BroadcastChannel', undefined)
    seedTab('ns-nobc')
    localStorage.setItem(OPEN('ns-nobc'), JSON.stringify({ n: 'other-doc', t: 1 }))
    expect(await (await load()).claimClientInstanceId()).toBe('fresh-1')
  })

  it('打开着的标签页只回答对自己当前编号的询问，不答别的编号、不答自己发的', async () => {
    seedTab('ns-answer')
    const tab = await load()
    tab.getClientInstanceId()
    const asker = new FakeBroadcastChannel('gt-client-instance-probe')
    const got: unknown[] = []
    asker.onmessage = (ev) => got.push(ev.data)

    asker.postMessage({ type: 'probe', id: 'ns-answer', from: 'doc-x' })
    asker.postMessage({ type: 'probe', id: 'someone-else', from: 'doc-x' })
    await new Promise((r) => setTimeout(r, 0))
    expect(got).toEqual([expect.objectContaining({ type: 'alive', id: 'ns-answer', to: 'doc-x' })])
  })

  it('刷新：旧文档隐藏时已注销登记 ⇒ 认回原编号并重新登记，不用问', async () => {
    seedTab('ns-reload')
    const mod = await load()

    expect(await mod.claimClientInstanceId()).toBe('ns-reload')
    expect(openEntry('ns-reload')?.n).toBeTruthy()
    expect(FakeBroadcastChannel.sent).toEqual([])
  })

  it('页面隐藏只注销本文档的登记；从往返缓存恢复时重新登记；冻结 / 解冻改冻结标记', async () => {
    seedTab('ns-hide')
    const before = await load()
    expect(before.getClientInstanceId()).toBe('ns-hide')
    expect(openEntry('ns-hide')?.f).toBeUndefined()

    document.dispatchEvent(new Event('freeze'))
    expect(openEntry('ns-hide')?.f).toBe(1)
    document.dispatchEvent(new Event('resume'))
    expect(openEntry('ns-hide')?.f).toBeUndefined()

    pageTransition('pagehide', true)
    expect(localStorage.getItem(OPEN('ns-hide'))).toBeNull()
    pageTransition('pageshow', true)
    expect(localStorage.getItem(OPEN('ns-hide'))).not.toBeNull()

    localStorage.setItem(OPEN('ns-hide'), JSON.stringify({ n: 'another-doc', t: 1 }))
    pageTransition('pagehide', false) // 登记已不是本文档的：不删别人的
    expect(openEntry('ns-hide')?.n).toBe('another-doc')
    localStorage.removeItem(OPEN('ns-hide'))
    expect(await (await load()).claimClientInstanceId()).toBe('ns-hide')
  })

  it('被浏览器丢弃（省内存）后重新加载：登记是本页自己留下的 ⇒ 认回原编号，不用问', async () => {
    seedTab('ns-discarded')
    localStorage.setItem(OPEN('ns-discarded'), JSON.stringify({ n: 'before-discard', t: 1 }))
    Object.defineProperty(document, 'wasDiscarded', { value: true, configurable: true })

    expect(await (await load()).claimClientInstanceId()).toBe('ns-discarded')
    expect(FakeBroadcastChannel.sent).toEqual([])
  })

  it('有活着的 opener（window.open 复制了 sessionStorage）⇒ 换新号；没有 opener 就复用', async () => {
    seedTab('ns-opened')
    setOpener({ closed: false })
    expect(await (await load()).claimClientInstanceId()).toBe('fresh-1')

    seedTab('ns-own')
    setOpener(null)
    expect(await (await load()).claimClientInstanceId()).toBe('ns-own')
  })

  it('localStorage 读写抛错：不抛出，退回 opener 判断', async () => {
    const realGet = Storage.prototype.getItem
    const realSet = Storage.prototype.setItem
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(function (this: Storage, k: string) {
      if (k.startsWith('gt-client-instance-open:')) throw new DOMException('denied', 'SecurityError')
      return realGet.call(this, k)
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(function (this: Storage, k: string, v: string) {
      if (k.startsWith('gt-client-instance-open:')) throw new DOMException('quota', 'QuotaExceededError')
      return realSet.call(this, k, v)
    })

    seedTab('ns-nols')
    expect(await (await load()).claimClientInstanceId()).toBe('ns-nols')

    seedTab('ns-nols')
    setOpener({ closed: false })
    expect(await (await load()).claimClientInstanceId()).toBe('fresh-1')
  })
})
