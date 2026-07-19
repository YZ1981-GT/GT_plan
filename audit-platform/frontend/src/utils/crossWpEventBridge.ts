/**
 * crossWpEventBridge — 统一跨底稿事件传输桥（P0 · 附注联动加固）
 *
 * 背景（2026-07-17 复盘）：跨底稿事件 `substantive:adjudicated` /
 * `disclosure:note-text-updated` 历史上被两套互不相通的传输通道发布/订阅——
 *   - `window.dispatchEvent(new CustomEvent(...))` / `window.addEventListener(...)`
 *   - 进程内 mitt `eventBus.emit(...)` / `eventBus.on(...)`
 * 二者不互通：`eventBus.emit` 不触发 `window.addEventListener`，反之亦然。
 * 后果是跨族联动（如 K11 订阅源底稿减值、各附注 tab 刷新）静默失效。
 *
 * 本桥在应用启动时安装一次（`installCrossWpEventBridge()`），做两件事：
 *  1. **双向转发**：`eventBus.emit` ⇄ `window.dispatchEvent`，带再入守卫（`__fromBus`/
 *     `__fromWindow` 标记）绝不成环——任一侧的生产者，两侧的消费者都能收到。
 *  2. **payload 归一**：`substantive:adjudicated` 的 `auditedAmount` /
 *     `adjudicatedAmount` / `auditedTotal` 三金额别名互填，`wpCode`/`timestamp` 兜底，
 *     使任一侧消费者无论读哪个字段名都拿得到值。
 *
 * 只桥接 `BRIDGED_EVENTS` 内的跨底稿事件；其余事件原样通过 `eventBus`，零影响。
 *
 * @see .kiro/steering/memory.md §待办（复盘发现）附注模块跨模块联动复盘
 */
import { eventBus } from './eventBus'

/** 需要跨传输通道桥接的事件名（跨底稿联动事件）。 */
export const BRIDGED_EVENTS: ReadonlySet<string> = new Set<string>([
  'substantive:adjudicated',
  'disclosure:note-text-updated',
  // 函证联动：confirmation:received 走 mitt（ConfirmationHub 发/摘要卡订阅），
  // confirmation:completed 走 window（历史 emitConfirmationCompleted 约定）——纳入桥接后
  // 两传输通道统一，任一侧生产者两侧消费者都能收到。
  'confirmation:received',
  'confirmation:completed',
  // 调整分录联动：底稿 publishAdjustment 发出，集中式调整管理页及 A13 错报汇总订阅。
  'adjustment:created',
  'a13:push-misstatement',
])

/** 再入守卫标记：源自 eventBus 转发到 window 的事件带此标记，window 监听器见此不回灌。 */
const FROM_BUS = '__fromBus'
/** 再入守卫标记：源自 window 回灌到 eventBus 的事件带此标记，包装 emit 见此不再派发到 window。 */
const FROM_WINDOW = '__fromWindow'

/**
 * payload 归一化。就地补齐金额别名与兜底字段，返回同一对象。
 * - substantive:adjudicated：auditedAmount / adjudicatedAmount / auditedTotal 三别名互填。
 * - disclosure:note-text-updated：timestamp 兜底。
 * - adjustment:created / a13:push-misstatement：wpCode + timestamp 兜底。
 */
export function normalizeBridgedPayload(type: string, p: any): any {
  if (!p || typeof p !== 'object') return p
  if (type === 'substantive:adjudicated') {
    const amt =
      p.auditedAmount ??
      p.adjudicatedAmount ??
      p.auditedTotal ??
      undefined
    if (amt !== undefined) {
      p.auditedAmount = amt
      p.adjudicatedAmount = amt
    }
    if (p.wpCode === undefined) p.wpCode = p.wp_code ?? ''
    if (p.timestamp === undefined) p.timestamp = Date.now()
  } else if (type === 'disclosure:note-text-updated') {
    if (p.timestamp === undefined) p.timestamp = Date.now()
  } else if (type === 'adjustment:created' || type === 'a13:push-misstatement') {
    if (p.wpCode === undefined) p.wpCode = p.wp_code ?? ''
    if (p.timestamp === undefined) p.timestamp = Date.now()
  }
  return p
}

let installed = false

/**
 * 安装跨底稿事件桥（幂等）。在 `main.ts` 应用挂载前调用一次。
 * 返回卸载函数（主要供测试清理；生产环境无需卸载）。
 */
export function installCrossWpEventBridge(): () => void {
  if (installed) return () => undefined
  if (typeof window === 'undefined') return () => undefined
  installed = true

  const originalEmit = eventBus.emit.bind(eventBus)

  // ── 1. 包装 eventBus.emit：桥接事件在派发给 bus 消费者后，再转发到 window ──
  const wrappedEmit = (type: any, evt?: any) => {
    if (BRIDGED_EVENTS.has(type as string)) {
      const payload = normalizeBridgedPayload(type as string, evt)
      // 先派发给 bus 侧消费者（eventBus.on）
      originalEmit(type, payload)
      // 若非来自 window 回灌，则转发到 window（供 addEventListener 侧消费者）
      if (!payload || !(payload as any)[FROM_WINDOW]) {
        try {
          window.dispatchEvent(
            new CustomEvent(type as string, {
              detail: { ...(payload || {}), [FROM_BUS]: true },
            }),
          )
        } catch {
          /* CustomEvent 不可用时静默降级 */
        }
      }
      return
    }
    return originalEmit(type, evt)
  }
  ;(eventBus as any).emit = wrappedEmit

  // ── 2. 监听 window：window 侧生产者 → 回灌 eventBus（带守卫，避免成环）──
  const windowListeners: Array<[string, EventListener]> = []
  for (const type of BRIDGED_EVENTS) {
    const listener = (ev: Event) => {
      const detail = (ev as CustomEvent).detail
      // 来自 bus 的转发（__fromBus）不再回灌 bus，避免成环
      if (detail && (detail as any)[FROM_BUS]) return
      const payload = normalizeBridgedPayload(type, { ...(detail || {}) })
      ;(payload as any)[FROM_WINDOW] = true
      // 直接用 originalEmit（非 wrappedEmit）→ 不会再次派发回 window
      originalEmit(type as any, payload)
    }
    window.addEventListener(type, listener)
    windowListeners.push([type, listener])
  }

  return () => {
    ;(eventBus as any).emit = originalEmit
    for (const [type, listener] of windowListeners) {
      window.removeEventListener(type, listener)
    }
    installed = false
  }
}

/** 测试辅助：查询桥是否已安装。 */
export function isCrossWpEventBridgeInstalled(): boolean {
  return installed
}
