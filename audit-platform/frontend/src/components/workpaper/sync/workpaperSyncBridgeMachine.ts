/**
 * 底稿 HTML ↔ OnlyOffice 双向回写的**桥状态机**（纯函数，零副作用）。
 *
 * spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 32
 * Requirements: 3.1, 3.6, 3.7, 4.1, 4.2, 4.4, 4.5, 4.6, 4.7, 4.8, 5.8, 11.1, 11.2,
 *               11.3, 11.6, 11.8, 11.10, 14.8
 * Properties: P10 / P12 / P13 / P14 / P15 / P46 / P48（本模块是 P46 的判据面）
 *
 * ═══ 为什么状态机要单独成模块 ═══
 *
 * Property 46 要求「随机事件序列只能进入声明状态；非法转换抛显式错误且不改变 mode」。
 * 把转换表和 Vue 的 `ref` / HTTP 调用混在一个 composable 里，随机序列判据就必须挂载
 * 组件才能跑，于是「非法转换是否真被拒」这条最贵的判据会被 mock 的形状左右。
 * 本模块只有**声明表 + 纯函数**，所以判据可以逐条穷举。
 *
 * ═══ 转换合法性 = 一张显式邻接表 ═══
 *
 * 🔴 刻意**不用**「rank 单调前进」这类通用规则。本 spec 的变异运行反复证明：一条
 * 「只要往前就放行」的规则会让绝大多数非法转换判据变成空操作（`applied → merging`
 * 被拦住，而真正致命的 `recovery_download_only → applied`、`oo_editing → applied`
 * 恰好也「往前」）。邻接表冗长，但每条边都是一次显式裁决，删一条就有一条判据变红。
 *
 * ═══ 三个 terminal 的含义 ═══
 *
 * `duplicate` / `recovery_download_only` / `close_recovery_required` 的出边**只有**
 * `reset`（用户显式确认后回 `html_idle`）。它们不是「等一等还会动」的中间态：
 *
 * * `duplicate` —— 自己发起的 operation 已被折叠进别人的 canonical primary，
 *   本 operation 的状态永不再变，也不得再新建 operation/application（AC 5.5 / 5.10）。
 *   后续 GET/timeline/conflicts/retry/resolve 仍按 **requested** id 发起（服务端先授权
 *   再 canonicalize），但**不改桥状态** —— 那正是「duplicate 是 terminal」的可观测含义。
 * * `recovery_download_only` —— 只下载并终结 case，三实体恒为 0，**不得**转 `applied`
 *   （AC 5.8）。表里没有这条边就是唯一判据。
 * * `close_recovery_required` —— close leader 失权且无合法 successor（AC 4.10）。
 *   它必须显式可见，不能被渲染成「保存成功」也不能是永久 loading。
 */
import {
  WP_SYNC_OPERATION_STATES,
  type WorkpaperSyncOperationState,
} from './workpaperSyncContract.generated'
import {
  WorkpaperSyncContractError,
  type WorkpaperSyncOperationSnapshot,
} from './workpaperSyncDto'

function refuse(code: string, message: string): never {
  throw new WorkpaperSyncContractError(code, message)
}

// ═══════════════════════════════════════════════════════════════════════════
// 1. 状态域
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 桥状态封闭域。
 *
 * AC 11.2 的 19 个状态**逐字**在内（`html_idle` … `error`）；本域另加 6 个，每个都有
 * 独立的可观测触发与独立的用户可见含义：
 *
 * | 追加状态 | 触发 | 为什么不能合并进 AC 11.2 的某个状态 |
 * |---|---|---|
 * | `descriptor_mounted` | 宿主报告 DocEditor 已创建 | 「已挂载但 `onDocumentReady` 未触发」与「正在挂载」是两种排障结论 |
 * | `forcesave_frozen` | 202 带 `dispatch_error` | request 已冻结但命令未被 Command Service 受理（design 文案「已冻结保存请求」≠「已发送强制保存」） |
 * | `waiting_application` | 202 后开始跟踪两 link 均空的 shell | AC 4.1 的 `application_id=NULL` shell 阶段 |
 * | `application_bound` | 快照 shape=primary | 与 `merging` 不同：已绑 application 但引擎尚未开工 |
 * | `duplicate` | 快照 shape=duplicate | terminal，且必须同时显示 requested→canonical |
 * | `close_authorization_stale` | close leader 失权 | AC 4.10 要求先显示它与 successor 进展，再决定 recovery |
 */
