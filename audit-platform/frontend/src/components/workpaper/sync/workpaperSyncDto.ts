/**
 * 底稿 HTML ↔ OnlyOffice 双向回写的**前端 DTO 与解析器**。
 *
 * spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 31
 * Requirements: 3.1, 3.6, 3.7, 5.8, 11.2, 11.4, 11.5, 11.6, 11.11
 * Properties: P10（幂等 commit 的客户端凭据）/ P11（descriptor 唯一 config 来源）/
 *             P47（descriptor 消费面）
 *
 * ═══ 本模块只做两件事 ═══
 *
 * 1. **把线上 snake_case 载荷解析成 camelCase DTO**，逐项校验域与不变量；
 * 2. **拒绝非法形态并保留可诊断 code** —— 未知状态、非法 shape、claim 前伪造三实体、
 *    download-only 冒充 applied、descriptor 缺项，一律抛
 *    :class:`WorkpaperSyncContractError` 而不是兜底。
 *
 * **不做**的事（做了就是第二套业务逻辑）：
 *
 * * 不发请求（那是 `workpaperSyncApi.ts`）；
 * * 不维护模式状态机（那是 Task 32 的 `useWorkpaperSyncBridge`）；
 * * 不拼 OnlyOffice config —— descriptor 里的 `onlyofficeConfig` 是唯一来源，
 *   本模块既不补字段也不签 URL（Task 25/28 的 signature-TTL 论证）。
 *
 * ═══ 为什么「未知状态」必须抛而不能兜底 ═══
 *
 * AC 4.9 明文「未知状态或无法唯一归组 SHALL fail visible」。把未知 operation state
 * 兜底成 `'error'` 看起来更健壮，实际后果是后端新增一个终态时前端把它显示成失败，
 * 审计师会去点重试 —— 而那条路径可能根本不允许重试。封闭域来自生成的
 * `workpaperSyncContract.generated.ts`（真源 = 后端 Enum），不是手抄。
 */
import {
  WP_SYNC_AUTHORITY_MODELS,
  WP_SYNC_DESCRIPTOR_CONFIRM_KEYS,
  WP_SYNC_DESCRIPTOR_FIELDS,
  WP_SYNC_OPERATION_STATES,
  WP_SYNC_OPERATION_TERMINAL_STATES,
  WP_SYNC_RECOVERY_CASE_STATES,
  WP_SYNC_RECOVERY_REASONS,
  WP_SYNC_REJECTION_STATUS,
  WP_SYNC_ROOM_STATES,
  type WorkpaperSyncAuthorityModel,
  type WorkpaperSyncOperationShape,
  type WorkpaperSyncOperationState,
  type WorkpaperSyncRecoveryCaseState,
  type WorkpaperSyncRecoveryReason,
  type WorkpaperSyncRoomState,
} from './workpaperSyncContract.generated'

// ═══════════════════════════════════════════════════════════════════════════
// 1. 唯一拒绝面
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 契约违约的**唯一**异常类型。
 *
 * 🔴 每一处拒绝都带**互不相同**的 `code`：两个分支共用一个 code 时，先到的那条会把
 * 后到的那条遮成永远不可达（本 spec 的变异运行已经三次抓到这个形态），于是「后一条
 * 判据是否还在起作用」不可判。测试一律断言 `code` 而不是「抛了就算过」。
 */
export class WorkpaperSyncContractError extends Error {
  readonly code: string

  constructor(code: string, message: string) {
    super(message)
    this.name = 'WorkpaperSyncContractError'
    this.code = code
  }
}

function refuse(code: string, message: string): never {
  throw new WorkpaperSyncContractError(code, message)
}

// ═══════════════════════════════════════════════════════════════════════════
// 2. 原子取值
// ═══════════════════════════════════════════════════════════════════════════

type Wire = Record<string, unknown>

function asWire(value: unknown, label: string): Wire {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    refuse(
      'wire_payload_not_object',
      `${label} 的响应体不是对象（实得 ${value === null ? 'null' : typeof value}）`,
    )
  }
  return value as Wire
}

/**
 * 平台 `{code,message,data}` envelope 只在 API 层解一次（`utils/http` 的响应拦截器）。
 *
 * 🔴 本函数**不解包**，只在「载荷仍是 envelope」时 fail visible。第二次解包会让
 * 「拦截器某天不再解包」与「响应本来就长这样」两种情形都静默通过，而两者的正确处理
 * 完全不同。callback 路由被 `ResponseWrapperMiddleware` 刻意排除包装，前端也从不调用
 * 它 —— 所以本模块见到 envelope 只有一种解释：解包层出了问题。
 */
export function assertUnwrappedOnce(payload: unknown, label: string): Wire {
  const wire = asWire(payload, label)
  if (
    typeof wire.code === 'number' &&
    Object.prototype.hasOwnProperty.call(wire, 'message') &&
    Object.prototype.hasOwnProperty.call(wire, 'data')
  ) {
    refuse(
      'envelope_not_unwrapped',
      `${label} 的载荷仍是平台 envelope（code/message/data）—— envelope 只能在 API 层` +
        '解一次，此处再解一次会让「拦截器停止解包」静默通过',
    )
  }
  return wire
}

function requiredString(wire: Wire, key: string, label: string): string {
  const value = wire[key]
  if (typeof value !== 'string' || value.trim() === '') {
    refuse('wire_field_missing', `${label} 缺必填字段 ${key}（实得 ${JSON.stringify(value)}）`)
  }
  return value
}

