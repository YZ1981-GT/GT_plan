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
 * 浏览器不提供 Web Locks 时（用 http + 内网地址访问不是安全上下文，`navigator.locks` 与 `crypto.randomUUID` 都没有，
 * 2026-10-31 实测）：打开着的标签页把编号登记在 localStorage，页面隐藏（刷新 / 关闭 / 离开）时注销；读到自己的编号
 * 已被登记 ⇒ 另一个打开着的标签页在用 ⇒ 换新编号。另外仍按原先的 opener 判断（localStorage 不可用时只剩它）。
 * 页面崩溃来不及注销 ⇒ 重新加载时多换一次号（不会两窗共用；崩溃前在编辑的话要等原来的编辑锁过期）；
 * 被浏览器丢弃（省内存）后重新加载时认回原编号。
 *
 * spec: multi-window-ledger-workbench Phase 2 Task 8 + 复盘 P0-1 修复；workpaper-multi-window-lock-gaps R1
 */
import { newUuid } from './uuid'

const STORAGE_KEY = 'gt-client-instance-id'
const LOCK_PREFIX = 'gt-client-instance:'
/** 不支持 Web Locks 时打开着的标签页的编号登记（localStorage，值为登记时间） */
const OPEN_PREFIX = 'gt-client-instance-open:'

let _cached: string | null = null
let _claim: Promise<string> | null = null
let _openListening = false

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

/** 编号已被另一个打开着的标签页登记。被浏览器丢弃后重新加载时，登记是本页被丢弃前自己留下的，不算。 */
function openElsewhere(id: string): boolean {
  if (typeof document !== 'undefined' && (document as Document & { wasDiscarded?: boolean }).wasDiscarded) return false
  try {
    return openRegistry()?.getItem(OPEN_PREFIX + id) != null
  } catch {
    return false
  }
}

/** 登记本页编号；页面隐藏时注销（刷新后的新文档才能认回原编号），从往返缓存恢复时重新登记。 */
function holdOpen(): void {
  const mark = () => {
    try {
      if (_cached) openRegistry()?.setItem(OPEN_PREFIX + _cached, String(Date.now()))
    } catch {
      // 写不进：只剩 opener 判断
    }
  }
  mark()
  if (_openListening || typeof window === 'undefined') return
  _openListening = true
  window.addEventListener('pagehide', () => {
    try {
      if (_cached) openRegistry()?.removeItem(OPEN_PREFIX + _cached)
    } catch {
      // ignore
    }
  })
  window.addEventListener('pageshow', (e) => {
    if (e.persisted) mark()
  })
}

/**
 * 当前窗口编号（同步）。认领完成前可能还是从别的标签页复制来的编号 ——
 * 用它取锁 / 写底稿的地方先等 {@link claimClientInstanceId}。
 */
export function getClientInstanceId(): string {
  if (_cached) return _cached

  // 1. 尝试从 sessionStorage 读取已有的 ID
  let existing: string | null = null
  try {
    existing = sessionStorage.getItem(STORAGE_KEY)
  } catch {
    // sessionStorage 不可用
  }

  const locks = webLocks()
  let id: string
  if (!existing) {
    // sessionStorage 里没有 ID → 全新标签页（手动输入 URL / sessionStorage 被清空）
    id = _generateAndStore()
  } else if (!locks && (openElsewhere(existing) || (window.opener && !window.opener.closed))) {
    // 不支持 Web Locks：编号已被另一个打开着的标签页登记（复制标签页），或有活跃的 opener（window.open 打开的新标签页）
    // → 生成新 ID（刷新时本页旧文档已注销登记；opener 关闭后 window.opener.closed=true，都走下面的复用路径）
    id = _generateAndStore()
  } else {
    // 刷新 / 复制来的编号：支持 Web Locks 时由认领判定是否被别的标签页占着
    id = existing
  }
  _cached = id
  if (!locks) holdOpen()

  return id
}

/** 认领结果：held = 拿到并持有；taken = 另一个活着的标签页正持有；unavailable = Web Locks 出错。 */
type HoldResult = 'held' | 'taken' | 'unavailable'

function hold(locks: LockManager, id: string): Promise<HoldResult> {
  return new Promise<HoldResult>((resolve) => {
    try {
      locks.request(`${LOCK_PREFIX}${id}`, { ifAvailable: true }, (lock) => {
        if (!lock) {
          resolve('taken')
          return undefined
        }
        resolve('held')
        // 回调返回的 Promise 不结束 ⇒ 锁一直持有到本页卸载（浏览器随文档销毁释放）
        return new Promise<void>(() => {})
      }).catch(() => resolve('unavailable'))
    } catch {
      resolve('unavailable')
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
    const id = getClientInstanceId()
    const locks = webLocks()
    if (!locks) return id
    const result = await hold(locks, id)
    if (result !== 'taken') return id // held：本页独占；unavailable：保留当前编号，不误判成重复
    const fresh = _generateAndStore()
    _cached = fresh
    await hold(locks, fresh)
    return fresh
  })()
  return _claim
}

function _generateAndStore(): string {
  // crypto.randomUUID 只在安全上下文（https / localhost）有，http + 内网地址访问时没有 ⇒ 用 newUuid（自带回退）
  const id = newUuid()
  try {
    sessionStorage.setItem(STORAGE_KEY, id)
  } catch {
    // sessionStorage 不可用时仅在内存中保留
  }
  return id
}
