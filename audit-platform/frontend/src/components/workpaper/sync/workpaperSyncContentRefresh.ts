/**
 * commit 后 `workpaper.content.updated` → **前端刷新**的唯一接线层。
 *
 * spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 35
 * Requirements: 11.9, 13.1, 13.2, 13.3, 13.4
 * Properties: P52（只消费 commit 后事件）/ P53（payload 逐项不丢，含 `extra`）/
 *             P54（event/刷新失败落可恢复态，不静默丢失）
 *
 * ═══ 三条职责 ═══
 *
 * 1. **归一 wire 形态**（Property 53 的消费侧）。同一条耐久事件有两种到达形态：
 *
 *    * `GET /events/stream` 的 typed SSE 信封 —— 业务键在 `extra` 里
 *      （`{event_type, project_id, year, account_codes, entry_group_id, batch_id, extra}`，
 *      见 `app/routers/events.py`）；
 *    * `GET /events/since` 的 typed replay 项 —— 同样把 payload 放在 `extra`。
 *
 *    🔴 本模块**必须**解这一层。Task 31 的 `contentUpdateDedupeKey()` 只读顶层
 *    `wp_id`/`revision`，对真实 SSE 信封恒返回 `null` ⇒ AC 11.9 的
 *    `wp_id + revision` 去重从未生效（每条事件都退化成"补读一次"）。那是本任务实测
 *    抓到的真实缺陷，不是新功能。
 *
 * 2. **按 `wp_id + revision` 去重，dirty 时不静默覆盖**（AC 11.9 + Task 35 正文）。
 *    本地有未保存修改时**不调**宿主 reload，而是落 `deferred_dirty` 并把目标 revision
 *    记成待办，等用户显式确认。静默 reload 等于把审计师刚录的数吞掉。
 *
 * 3. **失败落可恢复态，且零写路径**（AC 13.4 / Task 35 正文）。事件形态失败与刷新失败
 *    是**两类**、各有各的码：归一到一个码会让先到的那条把后到的遮成永不可达
 *    （本 spec 已三次抓到这个形态）。两类都不发任何请求 —— 本模块的注入面只有
 *    `reload` / `isDirty` / `loadedRevision`，**没有** api 面，因此结构上不可能
 *    "刷新失败又制造一个新 revision"。
 *
 * ═══ 本模块不做的事 ═══
 *
 * 不判定编辑器模式、不碰 forcesave 门控、不解析 operation 快照 —— 那些是 Task 32 的
 * 桥与 Task 31 的 `WorkpaperSyncOperationTracker`。桥的 `reloadAfterApplied()` 走的是
 * **本会话自己发起的**回写终态；本模块处理的是**别人**（或后台升级）提交的内容变更。
 */
import { computed, readonly, ref, type Ref } from 'vue'

import { subscribeProjectEvent } from '@/services/sse/projectEventStream'

import { WorkpaperSyncContractError, isOpaqueUuid } from './workpaperSyncDto'

function refuse(code: string, message: string): never {
  throw new WorkpaperSyncContractError(code, message)
}

// ═══════════════════════════════════════════════════════════════════════════
// 1. 事件名与键集（真源：后端 `EventType.WORKPAPER_CONTENT_UPDATED` 与三个 payload 构造器）
// ═══════════════════════════════════════════════════════════════════════════

/** 内容提交事件名。后端 `EventType.WORKPAPER_CONTENT_UPDATED.value` 的逐字副本。 */
export const WP_CONTENT_UPDATED_EVENT_NAME = 'workpaper.content.updated'

/**
 * design §outbox 声明的 7 个必填键。
 *
 * 后端真源是 `content_mutation.EVENT_PAYLOAD_REQUIRED_KEYS`；
 * `test_task35_content_event_refresh.py` 反向锁死这份清单，漂移即打红。
 */
export const WP_CONTENT_EVENT_DESIGN_KEYS = [
  'wp_id',
  'project_id',
  'revision',
  'operation_id',
  'source',
  'adapter_id',
  'file_sha256',
] as const

