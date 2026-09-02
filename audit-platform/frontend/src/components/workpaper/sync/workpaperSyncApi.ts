/**
 * 底稿 HTML ↔ OnlyOffice 双向回写的**前端 API 层**（唯一 HTTP 调用面）。
 *
 * spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 31
 * Requirements: 3.1, 3.6, 3.7, 5.8, 11.2, 11.4, 11.5, 11.6, 11.11
 * Properties: P10 / P11 / P47（前端侧）
 *
 * ═══ 三条硬约束 ═══
 *
 * 1. **路径只从生成的 `WP_SYNC_ROUTES` 取**。真源是 Task 28 的 router；手写字面量
 *    的漂移形态是「该端点前端永远打不到」，而任何「函数存在」的判据都全绿。
 * 2. **`entry_id` 不 percent-encode 其中的 `/`**。186 条 entry_id 全部含 `/`（最深四段），
 *    路由用 Starlette `:path` 转换器接收。`encodeURIComponent` 会把 `/` 变成 `%2F`，
 *    Starlette 解出的 `entry_id` 不再等于原值 —— Task 28 的变异 B01 已证明默认转换器
 *    下**每一个**端点恒 404（还是 Starlette 自己的 404，连 guard 都进不去）。
 * 3. **平台 envelope 只解一次**，解包点是 `utils/http` 的响应拦截器。本模块不再解，
 *    只在「载荷仍是 envelope」时 fail visible（见 `assertUnwrappedOnce`）。
 *
 * ═══ 每个 method 都显式接收 project/wp/entry ═══
 *
 * :interface:`WorkpaperSyncEntryScope` 是**首个必填参数**，没有默认值、不从 store 反查。
 * design §API 明文「project/wp/entry 都是显式 route scope，不得从 room/operation/recovery
 * 业务 row 反查后才授权」—— 让客户端可以省掉其中任一段，等于把授权对象的选择权交给
 * 调用点。
 *
 * ═══ 刻意**没有**的东西 ═══
 *
 * * 没有 `getConfig()` / `fetchOnlyOfficeConfig()` —— descriptor 是唯一 config 来源
 *   （Property 11）。组件再请求一份 config 就是 Requirement 11.4 明令禁止的第二份解释。
 * * 没有 callback 调用面 —— `onlyoffice-callback` 是 DocServer 的服务凭证路由，
 *   同时被 `ResponseWrapperMiddleware` 排除包装；前端一旦拼它，解包层就会错一层。
 * * 没有 `document.url` 的签名逻辑 —— URL 由服务端在响应时放进 `onlyoffice_config`。
 */
import http from '@/utils/http'

import {
  WP_SYNC_ROUTES,
  WP_SYNC_USER_PREFIX_TEMPLATE,
  type WorkpaperSyncRouteSpec,
} from './workpaperSyncContract.generated'
import {
  WorkpaperSyncContractError,
  isOpaqueUuid,
  parseDescriptorConfirmation,
  parseEditorLaunchDescriptor,
  parseForcesaveAccepted,
  parseOperationSnapshot,
  parsePendingMutation,
  parseRecoveryArtifact,
  parseRecoveryCaseList,
  parseRecoveryClaim,
  parseRecoveryDownloadOnly,
  assertUnwrappedOnce,
  type WorkpaperSyncDescriptorConfirmation,
  type WorkpaperSyncEditorLaunchDescriptor,
  type WorkpaperSyncForcesaveAccepted,
  type WorkpaperSyncOperationSnapshot,
  type WorkpaperSyncPendingMutation,
  type WorkpaperSyncRecoveryArtifact,
  type WorkpaperSyncRecoveryCaseList,
  type WorkpaperSyncRecoveryClaim,
  type WorkpaperSyncRecoveryDownloadOnly,
} from './workpaperSyncDto'

// ═══════════════════════════════════════════════════════════════════════════
// 1. 显式 scope 与路径拼接
// ═══════════════════════════════════════════════════════════════════════════

/** 每个 client method 的**首个必填参数**。三段缺一即拒绝。 */
export interface WorkpaperSyncEntryScope {
  readonly projectId: string
  readonly wpId: string
  /** 多段 entry id（如 `xlsx/d4/analysis/d4-tab-customer-price`），保留其中的 `/`。 */
  readonly entryId: string
}

