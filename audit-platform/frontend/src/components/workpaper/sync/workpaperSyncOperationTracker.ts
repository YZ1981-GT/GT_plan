/**
 * operation 追踪器：**SSE 优先、轮询恢复**，按 operation/revision 去重。
 *
 * spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 31
 * Requirements: 11.9, 11.11, 4.2, 5.10
 *
 * ═══ 三条职责 ═══
 *
 * 1. **起始读一次** —— SSE 只投递「之后」的事件，当前状态必须先读一次。
 *    这一次不算轮询。
 * 2. **SSE 健康时不轮询** —— design §API 明文「前端优先 SSE/事件，轮询作为断线恢复」。
 *    无条件起一个 interval 会在 6000 会话规模下把 operation GET 打成常态流量，
 *    而功能上完全「正常」。
 * 3. **去重键 = (canonical operation, state, result revision)** —— AC 11.9 的
 *    `wp_id + revision` 用于 `workpaper.content.updated`，operation 侧再叠一层：
 *    同一事实重复投递只通知一次，但**状态推进与 revision 推进必须通知**。
 *    只按 operation 去重会把整条状态机压成一次通知（UI 永远停在第一个状态）。
 *
 * ═══ 本模块不做的事 ═══
 *
 * 不判定模式、不改 editing/forcesave 门控、不把 409 变成可重试 —— 那是 Task 32 的
 * bridge 状态机与 `classifySyncFailure()` 的职责。
 */
import { subscribeProjectEvent } from '@/services/sse/projectEventStream'

import { getOperation, type WorkpaperSyncEntryScope } from './workpaperSyncApi'
import {
  WP_CONTENT_UPDATED_EVENT_NAME,
  contentUpdateDedupeKey as contentUpdateDedupeKeyImpl,
} from './workpaperSyncContentRefresh'
import type { WorkpaperSyncOperationSnapshot } from './workpaperSyncDto'

/** 内容提交事件名（真源 = 后端 `EventType.WORKPAPER_CONTENT_UPDATED`）。 */
export const WORKPAPER_CONTENT_UPDATED_EVENT = WP_CONTENT_UPDATED_EVENT_NAME

export interface WorkpaperSyncSubscription {
  close(): void
}

export interface WorkpaperSyncSubscribeContext {
  readonly projectId: string
  readonly onEvent: (payload: unknown) => void
  readonly onReconnect: () => void
  readonly onDegraded: () => void
}

export interface WorkpaperSyncTrackerOptions {
  readonly scope: WorkpaperSyncEntryScope
  readonly operationId: string
  readonly onSnapshot: (snapshot: WorkpaperSyncOperationSnapshot) => void
  /** 注入点：默认订阅项目共享事件流。 */
  readonly subscribe?: (context: WorkpaperSyncSubscribeContext) => WorkpaperSyncSubscription
  /** 注入点：默认打 `GET .../operations/{id}`。 */
  readonly poll?: (
    scope: WorkpaperSyncEntryScope,
    operationId: string,
  ) => Promise<WorkpaperSyncOperationSnapshot>
  /** 降级后的轮询间隔。 */
  readonly degradedPollIntervalMs?: number
}

/** 去重结果。`accepted=false` 表示这条事实此前已投递过。 */
export interface WorkpaperSyncDedupeResult {
  readonly accepted: boolean
  readonly key: string
}

/**
 * `workpaper.content.updated` 的去重键 —— AC 11.9 的 `wp_id + revision`。
 *
 * 🔴 不含 `operation_id`：同一次 commit 可能由 operation 应用也可能由纯表示升级触发
 * （后者 `content_revision_advanced=false`），把 operation 放进键会让同一个 revision
 * 被投递两次。
 *
 * 🔴 Task 35 修点：实现下沉到 `workpaperSyncContentRefresh.contentUpdateDedupeKey()`。
 * 本函数原来只读**顶层** `wp_id`/`revision`，而真实 SSE 到达的是 typed 信封
 * （业务键在 `extra` 里，见 `app/routers/events.py`）—— 于是键恒为 `null`，AC 11.9 的
 * 去重从未生效，每条事件都退化成"补读一次"。归一放在单一真源里，两个消费方共用。
 */
export function contentUpdateDedupeKey(payload: unknown): string | null {
  return contentUpdateDedupeKeyImpl(payload)
}

