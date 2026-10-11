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
 *
 * ═══ 2026-10-11 起本文件只是别名（spec d2-online-edit-platform-closure R20）═══════
 *
 * 同一个缺陷在 D 循环的子 Tab 上原样复现（`useD2Detail` 的私有 2s 防抖 ⇒ 改格后 2 秒内点
 * 在线编辑，store-projection 读到旧值，随后被 OO 保存覆盖）。注册表因此上提为平台模块
 * `./pendingWrites`，并由双向桥在**每次** `flushHtml` 之前统一调用。这里保留 H 的名字，
 * 指向**同一张**注册表 —— H5/H7 的登记与宿主里的 `flushHPendingWrites()` 调用一行不用改。
 */
export {
  _pendingWriteCounts as _hPendingWriteCounts,
  flushPendingWrites as flushHPendingWrites,
  registerPendingFlusher as registerHPendingFlusher,
  trackPendingWrite as trackHPendingWrite,
  type PendingWriteFlusher as HPendingFlusher,
} from './pendingWrites'