const ROUTE_BY_ENDPOINT: Readonly<Record<string, WorkpaperSyncRouteSpec>> =
  Object.freeze(
    Object.fromEntries(WP_SYNC_ROUTES.map((route) => [route.endpoint, route])),
  ) as Readonly<Record<string, WorkpaperSyncRouteSpec>>

function refuse(code: string, message: string): never {
  throw new WorkpaperSyncContractError(code, message)
}

/**
 * `project_id` / `wp_id` 等**单段** opaque id 的编码。
 *
 * 单段 id 里出现 `/` 只可能是拼错或注入，所以这里用 `encodeURIComponent`；
 * 与 `entry_id` 的**不编码**规则刻意分成两个函数，避免哪天有人「统一一下」。
 */
function segment(value: string, label: string): string {
  const text = String(value ?? '').trim()
  if (text === '') {
    refuse('scope_segment_missing', `URL 段 ${label} 为空 —— 显式 scope 不得缺段`)
  }
  return encodeURIComponent(text)
}

/**
 * 多段 `entry_id` 的编码：**逐段** encode 再用未编码的 `/` 连接。
 *
 * 逐段 encode 保留了对段内特殊字符的转义，同时让分隔符 `/` 原样进入 URL ——
 * 这正是 `:path` 转换器需要的形态。
 */
export function encodeEntryId(entryId: string): string {
  const text = String(entryId ?? '').trim()
  if (text === '') {
    refuse('scope_segment_missing', 'entry_id 为空 —— 显式 scope 不得缺段')
  }
  if (text.startsWith('/') || text.endsWith('/') || text.includes('//')) {
    refuse(
      'entry_id_malformed',
      `entry_id=${JSON.stringify(text)} 含空段 —— 会让路由解出的 entry_id 不等于原值`,
    )
  }
  return text
    .split('/')
    .map((part) => encodeURIComponent(part))
    .join('/')
}

/** 显式 scope 前缀。模板来自生成物，本函数只做替换。 */
export function buildSyncEntryPrefix(scope: WorkpaperSyncEntryScope): string {
  return WP_SYNC_USER_PREFIX_TEMPLATE.replace(
    '{project_id}',
    segment(scope.projectId, 'project_id'),
  )
    .replace('{wp_id}', segment(scope.wpId, 'wp_id'))
    .replace('{entry_id}', encodeEntryId(scope.entryId))
}

/**
 * 按 endpoint 名拼完整 URL。
 *
 * `params` 填的是 suffix 模板里的 `{room_id}` / `{operation_id}` / `{case_id}` /
 * `{version_id}`。缺任一占位符即拒绝 —— 留一个未替换的 `{room_id}` 在 URL 里会得到
 * 统一 404，而「函数被调用了」的判据全绿。
 */
export function buildSyncEndpointUrl(
  endpoint: string,
  scope: WorkpaperSyncEntryScope,
  params: Readonly<Record<string, string>> = {},
): string {
  const route = ROUTE_BY_ENDPOINT[endpoint]
  if (!route) {
    refuse(
      'endpoint_not_in_contract',
      `endpoint ${endpoint} 不在生成的路由表内 —— 路径只能取自 WP_SYNC_ROUTES`,
    )
  }
  let suffix: string = route.suffix
  for (const [key, value] of Object.entries(params)) {
    const placeholder = `{${key}}`
    if (!suffix.includes(placeholder)) {
      refuse(
        'route_param_unexpected',
        `endpoint ${endpoint} 的路径 ${route.suffix} 里没有占位符 ${placeholder}`,
      )
    }
    suffix = suffix.replace(placeholder, segment(value, key))
  }
  const unresolved = suffix.match(/\{[a-z_]+\}/g)
  if (unresolved) {
    refuse(
      'route_param_missing',
      `endpoint ${endpoint} 的路径仍有未替换占位符 ${unresolved.join(', ')}`,
    )
  }
  return buildSyncEntryPrefix(scope) + suffix
}

// ═══════════════════════════════════════════════════════════════════════════
// 2. 唯一请求面
// ═══════════════════════════════════════════════════════════════════════════