/**
 * 消费侧**额外**必需的键。三条 lane（标准 commit / html-only commit / 纯表示升级）
 * 都提供它们，守卫对三个真实 payload 构造器逐一断言。
 *
 * * `content_version_id` —— **commit 后**才存在的不可变 id。AC 11.9 明文"不得依赖
 *   进程内 commit 前 debounce 事件"，而 commit 前的 debounce 事件**不可能**带一个
 *   已落库的 content version id。这是本模块区分两者的结构判据（不是靠事件名）。
 * * `content_revision_advanced` —— 纯表示升级为 `false`。少了它，一次隐形模板升级
 *   会被当成业务改动推给审计师去重载。
 * * `entry_id` / `reason` —— 追溯与文案分型。
 */
export const WP_CONTENT_EVENT_CONSUMER_KEYS = [
  'entry_id',
  'content_version_id',
  'content_revision_advanced',
  'reason',
] as const

/** 消费一条内容事件所需的全部键（两段之和，不另抄一份）。 */
export const WP_CONTENT_EVENT_REQUIRED_KEYS: readonly string[] = [
  ...WP_CONTENT_EVENT_DESIGN_KEYS,
  ...WP_CONTENT_EVENT_CONSUMER_KEYS,
]

// ═══════════════════════════════════════════════════════════════════════════
// 2. 归一与解析
// ═══════════════════════════════════════════════════════════════════════════

/** 一条内容事件到达时的信封形态。 */
export type WorkpaperContentUpdateEnvelope = 'typed_sse' | 'flat_payload'

export interface WorkpaperContentUpdate {
  readonly envelope: WorkpaperContentUpdateEnvelope
  readonly wpId: string
  readonly projectId: string
  readonly revision: number
  readonly operationId: string | null
  readonly source: string
  readonly adapterId: string | null
  readonly fileSha256: string
  readonly entryId: string
  readonly contentVersionId: string
  /** `false` = 纯表示升级，业务内容没变（不得据此重载 HTML）。 */
  readonly contentRevisionAdvanced: boolean
  readonly reason: string
  /** 耐久行 id（`__event_id`），缺失为 null。Requirement 13.3 的幂等键。 */
  readonly eventId: string | null
  /**
   * **整份** payload，逐键原样保留（Requirement 13.2「不得丢失 extra」）。
   *
   * 解析出的强类型字段是投影，不是替代：下游 evidence/追溯要读扩展键
   * （`representation_id` / `definition_bundle_sha256` / `requires_client_refresh` …），
   * 只留 11 个已知键就等于在消费侧把 `extra` 丢了。
   */
  readonly payload: Readonly<Record<string, unknown>>
}

type Wire = Record<string, unknown>

function asWire(value: unknown): Wire | null {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Wire
}

/**
 * 剥掉 typed SSE / typed replay 的信封，交回**内层业务 payload**。
 *
 * 判据：信封的标志是"顶层有 `event_type` 且 `extra` 是对象"。两个条件都要
 * —— 只看 `extra` 会把一个恰好带 `extra` 键的扁平 payload 误剥一层。
 */
export function unwrapContentEventWire(wire: unknown): {
  readonly payload: Wire | null
  readonly envelope: WorkpaperContentUpdateEnvelope
  readonly eventName: string | null
} {
  const outer = asWire(wire)
  if (outer === null) return { payload: null, envelope: 'flat_payload', eventName: null }
  const eventName = typeof outer.event_type === 'string' ? outer.event_type : null
  const inner = asWire(outer.extra)
  if (eventName !== null && inner !== null) {
    return { payload: inner, envelope: 'typed_sse', eventName }
  }
  return { payload: outer, envelope: 'flat_payload', eventName }
}

/**
 * `wp_id + revision` 去重键（AC 11.9）。**宽松**：拿不到就返回 `null`。
 *
 * 🔴 键里刻意**不含** `operation_id`：同一次 commit 既可能由 operation 应用触发，也可能
 * 由纯表示升级触发（`operation_id=null`），把它放进键会让同一个 revision 投两次。
 */
