/**
 * 窗口编号认领（spec workpaper-multi-window-lock-gaps R1）。
 *
 * 浏览器「复制标签页」把 sessionStorage 原样复制、且没有 opener：原先新标签页沿用原编号，
 * 编辑锁把两个窗口当成一个，同一底稿两边都能编辑。认领用 Web Locks：编号被另一个活着的标签页占着就换新号。
 * 假 LockManager 用一张共享锁表模拟同源的多个标签页。
 * 不支持 Web Locks（http + 内网地址访问不是安全上下文）一组：localStorage 登记打开着的编号；各用例编号互不相同，
 * 先前用例加载的模块实例也挂着页面隐藏 / 显示监听，同号会互相改登记。
 */
import { webcrypto } from 'node:crypto'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const KEY = 'gt-client-instance-id'
const LOCK = (id: string) => `gt-client-instance:${id}`
const OPEN = (id: string) => `gt-client-instance-open:${id}`
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

function fakeLocks(held: Set<string>, opts: { reject?: boolean } = {}) {
  return {
    request: vi.fn((name: string, _options: unknown, cb: (lock: unknown) => unknown) => {
      if (opts.reject) return Promise.reject(new DOMException('denied', 'SecurityError'))
      if (held.has(name)) return Promise.resolve(cb(null))
      held.add(name)
      return Promise.resolve(cb({ name, mode: 'exclusive' }))
    }),
  }
}