/**
 * `Idempotency-Key` 的生成。调用方也可自带（重放同一 key 是协议要求的能力）。
 *
 * 🔴 服务端把这七个端点的 header 声明为**必填**（Task 28 已证明改成可选时零测试失败，
 * 而后果是复合幂等键 `(room, generation, participant, kind, key)` 的最后一项恒为空串，
 * 同一 participant 的任意两次 forcesave 折叠成一次）。所以客户端一律带，且由
 * `request()` 在**发出前**按生成的 `idempotencyKey === 'required'` 强制检查。
 */
export function newIdempotencyKey(): string {
  const cryptoRef = globalThis.crypto as { randomUUID?: () => string } | undefined
  if (cryptoRef && typeof cryptoRef.randomUUID === 'function') {
    return cryptoRef.randomUUID()
  }
  return `wp-sync-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`
}

interface RequestOptions {
  readonly endpoint: string
  readonly scope: WorkpaperSyncEntryScope
  readonly params?: Readonly<Record<string, string>>
  readonly query?: Readonly<Record<string, string | number>>
  readonly body?: unknown
  readonly idempotencyKey?: string
}

async function request(options: RequestOptions): Promise<Record<string, unknown>> {
  const route = ROUTE_BY_ENDPOINT[options.endpoint]
  if (!route) {
    refuse(
      'endpoint_not_in_contract',
      `endpoint ${options.endpoint} 不在生成的路由表内`,
    )
  }
  const url = buildSyncEndpointUrl(options.endpoint, options.scope, options.params)

  const headers: Record<string, string> = {}
  if (route.idempotencyKey === 'required') {
    const key = (options.idempotencyKey ?? '').trim()
    if (key === '') {
      // 生成表说这个端点服务端强制要 key，而调用点没给 ⇒ 在**发出前**拒绝。
      // 交给服务端 422 也能挡住，但那时错误已经和「网络问题」混在一起了。
      refuse(
        'idempotency_key_required',
        `endpoint ${options.endpoint} 服务端强制要求 Idempotency-Key，调用点未提供`,
      )
    }
    headers['Idempotency-Key'] = key
  }

  const config: Record<string, unknown> = { headers }
  if (options.query) {
    config.params = { ...options.query }
  }

  // envelope 的解包发生在 `utils/http` 的响应拦截器（唯一一次）；此处只取 `data`。
  const response =
    route.method === 'GET'
      ? await http.get(url, config)
      : await http.post(url, options.body ?? {}, config)
  return assertUnwrappedOnce(response?.data, options.endpoint)
}

// ═══════════════════════════════════════════════════════════════════════════
// 3. HTML → OO
// ═══════════════════════════════════════════════════════════════════════════

export interface CreatePendingMutationInput {
  readonly sheetKey: string
  readonly expectedRevision: number
  readonly projection: unknown
  readonly clientEditEpoch?: number
  readonly idempotencyKey?: string
}

/** `flushHtml()` 的落点。**不推进** revision（AC 3.1）。 */
export async function createPendingMutation(
  scope: WorkpaperSyncEntryScope,
  input: CreatePendingMutationInput,
): Promise<WorkpaperSyncPendingMutation> {
  const key = input.idempotencyKey ?? newIdempotencyKey()
  const payload = await request({
    endpoint: 'create_pending_mutation',
    scope,
    idempotencyKey: key,
    body: {
      // route 已显式给出 entry；payload 保留它时必须**逐字相等**（design §API）。
      entry_id: scope.entryId,
      sheet_key: input.sheetKey,
      expected_revision: input.expectedRevision,
      projection: input.projection,
      client_edit_epoch: input.clientEditEpoch ?? 0,
    },
  })
  return parsePendingMutation(payload, key)
}

export interface MaterializeInput {
  readonly sheetKey: string
  readonly expectedRevision: number
  readonly pendingMutationToken: string
  readonly projection: unknown
  readonly clientEditEpoch?: number
  readonly idempotencyKey?: string
}