export const WP_BRIDGE_STATES = [
  // ── HTML 侧（mode=html）
  'html_idle',
  'flushing',
  'committing',
  'materializing',
  // ── OO 打开（mode=oo）
  'oo_loading',
  'descriptor_mounted',
  'confirming_descriptor',
  'oo_editing',
  // ── OO → HTML（mode=oo）
  'forcesave_requesting',
  'forcesave_frozen',
  'forcesave_accepted',
  'waiting_application',
  'incoming_durable',
  'application_bound',
  'duplicate',
  'merging',
  'rematerializing',
  'conflict',
  'refresh_required',
  'applied',
  // ── close 仲裁（mode=oo）
  'close_authorization_stale',
  'close_recovery_required',
  // ── recovery（mode 继承）
  'recovery_pending',
  'recovery_claiming',
  'recovery_download_only',
  // ── 失败（mode 继承）
  'error',
] as const
export type WorkpaperSyncBridgeState = (typeof WP_BRIDGE_STATES)[number]

/** AC 11.2 逐字要求的状态（判据用它证明「一个都没漏、一个都没改名」）。 */
export const WP_BRIDGE_AC_11_2_REQUIRED_STATES = [
  'html_idle',
  'flushing',
  'committing',
  'materializing',
  'oo_loading',
  'confirming_descriptor',
  'oo_editing',
  'forcesave_requesting',
  'forcesave_accepted',
  'incoming_durable',
  'merging',
  'rematerializing',
  'conflict',
  'refresh_required',
  'recovery_pending',
  'recovery_claiming',
  'recovery_download_only',
  'applied',
  'error',
] as const

/** 出边只有 `reset` 的三个终态。 */
export const WP_BRIDGE_TERMINAL_STATES = [
  'duplicate',
  'recovery_download_only',
  'close_recovery_required',
] as const

// ═══════════════════════════════════════════════════════════════════════════
// 2. 事件域
// ═══════════════════════════════════════════════════════════════════════════

export const WP_BRIDGE_EVENTS = [
  'flush_started',
  'pending_mutation_created',
  'descriptor_received',
  'descriptor_accepted',
  'editor_mounted',
  'document_ready',
  'descriptor_confirmed',
  'identity_rejected',
  'forcesave_started',
  'forcesave_dispatch_failed',
  'forcesave_command_accepted',
  'shell_tracking_started',
  'operation_observed',
  'conflict_resolution_submitted',
  'reload_completed',
  'close_authorization_lost',
  'close_successor_applied',
  'close_no_successor',
  'recovery_case_observed',
  'recovery_claim_started',
  'recovery_claim_failed',
  'recovery_claim_succeeded',
  'recovery_download_only_terminated',
  'sync_failed',
  'reset',
] as const
export type WorkpaperSyncBridgeEvent = (typeof WP_BRIDGE_EVENTS)[number]

// ═══════════════════════════════════════════════════════════════════════════
// 3. mode 归属
// ═══════════════════════════════════════════════════════════════════════════

export type WorkpaperSyncBridgeMode = 'html' | 'oo'

/**
 * 每个状态钉住的 mode。`inherit` = 保持进入前的 mode。
 *
 * 🔴 `error` 与三个 recovery 状态都是 `inherit`，因为 AC 11.6 明文「失败后**保持原模式**
 * 并提供重试」。给 `error` 钉一个 `'html'` 会让 OO 里的一次失败把用户踢回 HTML，
 * 而 OO 里可能还有没耐久的编辑 —— 那是 AC 4.4 明令禁止的形态。
 *
 * 🔴 `applied` 仍是 `'oo'`：结构化回写完成但 HTML 还没重载，此刻切 mode 会让用户看到
 * 一个旧 revision 的 HTML（Property 14 要求重载后的 revision 不低于 result revision）。
 * mode 只在 `applied --reload_completed--> html_idle` 那一步翻转。
 */
export const WP_BRIDGE_STATE_MODE: Readonly<
  Record<WorkpaperSyncBridgeState, WorkpaperSyncBridgeMode | 'inherit'>