function requiredInt(wire: Wire, key: string, label: string): number {
  const value = wire[key]
  if (typeof value !== 'number' || !Number.isInteger(value)) {
    refuse('wire_field_missing', `${label} 的 ${key} 不是整数（实得 ${JSON.stringify(value)}）`)
  }
  return value
}

function nullableInt(wire: Wire, key: string, label: string): number | null {
  const value = wire[key]
  if (value === null || value === undefined) return null
  return requiredInt(wire, key, label)
}

/** opaque id：非空字符串且**不是纯数字**（numeric revision 不得当 resource key）。 */
function nullableOpaqueId(wire: Wire, key: string, label: string): string | null {
  const value = wire[key]
  if (value === null || value === undefined) return null
  const text = requiredString(wire, key, label)
  if (/^\d+$/.test(text)) {
    refuse(
      'opaque_id_required',
      `${label} 的 ${key}=${JSON.stringify(text)} 是纯数字 —— numeric revision 只能展示/作乐观锁`,
    )
  }
  return text
}

function requiredOpaqueId(wire: Wire, key: string, label: string): string {
  const value = nullableOpaqueId(wire, key, label)
  if (value === null) {
    refuse('wire_field_missing', `${label} 缺必填 opaque id ${key}`)
  }
  return value
}

function member<T extends string>(
  domain: readonly T[],
  value: unknown,
  code: string,
  label: string,
): T {
  if (typeof value !== 'string' || !(domain as readonly string[]).includes(value)) {
    refuse(
      code,
      `${label} 的取值 ${JSON.stringify(value)} 不在封闭域 [${domain.join(', ')}] 内 —— ` +
        '未知状态必须 fail visible，不得兜底',
    )
  }
  return value as T
}

/** 内容身份 digest：64 位**小写** hex 且非全零（与后端 `is_digest` 逐条对齐）。 */
export function isSyncDigest(value: unknown): boolean {
  if (typeof value !== 'string') return false
  const text = value.trim()
  if (text === '' || text === '0'.repeat(64)) return false
  return /^[0-9a-f]{64}$/.test(text)
}

/** 全零 UUID —— 「我还没拿到」的常见占位值。 */
const NIL_UUID = '00000000-0000-0000-0000-000000000000'

/**
 * opaque immutable UUID：8-4-4-4-12 hex，且**不是全零**。
 *
 * 🔴 全零单独排除与后端 `assert_descriptor_mountable` 同理：`uuid.UUID(int=0)` 是事务前
 * 占位值（Task 15 的 `SyncContext` 就用它），它非 `null` 却毫无意义 —— 只查
 * 「格式对不对」的判据会把一份全是占位 id 的 descriptor 判成可挂载。
 * 纯数字 revision 也必然不满足这个正则。
 */
export function isOpaqueUuid(value: unknown): boolean {
  if (typeof value !== 'string') return false
  const text = value.trim()
  if (text.toLowerCase() === NIL_UUID) return false
  return /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/.test(
    text,
  )
}

// ═══════════════════════════════════════════════════════════════════════════
// 3. HTML → OO：pending mutation / descriptor / confirmation
// ═══════════════════════════════════════════════════════════════════════════

/** `POST .../pending-mutations` 的回执。flush **不推进** revision（AC 3.1）。 */
export interface WorkpaperSyncPendingMutation {
  readonly pendingMutationToken: string
  readonly expectedRevision: number
  readonly payloadSha256: string
  readonly expiresAt: string
  /** 本次请求实际发出的 `Idempotency-Key`（逐项回传给调用方，便于重放同一 key）。 */
  readonly idempotencyKey: string
}

export function parsePendingMutation(
  payload: unknown,
  idempotencyKey: string,
): WorkpaperSyncPendingMutation {
  const wire = assertUnwrappedOnce(payload, 'pending-mutations')
  const digest = wire.payload_sha256
  if (!isSyncDigest(digest)) {
    refuse(
      'payload_digest_invalid',
      `pending mutation 的 payload_sha256=${JSON.stringify(digest)} 非法（须 64 位小写 hex 且非全零）`,
    )
  }
  return {
    pendingMutationToken: requiredString(wire, 'pending_mutation_token', 'pending-mutations'),
    expectedRevision: requiredInt(wire, 'expected_revision', 'pending-mutations'),
    payloadSha256: digest as string,
    expiresAt: requiredString(wire, 'expires_at', 'pending-mutations'),
    idempotencyKey,
  }
}

export interface WorkpaperSyncBundleSlot {
  readonly type: string
  readonly sha256: string
}

/**
 * Excel / Word editor 的**唯一** config 来源（Requirement 3.7 / 11.4 / Property 11）。
 *
 * 🔴 刻意**没有** `documentUrl`：descriptor 是 room 代际的身份快照，签名下载 URL 有
 * 独立短 TTL，两者同寿会让签名长到不安全或 descriptor 提前失效。URL 由服务端在响应时
 * 放进 `onlyofficeConfig.document`，前端只能原样用，既不得伪造也不得再请求一份 config。
 */
export interface WorkpaperSyncEditorLaunchDescriptor {
  readonly operationId: string
  readonly roomId: string
  readonly participantId: string
  readonly docKey: string
  readonly generation: number
  readonly serverAppliedRevision: number
  readonly clientConfirmedBaseRevision: number | null
  readonly contentVersionId: string
  readonly representationId: string
  readonly representationGeneration: number
  readonly artifactSha256: string
  readonly writeFenceEpoch: number
  readonly authorityModel: WorkpaperSyncAuthorityModel
  readonly authorityModelDefinitionSha256: string
  readonly definitionBundleId: string
  readonly definitionBundleSha256: string
  readonly definitionBundleSlots: Readonly<Record<string, WorkpaperSyncBundleSlot>>
  readonly documentType: string
  readonly mode: string
  readonly onlyofficeConfig: Readonly<Record<string, unknown>>
  /** 相同 pending token + Idempotency-Key 的成功重放（AC 3.6 的幂等复用）。 */
  readonly replayed: boolean
}