/** 唯一 `EditorLaunchDescriptor`（Property 11）。成功前不得挂载 DocEditor。 */
export async function materialize(
  scope: WorkpaperSyncEntryScope,
  input: MaterializeInput,
): Promise<WorkpaperSyncEditorLaunchDescriptor> {
  const token = String(input.pendingMutationToken ?? '').trim()
  if (token === '') {
    refuse(
      'pending_mutation_token_required',
      'materialize 缺 pending_mutation_token —— flush 未成功时不得 materialize（AC 3.2）',
    )
  }
  const payload = await request({
    endpoint: 'materialize',
    scope,
    idempotencyKey: input.idempotencyKey ?? newIdempotencyKey(),
    body: {
      entry_id: scope.entryId,
      sheet_key: input.sheetKey,
      expected_revision: input.expectedRevision,
      pending_mutation_token: token,
      projection: input.projection,
      client_edit_epoch: input.clientEditEpoch ?? 0,
    },
  })
  return parseEditorLaunchDescriptor(payload)
}

/**
 * `onDocumentReady` 之后的幂等确认。逐项回传 descriptor identity。
 *
 * 🔴 回传体由 `buildDescriptorConfirmPayload(descriptor)` 从**同一个 descriptor** 构造，
 * 不接受调用点自己拼：少一项或多一项都会让服务端逐项比对永远 409，而编辑器会停在
 * 「已挂载但不能保存」——那正是 Property 11 后半最贵的失败形态。
 */
export async function confirmDescriptor(
  scope: WorkpaperSyncEntryScope,
  input: {
    readonly descriptor: WorkpaperSyncEditorLaunchDescriptor
    readonly confirmPayload: Readonly<Record<string, unknown>>
    readonly idempotencyKey?: string
  },
): Promise<WorkpaperSyncDescriptorConfirmation> {
  const payload = await request({
    endpoint: 'confirm_descriptor',
    scope,
    params: { room_id: input.descriptor.roomId },
    idempotencyKey: input.idempotencyKey ?? newIdempotencyKey(),
    body: { ...input.confirmPayload, sheet_key: scope.entryId },
  })
  return parseDescriptorConfirmation(payload)
}

// ═══════════════════════════════════════════════════════════════════════════
// 4. OO → HTML
// ═══════════════════════════════════════════════════════════════════════════

export interface RequestForcesaveInput {
  readonly roomId: string
  readonly participantId: string
  readonly clientEditEpoch?: number
  readonly contributorUserIds?: readonly string[]
  readonly expectedWriteFenceEpoch?: number
  readonly idempotencyKey?: string
}

/**
 * 普通 forcesave。202 只代表「命令已受理」，不代表保存完成。
 *
 * 🔴 刻意**不接受** `kind` 参数：`close_capture` 只能由 room arbiter 在锁内 CAS 提升
 * （AC 4.10），客户端直接发起会被服务端 403。留一个 `kind` 入参等于把这条禁令变成
 * 「调用点自觉」。clean close 走 `createCloseIntent()`。
 */
export async function requestForcesave(
  scope: WorkpaperSyncEntryScope,
  input: RequestForcesaveInput,
): Promise<WorkpaperSyncForcesaveAccepted> {
  const payload = await request({
    endpoint: 'request_forcesave',
    scope,
    params: { room_id: input.roomId },
    idempotencyKey: input.idempotencyKey ?? newIdempotencyKey(),
    body: {
      participant_id: input.participantId,
      client_edit_epoch: input.clientEditEpoch ?? 0,
      contributor_user_ids: [...(input.contributorUserIds ?? [])],
      expected_write_fence_epoch: input.expectedWriteFenceEpoch ?? null,
    },
  })
  return parseForcesaveAccepted(payload)
}

export interface CreateCloseIntentInput {
  readonly roomId: string
  readonly participantId: string
  readonly clientEditEpoch?: number
  readonly adapterBuildDigest?: string
  readonly contributorSnapshotDigest?: string
  readonly contributorUserIds?: readonly string[]
  readonly expectedWriteFenceEpoch?: number
  readonly idempotencyKey?: string
}

/** clean close 的唯一入口；leader 仲裁与 exactly-one close-capture 在服务端。 */
export async function createCloseIntent(
  scope: WorkpaperSyncEntryScope,
  input: CreateCloseIntentInput,
): Promise<Record<string, unknown>> {
  return request({
    endpoint: 'create_close_intent',
    scope,
    params: { room_id: input.roomId },
    idempotencyKey: input.idempotencyKey ?? newIdempotencyKey(),
    body: {
      participant_id: input.participantId,
      client_edit_epoch: input.clientEditEpoch ?? 0,
      adapter_build_digest: input.adapterBuildDigest ?? '',
      contributor_snapshot_digest: input.contributorSnapshotDigest ?? '',
      contributor_user_ids: [...(input.contributorUserIds ?? [])],
      expected_write_fence_epoch: input.expectedWriteFenceEpoch ?? null,
    },
  })
}

