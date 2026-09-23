/**
 * 底稿 HTML ↔ OnlyOffice 双向回写的**唯一模式状态机**（Vue composable）。
 *
 * spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 32
 * Requirements: 3.1, 3.6, 3.7, 4.1, 4.2, 4.4, 4.5, 4.6, 4.7, 4.8, 5.8, 11.1, 11.2,
 *               11.3, 11.6, 11.8, 11.10, 14.8
 * Properties: P10 / P12 / P13 / P14 / P15 / P46 / P48（本模块是它们的前端判据面）
 *
 * ═══ 职责边界 ═══
 *
 * * **状态**归本模块（转换表在 `workpaperSyncBridgeMachine.ts`，纯函数可穷举）。
 * * **HTTP** 归 `workpaperSyncApi.ts`（16 个 method，首参恒为显式 entry scope）。
 * * **DOM/挂载时序**归 Task 33 的 `GtOnlyOfficeSheet` / Word editor —— 本模块只提供
 *   `notifyEditorMounted()` / `notifyDocumentReady()` 两个上报口，**不碰 DOM**。
 *   Property 11 / 47 的「mount → ready → confirm → 可编辑」DOM 侧判据在 Task 33。
 * * **状态条/冲突面板/recovery 面板/timeline** 归 Task 34；本模块只给状态与中文文案。
 *
 * ═══ 与 design §Frontend 的一处显式偏离 ═══
 *
 * design 的 `flushHtml` 返回 `{expectedRevision, pendingMutationToken, payloadSha256,
 * expiresAt}` —— 那是 `POST .../pending-mutations` 的**回执**，意味着宿主自己打这个
 * 端点。但 AC 11.1 明文「业务组件只提供 `entry_id`、flush/reload 钩子和 adapter 上下文，
 * 不得自行拼 config/forcesave URL」，design §Frontend 末段也写「业务 composable 不拼
 * endpoint」。两处冲突时取 AC：本模块的 `flushHtml` 只交回**要提交的 projection 与
 * expected revision**，pending mutation 与 materialize 都由桥调用。
 */
import { computed, getCurrentInstance, onBeforeUnmount, readonly, ref, type Ref } from 'vue'

import {
  WP_BRIDGE_STATE_TEXT,
  auditBridgeMachine,
  bridgeStateForOperation,
  transitionBridgeState,
  type WorkpaperSyncBridgeEvent,
  type WorkpaperSyncBridgeMode,
  type WorkpaperSyncBridgeState,
  type WorkpaperSyncBridgeTransitionContext,
} from './workpaperSyncBridgeMachine'
import {
  WorkpaperSyncContractError,
  WP_SYNC_STALE_IDENTITY_CODES,
  buildDescriptorConfirmPayload,
  classifySyncFailure,
  isSyncDigest,
  type WorkpaperSyncDescriptorConfirmation,
  type WorkpaperSyncEditorLaunchDescriptor,
  type WorkpaperSyncFailureVerdict,
  type WorkpaperSyncOperationSnapshot,
  type WorkpaperSyncRecoveryCase,
} from './workpaperSyncDto'
import * as syncApi from './workpaperSyncApi'
import type { WorkpaperSyncEntryScope } from './workpaperSyncApi'
import {
  migrateWorkpaperSyncMode,
  persistWorkpaperSyncMode,
  supportedModesForCapability,
  workpaperSyncModeKey,
  type WorkpaperSyncModeMigration,
} from './workpaperSyncModeStorage'
import type { WorkpaperSyncCapability } from './workpaperSyncManifest.generated'

function refuse(code: string, message: string): never {
  throw new WorkpaperSyncContractError(code, message)
}

// ═══════════════════════════════════════════════════════════════════════════
// 1. 失败归一
// ═══════════════════════════════════════════════════════════════════════════

/**
 * scope / 授权失败的**唯一**合成码。
 *
 * 服务端把「不存在 / 已 retire / 跨 scope / 无 visibility」四种原因压成同一个 404，
 * 响应体是纯字符串 `资源不存在或不可访问`，**没有** `error_code`。前端因此必须自己
 * 合成一个码才能分型，而这个码刻意**不区分**那四种原因 —— 区分开就等于泄露存在性。
 */
export const WP_BRIDGE_NON_DISCLOSURE_CODE = 'sync_scope_not_visible_or_forbidden'

/**
 * **没有任何服务端 `error_code`** 的失败（本地 flush/reload 钩子抛错、网络中断、超时、
 * 5xx 纯文本）的唯一合成码。
 *
 * 🔴 必须与 `WP_BRIDGE_NON_DISCLOSURE_CODE` 分开：两者共用一个码会让「统一 404 的
 * 存在性不泄露」与「本地钩子抛了个普通 Error」在 UI 上不可区分，而前者不可重试、
 * 后者恰恰是 AC 4.4 要求「保持 OO 并允许重试」的那一类。
 */
export const WP_BRIDGE_LOCAL_FAILURE_CODE = 'sync_step_failed_without_server_code'

/**
 * axios「请求被取消」判据（`utils/http.ts` 的请求去重层 `AbortController.abort()`）。
 *
 * 🔴 为什么要在桥里单独识别它、且**绝不**记进 `lastError`/`error` 态：
 * D4 整册的 40+ 张子 sheet **共用同一个 entryId**（`xlsx/gt-d4-operating-revenue`），
 * 于是 `read_store_projection` / `materialize` 在不同子 sheet 间是**同一个 URL**。
 * 用户切页签后再点「在线编辑」，http.ts 去重层会把上一发在飞的同 URL 请求 `abort()`
 * —— 这是**纯 UI 竞态**，不是同步失败：真正落库/授权/身份都没发生任何错误。
 *
 * 若把它当普通失败（`readWireError` 看不出它是 cancel：无 response、message 恰好是
 * `'canceled'`），就会弹出「同步失败: canceled」红色遮罩，而且因 `lastError` 是 sticky
 * （Property 48）永不消退。全仓其余保存路径（`useD4FormData`/`WpPopupMixedForm` 等
 * 十余处）都对 canceled 做了同款短路，唯独 sync 目录漏了这一处 —— 此判据补齐它。
 */
function isRequestCanceled(error: unknown): boolean {
  const e = (error ?? {}) as { code?: unknown; name?: unknown; message?: unknown; __CANCEL__?: unknown }
  return (
    e.code === 'ERR_CANCELED' ||
    e.name === 'CanceledError' ||
    e.__CANCEL__ === true ||
    e.message === 'canceled'
  )
}

/** 合成码的中文文案：可诊断（说得出是 scope/授权面）但不透露对象是否存在。 */
const NON_DISCLOSURE_TEXT = '该同步对象不可访问：请确认项目/底稿/条目范围与当前权限'

export interface WorkpaperSyncBridgeError {
  readonly stage: string
  readonly httpStatus: number | null
  readonly errorCode: string
  readonly message: string
  readonly verdict: WorkpaperSyncFailureVerdict
  readonly staleIdentity: boolean
}

interface WireErrorShape {
  response?: { status?: unknown; data?: unknown }
  code?: unknown
  message?: unknown
}

/** 从 axios 风格的异常里取 `(status, error_code, message)`。 */
function readWireError(error: unknown): {
  status: number | null
  errorCode: string
  message: string
} {
  if (error instanceof WorkpaperSyncContractError) {
    return { status: null, errorCode: error.code, message: error.message }
  }
  const shape = (error ?? {}) as WireErrorShape
  const rawStatus = shape.response?.status
  const status = typeof rawStatus === 'number' && Number.isInteger(rawStatus) ? rawStatus : null
  const data = shape.response?.data as { detail?: unknown } | undefined
  const detail = data?.detail
  let errorCode = ''
  let message = typeof shape.message === 'string' ? shape.message : ''
  if (detail !== null && typeof detail === 'object' && !Array.isArray(detail)) {
    const wire = detail as Record<string, unknown>
    if (typeof wire.error_code === 'string') errorCode = wire.error_code.trim()
    if (typeof wire.message === 'string' && wire.message.trim() !== '') {
      message = wire.message
    }
  } else if (typeof detail === 'string' && detail.trim() !== '') {
    // 统一 404/403 的纯字符串 detail —— 逐字保留不能当 error_code 用。
    message = detail
  }
  return { status, errorCode, message }
}

