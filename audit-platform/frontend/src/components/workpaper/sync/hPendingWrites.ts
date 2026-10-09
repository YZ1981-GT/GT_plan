/**
 * H 循环 `per_tab_*` 载体族的**待写盘追踪器** —— 让宿主层的双向桥能 await 子 Tab 的写入。
 *
 * spec: `h3-h5-h7-variant-axis-and-dynamic-column-paradigm`
 *
 * ═══ 为什么需要它（HD-1 的两个载体族天生够不到宿主）═══════════════════════════
 *
 * 双向桥切「在线编辑」前必须确认 HTML 侧**已落库**，否则 materialize 出的 xlsx 会少掉
 * 还在客户端的那批编辑（静默丢数据）。H2/H9 的写入在宿主里（`flushPendingSaves` 直接
 * 拿得到），H3 的写在宿主级 `useH3FormData`（导出 flush 即可）。
 *
 * 但 H5/H7 的载体在**子 Tab 里各自 new 一份**，宿主拿不到：
 *
 *   · **H5（`per_tab_formdata_instance`）**：`H5TabDetail.vue` 自己
 *     `useH5FormData({...})` 一个实例，`debouncedSave` 有 **2s** 窗口。宿主没有这个实例的
 *     引用 ⇒ 无从 flush。
 *   · **H7（`per_tab_self_persisting`）**：`H7TabDetailCost/Fair.vue` 直接
 *     `void persist(...)` → `await api.put(...)`，**没有防抖**但 promise 被 `void` 丢掉
 *     ⇒ 最后一次 PUT 可能仍在飞，宿主无从 await。
 *
 * ⇒ 两族各需要一种登记方式，宿主只调一个 `flushHPendingWrites()`。
 *
 * ═══ 🔴 为什么不改成「把载体提到宿主层」 ═══════════════════════════════════════
 *
 * 那是正解，但代价是重写 H5/H7 的整套 Tab 数据流（H5 有 19 张子表、H7 有 24 张），
 * 且会与并发会话在这些文件上的改动正面冲突。本模块是**接桥所需的最小增量**：
 * 两族各加一行登记，宿主得到一个真实的 await 点。载体上提登记为后续任务。
 *
 * ═══ 生命周期 ═══════════════════════════════════════════════════════════════
 *
 * 登记走 `onScopeDispose` 自动注销 —— Tab 卸载后不会留下悬挂的 flusher
 * （留了会在下次切换时对已销毁的实例调用，报 `Cannot read properties of null`）。
 */
import { onScopeDispose } from 'vue'

/** 防抖型载体的 flush 函数（调用即「清防抖 + 落库 + await 到写完」）。 */
export type HPendingFlusher = () => Promise<void>

const _flushers = new Set<HPendingFlusher>()
const _inFlight = new Set<Promise<unknown>>()

/**
 * 登记一个防抖型载体的 flush 函数（H5 的 `useH5FormData` 用）。
 *
 * 在 composable 内调用；当前 effect scope 销毁时自动注销。
 */
export function registerHPendingFlusher(flush: HPendingFlusher): void {
  _flushers.add(flush)
  onScopeDispose(() => {
    _flushers.delete(flush)
  })
}

/**
 * 追踪一次**立即写入**的 promise（H7 的 Tab `persist()` 用）。
 *
 * 用法是把原本 `void persist(...)` 改成 `trackHPendingWrite(persist(...))` ——
 * 返回同一个 promise，调用方的写法不变，只是桥这边多了一个 await 点。
 *
 * 🔴 失败不吞也不抛：写入失败由调用方自己的 catch 报（Tab 里已有）；这里只负责
 * 「不让 `flushHPendingWrites()` 因为一次失败的写入而整体 reject」——
 * 否则一个 500 会把切换按钮变成死键。
 */
export function trackHPendingWrite<T>(promise: Promise<T>): Promise<T> {
  const settled = promise.catch(() => undefined)
  _inFlight.add(settled)
  void settled.finally(() => {
    _inFlight.delete(settled)
  })
  return promise
}

/**
 * 等所有已登记的待写盘完成 —— 宿主双向桥 `flushHtml` 的第一步。
 *
 * 用户要求的「点保存后切换要丝滑」在这条路径上成立：无待写盘 ⇒ 本函数是零请求空转，
 * 切换耗时只剩桥的 materialize。未保存才在这里付出一次 PUT。
 *
 * 🔴 两族都要走：只 await in-flight 会漏掉 H5 还在防抖窗口里的那批；
 * 只调 flusher 会漏掉 H7 已发出但未返回的那次。
 */
export async function flushHPendingWrites(): Promise<void> {
  // 先 flush 防抖型：它会产生新的写入 promise，这些 promise 自己会 await 完
  await Promise.all([..._flushers].map((f) => f().catch(() => undefined)))
  // 再等所有在途写入（含上一步新产生的）
  while (_inFlight.size > 0) {
    await Promise.all([..._inFlight])
  }
}

/** 仅供测试：当前登记数（生产代码不要依赖）。 */
export function _hPendingWriteCounts(): { flushers: number; inFlight: number } {
  return { flushers: _flushers.size, inFlight: _inFlight.size }
}