/** 按**调用方给的** operation id 查（服务端先授权再 canonicalize）。 */
export async function getOperation(
  scope: WorkpaperSyncEntryScope,
  operationId: string,
): Promise<WorkpaperSyncOperationSnapshot> {
  const payload = await request({
    endpoint: 'get_operation',
    scope,
    params: { operation_id: operationId },
  })
  return parseOperationSnapshot(payload)
}

export async function getOperationConflicts(
  scope: WorkpaperSyncEntryScope,
  operationId: string,
  options: { readonly includeSuperseded?: boolean } = {},
): Promise<Record<string, unknown>> {
  return request({
    endpoint: 'get_operation_conflicts',
    scope,
    params: { operation_id: operationId },
    query: { include_superseded: options.includeSuperseded ? 'true' : 'false' },
  })
}

export async function getOperationTimeline(
  scope: WorkpaperSyncEntryScope,
  operationId: string,
  options: { readonly limit?: number } = {},
): Promise<Record<string, unknown>> {
  return request({
    endpoint: 'get_operation_timeline',
    scope,
    params: { operation_id: operationId },
    query: { limit: options.limit ?? 200 },
  })
}

/**
 * recovery case 的**独立** timeline。
 *
 * 与 operation timeline 分两个端点是刻意的：claim 之前根本没有 operation，
 * 合成一个「统一 timeline」就必须给 recovery 事件编一个 operation id。
 */
export async function getRecoveryCaseTimeline(
  scope: WorkpaperSyncEntryScope,
  caseId: string,
  options: { readonly limit?: number } = {},
): Promise<Record<string, unknown>> {
  return request({
    endpoint: 'get_recovery_case_timeline',
    scope,
    params: { case_id: caseId },
    query: { limit: options.limit ?? 200 },
  })
}

export interface ResolveConflictsInput {
  readonly operationId: string
  readonly expectedCurrentRevision: number
  readonly roomGeneration: number
  readonly clientEditEpoch: number
  readonly canonicalApplicationId: string
  readonly applicationEffectiveRequestSequence: number
  readonly roomLatestDurableApplicationId: string
  readonly roomLatestDurableSequence: number
  readonly conflictSetDigest: string
  readonly resolutions: readonly { conflictId: string; choice: string; value?: unknown }[]
  readonly idempotencyKey?: string
}

export async function resolveConflicts(
  scope: WorkpaperSyncEntryScope,
  input: ResolveConflictsInput,
): Promise<Record<string, unknown>> {
  return request({
    endpoint: 'resolve_conflicts',
    scope,
    params: { operation_id: input.operationId },
    idempotencyKey: input.idempotencyKey ?? newIdempotencyKey(),
    body: {
      expected_current_revision: input.expectedCurrentRevision,
      room_generation: input.roomGeneration,
      client_edit_epoch: input.clientEditEpoch,
      canonical_application_id: input.canonicalApplicationId,
      application_effective_request_sequence: input.applicationEffectiveRequestSequence,
      room_latest_durable_application_id: input.roomLatestDurableApplicationId,
      room_latest_durable_sequence: input.roomLatestDurableSequence,
      conflict_set_digest: input.conflictSetDigest,
      resolutions: input.resolutions.map((item) => ({
        conflict_id: item.conflictId,
        choice: item.choice,
        ...(item.value === undefined ? {} : { value: item.value }),
      })),
    },
  })
}

/**
 * 从既有 operation 的 durable incoming 重试。
 *
 * 🔴 `operationId` 必须非空且是 opaque id：`operation_id=NULL` 的 unmatched/ambiguous
 * recovery case **不得**走这里（AC 5.8 末句），它必须先 authorization-first claim。
 * 空串会拼出 `/operations//retry` 并拿到统一 404 —— 那个 404 与「无权限」不可区分。
 */