/**
 * 归一成 `WorkpaperSyncBridgeError`。**三个互斥分桶，三个互不相同的码。**
 *
 * | 分桶 | 判据 | 码 | 可重试 |
 * |---|---|---|---|
 * | 业务失败 | 响应体带 `detail.error_code` | 服务端原码 | `classifySyncFailure` 裁决 |
 * | scope/授权 | 无码且 403/404（统一响应体是纯字符串） | `WP_BRIDGE_NON_DISCLOSURE_CODE` | 否 |
 * | 本地/传输 | 完全没有码（钩子抛错、断网、超时、5xx 纯文本） | `WP_BRIDGE_LOCAL_FAILURE_CODE` | 无响应或 500/503 时是 |
 *
 * 🔴 第三桶**不能**转交 `classifySyncFailure` —— 它对空 `error_code` 会抛
 * `failure_error_code_missing`。那条拒绝是给「服务端返回业务失败却漏了码」用的判据，
 * 拿它兜住本地钩子抛错会有两个后果：①原始异常被替换成一个看不懂的契约错误，
 * ②`lastError` 根本没来得及被记住，于是 Property 48 的粘性 error 直接失效。
 * 这条正是本任务写判据时打红抓到的真实缺陷。
 */
export function describeBridgeFailure(stage: string, error: unknown): WorkpaperSyncBridgeError {
  const wire = readWireError(error)
  if (wire.errorCode !== '') {
    const verdict = classifySyncFailure({ httpStatus: wire.status, errorCode: wire.errorCode })
    return {
      stage,
      httpStatus: wire.status,
      errorCode: wire.errorCode,
      message: wire.message || WP_BRIDGE_STATE_TEXT.error,
      verdict,
      staleIdentity: (WP_SYNC_STALE_IDENTITY_CODES as readonly string[]).includes(wire.errorCode),
    }
  }
  if (wire.status === 404 || wire.status === 403) {
    return {
      stage,
      httpStatus: wire.status,
      errorCode: WP_BRIDGE_NON_DISCLOSURE_CODE,
      message: NON_DISCLOSURE_TEXT,
      verdict: {
        httpStatus: wire.status,
        errorCode: WP_BRIDGE_NON_DISCLOSURE_CODE,
        canEnterEditing: false,
        retryableOperation: false,
        canForcesave: false,
        unregistered: false,
      },
      staleIdentity: false,
    }
  }
  // 无响应（本地/网络）或 5xx 纯文本：可重试面沿用 DTO 的登记规则（500/503），
  // 完全没有响应时按「可重试」处理 —— AC 4.4 明文要求超时/命令失败保持 OO 并允许重试。
  const retryable = wire.status === null || wire.status === 500 || wire.status === 503
  return {
    stage,
    httpStatus: wire.status,
    errorCode: WP_BRIDGE_LOCAL_FAILURE_CODE,
    message: wire.message || WP_BRIDGE_STATE_TEXT.error,
    verdict: {
      httpStatus: wire.status,
      errorCode: WP_BRIDGE_LOCAL_FAILURE_CODE,
      canEnterEditing: false,
      retryableOperation: retryable,
      canForcesave: false,
      unregistered: true,
    },
    staleIdentity: false,
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 2. in-flight / 离开阻断
// ═══════════════════════════════════════════════════════════════════════════

/**
 * AC 4.8 的阻断集：这些状态下关闭/刷新/路由离开必须提示用户。
 *
 * 🔴 `applied` **在**集合里：结构化回写已完成但 HTML 还没按 result revision 重载，
 * 此刻离开会让用户下次看到旧 revision 并以为回写丢了（Property 14）。
 * `oo_editing` **不在**集合里 —— 它靠 `dirty` 单独判定，否则打开编辑器就永远走不掉。
 */
export const WP_BRIDGE_IN_FLIGHT_STATES: readonly WorkpaperSyncBridgeState[] = [
  'flushing',
  'committing',
  'materializing',
  'oo_loading',
  'descriptor_mounted',
  'confirming_descriptor',
  'forcesave_requesting',
  'forcesave_frozen',
  'forcesave_accepted',
  'waiting_application',
  'incoming_durable',
  'application_bound',
  'merging',
  'rematerializing',
  'conflict',
  'refresh_required',
  'applied',
  'recovery_claiming',
]

/**
 * 可以（重新）发强制保存命令的状态集合。
 *
 * 🔴 `forcesave_frozen` 必须在内，否则「允许重试」只是说法：转换表里
 * `forcesave_frozen --forcesave_started--> forcesave_requesting` 本来就在（design
 * §retryOperation「重试只重发命令，不重新冻结 request」），状态提示也写着「请重新发送
 * 强制保存命令」，但 `canForcesave` 只认 `oo_editing` ⇒ 宿主的保存按钮
 * `:disabled="!canForcesave"` 永久灰掉、`switchToHtml()` 的首道门也直接 refuse。
 *
 * 2026-09-22 真栈实测的死角：用户进 OO 什么都没改就点保存 → Command Service 返
 * `no_changes` → `callback_expected=false` → `forcesave_frozen`，界面显示「文档没有
 * 检测到改动……请在编辑器内先点一下单元格外的空白处让改动生效，**再重新保存**」，而那个
 * 按钮已经灰了；同时 room 开着、结构化视图的切换入口也是禁用的 ⇒ 用户被关在 OO 里无路可走。
 *
 * `forcesaveUnlocked` 仍是硬前提（在 `canForcesave` 里与本集合取合），没拿到
 * confirm-descriptor 成功响应之前一律不放行。
 */
export const WP_BRIDGE_FORCESAVE_READY_STATES: readonly WorkpaperSyncBridgeState[] = [
  'oo_editing',
  'forcesave_frozen',
]

// ═══════════════════════════════════════════════════════════════════════════
// 3. 选项
// ═══════════════════════════════════════════════════════════════════════════

export interface WorkpaperSyncFlushResult {
  readonly expectedRevision: number
  readonly projection: unknown
  readonly sheetKey?: string
  readonly clientEditEpoch?: number
}

export interface WorkpaperSyncBridgeOptions {
  readonly entryId: Ref<string>
  readonly wpId: Ref<string>
  readonly projectId: Ref<string>
  readonly sheetKey?: Ref<string>
  readonly capability: WorkpaperSyncCapability
  /** 宿主的 flush 钩子：只交回 projection 与 expected revision，不打端点。 */
  readonly flushHtml: () => Promise<WorkpaperSyncFlushResult>
  /** 宿主的重载钩子：**必须**加载到不低于 `minimumRevision` 的内容（Property 14）。 */
  readonly reloadHtml: (minimumRevision: number) => Promise<void>
  /** 注入点：默认 `workpaperSyncApi`（测试注入 stub，不 mock 模块）。 */
  readonly api?: WorkpaperSyncApiSurface
  /** 注入点：localStorage（测试注入内存实现）。 */
  readonly storage?: {
    readonly length: number
    key(index: number): string | null
    getItem(key: string): string | null
    setItem(key: string, value: string): void
    removeItem(key: string): void
  } | null
  /** 默认 true；测试或无 window 环境可关。 */
  readonly installBeforeUnload?: boolean
}

/** 桥用到的 API 面（`typeof syncApi` 的子集，显式列出便于注入 stub）。 */
export interface WorkpaperSyncApiSurface {
  createPendingMutation: typeof syncApi.createPendingMutation
  materialize: typeof syncApi.materialize
  confirmDescriptor: typeof syncApi.confirmDescriptor
  requestForcesave: typeof syncApi.requestForcesave
  /**
   * close **barrier 仲裁**（多人协同的收尾）。
   *
   * 🔴 **不是**「我走了」—— 它会把 participant 推成 `closing` 并提升一条 `close_capture`
   * 写请求。未改动离开走 `leaveRoom`，见 `leaveWithoutSaving()`。桥当前没有调用它的
   * 路径（clean close 已改走 leave），保留在这个面上是因为它仍是 close 仲裁的唯一入口，
   * 且 `cleanCloseWithoutSaving.spec.ts` 的「零次 close-intent」判据要能看见它。
   */
  createCloseIntent: typeof syncApi.createCloseIntent
  /** participant 主动离开（未改动直接返回表单）。见 `leaveWithoutSaving()`。 */
  leaveRoom: typeof syncApi.leaveRoom
  getOperation: typeof syncApi.getOperation
  getOperationConflicts: typeof syncApi.getOperationConflicts
  getOperationTimeline: typeof syncApi.getOperationTimeline
  getRecoveryCaseTimeline: typeof syncApi.getRecoveryCaseTimeline
  resolveConflicts: typeof syncApi.resolveConflicts
  retryOperation: typeof syncApi.retryOperation
  listRecoveryCases: typeof syncApi.listRecoveryCases
  claimRecoveryCase: typeof syncApi.claimRecoveryCase
  terminateRecoveryDownloadOnly: typeof syncApi.terminateRecoveryDownloadOnly
  downloadRecoveryArtifact: typeof syncApi.downloadRecoveryArtifact
  rollbackVersion: typeof syncApi.rollbackVersion
}

const DEFAULT_API: WorkpaperSyncApiSurface = {
  createPendingMutation: syncApi.createPendingMutation,
  materialize: syncApi.materialize,
  confirmDescriptor: syncApi.confirmDescriptor,
  requestForcesave: syncApi.requestForcesave,
  createCloseIntent: syncApi.createCloseIntent,
  leaveRoom: syncApi.leaveRoom,
  getOperation: syncApi.getOperation,
  getOperationConflicts: syncApi.getOperationConflicts,
  getOperationTimeline: syncApi.getOperationTimeline,
  getRecoveryCaseTimeline: syncApi.getRecoveryCaseTimeline,
  resolveConflicts: syncApi.resolveConflicts,
  retryOperation: syncApi.retryOperation,
  listRecoveryCases: syncApi.listRecoveryCases,
  claimRecoveryCase: syncApi.claimRecoveryCase,
  terminateRecoveryDownloadOnly: syncApi.terminateRecoveryDownloadOnly,
  downloadRecoveryArtifact: syncApi.downloadRecoveryArtifact,
  rollbackVersion: syncApi.rollbackVersion,
}

export interface WorkpaperSyncResolveFence {
  readonly canonicalApplicationId: string
  readonly applicationEffectiveRequestSequence: number
  readonly roomLatestDurableApplicationId: string
  readonly roomLatestDurableSequence: number
  readonly conflictSetDigest: string
  readonly expectedCurrentRevision: number
  readonly roomGeneration: number
  readonly clientEditEpoch: number
}

// ═══════════════════════════════════════════════════════════════════════════
// 4. composable
// ═══════════════════════════════════════════════════════════════════════════

export function useWorkpaperSyncBridge(options: WorkpaperSyncBridgeOptions) {
  const api = options.api ?? DEFAULT_API
  const state = ref<WorkpaperSyncBridgeState>('html_idle')
  const mode = ref<WorkpaperSyncBridgeMode>('html')
  const dirty = ref(false)
  const descriptor = ref<WorkpaperSyncEditorLaunchDescriptor | null>(null)
  const confirmation = ref<WorkpaperSyncDescriptorConfirmation | null>(null)
  const operation = ref<WorkpaperSyncOperationSnapshot | null>(null)
  const recoveryCases = ref<readonly WorkpaperSyncRecoveryCase[]>([])
  const activeRecoveryCaseId = ref<string | null>(null)
  const conflicts = ref<Record<string, unknown> | null>(null)
  const lastError = ref<WorkpaperSyncBridgeError | null>(null)
  const transitions = ref<readonly WorkpaperSyncBridgeEvent[]>([])
  const migration = ref<WorkpaperSyncModeMigration | null>(null)

  /** 202 回执里的 requested operation id —— duplicate 之后所有调用仍用它。 */
  const requestedOperationId = ref<string | null>(null)
  const pendingMutationToken = ref<string | null>(null)
  /** canonical application 的 fold 观测面（AC 5.10 的 same-app 单调 fold）。 */
  const canonicalApplicationId = ref<string | null>(null)
  const applicationEffectiveSequence = ref<number | null>(null)
  const mountCallCount = ref(0)
  const forcesaveCallCount = ref(0)
  /**
   * `leaveRoom` 的调用次数。
   *
   * 🔴 存在的理由是判据可观测性：`leaveWithoutSaving()` 刻意**吞掉** leave 的失败（见那里
   * 的说明），于是「有没有真的发出过那一次 leave」不能从 `lastError` 看出来。有这个计数
   * 之后，「恰一次 leave」与「零次 forcesave / 零次 close-intent」是同一份判据里三个
   * 同等可测的数（AC 4.5）。
   */
  const leaveCallCount = ref(0)
  /**
   * 后端 forcesave 202 给的轮询节奏（`poll_after_ms`，当前 500）。
   *
   * 桥自己**不**用它（桥被动、不起定时器），但必须把它**透出去**给宿主的 operation
   * 推进器用。此前它被 DTO 解析后就地丢弃 —— 后端给了节奏、前端没人接，正是
   * 「保存后永久转圈」这条缺陷的一部分。
   */
  const pollAfterMs = ref<number | null>(null)

  function scope(): WorkpaperSyncEntryScope {
    return {
      projectId: options.projectId.value,
      wpId: options.wpId.value,
      entryId: options.entryId.value,
    }
  }

  function sheetKey(): string {
    return options.sheetKey?.value?.trim() || 'default'
  }

  // ── 4.1 转换入口（唯一写 state/mode 的地方）

  function apply(
    event: WorkpaperSyncBridgeEvent,
    context: WorkpaperSyncBridgeTransitionContext = {},
  ): WorkpaperSyncBridgeState {
    // 非法转换在这里抛，`state`/`mode` 两个 ref 一个都没被写过（Property 46 后半）。
    const result = transitionBridgeState(state.value, event, mode.value, context)
    state.value = result.to
    mode.value = result.mode
    transitions.value = [...transitions.value, event]
    return result.to
  }

  /** 用户显式发起一次新尝试：只有这里允许清掉 sticky error（Property 48）。 */
  function beginAttempt(): void {
    lastError.value = null
  }

  /**
   * 请求被去重层取消（切页签竞态，见 `isRequestCanceled`）：这不是失败，是一次被
   * 上层新请求作废的在飞尝试。处理成「干净退回 HTML」——
   *
   * * **不写 `lastError`**：否则 sticky error 遮罩（Property 48）永不消退；
   * * 用 `identity_rejected` 把状态从 `flushing`/`committing`/`materializing` 退回
   *   `html_idle`（这三态在 `DETERMINISTIC_EDGES` 里都有这条边）——若原样停在
   *   `flushing`，下一次点「在线编辑」发的 `flush_started` 会因非法转换抛错；
   * * 最后 `throw` 原异常，宿主 `switchRenderMode` 的空 catch 吞掉即保持 HTML 态。
   */
  function recoverFromCanceled(error: unknown): never {
    try {
      apply('identity_rejected')
    } catch {
      // 已不在 in-flight 态（terminal / 已回 html_idle）：状态不动即可。
    }
    throw error
  }

  function fail(stage: string, error: unknown): never {
    if (isRequestCanceled(error)) {
      recoverFromCanceled(error)
    }
    const described = describeBridgeFailure(stage, error)
    lastError.value = described
    // `sync_failed` 在当前状态不合法时，宁可保留原状态也不越表 —— 表就是判据。
    try {
      apply('sync_failed')
    } catch {
      // 已在 terminal / error 上：状态不动，`lastError` 仍然被记住（sticky）。
    }
    throw error
  }

  // ── 4.2 HTML → OO

  /**
   * flush → pending mutation → 单次 content commit（materialize）→ 消费 descriptor。
   *
   * **不挂载编辑器**：返回 descriptor 之后状态是 `oo_loading`，宿主（Task 33）拿到
   * `descriptor` 才创建 DocEditor，创建完调 `notifyEditorMounted()`。
   */
  async function switchToOnlyOffice(): Promise<WorkpaperSyncEditorLaunchDescriptor> {
    if (!supportedModesForCapability(options.capability).includes('oo')) {
      refuse(
        'bridge_mode_not_supported',
        `capability=${options.capability} 不支持 OnlyOffice 模式 —— 模式开关不得打开它`,
      )
    }
    beginAttempt()
    apply('flush_started')
    let flushed: WorkpaperSyncFlushResult
    try {
      flushed = await options.flushHtml()
    } catch (error) {
      return fail('flush', error)
    }
    let token: string
    let pendingKey: string
    try {
      const receipt = await api.createPendingMutation(scope(), {
        sheetKey: flushed.sheetKey ?? sheetKey(),
        expectedRevision: flushed.expectedRevision,
        projection: flushed.projection,
        clientEditEpoch: flushed.clientEditEpoch,
      })
      token = receipt.pendingMutationToken
      pendingKey = receipt.idempotencyKey
      pendingMutationToken.value = token
    } catch (error) {
      return failIdentityOrSync('pending_mutation', error)
    }
    apply('pending_mutation_created')

    let received: WorkpaperSyncEditorLaunchDescriptor
    try {
      received = await api.materialize(scope(), {
        sheetKey: flushed.sheetKey ?? sheetKey(),
        expectedRevision: flushed.expectedRevision,
        pendingMutationToken: token,
        projection: flushed.projection,
        clientEditEpoch: flushed.clientEditEpoch,
        // 🔴 与 pending-mutation 同源 Idempotency-Key：token 已冻结该 key，
        // materialize 再 new 一把会 409 materialize_idempotency_key_mismatch。
        idempotencyKey: pendingKey,
      })
    } catch (error) {
      return failIdentityOrSync('materialize', error)
    }
    // pending token 是**单次逻辑消费**（AC 3.1）：materialize 成功即作废本地副本，
    // 留着它会让「失败后重试」误用一个已消费的 token 并拿到 409。
    pendingMutationToken.value = null
    apply('descriptor_received')
    descriptor.value = received
    apply('descriptor_accepted')
    return received
  }

  /**
   * token / bundle identity 类失败**停留 HTML**；其余失败按普通同步失败处理。
   *
   * 判据来自 `classifySyncFailure`：`launch_descriptor_stale_identity` 与
   * `launch_descriptor_substrate_stale` 三门全关，`pending_mutation_token_*` 是 409
   * 且不可重试 —— 两类都不得让编辑器打开。
   */
  function failIdentityOrSync(stage: string, error: unknown): never {
    if (isRequestCanceled(error)) {
      recoverFromCanceled(error)
    }
    const described = describeBridgeFailure(stage, error)
    lastError.value = described
    const identityFailure =
      described.staleIdentity || described.errorCode.startsWith('pending_mutation_token_')
    try {
      apply(identityFailure ? 'identity_rejected' : 'sync_failed')
    } catch {
      // 当前状态不接受该事件：保持原状态，错误仍然 sticky。
    }
    throw error
  }

  /** 宿主创建完 DocEditor 后上报（Task 33 的唯一入口）。 */
  function notifyEditorMounted(): void {
    mountCallCount.value += 1
    apply('editor_mounted')
  }

  /**
   * 真实 `onDocumentReady` 之后 **await** confirm-descriptor。
   *
   * 确认成功之前既不进 `oo_editing` 也不解锁 forcesave（Property 11 后半）。
   * 服务端 `forcesave_unlocked=false` 时同样**不**进入 editing —— 那是一份「已确认但
   * 不可写」的确认（只读 participant），把它读成可编辑就是最贵的假绿。
   */
  async function notifyDocumentReady(): Promise<WorkpaperSyncDescriptorConfirmation> {
    const current = descriptor.value
    if (!current) {
      refuse(
        'bridge_ready_without_descriptor',
        'onDocumentReady 早于 descriptor —— descriptor 是编辑器唯一 config 来源',
      )
    }
    apply('document_ready')
    let confirmed: WorkpaperSyncDescriptorConfirmation
    try {
      confirmed = await api.confirmDescriptor(scope(), {
        descriptor: current,
        confirmPayload: buildDescriptorConfirmPayload(current),
      })
    } catch (error) {
      return failIdentityOrSync('confirm_descriptor', error)
    }
    if (!confirmed.forcesaveUnlocked) {
      confirmation.value = confirmed
      return failIdentityOrSync('confirm_descriptor', {
        response: {
          status: 409,
          data: {
            detail: {
              error_code: 'launch_descriptor_stale_identity',
              message: '服务端未解锁强制保存：该确认不可写，编辑器不得进入可编辑状态',
            },
          },
        },
      })
    }
    confirmation.value = confirmed
    apply('descriptor_confirmed')
    return confirmed
  }

  const canForcesave = computed(
    () =>
      WP_BRIDGE_FORCESAVE_READY_STATES.includes(state.value) &&
      confirmation.value?.forcesaveUnlocked === true,
  )

  // ── 4.3 OO → HTML

  /**
   * 冻结 forcesave request → 命令受理 → 跟踪两 link 均空的 shell。
   *
   * 🔴 `forcesave_accepted` 之后**必须**经 `shell_tracking_started` 才能继续：
   * 转换表里 `forcesave_accepted` 没有 `operation_observed` 出边，所以
   * 「跳过 shell 阶段直接显示 application-bound」在结构上不可达（AC 4.1 / Property 12）。
   */
  async function switchToHtml(): Promise<void> {
    if (!canForcesave.value) {
      refuse(
        'bridge_forcesave_before_confirmation',
        `state=${state.value} 且 forcesave_unlocked=${String(
          confirmation.value?.forcesaveUnlocked,
        )} —— 未拿到 confirm-descriptor 成功响应前不得 forcesave`,
      )
    }
    const current = descriptor.value
    if (!current) {
      refuse('bridge_forcesave_without_descriptor', 'forcesave 缺 descriptor 身份')
    }
    beginAttempt()
    apply('forcesave_started')
    let accepted
    try {
      forcesaveCallCount.value += 1
      accepted = await api.requestForcesave(scope(), {
        roomId: current.roomId,
        participantId: current.participantId,
        expectedWriteFenceEpoch: current.writeFenceEpoch,
      })
    } catch (error) {
      return fail('forcesave', error)
    }
    requestedOperationId.value = accepted.operationId
    pollAfterMs.value = accepted.pollAfterMs
    if (accepted.dispatchError !== null) {
      // request 已冻结、shell 已建，但 Command Service 未受理 ⇒ 保持 OO 并允许重试
      // （AC 4.4）。这一步**不是** error：request 是真的冻结了，文案必须区分。
      apply('forcesave_dispatch_failed')
      lastError.value = describeBridgeFailure('forcesave_dispatch', {
        response: {
          status: 502,
          data: {
            detail: { error_code: accepted.dispatchError, message: '强制保存命令未被受理' },
          },
        },
      })
      return
    }
    // 🔴 2026-09-22：后端明确说「这次不会再有 callback」时**不得**进 `waiting_application`。
    //
    // `request_forcesave` 对 CS 的 `terminal_without_callback`（`no_changes` /
    // `doc_not_online` / `configuration_error` / `implementation_defect`）已经
    // `terminate_without_callback` 就地终结 request+shell，并在 202 里回传
    // `callback_expected=false`。此前前端不读这个字段，于是照样 `shell_tracking_started`
    // → `waiting_application` 干等一个后端已经宣告不会来的 callback。最常见触发路径是
    // **用户进 OO 什么都没改就点保存**（CS 返 `no_changes`），真栈实测永久转圈。
    //
    // 落到 `forcesave_frozen`（`forcesave_dispatch_failed` 的目标态）而不是 `error`：
    // request 确实冻结成功了、OO 会话仍然健康、用户改点东西再存就能成 —— 这正是
    // `forcesave_frozen` 的语义（保持 OO、允许重试）。具体原因走 `lastError`，
    // 它在 `feedback` 里优先级最高，用户看到的是人话而不是笼统的「未被受理」。
    if (accepted.callbackExpected === false) {
      apply('forcesave_dispatch_failed')
      lastError.value = describeBridgeFailure('forcesave_dispatch', {
        response: {
          status: 409,
          data: {
            detail: {
              error_code: `forcesave_${accepted.csOutcome ?? 'terminal_without_callback'}`,
              message: forcesaveTerminalMessage(accepted.csOutcome, accepted.csError),
            },
          },
        },
      })
      return
    }
    apply('forcesave_command_accepted')
    apply('shell_tracking_started', { requestedOperationId: accepted.operationId })
    // 🔴 到此**刻意**结束：桥是被动的，不自己发定时器/不自己订 SSE。
    //    推进 `waiting_application` 的责任在宿主（`WorkpaperSyncEditorHost.vue` 用
    //    `WorkpaperSyncOperationTracker` 喂 `ingestOperationSnapshot`）——它持有组件
    //    生命周期，能保证定时器随卸载停掉。
    //
    //    这条分工不是洁癖：桥若自己轮询，`switchToHtml()` 就会多打一次 operation GET，
    //    而本 spec 的独立回归（T69-I27「整趟端点多重集恰为三项」等 10 条）正是按
    //    「桥只在被调用时发请求」建立的判据 —— 桥自轮询会把那批判据全部打红，
    //    等于用改判据来迁就实现。2026-09-22 первый版把 tracker 放进桥，实测打红 10 条后
    //    移到宿主，判据零改动。
    //
    //    🔴 曾经的缺陷正是「两边都没接」：宿主没接 tracker、桥也不轮询，于是保存后 UI
    //    永远停在「已发送强制保存，等待 OnlyOffice 回传文件」，而服务端早已 applied
    //    （真栈证据：`operation.state=applied` / `application.state=applied`，
    //    而 `host_status` 一直是那句等待文案）。
  }

  /** `terminal_without_callback` 的人话文案（按 CS 语义分型，不压成一句）。 */
  function forcesaveTerminalMessage(outcome: string | null, code: number | null): string {
    const suffix = code === null ? '' : `（Command Service 返回码 ${code}）`
    switch (outcome) {
      case 'no_changes':
        return `文档没有检测到改动，本次无需保存${suffix}。若确实改过，请在编辑器内先点一下单元格外的空白处让改动生效，再重新保存。`
      case 'doc_not_online':
        return `编辑会话已不在线，无法保存${suffix}。请退出在线编辑后重新进入，再保存。`
      case 'configuration_error':
        return `OnlyOffice 服务配置异常，保存命令无法执行${suffix}。请联系管理员检查 OnlyOffice 配置。`
      default:
        return `强制保存已终结且不会有回传${suffix}：${outcome ?? '未知原因'}。`
    }
  }

  /**
   * 吃进一份 operation 快照。
   *
   * `duplicate` 是 terminal：进入后转换表不再接受 `operation_observed`，于是
   * 「duplicate 又被推成 applied」在结构上不可达。requested/canonical 两个 id 都保留。
   */
  function ingestOperationSnapshot(snapshot: WorkpaperSyncOperationSnapshot): void {
    const requested = requestedOperationId.value
    if (requested !== null && snapshot.requestedOperationId !== requested) {
      refuse(
        'bridge_operation_identity_drift',
        `观测到的 requested operation ${snapshot.requestedOperationId} ≠ 本次冻结的 ` +
          `${requested} —— 桥必须沿同一 requested operation 推进，不得跟错一条`,
      )
    }
    observeApplicationFence({
      applicationId: snapshot.applicationId,
      effectiveRequestSequence: applicationEffectiveSequence.value,
    })
    apply('operation_observed', { operation: snapshot })
    operation.value = snapshot
    // 🔴 落 `error` 时必须把**真因**摆出来。快照的 `errorCode` 在 post-durable 路径上
    // 恒为 null（`apply_durable_incoming` durable 之后刻意不抛，失败只落 application
    // 事件流），此前界面因此只剩一句「同步失败」——真栈实测：往 amount 列填了文本，
    // `excel_materialize_editable_write_failed` 全程只在后端日志里，用户无从下手。
    // 后端已按读侧投影补上 application_error_* 三项（中文措辞单源在后端），这里只是把它
    // 接到 `lastError`（`feedback` 里优先级最高），不做任何码→文案的二次映射。
    if (state.value === 'error') {
      const code = snapshot.applicationErrorCode ?? snapshot.errorCode
      if (code !== null) {
        lastError.value = describeBridgeFailure('apply', {
          response: {
            status: 422,
            data: {
              detail: {
                error_code: code,
                message: snapshot.applicationErrorMessage ?? `回写失败：${code}`,
              },
            },
          },
        })
      }
    }
  }

  /**
   * same-application 的 sequence fold（AC 5.10）。
   *
   * 同一 canonical application 的**更高** sequence 只单调 fold，**不**把 primary/conflict
   * 显示成 stale；只有 canonical application **不同**才要求重载新基线。
   */
  function observeApplicationFence(input: {
    readonly applicationId: string | null
    readonly effectiveRequestSequence: number | null
  }): { readonly folded: boolean; readonly rebased: boolean } {
    if (input.applicationId === null) return { folded: false, rebased: false }
    const known = canonicalApplicationId.value
    if (known !== null && known !== input.applicationId) {
      canonicalApplicationId.value = input.applicationId
      applicationEffectiveSequence.value = input.effectiveRequestSequence
      // 不同 canonical application ⇒ superseded/rebase，需重载编辑器确认新基线。
      if (state.value !== 'refresh_required') {
        apply('operation_observed', {
          operation: { ...(operation.value as WorkpaperSyncOperationSnapshot), state: 'superseded' },
        })
      }
      return { folded: false, rebased: true }
    }
    canonicalApplicationId.value = input.applicationId
    const previous = applicationEffectiveSequence.value
    const next = input.effectiveRequestSequence
    if (next !== null) {
      applicationEffectiveSequence.value = previous === null ? next : Math.max(previous, next)
    }
    return { folded: previous !== null && next !== null && next > previous, rebased: false }
  }

  /** applied 后按 result revision 重载（Property 14）。 */
  async function reloadAfterApplied(): Promise<void> {
    if (state.value !== 'applied') {
      refuse(
        'bridge_reload_before_applied',
        `state=${state.value} 时不得重载 —— 只有 applied 才有 result revision 可校验`,
      )
    }
    const revision = operation.value?.resultRevision ?? null
    if (revision === null) {
      refuse(
        'bridge_reload_without_result_revision',
        'applied 快照缺 result_revision —— 无最小 revision 可校验时重载等于伪造完成',
      )
    }
    try {
      await options.reloadHtml(revision)
    } catch (error) {
      return fail('reload', error)
    }
    apply('reload_completed')
    descriptor.value = null
    confirmation.value = null
    dirty.value = false
  }

  // ── 4.4 duplicate 也走同一条：requested id 授权 → 服务端 canonicalize

  function operationIdForCalls(): string {
    const requested = requestedOperationId.value ?? operation.value?.requestedOperationId ?? ''
    if (String(requested).trim() === '') {
      refuse(
        'bridge_no_requested_operation',
        '没有 requested operation 可查 —— claim 前的 recovery case 三实体为 0',
      )
    }
    return requested
  }

  /** 重新读一次快照。duplicate 时仍按 requested id 发起（服务端先授权后 canonicalize）。 */
  /**
   * 只**取**一份 operation 快照，不动任何状态。
   *
   * 🔴 2026-09-22 新增，供宿主的 operation 追踪器用。为什么不让追踪器自己打端点：
   * `WorkpaperSyncOperationTracker` 的 `poll` 默认直接调模块级 `getOperation`，那是
   * **第二条 api 通道** —— 绕过桥注入的 `api`，于是拦截器/鉴权/测试替身全都不一致
   * （实测表现为：测试注入的 api stub 明明排好了响应，追踪器却去打真实端点）。
   * 追踪器改用本函数后，全链路只有一条 api 通道。
   *
   * 与 {@link refreshOperation} 的分工：本函数**只读**；要不要把快照喂进状态机由调用方
   * 显式调 {@link ingestOperationSnapshot} 决定。两件事分开才能让追踪器在 `duplicate`
   * 这类 terminal 上只更新投影而不推状态。
   */
  async function fetchOperationSnapshot(
    operationId: string,
  ): Promise<WorkpaperSyncOperationSnapshot> {
    return api.getOperation(scope(), operationId)
  }

  async function refreshOperation(): Promise<WorkpaperSyncOperationSnapshot> {
    const id = operationIdForCalls()
    let snapshot: WorkpaperSyncOperationSnapshot
    try {
      snapshot = await api.getOperation(scope(), id)
    } catch (error) {
      return fail('get_operation', error)
    }
    assertNoNewCanonicalIdentity(snapshot)
    if (state.value === 'duplicate') {
      // terminal：只更新投影，不动状态。
      operation.value = snapshot
      return snapshot
    }
    ingestOperationSnapshot(snapshot)
    return snapshot
  }

  /**
   * duplicate 的读路径不得**新建** operation/application。
   *
   * 服务端 canonicalize 到的 primary 必须始终是同一个；换了一个 canonical id 或
   * canonical primary 没绑 application，都说明读路径走错了分支。
   */
  function assertNoNewCanonicalIdentity(snapshot: WorkpaperSyncOperationSnapshot): void {
    const known = operation.value
    if (known === null) return
    if (known.shape !== 'duplicate') return
    if (snapshot.canonicalOperationId !== known.canonicalOperationId) {
      refuse(
        'bridge_duplicate_recanonicalized',
        `duplicate 的 canonical primary 从 ${known.canonicalOperationId} 变成 ` +
          `${snapshot.canonicalOperationId} —— duplicate 的后续调用不得新建 operation`,
      )
    }
  }

  async function fetchConflicts(
    input: { readonly includeSuperseded?: boolean } = {},
  ): Promise<Record<string, unknown>> {
    const id = operationIdForCalls()
    let preview: Record<string, unknown>
    try {
      preview = await api.getOperationConflicts(scope(), id, input)
    } catch (error) {
      return fail('get_conflicts', error)
    }
    conflicts.value = preview
    const applicationId = preview.canonical_application_id
    const sequence = preview.incoming_sequence
    if (typeof applicationId === 'string') {
      observeApplicationFence({
        applicationId,
        effectiveRequestSequence: typeof sequence === 'number' ? sequence : null,
      })
    }
    return preview
  }

  async function fetchTimeline(
    input: { readonly limit?: number } = {},
  ): Promise<Record<string, unknown>> {
    try {
      return await api.getOperationTimeline(scope(), operationIdForCalls(), input)
    } catch (error) {
      return fail('get_timeline', error)
    }
  }

  /**
   * 普通 retry：只对**已有** operation 从 durable incoming 恢复。
   *
   * `operationIdForCalls()` 在没有 requested operation 时先拒绝，
   * `api.retryOperation()` 再拒绝空串 —— 两层各有自己的码，claim 前的 recovery case
   * 不可能走到这里（AC 5.8 末句）。
   */
  async function retryOperation(): Promise<Record<string, unknown>> {
    beginAttempt()
    const id = operationIdForCalls()
    try {
      return await api.retryOperation(scope(), id)
    } catch (error) {
      return fail('retry_operation', error)
    }
  }

  /**
   * 提交冲突裁决。fence 六项由调用方（Task 34 的冲突面板）**完整**给出。
   *
   * 🔴 `room_latest_durable_application_id` / `room_latest_durable_sequence` 在当前
   * 16 条用户路由里**没有**任何读取面（conflict preview 只给 `canonical_application_id`
   * 与 `incoming_sequence`）。桥因此**拒绝**替调用方编这两项 —— 用 canonical application
   * 顶替 room 的 latest durable 等于客户端断言了一个它观测不到的 room 事实，
   * 而服务端会照着这个断言做 fence 裁决。这是一处已登记的上游缺口。
   */
  async function resolveConflicts(input: {
    readonly fence: WorkpaperSyncResolveFence
    readonly resolutions: readonly { conflictId: string; choice: string; value?: unknown }[]
  }): Promise<Record<string, unknown>> {
    const fence = input.fence
    const missing = (
      [
        'canonicalApplicationId',
        'applicationEffectiveRequestSequence',
        'roomLatestDurableApplicationId',
        'roomLatestDurableSequence',
        'conflictSetDigest',
        'expectedCurrentRevision',
        'roomGeneration',
        'clientEditEpoch',
      ] as const
    ).filter((key) => fence[key] === undefined || fence[key] === null || fence[key] === '')
    if (missing.length > 0) {
      refuse(
        'bridge_resolve_fence_incomplete',
        `resolve 的 fence 缺 [${missing.join(', ')}] —— 桥不替调用方编 room fence，` +
          '缺项只能 fail visible',
      )
    }
    beginAttempt()
    try {
      return await api.resolveConflicts(scope(), {
        operationId: operationIdForCalls(),
        expectedCurrentRevision: fence.expectedCurrentRevision,
        roomGeneration: fence.roomGeneration,
        clientEditEpoch: fence.clientEditEpoch,
        canonicalApplicationId: fence.canonicalApplicationId,
        applicationEffectiveRequestSequence: fence.applicationEffectiveRequestSequence,
        roomLatestDurableApplicationId: fence.roomLatestDurableApplicationId,
        roomLatestDurableSequence: fence.roomLatestDurableSequence,
        conflictSetDigest: fence.conflictSetDigest,
        resolutions: input.resolutions,
      })
    } catch (error) {
      return fail('resolve_conflicts', error)
    }
  }

  // ── 4.5 recovery（authorization-first）

  function roomScopeForRecovery(input?: {
    readonly roomId?: string
    readonly generation?: number
  }): { roomId: string; generation: number } {
    const roomId = input?.roomId ?? descriptor.value?.roomId ?? ''
    const generation = input?.generation ?? descriptor.value?.generation ?? null
    if (String(roomId).trim() === '' || generation === null || !Number.isInteger(generation)) {
      refuse(
        'bridge_recovery_room_scope_required',
        'listRecoveryCases 必须显式携带 room_id 与 generation（AC 10.6）—— ' +
          'crash 重开时没有 descriptor，宿主必须自己给',
      )
    }
    return { roomId: String(roomId), generation }
  }

  async function listRecoveryCases(input?: {
    readonly roomId?: string
    readonly generation?: number
  }): Promise<readonly WorkpaperSyncRecoveryCase[]> {
    const room = roomScopeForRecovery(input)
    try {
      const list = await api.listRecoveryCases(scope(), room)
      recoveryCases.value = list.cases
      const claimable = list.cases.find((item) => item.state === 'unclaimed')
      if (claimable) {
        activeRecoveryCaseId.value = claimable.caseId
        if (state.value !== 'recovery_pending') {
          // 三实体必须全空才允许进入 —— DTO 已在解析时校验过，这里再交叉一次，
          // 因为「进入 recovery_pending」是唯一会让 UI 显示「认领/仅下载」的地方。
          apply('recovery_case_observed', {
            recoveryEntities: {
              forcesaveRequestId: claimable.forcesaveRequestId,
              applicationId: claimable.applicationId,
              operationId: claimable.operationId,
            },
          })
        }
      }
      return list.cases
    } catch (error) {
      return fail('list_recovery_cases', error)
    }
  }

  /**
   * authorization-first claim。**成功后才**同时关联三实体并进入 primary/duplicate 终态。
   *
   * 客户端侧的三条前置（服务端还会再验一遍，但缺口见下）：
   *
   * 1. `priorConfirmationId` 必须来自本 case 的 `candidatePriorConfirmations` ——
   *    claim 只能引用**同 room/generation 的 prior confirmed descriptor**（AC 5.8），
   *    客户端不得指定任意 base；
   * 2. `expectedDefinitionBundleSha256` 必须是合法 digest；
   * 3. `expectedGeneration` / `expectedWriteFence` 必须是非负整数。
   *
   * 🔴 已登记的上游缺口：服务端 `claim_recovery_case` 只读
   * `room_id / prior_confirmation_id / participant_id / expected_current_revision`，
   * design 规定的 `expected_generation / expected_write_fence /
   * expected_definition_bundle_sha256` **声明了但从不校验**。因此「错误 bundle/fence
   * 被拒 ⇒ 三实体保持为 0」这条只能由服务端补齐后才成立；桥这一侧能做到的是
   * **发出前**就拒绝形态非法的值，并在 claim 失败时保持三实体为 0。
   */
  async function claimRecoveryCase(input: {
    readonly caseId: string
    readonly roomId: string
    readonly participantId: string
    readonly priorConfirmationId: string
    readonly expectedGeneration: number
    readonly expectedWriteFence: number
    readonly expectedDefinitionBundleSha256: string
    readonly expectedCurrentRevision: number
  }): Promise<void> {
    const target = recoveryCases.value.find((item) => item.caseId === input.caseId)
    if (!target) {
      refuse(
        'bridge_claim_case_unknown',
        `case ${input.caseId} 不在已授权列出的 recovery 列表内 —— claim 只能针对 ` +
          'authorization-first 列出的 case',
      )
    }
    const candidate = target.candidatePriorConfirmations.find(
      (item) => item.confirmationId === input.priorConfirmationId,
    )
    if (!candidate) {
      refuse(
        'bridge_claim_prior_confirmation_not_candidate',
        `prior confirmation ${input.priorConfirmationId} 不在本 case 的候选内 —— ` +
          '客户端不得指定任意 base',
      )
    }
    if (!isSyncDigest(input.expectedDefinitionBundleSha256)) {
      refuse(
        'bridge_claim_bundle_digest_invalid',
        `expected_definition_bundle_sha256=${JSON.stringify(
          input.expectedDefinitionBundleSha256,
        )} 非法 —— claim 必须冻结非空 immutable definition bundle`,
      )
    }
    if (
      !Number.isInteger(input.expectedGeneration) ||
      input.expectedGeneration < 1 ||
      !Number.isInteger(input.expectedWriteFence) ||
      input.expectedWriteFence < 0
    ) {
      refuse(
        'bridge_claim_fence_invalid',
        `expected_generation=${input.expectedGeneration} / expected_write_fence=` +
          `${input.expectedWriteFence} 形态非法`,
      )
    }
    beginAttempt()
    apply('recovery_claim_started', {
      recoveryEntities: {
        forcesaveRequestId: target.forcesaveRequestId,
        applicationId: target.applicationId,
        operationId: target.operationId,
      },
    })
    let claim
    try {
      claim = await api.claimRecoveryCase(scope(), input)
    } catch (error) {
      const described = describeBridgeFailure('claim_recovery_case', error)
      lastError.value = described
      // claim 失败：三实体仍为 0，回 pending 而不是进 operation 流程。
      apply('recovery_claim_failed', {
        recoveryEntities: {
          forcesaveRequestId: null,
          applicationId: null,
          operationId: null,
        },
      })
      throw error
    }
    // 🔴 claim 的 202 响应体只有 `case_id / forcesave_request_id / operation_id /
    // application_id / state` —— **没有** shape，也没有 duplicate 指针。而 claim 既可能
    // 新建 application（primary），也可能命中既有同 key application 并落成 direct
    // terminal duplicate（服务端 `outcome.shape` 分得清，只是没投影出来）。
    // 因此这里**读一次 operation** 让服务端自己说形态，绝不默认 `'primary'`：
    // 默认值会把「命中既有 application 的 duplicate」显示成 primary application-bound，
    // 而那正是 AC 5.8 要求区分的两个终态。
    let landed: WorkpaperSyncOperationSnapshot
    try {
      landed = await api.getOperation(scope(), claim.operationId)
    } catch (error) {
      // claim 已成功（三实体确实存在），但形态未知 ⇒ fail visible，不猜一个终态。
      return fail('claim_shape_probe', error)
    }
    if (landed.requestedOperationId !== claim.operationId) {
      refuse(
        'bridge_claim_operation_identity_drift',
        `claim 返回 operation ${claim.operationId}，读回来的 requested id 却是 ` +
          `${landed.requestedOperationId}`,
      )
    }
    if (landed.shape === 'pre_correlation') {
      refuse(
        'bridge_claim_landed_pre_correlation',
        'claim 成功后 operation 仍是两 link 均空的 shell —— claim 必须在同一事务内 ' +
          '创建/命中 application 并绑定 shell（AC 5.8）',
      )
    }
    requestedOperationId.value = claim.operationId
    canonicalApplicationId.value = claim.applicationId
    activeRecoveryCaseId.value = claim.caseId
    operation.value = landed
    apply('recovery_claim_succeeded', {
      claimedEntities: {
        forcesaveRequestId: claim.forcesaveRequestId,
        applicationId: claim.applicationId,
        operationId: claim.operationId,
      },
      claimedShape: landed.shape,
    })
  }

  /** 仅下载并终结 case：三实体恒 0，独立终态，**不得**转 applied。 */
  async function terminateRecoveryDownloadOnly(caseId: string): Promise<string> {
    beginAttempt()
    try {
      const receipt = await api.terminateRecoveryDownloadOnly(scope(), caseId)
      apply('recovery_download_only_terminated', {
        recoveryEntities: {
          forcesaveRequestId: null,
          applicationId: null,
          operationId: null,
        },
      })
      activeRecoveryCaseId.value = receipt.caseId
      return receipt.downloadClaim
    } catch (error) {
      return fail('terminate_download_only', error)
    }
  }

  /** download-only 签发的 claim 的唯一消费方。终态下调用，不改状态。 */
  async function downloadRecoveryArtifact(input: {
    readonly caseId: string
    readonly claim: string
  }) {
    try {
      return await api.downloadRecoveryArtifact(scope(), input)
    } catch (error) {
      return fail('download_recovery_artifact', error)
    }
  }

  async function fetchRecoveryCaseTimeline(
    caseId: string,
    input: { readonly limit?: number } = {},
  ): Promise<Record<string, unknown>> {
    try {
      return await api.getRecoveryCaseTimeline(scope(), caseId, input)
    } catch (error) {
      return fail('recovery_case_timeline', error)
    }
  }

  // ── 4.6 close 仲裁

  /** close leader 失权：先显示 authorization-stale，再等 successor 或 recovery。 */
  function notifyCloseAuthorizationLost(): void {
    apply('close_authorization_lost')
  }

  /** 有合法 successor 且其 capture 已完成。缺 successor intent id 时拒绝。 */
  function notifyCloseSuccessorApplied(successorIntentId: string): void {
    apply('close_successor_applied', { successorIntentId })
  }

  /** 无合法 successor：显式 recovery-required，不得渲染成保存成功或永久 loading。 */
  function notifyCloseNoSuccessor(): void {
    apply('close_no_successor')
  }

  // ── 4.7 rollback

  /** 只接受 opaque immutable UUID —— numeric revision 的拒绝在 API 层单点实现。 */
  async function rollbackVersion(input: {
    readonly versionId: string
    readonly expectedCurrentRevision: number
    readonly confirmed: boolean
  }): Promise<Record<string, unknown>> {
    beginAttempt()
    try {
      return await api.rollbackVersion(scope(), input)
    } catch (error) {
      return fail('rollback_version', error)
    }
  }

  // ── 4.8 localStorage 迁移 / 模式持久化

  function migrateMode(): WorkpaperSyncModeMigration {
    const result = migrateWorkpaperSyncMode(
      { entryId: options.entryId.value, wpId: options.wpId.value, sheetKey: sheetKey() },
      options.capability,
      { storage: options.storage },
    )
    migration.value = result
    return result
  }

  function persistMode(target: WorkpaperSyncBridgeMode): boolean {
    return persistWorkpaperSyncMode(
      { entryId: options.entryId.value, wpId: options.wpId.value, sheetKey: sheetKey() },
      options.capability,
      target,
      { storage: options.storage },
    )
  }

  const modeStorageKey = computed(() =>
    workpaperSyncModeKey({
      entryId: options.entryId.value,
      wpId: options.wpId.value,
      sheetKey: sheetKey(),
    }),
  )

  // ── 4.9 离开阻断

  const leaveBlockReason = computed<string | null>(() => {
    if (dirty.value) return '编辑器仍有未保存的修改'
    if (WP_BRIDGE_IN_FLIGHT_STATES.includes(state.value)) {
      return `同步进行中：${WP_BRIDGE_STATE_TEXT[state.value]}`
    }
    return null
  })
  const canLeave = computed(() => leaveBlockReason.value === null)

  /** 路由离开守卫（Task 33/34 的宿主把它接到 `onBeforeRouteLeave`）。 */
  function routeLeaveGuard(): boolean {
    return canLeave.value
  }

  function handleBeforeUnload(event: BeforeUnloadEvent): void {
    // 唯一消费方：下面 `addEventListener` 注册的正是本函数，判据据此断言
    // dirty/in-flight 时 `defaultPrevented === true`。
    if (routeLeaveGuard()) return
    event.preventDefault()
    // Chrome 仍要求 returnValue 非空才弹确认框。
    event.returnValue = leaveBlockReason.value ?? ''
  }

  const beforeUnloadInstalled = ref(false)
  if (options.installBeforeUnload !== false && typeof window !== 'undefined') {
    window.addEventListener('beforeunload', handleBeforeUnload)
    beforeUnloadInstalled.value = true
    if (getCurrentInstance()) {
      onBeforeUnmount(() => {
        window.removeEventListener('beforeunload', handleBeforeUnload)
        beforeUnloadInstalled.value = false
      })
    }
  }

  function destroy(): void {
    if (beforeUnloadInstalled.value && typeof window !== 'undefined') {
      window.removeEventListener('beforeunload', handleBeforeUnload)
      beforeUnloadInstalled.value = false
    }
  }

  // ── 4.10 反馈文案（Property 48 的 sticky error）

  const feedback = computed<{ kind: 'idle' | 'progress' | 'success' | 'error'; message: string }>(
    () => {
      // 🔴 error 优先于任何状态文案：一次真失败之后，后续清理/reload 成功也不得
      // 把它覆盖成成功文案（AC 11.10 / Property 48）。只有 `reset()` 或用户显式发起
      // 的新尝试（`beginAttempt`）才清掉它。
      if (lastError.value !== null) {
        return { kind: 'error', message: lastError.value.message || WP_BRIDGE_STATE_TEXT.error }
      }
      const text = WP_BRIDGE_STATE_TEXT[state.value]
      if (state.value === 'html_idle') return { kind: 'idle', message: text }
      if (state.value === 'applied') return { kind: 'success', message: text }
      if (state.value === 'oo_editing') return { kind: 'idle', message: text }
      return { kind: 'progress', message: text }
    },
  )

  /**
   * 未改动时离开 OnlyOffice，**不**走强制保存（用户点「结构化视图」的常态路径）。
   *
   * 三条安全前提（`dirty` 硬门 / in-flight 一律 refuse / 不发 forcesave 也不发
   * close-intent）与它们各自的真栈证据，写在 `workpaperSyncBridgeMachine.ts` 的
   * `clean_close_completed` 边上 —— 那里是这条边语义的单源；另见
   * `__tests__/cleanCloseWithoutSaving.spec.ts` 文件头。
   *
   * 🔴 2026-09-22 起它**恰发一个请求**：`leaveRoom`（服务端 `active/closing → left`）。
   * 在那条端点存在之前这里是纯本地转换，lease 只能等 `expires_at` 自然过期
   * （spec `oo-single-pass-materialize-and-room-leave` Requirement 4.5 的切换点）。
   * 判据面因此从「零请求」变成「**恰一次 leave、零次 forcesave、零次 close-intent**」。
   */
  async function leaveWithoutSaving(): Promise<void> {
    if (mode.value !== 'oo') return
    // 🔴 **一道门**：`canLeave` 已含 dirty 与 in-flight 两种阻断（`leaveBlockReason` 是这两条
    // 理由的单源）。首版在它前面另写了一次 `if (dirty)`，变异检验实测那是冗余（去掉照样绿）。
    // 两个 error_code 仍可分辨，前端据此决定提示「先保存」还是「稍等」。
    if (!canLeave.value) {
      refuse(
        dirty.value
          ? 'bridge_clean_close_with_dirty_editor'
          : 'bridge_clean_close_while_in_flight',
        `${leaveBlockReason.value} —— clean close 不得丢弃编辑或打断进行中的同步`,
      )
    }
    const current = descriptor.value
    if (current) {
      try {
        leaveCallCount.value += 1
        await api.leaveRoom(scope(), {
          roomId: current.roomId,
          participantId: current.participantId,
          // 走到这里 `canLeave` 必为真 ⇒ `dirty` 必为假。仍然**显式**把它送出去，而不是
          // 写死 `false`：服务端那道 dirty 门与本地这道同源（AC 4.4），传一个常量等于
          // 让服务端永远收不到会触发它的输入，那道门就变成了死代码。
          dirty: dirty.value,
        })
      } catch {
        // 🔴 leave 失败**不阻断**返回表单，也不记 `lastError`。
        //
        // 它是一次 lease 释放，不是内容操作：失败的唯一后果是这条 lease 退回到端点存在
        // 之前的形态 —— 按 `expires_at` 自然过期。拿它去挡用户返回结构化视图，会把一个
        // 「什么都没改」的常态路径变成红字（那正是本 spec Requirement 4 的起因形态）。
        // 判据 `网络整体不可用时仍能回表单` 两头锁住这一条。
      }
    }
    apply('clean_close_completed')
    descriptor.value = null
    confirmation.value = null
    requestedOperationId.value = null
    pendingMutationToken.value = null
    dirty.value = false
  }

  function reset(): void {
    apply('reset')
    lastError.value = null
    descriptor.value = null
    confirmation.value = null
    operation.value = null
    conflicts.value = null
    requestedOperationId.value = null
    pendingMutationToken.value = null
    canonicalApplicationId.value = null
    applicationEffectiveSequence.value = null
    dirty.value = false
  }

  function notifyDirty(next: boolean): void {
    dirty.value = next === true
  }

  /**
   * 宿主（Task 33）侧真实失败的**唯一**上报口。不抛 —— 调用点在 DocsAPI 回调里。
   *
   * 🔴 为什么必须有：`oo_loading` / `descriptor_mounted` 都在
   * `WP_BRIDGE_IN_FLIGHT_STATES` 里。宿主载不到 DocsAPI、config 被拒或 DocEditor
   * 构造抛错时，若没有上报口，桥就永远停在「正在打开 OnlyOffice 编辑器」：
   * 状态条显示进度、离开被阻断、而失败只存在于宿主局部 —— 正是 AC 11.10 禁止的
   * fail-open（真失败被非失败文案盖住）。本口把它变成 sticky `error`。
   *
   * 只收**桥自己不知道**的失败：桥内部已 `fail()` 过的（如 `notifyDocumentReady()`
   * 抛出的 confirm 失败）不得再报一次，否则会多记一次 `sync_failed` 转换。
   */
  function notifyHostFailure(stage: string, error: unknown): WorkpaperSyncBridgeError {
    const described = describeBridgeFailure(stage, error)
    lastError.value = described
    try {
      apply('sync_failed')
    } catch {
      // 当前状态不接受 `sync_failed`（三个 terminal / 已在 error）：状态不动，
      // `lastError` 仍然被记住 —— 与 `fail()` 的处理逐字一致。
    }
    return described
  }

  function notifyRecoveryCase(recoveryCase: WorkpaperSyncRecoveryCase): void {
    recoveryCases.value = [recoveryCase]
    activeRecoveryCaseId.value = recoveryCase.caseId
    apply('recovery_case_observed', {
      recoveryEntities: {
        forcesaveRequestId: recoveryCase.forcesaveRequestId,
        applicationId: recoveryCase.applicationId,
        operationId: recoveryCase.operationId,
      },
    })
  }

  return {
    // 只读投影
    state: readonly(state),
    mode: readonly(mode),
    dirty: readonly(dirty),
    capability: options.capability,
    descriptor: readonly(descriptor),
    confirmation: readonly(confirmation),
    operation: readonly(operation),
    recoveryCases: readonly(recoveryCases),
    activeRecoveryCaseId: readonly(activeRecoveryCaseId),
    conflicts: readonly(conflicts),
    lastError: readonly(lastError),
    transitions: readonly(transitions),
    migration: readonly(migration),
    requestedOperationId: readonly(requestedOperationId),
    canonicalApplicationId: readonly(canonicalApplicationId),
    applicationEffectiveSequence: readonly(applicationEffectiveSequence),
    mountCallCount: readonly(mountCallCount),
    forcesaveCallCount: readonly(forcesaveCallCount),
    leaveCallCount: readonly(leaveCallCount),
    pollAfterMs: readonly(pollAfterMs),
    /** 当前 entry scope（宿主的 operation 推进器要用它构造 tracker）。 */
    scope,
    canForcesave,
    canLeave,
    leaveBlockReason,
    leaveWithoutSaving,
    feedback,
    modeStorageKey,
    beforeUnloadInstalled: readonly(beforeUnloadInstalled),
    // HTML → OO
    switchToOnlyOffice,
    notifyEditorMounted,
    notifyDocumentReady,
    // OO → HTML
    switchToHtml,
    ingestOperationSnapshot,
    observeApplicationFence,
    fetchOperationSnapshot,
    refreshOperation,
    reloadAfterApplied,
    fetchConflicts,
    fetchTimeline,
    retryOperation,
    resolveConflicts,
    // recovery
    listRecoveryCases,
    claimRecoveryCase,
    terminateRecoveryDownloadOnly,
    downloadRecoveryArtifact,
    fetchRecoveryCaseTimeline,
    // close 仲裁
    notifyCloseAuthorizationLost,
    notifyCloseSuccessorApplied,
    notifyCloseNoSuccessor,
    // 其它
    rollbackVersion,
    migrateMode,
    persistMode,
    routeLeaveGuard,
    notifyDirty,
    notifyRecoveryCase,
    notifyHostFailure,
    reset,
    destroy,
    /** 表自证（判据用；不参与运行时行为）。 */
    auditMachine: auditBridgeMachine,
    projectOperation: bridgeStateForOperation,
  }
}

export type WorkpaperSyncBridge = ReturnType<typeof useWorkpaperSyncBridge>
