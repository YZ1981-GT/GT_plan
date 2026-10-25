/**
 * 先回表单、后台合并（桥的伴生模块）。
 *
 * spec: oo-return-to-form-dead-end-and-save-speed · R4
 *
 * ═══ 为什么 ═══
 *
 * 「保存并回到表单模式」原来要等服务端整段合并落地（D2 实测 7~10 s，后端刚重载时 76 s）才离开
 * 编辑器，期间编辑器盖着「同步中」。文件一旦在服务端耐久（`incoming_durable` 及之后），之后的
 * 合并就不再需要编辑器：这里接手 —— 关编辑器回到只读表单 + 横幅，桥自己追踪到落地再按结果
 * revision 重载表单、释放 lease。
 *
 * ═══ 两条硬约束 ═══
 *
 * * **lease 只在落地之后释放**：服务端最后一道门要求发起保存的 participant 仍在线
 *   （`oo_to_html` 的 `_INITIATOR_LIVE_STATES`），提前 leave 会让这次合并以「失权」收场；
 *   失败后也留着，「重试回写」同样要过这道门。关提示时才 leave。
 * * **追踪归桥**：宿主随模式切换卸载、它的定时器随之停掉；后台阶段改由桥持有追踪器
 *   （同 180 s 窗口、同一个 api 通道），桥卸载时停掉并注销（服务端照常完成）。
 */
import { WP_BRIDGE_BACKGROUND_MERGE_SOURCE_STATES } from './bridgeStateSets'
import { registerBackgroundMerge, type BackgroundMergeEntry } from './backgroundMergeRegistry'
import {
  bridgeStateForOperation,
  type WorkpaperSyncBridgeEvent,
  type WorkpaperSyncBridgeState,
} from './workpaperSyncBridgeMachine'
import { WorkpaperSyncContractError, type WorkpaperSyncOperationSnapshot } from './workpaperSyncDto'
import {
  WorkpaperSyncOperationTracker,
  type WorkpaperSyncTrackerOptions,
} from './workpaperSyncOperationTracker'
import type { WorkpaperSyncEntryScope } from './workpaperSyncApi'

/** 与宿主前台追踪同一窗口（spec Task 34「不得无限等待」）。 */
export const BACKGROUND_MERGE_DEADLINE_MS = 180_000
const FALLBACK_POLL_MS = 1_000

export const BACKGROUND_MERGE_TEXT = Object.freeze({
  merging: '正在合并在线编辑的改动，表单暂时只读；合并完成后会自动刷新，之后才能再次进入在线编辑。',
  conflict:
    '在线编辑的改动与表单里的内容有冲突，没有自动合并进表单。关闭提示后表单保持合并前的内容。',
  authorization: '发起这次保存的在线编辑资格已失效，改动没有合并进表单。',
  timeout: '等了 3 分钟还没有合并结果。可点「刷新状态」再查一次，或关闭提示。',
  reloadFailed: '合并已完成，但表单刷新失败，可点「刷新状态」重试。',
  failedFallback: '在线编辑的改动合并失败。',
})

export interface BackgroundMergeTracker {
  start(): Promise<void>
  stop(): void
}

export interface BackgroundMergeDeps {
  readonly wpId: () => string
  readonly scope: () => WorkpaperSyncEntryScope
  readonly operationId: () => string | null
  readonly pollAfterMs: () => number | null
  readonly state: () => WorkpaperSyncBridgeState
  readonly apply: (event: WorkpaperSyncBridgeEvent) => void
  readonly fetchSnapshot: (operationId: string) => Promise<WorkpaperSyncOperationSnapshot>
  /** 观测到的快照（桥据此更新 `operation` 投影）。 */
  readonly observe: (snapshot: WorkpaperSyncOperationSnapshot) => void
  /** 服务端重新合并同一份已耐久文件（桥的 `retryOperation`）。 */
  readonly retry: () => Promise<unknown>
  readonly reloadHtml: (minimumRevision: number) => Promise<void>
  /** 落地 / 关提示后结束在线编辑会话（释放 lease、清本地身份；失败不阻断）。 */
  readonly finishSession: () => Promise<void>
  /** 落地后的普通提示（如服务器合并了较新的内容）。 */
  readonly notify?: (message: string) => void
  readonly trackerFactory?: (options: WorkpaperSyncTrackerOptions) => BackgroundMergeTracker
  readonly deadlineMs?: number
}

export interface BackgroundMerge {
  /** 宿主在文件耐久后调用：转后台合并、登记、开始追踪。 */
  continueInBackground(): void
  /** 桥卸载：停追踪、注销（不改状态，服务端照常完成）。 */
  dispose(): void
}

type Verdict =
  | { readonly kind: 'wait' }
  | { readonly kind: 'landed'; readonly revision: number; readonly notice: string | null }
  | { readonly kind: 'failed'; readonly message: string; readonly canRetry: boolean }

/** 一份快照对后台合并意味着什么（纯函数）。 */
export function backgroundMergeVerdict(snapshot: WorkpaperSyncOperationSnapshot): Verdict {
  const projected = bridgeStateForOperation(snapshot)
  if (projected === 'applied') {
    // `applying` 也投影成 applied，但还没有结果 revision ⇒ 继续等。
    return snapshot.resultRevision === null
      ? { kind: 'wait' }
      : { kind: 'landed', revision: snapshot.resultRevision, notice: null }
  }
  if (projected === 'refresh_required' || projected === 'duplicate') {
    return {
      kind: 'landed',
      revision: snapshot.resultRevision ?? 0,
      notice: '服务器上已有较新的合并结果，表单已刷新到最新内容。',
    }
  }
  if (projected === 'conflict') {
    return { kind: 'failed', message: BACKGROUND_MERGE_TEXT.conflict, canRetry: false }
  }
  if (projected === 'close_authorization_stale') {
    return { kind: 'failed', message: BACKGROUND_MERGE_TEXT.authorization, canRetry: false }
  }
  if (projected === 'error') {
    const reason = snapshot.applicationErrorMessage
    return {
      kind: 'failed',
      message: reason ? `在线编辑的改动合并失败：${reason}` : BACKGROUND_MERGE_TEXT.failedFallback,
      canRetry: true,
    }
  }
  return { kind: 'wait' }
}