export async function retryOperation(
  scope: WorkpaperSyncEntryScope,
  operationId: string | null | undefined,
): Promise<Record<string, unknown>> {
  const id = String(operationId ?? '').trim()
  if (id === '') {
    refuse(
      'retry_requires_operation',
      '普通 retry 需要既有 operation id —— claim 前的 recovery case 三实体为空，' +
        '必须先走 authorization-first claim',
    )
  }
  return request({
    endpoint: 'retry_operation',
    scope,
    params: { operation_id: id },
  })
}

// ═══════════════════════════════════════════════════════════════════════════
// 5. recovery client
// ═══════════════════════════════════════════════════════════════════════════

/**
 * recovery case 列表。`roomId` / `generation` 是**必填** query。
 *
 * 服务端把它们声明为必填是因为「列出这个 wp 下所有 case」本身是存在性泄露面
 * （AC 10.6）。客户端把它们做成可选参数就会在缺省时打出一个 422，然后调用点很容易
 * 把 422 当「暂时没有恢复项」。
 */
export async function listRecoveryCases(
  scope: WorkpaperSyncEntryScope,
  input: { readonly roomId: string; readonly generation: number },
): Promise<WorkpaperSyncRecoveryCaseList> {
  const roomId = String(input.roomId ?? '').trim()
  if (roomId === '') {
    refuse('recovery_list_scope_required', 'listRecoveryCases 缺 room_id（AC 10.6 必填）')
  }
  if (!Number.isInteger(input.generation)) {
    refuse(
      'recovery_list_scope_required',
      `listRecoveryCases 的 generation=${JSON.stringify(input.generation)} 不是整数（AC 10.6 必填）`,
    )
  }
  const payload = await request({
    endpoint: 'list_recovery_cases',
    scope,
    query: { room_id: roomId, generation: input.generation },
  })
  return parseRecoveryCaseList(payload)
}

/**
 * authorization-first claim。
 *
 * 🔴 请求体**只能**含 case（在 route 里）/ participant / prior confirmation /
 * expected bundle / expected fence / expected generation / expected current revision。
 * 客户端不得提交任意 base、bundle 内容或 contributor —— 服务端自己从候选 confirmation
 * 与 approved bundle 冻结（design §API：「客户端不得提交任意 base/bundle」）。
 * 因此本函数的 body 是**白名单构造**而不是 `{...input}`：后者会让调用点随手多塞一个
 * `client_confirmed_base_version_id` 而没有任何判据打红。
 */
export interface ClaimRecoveryCaseInput {
  readonly caseId: string
  readonly roomId: string
  readonly participantId: string
  readonly priorConfirmationId: string
  readonly expectedGeneration: number
  readonly expectedWriteFence: number
  readonly expectedDefinitionBundleSha256: string
  readonly expectedCurrentRevision: number
  readonly idempotencyKey?: string
}

/** claim 请求体允许出现的键（白名单，唯一真源）。 */
export const CLAIM_REQUEST_ALLOWED_KEYS = [
  'room_id',
  'participant_id',
  'prior_confirmation_id',
  'expected_generation',
  'expected_write_fence',
  'expected_definition_bundle_sha256',
  'expected_current_revision',
] as const

export function buildClaimRequestBody(
  input: ClaimRecoveryCaseInput,
): Record<string, unknown> {
  const body: Record<string, unknown> = {
    room_id: input.roomId,
    participant_id: input.participantId,
    prior_confirmation_id: input.priorConfirmationId,
    expected_generation: input.expectedGeneration,
    expected_write_fence: input.expectedWriteFence,
    expected_definition_bundle_sha256: input.expectedDefinitionBundleSha256,
    expected_current_revision: input.expectedCurrentRevision,
  }
  const produced = Object.keys(body).sort()
  const allowed = [...CLAIM_REQUEST_ALLOWED_KEYS].sort()
  if (produced.join('|') !== allowed.join('|')) {
    refuse(
      'claim_body_key_drift',
      `claim 请求体键集 [${produced.join(', ')}] ≠ 白名单 [${allowed.join(', ')}] —— ` +
        '客户端不得指定 base/bundle 内容',
    )
  }
  return body
}

export async function claimRecoveryCase(
  scope: WorkpaperSyncEntryScope,
  input: ClaimRecoveryCaseInput,
): Promise<WorkpaperSyncRecoveryClaim> {
  const payload = await request({
    endpoint: 'claim_recovery_case',
    scope,
    params: { case_id: input.caseId },
    idempotencyKey: input.idempotencyKey ?? newIdempotencyKey(),
    body: buildClaimRequestBody(input),
  })
  return parseRecoveryClaim(payload)
}