> = Object.freeze({
  html_idle: 'html',
  flushing: 'html',
  committing: 'html',
  materializing: 'html',
  oo_loading: 'oo',
  descriptor_mounted: 'oo',
  confirming_descriptor: 'oo',
  oo_editing: 'oo',
  forcesave_requesting: 'oo',
  forcesave_frozen: 'oo',
  forcesave_accepted: 'oo',
  waiting_application: 'oo',
  incoming_durable: 'oo',
  application_bound: 'oo',
  duplicate: 'oo',
  merging: 'oo',
  rematerializing: 'oo',
  conflict: 'oo',
  refresh_required: 'oo',
  applied: 'oo',
  close_authorization_stale: 'oo',
  close_recovery_required: 'oo',
  recovery_pending: 'inherit',
  recovery_claiming: 'inherit',
  recovery_download_only: 'inherit',
  error: 'inherit',
})

// ═══════════════════════════════════════════════════════════════════════════
// 4. 用户可见文案（全中文，逐状态互不相同）
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 状态 → 中文文案。**唯一真源**：design §Frontend 明文「业务 composable 不拼 endpoint、
 * localStorage key 或成功文案」，所以文案只能在桥这一层。
 *
 * AC 11.3 要求「命令已接受 / 文件已耐久 / 结构化回写完成 / 发生冲突」分别表达，
 * 不得统一显示「同步成功」；design 另点名「已冻结保存请求」与「服务器已合并，需重载
 * 编辑器确认新基线」。判据据此断言四类文案两两不同、且没有任何一条含「同步成功」。
 */
export const WP_BRIDGE_STATE_TEXT: Readonly<
  Record<WorkpaperSyncBridgeState, string>
> = Object.freeze({
  html_idle: '当前为表单模式',
  flushing: '正在保存表单待提交编辑',
  committing: '正在提交内容版本',
  materializing: '正在生成 OnlyOffice 文件',
  oo_loading: '正在打开 OnlyOffice 编辑器',
  descriptor_mounted: '编辑器已挂载，等待文档就绪',
  confirming_descriptor: '正在向服务端确认编辑器身份',
  oo_editing: 'OnlyOffice 编辑中',
  forcesave_requesting: '正在冻结保存请求',
  forcesave_frozen: '已冻结保存请求，强制保存命令未被受理',
  forcesave_accepted: '已发送强制保存，命令已接受',
  waiting_application: '已发送强制保存，等待 OnlyOffice 回传文件',
  incoming_durable: 'OO 文件已耐久保存，等待关联回写任务',
  application_bound: '回写任务已关联，等待解析合并',
  duplicate: '本次保存请求已折叠到同一份回写任务，请查看规范操作',
  merging: '正在解析并合并 OnlyOffice 内容',
  rematerializing: '正在按新基线重新生成 OnlyOffice 文件',
  conflict: '发生冲突，需逐项裁决',
  refresh_required: '服务器已合并，需重载编辑器确认新基线',
  applied: '结构化回写完成',
  close_authorization_stale: '关闭发起人已失去资格，正在等待接任者完成保存',
  close_recovery_required: '无合法接任者，需重新授权后从恢复流程继续',
  recovery_pending: '存在待认领的恢复项，尚未创建回写任务',
  recovery_claiming: '正在认领恢复项',
  recovery_download_only: '已仅下载并终结恢复项，未执行结构化回写',
  error: '同步失败',
})

// ═══════════════════════════════════════════════════════════════════════════
// 5. 邻接表
// ═══════════════════════════════════════════════════════════════════════════

type EdgeMap = Partial<Record<WorkpaperSyncBridgeEvent, WorkpaperSyncBridgeState>>

/**
 * `operation_observed` 之外的**确定性**边：一个事件在一个状态下只有一个目标。
 *
 * 读表要点（每条缺省都是一次裁决）：
 *
 * * `oo_editing` **没有** `reload_completed` / `operation_observed` —— 不做 forcesave
 *   就无法进入 `applied`（Property 12：未收到 terminal 不得切 HTML）。
 * * `descriptor_mounted` / `confirming_descriptor` **没有** `forcesave_started` ——
 *   confirm 成功前不得 forcesave（Property 11 后半）。
 * * `error` **没有** `reload_completed` —— 后续清理/reload 成功不得覆盖 error
 *   （AC 11.10 / Property 48）。
 * * `recovery_pending` / `recovery_claiming` **没有** `operation_observed` ——
 *   claim 成功前根本没有 operation（AC 5.8）。
 * * 三个 terminal 只有 `reset`。
 */