export function createBackgroundMerge(deps: BackgroundMergeDeps): BackgroundMerge {
  let tracker: BackgroundMergeTracker | null = null
  let registration: { entry: BackgroundMergeEntry; unregister: () => void } | null = null
  let settling = false
  let disposed = false
  /** 追踪代次：停一次加一。被停掉的追踪器迟到的快照 / 到点回调对不上代次 ⇒ 不起作用。 */
  let generation = 0

  function stopTracking(): void {
    generation += 1
    tracker?.stop()
    tracker = null
  }

  function track(operationId: string): void {
    stopTracking()
    const token = generation
    const live = () => !disposed && token === generation
    const options: WorkpaperSyncTrackerOptions = {
      scope: deps.scope(),
      operationId,
      pollIntervalMs: deps.pollAfterMs() ?? FALLBACK_POLL_MS,
      deadlineMs: deps.deadlineMs ?? BACKGROUND_MERGE_DEADLINE_MS,
      poll: (_scope, id) => deps.fetchSnapshot(id),
      onSnapshot: (snapshot) => {
        if (!live()) return
        // 收尾里的转换若被拒（状态已被别的事件推走）⇒ 落失败态让横幅可见，不留未捕获的 rejection。
        void onSnapshot(snapshot).catch((error) => {
          settling = false
          fail(messageOf(error), false)
        })
      },
      onDeadline: () => {
        if (live()) fail(BACKGROUND_MERGE_TEXT.timeout, false)
      },
    }
    const created = deps.trackerFactory?.(options) ?? new WorkpaperSyncOperationTracker(options)
    tracker = created
    void created.start().catch(() => undefined) // 读失败由下一轮轮询 / 窗口到点兜住
  }

  async function onSnapshot(snapshot: WorkpaperSyncOperationSnapshot): Promise<void> {
    if (settling || deps.state() !== 'merging_in_background') return
    deps.observe(snapshot)
    let verdict: Verdict
    try {
      verdict = backgroundMergeVerdict(snapshot)
    } catch (error) {
      verdict = { kind: 'failed', message: messageOf(error), canRetry: false }
    }
    if (verdict.kind === 'wait') return
    stopTracking()
    if (verdict.kind === 'failed') return fail(verdict.message, verdict.canRetry)
    settling = true
    try {
      await deps.reloadHtml(verdict.revision)
    } catch {
      settling = false
      return fail(BACKGROUND_MERGE_TEXT.reloadFailed, false)
    }
    // 重载期间桥已卸载 ⇒ 不再改状态（与卸载「不改状态」同口径；lease 随服务端过期回收）。
    if (disposed) return
    await deps.finishSession()
    deps.apply('reload_completed')
    settling = false
    registration?.unregister()
    registration = null
    if (verdict.notice) deps.notify?.(verdict.notice)
  }

  function fail(message: string, canRetry: boolean): void {
    stopTracking()
    if (disposed || deps.state() !== 'merging_in_background') return
    deps.apply('background_merge_failed')
    if (registration) {
      registration.entry.status = 'failed'
      registration.entry.message = message
      registration.entry.canRetry = canRetry
    }
  }

  function resume(): void {
    const operationId = deps.operationId()
    if (operationId === null) {
      throw new WorkpaperSyncContractError(
        'bridge_background_merge_without_operation',
        '没有本次保存的 operation，无法在后台追踪合并结果',
      )
    }
    deps.apply('background_merge_started')
    if (registration) {
      registration.entry.status = 'merging'
      registration.entry.message = BACKGROUND_MERGE_TEXT.merging
      registration.entry.canRetry = false
    }
    track(operationId)
  }

  async function retry(): Promise<void> {
    if (deps.state() !== 'background_merge_failed') return
    await deps.retry()
    resume()
  }

  async function refresh(): Promise<void> {
    if (deps.state() !== 'background_merge_failed') return
    resume()
  }

  async function dismiss(): Promise<void> {
    if (deps.state() !== 'background_merge_failed') return
    await deps.finishSession()
    deps.apply('reset')
    registration?.unregister()
    registration = null
  }

  function continueInBackground(): void {
    disposed = false
    const from = deps.state()
    if (!(WP_BRIDGE_BACKGROUND_MERGE_SOURCE_STATES as readonly string[]).includes(from)) {
      throw new WorkpaperSyncContractError(
        'bridge_background_merge_out_of_phase',
        `state=${from} 时不能转后台合并 —— 文件还没在服务端耐久，关编辑器可能丢改动`,
      )
    }
    registration?.unregister()
    registration = registerBackgroundMerge({
      wpId: deps.wpId(),
      status: 'merging',
      message: BACKGROUND_MERGE_TEXT.merging,
      canRetry: false,
      retry,
      refresh,
      dismiss,
    })
    resume()
  }

  function dispose(): void {
    disposed = true
    stopTracking()
    registration?.unregister()
    registration = null
  }

  return { continueInBackground, dispose }
}

function messageOf(error: unknown): string {
  if (error instanceof WorkpaperSyncContractError) return `在线编辑的改动合并失败：${error.message}`
  return BACKGROUND_MERGE_TEXT.failedFallback
}