/** 只终结 case 并签发短期下载 claim；三实体保持为 0。 */
export async function terminateRecoveryDownloadOnly(
  scope: WorkpaperSyncEntryScope,
  caseId: string,
): Promise<WorkpaperSyncRecoveryDownloadOnly> {
  const payload = await request({
    endpoint: 'terminate_recovery_download_only',
    scope,
    params: { case_id: caseId },
  })
  return parseRecoveryDownloadOnly(payload)
}

/**
 * download-only 签发的 claim 的唯一消费方。
 *
 * `claim` 是服务端签发的短期凭证，必须原样带回；缺它时 guard 会做三向比对失败并返回
 * 统一 404，调用点无法区分「凭证过期」与「无权限」。
 */
export async function downloadRecoveryArtifact(
  scope: WorkpaperSyncEntryScope,
  input: { readonly caseId: string; readonly claim: string },
): Promise<WorkpaperSyncRecoveryArtifact> {
  const claim = String(input.claim ?? '').trim()
  if (claim === '') {
    refuse(
      'download_claim_required',
      'downloadRecoveryArtifact 缺 download-only 签发的 claim —— 无签名下载会得到统一 404',
    )
  }
  const payload = await request({
    endpoint: 'download_recovery_artifact',
    scope,
    params: { case_id: input.caseId },
    query: { claim },
  })
  return parseRecoveryArtifact(payload)
}

// ═══════════════════════════════════════════════════════════════════════════
// 6. rollback
// ═══════════════════════════════════════════════════════════════════════════

/**
 * 按 **opaque immutable content-version UUID** 回滚。
 *
 * 🔴 `versionId` 只接受 UUID。numeric revision 只能展示或作 `expectedCurrentRevision`
 * 乐观锁：两个不同 wp 都存在 revision 1，用它拼 route 会在授权索引里碰撞成同一行
 * （AC 10.6 / 8.7）。服务端把路径参数声明成 `str` 正是为了让这条禁令由 guard 判定并走
 * 统一 404，所以客户端必须在**发出前**拦住，否则 UI 只会看到一个「找不到」。
 */
export async function rollbackVersion(
  scope: WorkpaperSyncEntryScope,
  input: {
    readonly versionId: string
    readonly expectedCurrentRevision: number
    readonly confirmed: boolean
  },
): Promise<Record<string, unknown>> {
  if (!isOpaqueUuid(input.versionId)) {
    refuse(
      'version_id_not_opaque',
      `rollback 的 versionId=${JSON.stringify(input.versionId)} 不是 opaque immutable UUID ——` +
        ' numeric revision 只能展示/作 expected-current 乐观锁，不得拼 route',
    )
  }
  if (input.confirmed !== true) {
    refuse(
      'rollback_confirmation_required',
      'rollback 需要二次确认（design §API：需编辑权限和二次确认）',
    )
  }
  return request({
    endpoint: 'rollback_version',
    scope,
    params: { version_id: input.versionId },
    body: {
      expected_current_revision: input.expectedCurrentRevision,
      confirmed: true,
    },
  })
}

/** 全部 client method 名 → endpoint 名。判据用它证明「每条路由都有唯一消费方」。 */
export const WORKPAPER_SYNC_CLIENT_ENDPOINTS = Object.freeze({
  createPendingMutation: 'create_pending_mutation',
  materialize: 'materialize',
  confirmDescriptor: 'confirm_descriptor',
  requestForcesave: 'request_forcesave',
  createCloseIntent: 'create_close_intent',
  getOperation: 'get_operation',
  getOperationConflicts: 'get_operation_conflicts',
  getOperationTimeline: 'get_operation_timeline',
  getRecoveryCaseTimeline: 'get_recovery_case_timeline',
  resolveConflicts: 'resolve_conflicts',
  retryOperation: 'retry_operation',
  listRecoveryCases: 'list_recovery_cases',
  claimRecoveryCase: 'claim_recovery_case',
  terminateRecoveryDownloadOnly: 'terminate_recovery_download_only',
  downloadRecoveryArtifact: 'download_recovery_artifact',
  rollbackVersion: 'rollback_version',
} as const)