/** bundle 的三个 typed slot 必须**全在**（Requirement 2.3）。 */
const REQUIRED_BUNDLE_SLOTS = ['template', 'instrumentation', 'contract'] as const

const DESCRIPTOR_UUID_FIELDS = [
  'operation_id',
  'room_id',
  'participant_id',
  'content_version_id',
  'representation_id',
  'definition_bundle_id',
] as const

const DESCRIPTOR_DIGEST_FIELDS = [
  'artifact_sha256',
  'authority_model_definition_sha256',
  'definition_bundle_sha256',
] as const

const DESCRIPTOR_POSITIVE_INT_FIELDS = [
  'generation',
  'representation_generation',
  'server_applied_revision',
  'write_fence_epoch',
] as const

export function parseEditorLaunchDescriptor(
  payload: unknown,
): WorkpaperSyncEditorLaunchDescriptor {
  const wire = assertUnwrappedOnce(payload, 'materialize')

  // 缺项清单来自生成的 `WP_SYNC_DESCRIPTOR_FIELDS`（真源 = 后端
  // `DESCRIPTOR_REQUIRED_FIELDS`）—— 不在这里手抄第二份，否则后端加一项就静默漏检。
  const missing = WP_SYNC_DESCRIPTOR_FIELDS.filter(
    (field) => !Object.prototype.hasOwnProperty.call(wire, field),
  )
  if (missing.length > 0) {
    refuse(
      'descriptor_field_missing',
      `launch descriptor 缺字段 [${missing.join(', ')}] —— 字段不全时不得挂载 DocEditor`,
    )
  }
  for (const field of DESCRIPTOR_UUID_FIELDS) {
    if (!isOpaqueUuid(wire[field])) {
      refuse(
        'descriptor_uuid_invalid',
        `descriptor 的 ${field}=${JSON.stringify(wire[field])} 不是 opaque UUID`,
      )
    }
  }
  for (const field of DESCRIPTOR_DIGEST_FIELDS) {
    if (!isSyncDigest(wire[field])) {
      refuse(
        'descriptor_digest_invalid',
        `descriptor 的 ${field}=${JSON.stringify(wire[field])} 不是合法 digest（64 位小写 hex 且非全零）`,
      )
    }
  }
  for (const field of DESCRIPTOR_POSITIVE_INT_FIELDS) {
    const value = wire[field]
    if (typeof value !== 'number' || !Number.isInteger(value) || value < 1) {
      refuse(
        'descriptor_generation_invalid',
        `descriptor 的 ${field}=${JSON.stringify(value)} 必须是 >= 1 的整数`,
      )
    }
  }

  const rawSlots = wire.definition_bundle_slots
  if (rawSlots === null || typeof rawSlots !== 'object' || Array.isArray(rawSlots)) {
    refuse(
      'descriptor_slot_missing',
      `descriptor 的 definition_bundle_slots 不是映射（实得 ${JSON.stringify(rawSlots)}）`,
    )
  }
  const slots: Record<string, WorkpaperSyncBundleSlot> = {}
  for (const slot of REQUIRED_BUNDLE_SLOTS) {
    const spec = (rawSlots as Wire)[slot]
    if (spec === null || typeof spec !== 'object' || Array.isArray(spec)) {
      refuse(
        'descriptor_slot_missing',
        `descriptor 缺 typed slot ${slot} —— 三个 slot 必须全部出现，可选 child 只能用 ` +
          'typed null marker',
      )
    }
    const slotType = (spec as Wire).type
    if (typeof slotType !== 'string' || slotType.trim() === '') {
      refuse(
        'descriptor_slot_type_missing',
        `descriptor 的 definition_bundle_slots.${slot}.type 为空 —— 禁以缺字段/空串代替 typed null marker`,
      )
    }
    if (!isSyncDigest((spec as Wire).sha256)) {
      refuse(
        'descriptor_slot_digest_invalid',
        `descriptor 的 definition_bundle_slots.${slot}.sha256 非法`,
      )
    }
    slots[slot] = { type: slotType, sha256: (spec as Wire).sha256 as string }
  }

  const config = wire.onlyoffice_config
  if (
    config === null ||
    typeof config !== 'object' ||
    Array.isArray(config) ||
    Object.keys(config as Wire).length === 0
  ) {
    refuse(
      'descriptor_config_empty',
      'descriptor 的 onlyoffice_config 为空 —— 它是编辑器 config 的唯一来源，空 config ' +
        '会逼组件自行再请求一次（Property 11 明令禁止）',
    )
  }

  return {
    operationId: wire.operation_id as string,
    roomId: wire.room_id as string,
    participantId: wire.participant_id as string,
    docKey: requiredString(wire, 'doc_key', 'materialize'),
    generation: wire.generation as number,
    serverAppliedRevision: wire.server_applied_revision as number,
    clientConfirmedBaseRevision: nullableInt(
      wire,
      'client_confirmed_base_revision',
      'materialize',
    ),
    contentVersionId: wire.content_version_id as string,
    representationId: wire.representation_id as string,
    representationGeneration: wire.representation_generation as number,
    artifactSha256: wire.artifact_sha256 as string,
    writeFenceEpoch: wire.write_fence_epoch as number,
    authorityModel: member(
      WP_SYNC_AUTHORITY_MODELS,
      wire.authority_model,
      'unknown_authority_model',
      'descriptor.authority_model',
    ),
    authorityModelDefinitionSha256: wire.authority_model_definition_sha256 as string,
    definitionBundleId: wire.definition_bundle_id as string,
    definitionBundleSha256: wire.definition_bundle_sha256 as string,
    definitionBundleSlots: slots,
    documentType: requiredString(wire, 'document_type', 'materialize'),
    mode: requiredString(wire, 'mode', 'materialize'),
    onlyofficeConfig: config as Record<string, unknown>,
    replayed: wire.replayed === true,
  }
}

