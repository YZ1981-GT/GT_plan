/**
 * 平台级**待写盘追踪器** —— 让双向桥在切「在线编辑」前 await 到 HTML 侧的全部写入。
 *
 * spec: `d2-online-edit-platform-closure` · R20（泛化自 H 循环的 `hPendingWrites.ts`，
 * 那份文件现在只是本模块的别名，两者共用**同一张**注册表）
 *
 * ═══ 修的是什么（2026-10-11 和平药房 D2-2 真栈实测）═══════════════════════════
 *
 * 切「在线编辑」时桥先调宿主 `flushHtml`，宿主再读 store-projection 交给 materialize。
 * 宿主的 `formData.flushPendingSave()` 只管它**自己**那层防抖；而 D 循环这类宿主的子 Tab
 * 各自 new 一个 composable，里面还有一层**私有** 2s 防抖（`useD2Detail` 的 `debounceTimer`），
 * 宿主拿不到。于是「改一格 → 2 秒内点在线编辑」：
 *
 *   ① store-projection 读到的是**旧** store（网络序：GET store-projection 早于那次 PUT）；
 *   ② OO 里打开的是旧值；
 *   ③ 防抖随后照常落库 —— store 已是新值，但 OO 不知道；
 *   ④ OO 保存回来时三方合并以旧值为 base，镜像把旧值（或清空）写回 store ⇒ **HTML 侧那次
 *      编辑被静默覆盖**，用户毫无提示。
 *
 * ═══ 两类写入各一种登记方式，桥只调一个 `flushPendingWrites()` ═══════════════════
 *
 * * **防抖型**（子 composable 自己的 setTimeout）：`registerPendingFlusher(fn)`，`fn` 的语义是
 *   「有挂起的防抖就清掉并立即发起写入」。
 * * **在途型**（已发出但未返回的 PUT）：`trackPendingWrite(promise)`。宿主把注入给子 Tab 的
 *   保存函数包一层即可覆盖它下面的全部子 composable。
 *
 * 桥在每次 `flushHtml` 之前调用 `flushPendingWrites()`（`useWorkpaperSyncBridge`），所以任何
 * 宿主只要它的写入方登记过，就自动生效，不必逐个宿主改 `flushHtml`。
 *
 * ═══ 生命周期 ═══════════════════════════════════════════════════════════════
 *
 * 登记走 `onScopeDispose` 自动注销（Tab 卸载后不留悬挂的 flusher —— 留了会对已销毁的实例
 * 调用）。**不在 effect scope 里**调用时不登记：生产里 composable 恒在组件 setup 内，scope
 * 外只会是脱离组件直接调用 composable 的单测，那里没有可以注销它的时机。
 */
import { getCurrentScope, onScopeDispose } from 'vue'

/** 防抖型写入方的 flush 函数（调用即「清防抖 + 立即发起写入」）。 */
export type PendingWriteFlusher = () => Promise<void> | void

const _flushers = new Set<PendingWriteFlusher>()
const _inFlight = new Set<Promise<unknown>>()

/**
 * 登记一个防抖型写入方的 flush 函数。在 composable / 组件 setup 内调用；当前 effect scope
 * 销毁时自动注销。scope 外调用不登记（见模块 docstring）。
 */
export function registerPendingFlusher(flush: PendingWriteFlusher): void {
  if (!getCurrentScope()) return
  _flushers.add(flush)
  onScopeDispose(() => {
    _flushers.delete(flush)
  })
}

/**
 * 追踪一次**已发起**的写入 promise —— 返回同一个 promise，调用方写法不变。
 *
 * 🔴 失败不吞也不抛：写入失败由调用方自己的 catch 报；这里只保证 `flushPendingWrites()`
 * 不会因为一次失败的写入而整体 reject（否则一个 500 会把「在线编辑」按钮变成死键）。
 */
export function trackPendingWrite<T>(promise: Promise<T>): Promise<T> {
  const settled = promise.catch(() => undefined)
  _inFlight.add(settled)
  void settled.finally(() => {
    _inFlight.delete(settled)
  })
  return promise
}

/**
 * 等所有已登记的待写盘完成 —— 双向桥 `flushHtml` 之前的那一步。无待写盘时零请求空转。
 *
 * 🔴 两类都要走：只等在途会漏掉还在防抖窗口里的那批；只调 flusher 会漏掉已发出未返回的那次。
 * flusher 同步发起的写入（经宿主的 `trackPendingWrite`）在第一步之后已进在途集合，第二步一并等到。
 */
export async function flushPendingWrites(): Promise<void> {
  await Promise.all([..._flushers].map(async (flush) => {
    try {
      await flush()
    } catch {
      // 单个写入方失败不阻断其余写入方，也不阻断切换（失败由写入方自己提示）
    }
  }))
  while (_inFlight.size > 0) {
    await Promise.all([..._inFlight])
  }
}

/** 仅供测试：当前登记数（生产代码不要依赖）。 */
export function _pendingWriteCounts(): { flushers: number; inFlight: number } {
  return { flushers: _flushers.size, inFlight: _inFlight.size }
}
