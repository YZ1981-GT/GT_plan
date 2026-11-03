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
import { computed, getCurrentScope, onScopeDispose, ref, type ComputedRef } from 'vue'

/** 防抖型写入方的 flush 函数（调用即「清防抖 + 立即发起写入」）。 */
export type PendingWriteFlusher = () => Promise<void> | void

/** 一条写入屏障失败；保留原异常供界面/日志定位。 */
export interface PendingWriteFailure {
  readonly source: 'flusher' | 'in_flight'
  readonly error: unknown
}

/**
 * 从一条失败里取出能给用户看的原因。
 *
 * 只有计数的文案（「有 N 项内容保存失败」）在多失败场景下无法定位，用户只能盲猜；
 * `failures` 里本来就带着原始异常，这里把它摊成人读得懂的一行。
 */
export function describePendingWriteFailure(failure: PendingWriteFailure): string {
  const error = failure.error as
    | { response?: { data?: { message?: unknown; detail?: unknown } }; message?: unknown }
    | string
    | null
    | undefined
  if (typeof error === 'string') return error.trim()
  const data = (typeof error === 'object' && error?.response?.data) || undefined
  const fromEnvelope = data?.message ?? (typeof data?.detail === 'string' ? data.detail : undefined)
  if (typeof fromEnvelope === 'string' && fromEnvelope.trim()) return fromEnvelope.trim()
  const message = typeof error === 'object' ? error?.message : undefined
  if (typeof message === 'string' && message.trim()) return message.trim()
  return '未知错误'
}

export class PendingWritesFlushError extends Error {
  readonly failures: readonly PendingWriteFailure[]
  /** 去重后的失败原因（按出现顺序）；界面可直接逐条列出。 */
  readonly reasons: readonly string[]

  constructor(failures: readonly PendingWriteFailure[]) {
    const reasons = [...new Set(failures.map(describePendingWriteFailure))]
    // 文案里最多带 3 条，避免把 ElMessage 撑爆；完整清单在 `reasons` / `failures` 上。
    const shown = reasons.slice(0, 3).join('；')
    const more = reasons.length > 3 ? `（另有 ${reasons.length - 3} 类原因）` : ''
    super(
      `切换在线编辑前有 ${failures.length} 项内容保存失败，请重试`
      + (shown ? `：${shown}${more}` : ''),
    )
    this.name = 'PendingWritesFlushError'
    this.failures = failures
    this.reasons = reasons
  }
}

interface PendingWriteOutcome {
  readonly ok: boolean
  readonly error?: unknown
}

const _flushers = new Set<PendingWriteFlusher>()
const _inFlight = new Set<Promise<PendingWriteOutcome>>()
let _flushInProgress: Promise<void> | null = null
const _barrierDepth = ref(0)

/**
 * 从点击进入在线编辑起，到 projection/config/materialize 与模式切换全部完成前保持 true。
 * 只导出只读 computed；结构化输入据此冻结，不能由宿主自行提前解除。
 */
export const pendingWriteBarrierActive: ComputedRef<boolean> = computed(
  () => _barrierDepth.value > 0,
)

/**
 * 持有一次完整 HTML→OnlyOffice 过渡的全局 lease。
 *
 * 计数而非 boolean 可保证并发宿主或嵌套包装中，先完成的一方不会提前解冻另一方。
 * 实际 flush 由调用方在 operation 内显式执行，避免 bridge/legacy 重复冲刷。
 */
export async function runWithPendingWriteBarrier<T>(operation: () => Promise<T>): Promise<T> {
  _barrierDepth.value += 1
  try {
    return await operation()
  } finally {
    _barrierDepth.value -= 1
  }
}

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
 * 追踪一次**已发起**的写入 promise，并把结局留给当前保存屏障；返回原 promise，调用方写法不变。
 *
 * 写入失败仍由原调用方显示，但屏障必须知道失败并阻止 materialize。只在这里把 rejection
 * 转成 outcome，是为了让所有写入都结算后一次报告，而不是第一项失败就跳过其余 flusher。
 */
export function trackPendingWrite<T>(promise: Promise<T>): Promise<T> {
  const settled: Promise<PendingWriteOutcome> = promise.then(
    () => ({ ok: true }),
    (error: unknown) => ({ ok: false, error }),
  )
  _inFlight.add(settled)
  void settled.finally(() => {
    _inFlight.delete(settled)
  })
  return promise
}

/**
 * 等所有已登记的待写盘完成。每项都尝试并结算；任一失败则在末尾抛结构化错误，调用方必须
 * 保持 HTML 模式。flusher 同步发起的 trackPendingWrite 会进入随后循环并被同一轮等待。
 */
async function flushPendingWritesOnce(): Promise<void> {
  const failures: PendingWriteFailure[] = []
  const seenErrors = new Set<unknown>()
  const tracked = new Set<Promise<PendingWriteOutcome>>(_inFlight)
  const addFailure = (source: PendingWriteFailure['source'], error: unknown) => {
    if (seenErrors.has(error)) return
    seenErrors.add(error)
    failures.push({ source, error })
  }
  const flusherPromise = Promise.all([..._flushers].map(async (flush) => {
    try {
      await flush()
      return null
    } catch (error) {
      return { source: 'flusher' as const, error }
    }
  }))
  // flusher 会在第一次 await 前同步登记它发起的真实请求；让一个微任务后把它们也纳入本轮。
  await Promise.resolve()
  for (const pending of _inFlight) tracked.add(pending)
  const flusherResults = await flusherPromise
  for (const failure of flusherResults) {
    if (failure) addFailure(failure.source, failure.error)
  }
  while (_inFlight.size > 0) {
    const batch = [..._inFlight]
    for (const pending of batch) tracked.add(pending)
    await Promise.all(batch)
  }
  for (const outcome of await Promise.all(tracked)) {
    if (!outcome.ok) addFailure('in_flight', outcome.error)
  }
  if (failures.length > 0) throw new PendingWritesFlushError(failures)
}

/** 并发切换共享同一轮屏障及同一结果；否则先到者会消费失败，后到者反而错误放行。 */
export function flushPendingWrites(): Promise<void> {
  if (_flushInProgress) return _flushInProgress
  const current = flushPendingWritesOnce()
  _flushInProgress = current
  void current.then(
    () => { if (_flushInProgress === current) _flushInProgress = null },
    () => { if (_flushInProgress === current) _flushInProgress = null },
  )
  return current
}

/** 仅供测试：当前登记数（生产代码不要依赖）。 */
export function _pendingWriteCounts(): { flushers: number; inFlight: number } {
  return { flushers: _flushers.size, inFlight: _inFlight.size }
}