/**
 * `onDocumentReady` 之后要逐项回传的 identity（design §API 的十项）。
 *
 * 键集来自生成的 `WP_SYNC_DESCRIPTOR_CONFIRM_KEYS`（真源 =
 * `EditorLaunchDescriptor.confirm_payload()` 的真实调用结果）。少回传一项 ⇒ 服务端逐项
 * 比对永远 409 ⇒ 编辑器永远进不了 `oo_editing`，而任何「字段名长得对」的判据都全绿。
 */
export function buildDescriptorConfirmPayload(
  descriptor: WorkpaperSyncEditorLaunchDescriptor,
): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    participant_id: descriptor.participantId,
    generation: descriptor.generation,
    doc_key: descriptor.docKey,
    representation_id: descriptor.representationId,
    artifact_sha256: descriptor.artifactSha256,
    content_revision: descriptor.serverAppliedRevision,
    write_fence_epoch: descriptor.writeFenceEpoch,
    authority_model_definition_sha256: descriptor.authorityModelDefinitionSha256,
    definition_bundle_id: descriptor.definitionBundleId,
    definition_bundle_sha256: descriptor.definitionBundleSha256,
  }
  const produced = Object.keys(payload).sort()
  const expected = [...WP_SYNC_DESCRIPTOR_CONFIRM_KEYS].sort()
  if (produced.join('|') !== expected.join('|')) {
    refuse(
      'confirm_payload_key_drift',
      `confirm 回传键集 [${produced.join(', ')}] ≠ 服务端要求的 [${expected.join(', ')}]`,
    )
  }
  return payload
}

/** `confirm-descriptor` 的结果。`forcesaveUnlocked` 之前不得 forcesave。 */
export interface WorkpaperSyncDescriptorConfirmation {
  readonly confirmationId: string
  readonly roomId: string
  readonly participantId: string
  readonly generation: number
  readonly representationId: string
  readonly contentVersionId: string
  readonly roomState: WorkpaperSyncRoomState
  readonly replayed: boolean
  readonly forcesaveUnlocked: boolean
}