/**
 * operation 快照的去重键。
 *
 * 三段都必须在键里：
 *
 * * `canonicalOperationId` —— duplicate 跟随 primary 后，两个 requested id 会看到同一
 *   份 canonical 事实，按 requested id 去重会重复通知；
 * * `state` —— 状态推进是必须投递的事实；
 * * `resultRevision` —— same-application 的 sequence fold 不改 state，但 applied
 *   revision 会推进。
 */
export function operationSnapshotDedupeKey(
  snapshot: WorkpaperSyncOperationSnapshot,
): string {
  return [
    snapshot.canonicalOperationId,
    snapshot.state,
    snapshot.resultRevision === null ? '-' : String(snapshot.resultRevision),
  ].join('|')
}

function defaultSubscribe(
  context: WorkpaperSyncSubscribeContext,
): WorkpaperSyncSubscription {
  return subscribeProjectEvent(
    context.projectId,
    WORKPAPER_CONTENT_UPDATED_EVENT,
    (data) => context.onEvent(data),
    { onReconnect: context.onReconnect, onDegraded: context.onDegraded },
  )
}

/**
 * 追踪一个 operation 直到调用方 `stop()`。
 *
 * 生命周期：`start()` → 初次读一次 → SSE 投递 → （重连时补读一次 / 降级后才轮询）。
 */
export class WorkpaperSyncOperationTracker {
  private readonly options: WorkpaperSyncTrackerOptions

  private readonly seen = new Set<string>()

  private subscription: WorkpaperSyncSubscription | null = null

  private timer: ReturnType<typeof setInterval> | null = null

  /** 观测面：真实发出的 operation GET 次数（含初次读）。 */
  pollCount = 0

  /** 观测面：因 SSE 降级而进入轮询。 */
  degraded = false

  private stopped = false

  constructor(options: WorkpaperSyncTrackerOptions) {
    this.options = options
  }

  async start(): Promise<void> {
    this.stopped = false
    const subscribe = this.options.subscribe ?? defaultSubscribe
    this.subscription = subscribe({
      projectId: this.options.scope.projectId,
      onEvent: (payload) => this.handleContentUpdate(payload),
      onReconnect: () => {
        // 断线期间的事件已经错过 ⇒ 补读一次（这才是「轮询恢复」）。
        void this.refresh()
      },
      onDegraded: () => this.enterDegradedPolling(),
    })
    // 初次读一次当前状态：SSE 只投递之后的事件。
    await this.refresh()
  }

  stop(): void {
    this.stopped = true
    this.subscription?.close()
    this.subscription = null
    if (this.timer !== null) {
      clearInterval(this.timer)
      this.timer = null
    }
  }

  /** 显式读一次并按去重键投递。 */
  async refresh(): Promise<void> {
    if (this.stopped) return
    const poll = this.options.poll ?? getOperation
    this.pollCount += 1
    const snapshot = await poll(this.options.scope, this.options.operationId)
    this.deliver(snapshot)
  }

  /** SSE 事件 → 先按 `wp_id + revision` 去重，再补读 operation 快照。 */
  handleContentUpdate(payload: unknown): WorkpaperSyncDedupeResult {
    const key = contentUpdateDedupeKey(payload)
    if (key === null) {
      // 缺 wp_id/revision 的事件无法去重 ⇒ 不静默丢，补读一次由快照去重兜住。
      void this.refresh()
      return { accepted: true, key: '' }
    }
    if (this.seen.has(key)) {
      return { accepted: false, key }
    }
    this.seen.add(key)
    void this.refresh()
    return { accepted: true, key }
  }

  /** 快照去重后才通知调用方。 */
  deliver(snapshot: WorkpaperSyncOperationSnapshot): WorkpaperSyncDedupeResult {
    const key = operationSnapshotDedupeKey(snapshot)
    if (this.seen.has(key)) {
      return { accepted: false, key }
    }
    this.seen.add(key)
    this.options.onSnapshot(snapshot)
    return { accepted: true, key }
  }

  private enterDegradedPolling(): void {
    if (this.degraded || this.stopped) return
    this.degraded = true
    const interval = this.options.degradedPollIntervalMs ?? 5000
    this.timer = setInterval(() => {
      void this.refresh()
    }, interval)
  }
}
