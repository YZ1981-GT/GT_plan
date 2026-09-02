/**
 * Task 34 四个 UI 判据文件共用的**夹具与桥驱动器**。
 *
 * spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 34
 *
 * ═══ 为什么用真桥而不是假桥 ═══
 *
 * 一个「形状像桥」的 plain object 能让任何 UI 判据通过，却抓不住「组件读错了字段」——
 * 而那恰好是 Vue 里最贵的静默失效。因此本夹具构造**真的** `useWorkpaperSyncBridge()`，
 * 只注入 API stub（Task 33 已验证过的注入点），再用桥自己的公开动作把状态推到位。
 *
 * ═══ 两个状态**结构上不可观测**（本任务的实测发现，非本任务引入） ═══
 *
 * `materializing` 与 `forcesave_accepted` 在 Task 32 的实现里都是「两个 `apply()` 同步
 * 相邻」的中间态：
 *
 * * `descriptor_received`（→ materializing）与 `descriptor_accepted`（→ oo_loading）
 *   在 `switchToOnlyOffice()` 里紧挨着，中间没有 await；
 * * `forcesave_command_accepted`（→ forcesave_accepted）与 `shell_tracking_started`
 *   （→ waiting_application）在 `switchToHtml()` 里同样紧挨着。
 *
 * 于是外部（含状态条）永远看不到这两个状态。:data:`UNOBSERVABLE_BRIDGE_STATES` 把这个
 * 事实登记下来，并由判据反向自证「它们确实推不到」——**不是**把它们豁免掉了事。
 */
import { vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { ref } from 'vue'

import {
  useWorkpaperSyncBridge,
  type WorkpaperSyncApiSurface,
  type WorkpaperSyncBridge,
} from '../useWorkpaperSyncBridge'
import { WP_BRIDGE_STATES, type WorkpaperSyncBridgeState } from '../workpaperSyncBridgeMachine'
import type {
  WorkpaperSyncDescriptorConfirmation,
  WorkpaperSyncEditorLaunchDescriptor,
  WorkpaperSyncOperationSnapshot,
  WorkpaperSyncRecoveryCase,
} from '../workpaperSyncDto'

export const UUID = (n: number): string =>
  `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
export const DIGEST = (n: number): string =>
  String(n).repeat(2).padEnd(64, 'abc123def0'.repeat(7)).slice(0, 64)

export const PROJECT = UUID(101)
export const WP = UUID(102)
export const ENTRY = 'xlsx/d4/analysis/d4-tab-customer-price'
export const SHEET = 'D4-1'

/**
 * 结构上不可观测的桥状态（见文件头）。判据必须反向证明它们推不到。
 *
 * 用 `as const` 元组是为了让 `driveTo` 的 `switch` 默认支保住**穷尽性检查**：
 * 默认支把 `target` 赋给 `UnobservableBridgeState`，于是「桥状态域新增一个成员却
 * 忘了给驱动路径」会在类型层报错，而不是等到运行时才抛。
 */
const UNOBSERVABLE = ['materializing', 'forcesave_accepted'] as const
export type UnobservableBridgeState = (typeof UNOBSERVABLE)[number]
export const UNOBSERVABLE_BRIDGE_STATES: readonly WorkpaperSyncBridgeState[] = UNOBSERVABLE

export const OBSERVABLE_BRIDGE_STATES: readonly WorkpaperSyncBridgeState[] =
  WP_BRIDGE_STATES.filter((state) => !UNOBSERVABLE_BRIDGE_STATES.includes(state))

const OO_CONFIG = Object.freeze({
  document: {
    key: 'dockey-1',
    fileType: 'xlsx',
    title: 'd4.detail.rows.xlsx',
    url: 'https://backend.internal/signed/incoming.xlsx?sig=abc',
    permissions: { edit: true, download: true },
  },
  documentType: 'cell',
  editorConfig: { mode: 'edit', customization: { forcesave: false } },
})

export function descriptorFixture(
  over: Partial<WorkpaperSyncEditorLaunchDescriptor> = {},
): WorkpaperSyncEditorLaunchDescriptor {
  return {
    operationId: UUID(20),
    roomId: UUID(21),
    participantId: UUID(22),
    docKey: 'dockey-1',
    generation: 3,
    serverAppliedRevision: 11,
    clientConfirmedBaseRevision: 10,
    contentVersionId: UUID(23),
    representationId: UUID(24),
    representationGeneration: 2,
    artifactSha256: DIGEST(1),
    writeFenceEpoch: 5,
    authorityModel: 'projection_contract',
    authorityModelDefinitionSha256: DIGEST(2),
    definitionBundleId: UUID(25),
    definitionBundleSha256: DIGEST(3),
    definitionBundleSlots: {
      template: { type: 'excel_template', sha256: DIGEST(4) },
      instrumentation: { type: 'excel_instrumentation', sha256: DIGEST(5) },
      contract: { type: 'sync_contract', sha256: DIGEST(6) },
    },
    documentType: 'xlsx',
    mode: 'edit',
    onlyofficeConfig: OO_CONFIG,
    replayed: false,
    ...over,
  }
}

export function confirmationFixture(
  over: Partial<WorkpaperSyncDescriptorConfirmation> = {},
): WorkpaperSyncDescriptorConfirmation {
  return {
    confirmationId: UUID(26),
    roomId: UUID(21),
    participantId: UUID(22),
    generation: 3,
    representationId: UUID(24),
    contentVersionId: UUID(23),
    roomState: 'active',
    replayed: false,
    forcesaveUnlocked: true,
    ...over,
  }
}

export function snapshot(
  over: Partial<WorkpaperSyncOperationSnapshot> = {},
): WorkpaperSyncOperationSnapshot {
  return {
    requestedOperationId: UUID(30),
    canonicalOperationId: UUID(30),
    followedDuplicate: false,
    state: 'accepted',
    shape: 'pre_correlation',
    applicationId: null,
    duplicateOfOperationId: null,
    errorCode: null,
    errorStage: null,
    acceptedAt: '2026-08-16T00:00:00Z',
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
    ...over,
  }
}

export function recoveryCaseFixture(
  over: Partial<WorkpaperSyncRecoveryCase> = {},
): WorkpaperSyncRecoveryCase {
  return {
    caseId: UUID(40),
    reason: 'crash_close',
    state: 'unclaimed',
    operationId: null,
    applicationId: null,
    forcesaveRequestId: null,
    candidatePriorConfirmations: [
      {
        confirmationId: UUID(41),
        participantId: UUID(22),
        contentVersionId: UUID(23),
        confirmedAt: '2026-08-16T00:00:00Z',
      },
    ],
    actions: { claim: true, downloadOnly: true },
    ...over,
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 冲突预览夹具（形态逐字对齐 `ConflictPreview.as_dict()`）
// ═══════════════════════════════════════════════════════════════════════════

export interface ConflictItemOverrides {
  conflict_id?: string
  stable_field_key?: string
  business_label?: string
  sheet_key?: string
  table_key?: string
  row_key?: string
  json_pointer?: string
  oo_location?: string
  kind?: string
  field_source?: string
  protection_policy?: string
  suggested_action?: string
  value_type?: string
  base?: unknown
  current?: unknown
  incoming?: unknown
  client_edit_epoch?: number
  incoming_sequence?: number | null
  resolved?: boolean
  is_protected?: boolean
  adjudicable_by_value_choice?: boolean
}

export function conflictItemWire(over: ConflictItemOverrides = {}): Record<string, unknown> {
  return {
    conflict_id: UUID(60),
    stable_field_key: 'rows[].amount',
    business_label: '期末余额',
    sheet_key: '明细表',
    table_key: 'tbl_detail',
    row_key: 'row-1',
    json_pointer: '/rows/0/amount',
    oo_location: '明细表!D7',
    kind: 'value',
    field_source: 'onlyoffice_cell',
    protection_policy: 'editable',
    suggested_action: 'take_incoming',
    value_type: 'amount',
    base: { present: true, value: 1000 },
    current: { present: true, value: 2000 },
    incoming: { present: true, value: 1234567.5 },
    client_edit_epoch: 4,
    incoming_sequence: 7,
    resolved: false,
    is_protected: false,
    adjudicable_by_value_choice: true,
    ...over,
  }
}

export function conflictPreviewWire(
  groups: { sheet_key: string; table_key: string; row_key: string; items: Record<string, unknown>[] }[],
  over: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    requested_operation_id: UUID(30),
    canonical_operation_id: UUID(30),
    followed_duplicate: false,
    canonical_application_id: UUID(50),
    client_edit_epoch: 4,
    incoming_sequence: 7,
    room_id: UUID(21),
    room_generation: 3,
    current_revision: 11,
    conflict_set_digest: DIGEST(9),
    definition_bundle_id: UUID(25),
    definition_bundle_sha256: DIGEST(3),
    authority_model: 'projection_contract',
    authority_model_definition_sha256: DIGEST(2),
    contract_id: 'd4-tab-customer-price',
    contract_semantic_version: '1.2.0',
    conflict_count: groups.reduce((acc, group) => acc + group.items.length, 0),
    groups,
    ...over,
  }
}

/** 三组（两 sheet / 两 table / 三 row），足以区分四种批量范围。 */
export function threeGroupPreview(): Record<string, unknown> {
  return conflictPreviewWire([
    {
      sheet_key: '明细表',
      table_key: 'tbl_detail',
      row_key: 'row-1',
      items: [
        conflictItemWire({ conflict_id: UUID(61) }),
        conflictItemWire({
          conflict_id: UUID(62),
          stable_field_key: 'rows[].memo',
          business_label: '摘要',
          value_type: 'text',
          base: { present: true, value: '旧摘要' },
          current: { present: true, value: '当前摘要' },
          incoming: { present: true, value: '回传摘要' },
        }),
      ],
    },
    {
      sheet_key: '明细表',
      table_key: 'tbl_detail',
      row_key: 'row-2',
      items: [conflictItemWire({ conflict_id: UUID(63), row_key: 'row-2' })],
    },
    {
      sheet_key: '汇总表',
      table_key: 'tbl_summary',
      row_key: 'row-9',
      items: [
        conflictItemWire({
          conflict_id: UUID(64),
          sheet_key: '汇总表',
          table_key: 'tbl_summary',
          row_key: 'row-9',
          kind: 'schema',
          protection_policy: 'read_only_formula',
          suggested_action: 'fix_structure',
          is_protected: true,
          adjudicable_by_value_choice: false,
        }),
      ],
    },
  ])
}

// ═══════════════════════════════════════════════════════════════════════════
// 桥 harness
// ═══════════════════════════════════════════════════════════════════════════

export type ApiStubs = { [K in keyof WorkpaperSyncApiSurface]: ReturnType<typeof vi.fn> }

export interface Harness {
  bridge: WorkpaperSyncBridge
  api: ApiStubs
}

/** 永不 resolve 的 promise —— 用来把桥钉在某个「正在飞」的中间态上。 */
export function pending<T>(): Promise<T> {
  return new Promise<T>(() => {})
}

export interface HarnessHooks {
  /** 覆盖宿主 flush 钩子（用 `pending()` 可把桥钉在 `flushing`）。 */
  readonly flushHtml?: () => Promise<{ expectedRevision: number; projection: unknown }>
  readonly reloadHtml?: (minimumRevision: number) => Promise<void>
}

export function harness(
  overrides: Partial<Record<keyof WorkpaperSyncApiSurface, unknown>> = {},
  hooks: HarnessHooks = {},
): Harness {
  const api = {
    createPendingMutation: vi.fn(async () => ({
      pendingMutationToken: 'tok-1',
      expectedRevision: 11,
      payloadSha256: DIGEST(7),
      expiresAt: '2026-08-16T00:05:00Z',
      idempotencyKey: 'idem-1',
    })),
    materialize: vi.fn(async () => descriptorFixture()),
    confirmDescriptor: vi.fn(async () => confirmationFixture()),
    requestForcesave: vi.fn(async () => ({
      forcesaveRequestId: UUID(29),
      operationId: UUID(30),
      requestSequence: 7,
      state: 'accepted' as const,
      pollAfterMs: 800,
      replayed: false,
      dispatchError: null,
    })),
    // 🔴 必须**回显**被问的 operation id：桥在 claim 之后会读一次 operation 让服务端
    // 自己说形态（202 回执没有 shape），并断言读回来的 requested id 与 claim 返回的一致。
    // 固定返回 `snapshot()` 会让那条一致性检查恒红 —— 不是判据太严，是夹具不像真服务端。
    getOperation: vi.fn(async (_scope: unknown, operationId: string) =>
      snapshot({
        requestedOperationId: operationId,
        canonicalOperationId: operationId,
        state: 'application_bound',
        shape: 'primary',
        applicationId: UUID(44),
        durableAt: '2026-08-16T00:00:10Z',
        applicationBoundAt: '2026-08-16T00:00:11Z',
      }),
    ),
    getOperationConflicts: vi.fn(async () => threeGroupPreview()),
    getOperationTimeline: vi.fn(async () => ({
      requested_operation_id: UUID(30),
      canonical_operation_id: UUID(30),
      followed_duplicate: false,
      application_id: UUID(50),
      operation_events: [
        {
          stream: 'operation',
          parent_id: UUID(30),
          sequence_no: 1,
          occurred_at: '2026-08-16T00:00:01Z',
          from_state: null,
          to_state: 'accepted',
          correlation_id: UUID(70),
        },
        {
          stream: 'operation',
          parent_id: UUID(30),
          sequence_no: 2,
          occurred_at: '2026-08-16T00:00:05Z',
          from_state: 'accepted',
          to_state: 'application_bound',
          correlation_id: UUID(71),
        },
      ],
      application_events: [
        {
          stream: 'application',
          parent_id: UUID(50),
          sequence_no: 1,
          occurred_at: '2026-08-16T00:00:06Z',
          from_state: null,
          to_state: 'created',
        },
      ],
      checks: [],
      server_clock_source: 'database',
    })),
    getRecoveryCaseTimeline: vi.fn(async () => ({
      case_id: UUID(40),
      state: 'application_created',
      reason: 'crash_close',
      claimed_operation_id: UUID(43),
      claimed_application_id: UUID(44),
      recovery_request_id: UUID(42),
      has_three_entities: true,
      events: [
        {
          stream: 'recovery_case',
          parent_id: UUID(40),
          sequence_no: 1,
          occurred_at: '2026-08-16T00:01:00Z',
          from_state: null,
          to_state: 'unclaimed',
        },
        {
          stream: 'recovery_case',
          parent_id: UUID(40),
          sequence_no: 2,
          occurred_at: '2026-08-16T00:02:00Z',
          from_state: 'unclaimed',
          to_state: 'application_created',
        },
      ],
      checks: [],
      server_clock_source: 'database',
    })),
    resolveConflicts: vi.fn(async () => ({ decision: 'proceed', revision_after: 12 })),
    retryOperation: vi.fn(async () => ({ retried: true })),
    listRecoveryCases: vi.fn(async () => ({
      roomId: UUID(21),
      generation: 3,
      cases: [recoveryCaseFixture()],
    })),
    claimRecoveryCase: vi.fn(async () => ({
      caseId: UUID(40),
      forcesaveRequestId: UUID(42),
      operationId: UUID(43),
      applicationId: UUID(44),
      state: 'application_created' as const,
    })),
    terminateRecoveryDownloadOnly: vi.fn(async () => ({
      caseId: UUID(40),
      state: 'download_only' as const,
      downloadClaim: 'claim-1',
      expiresInSeconds: 300,
    })),
    downloadRecoveryArtifact: vi.fn(async () => ({
      caseId: UUID(40),
      artifactId: UUID(45),
      artifactSha256: DIGEST(8),
      documentType: 'xlsx',
      sizeBytes: 1024,
      relativePath: 'incoming/a.xlsx',
    })),
    rollbackVersion: vi.fn(async () => ({ revision_after: 12, rolled_back: true })),
  }
  for (const [key, value] of Object.entries(overrides)) {
    ;(api as Record<string, unknown>)[key] = value
  }
  const bridge = useWorkpaperSyncBridge({
    entryId: ref(ENTRY),
    wpId: ref(WP),
    projectId: ref(PROJECT),
    sheetKey: ref(SHEET),
    capability: 'bidirectional',
    flushHtml:
      hooks.flushHtml ?? vi.fn(async () => ({ expectedRevision: 11, projection: { rows: [] } })),
    reloadHtml: hooks.reloadHtml ?? vi.fn(async () => {}),
    api: api as unknown as WorkpaperSyncApiSurface,
    storage: null,
    installBeforeUnload: false,
  })
  return { bridge, api: api as ApiStubs }
}

/** 走完 flush → materialize → mount → ready → confirm，落在 `oo_editing`。 */
export async function openToEditing(h: Harness): Promise<WorkpaperSyncEditorLaunchDescriptor> {
  const descriptor = await h.bridge.switchToOnlyOffice()
  h.bridge.notifyEditorMounted()
  await h.bridge.notifyDocumentReady()
  return descriptor
}

/** 走到 `waiting_application`（已发命令、shell 两 link 均空）。 */
export async function openToWaitingApplication(h: Harness): Promise<void> {
  await openToEditing(h)
  await h.bridge.switchToHtml()
}

/**
 * 用桥**自己的**公开动作把状态推到 `target`。
 *
 * 每条分支都是一次真实的调用序列，没有任何一处直接写 `state` ——
 * 于是「组件读了桥的哪个字段」这件事仍然由真实数据流决定。
 */
export async function driveTo(
  target: WorkpaperSyncBridgeState,
  options: { readonly successorIntentId?: string } = {},
): Promise<Harness> {
  if (UNOBSERVABLE_BRIDGE_STATES.includes(target)) {
    throw new Error(
      `${target} 在 Task 32 的实现里是同步相邻的中间态，公开面推不到 —— ` +
        '不要给它编一条驱动路径',
    )
  }
  switch (target) {
    case 'html_idle': {
      return harness()
    }
    case 'flushing': {
      // flushHtml 永不 resolve ⇒ 桥停在 `apply('flush_started')` 之后。
      const h = harness({}, { flushHtml: () => pending() })
      void h.bridge.switchToOnlyOffice().catch(() => {})
      await flushPromises()
      return h
    }
    case 'committing': {
      const h = harness({ materialize: vi.fn(() => pending()) })
      void h.bridge.switchToOnlyOffice().catch(() => {})
      await flushPromises()
      return h
    }
    case 'oo_loading': {
      const h = harness()
      await h.bridge.switchToOnlyOffice()
      return h
    }
    case 'descriptor_mounted': {
      const h = harness()
      await h.bridge.switchToOnlyOffice()
      h.bridge.notifyEditorMounted()
      return h
    }
    case 'confirming_descriptor': {
      const h = harness({ confirmDescriptor: vi.fn(() => pending()) })
      await h.bridge.switchToOnlyOffice()
      h.bridge.notifyEditorMounted()
      void h.bridge.notifyDocumentReady().catch(() => {})
      await flushPromises()
      return h
    }
    case 'oo_editing': {
      const h = harness()
      await openToEditing(h)
      return h
    }
    case 'forcesave_requesting': {
      const h = harness({ requestForcesave: vi.fn(() => pending()) })
      await openToEditing(h)
      void h.bridge.switchToHtml().catch(() => {})
      await flushPromises()
      return h
    }
    case 'forcesave_frozen': {
      const h = harness({
        requestForcesave: vi.fn(async () => ({
          forcesaveRequestId: UUID(29),
          operationId: UUID(30),
          requestSequence: 7,
          state: 'accepted' as const,
          pollAfterMs: 800,
          replayed: false,
          dispatchError: 'command_service_unavailable',
        })),
      })
      await openToEditing(h)
      await h.bridge.switchToHtml()
      return h
    }
    case 'waiting_application': {
      const h = harness()
      await openToWaitingApplication(h)
      return h
    }
    case 'incoming_durable': {
      const h = harness()
      await openToWaitingApplication(h)
      h.bridge.ingestOperationSnapshot(
        snapshot({ state: 'accepted', durableAt: '2026-08-16T00:00:10Z' }),
      )
      return h
    }
    case 'application_bound': {
      const h = harness()
      await openToWaitingApplication(h)
      h.bridge.ingestOperationSnapshot(
        snapshot({
          state: 'application_bound',
          shape: 'primary',
          applicationId: UUID(50),
          durableAt: '2026-08-16T00:00:10Z',
          applicationBoundAt: '2026-08-16T00:00:11Z',
          definitionBundleSha256: DIGEST(3),
          authorityModelDefinitionSha256: DIGEST(2),
        }),
      )
      return h
    }
    case 'duplicate': {
      const h = harness()
      await openToWaitingApplication(h)
      h.bridge.ingestOperationSnapshot(
        snapshot({
          state: 'duplicate',
          shape: 'duplicate',
          canonicalOperationId: UUID(31),
          duplicateOfOperationId: UUID(31),
          durableAt: '2026-08-16T00:00:10Z',
          terminal: true,
        }),
      )
      return h
    }
    case 'merging': {
      const h = harness()
      await openToWaitingApplication(h)
      h.bridge.ingestOperationSnapshot(
        snapshot({ state: 'merging', shape: 'primary', applicationId: UUID(50) }),
      )
      return h
    }
    case 'rematerializing': {
      const h = harness()
      await openToWaitingApplication(h)
      h.bridge.ingestOperationSnapshot(
        snapshot({ state: 'rematerializing', shape: 'primary', applicationId: UUID(50) }),
      )
      return h
    }
    case 'conflict': {
      const h = harness()
      await openToWaitingApplication(h)
      h.bridge.ingestOperationSnapshot(
        snapshot({
          state: 'conflict',
          shape: 'primary',
          applicationId: UUID(50),
          conflictCount: 4,
          durableAt: '2026-08-16T00:00:10Z',
        }),
      )
      return h
    }
    case 'refresh_required': {
      const h = harness()
      await openToWaitingApplication(h)
      h.bridge.ingestOperationSnapshot(
        snapshot({ state: 'refresh_required', shape: 'primary', applicationId: UUID(50) }),
      )
      return h
    }
    case 'applied': {
      const h = harness()
      await openToWaitingApplication(h)
      h.bridge.ingestOperationSnapshot(
        snapshot({
          state: 'applied',
          shape: 'primary',
          applicationId: UUID(50),
          resultRevision: 12,
          durableAt: '2026-08-16T00:00:10Z',
          operationFinishedAt: '2026-08-16T00:00:20Z',
          definitionBundleSha256: DIGEST(3),
          authorityModelDefinitionSha256: DIGEST(2),
          terminal: true,
        }),
      )
      return h
    }
    case 'close_authorization_stale': {
      const h = harness()
      await openToEditing(h)
      h.bridge.notifyCloseAuthorizationLost()
      return h
    }
    case 'close_recovery_required': {
      const h = harness()
      await openToEditing(h)
      h.bridge.notifyCloseAuthorizationLost()
      h.bridge.notifyCloseNoSuccessor()
      return h
    }
    case 'recovery_pending': {
      const h = harness()
      h.bridge.notifyRecoveryCase(recoveryCaseFixture())
      return h
    }
    case 'recovery_claiming': {
      const h = harness({ claimRecoveryCase: vi.fn(() => pending()) })
      await h.bridge.listRecoveryCases({ roomId: UUID(21), generation: 3 })
      void h.bridge
        .claimRecoveryCase({
          caseId: UUID(40),
          roomId: UUID(21),
          participantId: UUID(22),
          priorConfirmationId: UUID(41),
          expectedGeneration: 3,
          expectedWriteFence: 5,
          expectedDefinitionBundleSha256: DIGEST(3),
          expectedCurrentRevision: 11,
        })
        .catch(() => {})
      await flushPromises()
      return h
    }
    case 'recovery_download_only': {
      const h = harness()
      h.bridge.notifyRecoveryCase(recoveryCaseFixture())
      await h.bridge.terminateRecoveryDownloadOnly(UUID(40))
      return h
    }
    case 'error': {
      const h = harness()
      await openToEditing(h)
      h.bridge.notifyHostFailure('editor_runtime', new Error('内核异常'))
      return h
    }
    default: {
      // 穷尽性检查：走到这里的只能是两个不可观测中间态；
      // 桥状态域新增成员而没给驱动路径时，本行在类型层就报错。
      const onlyUnobservable: UnobservableBridgeState = target
      throw new Error(`未登记驱动路径：${JSON.stringify(onlyUnobservable)}`)
    }
  }
}

/** `close_successor_applied` 的驱动（结局是 `applied`，但归因于接任者）。 */
export async function driveToSuccessorApplied(successorIntentId: string): Promise<Harness> {
  const h = harness()
  await openToEditing(h)
  h.bridge.notifyCloseAuthorizationLost()
  h.bridge.notifyCloseSuccessorApplied(successorIntentId)
  return h
}

/**
 * 剥掉 `<!-- -->`、块注释与行注释。
 *
 * 🔴 结构判据必须剥注释：本任务的源码注释里逐字写着「本文件没有 retryOperation 入口」，
 * 不剥就等于把说明当成违规证据。剥完必须正反自检（剥过头会让判据恒真）。
 */
export function stripComments(source: string): string {
  return source
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}
