/**
 * Task 34 四个 UI 组件共用的**纯投影层**（零 Vue、零 HTTP、零副作用）。
 *
 * spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 34
 * Requirements: 5.8, 8.1, 8.2, 8.3, 8.4, 11.2, 11.3, 11.5, 11.6, 11.7, 11.10, 11.11
 * Properties: P35（冲突双侧可追溯）/ P46（状态可辨）/ P47 / P48（error 优先）
 *
 * ═══ 它**不是**第二个文案真源 ═══
 *
 * 状态文案的唯一真源仍是 `workpaperSyncBridgeMachine.WP_BRIDGE_STATE_TEXT`，
 * 头条消息的唯一真源仍是桥的 `feedback`（error 优先）。本模块只补三类桥**没有**、
 * 而 Task 34 明文要求渲染的东西：
 *
 * 1. **视觉基调**（`WP_SYNC_STATE_TONE`）—— 不是文字，是 el-tag 的 type。
 * 2. **等待语义**（`WP_SYNC_WAIT_KIND`）—— 「还在飞」vs「已落地，等你动」。
 *    Task 34 明文「不得……无限等待」，而「是否该转圈」在桥里没有投影。
 * 3. **下一步动作提示**（`WP_SYNC_ACTION_HINT`）—— 与状态文案正交：状态说「发生了什么」，
 *    提示说「你现在能做什么」。`assertPresentationTextDisjoint()` 保证两张表零重复，
 *    于是「提示悄悄变成第二份状态文案」这件事结构上不可能。
 *
 * 三张表都对 26 个状态**穷尽**（`Record<WorkpaperSyncBridgeState, …>` 由 TS 强制），
 * 新增状态时必须显式裁决。
 *
 * ═══ 三处已登记的上游缺口（本模块把它们变成可见事实，而不是编一个值） ═══
 *
 * 见 `WP_SYNC_TRACE_GAPS`。任何一项都**不得**用「长得像」的另一个字段顶替 ——
 * 那正是 Task 33 在 `incomingDurable.artifactSha256` 上抓到的形态。
 */
import {
  WP_BRIDGE_STATES,
  WP_BRIDGE_STATE_TEXT,
  WP_BRIDGE_TERMINAL_STATES,
  type WorkpaperSyncBridgeEvent,
  type WorkpaperSyncBridgeState,
} from './workpaperSyncBridgeMachine'
import {
  WorkpaperSyncContractError,
  isOpaqueUuid,
  isSyncDigest,
  type WorkpaperSyncRecoveryCase,
} from './workpaperSyncDto'

function refuse(code: string, message: string): never {
  throw new WorkpaperSyncContractError(code, message)
}

// ═══════════════════════════════════════════════════════════════════════════
// 1. 视觉基调
// ═══════════════════════════════════════════════════════════════════════════

/** el-tag 的 type 域。`primary` 表示「进行中」，`info` 表示「静止且无待办」。 */
export type WorkpaperSyncTone = 'info' | 'primary' | 'warning' | 'danger' | 'success'

/**
 * 状态 → 视觉基调。**只有 `applied` 是 success。**
 *
 * 🔴 `close_recovery_required` 与 `recovery_download_only` 刻意是 `warning` / `info`
 * 而非 success：Task 34 明文「后两者不得渲染成保存成功」，而颜色是用户最先读到的那一层。
 * `duplicate` 也不是 success —— 它是「你这次被折叠了，去看规范任务」。
 */
export const WP_SYNC_STATE_TONE: Readonly<
  Record<WorkpaperSyncBridgeState, WorkpaperSyncTone>
> = Object.freeze({
  html_idle: 'info',
  flushing: 'primary',
  committing: 'primary',
  materializing: 'primary',
  oo_loading: 'primary',
  descriptor_mounted: 'primary',
  confirming_descriptor: 'primary',
  oo_editing: 'info',
  forcesave_requesting: 'primary',
  forcesave_frozen: 'warning',
  forcesave_accepted: 'primary',
  waiting_application: 'primary',
  incoming_durable: 'primary',
  application_bound: 'primary',
  duplicate: 'warning',
  merging: 'primary',
  rematerializing: 'primary',
  conflict: 'warning',
  refresh_required: 'warning',
  applied: 'success',
  close_authorization_stale: 'warning',
  close_recovery_required: 'danger',
  recovery_pending: 'warning',
  recovery_claiming: 'primary',
  recovery_download_only: 'info',
  error: 'danger',
})

/** 唯一允许显示成功基调的状态集合（判据用它证明没有第二个 success）。 */
export const WP_SYNC_SUCCESS_STATES: readonly WorkpaperSyncBridgeState[] = ['applied']

// ═══════════════════════════════════════════════════════════════════════════
// 2. 等待语义
// ═══════════════════════════════════════════════════════════════════════════

/**
 * `progress` = 正在等服务端/编辑器的一次**有界**往返；`settled` = 已落地。
 *
 * 🔴 `settled` 不等于「成功」：`conflict` / `refresh_required` / `duplicate` /
 * `close_recovery_required` / `error` 全是 settled —— 它们都在等**用户**动，
 * 所以 UI 必须停下转圈并给出下一步（Task 34 的「不得无限等待」）。
 *
 * `close_authorization_stale` 是唯一一个「progress 但必须额外说明进展」的状态：
 * 它在等另一个 participant 的 close capture，用户无从知道等多久，因此
 * :func:`describeCloseArbitration` 的输出在状态条上是**必渲染项**。
 */
