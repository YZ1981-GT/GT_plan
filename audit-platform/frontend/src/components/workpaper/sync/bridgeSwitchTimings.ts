/**
 * 一次「HTML → 在线编辑」切换的分段计时（spec workpaper-sync-switch-performance 需求 1.3）。
 *
 * 只观测：任何一步计时失败都不影响切换本身。各段以切换开始为零点（毫秒，保留 1 位小数），
 * 同时发一条 User Timing `performance.measure`（DevTools 性能面板与浏览器实测可直接读取，
 * 名称 `wp-sync-switch:<stage>`，detail 带路径）。
 *
 * 段的含义（与后端 `[sync-timing]` 日志拼起来就是一次切换的完整时间线）：
 *
 * | stage            | 截止于                                                    |
 * |------------------|-----------------------------------------------------------|
 * | writes_flushed   | 子 Tab 私有防抖里的待写落库                               |
 * | html_flushed     | 宿主 flushHtml 返回（客户端路径含 GET store-projection）   |
 * | pending_created  | 客户端路径：POST pending-mutations（上传整份投影）返回     |
 * | materialized     | materialize / materialize-from-store 返回 descriptor      |
 * | mounted          | DocEditor 已创建                                          |
 * | ready            | OnlyOffice onDocumentReady                                |
 * | confirmed        | confirm-descriptor 成功（可编辑）                         |
 */

export type WorkpaperSyncSwitchPath = 'client' | 'server_store' | 'server_store_fast'

export type WorkpaperSyncSwitchStage =
  | 'writes_flushed'
  | 'html_flushed'
  | 'pending_created'
  | 'materialized'
  | 'mounted'
  | 'ready'
  | 'confirmed'

export interface WorkpaperSyncSwitchTimings {
  /** 本次切换走的路径；物化返回前为 `null`。 */
  readonly path: WorkpaperSyncSwitchPath | null
  /** 各段距切换开始的毫秒数；未到达的段缺省。 */
  readonly marks: Readonly<Partial<Record<WorkpaperSyncSwitchStage, number>>>
}

export const SWITCH_MEASURE_PREFIX = 'wp-sync-switch'

export const EMPTY_SWITCH_TIMINGS: WorkpaperSyncSwitchTimings = Object.freeze({
  path: null,
  marks: Object.freeze({}),
})

export interface WorkpaperSyncSwitchTimer {
  /** 开始一次新切换（清掉上一次）。 */
  begin(): WorkpaperSyncSwitchTimings
  setPath(path: WorkpaperSyncSwitchPath): WorkpaperSyncSwitchTimings
  /** 记一段；`confirmed` 之后计时关闭，其后的 mark 不再计入（如 refresh 后的重挂载）。 */
  mark(stage: WorkpaperSyncSwitchStage): WorkpaperSyncSwitchTimings
}

export function createSwitchTimer(
  now: () => number = () => performance.now(),
): WorkpaperSyncSwitchTimer {
  let origin: number | null = null
  let path: WorkpaperSyncSwitchPath | null = null
  let marks: Partial<Record<WorkpaperSyncSwitchStage, number>> = {}

  const snapshot = (): WorkpaperSyncSwitchTimings => ({ path, marks: { ...marks } })

  return {
    begin() {
      origin = now()
      path = null
      marks = {}
      return snapshot()
    },
    setPath(next) {
      if (origin !== null) path = next
      return snapshot()
    },
    mark(stage) {
      if (origin === null) return snapshot()
      const at = now()
      marks = { ...marks, [stage]: Math.round((at - origin) * 10) / 10 }
      try {
        performance.measure(`${SWITCH_MEASURE_PREFIX}:${stage}`, {
          start: origin,
          end: at,
          detail: { path },
        })
      } catch {
        // 只观测：User Timing 不可用（或注入的时钟不在 performance 时间线上）时静默。
      }
      if (stage === 'confirmed') origin = null
      return snapshot()
    },
  }
}