export function contentUpdateDedupeKey(wire: unknown): string | null {
  const { payload } = unwrapContentEventWire(wire)
  if (payload === null) return null
  const wpId = payload.wp_id
  const revision = payload.revision
  if (typeof wpId !== 'string' || wpId.trim() === '') return null
  if (typeof revision !== 'number' || !Number.isInteger(revision)) return null
  return `${wpId}|${revision}`
}

/**
 * 严格解析一条内容事件。**每个拒绝都有互不相同的码。**
 *
 * | 码 | 什么时候 |
 * |---|---|
 * | `content_event_not_an_object` | 载荷根本不是对象（SSE `data:` 传了裸串/数组） |
 * | `content_event_name_mismatch` | 信封的 `event_type` 不是内容事件 |
 * | `content_event_wp_id_invalid` | 缺 `wp_id` 或不是不透明 UUID |
 * | `content_event_revision_invalid` | `revision` 不是非负整数 |
 * | `content_event_precommit_shape` | 缺 `content_version_id` ⇒ 这不是 commit 后事件 |
 * | `content_event_required_key_missing` | 其余必填键缺失 |
 */
export function parseContentUpdatedEvent(wire: unknown): WorkpaperContentUpdate {
  const { payload, envelope, eventName } = unwrapContentEventWire(wire)
  if (payload === null) {
    refuse(
      'content_event_not_an_object',
      `内容事件载荷不是对象（实得 ${wire === null ? 'null' : typeof wire}）`,
    )
  }
  if (eventName !== null && eventName !== WP_CONTENT_UPDATED_EVENT_NAME) {
    refuse(
      'content_event_name_mismatch',
      `事件名 ${JSON.stringify(eventName)} 不是 ${WP_CONTENT_UPDATED_EVENT_NAME} —— ` +
        '同一条共享连接上还有别的事件，串型消费会按错误的 payload 去刷新',
    )
  }
  if (!isOpaqueUuid(payload.wp_id)) {
    refuse(
      'content_event_wp_id_invalid',
      `内容事件的 wp_id=${JSON.stringify(payload.wp_id)} 不是不透明 UUID`,
    )
  }
  const revision = payload.revision
  if (typeof revision !== 'number' || !Number.isInteger(revision) || revision < 0) {
    refuse(
      'content_event_revision_invalid',
      `内容事件的 revision=${JSON.stringify(revision)} 不是非负整数 —— ` +
        '去重键与"是否更新"两处判据都建立在它上面',
    )
  }
  // 🔴 commit 后判据：`content_version_id` 是**已落库**的不可变 content version。
  // 进程内 commit 前 debounce 事件不可能持有它（那时版本行还没写），所以缺它就是
  // "这条不是 AC 11.9 要求消费的那种事件"，必须显式拒绝而不是当成可刷新事件。
  if (!isOpaqueUuid(payload.content_version_id)) {
    refuse(
      'content_event_precommit_shape',
      `内容事件缺已落库的 content_version_id（实得 ` +
        `${JSON.stringify(payload.content_version_id)}）—— ` +
        'commit 前的进程内事件不得驱动刷新（AC 11.9）',
    )
  }
  for (const key of WP_CONTENT_EVENT_REQUIRED_KEYS) {
    if (!Object.prototype.hasOwnProperty.call(payload, key)) {
      refuse(
        'content_event_required_key_missing',
        `内容事件缺必填键 ${key} —— design §outbox 的 7 键与消费侧 4 键都必须在`,
      )
    }
  }
  if (typeof payload.content_revision_advanced !== 'boolean') {
    refuse(
      'content_event_required_key_missing',
      `内容事件的 content_revision_advanced=` +
        `${JSON.stringify(payload.content_revision_advanced)} 不是布尔 —— ` +
        '纯表示升级与业务改动的分型全靠它',
    )
  }
  const eventId = payload.__event_id
  return {
    envelope,
    wpId: String(payload.wp_id),
    projectId: typeof payload.project_id === 'string' ? payload.project_id : '',
    revision,
    operationId: typeof payload.operation_id === 'string' ? payload.operation_id : null,
    source: typeof payload.source === 'string' ? payload.source : '',
    adapterId: typeof payload.adapter_id === 'string' ? payload.adapter_id : null,
    fileSha256: typeof payload.file_sha256 === 'string' ? payload.file_sha256 : '',
    entryId: typeof payload.entry_id === 'string' ? payload.entry_id : '',
    contentVersionId: String(payload.content_version_id),
    contentRevisionAdvanced: payload.content_revision_advanced,
    reason: typeof payload.reason === 'string' ? payload.reason : '',
    eventId: typeof eventId === 'string' && eventId.trim() !== '' ? eventId : null,
    // 整份 payload 原样带出（Requirement 13.2）。冻结一层防止下游改写共享对象。
    payload: Object.freeze({ ...payload }),
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 3. 可见状态与文案
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 内容刷新的可见状态。
 *
 * `deferred_dirty` / `refresh_failed` / `event_rejected` 三个都是**已落地、等用户动**
 * 的状态：UI 不得转圈，必须给出具体动作（与 Task 34 的 `WP_SYNC_WAIT_KIND` 同一取向）。
 */
export type WorkpaperContentRefreshStatus =
  | 'idle'
  | 'refreshing'
  | 'synced'
  | 'deferred_dirty'
  | 'refresh_failed'
  | 'event_rejected'

/** 一次 `handleEvent()` 的结局。每一种都可达，且互不相同。 */
export type WorkpaperContentRefreshOutcomeKind =
  | 'rejected'
  | 'other_wp'
  | 'duplicate'
  | 'stale'
  | 'representation_only'
  | 'deferred_dirty'
  | 'refreshed'
  | 'refresh_failed'

export interface WorkpaperContentRefreshOutcome {
  readonly kind: WorkpaperContentRefreshOutcomeKind
  readonly dedupeKey: string | null
  readonly revision: number | null
  /** 仅 `rejected` / `refresh_failed` 非空，且两类的码集不相交。 */
  readonly errorCode: string | null
}

export interface WorkpaperContentRefreshFailure {
  /** `event` = 事件形态失败；`refresh` = 宿主 reload 失败。两类不得共用一个码。 */
  readonly kind: 'event' | 'refresh'
  readonly errorCode: string
  readonly message: string
  /** 是否可由用户显式重试。事件形态失败不可重试（下一条事件才是新事实）。 */
  readonly retryable: boolean
}

export const WP_CONTENT_REFRESH_STATUS_TEXT: Readonly<
  Record<WorkpaperContentRefreshStatus, string>
> = Object.freeze({
  idle: '尚未收到新的内容提交通知',
  refreshing: '正在按提交后的内容修订号重新加载表单',
  synced: '表单已加载到最新提交的内容修订号',
  deferred_dirty: '服务端已有更新的内容修订号，但本地存在未保存修改，已暂不覆盖',
  refresh_failed: '重新加载表单失败：已提交的内容未受影响，可重试加载',
  event_rejected: '收到的内容提交通知形态异常，未据此刷新表单',
})

export const WP_CONTENT_REFRESH_ACTION_HINT: Readonly<
  Record<WorkpaperContentRefreshStatus, string>
> = Object.freeze({
  idle: '',
  refreshing: '',
  synced: '',
  deferred_dirty: '请先保存或放弃本地修改，再点击「加载服务端最新版本」',
  refresh_failed: '请点击「重试加载」；若仍失败请打开详情追溯本次内容提交',
  event_rejected: '请打开详情核对通知内容；表单可继续使用，等待下一条提交通知',
})

/**
 * 表自证：`deferred_dirty` / `refresh_failed` / `event_rejected` 必须各有动作提示，
 * `refreshing` 不得有（此时用户无事可做），且提示不得与状态文案逐字相同。
 *
 * 🔴 存在的理由与 Task 34 的 `assertPresentationTextDisjoint()` 相同：一条提示只要
 * 逐字等于状态文案，就退化成第二份状态文案，而"两处都非空"这类判据全绿。
 */
export function assertContentRefreshTextDisjoint(): void {
  const statusTexts = new Set(Object.values(WP_CONTENT_REFRESH_STATUS_TEXT))
  const settled: readonly WorkpaperContentRefreshStatus[] = [
    'deferred_dirty',
    'refresh_failed',
    'event_rejected',
  ]
  for (const status of Object.keys(WP_CONTENT_REFRESH_STATUS_TEXT) as WorkpaperContentRefreshStatus[]) {
    const hint = WP_CONTENT_REFRESH_ACTION_HINT[status]
    if (settled.includes(status) && hint.trim() === '') {
      refuse(
        'content_refresh_settled_state_without_hint',
        `${status} 已落地却没有下一步提示 —— 那就是一次无限等待`,
      )
    }
    if (!settled.includes(status) && hint !== '') {
      refuse(
        'content_refresh_transient_state_has_hint',
        `${status} 不需要用户动作却给了动作提示`,
      )
    }
    if (hint !== '' && statusTexts.has(hint)) {
      refuse(
        'content_refresh_hint_duplicates_status_text',
        `${status} 的动作提示逐字等于某状态文案 —— 它会退化成第二份状态文案`,
      )
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 4. 协调器
// ═══════════════════════════════════════════════════════════════════════════

export interface WorkpaperContentRefreshSubscription {
  close(): void
}

export interface WorkpaperContentRefreshSubscribeContext {
  readonly projectId: string
  readonly eventName: string
  readonly onEvent: (payload: unknown) => void
  readonly onReconnect: () => void
  readonly onDegraded: () => void
}

export interface WorkpaperContentRefreshOptions {
  readonly wpId: Ref<string>
  readonly projectId: Ref<string>
  /**
   * 当前**已加载**内容的 revision（宿主真源）。
   *
   * 用回调而不是快照值：宿主自己保存成功后 revision 会变，协调器每次判定都必须读当时的值，
   * 否则"自己刚提交的那条事件"会被当成别人的更新再刷一次。
   */
  readonly loadedRevision: () => number | null
  /** 本地是否有未保存修改。dirty 时**不**静默覆盖。 */
  readonly isDirty: () => boolean
  /** 宿主重载钩子：必须加载到不低于 `minimumRevision` 的内容。 */
  readonly reload: (minimumRevision: number) => Promise<void>
  /** 注入点：默认订阅项目共享事件流。 */
  readonly subscribe?: (
    context: WorkpaperContentRefreshSubscribeContext,
  ) => WorkpaperContentRefreshSubscription
}

function defaultSubscribe(
  context: WorkpaperContentRefreshSubscribeContext,
): WorkpaperContentRefreshSubscription {
  return subscribeProjectEvent(
    context.projectId,
    context.eventName,
    (data) => context.onEvent(data),
    { onReconnect: context.onReconnect, onDegraded: context.onDegraded },
  )
}

/**
 * 消费 commit 后内容事件并驱动宿主刷新。
 *
 * 🔴 注入面里**没有任何 api 面**：只有 `reload` / `isDirty` / `loadedRevision`。
 * 于是"刷新失败之后又制造一个新 revision"在结构上不可达 —— 协调器根本没有写入口
 * （Task 35 正文：不影响已提交内容，不产生新 revision）。
 */
export function useWorkpaperContentRefresh(options: WorkpaperContentRefreshOptions) {
  const status = ref<WorkpaperContentRefreshStatus>('idle')
  const lastFailure = ref<WorkpaperContentRefreshFailure | null>(null)
  const lastUpdate = ref<WorkpaperContentUpdate | null>(null)
  /** dirty 或刷新失败时待加载的目标 revision（单调取最大）。 */
  const pendingRevision = ref<number | null>(null)
  const appliedRevision = ref<number | null>(null)
  const outcomes = ref<readonly WorkpaperContentRefreshOutcome[]>([])
  const reloadCallCount = ref(0)
  const degraded = ref(false)
  const seen = new Set<string>()
  let subscription: WorkpaperContentRefreshSubscription | null = null

  function record(outcome: WorkpaperContentRefreshOutcome): WorkpaperContentRefreshOutcome {
    outcomes.value = [...outcomes.value, outcome]
    return outcome
  }

  function rememberPending(revision: number): void {
    const known = pendingRevision.value
    pendingRevision.value = known === null ? revision : Math.max(known, revision)
  }

  /** 真正调用宿主 reload 的**唯一**地方。 */
  async function runReload(revision: number): Promise<WorkpaperContentRefreshOutcome> {
    status.value = 'refreshing'
    reloadCallCount.value += 1
    try {
      await options.reload(revision)
    } catch (error) {
      // 🔴 刷新失败与事件形态失败是两类：码不同、可重试性不同。归一到一个码会让
      // 其中一条分支永远不可达（永久 GREEN）。
      lastFailure.value = {
        kind: 'refresh',
        errorCode: 'content_refresh_reload_failed',
        message:
          `${WP_CONTENT_REFRESH_STATUS_TEXT.refresh_failed}（` +
          `目标修订号 ${revision}：${error instanceof Error ? error.message : String(error)}）`,
        retryable: true,
      }
      status.value = 'refresh_failed'
      rememberPending(revision)
      return record({
        kind: 'refresh_failed',
        dedupeKey: null,
        revision,
        errorCode: 'content_refresh_reload_failed',
      })
    }
    appliedRevision.value = revision
    pendingRevision.value = null
    lastFailure.value = null
    status.value = 'synced'
    return record({ kind: 'refreshed', dedupeKey: null, revision, errorCode: null })
  }

  /**
   * 吃进一条到达的事件。**七个分支，各自可达且互不覆盖。**
   *
   * 判定次序刻意如此：
   *
   * 1. 形态非法 → `rejected`（不进 `seen`：一条读不懂的事件不该把某个 revision 标成已处理）
   * 2. 不是本 wp → `other_wp`（共享连接是**项目级**的，同项目其它底稿的事件必然到达）
   * 3. 去重键命中 → `duplicate`（Requirement 13.3：重复投递不得重复刷新）
   * 4. `content_revision_advanced=false` → `representation_only`（纯表示升级不改 HTML 内容）
   * 5. `revision <= 已加载` → `stale`（自己刚提交的那条事件走这里，不自触发重载）
   * 6. dirty → `deferred_dirty`（**不**调 reload）
   * 7. 其余 → 真的刷新
   */
  async function handleEvent(wire: unknown): Promise<WorkpaperContentRefreshOutcome> {
    let update: WorkpaperContentUpdate
    try {
      update = parseContentUpdatedEvent(wire)
    } catch (error) {
      const code =
        error instanceof WorkpaperSyncContractError ? error.code : 'content_event_not_an_object'
      lastFailure.value = {
        kind: 'event',
        errorCode: code,
        message: `${WP_CONTENT_REFRESH_STATUS_TEXT.event_rejected}（${
          error instanceof Error ? error.message : String(error)
        }）`,
        // 事件形态失败不可由用户重试：重放同一条坏事件只会再坏一次，
        // 新事实只能由下一条事件（或宿主自己的显式重载）带来。
        retryable: false,
      }
      status.value = 'event_rejected'
      return record({ kind: 'rejected', dedupeKey: null, revision: null, errorCode: code })
    }
    if (update.wpId !== options.wpId.value) {
      return record({
        kind: 'other_wp',
        dedupeKey: `${update.wpId}|${update.revision}`,
        revision: update.revision,
        errorCode: null,
      })
    }
    const key = `${update.wpId}|${update.revision}`
    if (seen.has(key)) {
      return record({ kind: 'duplicate', dedupeKey: key, revision: update.revision, errorCode: null })
    }
    seen.add(key)
    lastUpdate.value = update
    if (!update.contentRevisionAdvanced) {
      // 纯表示升级：business revision 没变，HTML 投影一个字节都没动。
      return record({
        kind: 'representation_only',
        dedupeKey: key,
        revision: update.revision,
        errorCode: null,
      })
    }
    const loaded = options.loadedRevision()
    if (loaded !== null && update.revision <= loaded) {
      return record({ kind: 'stale', dedupeKey: key, revision: update.revision, errorCode: null })
    }
    if (options.isDirty()) {
      rememberPending(update.revision)
      status.value = 'deferred_dirty'
      return record({
        kind: 'deferred_dirty',
        dedupeKey: key,
        revision: update.revision,
        errorCode: null,
      })
    }
    // `runReload` 自己登记 outcome（`refreshed` / `refresh_failed` 两种），这里不再补记。
    return runReload(update.revision)
  }

  /**
   * 用户显式确认后加载待办 revision（dirty 分支的唯一出口）。
   *
   * 没有待办时**拒绝**而不是静默成功：静默成功会让"加载最新版本"按钮在没有待办时
   * 也显示成功，用户以为自己已经拿到最新内容。
   */
  async function acceptPending(): Promise<WorkpaperContentRefreshOutcome> {
    const revision = pendingRevision.value
    if (revision === null) {
      refuse(
        'content_refresh_no_pending_revision',
        '没有待加载的内容修订号 —— 不得把一次空操作显示成加载成功',
      )
    }
    return runReload(revision)
  }

  /** 刷新失败后的显式重试。与 `acceptPending()` 同一条 reload 路径。 */
  async function retry(): Promise<WorkpaperContentRefreshOutcome> {
    const revision = pendingRevision.value
    if (revision === null) {
      refuse(
        'content_refresh_nothing_to_retry',
        '没有失败的加载目标可重试 —— 事件形态失败不可重试，请等下一条事件',
      )
    }
    return runReload(revision)
  }

  /**
   * 放弃本次待办（保留本地未保存修改）。
   *
   * 刻意**不**清 `seen`：那条 revision 的事件确实已经处理过了，重新投递不该再弹一次。
   * 但状态回到 `idle` 而不是 `synced` —— 我们并没有加载到那个 revision，
   * 显示"已最新"就是骗人。
   */
  function dismissPending(): void {
    pendingRevision.value = null
    lastFailure.value = null
    status.value = 'idle'
  }

  /** 接到真实项目事件流上。`start()` 之后每条内容事件都经 `handleEvent()`。 */
  function start(): void {
    if (subscription !== null) return
    const subscribe = options.subscribe ?? defaultSubscribe
    subscription = subscribe({
      projectId: options.projectId.value,
      eventName: WP_CONTENT_UPDATED_EVENT_NAME,
      onEvent: (payload) => {
        void handleEvent(payload)
      },
      onReconnect: () => {
        // 断线期间的事件已经错过。协调器**不自己补拉** —— 那要打端点，而本模块
        // 刻意没有 api 面。这里只把"可能已落后"变成可见事实，由宿主决定是否重载。
        degraded.value = false
        if (status.value === 'synced' || status.value === 'idle') {
          status.value = 'idle'
        }
      },
      onDegraded: () => {
        degraded.value = true
      },
    })
  }

  function stop(): void {
    subscription?.close()
    subscription = null
  }

  const feedback = computed<{
    readonly kind: 'idle' | 'progress' | 'success' | 'warning' | 'error'
    readonly message: string
    readonly hint: string
  }>(() => {
    const text = WP_CONTENT_REFRESH_STATUS_TEXT[status.value]
    const hint = WP_CONTENT_REFRESH_ACTION_HINT[status.value]
    if (status.value === 'refresh_failed' || status.value === 'event_rejected') {
      return { kind: 'error', message: lastFailure.value?.message ?? text, hint }
    }
    if (status.value === 'deferred_dirty') return { kind: 'warning', message: text, hint }
    if (status.value === 'refreshing') return { kind: 'progress', message: text, hint }
    if (status.value === 'synced') return { kind: 'success', message: text, hint }
    return { kind: 'idle', message: text, hint }
  })

  return {
    status: readonly(status),
    lastFailure: readonly(lastFailure),
    lastUpdate: readonly(lastUpdate),
    pendingRevision: readonly(pendingRevision),
    appliedRevision: readonly(appliedRevision),
    outcomes: readonly(outcomes),
    reloadCallCount: readonly(reloadCallCount),
    degraded: readonly(degraded),
    feedback,
    handleEvent,
    acceptPending,
    retry,
    dismissPending,
    start,
    stop,
    /** 观测面：已处理过的去重键（判据用；不参与运行时行为）。 */
    seenKeys: () => Array.from(seen),
  }
}

export type WorkpaperContentRefresh = ReturnType<typeof useWorkpaperContentRefresh>