const DETERMINISTIC_EDGES: Readonly<Record<WorkpaperSyncBridgeState, EdgeMap>> =
  Object.freeze({
    html_idle: {
      flush_started: 'flushing',
      recovery_case_observed: 'recovery_pending',
      sync_failed: 'error',
    },
    flushing: {
      pending_mutation_created: 'committing',
      identity_rejected: 'html_idle',
      sync_failed: 'error',
    },
    committing: {
      descriptor_received: 'materializing',
      identity_rejected: 'html_idle',
      sync_failed: 'error',
    },
    materializing: {
      // 只有 descriptor 逐项校验通过才 mount（AC 3.7 / Property 11）。
      descriptor_accepted: 'oo_loading',
      identity_rejected: 'html_idle',
      sync_failed: 'error',
    },
    oo_loading: {
      editor_mounted: 'descriptor_mounted',
      identity_rejected: 'html_idle',
      sync_failed: 'error',
    },
    descriptor_mounted: {
      document_ready: 'confirming_descriptor',
      identity_rejected: 'html_idle',
      sync_failed: 'error',
    },
    confirming_descriptor: {
      descriptor_confirmed: 'oo_editing',
      // token / bundle identity 的 409 停留 HTML，不得转 editing。
      identity_rejected: 'html_idle',
      sync_failed: 'error',
    },
    oo_editing: {
      forcesave_started: 'forcesave_requesting',
      close_authorization_lost: 'close_authorization_stale',
      recovery_case_observed: 'recovery_pending',
      sync_failed: 'error',
    },
    forcesave_requesting: {
      forcesave_dispatch_failed: 'forcesave_frozen',
      forcesave_command_accepted: 'forcesave_accepted',
      close_authorization_lost: 'close_authorization_stale',
      sync_failed: 'error',
    },
    forcesave_frozen: {
      // 重试只重发命令，不重新冻结 request（design §retryOperation）。
      forcesave_started: 'forcesave_requesting',
      close_authorization_lost: 'close_authorization_stale',
      sync_failed: 'error',
    },
    forcesave_accepted: {
      shell_tracking_started: 'waiting_application',
      close_authorization_lost: 'close_authorization_stale',
      sync_failed: 'error',
    },
    waiting_application: {
      close_authorization_lost: 'close_authorization_stale',
      sync_failed: 'error',
    },
    incoming_durable: {
      close_authorization_lost: 'close_authorization_stale',
      sync_failed: 'error',
    },
    application_bound: {
      close_authorization_lost: 'close_authorization_stale',
      sync_failed: 'error',
    },
    duplicate: {
      reset: 'html_idle',
    },
    merging: {
      close_authorization_lost: 'close_authorization_stale',
      sync_failed: 'error',
    },
    rematerializing: {
      // refresh-required 后销毁旧 generation，用新 descriptor 重新 mount + confirm。
      descriptor_accepted: 'oo_loading',
      close_authorization_lost: 'close_authorization_stale',
      sync_failed: 'error',
    },
    conflict: {
      conflict_resolution_submitted: 'merging',
      close_authorization_lost: 'close_authorization_stale',
      sync_failed: 'error',
    },
    refresh_required: {
      descriptor_received: 'rematerializing',
      close_authorization_lost: 'close_authorization_stale',
      close_no_successor: 'close_recovery_required',
      sync_failed: 'error',
    },
    applied: {
      reload_completed: 'html_idle',
      sync_failed: 'error',
    },
    close_authorization_stale: {
      close_successor_applied: 'applied',
      close_no_successor: 'close_recovery_required',
      sync_failed: 'error',
    },
    close_recovery_required: {
      reset: 'html_idle',
    },
    recovery_pending: {
      recovery_claim_started: 'recovery_claiming',
      recovery_download_only_terminated: 'recovery_download_only',
      sync_failed: 'error',
    },
    recovery_claiming: {
      // claim 失败回 pending，三实体仍为 0。
      recovery_claim_failed: 'recovery_pending',
      sync_failed: 'error',
    },
    recovery_download_only: {
      reset: 'html_idle',
    },
    error: {
      reset: 'html_idle',
      flush_started: 'flushing',
      forcesave_started: 'forcesave_requesting',
      recovery_claim_started: 'recovery_claiming',
    },
  })