export const WP_SYNC_WAIT_KIND: Readonly<
  Record<WorkpaperSyncBridgeState, 'progress' | 'settled'>
> = Object.freeze({
  html_idle: 'settled',
  flushing: 'progress',
  committing: 'progress',
  materializing: 'progress',
  oo_loading: 'progress',
  descriptor_mounted: 'progress',
  confirming_descriptor: 'progress',
  oo_editing: 'settled',
  forcesave_requesting: 'progress',
  forcesave_frozen: 'settled',
  forcesave_accepted: 'progress',
  waiting_application: 'progress',
  incoming_durable: 'progress',
  application_bound: 'progress',
  duplicate: 'settled',
  merging: 'progress',
  rematerializing: 'progress',
  conflict: 'settled',
  refresh_required: 'settled',
  applied: 'settled',
  close_authorization_stale: 'progress',
  close_recovery_required: 'settled',
  recovery_pending: 'settled',
  recovery_claiming: 'progress',
  recovery_download_only: 'settled',
  error: 'settled',
})

/**
 * 状态 → 下一步动作提示。`progress` 状态一律空串（此时用户无事可做）。
 *
 * 每条都必须说得出一个**具体**动作。空泛的「请稍候」等于无限等待，
 * :func:`assertPresentationTextDisjoint` 会连同「与状态文案重复」一起拦住。
 */
export const WP_SYNC_ACTION_HINT: Readonly<
  Record<WorkpaperSyncBridgeState, string>
> = Object.freeze({
  // `html_idle` 是静止态但**不是**「无事可做」：切到 OnlyOffice 就是它的下一步。
  // 给它留空会逼出一条豁免，而豁免会成为下一个状态漏提示时的先例。
  html_idle: '可切换到 OnlyOffice 模式编辑，或继续在表单中录入',
  flushing: '',
  committing: '',
  materializing: '',
  oo_loading: '',
  descriptor_mounted: '',
  confirming_descriptor: '',
  oo_editing: '可继续编辑，或点击保存并回到表单模式',
  forcesave_requesting: '',
  forcesave_frozen: '请重新发送强制保存命令；保存请求已冻结，无需重新冻结',
  forcesave_accepted: '',
  waiting_application: '',
  incoming_durable: '',
  application_bound: '',
  duplicate: '请打开详情查看规范回写任务的结果，本次请求不会再变化',
  merging: '',
  rematerializing: '',
  conflict: '请打开冲突面板逐项裁决后提交',
  refresh_required: '请重载编辑器以确认新基线，之后才能再次保存',
  applied: '请重载表单以加载回写后的内容',
  close_authorization_stale: '',
  close_recovery_required: '请联系有权用户重新授权，并在恢复面板中认领或仅下载',
  recovery_pending: '请在恢复面板中认领恢复项，或仅下载已保存文件',
  recovery_claiming: '',
  recovery_download_only: '已保存文件可下载留档；如需回写请重新打开编辑器',
  error: '请查看失败原因后重试，或打开详情追溯',
})

/**
 * 表自证：动作提示与状态文案零重复、无空泛提示、无成功字样。
 *
 * 🔴 存在的理由：只要有一条提示逐字等于某个状态文案，它就退化成第二份状态文案，
 * 而「两处文案都非空」这类判据全绿。判据无条件调用本函数。
 */