let uuidSeq = 0
async function load() {
  vi.resetModules()
  return import('@/utils/clientInstance')
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

beforeEach(() => {
  sessionStorage.clear()
  localStorage.clear()
  uuidSeq = 0
  vi.spyOn(crypto, 'randomUUID').mockImplementation(() => `fresh-${++uuidSeq}` as `${string}-${string}-${string}-${string}-${string}`)
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  setLocks(undefined)
  setOpener(null)
  delete (document as Document & { wasDiscarded?: boolean }).wasDiscarded
})

describe('claimClientInstanceId', () => {
  it('复制标签页：编号被原标签页占着 ⇒ 换新号并写回 sessionStorage', async () => {
    sessionStorage.setItem(KEY, 'copied')
    const held = new Set([LOCK('copied')]) // 原标签页持有
    setLocks(fakeLocks(held))
    const mod = await load()

    const id = await mod.claimClientInstanceId()

    expect(id).toBe('fresh-1')
    expect(mod.getClientInstanceId()).toBe('fresh-1')
    expect(sessionStorage.getItem(KEY)).toBe('fresh-1')
    expect(held.has(LOCK('fresh-1'))).toBe(true)
  })

  it('刷新：编号没被别人占着 ⇒ 认领回原编号（编辑锁心跳不断）', async () => {
    sessionStorage.setItem(KEY, 'mine')
    const held = new Set<string>()
    setLocks(fakeLocks(held))
    const mod = await load()

    expect(await mod.claimClientInstanceId()).toBe('mine')
    expect(held).toEqual(new Set([LOCK('mine')]))
    expect(sessionStorage.getItem(KEY)).toBe('mine')
  })

  it('支持 Web Locks 时有 opener 也交给认领判定：opener 没占着就保留，占着才换', async () => {
    setOpener({ closed: false })
    sessionStorage.setItem(KEY, 'from-opener')
    setLocks(fakeLocks(new Set()))
    expect(await (await load()).claimClientInstanceId()).toBe('from-opener')

    sessionStorage.setItem(KEY, 'from-opener')
    setLocks(fakeLocks(new Set([LOCK('from-opener')])))
    expect(await (await load()).claimClientInstanceId()).toBe('fresh-1')
  })

  it('不支持 Web Locks：保持原 opener 判断（有活着的 opener 换新，没有就复用）', async () => {
    sessionStorage.setItem(KEY, 'copied')
    setOpener({ closed: false })
    expect(await (await load()).claimClientInstanceId()).toBe('fresh-1')

    sessionStorage.setItem(KEY, 'reload')
    setOpener(null)
    expect(await (await load()).claimClientInstanceId()).toBe('reload')
  })

  it('Web Locks 请求被拒：保留当前编号，不误判成复制', async () => {
    sessionStorage.setItem(KEY, 'mine')
    setLocks(fakeLocks(new Set(), { reject: true }))
    const mod = await load()
    expect(await mod.claimClientInstanceId()).toBe('mine')
  })

  it('只认领一次：多次调用同一个结果，锁只请求一次', async () => {
    sessionStorage.setItem(KEY, 'mine')
    const locks = fakeLocks(new Set())
    setLocks(locks)
    const mod = await load()
    const [a, b] = await Promise.all([mod.claimClientInstanceId(), mod.claimClientInstanceId()])
    expect(a).toBe('mine')
    expect(b).toBe('mine')
    expect(locks.request).toHaveBeenCalledTimes(1)
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

  it('生成编号不依赖 crypto.randomUUID：形如 UUID，写进 sessionStorage 并登记为打开着', async () => {
    // 非安全上下文没有 crypto.randomUUID（只有 getRandomValues）：原先生成编号直接抛 TypeError，写请求全部发不出去
    vi.stubGlobal('crypto', { getRandomValues: <T extends ArrayBufferView>(a: T) => webcrypto.getRandomValues(a as any) as T })
    const mod = await load()

    const id = mod.getClientInstanceId()

    expect(id).toMatch(UUID_V4)
    expect(sessionStorage.getItem(KEY)).toBe(id)
    expect(localStorage.getItem(OPEN(id))).not.toBeNull()
    expect(await mod.claimClientInstanceId()).toBe(id)
  })

  it('复制标签页：编号已被另一个打开着的标签页登记 ⇒ 换新号，原标签页的登记不动', async () => {
    sessionStorage.setItem(KEY, 'ns-copied')
    localStorage.setItem(OPEN('ns-copied'), '1') // 原标签页登记的
    const mod = await load()

    expect(await mod.claimClientInstanceId()).toBe('fresh-1')
    expect(sessionStorage.getItem(KEY)).toBe('fresh-1')
    expect(localStorage.getItem(OPEN('ns-copied'))).toBe('1')
    expect(localStorage.getItem(OPEN('fresh-1'))).not.toBeNull()
  })

  it('刷新：旧文档隐藏时已注销登记 ⇒ 认回原编号并重新登记', async () => {
    sessionStorage.setItem(KEY, 'ns-reload')
    const mod = await load()

    expect(await mod.claimClientInstanceId()).toBe('ns-reload')
    expect(localStorage.getItem(OPEN('ns-reload'))).not.toBeNull()
  })

  it('页面隐藏注销登记、新文档认回原编号；从往返缓存恢复时重新登记', async () => {
    sessionStorage.setItem(KEY, 'ns-hide')
    const before = await load()
    expect(before.getClientInstanceId()).toBe('ns-hide')
    expect(localStorage.getItem(OPEN('ns-hide'))).not.toBeNull()

    pageTransition('pagehide', true)
    expect(localStorage.getItem(OPEN('ns-hide'))).toBeNull()
    pageTransition('pageshow', true)
    expect(localStorage.getItem(OPEN('ns-hide'))).not.toBeNull()

    pageTransition('pagehide', false) // 刷新：旧文档隐藏
    expect(localStorage.getItem(OPEN('ns-hide'))).toBeNull()
    expect(await (await load()).claimClientInstanceId()).toBe('ns-hide')
  })

  it('被浏览器丢弃（省内存）后重新加载：登记是本页自己留下的 ⇒ 认回原编号', async () => {
    sessionStorage.setItem(KEY, 'ns-discarded')
    localStorage.setItem(OPEN('ns-discarded'), '1')
    Object.defineProperty(document, 'wasDiscarded', { value: true, configurable: true })

    expect(await (await load()).claimClientInstanceId()).toBe('ns-discarded')
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

    sessionStorage.setItem(KEY, 'ns-nols')
    expect(await (await load()).claimClientInstanceId()).toBe('ns-nols')

    sessionStorage.setItem(KEY, 'ns-nols')
    setOpener({ closed: false })
    expect(await (await load()).claimClientInstanceId()).toBe('fresh-1')
  })
})