export function parseDescriptorConfirmation(
  payload: unknown,
): WorkpaperSyncDescriptorConfirmation {
  const wire = assertUnwrappedOnce(payload, 'confirm-descriptor')
  return {
    confirmationId: requiredOpaqueId(wire, 'confirmation_id', 'confirm-descriptor'),
    roomId: requiredOpaqueId(wire, 'room_id', 'confirm-descriptor'),
    participantId: requiredOpaqueId(wire, 'participant_id', 'confirm-descriptor'),
    generation: requiredInt(wire, 'generation', 'confirm-descriptor'),
    representationId: requiredOpaqueId(wire, 'representation_id', 'confirm-descriptor'),
    contentVersionId: requiredOpaqueId(wire, 'content_version_id', 'confirm-descriptor'),
    roomState: member(
      WP_SYNC_ROOM_STATES,
      wire.room_state,
      'unknown_room_state',
      'confirm-descriptor.room_state',
    ),
    replayed: wire.replayed === true,
    forcesaveUnlocked: wire.forcesave_unlocked === true,
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 4. room / participant 身份投影
// ═══════════════════════════════════════════════════════════════════════════

/**
 * room 身份。
 *
 * 🔴 `state` 只在 `confirm-descriptor` 响应里出现，所以它是 `null`-able 而不是必填：
 * materialize 阶段服务端还没把 room 转 active（Property 11：确认前 room 不得 active），
 * 给它编一个 `'opening'` 会让「确认失败仍显示已就绪」这条最贵的假绿重新可达。
 */
export interface WorkpaperSyncRoomIdentity {
  readonly roomId: string
  readonly docKey: string
  readonly generation: number
  readonly writeFenceEpoch: number
  readonly state: WorkpaperSyncRoomState | null
}

/**
 * participant 身份。
 *
 * 🔴 **只有 id**：这 16 个端点没有任何一个返回 participant 的 state/mode，投影一个
 * 「看起来完整」的 `state` 字段等于给 UI 一个永远为占位值的门控 —— 那是 additive 死代码
 * （本 spec 第一类假绿）。生成的 contract 因此也**不投影** `ParticipantState` /
 * `ParticipantMode` 枚举：没有 wire 来源就没有判据可写。真需要时先让后端把它放进响应。
 *
 * descriptor 的 `mode`（`edit`/`view`）是**编辑器** config 的模式，不是 participant 的
 * 授权模式；两者同名不同义，本模块刻意不把它套到 `ParticipantMode` 上。
 */
export interface WorkpaperSyncParticipantIdentity {
  readonly participantId: string
}

export function roomIdentityOfDescriptor(
  descriptor: WorkpaperSyncEditorLaunchDescriptor,
): WorkpaperSyncRoomIdentity {
  return {
    roomId: descriptor.roomId,
    docKey: descriptor.docKey,
    generation: descriptor.generation,
    writeFenceEpoch: descriptor.writeFenceEpoch,
    state: null,
  }
}

export function participantIdentityOfDescriptor(
  descriptor: WorkpaperSyncEditorLaunchDescriptor,
): WorkpaperSyncParticipantIdentity {
  return { participantId: descriptor.participantId }
}

// ═══════════════════════════════════════════════════════════════════════════
// 5. OO → HTML：forcesave / operation
// ═══════════════════════════════════════════════════════════════════════════

/** `POST .../forcesave` 的 202。`operationId` 只是 nullable-application shell。 */
export interface WorkpaperSyncForcesaveAccepted {
  readonly forcesaveRequestId: string
  readonly operationId: string
  readonly requestSequence: number
  readonly state: 'accepted'
  readonly pollAfterMs: number
  readonly replayed: boolean
  /** 出站失败时的 error_code；`null` 才代表 Command Service 已受理。 */
  readonly dispatchError: string | null
}

export function parseForcesaveAccepted(payload: unknown): WorkpaperSyncForcesaveAccepted {
  const wire = assertUnwrappedOnce(payload, 'forcesave')
  const state = wire.state
  if (state !== 'accepted') {
    refuse(
      'forcesave_state_unexpected',
      `forcesave 202 的 state=${JSON.stringify(state)} —— 只允许 'accepted'；` +
        'Command Service HTTP 200 都不等于保存完成',
    )
  }
  const dispatchError = wire.dispatch_error
  if (dispatchError !== null && dispatchError !== undefined && typeof dispatchError !== 'string') {
    refuse(
      'forcesave_dispatch_error_invalid',
      `forcesave 的 dispatch_error=${JSON.stringify(dispatchError)} 既不是 null 也不是 error_code 字符串`,
    )
  }
  return {
    forcesaveRequestId: requiredOpaqueId(wire, 'forcesave_request_id', 'forcesave'),
    operationId: requiredOpaqueId(wire, 'operation_id', 'forcesave'),
    requestSequence: requiredInt(wire, 'request_sequence', 'forcesave'),
    state: 'accepted',
    pollAfterMs: requiredInt(wire, 'poll_after_ms', 'forcesave'),
    replayed: wire.replayed === true,
    dispatchError: typeof dispatchError === 'string' ? dispatchError : null,
  }
}

/**
 * operation 快照。
 *
 * 三个 link 全部 nullable，且三态互斥穷尽（与后端 `classify_operation_shape` 同表）：
 *
 * | shape           | applicationId | duplicateOfOperationId | state        |
 * |-----------------|---------------|------------------------|--------------|
 * | pre_correlation | null          | null                   | ≠ duplicate  |
 * | primary         | 非空          | null                   | ≠ duplicate  |
 * | duplicate       | null          | 非空                   | = duplicate  |
 *
 * `canonicalOperationId` 始终有值（duplicate 时指向 direct primary），
 * `requestedOperationId` 保留调用方给的那个 —— 两者都要显示，否则 UI 无法说明
 * 「你发起的那次被折叠到了哪一次」。
 */
export interface WorkpaperSyncOperationSnapshot {
  readonly requestedOperationId: string
  readonly canonicalOperationId: string
  readonly followedDuplicate: boolean
  readonly state: WorkpaperSyncOperationState
  readonly shape: WorkpaperSyncOperationShape
  readonly applicationId: string | null
  readonly duplicateOfOperationId: string | null
  readonly errorCode: string | null
  readonly errorStage: string | null
  readonly acceptedAt: string | null
  readonly applicationBoundAt: string | null
  readonly operationFinishedAt: string | null
  /** 以下五项只在 primary 绑定 application 之后才存在（AC 5.5）。 */
  readonly resultRevision: number | null
  readonly conflictCount: number | null
  readonly logicalResultCode: string | null
  readonly definitionBundleId: string | null
  readonly definitionBundleSha256: string | null
  readonly authorityModelDefinitionSha256: string | null
  readonly durableAt: string | null
  readonly finishedAt: string | null
  readonly terminal: boolean
}

/** 与后端 `classify_operation_shape` 逐条对齐；非法组合抛而不是「猜一个」。 */
export function classifyOperationShape(input: {
  applicationId: string | null
  duplicateOfOperationId: string | null
  state: WorkpaperSyncOperationState
}): WorkpaperSyncOperationShape {
  const { applicationId, duplicateOfOperationId, state } = input
  if (applicationId !== null && duplicateOfOperationId !== null) {
    refuse(
      'operation_shape_ambiguous',
      'operation 同时绑定 application 与 duplicate 指针 —— primary/duplicate 必须互斥',
    )
  }
  if (duplicateOfOperationId !== null) {
    if (state !== 'duplicate') {
      refuse(
        'duplicate_state_mismatch',
        `duplicate 必为 terminal state='duplicate'，实得 ${state}`,
      )
    }
    return 'duplicate'
  }
  if (state === 'duplicate') {
    refuse(
      'stranded_duplicate_shell',
      "state='duplicate' 但缺 duplicate_of_operation_id（stranded shell）",
    )
  }
  return applicationId !== null ? 'primary' : 'pre_correlation'
}

export function parseOperationSnapshot(payload: unknown): WorkpaperSyncOperationSnapshot {
  const wire = assertUnwrappedOnce(payload, 'operations')
  const state = member(
    WP_SYNC_OPERATION_STATES,
    wire.state,
    'unknown_operation_state',
    'operation.state',
  )
  const applicationId = nullableOpaqueId(wire, 'application_id', 'operations')
  const duplicateOfOperationId = nullableOpaqueId(
    wire,
    'duplicate_of_operation_id',
    'operations',
  )
  const shape = classifyOperationShape({ applicationId, duplicateOfOperationId, state })
  const requestedOperationId = requiredOpaqueId(wire, 'requested_operation_id', 'operations')
  const canonicalOperationId = requiredOpaqueId(wire, 'canonical_operation_id', 'operations')

  // duplicate 必须**直指**同 scope 的 canonical primary（禁自指/链/环）。
  if (shape === 'duplicate') {
    if (duplicateOfOperationId !== canonicalOperationId) {
      refuse(
        'duplicate_not_direct_primary',
        `duplicate 的 duplicate_of_operation_id=${duplicateOfOperationId} 不等于 ` +
          `canonical_operation_id=${canonicalOperationId} —— duplicate 只能直指 canonical primary`,
      )
    }
    if (requestedOperationId === canonicalOperationId) {
      refuse(
        'duplicate_self_reference',
        'duplicate 的 requested id 与 canonical id 相同 —— 禁 self-reference',
      )
    }
  }
  if (shape !== 'duplicate' && requestedOperationId !== canonicalOperationId) {
    refuse(
      'non_duplicate_canonicalized',
      `shape=${shape} 却把 requested ${requestedOperationId} canonicalize 成 ` +
        `${canonicalOperationId} —— 只有 duplicate 才允许跟随 primary`,
    )
  }

  // `error_code` 只保留原值供 UI 展示，**不**在此映射状态码：后端的 error_code 面比
  // materialize 拒绝表大（merge / extract / callback 各有自己的码），按那张表兜底会把
  // 未登记的码显示成 500。真正不可接受的是「未知 **状态** 被兜底」，由上面的
  // `member()` 拦住；失败分型由 `classifySyncFailure()` 单独负责并显式标 `unregistered`。
  const errorCode = wire.error_code

  return {
    requestedOperationId,
    canonicalOperationId,
    followedDuplicate: wire.followed_duplicate === true,
    state,
    shape,
    applicationId,
    duplicateOfOperationId,
    errorCode: typeof errorCode === 'string' && errorCode !== '' ? errorCode : null,
    errorStage: typeof wire.error_stage === 'string' ? wire.error_stage : null,
    acceptedAt: typeof wire.accepted_at === 'string' ? wire.accepted_at : null,
    applicationBoundAt:
      typeof wire.application_bound_at === 'string' ? wire.application_bound_at : null,
    operationFinishedAt:
      typeof wire.operation_finished_at === 'string' ? wire.operation_finished_at : null,
    resultRevision: nullableInt(wire, 'result_revision', 'operations'),
    conflictCount: nullableInt(wire, 'conflict_count', 'operations'),
    logicalResultCode:
      typeof wire.logical_result_code === 'string' ? wire.logical_result_code : null,
    definitionBundleId: nullableOpaqueId(wire, 'definition_bundle_id', 'operations'),
    definitionBundleSha256:
      typeof wire.definition_bundle_sha256 === 'string' ? wire.definition_bundle_sha256 : null,
    authorityModelDefinitionSha256:
      typeof wire.authority_model_definition_sha256 === 'string'
        ? wire.authority_model_definition_sha256
        : null,
    durableAt: typeof wire.durable_at === 'string' ? wire.durable_at : null,
    finishedAt: typeof wire.finished_at === 'string' ? wire.finished_at : null,
    terminal: (WP_SYNC_OPERATION_TERMINAL_STATES as readonly string[]).includes(state),
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 6. recovery
// ═══════════════════════════════════════════════════════════════════════════

export interface WorkpaperSyncPriorConfirmationCandidate {
  readonly confirmationId: string
  readonly participantId: string
  readonly contentVersionId: string
  readonly confirmedAt: string | null
}

/**
 * recovery case 摘要。
 *
 * 三实体（`forcesaveRequestId / applicationId / operationId`）的可空性是 AC 5.8 的
 * **可观测事实**，不是「可能没填」：claim 之前必须全空，claim 成功后必须全满，
 * download-only / quarantined / expired 必须全空。任一违反即 fail visible ——
 * 一个伪造的 operationId 会让 UI 显示普通「重试」，而 AC 5.8 明令 nullable-operation
 * 的 case 不得进入普通 operation retry。
 */
export interface WorkpaperSyncRecoveryCase {
  readonly caseId: string
  readonly reason: WorkpaperSyncRecoveryReason
  readonly state: WorkpaperSyncRecoveryCaseState
  readonly operationId: string | null
  readonly applicationId: string | null
  readonly forcesaveRequestId: string | null
  readonly candidatePriorConfirmations: readonly WorkpaperSyncPriorConfirmationCandidate[]
  readonly actions: { readonly claim: boolean; readonly downloadOnly: boolean }
}

/** claim 成功之前三实体必须全空的 case 状态。 */
const RECOVERY_STATES_WITHOUT_ENTITIES = [
  'unclaimed',
  'claiming',
  'download_only',
  'quarantined',
  'expired',
] as const

/** claim 成功后三实体必须全满的 case 状态。 */
const RECOVERY_STATES_WITH_ENTITIES = ['application_created'] as const

export function parseRecoveryCase(payload: unknown): WorkpaperSyncRecoveryCase {
  const wire = assertUnwrappedOnce(payload, 'recovery-cases')
  const state = member(
    WP_SYNC_RECOVERY_CASE_STATES,
    wire.state,
    'unknown_recovery_case_state',
    'recovery-case.state',
  )
  const reason = member(
    WP_SYNC_RECOVERY_REASONS,
    wire.reason,
    'unknown_recovery_reason',
    'recovery-case.reason',
  )
  const operationId = nullableOpaqueId(wire, 'operation_id', 'recovery-cases')
  const applicationId = nullableOpaqueId(wire, 'application_id', 'recovery-cases')
  const forcesaveRequestId = nullableOpaqueId(wire, 'forcesave_request_id', 'recovery-cases')
  const entities = { operationId, applicationId, forcesaveRequestId }
  const present = Object.entries(entities)
    .filter(([, value]) => value !== null)
    .map(([key]) => key)

  if ((RECOVERY_STATES_WITHOUT_ENTITIES as readonly string[]).includes(state)) {
    if (present.length > 0) {
      refuse(
        'recovery_case_premature_entities',
        `recovery case state=${state} 却带 [${present.join(', ')}] —— claim 成功前 ` +
          'request/application/operation 三者必须全空，download-only 终态同样全空',
      )
    }
  } else if ((RECOVERY_STATES_WITH_ENTITIES as readonly string[]).includes(state)) {
    if (present.length !== 3) {
      refuse(
        'recovery_case_incomplete_entities',
        `recovery case state=${state} 只带 [${present.join(', ')}] —— claim 成功后 ` +
          'request/application/operation 必须同时具备',
      )
    }
  } else {
    refuse(
      'recovery_case_state_unclassified',
      `recovery case state=${state} 未登记三实体期望 —— 新增状态必须显式裁决，不得默认放行`,
    )
  }

  const rawCandidates = wire.candidate_prior_confirmations
  if (!Array.isArray(rawCandidates)) {
    refuse(
      'recovery_candidates_missing',
      `recovery case 的 candidate_prior_confirmations 不是数组（实得 ${JSON.stringify(rawCandidates)}）`,
    )
  }
  const actions = wire.actions
  if (actions === null || typeof actions !== 'object' || Array.isArray(actions)) {
    refuse(
      'recovery_actions_missing',
      'recovery case 缺 actions —— 能力布尔缺失时 UI 会同时显示两个按钮',
    )
  }

  return {
    caseId: requiredOpaqueId(wire, 'case_id', 'recovery-cases'),
    reason,
    state,
    operationId,
    applicationId,
    forcesaveRequestId,
    candidatePriorConfirmations: (rawCandidates as Wire[]).map((candidate) => ({
      confirmationId: requiredOpaqueId(candidate, 'confirmation_id', 'recovery-candidate'),
      participantId: requiredOpaqueId(candidate, 'participant_id', 'recovery-candidate'),
      contentVersionId: requiredOpaqueId(candidate, 'content_version_id', 'recovery-candidate'),
      confirmedAt: typeof candidate.confirmed_at === 'string' ? candidate.confirmed_at : null,
    })),
    actions: {
      claim: (actions as Wire).claim === true,
      downloadOnly: (actions as Wire).download_only === true,
    },
  }
}

export interface WorkpaperSyncRecoveryCaseList {
  readonly roomId: string
  readonly generation: number
  readonly cases: readonly WorkpaperSyncRecoveryCase[]
}

export function parseRecoveryCaseList(payload: unknown): WorkpaperSyncRecoveryCaseList {
  const wire = assertUnwrappedOnce(payload, 'recovery-cases')
  const cases = wire.cases
  if (!Array.isArray(cases)) {
    refuse(
      'recovery_list_missing_cases',
      `recovery list 的 cases 不是数组（实得 ${JSON.stringify(cases)}）`,
    )
  }
  return {
    roomId: requiredOpaqueId(wire, 'room_id', 'recovery-cases'),
    generation: requiredInt(wire, 'generation', 'recovery-cases'),
    cases: (cases as unknown[]).map(parseRecoveryCase),
  }
}

/**
 * claim 成功的结果 —— **唯一**可以同时带 request/application/operation 的响应。
 *
 * `applicationId` 在协议上必须非空（AC 5.8：claim 在同一事务内创建**或命中**一个
 * application；`assert_recovery_claim_shape` 在 commit 前就拒绝 `application_id IS NULL`）。
 * 服务端把它投影成 nullable 只是因为 `outcome.application` 的类型是 Optional，
 * 前端见到 null 必须 fail visible 而不是显示「已认领」。
 */
export interface WorkpaperSyncRecoveryClaim {
  readonly caseId: string
  readonly forcesaveRequestId: string
  readonly operationId: string
  readonly applicationId: string
  readonly state: WorkpaperSyncRecoveryCaseState
}

export function parseRecoveryClaim(payload: unknown): WorkpaperSyncRecoveryClaim {
  const wire = assertUnwrappedOnce(payload, 'recovery-claim')
  const applicationId = nullableOpaqueId(wire, 'application_id', 'recovery-claim')
  if (applicationId === null) {
    refuse(
      'recovery_claim_without_application',
      'claim 成功响应缺 application_id —— claim 必须在同一事务内创建/命中 application，' +
        '缺它意味着 shell 停在 pre-correlation',
    )
  }
  return {
    caseId: requiredOpaqueId(wire, 'case_id', 'recovery-claim'),
    forcesaveRequestId: requiredOpaqueId(wire, 'forcesave_request_id', 'recovery-claim'),
    operationId: requiredOpaqueId(wire, 'operation_id', 'recovery-claim'),
    applicationId,
    state: member(
      WP_SYNC_RECOVERY_CASE_STATES,
      wire.state,
      'unknown_recovery_case_state',
      'recovery-claim.state',
    ),
  }
}

/**
 * download-only 的终结回执。**三实体必须全空**，且不得被读成「回写完成」。
 *
 * 所以本 DTO 刻意没有任何 revision / applied 字段：只要类型里存在一个
 * `resultRevision`，UI 就有可能把它显示成结构化回写结果。
 */
export interface WorkpaperSyncRecoveryDownloadOnly {
  readonly caseId: string
  readonly state: WorkpaperSyncRecoveryCaseState
  readonly downloadClaim: string
  readonly expiresInSeconds: number
}

/** download-only 响应里出现任一项即视为伪造 applied。 */
const DOWNLOAD_ONLY_FORBIDDEN_KEYS = [
  'forcesave_request_id',
  'application_id',
  'operation_id',
  'result_revision',
  'applied',
] as const

export function parseRecoveryDownloadOnly(
  payload: unknown,
): WorkpaperSyncRecoveryDownloadOnly {
  const wire = assertUnwrappedOnce(payload, 'download-only')
  const leaked = DOWNLOAD_ONLY_FORBIDDEN_KEYS.filter(
    (key) => Object.prototype.hasOwnProperty.call(wire, key) && wire[key] !== null,
  )
  if (leaked.length > 0) {
    refuse(
      'download_only_fabricated_entities',
      `download-only 响应带 [${leaked.join(', ')}] —— 它永不创建 request/application/operation，` +
        '也不得显示「回写完成」',
    )
  }
  return {
    caseId: requiredOpaqueId(wire, 'case_id', 'download-only'),
    state: member(
      WP_SYNC_RECOVERY_CASE_STATES,
      wire.state,
      'unknown_recovery_case_state',
      'download-only.state',
    ),
    downloadClaim: requiredString(wire, 'download_claim', 'download-only'),
    expiresInSeconds: requiredInt(wire, 'expires_in_seconds', 'download-only'),
  }
}

export interface WorkpaperSyncRecoveryArtifact {
  readonly caseId: string
  readonly artifactId: string
  readonly artifactSha256: string
  readonly documentType: string
  readonly sizeBytes: number
  readonly relativePath: string
}

export function parseRecoveryArtifact(payload: unknown): WorkpaperSyncRecoveryArtifact {
  const wire = assertUnwrappedOnce(payload, 'recovery-download')
  if (!isSyncDigest(wire.artifact_sha256)) {
    refuse(
      'artifact_digest_invalid',
      `recovery artifact 的 artifact_sha256=${JSON.stringify(wire.artifact_sha256)} 非法`,
    )
  }
  return {
    caseId: requiredOpaqueId(wire, 'case_id', 'recovery-download'),
    artifactId: requiredOpaqueId(wire, 'artifact_id', 'recovery-download'),
    artifactSha256: wire.artifact_sha256 as string,
    documentType: requiredString(wire, 'document_type', 'recovery-download'),
    sizeBytes: requiredInt(wire, 'size_bytes', 'recovery-download'),
    relativePath: requiredString(wire, 'relative_path', 'recovery-download'),
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 7. 失败分型
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 一次同步失败对**可执行动作**的裁决。
 *
 * 三个布尔各自对应一条明文禁令（Task 31 bullet 4）：stale descriptor / recovery
 * identity 的 409 不得转成 editing、不得转成 retryable operation、不得可 forcesave。
 * 把它们做成三个独立布尔而不是一个 `fatal`，是因为三者会被三个不同的消费方读：
 * 编辑器门控、重试按钮、forcesave 按钮。压成一个会让「重试按钮消失但 forcesave 还在」
 * 这类接线错误看不出来。
 */
export interface WorkpaperSyncFailureVerdict {
  readonly httpStatus: number | null
  readonly errorCode: string
  readonly canEnterEditing: boolean
  readonly retryableOperation: boolean
  readonly canForcesave: boolean
  /** 未在服务端拒绝表里登记的 error_code —— 必须显式可见，不得兜底成普通失败。 */
  readonly unregistered: boolean
}

/** 陈旧 descriptor / substrate identity 的两个 409 error_code。 */
export const WP_SYNC_STALE_IDENTITY_CODES = [
  'launch_descriptor_stale_identity',
  'launch_descriptor_substrate_stale',
] as const

export function classifySyncFailure(input: {
  httpStatus?: number | null
  errorCode?: unknown
}): WorkpaperSyncFailureVerdict {
  const errorCode = typeof input.errorCode === 'string' ? input.errorCode.trim() : ''
  if (errorCode === '') {
    refuse(
      'failure_error_code_missing',
      '同步失败缺 error_code —— 无码失败无法分型，禁止按「通用错误」处理',
    )
  }
  const registered = Object.prototype.hasOwnProperty.call(WP_SYNC_REJECTION_STATUS, errorCode)
  const mapped = registered
    ? (WP_SYNC_REJECTION_STATUS as Record<string, number>)[errorCode]
    : null
  const httpStatus =
    typeof input.httpStatus === 'number' && Number.isInteger(input.httpStatus)
      ? input.httpStatus
      : mapped
  const stale = (WP_SYNC_STALE_IDENTITY_CODES as readonly string[]).includes(errorCode)
  if (stale) {
    return {
      httpStatus,
      errorCode,
      canEnterEditing: false,
      retryableOperation: false,
      canForcesave: false,
      unregistered: false,
    }
  }
  return {
    httpStatus,
    errorCode,
    canEnterEditing: false,
    retryableOperation: httpStatus === 500 || httpStatus === 503,
    canForcesave: false,
    unregistered: !registered,
  }
}