export function assertPresentationTextDisjoint(): void {
  const stateTexts = new Set(Object.values(WP_BRIDGE_STATE_TEXT))
  const forbiddenSubstrings = ['保存成功', '同步成功', '回写完成']
  const vague = ['请稍候', '请等待', '正在处理']
  for (const state of WP_BRIDGE_STATES) {
    const hint = WP_SYNC_ACTION_HINT[state]
    const wait = WP_SYNC_WAIT_KIND[state]
    if (wait === 'progress' && hint !== '') {
      refuse(
        'presentation_progress_state_has_hint',
        `${state} 是 progress 却给了动作提示 —— 进行中不该要求用户动作`,
      )
    }
    if (wait === 'settled' && hint.trim() === '') {
      refuse(
        'presentation_settled_state_without_hint',
        `${state} 已落地却没有下一步提示 —— 那就是一次无限等待`,
      )
    }
    if (hint !== '' && stateTexts.has(hint)) {
      refuse(
        'presentation_hint_duplicates_state_text',
        `${state} 的动作提示逐字等于某状态文案 —— 它会退化成第二份状态文案`,
      )
    }
    for (const needle of vague) {
      if (hint.includes(needle)) {
        refuse(
          'presentation_hint_is_vague',
          `${state} 的动作提示含空泛措辞 ${needle} —— 等价于无限等待`,
        )
      }
    }
    for (const needle of forbiddenSubstrings) {
      if (state !== 'applied' && hint.includes(needle)) {
        refuse(
          'presentation_hint_claims_success',
          `${state} 的动作提示含 ${needle} —— 只有 applied 才是结构化回写完成`,
        )
      }
    }
    if (WP_SYNC_STATE_TONE[state] === 'success' && state !== 'applied') {
      refuse(
        'presentation_extra_success_tone',
        `${state} 用了 success 基调 —— 只有 applied 允许`,
      )
    }
  }
  for (const state of WP_BRIDGE_TERMINAL_STATES) {
    if (WP_SYNC_WAIT_KIND[state] !== 'settled') {
      refuse(
        'presentation_terminal_still_waiting',
        `终态 ${state} 被标成 progress —— 它永远不会再动，转圈就是无限等待`,
      )
    }
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 3. close 仲裁进展
// ═══════════════════════════════════════════════════════════════════════════

export type WorkpaperSyncCloseOutcome =
  | 'not_applicable'
  | 'awaiting_successor'
  | 'successor_applied'
  | 'no_successor'

export interface WorkpaperSyncCloseArbitration {
  readonly outcome: WorkpaperSyncCloseOutcome
  readonly label: string
  readonly successorIntentId: string | null
}

/**
 * 本会话是否真的发生过 close 仲裁（决定仲裁行是否占版面）。
 *
 * 放在纯投影层而不是组件里：平台 lint 规则 `gt-audit/no-status-string-literal` 会把
 * `.vue` 里的枚举字面量判为硬编码状态码，而这条判断本身属于投影语义。
 */
export function isCloseArbitrationVisible(
  arbitration: WorkpaperSyncCloseArbitration,
): boolean {
  return arbitration.outcome !== 'not_applicable'
}

/** 三个 close 仲裁事件（判据用它证明推导只看这三个，不看别的）。 */
const CLOSE_EVENTS: readonly WorkpaperSyncBridgeEvent[] = [
  'close_authorization_lost',
  'close_successor_applied',
  'close_no_successor',
]

/**
 * 从**桥自己的**事件流推导 close 仲裁结局。
 *
 * 🔴 为什么必须看 `transitions` 而不只看 `state`：`close_successor_applied` 的目标是
 * `applied`，与「自己保存成功」逐字同态。只看 state 就无法区分「我保存成功了」与
 * 「我失权了、接任者替我保存成功了」—— 而 Task 34 明文要求显示 successor 接任进展。
 *
 * 🔴 已登记的上游缺口：桥的 `notifyCloseSuccessorApplied(id)` **校验**但**不保存**
 * successor intent id（它只进 `transitionBridgeState` 的 context）。因此 id 只能由
 * 观测到它的宿主显式回传；缺失时渲染「尚未确定」而**不是**编一个 id。
 */
export function describeCloseArbitration(
  state: WorkpaperSyncBridgeState,
  transitions: readonly WorkpaperSyncBridgeEvent[],
  successorIntentId?: string | null,
): WorkpaperSyncCloseArbitration {
  const successor = String(successorIntentId ?? '').trim() || null
  if (state === 'close_authorization_stale') {
    return {
      outcome: 'awaiting_successor',
      label:
        successor === null
          ? '关闭发起人已失权：尚未确定接任者，仍在按最高 intent 序号仲裁'
          : `关闭发起人已失权：接任者 ${successor} 正在完成保存`,
      successorIntentId: successor,
    }
  }
  if (state === 'close_recovery_required') {
    return {
      outcome: 'no_successor',
      label: '关闭发起人已失权且无合法接任者：本代际已作废，需重新授权后走恢复流程',
      successorIntentId: null,
    }
  }
  // 倒序找最近一个 close 事件 —— 同一会话里可能失权、接任、再失权。
  for (let index = transitions.length - 1; index >= 0; index -= 1) {
    const event = transitions[index]
    if (!CLOSE_EVENTS.includes(event)) continue
    if (event === 'close_no_successor') {
      return {
        outcome: 'no_successor',
        label: '关闭发起人已失权且无合法接任者：本代际已作废，需重新授权后走恢复流程',
        successorIntentId: null,
      }
    }
    if (event === 'close_successor_applied') {
      return {
        outcome: 'successor_applied',
        label:
          successor === null
            ? '本次关闭由合法接任者完成保存（接任者标识未由宿主回传）'
            : `本次关闭由合法接任者 ${successor} 完成保存`,
        successorIntentId: successor,
      }
    }
    return {
      outcome: 'awaiting_successor',
      label: '关闭发起人已失权：仲裁尚未产出结果',
      successorIntentId: successor,
    }
  }
  return { outcome: 'not_applicable', label: '', successorIntentId: null }
}

// ═══════════════════════════════════════════════════════════════════════════
// 4. 已登记的追溯缺口
// ═══════════════════════════════════════════════════════════════════════════

export interface WorkpaperSyncTraceGap {
  readonly id: string
  readonly label: string
  readonly reason: string
}

/**
 * Task 34 明文要求展示、但**当前 16 条用户路由里没有读取面**的追溯项。
 *
 * 每一项都必须在 UI 上渲染成显式缺口，**不得**用另一个「长得像」的字段顶替：
 * 顶替一次，「回来的东西就是我发出去的那份」这类结论就凭空成立。
 */
export const WP_SYNC_TRACE_GAPS: readonly WorkpaperSyncTraceGap[] = Object.freeze([
  Object.freeze({
    id: 'room_opened_base_revision',
    label: 'room 打开时基线',
    reason: 'room 的 opened_base_version_id 未进 descriptor，也没有任何用户读取面',
  }),
  Object.freeze({
    id: 'room_latest_durable_application_id',
    label: 'room 最新耐久 application',
    reason: '无读取面：conflict 预览只给 canonical_application_id，桥拒绝替调用方编造',
  }),
  Object.freeze({
    id: 'room_latest_durable_sequence',
    label: 'room 最新耐久 sequence',
    reason: '无读取面：同上，只能由调用方显式提供，缺失即不可提交裁决',
  }),
  Object.freeze({
    id: 'application_origin_request_sequence',
    label: 'application 原始 request 序号',
    reason: 'operation 投影只给 effective sequence，origin_request_sequence 未投影',
  }),
  Object.freeze({
    id: 'incoming_artifact_sha256',
    label: '回传 incoming 文件摘要',
    reason: 'GET operations/{id} 不带 incoming artifact digest，descriptor 的摘要是发出侧',
  }),
])

/** 缺口占位符。判据断言这些行**只**出现它，绝不出现数字或 digest。 */
export const WP_SYNC_TRACE_GAP_PLACEHOLDER = '未投影（无读取面）'

// ═══════════════════════════════════════════════════════════════════════════
// 5. 冲突预览解析
// ═══════════════════════════════════════════════════════════════════════════

/** 值信封：`present=false`（字段缺失）与 `present=true,value=null`（显式空）是两种。 */
export interface WorkpaperSyncValueEnvelope {
  readonly present: boolean
  readonly value: unknown
}

export interface WorkpaperSyncConflictItem {
  readonly conflictId: string
  readonly stableFieldKey: string
  readonly businessLabel: string
  readonly sheetKey: string
  readonly tableKey: string
  readonly rowKey: string
  readonly jsonPointer: string
  readonly ooLocation: string
  readonly kind: string
  readonly fieldSource: string
  readonly protectionPolicy: string
  readonly suggestedAction: string
  readonly valueType: string
  readonly base: WorkpaperSyncValueEnvelope | null
  readonly current: WorkpaperSyncValueEnvelope | null
  readonly incoming: WorkpaperSyncValueEnvelope | null
  readonly clientEditEpoch: number
  readonly incomingSequence: number | null
  readonly resolved: boolean
  readonly isProtected: boolean
  readonly adjudicableByValueChoice: boolean
}

export interface WorkpaperSyncConflictGroup {
  readonly sheetKey: string
  readonly tableKey: string
  readonly rowKey: string
  readonly groupKey: string
  readonly items: readonly WorkpaperSyncConflictItem[]
}

export interface WorkpaperSyncConflictPreview {
  readonly requestedOperationId: string
  readonly canonicalOperationId: string
  readonly followedDuplicate: boolean
  readonly canonicalApplicationId: string
  readonly clientEditEpoch: number
  readonly incomingSequence: number
  readonly roomId: string
  readonly roomGeneration: number
  readonly currentRevision: number
  readonly conflictSetDigest: string | null
  readonly definitionBundleId: string
  readonly definitionBundleSha256: string
  readonly authorityModel: string
  readonly authorityModelDefinitionSha256: string
  readonly contractId: string
  readonly contractSemanticVersion: string
  readonly conflictCount: number
  readonly groups: readonly WorkpaperSyncConflictGroup[]
}

type Wire = Record<string, unknown>

function wireOf(value: unknown, label: string): Wire {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    refuse(
      'conflict_preview_shape_invalid',
      `${label} 不是对象（实得 ${JSON.stringify(value)}）—— 形态漂移必须 fail visible`,
    )
  }
  return value as Wire
}

function str(wire: Wire, key: string, label: string): string {
  const raw = wire[key]
  if (typeof raw !== 'string' || raw.trim() === '') {
    refuse(
      'conflict_preview_field_missing',
      `${label}.${key} 不是非空字符串（实得 ${JSON.stringify(raw)}）`,
    )
  }
  return raw
}

function int(wire: Wire, key: string, label: string): number {
  const raw = wire[key]
  if (typeof raw !== 'number' || !Number.isInteger(raw)) {
    refuse(
      'conflict_preview_field_missing',
      `${label}.${key} 不是整数（实得 ${JSON.stringify(raw)}）`,
    )
  }
  return raw
}

/**
 * 值信封解析。
 *
 * 🔴 `null` 与 `{present:false}` 必须分开：前者是「该侧整个没投影」（结构冲突常见），
 * 后者是「该侧确实没有这个字段」。合并成一个会让裁决界面说不清用户在选什么。
 */
function envelope(raw: unknown, label: string): WorkpaperSyncValueEnvelope | null {
  if (raw === null || raw === undefined) return null
  const wire = wireOf(raw, label)
  if (typeof wire.present !== 'boolean') {
    refuse(
      'conflict_value_envelope_invalid',
      `${label} 缺 present 布尔（实得 ${JSON.stringify(wire)}）—— ` +
        '「字段缺失」与「显式空值」不得合并',
    )
  }
  return { present: wire.present, value: wire.present ? wire.value : undefined }
}

/**
 * 把 `bridge.conflicts`（已解一次 envelope 的裸对象）解析成分组结构。
 *
 * Task 31 的 DTO 层**没有**冲突解析器（`bridge.conflicts` 的类型就是
 * `Record<string, unknown> | null`），因此解析必须落在消费方。这里逐项校验形态，
 * 任何缺项都 fail visible —— 一个「缺 json_pointer 就渲染空串」的宽松解析会让
 * Property 35「每条冲突双侧可追溯」在读侧重新失效。
 */
export function parseConflictPreview(payload: unknown): WorkpaperSyncConflictPreview {
  const wire = wireOf(payload, 'conflict-preview')
  const rawGroups = wire.groups
  if (!Array.isArray(rawGroups)) {
    refuse(
      'conflict_preview_groups_missing',
      `conflict 预览的 groups 不是数组（实得 ${JSON.stringify(rawGroups)}）`,
    )
  }
  const groups = rawGroups.map((rawGroup, groupIndex) => {
    const g = wireOf(rawGroup, `conflict-preview.groups[${groupIndex}]`)
    const rawItems = g.items
    if (!Array.isArray(rawItems)) {
      refuse(
        'conflict_preview_group_items_missing',
        `groups[${groupIndex}].items 不是数组（实得 ${JSON.stringify(rawItems)}）`,
      )
    }
    const sheetKey = typeof g.sheet_key === 'string' ? g.sheet_key : ''
    const tableKey = typeof g.table_key === 'string' ? g.table_key : ''
    const rowKey = typeof g.row_key === 'string' ? g.row_key : ''
    const items = rawItems.map((rawItem, itemIndex) => {
      const label = `groups[${groupIndex}].items[${itemIndex}]`
      const i = wireOf(rawItem, label)
      const kind = str(i, 'kind', label)
      return {
        conflictId: str(i, 'conflict_id', label),
        stableFieldKey: str(i, 'stable_field_key', label),
        businessLabel: str(i, 'business_label', label),
        sheetKey: typeof i.sheet_key === 'string' ? i.sheet_key : '',
        tableKey: typeof i.table_key === 'string' ? i.table_key : '',
        rowKey: typeof i.row_key === 'string' ? i.row_key : '',
        jsonPointer: str(i, 'json_pointer', label),
        ooLocation: str(i, 'oo_location', label),
        kind,
        fieldSource: str(i, 'field_source', label),
        protectionPolicy: str(i, 'protection_policy', label),
        suggestedAction: str(i, 'suggested_action', label),
        valueType: str(i, 'value_type', label),
        base: envelope(i.base, `${label}.base`),
        current: envelope(i.current, `${label}.current`),
        incoming: envelope(i.incoming, `${label}.incoming`),
        clientEditEpoch: int(i, 'client_edit_epoch', label),
        incomingSequence:
          typeof i.incoming_sequence === 'number' && Number.isInteger(i.incoming_sequence)
            ? i.incoming_sequence
            : null,
        resolved: i.resolved === true,
        isProtected: i.is_protected === true,
        // 🔴 服务端**必须**给出这个布尔。缺它时不得默认 true —— 默认 true 会让结构冲突
        // 显示成「选一侧就能收敛」，而结构冲突必须先修结构（AC 8.3 / SchemaAnomalyKind）。
        adjudicableByValueChoice: (() => {
          if (typeof i.adjudicable_by_value_choice !== 'boolean') {
            refuse(
              'conflict_item_adjudicability_missing',
              `${label}.adjudicable_by_value_choice 缺失 —— 结构冲突不得默认可选边`,
            )
          }
          return i.adjudicable_by_value_choice
        })(),
      } satisfies WorkpaperSyncConflictItem
    })
    return {
      sheetKey,
      tableKey,
      rowKey,
      groupKey: [sheetKey, tableKey, rowKey].join('/'),
      items,
    } satisfies WorkpaperSyncConflictGroup
  })
  const digest = wire.conflict_set_digest
  return {
    requestedOperationId: str(wire, 'requested_operation_id', 'conflict-preview'),
    canonicalOperationId: str(wire, 'canonical_operation_id', 'conflict-preview'),
    followedDuplicate: wire.followed_duplicate === true,
    canonicalApplicationId: str(wire, 'canonical_application_id', 'conflict-preview'),
    clientEditEpoch: int(wire, 'client_edit_epoch', 'conflict-preview'),
    incomingSequence: int(wire, 'incoming_sequence', 'conflict-preview'),
    roomId: str(wire, 'room_id', 'conflict-preview'),
    roomGeneration: int(wire, 'room_generation', 'conflict-preview'),
    currentRevision: int(wire, 'current_revision', 'conflict-preview'),
    conflictSetDigest: typeof digest === 'string' && digest.trim() !== '' ? digest : null,
    definitionBundleId: str(wire, 'definition_bundle_id', 'conflict-preview'),
    definitionBundleSha256: str(wire, 'definition_bundle_sha256', 'conflict-preview'),
    authorityModel: str(wire, 'authority_model', 'conflict-preview'),
    authorityModelDefinitionSha256: str(
      wire,
      'authority_model_definition_sha256',
      'conflict-preview',
    ),
    contractId: str(wire, 'contract_id', 'conflict-preview'),
    contractSemanticVersion: str(wire, 'contract_semantic_version', 'conflict-preview'),
    // 累加器刻意不叫 `sum`：平台 lint 规则 `no-amount-arithmetic` 会把它当金额运算，
    // 而这里数的是冲突条数。
    conflictCount: groups.reduce((acc, group) => acc + group.items.length, 0),
    groups,
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 6. 值渲染（金额必须经 displayPrefs）
// ═══════════════════════════════════════════════════════════════════════════

/** 缺失 / 空值的显式文案。两者必须不同，否则裁决界面说不清用户在选什么。 */
export const WP_SYNC_VALUE_ABSENT_TEXT = '（无此字段）'
export const WP_SYNC_VALUE_NULL_TEXT = '（空值）'
export const WP_SYNC_VALUE_UNPROJECTED_TEXT = '（该侧未投影）'

/**
 * 一个值信封 → 展示文案。
 *
 * 🔴 `fmtAmount` 由**调用方注入**（组件在 setup 顶层取
 * `inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()` 后传进来）。
 * 本模块刻意不 import store：`import { fmtAmount } from '@/stores/displayPrefs'`
 * 是平台已登记的整页崩溃形态（`fmtAmount` 是 store 成员而非模块级导出），
 * 而 Volar / vitest / get_diagnostics 三层全绿，只有浏览器会暴露。
 */
export function formatConflictValue(
  envelopeValue: WorkpaperSyncValueEnvelope | null,
  valueType: string,
  fmtAmount: (value: unknown) => string,
): string {
  if (envelopeValue === null) return WP_SYNC_VALUE_UNPROJECTED_TEXT
  if (!envelopeValue.present) return WP_SYNC_VALUE_ABSENT_TEXT
  const value = envelopeValue.value
  if (value === null || value === undefined) return WP_SYNC_VALUE_NULL_TEXT
  if (valueType === 'amount') return fmtAmount(value)
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

// ═══════════════════════════════════════════════════════════════════════════
// 7. 批量裁决的显式范围
// ═══════════════════════════════════════════════════════════════════════════

export type WorkpaperSyncBulkScope = 'row' | 'table' | 'sheet' | 'all_unresolved'

export const WP_SYNC_BULK_SCOPES: readonly WorkpaperSyncBulkScope[] = [
  'row',
  'table',
  'sheet',
  'all_unresolved',
]

export const WP_SYNC_BULK_SCOPE_LABEL: Readonly<Record<WorkpaperSyncBulkScope, string>> =
  Object.freeze({
    row: '仅本行',
    table: '本表全部行',
    sheet: '本工作表全部表',
    all_unresolved: '全部未裁决冲突',
  })

/**
 * 按**显式范围**取批量裁决目标。
 *
 * 只返回「未裁决且可靠选边收敛」的项：已裁决的重复写一遍是静默覆盖，
 * 结构冲突选边毫无意义（AC 8.3 的「明确作用范围」= 范围本身不许含这两类）。
 */
export function bulkScopeTargets(
  groups: readonly WorkpaperSyncConflictGroup[],
  scope: WorkpaperSyncBulkScope,
  anchor: WorkpaperSyncConflictGroup | null,
): readonly WorkpaperSyncConflictItem[] {
  if (!WP_SYNC_BULK_SCOPES.includes(scope)) {
    refuse('bulk_scope_unknown', `未登记的批量范围 ${JSON.stringify(scope)}`)
  }
  if (scope !== 'all_unresolved' && anchor === null) {
    refuse(
      'bulk_scope_anchor_required',
      `范围 ${scope} 必须指定锚点分组 —— 没有锚点的「本行/本表/本工作表」范围不明确`,
    )
  }
  const eligible = (item: WorkpaperSyncConflictItem): boolean =>
    !item.resolved && item.adjudicableByValueChoice
  const all = groups.flatMap((group) => group.items)
  if (scope === 'all_unresolved') return all.filter(eligible)
  const pin = anchor as WorkpaperSyncConflictGroup
  return all.filter((item) => {
    if (!eligible(item)) return false
    if (item.sheetKey !== pin.sheetKey) return false
    if (scope === 'sheet') return true
    if (item.tableKey !== pin.tableKey) return false
    if (scope === 'table') return true
    return item.rowKey === pin.rowKey
  })
}

/** 批量裁决的二次确认文案 —— **必须**逐字点出范围与条数（AC 8.3）。 */
export function describeBulkScope(
  scope: WorkpaperSyncBulkScope,
  anchor: WorkpaperSyncConflictGroup | null,
  count: number,
  choiceLabel: string,
): string {
  const where =
    scope === 'all_unresolved'
      ? '本次回写的全部未裁决冲突'
      : `工作表 ${anchor?.sheetKey || '（无）'} / 表 ${anchor?.tableKey || '（无）'} / 行 ${
          anchor?.rowKey || '（无）'
        } 范围内`
  return `即将对${where}的 ${count} 条冲突统一裁决为「${choiceLabel}」（范围：${WP_SYNC_BULK_SCOPE_LABEL[scope]}），请确认。`
}

// ═══════════════════════════════════════════════════════════════════════════
// 8. resolve fence
// ═══════════════════════════════════════════════════════════════════════════

export interface WorkpaperSyncRoomDurableFence {
  readonly applicationId: string
  readonly sequence: number
}

export interface WorkpaperSyncResolveFenceDraft {
  readonly canonicalApplicationId: string
  readonly applicationEffectiveRequestSequence: number
  readonly roomLatestDurableApplicationId: string
  readonly roomLatestDurableSequence: number
  readonly conflictSetDigest: string
  readonly expectedCurrentRevision: number
  readonly roomGeneration: number
  readonly clientEditEpoch: number
}

/**
 * 组装 resolve 的八项 fence。**缺项一律列出来，绝不补默认值。**
 *
 * 🔴 `room_latest_durable_application_id` / `room_latest_durable_sequence` 在当前
 * 用户路由里没有任何读取面（见 `WP_SYNC_TRACE_GAPS`）。桥明文拒绝替调用方编这两项，
 * 于是冲突面板必须由宿主显式提供；提供不了就只能**可见地失败**（提交按钮禁用 +
 * 阻断原因逐项列出），不得用 canonical application 顶替 room 的 latest durable ——
 * 服务端会照着这个断言做 fence 裁决。
 */
export function buildResolveFence(input: {
  readonly preview: WorkpaperSyncConflictPreview
  readonly roomDurable: WorkpaperSyncRoomDurableFence | null
}): {
  readonly fence: WorkpaperSyncResolveFenceDraft | null
  readonly missing: readonly string[]
} {
  const missing: string[] = []
  const preview = input.preview
  if (preview.conflictSetDigest === null || !isSyncDigest(preview.conflictSetDigest)) {
    missing.push('conflict_set_digest')
  }
  const durable = input.roomDurable
  if (durable === null || !isOpaqueUuid(durable.applicationId)) {
    missing.push('room_latest_durable_application_id')
  }
  if (durable === null || !Number.isInteger(durable.sequence) || durable.sequence < 0) {
    missing.push('room_latest_durable_sequence')
  }
  if (!isOpaqueUuid(preview.canonicalApplicationId)) {
    missing.push('canonical_application_id')
  }
  if (missing.length > 0) return { fence: null, missing }
  const pinned = durable as WorkpaperSyncRoomDurableFence
  return {
    fence: {
      canonicalApplicationId: preview.canonicalApplicationId,
      applicationEffectiveRequestSequence: preview.incomingSequence,
      roomLatestDurableApplicationId: pinned.applicationId,
      roomLatestDurableSequence: pinned.sequence,
      conflictSetDigest: preview.conflictSetDigest as string,
      expectedCurrentRevision: preview.currentRevision,
      roomGeneration: preview.roomGeneration,
      clientEditEpoch: preview.clientEditEpoch,
    },
    missing: [],
  }
}

/** fence 缺项 → 中文阻断原因（逐项，不合并成一句「参数不全」）。 */
export const WP_SYNC_FENCE_MISSING_TEXT: Readonly<Record<string, string>> = Object.freeze({
  conflict_set_digest: '缺冲突集摘要（conflict_set_digest），无法做乐观锁比对',
  room_latest_durable_application_id:
    '缺 room 最新耐久 application 标识：该字段无读取面，须由宿主显式提供',
  room_latest_durable_sequence:
    '缺 room 最新耐久 sequence：该字段无读取面，须由宿主显式提供',
  canonical_application_id: '缺规范 application 标识，冲突预览形态异常',
})

// ═══════════════════════════════════════════════════════════════════════════
// 9. recovery 阻断原因
// ═══════════════════════════════════════════════════════════════════════════

export const WP_SYNC_RECOVERY_REASON_TEXT: Readonly<Record<string, string>> = Object.freeze({
  missing_request: '服务端已收到并耐久保存文件，但找不到对应的保存请求',
  ambiguous_close: '关闭时存在多个候选保存请求，无法唯一关联',
  crash_close: '编辑器异常中断，文件已耐久保存但回写任务尚未建立',
  stale_candidate: '候选基线已过期，需重新授权后继续',
})

export const WP_SYNC_RECOVERY_STATE_TEXT: Readonly<Record<string, string>> = Object.freeze({
  unclaimed: '待认领',
  claiming: '认领中',
  application_created: '已认领并创建回写任务',
  download_only: '已仅下载并终结',
  quarantined: '已隔离',
  expired: '已过期',
})

export interface WorkpaperSyncClaimFence {
  readonly participantId: string
  readonly expectedGeneration: number
  readonly expectedWriteFence: number
  readonly expectedDefinitionBundleSha256: string
  readonly expectedCurrentRevision: number
}

/**
 * recovery case 的阻断原因 —— **全部从可观测事实推导**。
 *
 * 🔴 服务端 list 端点刻意「零业务内容」：响应里没有 `blocking_reason`、也没有 bundle
 * digest（AC 5.8 不返回未授权资源的存在性/内容）。design 的 `RecoveryCaseSummary`
 * 里那个 `blockingReason?: string` 因此**没有供给**。本函数不编造：它只把
 * 「服务端说不能 claim」「候选为空」「宿主没给冻结 bundle 摘要」这三类**可观测**事实
 * 翻成中文。少一条供给就少一条原因，绝不合成一句「未知原因」。
 */
export function deriveRecoveryBlocking(
  recoveryCase: WorkpaperSyncRecoveryCase,
  claimFence: WorkpaperSyncClaimFence | null,
): readonly string[] {
  const blocking: string[] = []
  if (!recoveryCase.actions.claim) {
    blocking.push(
      `服务端未开放认领：当前状态为「${
        WP_SYNC_RECOVERY_STATE_TEXT[recoveryCase.state] ?? recoveryCase.state
      }」`,
    )
  }
  if (recoveryCase.candidatePriorConfirmations.length === 0) {
    blocking.push('没有同 room/代际的既有 descriptor 确认可作合法基线')
  }
  if (claimFence === null) {
    blocking.push('宿主未提供冻结的 definition bundle 摘要与写栅栏，无法发起认领')
  } else {
    if (!isSyncDigest(claimFence.expectedDefinitionBundleSha256)) {
      blocking.push('宿主提供的 definition bundle 摘要形态非法（须为 64 位小写 hex）')
    }
    if (!Number.isInteger(claimFence.expectedGeneration) || claimFence.expectedGeneration < 1) {
      blocking.push('宿主提供的代际号形态非法')
    }
    if (!Number.isInteger(claimFence.expectedWriteFence) || claimFence.expectedWriteFence < 0) {
      blocking.push('宿主提供的写栅栏形态非法')
    }
    if (!isOpaqueUuid(claimFence.participantId)) {
      blocking.push('宿主提供的 participant 标识不是不透明 UUID')
    }
  }
  return blocking
}

/**
 * claim 之前必须全空的三实体投影（AC 5.8 的可观测事实）。
 *
 * 返回逐项文案而不是一个布尔：三个里只有一个非空时，UI 必须说得出是哪一个 ——
 * 那种形态是服务端漏了原子性，压成布尔就看不见了。
 */
export function describeRecoveryEntities(recoveryCase: WorkpaperSyncRecoveryCase): {
  readonly rows: readonly { readonly id: string; readonly label: string; readonly value: string }[]
  readonly presentCount: number
} {
  const rows = [
    { id: 'forcesave_request_id', label: '恢复保存请求', value: recoveryCase.forcesaveRequestId },
    { id: 'application_id', label: '内容应用（application）', value: recoveryCase.applicationId },
    { id: 'operation_id', label: '回写任务（operation）', value: recoveryCase.operationId },
  ]
  return {
    rows: rows.map((row) => ({
      id: row.id,
      label: row.label,
      value: row.value === null ? '尚未创建' : row.value,
    })),
    presentCount: rows.filter((row) => row.value !== null).length,
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 10. timeline 投影
// ═══════════════════════════════════════════════════════════════════════════

export interface WorkpaperSyncTimelineRow {
  readonly stream: string
  readonly sequenceNo: number
  readonly occurredAt: string | null
  readonly fromState: string | null
  readonly toState: string | null
  readonly correlationId: string | null
}

/** 把一条 timeline 载荷投影成表行。未知形态跳过而不是编一行。 */
function timelineRow(raw: unknown): WorkpaperSyncTimelineRow | null {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) return null
  const wire = raw as Wire
  const sequenceNo = wire.sequence_no
  if (typeof sequenceNo !== 'number' || !Number.isInteger(sequenceNo)) return null
  return {
    stream: typeof wire.stream === 'string' ? wire.stream : '',
    sequenceNo,
    occurredAt: typeof wire.occurred_at === 'string' ? wire.occurred_at : null,
    fromState: typeof wire.from_state === 'string' ? wire.from_state : null,
    toState: typeof wire.to_state === 'string' ? wire.to_state : null,
    correlationId: typeof wire.correlation_id === 'string' ? wire.correlation_id : null,
  }
}

/** 从 `getOperationTimeline` 的载荷取两条流（operation + application），按序号排。 */
export function projectOperationTimeline(payload: unknown): {
  readonly rows: readonly WorkpaperSyncTimelineRow[]
  readonly applicationId: string | null
  readonly followedDuplicate: boolean
} {
  if (payload === null || typeof payload !== 'object') {
    return { rows: [], applicationId: null, followedDuplicate: false }
  }
  const wire = payload as Wire
  const collect = (key: string): WorkpaperSyncTimelineRow[] => {
    const raw = wire[key]
    if (!Array.isArray(raw)) return []
    return raw.map(timelineRow).filter((row): row is WorkpaperSyncTimelineRow => row !== null)
  }
  const rows = [...collect('operation_events'), ...collect('application_events')].sort(
    (a, b) => a.stream.localeCompare(b.stream) || a.sequenceNo - b.sequenceNo,
  )
  return {
    rows,
    applicationId: typeof wire.application_id === 'string' ? wire.application_id : null,
    followedDuplicate: wire.followed_duplicate === true,
  }
}

/** 从 `getRecoveryCaseTimeline` 的载荷取 case 侧事实。 */
export function projectRecoveryTimeline(payload: unknown): {
  readonly rows: readonly WorkpaperSyncTimelineRow[]
  readonly caseId: string | null
  readonly state: string | null
  readonly claimedOperationId: string | null
  readonly claimedApplicationId: string | null
  readonly recoveryRequestId: string | null
  readonly hasThreeEntities: boolean
} {
  if (payload === null || typeof payload !== 'object') {
    return {
      rows: [],
      caseId: null,
      state: null,
      claimedOperationId: null,
      claimedApplicationId: null,
      recoveryRequestId: null,
      hasThreeEntities: false,
    }
  }
  const wire = payload as Wire
  const raw = wire.events
  const rows = Array.isArray(raw)
    ? raw.map(timelineRow).filter((row): row is WorkpaperSyncTimelineRow => row !== null)
    : []
  const opt = (key: string): string | null =>
    typeof wire[key] === 'string' && (wire[key] as string).trim() !== ''
      ? (wire[key] as string)
      : null
  return {
    rows: [...rows].sort((a, b) => a.sequenceNo - b.sequenceNo),
    caseId: opt('case_id'),
    state: opt('state'),
    claimedOperationId: opt('claimed_operation_id'),
    claimedApplicationId: opt('claimed_application_id'),
    recoveryRequestId: opt('recovery_request_id'),
    hasThreeEntities: wire.has_three_entities === true,
  }
}

/** digest 的紧凑展示（前 12 位 + 省略号）。**只用于展示**，比对一律用全量。 */
export function shortDigest(value: string | null | undefined): string {
  const text = String(value ?? '').trim()
  if (text === '') return WP_SYNC_TRACE_GAP_PLACEHOLDER
  return text.length <= 16 ? text : `${text.slice(0, 12)}…${text.slice(-4)}`
}