/**
 * `operation_observed` 的**允许目标集**（逐状态显式列出）。
 *
 * 允许「跳跃」是必需的：SSE 去重与降级轮询都可能让第一份快照直接落在
 * `application_bound` 甚至 `applied`。但跳跃只在这张表里，**不是**一条通用规则 ——
 * 于是 `applied → merging`（回退）、`oo_editing → applied`（跳过 forcesave）、
 * `duplicate → 任何`（terminal）都不在表内，删一条边就有一条判据变红。
 */
const OPERATION_TARGETS: Readonly<
  Partial<Record<WorkpaperSyncBridgeState, readonly WorkpaperSyncBridgeState[]>>
> = Object.freeze({
  waiting_application: [
    'waiting_application',
    'incoming_durable',
    'application_bound',
    'duplicate',
    'merging',
    'rematerializing',
    'conflict',
    'refresh_required',
    'applied',
    'close_authorization_stale',
    'error',
  ],
  incoming_durable: [
    'incoming_durable',
    'application_bound',
    'duplicate',
    'merging',
    'rematerializing',
    'conflict',
    'refresh_required',
    'applied',
    'close_authorization_stale',
    'error',
  ],
  application_bound: [
    'application_bound',
    'merging',
    'rematerializing',
    'conflict',
    'refresh_required',
    'applied',
    'close_authorization_stale',
    'error',
  ],
  merging: [
    'merging',
    'rematerializing',
    'conflict',
    'refresh_required',
    'applied',
    'close_authorization_stale',
    'error',
  ],
  rematerializing: [
    'rematerializing',
    'merging',
    'conflict',
    'refresh_required',
    'applied',
    'close_authorization_stale',
    'error',
  ],
  conflict: [
    'conflict',
    'merging',
    'rematerializing',
    'refresh_required',
    'applied',
    'close_authorization_stale',
    'error',
  ],
  refresh_required: ['refresh_required', 'close_authorization_stale', 'error'],
  applied: ['applied', 'error'],
  // close leader 失权后，本 participant 自己的 operation 只可能停在 stale 或失败；
  // 「successor 接任并完成」必须走 `close_successor_applied`（带 successor intent id），
  // 否则无 successor 与有 successor 两种结局在 UI 上不可区分。
  close_authorization_stale: ['close_authorization_stale', 'error'],
})

/** `recovery_claim_succeeded` 只允许这两个目标（primary 或 terminal duplicate）。 */
const CLAIM_SUCCESS_TARGETS = ['application_bound', 'duplicate'] as const

// ═══════════════════════════════════════════════════════════════════════════
// 6. 快照 → 状态投影
// ═══════════════════════════════════════════════════════════════════════════

/**
 * operation 快照投影成桥状态。
 *
 * 🔴 两条前置不变量先于映射：
 *
 * 1. **pre-bind shell 不得带 result revision**（Property 14 末句）。一份
 *    `application_id=NULL` 却带 `result_revision` 的快照要么是服务端漏了绑定事件，
 *    要么是有人伪造了完成凭证；两者都不能被读成「已完成」。
 * 2. **穷尽映射**：`WP_SYNC_OPERATION_STATES` 的每个成员都要有归属，没有兜底分支。
 *    新增后端状态时这里必须显式裁决（AC 4.9「未知状态 fail visible」）。
 */
export function bridgeStateForOperation(
  snapshot: WorkpaperSyncOperationSnapshot,
): WorkpaperSyncBridgeState {
  if (snapshot.shape === 'pre_correlation' && snapshot.resultRevision !== null) {
    refuse(
      'bridge_pre_bind_result_revision',
      `operation ${snapshot.requestedOperationId} 尚未绑定 application 却带 ` +
        `result_revision=${snapshot.resultRevision} —— pre-bind shell 不得伪造完成凭证`,
    )
  }
  switch (snapshot.state) {
    case 'duplicate':
      return 'duplicate'
    case 'authorization_stale':
      return 'close_authorization_stale'
    case 'error':
    case 'rejected':
      return 'error'
    // 「较新且 canonical application 不同的 durable incoming」才会 supersede 旧 operation
    // （AC 5.10）；对用户而言那等于「服务器已合并，需重载编辑器确认新基线」。
    case 'superseded':
    case 'refresh_required':
      return 'refresh_required'
    case 'conflict':
      return 'conflict'
    case 'rematerializing':
      return 'rematerializing'
    case 'extracting':
    case 'merging':
      return 'merging'
    case 'applying':
    case 'applied':
      return 'applied'
    case 'application_bound':
      return 'application_bound'
    case 'created':
    case 'command_pending':
    case 'accepted':
    case 'waiting_application':
      if (snapshot.shape === 'primary') {
        // 绑定事件已落库但 operation state 还没推进 —— 已绑 application 是更强的事实。
        return 'application_bound'
      }
      return snapshot.durableAt === null ? 'waiting_application' : 'incoming_durable'
    default: {
      const unreachable: never = snapshot.state
      refuse(
        'bridge_operation_state_unmapped',
        `operation state ${JSON.stringify(unreachable)} 未登记桥状态投影 —— ` +
          '未知状态必须 fail visible',
      )
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 7. 转换
// ═══════════════════════════════════════════════════════════════════════════

export interface WorkpaperSyncBridgeTransitionContext {
  /** `operation_observed` 必填：本次观测到的快照。 */
  readonly operation?: WorkpaperSyncOperationSnapshot
  /** `shell_tracking_started` 必填：202 回执里的 operation id。 */
  readonly requestedOperationId?: string
  /** `close_successor_applied` 必填：接任者的 intent id。 */
  readonly successorIntentId?: string
  /** `recovery_claim_succeeded` 必填：claim 后的三实体。 */
  readonly claimedEntities?: {
    readonly forcesaveRequestId: string | null
    readonly applicationId: string | null
    readonly operationId: string | null
  }
  /** `recovery_claim_succeeded` 必填：claim 结果的 operation 形态。 */
  readonly claimedShape?: 'primary' | 'duplicate'
  /** `recovery_case_observed` / `recovery_claim_failed` 必填：case 的三实体。 */
  readonly recoveryEntities?: {
    readonly forcesaveRequestId: string | null
    readonly applicationId: string | null
    readonly operationId: string | null
  }
}

export interface WorkpaperSyncBridgeTransition {
  readonly from: WorkpaperSyncBridgeState
  readonly event: WorkpaperSyncBridgeEvent
  readonly to: WorkpaperSyncBridgeState
  /** 转换后的 mode（`inherit` 状态沿用 `fromMode`）。 */
  readonly mode: WorkpaperSyncBridgeMode
  readonly terminal: boolean
}

function entitiesPresent(entities: {
  readonly forcesaveRequestId: string | null
  readonly applicationId: string | null
  readonly operationId: string | null
}): string[] {
  return Object.entries(entities)
    .filter(([, value]) => value !== null && String(value).trim() !== '')
    .map(([key]) => key)
}

/**
 * 唯一转换函数。**非法转换抛 `WorkpaperSyncContractError` 且不返回任何值** ——
 * 调用方拿不到新状态，于是 mode 结构性地不可能被改（Property 46 后半）。
 *
 * 每一处拒绝都带互不相同的 `code`：本 spec 的变异运行已三次抓到「两个分支共用一个
 * code ⇒ 先到的把后到的遮成永远不可达」这个形态。
 */
export function transitionBridgeState(
  from: WorkpaperSyncBridgeState,
  event: WorkpaperSyncBridgeEvent,
  fromMode: WorkpaperSyncBridgeMode,
  context: WorkpaperSyncBridgeTransitionContext = {},
): WorkpaperSyncBridgeTransition {
  if (!(WP_BRIDGE_STATES as readonly string[]).includes(from)) {
    refuse('bridge_state_unknown', `未声明的桥状态 ${JSON.stringify(from)}`)
  }
  if (!(WP_BRIDGE_EVENTS as readonly string[]).includes(event)) {
    refuse('bridge_event_unknown', `未声明的桥事件 ${JSON.stringify(event)}`)
  }

  let to: WorkpaperSyncBridgeState
  if (event === 'operation_observed') {
    const snapshot = context.operation
    if (!snapshot) {
      refuse(
        'bridge_operation_context_required',
        'operation_observed 必须带快照 —— 无快照的观测无法判定目标状态',
      )
    }
    const allowed = OPERATION_TARGETS[from]
    if (!allowed) {
      refuse(
        'bridge_operation_not_observable',
        `状态 ${from} 不接受 operation 观测 —— 该阶段没有可跟踪的 operation` +
          '（claim 前的 recovery case 三实体为 0，terminal 状态不再推进）',
      )
    }
    const projected = bridgeStateForOperation(snapshot)
    if (!allowed.includes(projected)) {
      refuse(
        'bridge_operation_transition_illegal',
        `${from} 不允许经 operation 观测进入 ${projected}（允许 [${allowed.join(', ')}]）`,
      )
    }
    to = projected
  } else if (event === 'recovery_claim_succeeded') {
    if (from !== 'recovery_claiming') {
      refuse(
        'bridge_claim_success_out_of_phase',
        `claim 成功只能发生在 recovery_claiming，实得 ${from}`,
      )
    }
    const entities = context.claimedEntities
    if (!entities || entitiesPresent(entities).length !== 3) {
      refuse(
        'bridge_claim_entities_incomplete',
        'claim 成功必须同时关联 request/application/operation 三实体 —— ' +
          `实得 [${entities ? entitiesPresent(entities).join(', ') : ''}]`,
      )
    }
    const shape = context.claimedShape
    if (shape !== 'primary' && shape !== 'duplicate') {
      refuse(
        'bridge_claim_shape_required',
        `claim 结果必须是 primary 或 terminal duplicate，实得 ${JSON.stringify(shape)}`,
      )
    }
    to = shape === 'primary' ? 'application_bound' : 'duplicate'
    if (!(CLAIM_SUCCESS_TARGETS as readonly string[]).includes(to)) {
      refuse('bridge_claim_target_illegal', `claim 目标 ${to} 不在允许集内`)
    }
  } else {
    const edges = DETERMINISTIC_EDGES[from]
    const target = edges[event]
    if (!target) {
      refuse(
        'bridge_transition_illegal',
        `状态 ${from} 不接受事件 ${event}（允许 [${Object.keys(edges).join(', ') || '无'}]）`,
      )
    }
    to = target
  }

  // ── 目标态的进入前置条件（每条都对应一句明文禁令）
  if (event === 'shell_tracking_started') {
    const requested = String(context.requestedOperationId ?? '').trim()
    if (requested === '') {
      refuse(
        'bridge_shell_requires_requested_operation',
        'normal accepted 之后必须按 202 回执里的 requested operation 跟踪两 link 均空的 ' +
          'shell —— 缺 requested id 就无法沿同一 operation 进入 primary/duplicate',
      )
    }
  }
  if (event === 'close_successor_applied') {
    const successor = String(context.successorIntentId ?? '').trim()
    if (successor === '') {
      refuse(
        'bridge_close_successor_required',
        'close leader 失权后要显示「成功」必须有合法 successor 的 intent id —— ' +
          '否则只能进入 close_recovery_required，不得渲染成普通保存成功',
      )
    }
  }
  if (
    to === 'recovery_pending' ||
    to === 'recovery_claiming' ||
    to === 'recovery_download_only'
  ) {
    const entities = context.recoveryEntities
    if (entities) {
      const present = entitiesPresent(entities)
      if (present.length > 0) {
        refuse(
          'bridge_recovery_premature_entities',
          `进入 ${to} 时带 [${present.join(', ')}] —— claim 成功前与 download-only 终态，` +
            'request/application/operation 三者必须全空（AC 5.8）',
        )
      }
    }
  }

  const pinned = WP_BRIDGE_STATE_MODE[to]
  return {
    from,
    event,
    to,
    mode: pinned === 'inherit' ? fromMode : pinned,
    terminal: (WP_BRIDGE_TERMINAL_STATES as readonly string[]).includes(to),
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 8. 表自证（供判据调用，非运行时开关）
// ═══════════════════════════════════════════════════════════════════════════

export interface WorkpaperSyncBridgeMachineAudit {
  /** 没有任何入边的状态（`html_idle` 是初态，不计）。 */
  readonly unreachableStates: readonly WorkpaperSyncBridgeState[]
  /** 出边为空的状态。 */
  readonly deadEndStates: readonly WorkpaperSyncBridgeState[]
  /** 声明了 terminal 但出边不止 `reset` 的状态。 */
  readonly leakyTerminals: readonly WorkpaperSyncBridgeState[]
  /** 邻接表里出现过、但不在状态域内的目标。 */
  readonly undeclaredTargets: readonly string[]
  /** 邻接表里从未被任何状态接受的事件。 */
  readonly unusedEvents: readonly WorkpaperSyncBridgeEvent[]
}

/**
 * 遍历两张表，产出「每个状态都有入边、每个终态真是终态、每个事件都有用」的事实。
 *
 * 🔴 存在的理由：状态机最典型的死代码不是「函数没人调」，而是**声明了一个状态却没有
 * 任何一条边通向它**。这种缺陷下所有「状态域包含它」的判据全绿，而它的分支永远不会
 * 执行 —— 变异掉那段代码也永远 GREEN。本函数把可达性变成可断言的事实。
 */
export function auditBridgeMachine(): WorkpaperSyncBridgeMachineAudit {
  const incoming = new Set<string>()
  const undeclaredTargets = new Set<string>()
  const usedEvents = new Set<string>()
  const outDegree = new Map<WorkpaperSyncBridgeState, number>()

  for (const state of WP_BRIDGE_STATES) {
    const edges = DETERMINISTIC_EDGES[state]
    const operationTargets = OPERATION_TARGETS[state] ?? []
    let degree = Object.keys(edges).length + (operationTargets.length > 0 ? 1 : 0)
    if (state === 'recovery_claiming') {
      // `recovery_claim_succeeded` 的目标由 claim 形态决定，不在确定性表里。
      degree += 1
      for (const target of CLAIM_SUCCESS_TARGETS) incoming.add(target)
      usedEvents.add('recovery_claim_succeeded')
    }
    outDegree.set(state, degree)
    for (const [event, target] of Object.entries(edges)) {
      usedEvents.add(event)
      if (!(WP_BRIDGE_STATES as readonly string[]).includes(target)) {
        undeclaredTargets.add(target)
      }
      incoming.add(target)
    }
    for (const target of operationTargets) {
      usedEvents.add('operation_observed')
      if (!(WP_BRIDGE_STATES as readonly string[]).includes(target)) {
        undeclaredTargets.add(target)
      }
      // 自环不算入边（否则任何带幂等重入的状态都会被判成「可达」）。
      if (target !== state) incoming.add(target)
    }
  }

  const leaky = WP_BRIDGE_TERMINAL_STATES.filter((state) => {
    const events = Object.keys(DETERMINISTIC_EDGES[state])
    const hasOperation = (OPERATION_TARGETS[state] ?? []).length > 0
    return hasOperation || events.length !== 1 || events[0] !== 'reset'
  })

  return {
    unreachableStates: WP_BRIDGE_STATES.filter(
      (state) => state !== 'html_idle' && !incoming.has(state),
    ),
    deadEndStates: WP_BRIDGE_STATES.filter((state) => (outDegree.get(state) ?? 0) === 0),
    leakyTerminals: leaky,
    undeclaredTargets: [...undeclaredTargets].sort(),
    unusedEvents: WP_BRIDGE_EVENTS.filter((event) => !usedEvents.has(event)),
  }
}

/** 后端 operation 状态域 → 桥状态的完整投影（判据用它证明穷尽映射）。 */
export function bridgeStateProjectionByOperationState(): Readonly<
  Record<WorkpaperSyncOperationState, WorkpaperSyncBridgeState>
> {
  const out = {} as Record<WorkpaperSyncOperationState, WorkpaperSyncBridgeState>
  for (const state of WP_SYNC_OPERATION_STATES) {
    out[state] = bridgeStateForOperation({
      requestedOperationId: 'probe',
      canonicalOperationId: 'probe',
      followedDuplicate: false,
      state,
      shape: state === 'duplicate' ? 'duplicate' : 'pre_correlation',
      applicationId: null,
      duplicateOfOperationId: state === 'duplicate' ? 'primary' : null,
      errorCode: null,
      errorStage: null,
      acceptedAt: null,
      applicationBoundAt: null,
      operationFinishedAt: null,
      resultRevision: null,
      conflictCount: null,
      logicalResultCode: null,
      definitionBundleId: null,
      definitionBundleSha256: null,
      authorityModelDefinitionSha256: null,
      durableAt: null,
      finishedAt: null,
      terminal: false,
    })
  }
  return Object.freeze(out)
}
