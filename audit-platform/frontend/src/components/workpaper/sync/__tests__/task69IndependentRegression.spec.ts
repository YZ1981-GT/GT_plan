/**
 * Task 69 前端状态机 / recovery / descriptor / 宿主与 DOM **独立回归**判据面。
 *
 * spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 7 Task 69
 *
 * ═══ 为什么这个文件必须自己重新表达一遍 ═══
 *
 * 正文逐字：「不得由实现任务自证」。所以本文件：
 *
 * * **不 import** 任何实现任务的 `__tests__` 夹具（`workpaperSyncUiHarness.ts` 属 Task 34），
 *   自带 wire 级夹具工厂；
 * * **不 stub 被判据的模块**。唯一被替换的是平台 HTTP 面 `@/utils/http` —— 于是
 *   `workpaperSyncApi` 的 URL 拼接、`workpaperSyncDto` 的解析、`useWorkpaperSyncBridge`
 *   的转换、`WorkpaperSyncEditorHost` 的挂载全部**真跑**；
 * * 判据落在**真实挂载后的 DOM** 与**真实发出的 network 调用序列**上。正文逐字
 *   「判据不以 import/字符串存在」—— 本文件里没有一条 `toContain(源码)` 式断言。
 *
 * ═══ 一条共享的有序观测带 ═══
 *
 * :data:`OBS.trace` 是**唯一**时间轴：network 调用、DocEditor 构造、组件 emit、DOM 快照
 * 都往同一个单调序号里写。于是「mount → ready → confirm」这类顺序判据可以直接比下标，
 * 而不是「三件事都发生过」（后者对顺序被交换全绿）。
 *
 * ═══ 每条顺序/禁令判据都配一条反事实臂 ═══
 *
 * 判据函数（`assertOrder` / `assertEndpointMultiset` / `assertThreeEntitiesZero` …）先对
 * **真实观测**断言通过，再对一条**合成的坏观测**断言必须抛。只有正向不足以证明判据非
 * 重言 —— 本 spec 的变异运行已多次证明「三件事都发生过」型判据抓不住顺序错误。
 *
 * ═══ 本文件不宣称什么 ═══
 *
 * `WorkpaperSyncEditorHost.vue` 目前**没有任何生产宿主 import 它**（替代面 19/22 从
 * 生产文件不可达，见报告 `BP-69-1`）。因此本文件证明的是「组件级真实挂载链路」，
 * **不是**「生产 `Gt*.vue` 宿主链路」。两个档位在报告里分开记，后者 owner 不是本任务。
 */
import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { nextTick, ref } from 'vue'
import fc from 'fast-check'

// ═══════════════════════════════════════════════════════════════════════════
// §0 观测带 + HTTP 替身（唯一被替换的模块）
// ═══════════════════════════════════════════════════════════════════════════

interface TraceRow {
  readonly seq: number
  readonly kind: 'net' | 'editor' | 'emit' | 'dom'
  readonly name: string
  readonly detail: Record<string, unknown>
}

interface NetCall {
  readonly seq: number
  readonly method: 'GET' | 'POST'
  readonly url: string
  readonly endpoint: string
  readonly headers: Record<string, string>
  readonly params: Record<string, unknown> | null
  readonly body: unknown
}

const OBS = vi.hoisted(() => ({
  trace: [] as unknown[],
  net: [] as unknown[],
  routes: [] as { key: string; test: (url: string, method: string) => boolean; reply: (call: unknown) => unknown }[],
  counter: { n: 0 },
  /**
   * URL → endpoint 名的**独立**分类器。
   *
   * 刻意不 import 生成的 `WP_SYNC_ROUTES`：那份表是被判据的对象之一，用它分类等于
   * 让被测物自己给答案。顺序敏感（具体在前、宽松在后），分不出来返回 `UNKNOWN`
   * 并由判据打红 —— 静默归到某一类会让「打错端点」这条最贵的漂移看不见。
   */
  classify(url: string): string {
    const path = url.split('?')[0]
    const table: [string, RegExp][] = [
      ['create_pending_mutation', /\/pending-mutations$/],
      ['materialize', /\/materialize$/],
      ['confirm_descriptor', /\/rooms\/[^/]+\/confirm-descriptor$/],
      ['request_forcesave', /\/rooms\/[^/]+\/forcesave$/],
      ['create_close_intent', /\/rooms\/[^/]+\/close-intents$/],
      ['get_operation_conflicts', /\/operations\/[^/]+\/conflicts$/],
      ['get_operation_timeline', /\/operations\/[^/]+\/timeline$/],
      ['retry_operation', /\/operations\/[^/]+\/retry$/],
      ['resolve_conflicts', /\/operations\/[^/]+\/resolve$/],
      ['get_operation', /\/operations\/[^/]+$/],
      ['claim_recovery_case', /\/recovery-cases\/[^/]+\/claim$/],
      ['terminate_recovery_download_only', /\/recovery-cases\/[^/]+\/download-only$/],
      ['download_recovery_artifact', /\/recovery-cases\/[^/]+\/download$/],
      ['get_recovery_case_timeline', /\/recovery-cases\/[^/]+\/timeline$/],
      ['list_recovery_cases', /\/recovery-cases$/],
      ['rollback_version', /\/versions\/[^/]+\/rollback$/],
    ]
    for (const [name, pattern] of table) {
      if (pattern.test(path)) return name
    }
    return 'UNKNOWN'
  },
}))

vi.mock('@/utils/http', () => {
  const dispatch = (
    method: 'GET' | 'POST',
    url: string,
    config: { headers?: Record<string, string>; params?: Record<string, unknown> } | undefined,
    body: unknown,
  ): Promise<{ data: unknown }> => {
    OBS.counter.n += 1
    const call = {
      seq: OBS.counter.n,
      method,
      url,
      endpoint: OBS.classify(url),
      headers: { ...(config?.headers ?? {}) },
      params: config?.params ? { ...config.params } : null,
      body,
    }
    OBS.net.push(call)
    OBS.trace.push({ seq: call.seq, kind: 'net', name: call.endpoint, detail: { url, method } })
    for (let index = OBS.routes.length - 1; index >= 0; index -= 1) {
      const route = OBS.routes[index]
      if (!route.test(url, method)) continue
      let outcome: unknown
      try {
        outcome = route.reply(call)
      } catch (error) {
        return Promise.reject(error)
      }
      if (outcome instanceof Error) return Promise.reject(outcome)
      return Promise.resolve({ data: outcome })
    }
    return Promise.reject(
      new Error(`[T69] 未登记的请求 ${method} ${url} —— 判据必须显式登记每个被打到的端点`),
    )
  }
  return {
    default: {
      get: (url: string, config?: Record<string, never>) =>
        dispatch('GET', url, config as never, undefined),
      post: (url: string, body?: unknown, config?: Record<string, never>) =>
        dispatch('POST', url, config as never, body),
    },
  }
})

// ── 真实被判据的模块（一个都不 stub）

import {
  WP_BRIDGE_AC_11_2_REQUIRED_STATES,
  WP_BRIDGE_EVENTS,
  WP_BRIDGE_STATES,
  WP_BRIDGE_STATE_TEXT,
  auditBridgeMachine,
  transitionBridgeState,
  type WorkpaperSyncBridgeEvent,
  type WorkpaperSyncBridgeMode,
  type WorkpaperSyncBridgeState,
} from '../workpaperSyncBridgeMachine'
import { useWorkpaperSyncBridge, type WorkpaperSyncBridge } from '../useWorkpaperSyncBridge'
import WorkpaperSyncEditorHost from '../WorkpaperSyncEditorHost.vue'
import WorkpaperSyncConflictDialog from '../WorkpaperSyncConflictDialog.vue'
import { WP_SYNC_HOST_ADDED_CONFIG_KEYS } from '../workpaperSyncEditorHostRuntime'
import {
  migrateWorkpaperSyncMode,
  persistWorkpaperSyncMode,
  workpaperSyncModeKey,
} from '../workpaperSyncModeStorage'
import { useWorkpaperContentRefresh } from '../workpaperSyncContentRefresh'
import { WorkpaperSyncContractError } from '../workpaperSyncDto'
import * as syncApi from '../workpaperSyncApi'
// 唯一被替换的那一面。这里 import 它**只为**在 I34 里主动走一遍判据面自己的 fail-closed 分支。
import http from '@/utils/http'

// ═══════════════════════════════════════════════════════════════════════════
// §1 观测带辅助
// ═══════════════════════════════════════════════════════════════════════════

const trace = (): TraceRow[] => OBS.trace as TraceRow[]
const netCalls = (): NetCall[] => OBS.net as NetCall[]

function record(kind: TraceRow['kind'], name: string, detail: Record<string, unknown> = {}): void {
  OBS.counter.n += 1
  OBS.trace.push({ seq: OBS.counter.n, kind, name, detail })
}

function resetObservations(): void {
  OBS.trace.length = 0
  OBS.net.length = 0
  OBS.routes.length = 0
  OBS.counter.n = 0
}

/** 登记一条响应。后登记的优先（便于在单个测试里覆盖默认响应）。 */
function respond(
  endpoint: string,
  reply: (call: NetCall) => unknown,
  method?: 'GET' | 'POST',
): void {
  OBS.routes.push({
    key: endpoint,
    test: (url, m) => OBS.classify(url) === endpoint && (method === undefined || m === method),
    reply: reply as (call: unknown) => unknown,
  })
}

/** 观测带上某个标记的下标（`kind:name`），不存在返回 -1。 */
function at(marker: string): number {
  const [kind, name] = marker.split(':')
  return trace().findIndex((row) => row.kind === kind && row.name === name)
}

/**
 * 顺序判据。**接受一条观测带**（可以是真实的，也可以是合成的坏带）—— 于是同一个
 * 判据函数既能证明真实链路成立，也能被反事实臂证明它真的会拒绝顺序颠倒。
 *
 * 🔴 不是「三件事都发生过」：那种判据对交换顺序全绿。这里逐对比下标。
 */
function assertOrder(rows: readonly TraceRow[], markers: readonly string[]): void {
  const positions = markers.map((marker) => {
    const [kind, name] = marker.split(':')
    const index = rows.findIndex((row) => row.kind === kind && row.name === name)
    if (index < 0) throw new Error(`[T69] 观测带里缺 ${marker}`)
    return { marker, index }
  })
  for (let i = 1; i < positions.length; i += 1) {
    if (positions[i - 1].index >= positions[i].index) {
      throw new Error(
        `[T69] 顺序违反：${positions[i - 1].marker}(#${positions[i - 1].index}) 必须早于 ` +
          `${positions[i].marker}(#${positions[i].index})`,
      )
    }
  }
}

/** 交换观测带里两个标记的位置，用于反事实臂。 */
function swapped(rows: readonly TraceRow[], a: string, b: string): TraceRow[] {
  const copy = [...rows]
  const find = (marker: string): number => {
    const [kind, name] = marker.split(':')
    return copy.findIndex((row) => row.kind === kind && row.name === name)
  }
  const i = find(a)
  const j = find(b)
  if (i < 0 || j < 0) throw new Error(`[T69] 合成坏带失败：缺 ${a} 或 ${b}`)
  const tmp = copy[i]
  copy[i] = copy[j]
  copy[j] = tmp
  return copy
}

/** 端点多重集等值判据（**等值**而非包含：包含式对「多打了一次 config」全绿）。 */
function assertEndpointMultiset(calls: readonly NetCall[], expected: readonly string[]): void {
  const got = calls.map((call) => call.endpoint).sort()
  const want = [...expected].sort()
  if (got.join('|') !== want.join('|')) {
    throw new Error(`[T69] 端点多重集 [${got.join(', ')}] ≠ 期望 [${want.join(', ')}]`)
  }
}

/** 三实体全空判据（接受任意载体，反事实臂喂非空必须抛）。 */
function assertThreeEntitiesZero(
  label: string,
  entities: {
    forcesaveRequestId: string | null
    applicationId: string | null
    operationId: string | null
  },
): void {
  const present = Object.entries(entities)
    .filter(([, value]) => value !== null && String(value).trim() !== '')
    .map(([key]) => key)
  if (present.length > 0) {
    throw new Error(`[T69] ${label} 带 [${present.join(', ')}] —— claim 前/download-only 必须三者全空`)
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// §2 wire 级夹具（自带，不用实现任务的夹具）
// ═══════════════════════════════════════════════════════════════════════════

const UUID = (n: number): string => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const DIGEST = (n: number): string =>
  n.toString(16).padStart(2, '0').repeat(32).slice(0, 64)

const PROJECT = UUID(901)
const WP = UUID(902)
const ENTRY = 'xlsx/d4/analysis/d4-tab-customer-price'
const SHEET = 'D4-1'
const SCOPE_PREFIX = `/api/projects/${PROJECT}/workpapers/${WP}/sync/entries/${ENTRY}`

const ROOM = UUID(921)
const PARTICIPANT = UUID(922)
const OPERATION = UUID(930)
const PRIMARY_OPERATION = UUID(931)
const APPLICATION = UUID(940)
const REQUEST = UUID(941)
const CASE = UUID(950)
const CONFIRMATION = UUID(951)

const OO_CONFIG = Object.freeze({
  document: Object.freeze({
    key: 'dockey-t69',
    fileType: 'xlsx',
    title: 'd4.detail.rows.xlsx',
    url: 'https://backend.internal/signed/incoming.xlsx?sig=t69',
    permissions: Object.freeze({ edit: true, download: true }),
  }),
  documentType: 'cell',
  editorConfig: Object.freeze({
    mode: 'edit',
    customization: Object.freeze({ forcesave: false }),
  }),
})

function descriptorWire(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    operation_id: UUID(920),
    room_id: ROOM,
    participant_id: PARTICIPANT,
    doc_key: 'dockey-t69',
    generation: 3,
    server_applied_revision: 11,
    client_confirmed_base_revision: 10,
    content_version_id: UUID(923),
    representation_id: UUID(924),
    representation_generation: 2,
    artifact_sha256: DIGEST(1),
    write_fence_epoch: 5,
    authority_model: 'projection_contract',
    authority_model_definition_sha256: DIGEST(2),
    definition_bundle_id: UUID(925),
    definition_bundle_sha256: DIGEST(3),
    definition_bundle_slots: {
      template: { type: 'excel_template', sha256: DIGEST(4) },
      instrumentation: { type: 'excel_instrumentation', sha256: DIGEST(5) },
      contract: { type: 'sync_contract', sha256: DIGEST(6) },
    },
    document_type: 'xlsx',
    mode: 'edit',
    onlyoffice_config: OO_CONFIG,
    replayed: false,
    ...over,
  }
}

function pendingWire(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    pending_mutation_token: 'pmt-t69',
    expected_revision: 11,
    payload_sha256: DIGEST(7),
    expires_at: '2026-09-01T00:05:00Z',
    ...over,
  }
}

function confirmationWire(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    confirmation_id: CONFIRMATION,
    room_id: ROOM,
    participant_id: PARTICIPANT,
    generation: 3,
    representation_id: UUID(924),
    content_version_id: UUID(923),
    room_state: 'active',
    replayed: false,
    forcesave_unlocked: true,
    ...over,
  }
}

function acceptedWire(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    forcesave_request_id: REQUEST,
    operation_id: OPERATION,
    request_sequence: 4,
    state: 'accepted',
    poll_after_ms: 800,
    replayed: false,
    dispatch_error: null,
    ...over,
  }
}

function operationWire(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    requested_operation_id: OPERATION,
    canonical_operation_id: OPERATION,
    followed_duplicate: false,
    state: 'accepted',
    application_id: null,
    duplicate_of_operation_id: null,
    error_code: null,
    error_stage: null,
    accepted_at: '2026-09-01T00:00:00Z',
    application_bound_at: null,
    operation_finished_at: null,
    result_revision: null,
    conflict_count: null,
    logical_result_code: null,
    definition_bundle_id: null,
    definition_bundle_sha256: null,
    authority_model_definition_sha256: null,
    durable_at: null,
    finished_at: null,
    ...over,
  }
}

function recoveryCaseWire(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    case_id: CASE,
    reason: 'crash_close',
    state: 'unclaimed',
    operation_id: null,
    application_id: null,
    forcesave_request_id: null,
    candidate_prior_confirmations: [
      {
        confirmation_id: CONFIRMATION,
        participant_id: PARTICIPANT,
        content_version_id: UUID(923),
        confirmed_at: '2026-09-01T00:00:00Z',
      },
    ],
    actions: { claim: true, download_only: true },
    ...over,
  }
}

function recoveryListWire(cases: Record<string, unknown>[] = [recoveryCaseWire()]): Record<string, unknown> {
  return { room_id: ROOM, generation: 3, cases }
}

/** 冲突预览 wire（形态逐字对齐 `parseConflictPreview` 的必填集）。 */
function conflictPreviewWire(): Record<string, unknown> {
  return {
    requested_operation_id: OPERATION,
    canonical_operation_id: OPERATION,
    followed_duplicate: false,
    canonical_application_id: APPLICATION,
    client_edit_epoch: 4,
    incoming_sequence: 7,
    room_id: ROOM,
    room_generation: 3,
    current_revision: 12,
    conflict_set_digest: DIGEST(9),
    definition_bundle_id: UUID(925),
    definition_bundle_sha256: DIGEST(3),
    authority_model: 'projection_contract',
    authority_model_definition_sha256: DIGEST(2),
    contract_id: 'd4.detail',
    contract_semantic_version: '1.2.0',
    groups: [
      {
        sheet_key: '明细表',
        table_key: 'tbl_detail',
        row_key: 'row-1',
        items: [
          {
            conflict_id: UUID(960),
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
            incoming: { present: true, value: 3000 },
            client_edit_epoch: 4,
            incoming_sequence: 7,
            resolved: false,
            is_protected: false,
            adjudicable_by_value_choice: true,
          },
        ],
      },
    ],
  }
}

/** 服务端统一 404/403 的**逐字**形态：纯字符串 detail，没有 `error_code`。 */
function unifiedRefusal(status: 403 | 404): Error {
  const error = new Error('Request failed') as Error & {
    response: { status: number; data: { detail: string } }
  }
  error.response = { status, data: { detail: '资源不存在或不可访问' } }
  return error
}

/** 带 `error_code` 的业务失败。 */
function codedFailure(status: number, errorCode: string, message = '业务失败'): Error {
  const error = new Error(message) as Error & {
    response: { status: number; data: { detail: Record<string, unknown> } }
  }
  error.response = { status, data: { detail: { error_code: errorCode, message } } }
  return error
}

// ═══════════════════════════════════════════════════════════════════════════
// §3 真实桥 + 真实宿主装配
// ═══════════════════════════════════════════════════════════════════════════

interface Harness {
  readonly bridge: WorkpaperSyncBridge
  readonly wrapper: ReturnType<typeof mount>
  readonly editors: { placeholderId: string; config: Record<string, unknown> }[]
  readonly destroyed: string[]
  readonly reloads: number[]
  fireDocumentReady(): Promise<void>
  fireStateChange(dirty: boolean): void
  fireEditorError(code: number): Promise<void>
  status(): { kind: string; text: string }
  snapshotDom(label: string): void
}

interface HarnessOptions {
  readonly capability?: 'bidirectional' | 'single_html' | 'single_onlyoffice' | 'unreachable'
  readonly flushHtml?: () => Promise<{ expectedRevision: number; projection: unknown }>
  readonly reloadHtml?: (minimum: number) => Promise<void>
  readonly docsApiThrows?: boolean
  readonly installBeforeUnload?: boolean
  readonly descriptorPropName?: string
}

function makeHarness(options: HarnessOptions = {}): Harness {
  const editors: { placeholderId: string; config: Record<string, unknown> }[] = []
  const destroyed: string[] = []
  const reloads: number[] = []
  let events: Record<string, (payload?: unknown) => void> = {}

  const bridge = useWorkpaperSyncBridge({
    entryId: ref(ENTRY),
    wpId: ref(WP),
    projectId: ref(PROJECT),
    sheetKey: ref(SHEET),
    capability: options.capability ?? 'bidirectional',
    flushHtml:
      options.flushHtml ??
      (async () => ({ expectedRevision: 11, projection: { rows: [{ amount: 1 }] } })),
    reloadHtml:
      options.reloadHtml ??
      (async (minimum: number) => {
        reloads.push(minimum)
        record('dom', 'reload-html', { minimum })
      }),
    storage: null,
    installBeforeUnload: options.installBeforeUnload ?? false,
  })

  const docsApiLoader = async () => {
    if (options.docsApiThrows) {
      throw new Error('[T69] DocsAPI 载入失败（构造反事实臂）')
    }
    return {
      DocEditor: class {
        destroyEditor?: () => void
        constructor(placeholderId: string, config: Record<string, unknown>) {
          editors.push({ placeholderId, config })
          events = config.events as Record<string, (payload?: unknown) => void>
          record('editor', 'doc-editor-constructed', { placeholderId })
          this.destroyEditor = () => {
            destroyed.push(placeholderId)
            record('editor', 'doc-editor-destroyed', { placeholderId })
          }
        }
      },
    }
  }

  const descriptorProp = options.descriptorPropName ?? 'descriptor'
  const props: Record<string, unknown> = {
    bridge,
    docsApiLoader,
    onReady: (payload: unknown) => record('emit', 'ready', payload as Record<string, unknown>),
    onDirty: (payload: unknown) => record('emit', 'dirty', payload as Record<string, unknown>),
    onSaveRequested: (payload: unknown) =>
      record('emit', 'save-requested', payload as Record<string, unknown>),
    onIncomingDurable: (payload: unknown) =>
      record('emit', 'incoming-durable', payload as Record<string, unknown>),
    onTerminal: (payload: unknown) => record('emit', 'terminal', payload as Record<string, unknown>),
    onRecoveryCase: (payload: unknown) =>
      record('emit', 'recovery-case', payload as Record<string, unknown>),
    onError: (payload: unknown) => record('emit', 'error', payload as Record<string, unknown>),
  }
  props[descriptorProp] = null

  const wrapper = mount(WorkpaperSyncEditorHost, { props })

  const harness: Harness = {
    bridge,
    wrapper,
    editors,
    destroyed,
    reloads,
    async fireDocumentReady() {
      events.onDocumentReady()
      await flushPromises()
      await nextTick()
    },
    fireStateChange(dirty: boolean) {
      events.onDocumentStateChange({ data: dirty })
    },
    async fireEditorError(code: number) {
      events.onError({ data: { errorCode: code, errorDescription: '编辑器异常' } })
      await flushPromises()
      await nextTick()
    },
    status() {
      const node = wrapper.find('[data-testid="wp-sync-host-status"]')
      return { kind: node.attributes('data-kind') ?? '', text: node.text() }
    },
    snapshotDom(label: string) {
      const s = harness.status()
      record('dom', label, {
        kind: s.kind,
        text: s.text,
        editorRendered: wrapper.find('[data-testid="wp-sync-host-editor"]').exists(),
        maskRendered: wrapper.find('[data-testid="wp-sync-host-mask"]').exists(),
        recoveryRendered: wrapper.find('[data-testid="wp-sync-host-recovery"]').exists(),
        retryRendered: wrapper.find('[data-testid="wp-sync-host-retry"]').exists(),
      })
    },
  }
  return harness
}

/** 走完 flush → pending → materialize → mount → ready → confirm 的真实一趟。 */
async function driveOpen(harness: Harness): Promise<void> {
  respond('create_pending_mutation', () => pendingWire())
  respond('materialize', () => descriptorWire())
  respond('confirm_descriptor', () => confirmationWire())
  const descriptor = await harness.bridge.switchToOnlyOffice()
  await harness.wrapper.setProps({ descriptor })
  await flushPromises()
  await nextTick()
  await harness.fireDocumentReady()
}

/** 内存 localStorage（迁移判据用；不碰 jsdom 的全局 store）。 */
function memoryStorage(seed: Record<string, string> = {}) {
  const map = new Map(Object.entries(seed))
  return {
    get length() {
      return map.size
    },
    key: (index: number) => [...map.keys()][index] ?? null,
    getItem: (key: string) => (map.has(key) ? (map.get(key) as string) : null),
    setItem: (key: string, value: string) => {
      map.set(key, value)
    },
    removeItem: (key: string) => {
      map.delete(key)
    },
    snapshot: () => Object.fromEntries(map),
  }
}

/**
 * 导出给 Task 69 门的**真实观测带**。
 *
 * 门自己用 Python 重新实现同一套顺序判据并在这份观测带上现算一遍（教训 17：只读磁盘
 * 产物的判据对实现侧改动天生不敏感 ⇒ 每条结论都要配一条逻辑级现算）。观测带里没有
 * 随机值也没有墙钟耗时，所以门的逐字节锁不会因为多跑一次而对不上。
 */
const EXPORTED_TRACES: Record<string, TraceRow[]> = {}

function exportTrace(name: string): void {
  EXPORTED_TRACES[name] = trace().map((row) => ({ ...row, detail: { ...row.detail } }))
}

afterAll(async () => {
  const target = process.env.T69_TRACE_OUT
  if (!target) return
  const fs = await import('node:fs')
  fs.writeFileSync(
    target,
    JSON.stringify({ schema: 'task69-frontend-traces:v1', traces: EXPORTED_TRACES }, null, 1),
    'utf-8',
  )
})

beforeEach(() => {
  resetObservations()
})

// ═══════════════════════════════════════════════════════════════════════════
// §4 子条目 1：状态机 / 挂载 / 状态条 / 面板 / localStorage / 事件 / 双基线 /
//     shell→primary|duplicate / requested-canonical / refresh-required / close 仲裁
// ═══════════════════════════════════════════════════════════════════════════

describe('[T69-SB1] 桥状态机、宿主挂载与可见状态（独立回归）', () => {
  it('[T69-I01] 随机事件序列只能进入声明状态，非法转换抛显式码且不产出新状态', () => {
    const states = [...WP_BRIDGE_STATES] as WorkpaperSyncBridgeState[]
    const events = [...WP_BRIDGE_EVENTS] as WorkpaperSyncBridgeEvent[]
    const declared = new Set<string>(states)
    let accepted = 0
    let refused = 0
    const codes = new Set<string>()

    fc.assert(
      fc.property(
        fc.constantFrom(...states),
        fc.array(fc.constantFrom(...events), { minLength: 1, maxLength: 12 }),
        fc.constantFrom<WorkpaperSyncBridgeMode>('html', 'oo'),
        (start, sequence, startMode) => {
          let state = start
          let mode = startMode
          for (const event of sequence) {
            let next: ReturnType<typeof transitionBridgeState>
            try {
              next = transitionBridgeState(state, event, mode)
            } catch (error) {
              // 非法转换：必须是显式契约错误、必须带码，且**不返回新状态**
              expect(error).toBeInstanceOf(WorkpaperSyncContractError)
              const code = (error as WorkpaperSyncContractError).code
              expect(code.length).toBeGreaterThan(0)
              codes.add(code)
              refused += 1
              continue
            }
            expect(declared.has(next.to)).toBe(true)
            expect(next.mode === 'html' || next.mode === 'oo').toBe(true)
            state = next.to
            mode = next.mode
            accepted += 1
          }
          return true
        },
      ),
      { numRuns: 220 },
    )

    // 两边都必须非空：只有拒绝说明表太严，只有接受说明表没把住任何事
    expect(accepted).toBeGreaterThan(0)
    expect(refused).toBeGreaterThan(0)
    expect(codes.size).toBeGreaterThan(1)

    // AC 11.2 的 19 个状态逐字在域内（改名即红）
    for (const required of WP_BRIDGE_AC_11_2_REQUIRED_STATES) {
      expect(declared.has(required)).toBe(true)
    }

    // 表自证：无孤岛状态、无死端、终态真是终态
    const audit = auditBridgeMachine()
    expect(audit.unreachableStates).toEqual([])
    expect(audit.deadEndStates).toEqual([])
    expect(audit.leakyTerminals).toEqual([])
    expect(audit.undeclaredTargets).toEqual([])
    expect(audit.unusedEvents).toEqual([])
  })

  it('[T69-I02] 无 descriptor 时零 DocEditor 构造，descriptor 到位且 mode=oo 才构造恰一次', async () => {
    const harness = makeHarness()
    await flushPromises()
    expect(harness.editors).toHaveLength(0)
    expect(harness.wrapper.find('[data-testid="wp-sync-host-editor"]').exists()).toBe(false)

    await driveOpen(harness)
    expect(harness.editors).toHaveLength(1)
    expect(harness.wrapper.find('[data-testid="wp-sync-host-container"]').exists()).toBe(true)
    expect(harness.bridge.mountCallCount.value).toBe(1)
  })

  it('[T69-I03] 状态条文案是逐状态派生值而非常量，且没有一条写「同步成功」', async () => {
    const harness = makeHarness()
    const observed = new Map<string, string>()
    harness.snapshotDom('status-html-idle')
    observed.set(harness.bridge.state.value, harness.status().text)

    await driveOpen(harness)
    harness.snapshotDom('status-oo-editing')
    observed.set(harness.bridge.state.value, harness.status().text)

    respond('request_forcesave', () => acceptedWire())
    await harness.bridge.switchToHtml()
    await nextTick()
    observed.set(harness.bridge.state.value, harness.status().text)

    respond('get_operation', () =>
      operationWire({ state: 'waiting_application', durable_at: '2026-09-01T00:01:00Z' }),
    )
    await harness.bridge.refreshOperation()
    await nextTick()
    observed.set(harness.bridge.state.value, harness.status().text)

    respond('get_operation', () =>
      operationWire({
        state: 'applied',
        application_id: APPLICATION,
        durable_at: '2026-09-01T00:01:00Z',
        result_revision: 12,
      }),
    )
    await harness.bridge.refreshOperation()
    await nextTick()
    observed.set(harness.bridge.state.value, harness.status().text)

    // ≥4 个不同状态，文案两两不同（常量文案会让 size 塌成 1）
    expect(observed.size).toBeGreaterThanOrEqual(4)
    expect(new Set(observed.values()).size).toBe(observed.size)
    for (const [state, text] of observed) {
      expect(text).toBe(WP_BRIDGE_STATE_TEXT[state as WorkpaperSyncBridgeState])
    }
    // AC 11.3：四类文案分别表达，全域没有「同步成功」
    for (const text of Object.values(WP_BRIDGE_STATE_TEXT)) {
      expect(text.includes('同步成功')).toBe(false)
    }
    expect(WP_BRIDGE_STATE_TEXT.forcesave_accepted).not.toBe(WP_BRIDGE_STATE_TEXT.incoming_durable)
    expect(WP_BRIDGE_STATE_TEXT.incoming_durable).not.toBe(WP_BRIDGE_STATE_TEXT.applied)
    expect(WP_BRIDGE_STATE_TEXT.applied).not.toBe(WP_BRIDGE_STATE_TEXT.conflict)
  })

  it('[T69-I04] recovery 面板与普通重试按钮由状态门控：editing 无 recovery，recovery 期间无普通重试', async () => {
    const harness = makeHarness()
    await driveOpen(harness)
    expect(harness.wrapper.find('[data-testid="wp-sync-host-recovery"]').exists()).toBe(false)

    respond('list_recovery_cases', () => recoveryListWire())
    await harness.fireEditorError(1)
    expect(harness.bridge.state.value).toBe('recovery_pending')
    expect(harness.wrapper.find('[data-testid="wp-sync-host-recovery"]').exists()).toBe(true)
    // AC 5.8 末句：nullable-operation 的 case 不得进入普通 retry ⇒ 按钮结构性不渲染
    expect(harness.wrapper.find('[data-testid="wp-sync-host-retry"]').exists()).toBe(false)
    expect(harness.wrapper.find('[data-testid="wp-sync-host-recovery-case"]').text()).toBe(CASE)
  })

  it('[T69-I05] 旧模式键幂等迁移且按 capability 拦住不支持的存量值', () => {
    const scope = { entryId: ENTRY, wpId: WP, sheetKey: SHEET }
    const unified = workpaperSyncModeKey(scope)
    expect(unified.startsWith('workpaper-sync-mode:')).toBe(true)
    expect(unified.includes(ENTRY)).toBe(true)
    expect(unified.includes(WP)).toBe(true)
    expect(unified.includes(SHEET)).toBe(true)

    // ① 首次迁移：消费旧键、写统一键、删旧键
    const store = memoryStorage({ [`d4-dual-mode:${WP}`]: 'onlyoffice' })
    const first = migrateWorkpaperSyncMode(scope, 'bidirectional', { storage: store })
    expect(first.mode).toBe('oo')
    expect(first.consumedLegacyKeys).toEqual([`d4-dual-mode:${WP}`])
    expect(first.wroteUnifiedKey).toBe(true)
    expect(store.getItem(`d4-dual-mode:${WP}`)).toBeNull()
    expect(store.getItem(unified)).toBe('oo')

    // ② 用户在两次之间手动切回 html；第二次迁移不得覆盖
    store.setItem(unified, 'html')
    const second = migrateWorkpaperSyncMode(scope, 'bidirectional', { storage: store })
    expect(second.consumedLegacyKeys).toEqual([])
    expect(second.wroteUnifiedKey).toBe(false)
    expect(store.getItem(unified)).toBe('html')

    // ③ AC 11.8 末句：过期值不得打开不支持的模式
    const single = memoryStorage({ [`d4-dual-mode:${WP}`]: 'onlyoffice' })
    const fallback = migrateWorkpaperSyncMode(scope, 'single_html', { storage: single })
    expect(fallback.fallbackApplied).toBe(true)
    expect(fallback.mode).toBe('html')
    expect(single.getItem(unified)).toBe('html')
    expect(() => persistWorkpaperSyncMode(scope, 'single_html', 'oo', { storage: single })).toThrow(
      WorkpaperSyncContractError,
    )

    // ④ unreachable：两侧都不可用 ⇒ 不写统一键
    const dead = memoryStorage({ [`d4-dual-mode:${WP}`]: 'onlyoffice' })
    const none = migrateWorkpaperSyncMode(scope, 'unreachable', { storage: dead })
    expect(none.mode).toBeNull()
    expect(none.wroteUnifiedKey).toBe(false)
    expect(dead.getItem(unified)).toBeNull()
  })

  it('[T69-I06] 内容事件按 wp_id + revision 去重，重复投递不重复 reload', async () => {
    const reloaded: number[] = []
    const refresh = useWorkpaperContentRefresh({
      wpId: ref(WP),
      projectId: ref(PROJECT),
      loadedRevision: () => 11,
      isDirty: () => false,
      reload: async (minimum: number) => {
        reloaded.push(minimum)
      },
      subscribe: () => ({ close: () => undefined }),
    })
    const event = (revision: number, wpId = WP): Record<string, unknown> => ({
      event_type: 'workpaper.content.updated',
      extra: {
        wp_id: wpId,
        project_id: PROJECT,
        revision,
        operation_id: OPERATION,
        source: 'onlyoffice_callback',
        adapter_id: 'd4.detail',
        file_sha256: DIGEST(8),
        entry_id: ENTRY,
        content_version_id: UUID(923),
        content_revision_advanced: true,
        reason: 'application_applied',
      },
    })

    expect((await refresh.handleEvent(event(12))).kind).toBe('refreshed')
    expect((await refresh.handleEvent(event(12))).kind).toBe('duplicate')
    expect(reloaded).toEqual([12])

    // 同项目里另一个底稿的事件必然到达，不得触发本 wp 的 reload
    expect((await refresh.handleEvent(event(13, UUID(903)))).kind).toBe('other_wp')
    expect(reloaded).toEqual([12])

    // 去重键不含 operation_id：纯表示升级（operation_id=null）不得让同一 revision 投两次
    const representationOnly = event(14)
    ;(representationOnly.extra as Record<string, unknown>).operation_id = null
    ;(representationOnly.extra as Record<string, unknown>).content_revision_advanced = false
    expect((await refresh.handleEvent(representationOnly)).kind).toBe('representation_only')
    expect(reloaded).toEqual([12])
  })

  it('[T69-I07] server 与 client 两个基线是两个独立字段，且 confirm 逐项回传后者以外的身份', async () => {
    const harness = makeHarness()
    await driveOpen(harness)
    const descriptor = harness.bridge.descriptor.value
    expect(descriptor).not.toBeNull()
    expect(descriptor!.serverAppliedRevision).toBe(11)
    expect(descriptor!.clientConfirmedBaseRevision).toBe(10)
    expect(descriptor!.serverAppliedRevision).not.toBe(descriptor!.clientConfirmedBaseRevision)

    const confirm = netCalls().find((call) => call.endpoint === 'confirm_descriptor')
    expect(confirm).toBeDefined()
    const body = confirm!.body as Record<string, unknown>
    // 服务端已应用 revision 作为 `content_revision` 回传；client 基线**不**参与确认
    expect(body.content_revision).toBe(11)
    expect(Object.prototype.hasOwnProperty.call(body, 'client_confirmed_base_revision')).toBe(false)
    expect(body.doc_key).toBe('dockey-t69')
    expect(body.generation).toBe(3)
    expect(body.write_fence_epoch).toBe(5)
    expect(body.definition_bundle_sha256).toBe(DIGEST(3))
  })

  it('[T69-I08] normal accepted 之后 shell 先落 waiting_application，再按快照收敛为 primary 或 terminal duplicate', async () => {
    // ── primary 支
    const primary = makeHarness()
    await driveOpen(primary)
    respond('request_forcesave', () => acceptedWire())
    await primary.bridge.switchToHtml()
    expect(primary.bridge.state.value).toBe('waiting_application')
    expect(primary.bridge.requestedOperationId.value).toBe(OPERATION)
    expect(primary.bridge.mode.value).toBe('oo')
    // HTTP 202 之后 application 尚不存在
    expect(primary.bridge.canonicalApplicationId.value).toBeNull()

    respond('get_operation', () =>
      operationWire({ state: 'application_bound', application_id: APPLICATION, durable_at: '2026-09-01T00:01:00Z' }),
    )
    await primary.bridge.refreshOperation()
    expect(primary.bridge.state.value).toBe('application_bound')
    expect(primary.bridge.canonicalApplicationId.value).toBe(APPLICATION)

    // ── duplicate 支（独立一趟，证明同一入口两种终态都可达）
    resetObservations()
    const dup = makeHarness()
    await driveOpen(dup)
    respond('request_forcesave', () => acceptedWire())
    await dup.bridge.switchToHtml()
    respond('get_operation', () =>
      operationWire({
        state: 'duplicate',
        duplicate_of_operation_id: PRIMARY_OPERATION,
        canonical_operation_id: PRIMARY_OPERATION,
        followed_duplicate: true,
      }),
    )
    await dup.bridge.refreshOperation()
    expect(dup.bridge.state.value).toBe('duplicate')
    expect(dup.bridge.operation.value!.shape).toBe('duplicate')
    // terminal：再来一份快照也不改状态
    await dup.bridge.refreshOperation()
    expect(dup.bridge.state.value).toBe('duplicate')
  })

  it('[T69-I09] duplicate 之后所有后续调用仍按 requested id 发起，canonical 只作显示', async () => {
    const harness = makeHarness()
    await driveOpen(harness)
    respond('request_forcesave', () => acceptedWire())
    await harness.bridge.switchToHtml()
    respond('get_operation', () =>
      operationWire({
        state: 'duplicate',
        duplicate_of_operation_id: PRIMARY_OPERATION,
        canonical_operation_id: PRIMARY_OPERATION,
        followed_duplicate: true,
      }),
    )
    respond('get_operation_conflicts', () => ({
      canonical_application_id: APPLICATION,
      incoming_sequence: 7,
      groups: [],
    }))
    respond('get_operation_timeline', () => ({ events: [] }))
    respond('retry_operation', () => ({ state: 'accepted' }))

    await harness.bridge.refreshOperation()
    await harness.bridge.fetchConflicts()
    await harness.bridge.fetchTimeline()
    await harness.bridge.retryOperation()

    const followUps = netCalls().filter((call) =>
      ['get_operation', 'get_operation_conflicts', 'get_operation_timeline', 'retry_operation'].includes(
        call.endpoint,
      ),
    )
    expect(followUps.length).toBeGreaterThanOrEqual(4)
    for (const call of followUps) {
      expect(call.url.includes(`/operations/${OPERATION}`)).toBe(true)
      expect(call.url.includes(PRIMARY_OPERATION)).toBe(false)
    }
    // canonical 仍然保留在投影里（UI 要说明「折叠到了哪一次」）
    expect(harness.bridge.operation.value!.canonicalOperationId).toBe(PRIMARY_OPERATION)
    expect(harness.bridge.operation.value!.requestedOperationId).toBe(OPERATION)
  })

  it('[T69-I10] refresh-required reopen：转换表有 rematerializing 路径，但桥没有任何公开动作能走上去（如实登记，不假绿）', async () => {
    // ── 表侧：路径确实声明了
    expect(transitionBridgeState('refresh_required', 'descriptor_received', 'oo').to).toBe(
      'rematerializing',
    )
    expect(transitionBridgeState('rematerializing', 'descriptor_accepted', 'oo').to).toBe(
      'oo_loading',
    )

    const harness = makeHarness()
    await driveOpen(harness)
    const firstPlaceholder = harness.editors[0].placeholderId

    respond('request_forcesave', () => acceptedWire())
    await harness.bridge.switchToHtml()
    respond('get_operation', () => operationWire({ state: 'refresh_required' }))
    await harness.bridge.refreshOperation()
    expect(harness.bridge.state.value).toBe('refresh_required')
    expect(harness.status().text).toBe(WP_BRIDGE_STATE_TEXT.refresh_required)

    // ── 运行时侧：唯一会 apply `descriptor_received` 的公开动作是 `switchToOnlyOffice()`，
    // 而它第一步就 apply `flush_started` —— `refresh_required` 没有这条出边。
    // 于是 `rematerializing` 在运行时**不可达**：reopen 只能靠整页重挂。
    const before = netCalls().length
    await expect(harness.bridge.switchToOnlyOffice()).rejects.toThrow(WorkpaperSyncContractError)
    expect(harness.bridge.state.value).toBe('refresh_required')
    expect(netCalls().length).toBe(before)

    // ── DOM 侧后果：此刻直接推一份新 descriptor，宿主会挂新编辑器但桥拒绝该转换，
    // 于是必须显式失败（不得静默留下一个「桥不知道存在」的编辑器实例）。
    const reopened = descriptorWire({
      generation: 4,
      representation_generation: 3,
      doc_key: 'dockey-t69-g4',
      room_id: ROOM,
    })
    respond('materialize', () => reopened)
    respond('create_pending_mutation', () => pendingWire({ expected_revision: 12 }))
    const parsed = await syncApi
      .materialize(
        { projectId: PROJECT, wpId: WP, entryId: ENTRY },
        {
          sheetKey: SHEET,
          expectedRevision: 12,
          pendingMutationToken: 'pmt-t69',
          projection: { rows: [] },
        },
      )
    await harness.wrapper.setProps({ descriptor: parsed })
    await flushPromises()
    await nextTick()

    expect(harness.destroyed).toContain(firstPlaceholder)
    expect(harness.editors).toHaveLength(2)
    expect(harness.editors[1].placeholderId).not.toBe(firstPlaceholder)
    expect((harness.editors[1].config.document as Record<string, unknown>).key).toBe('dockey-t69')
    // 桥拒绝 `editor_mounted` ⇒ 宿主把它记成可见失败
    const hostError = harness.wrapper.find('[data-testid="wp-sync-host-error"]')
    expect(hostError.exists()).toBe(true)
    const errorEmits = trace().filter((row) => row.kind === 'emit' && row.name === 'error')
    expect(errorEmits.some((row) => row.detail.stage === 'notify_editor_mounted')).toBe(true)
    expect(harness.status().kind).toBe('error')
  })

  it('[T69-I11] close leader 失权先显示 close_authorization_stale；有合法 successor 才继续，无 successor 进 close_recovery_required 并停止 loading', async () => {
    const withSuccessor = makeHarness()
    await driveOpen(withSuccessor)
    withSuccessor.bridge.notifyCloseAuthorizationLost()
    await nextTick()
    expect(withSuccessor.bridge.state.value).toBe('close_authorization_stale')
    expect(withSuccessor.status().text).toBe(WP_BRIDGE_STATE_TEXT.close_authorization_stale)
    expect(withSuccessor.status().kind).not.toBe('success')

    // 缺 successor intent id 时不得渲染成保存成功
    expect(() => withSuccessor.bridge.notifyCloseSuccessorApplied('')).toThrow(
      WorkpaperSyncContractError,
    )
    expect(withSuccessor.bridge.state.value).toBe('close_authorization_stale')

    // 合法 successor 接任：generation 不变（descriptor 身份未换）
    const generationBefore = withSuccessor.bridge.descriptor.value!.generation
    withSuccessor.bridge.notifyCloseSuccessorApplied(UUID(960))
    await nextTick()
    expect(withSuccessor.bridge.state.value).toBe('applied')
    expect(withSuccessor.bridge.descriptor.value!.generation).toBe(generationBefore)

    // ── 无 successor 支
    resetObservations()
    const noSuccessor = makeHarness()
    await driveOpen(noSuccessor)
    noSuccessor.bridge.notifyCloseAuthorizationLost()
    noSuccessor.bridge.notifyCloseNoSuccessor()
    await nextTick()
    expect(noSuccessor.bridge.state.value).toBe('close_recovery_required')
    expect(noSuccessor.status().text).toBe(WP_BRIDGE_STATE_TEXT.close_recovery_required)
    expect(noSuccessor.status().kind).toBe('progress')
    // 「停止 loading」的可观测含义：不在 in-flight 集合里 ⇒ 可以离开
    expect(noSuccessor.bridge.canLeave.value).toBe(true)
    expect(noSuccessor.bridge.leaveBlockReason.value).toBeNull()
    // 禁止成功文案
    expect(noSuccessor.status().text).not.toBe(WP_BRIDGE_STATE_TEXT.applied)
  })

  it('[T69-I12] flush 失败时 materialize 调用次数与编辑器挂载次数均为 0（Property 8）', async () => {
    const harness = makeHarness({
      flushHtml: async () => {
        throw new Error('[T69] 表单 flush 失败')
      },
    })
    respond('create_pending_mutation', () => pendingWire())
    respond('materialize', () => descriptorWire())
    await expect(harness.bridge.switchToOnlyOffice()).rejects.toThrow()
    await flushPromises()

    expect(netCalls().filter((call) => call.endpoint === 'materialize')).toHaveLength(0)
    expect(netCalls().filter((call) => call.endpoint === 'create_pending_mutation')).toHaveLength(0)
    expect(harness.editors).toHaveLength(0)
    expect(harness.bridge.mountCallCount.value).toBe(0)
    expect(harness.bridge.mode.value).toBe('html')
    expect(harness.status().kind).toBe('error')
  })

  it('[T69-I13] callback 超时保持 OO：mode 不变、错误可见、可重试、reloadHtml 调用次数为 0（Property 13）', async () => {
    const harness = makeHarness()
    await driveOpen(harness)
    respond('request_forcesave', () => acceptedWire())
    await harness.bridge.switchToHtml()

    // 超时形态：无响应体、无 error_code
    respond('get_operation', () => new Error('timeout of 30000ms exceeded'))
    await expect(harness.bridge.refreshOperation()).rejects.toThrow()
    await nextTick()

    expect(harness.bridge.mode.value).toBe('oo')
    expect(harness.status().kind).toBe('error')
    expect(harness.bridge.lastError.value!.verdict.retryableOperation).toBe(true)
    expect(harness.reloads).toEqual([])
    expect(harness.wrapper.find('[data-testid="wp-sync-host-retry"]').exists()).toBe(true)
  })

  it('[T69-I14] applied 之后按 result revision 重载，且 pre-bind shell 不得伪造 result revision（Property 14）', async () => {
    const harness = makeHarness()
    await driveOpen(harness)
    respond('request_forcesave', () => acceptedWire())
    await harness.bridge.switchToHtml()

    respond('get_operation', () =>
      operationWire({
        state: 'applied',
        application_id: APPLICATION,
        durable_at: '2026-09-01T00:01:00Z',
        result_revision: 12,
      }),
    )
    await harness.bridge.refreshOperation()
    expect(harness.bridge.state.value).toBe('applied')
    await harness.bridge.reloadAfterApplied()
    expect(harness.reloads).toEqual([12])
    expect(harness.reloads[0]).toBeGreaterThanOrEqual(12)

    // pre-bind shell 带 result_revision ⇒ 显式拒绝（不得读成已完成）
    expect(() =>
      harness.bridge.projectOperation({
        requestedOperationId: OPERATION,
        canonicalOperationId: OPERATION,
        followedDuplicate: false,
        state: 'accepted',
        shape: 'pre_correlation',
        applicationId: null,
        duplicateOfOperationId: null,
        errorCode: null,
        errorStage: null,
        acceptedAt: null,
        applicationBoundAt: null,
        operationFinishedAt: null,
        resultRevision: 99,
        conflictCount: null,
        logicalResultCode: null,
        definitionBundleId: null,
        definitionBundleSha256: null,
        authorityModelDefinitionSha256: null,
        durableAt: null,
        finishedAt: null,
        terminal: false,
      }),
    ).toThrow(/bridge_pre_bind_result_revision|pre-bind/)
  })

  it('[T69-I33] 冲突面板逐项渲染 JSON Pointer / OO 位置 / 三方值 / kind，四者均非空（Property 35）', async () => {
    const harness = makeHarness()
    await driveOpen(harness)
    respond('request_forcesave', () => acceptedWire())
    await harness.bridge.switchToHtml()
    respond('get_operation', () =>
      operationWire({
        state: 'conflict',
        application_id: APPLICATION,
        durable_at: '2026-09-01T00:01:00Z',
        conflict_count: 1,
      }),
    )
    await harness.bridge.refreshOperation()
    expect(harness.bridge.state.value).toBe('conflict')

    respond('get_operation_conflicts', () => conflictPreviewWire())
    const dialog = mount(WorkpaperSyncConflictDialog, {
      props: {
        bridge: harness.bridge,
        visible: true,
        roomDurableFence: {
          latestDurableApplicationId: APPLICATION,
          latestDurableSequence: 7,
        },
      },
    })
    await flushPromises()
    await nextTick()

    const items = dialog.findAll('[data-testid="wp-sync-conflict-item"]')
    expect(items.length).toBe(1)
    for (const testid of [
      'wp-sync-conflict-item-pointer',
      'wp-sync-conflict-item-oo',
      'wp-sync-conflict-item-base',
      'wp-sync-conflict-item-current',
      'wp-sync-conflict-item-incoming',
      'wp-sync-conflict-item-label',
    ]) {
      const node = dialog.find(`[data-testid="${testid}"]`)
      expect(node.exists()).toBe(true)
      expect(node.text().trim().length).toBeGreaterThan(0)
    }
    // JSON Pointer 与 OO 位置必须是两个不同的定位面（压成一个就失去双侧可追溯）
    const pointer = dialog.find('[data-testid="wp-sync-conflict-item-pointer"]').text()
    const ooLocation = dialog.find('[data-testid="wp-sync-conflict-item-oo"]').text()
    expect(pointer).not.toBe(ooLocation)
    expect(pointer.includes('/rows/0/amount')).toBe(true)
    expect(ooLocation.includes('D7')).toBe(true)
    // 三方值两两不同（同值会让「选哪一侧」失去意义）
    const three = [
      dialog.find('[data-testid="wp-sync-conflict-item-base"]').text(),
      dialog.find('[data-testid="wp-sync-conflict-item-current"]').text(),
      dialog.find('[data-testid="wp-sync-conflict-item-incoming"]').text(),
    ]
    expect(new Set(three).size).toBe(3)
    // 关闭面板不得自动应用任何一侧（AC 11.7）
    const before = netCalls().length
    await dialog.find('[data-testid="wp-sync-conflict-close"]').trigger('click')
    await flushPromises()
    expect(netCalls().filter((call) => call.endpoint === 'resolve_conflicts')).toHaveLength(0)
    expect(netCalls().length).toBe(before)
    dialog.unmount()
  })

  it('[T69-I15] 确认失败（forcesave 未解锁）不得进入 editing，也不得解锁保存（Property 11 后半 / Property 15）', async () => {
    const harness = makeHarness()
    respond('create_pending_mutation', () => pendingWire())
    respond('materialize', () => descriptorWire())
    respond('confirm_descriptor', () => confirmationWire({ forcesave_unlocked: false }))
    const descriptor = await harness.bridge.switchToOnlyOffice()
    await harness.wrapper.setProps({ descriptor })
    await flushPromises()
    await harness.fireDocumentReady()

    expect(harness.bridge.state.value).not.toBe('oo_editing')
    expect(harness.bridge.canForcesave.value).toBe(false)
    expect(harness.status().kind).toBe('error')
    // 确认失败把 mode 打回 html ⇒ 宿主必须收回编辑器（DOM 上不可达「确认失败仍 editing」）
    expect(harness.bridge.mode.value).toBe('html')
    expect(harness.wrapper.find('[data-testid="wp-sync-host-editor"]').exists()).toBe(false)
    // 程序化调用 forceSave 也必须 fail visible
    const exposed = harness.wrapper.vm as unknown as { forceSave: () => Promise<unknown> }
    await expect(exposed.forceSave()).rejects.toThrow()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// §5 子条目 2：显式 scope / opaque versionId / 不泄露 / 三实体
// ═══════════════════════════════════════════════════════════════════════════

describe('[T69-SB2] 显式 scope、opaque 定位与 recovery 三实体（独立回归）', () => {
  it('[T69-I16] 每一个真实发出的请求都显式携带 project/wp/entry；缺任一段在发出前被拒且零调用', async () => {
    const harness = makeHarness()
    await driveOpen(harness)
    respond('request_forcesave', () => acceptedWire())
    await harness.bridge.switchToHtml()
    respond('get_operation', () => operationWire())
    await harness.bridge.refreshOperation()
    respond('list_recovery_cases', () => recoveryListWire())
    // 直接经 API 层：本判据只关心真实 URL 的三段 scope，不需要把桥推进 recovery 状态
    await syncApi.listRecoveryCases(
      { projectId: PROJECT, wpId: WP, entryId: ENTRY },
      { roomId: ROOM, generation: 3 },
    )

    const calls = netCalls()
    expect(calls.length).toBeGreaterThanOrEqual(6)
    for (const call of calls) {
      expect(call.endpoint).not.toBe('UNKNOWN')
      expect(call.url.startsWith(SCOPE_PREFIX)).toBe(true)
      expect(call.url.includes(`/projects/${PROJECT}/`)).toBe(true)
      expect(call.url.includes(`/workpapers/${WP}/`)).toBe(true)
      expect(call.url.includes(`/entries/${ENTRY}`)).toBe(true)
      // entry_id 的 `/` 必须原样进 URL（percent-encode 后 Starlette 解出的值不等于原值）
      expect(call.url.includes('%2F')).toBe(false)
    }

    // 反事实臂：三段各缺一次，都必须在**发出前**拒绝且不新增任何调用
    for (const broken of [
      { projectId: '', wpId: WP, entryId: ENTRY },
      { projectId: PROJECT, wpId: '   ', entryId: ENTRY },
      { projectId: PROJECT, wpId: WP, entryId: '' },
    ]) {
      const before = netCalls().length
      await expect(syncApi.getOperation(broken, OPERATION)).rejects.toThrow(
        WorkpaperSyncContractError,
      )
      expect(netCalls().length).toBe(before)
    }
  })

  it('[T69-I17] recovery list 另带 room_id 与 generation，缺任一项在发出前被拒', async () => {
    respond('list_recovery_cases', () => recoveryListWire())
    const scope = { projectId: PROJECT, wpId: WP, entryId: ENTRY }
    await syncApi.listRecoveryCases(scope, { roomId: ROOM, generation: 3 })
    const call = netCalls().find((row) => row.endpoint === 'list_recovery_cases')
    expect(call).toBeDefined()
    expect(call!.params).toEqual({ room_id: ROOM, generation: 3 })

    for (const broken of [
      { roomId: '', generation: 3 },
      { roomId: ROOM, generation: Number.NaN },
    ]) {
      const before = netCalls().length
      await expect(syncApi.listRecoveryCases(scope, broken as never)).rejects.toThrow(
        WorkpaperSyncContractError,
      )
      expect(netCalls().length).toBe(before)
    }
  })

  it('[T69-I18] rollback 只接受 opaque versionId 并保留 entry scope；numeric revision 不得拼 route', async () => {
    respond('rollback_version', () => ({ state: 'applied', revision: 13 }))
    const scope = { projectId: PROJECT, wpId: WP, entryId: ENTRY }
    const versionId = '3f2504e0-4f89-11d3-9a0c-0305e82c3301'
    await syncApi.rollbackVersion(scope, {
      versionId,
      expectedCurrentRevision: 12,
      confirmed: true,
    })
    const call = netCalls().find((row) => row.endpoint === 'rollback_version')
    expect(call).toBeDefined()
    expect(call!.url).toBe(`${SCOPE_PREFIX}/versions/${versionId}/rollback`)
    expect((call!.body as Record<string, unknown>).expected_current_revision).toBe(12)

    // numeric revision / 全零 UUID / 缺二次确认：三条各自在发出前被拒，零新增调用
    for (const broken of [
      { versionId: '12', expectedCurrentRevision: 12, confirmed: true },
      { versionId: '00000000-0000-0000-0000-000000000000', expectedCurrentRevision: 12, confirmed: true },
      { versionId, expectedCurrentRevision: 12, confirmed: false },
    ]) {
      const before = netCalls().length
      await expect(syncApi.rollbackVersion(scope, broken)).rejects.toThrow(
        WorkpaperSyncContractError,
      )
      expect(netCalls().length).toBe(before)
    }
  })

  it('[T69-I19] 统一 404 与 403 归一成同一个不泄露码，且文案不含被访问对象的标识', async () => {
    const seen: { status: number; code: string; message: string }[] = []
    for (const status of [404, 403] as const) {
      resetObservations()
      const harness = makeHarness()
      await driveOpen(harness)
      respond('request_forcesave', () => acceptedWire())
      await harness.bridge.switchToHtml()
      respond('get_operation', () => unifiedRefusal(status))
      await expect(harness.bridge.refreshOperation()).rejects.toThrow()
      const error = harness.bridge.lastError.value!
      seen.push({ status, code: error.errorCode, message: error.message })
      expect(error.verdict.retryableOperation).toBe(false)
      expect(error.message.includes(OPERATION)).toBe(false)
      expect(error.message.includes(ROOM)).toBe(false)
      expect(error.message.includes(WP)).toBe(false)
    }
    // 两个状态码在 UI 上不可区分（区分开就是存在性泄露）
    expect(seen[0].code).toBe(seen[1].code)
    expect(seen[0].message).toBe(seen[1].message)
    // 但与「本地/传输失败」必须可区分（后者可重试）
    resetObservations()
    const local = makeHarness()
    await driveOpen(local)
    respond('request_forcesave', () => acceptedWire())
    await local.bridge.switchToHtml()
    respond('get_operation', () => new Error('socket hang up'))
    await expect(local.bridge.refreshOperation()).rejects.toThrow()
    expect(local.bridge.lastError.value!.errorCode).not.toBe(seen[0].code)
  })

  it('[T69-I20] browser crash 进入 recovery_pending，claim 前 request/application/operation 均为空', async () => {
    const harness = makeHarness()
    await driveOpen(harness)
    respond('list_recovery_cases', () => recoveryListWire())
    await harness.fireEditorError(1)

    expect(harness.bridge.state.value).toBe('recovery_pending')
    const listed = harness.bridge.recoveryCases.value
    expect(listed).toHaveLength(1)
    assertThreeEntitiesZero('crash recovery case', {
      forcesaveRequestId: listed[0].forcesaveRequestId,
      applicationId: listed[0].applicationId,
      operationId: listed[0].operationId,
    })
    expect(harness.bridge.requestedOperationId.value).toBeNull()
    expect(harness.bridge.canonicalApplicationId.value).toBeNull()
    // recoveryCase emit 载荷里结构性没有 operation id
    const emitted = trace().find((row) => row.kind === 'emit' && row.name === 'recovery-case')
    expect(emitted).toBeDefined()
    expect(Object.keys(emitted!.detail).sort()).toEqual(['caseId', 'reason'])
    exportTrace('crash_recovery')

    // 反事实臂：同一个判据喂一个带 operation 的三实体必须抛
    expect(() =>
      assertThreeEntitiesZero('fabricated', {
        forcesaveRequestId: null,
        applicationId: null,
        operationId: OPERATION,
      }),
    ).toThrow(/三者全空/)

    // 服务端若真返回带三实体的 unclaimed case，DTO 必须 fail visible
    respond('list_recovery_cases', () => recoveryListWire([recoveryCaseWire({ operation_id: OPERATION })]))
    await expect(harness.bridge.listRecoveryCases({ roomId: ROOM, generation: 3 })).rejects.toThrow(
      /recovery_case_premature_entities|claim 成功前/,
    )
  })

  it('[T69-I21] claim 仅在成功后同时关联三实体；四类错误前置各自失败且三者仍为 0', async () => {
    const claimInput = {
      caseId: CASE,
      roomId: ROOM,
      participantId: PARTICIPANT,
      priorConfirmationId: CONFIRMATION,
      expectedGeneration: 3,
      expectedWriteFence: 5,
      expectedDefinitionBundleSha256: DIGEST(3),
      expectedCurrentRevision: 12,
    }

    // ── 成功支
    const ok = makeHarness()
    await driveOpen(ok)
    respond('list_recovery_cases', () => recoveryListWire())
    await ok.fireEditorError(1)
    respond('claim_recovery_case', () => ({
      case_id: CASE,
      forcesave_request_id: REQUEST,
      operation_id: OPERATION,
      application_id: APPLICATION,
      state: 'application_created',
    }))
    respond('get_operation', () =>
      operationWire({ state: 'application_bound', application_id: APPLICATION }),
    )
    await ok.bridge.claimRecoveryCase(claimInput)
    expect(ok.bridge.state.value).toBe('application_bound')
    expect(ok.bridge.requestedOperationId.value).toBe(OPERATION)
    expect(ok.bridge.canonicalApplicationId.value).toBe(APPLICATION)
    // claim 的请求体是白名单构造：客户端不得指定任意 base/bundle 内容
    const claimCall = netCalls().find((row) => row.endpoint === 'claim_recovery_case')!
    expect(Object.keys(claimCall.body as Record<string, unknown>).sort()).toEqual([
      'expected_current_revision',
      'expected_definition_bundle_sha256',
      'expected_generation',
      'expected_write_fence',
      'participant_id',
      'prior_confirmation_id',
      'room_id',
    ])
    // 顺序：list 必须早于 claim，claim 必须早于形态探针
    assertOrder(trace(), ['net:list_recovery_cases', 'net:claim_recovery_case', 'net:get_operation'])
    exportTrace('recovery_claim')
    // 反事实臂：list 与 claim 交换 ⇒ 同一判据必须抛
    expect(() =>
      assertOrder(swapped(trace(), 'net:list_recovery_cases', 'net:claim_recovery_case'), [
        'net:list_recovery_cases',
        'net:claim_recovery_case',
      ]),
    ).toThrow(/顺序违反/)

    // ── 四类错误：prior confirmation / bundle / fence / contributor
    const errorArms: { label: string; run: (h: Harness) => Promise<unknown> }[] = [
      {
        label: 'prior_confirmation',
        run: (h) => h.bridge.claimRecoveryCase({ ...claimInput, priorConfirmationId: UUID(999) }),
      },
      {
        label: 'bundle',
        run: (h) =>
          h.bridge.claimRecoveryCase({ ...claimInput, expectedDefinitionBundleSha256: 'not-a-digest' }),
      },
      {
        label: 'fence',
        run: (h) => h.bridge.claimRecoveryCase({ ...claimInput, expectedWriteFence: -1 }),
      },
      {
        label: 'contributor',
        run: (h) => {
          respond('claim_recovery_case', () =>
            codedFailure(409, 'recovery_claim_contributor_snapshot_mismatch'),
          )
          return h.bridge.claimRecoveryCase(claimInput)
        },
      },
    ]
    const codes = new Set<string>()
    for (const arm of errorArms) {
      resetObservations()
      const harness = makeHarness()
      await driveOpen(harness)
      respond('list_recovery_cases', () => recoveryListWire())
      await harness.fireEditorError(1)
      await expect(arm.run(harness)).rejects.toThrow()
      codes.add(harness.bridge.lastError.value?.errorCode ?? `local:${arm.label}`)
      // 三实体仍为 0
      expect(harness.bridge.requestedOperationId.value).toBeNull()
      expect(harness.bridge.canonicalApplicationId.value).toBeNull()
      expect(netCalls().filter((row) => row.endpoint === 'get_operation')).toHaveLength(0)
      expect(['recovery_pending', 'error']).toContain(harness.bridge.state.value)
    }
    // 四臂拒绝理由必须互不命中（共用一个码会让其中三条永远不可达）
    expect(codes.size).toBeGreaterThanOrEqual(3)
  })

  it('[T69-I22] download-only 三实体为 0、不显示回写成功，且不打任何创建型端点', async () => {
    const harness = makeHarness()
    await driveOpen(harness)
    respond('list_recovery_cases', () => recoveryListWire())
    await harness.fireEditorError(1)
    const before = netCalls().length

    respond('terminate_recovery_download_only', () => ({
      case_id: CASE,
      state: 'download_only',
      download_claim: 'dl-claim-t69',
      expires_in_seconds: 300,
    }))
    const claim = await harness.bridge.terminateRecoveryDownloadOnly(CASE)
    await nextTick()
    expect(claim).toBe('dl-claim-t69')
    expect(harness.bridge.state.value).toBe('recovery_download_only')

    assertThreeEntitiesZero('download-only', {
      forcesaveRequestId: null,
      applicationId: harness.bridge.canonicalApplicationId.value,
      operationId: harness.bridge.requestedOperationId.value,
    })
    const after = netCalls().slice(before)
    assertEndpointMultiset(after, ['terminate_recovery_download_only'])
    // 顺序：list → download-only
    assertOrder(trace(), ['net:list_recovery_cases', 'net:terminate_recovery_download_only'])
    exportTrace('recovery_download_only')
    expect(() =>
      assertOrder(
        swapped(trace(), 'net:list_recovery_cases', 'net:terminate_recovery_download_only'),
        ['net:list_recovery_cases', 'net:terminate_recovery_download_only'],
      ),
    ).toThrow(/顺序违反/)
    // 不显示回写成功
    expect(harness.status().kind).not.toBe('success')
    expect(harness.status().text).toBe(WP_BRIDGE_STATE_TEXT.recovery_download_only)
    expect(harness.status().text).not.toBe(WP_BRIDGE_STATE_TEXT.applied)

    // 服务端若在 download-only 回执里塞三实体或 applied，DTO 必须 fail visible
    respond('terminate_recovery_download_only', () => ({
      case_id: CASE,
      state: 'download_only',
      download_claim: 'dl-claim-t69',
      expires_in_seconds: 300,
      operation_id: OPERATION,
    }))
    await expect(
      syncApi.terminateRecoveryDownloadOnly({ projectId: PROJECT, wpId: WP, entryId: ENTRY }, CASE),
    ).rejects.toThrow(/download_only_fabricated_entities|永不创建/)
  })

  it('[T69-I23] 普通 retry 拒绝空 operation：桥与 API 层各有自己的码，且零网络调用', async () => {
    const harness = makeHarness()
    await driveOpen(harness)
    respond('list_recovery_cases', () => recoveryListWire())
    await harness.fireEditorError(1)
    const before = netCalls().length

    // 桥层：没有 requested operation
    const bridgeError = await harness.bridge.retryOperation().catch((error) => error)
    expect(bridgeError).toBeInstanceOf(WorkpaperSyncContractError)
    const bridgeCode = (bridgeError as WorkpaperSyncContractError).code
    expect(bridgeCode).toBe('bridge_no_requested_operation')

    // API 层：显式传空串
    const apiError = await syncApi
      .retryOperation({ projectId: PROJECT, wpId: WP, entryId: ENTRY }, '')
      .catch((e) => e)
    expect(apiError).toBeInstanceOf(WorkpaperSyncContractError)
    expect(apiError.code).toBe('retry_requires_operation')
    expect(apiError.code).not.toBe(bridgeCode)

    expect(netCalls().length).toBe(before)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// §6 子条目 3：DOM/network 顺序 + 五条「立即失败」
// ═══════════════════════════════════════════════════════════════════════════

describe('[T69-SB3] DOM/network 顺序与五条立即失败判据（独立回归）', () => {
  it('[T69-I24] descriptor 链路的真实顺序是 mount → ready → confirm，顺序被交换时同一判据必须抛', async () => {
    const harness = makeHarness()
    await driveOpen(harness)
    harness.snapshotDom('after-confirm')

    const rows = trace()
    assertOrder(rows, [
      'net:create_pending_mutation',
      'net:materialize',
      'editor:doc-editor-constructed',
      'emit:ready',
      'net:confirm_descriptor',
      'dom:after-confirm',
    ])
    exportTrace('descriptor_open')
    expect(harness.bridge.state.value).toBe('oo_editing')
    expect(harness.wrapper.find('[data-testid="wp-sync-host-mask"]').exists()).toBe(false)
    expect(harness.wrapper.find('[data-testid="wp-sync-host-forcesave"]').attributes('disabled')).toBeUndefined()

    // 反事实臂 ①：confirm 与 ready 交换
    expect(() =>
      assertOrder(swapped(rows, 'emit:ready', 'net:confirm_descriptor'), [
        'editor:doc-editor-constructed',
        'emit:ready',
        'net:confirm_descriptor',
      ]),
    ).toThrow(/顺序违反/)
    // 反事实臂 ②：mount 与 materialize 交换
    expect(() =>
      assertOrder(swapped(rows, 'net:materialize', 'editor:doc-editor-constructed'), [
        'net:materialize',
        'editor:doc-editor-constructed',
      ]),
    ).toThrow(/顺序违反/)
    // 反事实臂 ③：缺项也必须抛（不能把「没观测到」当成「顺序对」）
    expect(() => assertOrder(rows, ['net:materialize', 'net:never_happens'])).toThrow(/缺/)
  })

  it('[T69-I25] 已挂载但服务端未确认时：遮罩在位、保存按钮 disabled、程序化 forceSave 仍 fail visible', async () => {
    const harness = makeHarness()
    respond('create_pending_mutation', () => pendingWire())
    respond('materialize', () => descriptorWire())
    const descriptor = await harness.bridge.switchToOnlyOffice()
    await harness.wrapper.setProps({ descriptor })
    await flushPromises()
    await nextTick()

    // 已挂载（DocEditor 真的构造了）但 `onDocumentReady` 尚未触发
    expect(harness.editors).toHaveLength(1)
    expect(harness.bridge.state.value).toBe('descriptor_mounted')
    expect(harness.wrapper.find('[data-testid="wp-sync-host-mask"]').exists()).toBe(true)
    expect(
      harness.wrapper.find('[data-testid="wp-sync-host-forcesave"]').attributes('disabled'),
    ).toBeDefined()
    expect(harness.bridge.canForcesave.value).toBe(false)

    // 按钮虽 disabled，程序化调用也必须可见失败（0 次 forcesave 网络调用）
    const before = netCalls().length
    const exposed = harness.wrapper.vm as unknown as { forceSave: () => Promise<unknown> }
    await expect(exposed.forceSave()).rejects.toThrow(WorkpaperSyncContractError)
    expect(netCalls().length).toBe(before)
    expect(
      harness.wrapper.find('[data-testid="wp-sync-host-error"]').attributes('data-code'),
    ).toBe('editor_host_forcesave_before_confirmation')
    // 这一步刻意**不**上报给桥：一次早点击不得把正在飞行的确认推成 error
    expect(harness.bridge.state.value).toBe('descriptor_mounted')

    // ready → confirm 成功之后才解锁
    respond('confirm_descriptor', () => confirmationWire())
    await harness.fireDocumentReady()
    expect(harness.bridge.state.value).toBe('oo_editing')
    expect(harness.bridge.canForcesave.value).toBe(true)
    expect(harness.wrapper.find('[data-testid="wp-sync-host-mask"]').exists()).toBe(false)
  })

  it('[T69-I26] 立即失败①：prop 名写错时零挂载；expose 的 forceSave/getSyncState 必须真实存在且可调用', async () => {
    // 传一个**不存在**的 prop 名（Vue 里这是静默失效，只有真实挂载才暴露）
    const wrong = makeHarness({ descriptorPropName: 'launchDescriptor' })
    respond('create_pending_mutation', () => pendingWire())
    respond('materialize', () => descriptorWire())
    respond('confirm_descriptor', () => confirmationWire())
    const descriptor = await wrong.bridge.switchToOnlyOffice()
    await wrong.wrapper.setProps({ launchDescriptor: descriptor } as never)
    await flushPromises()
    await nextTick()
    expect(wrong.editors).toHaveLength(0)
    expect(wrong.wrapper.find('[data-testid="wp-sync-host-editor"]').exists()).toBe(false)

    // 对照组：正确 prop 名 ⇒ 真的挂载（证明上面的零挂载不是「什么都跑不起来」）
    resetObservations()
    const right = makeHarness()
    await driveOpen(right)
    expect(right.editors).toHaveLength(1)

    // expose 必须是真函数且真能跑
    const exposed = right.wrapper.vm as unknown as {
      forceSave?: unknown
      getSyncState?: unknown
    }
    expect(typeof exposed.forceSave).toBe('function')
    expect(typeof exposed.getSyncState).toBe('function')
    const snapshot = (exposed.getSyncState as () => Record<string, unknown>)()
    expect(snapshot.editorMounted).toBe(true)
    expect(snapshot.state).toBe('oo_editing')
    expect(snapshot.canForcesave).toBe(true)
    expect((exposed as { nonExistentApi?: unknown }).nonExistentApi).toBeUndefined()

    respond('request_forcesave', () => acceptedWire())
    const result = await (exposed.forceSave as () => Promise<{ operationId: string }>)()
    expect(result.operationId).toBe(OPERATION)
    const saveEmit = trace().find((row) => row.kind === 'emit' && row.name === 'save-requested')
    expect(saveEmit!.detail).toEqual({ operationId: OPERATION })
  })

  it('[T69-I27] 立即失败②：editor 不自行取 config —— 整趟端点多重集恰为三项，且交给 DocEditor 的 config 只多出 width/height/events', async () => {
    const harness = makeHarness()
    await driveOpen(harness)

    // 真实网络：整趟只有三次调用，多打一次 config 会让等值判据立刻红
    assertEndpointMultiset(netCalls(), ['create_pending_mutation', 'materialize', 'confirm_descriptor'])
    // 反事实臂：合成一次多余的 config 请求，同一判据必须抛
    expect(() =>
      assertEndpointMultiset(
        [...netCalls(), { ...netCalls()[1], endpoint: 'materialize' }],
        ['create_pending_mutation', 'materialize', 'confirm_descriptor'],
      ),
    ).toThrow(/端点多重集/)

    const config = harness.editors[0].config
    const descriptor = harness.bridge.descriptor.value!
    const source = descriptor.onlyofficeConfig as Record<string, unknown>
    const extra = Object.keys(config).filter((key) => !Object.prototype.hasOwnProperty.call(source, key))
    expect(extra.sort()).toEqual([...WP_SYNC_HOST_ADDED_CONFIG_KEYS].sort())
    // descriptor 的每一段都**同一引用**传下去（宿主不得改写字段）
    for (const key of Object.keys(source)) {
      expect(config[key]).toBe(source[key])
    }
    expect(config.token).toBeUndefined()
    expect((config.document as Record<string, unknown>).url).toBe(
      (source.document as Record<string, unknown>).url,
    )
    // 编辑器侧 forcesave 为 true 时必须拒绝挂载（不得照挂）
    resetObservations()
    const tampered = makeHarness()
    respond('create_pending_mutation', () => pendingWire())
    respond('materialize', () =>
      descriptorWire({
        onlyoffice_config: {
          ...OO_CONFIG,
          editorConfig: { mode: 'edit', customization: { forcesave: true } },
        },
      }),
    )
    const badDescriptor = await tampered.bridge.switchToOnlyOffice()
    await tampered.wrapper.setProps({ descriptor: badDescriptor })
    await flushPromises()
    await nextTick()
    expect(tampered.editors).toHaveLength(0)
    expect(tampered.wrapper.find('[data-testid="wp-sync-host-error"]').attributes('data-code')).toBe(
      'editor_host_editor_side_forcesave_enabled',
    )
  })

  it('[T69-I28] 立即失败③：normal shell 不得提前伪 application —— 202 后 shape 仍 pre_correlation，跳过 shell 阶段的观测被拒', async () => {
    const harness = makeHarness()
    await driveOpen(harness)
    respond('request_forcesave', () => acceptedWire())

    // forcesave_accepted 阶段（shell_tracking_started 之前）不接受 operation 观测：
    // 直接把 202 之前的状态喂一份 primary 快照必须被转换表拒绝
    expect(() =>
      transitionBridgeState('forcesave_accepted', 'operation_observed', 'oo', {
        operation: {
          requestedOperationId: OPERATION,
          canonicalOperationId: OPERATION,
          followedDuplicate: false,
          state: 'application_bound',
          shape: 'primary',
          applicationId: APPLICATION,
          duplicateOfOperationId: null,
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
        },
      }),
    ).toThrow(/bridge_operation_not_observable|不接受 operation 观测/)

    await harness.bridge.switchToHtml()
    expect(harness.bridge.state.value).toBe('waiting_application')
    // 202 之后：application 尚不存在，shell 两 link 均空
    respond('get_operation', () => operationWire({ state: 'waiting_application' }))
    const shell = await harness.bridge.refreshOperation()
    expect(shell.shape).toBe('pre_correlation')
    expect(shell.applicationId).toBeNull()
    expect(shell.duplicateOfOperationId).toBeNull()
    expect(harness.bridge.state.value).toBe('waiting_application')
    expect(harness.bridge.canonicalApplicationId.value).toBeNull()
    expect(harness.bridge.mode.value).toBe('oo')
    // shell_tracking_started 缺 requested id 时必须拒绝（否则无法沿同一 operation 收敛）
    let shellRefusal: unknown = null
    try {
      transitionBridgeState('forcesave_accepted', 'shell_tracking_started', 'oo')
    } catch (error) {
      shellRefusal = error
    }
    expect(shellRefusal).toBeInstanceOf(WorkpaperSyncContractError)
    expect((shellRefusal as WorkpaperSyncContractError).code).toBe(
      'bridge_shell_requires_requested_operation',
    )
  })

  it('[T69-I29] 立即失败④：claim 前不得伪三实体 —— 三个 recovery 状态各自拒绝带实体的进入', () => {
    for (const event of [
      'recovery_case_observed',
      'recovery_claim_started',
      'recovery_download_only_terminated',
    ] as WorkpaperSyncBridgeEvent[]) {
      const from: WorkpaperSyncBridgeState =
        event === 'recovery_claim_started' || event === 'recovery_download_only_terminated'
          ? 'recovery_pending'
          : 'oo_editing'
      // 干净的三实体：允许
      const ok = transitionBridgeState(from, event, 'oo', {
        recoveryEntities: { forcesaveRequestId: null, applicationId: null, operationId: null },
      })
      expect(['recovery_pending', 'recovery_claiming', 'recovery_download_only']).toContain(ok.to)
      // 逐个实体单独非空：三次各自必须被拒（只测一个会让另两个分支永远不可达）
      for (const key of ['forcesaveRequestId', 'applicationId', 'operationId'] as const) {
        const entities = {
          forcesaveRequestId: null as string | null,
          applicationId: null as string | null,
          operationId: null as string | null,
        }
        entities[key] = UUID(970)
        let thrown: unknown = null
        try {
          transitionBridgeState(from, event, 'oo', { recoveryEntities: entities })
        } catch (error) {
          thrown = error
        }
        expect(thrown).toBeInstanceOf(WorkpaperSyncContractError)
        expect((thrown as WorkpaperSyncContractError).code).toBe('bridge_recovery_premature_entities')
        expect((thrown as Error).message.includes(key)).toBe(true)
      }
    }
    // claim 成功必须三者齐备：缺任一即拒
    for (const key of ['forcesaveRequestId', 'applicationId', 'operationId'] as const) {
      const entities = {
        forcesaveRequestId: REQUEST,
        applicationId: APPLICATION,
        operationId: OPERATION,
      } as Record<string, string | null>
      entities[key] = null
      let thrown: unknown = null
      try {
        transitionBridgeState('recovery_claiming', 'recovery_claim_succeeded', 'oo', {
          claimedEntities: entities as never,
          claimedShape: 'primary',
        })
      } catch (error) {
        thrown = error
      }
      expect((thrown as WorkpaperSyncContractError).code).toBe('bridge_claim_entities_incomplete')
    }
    // download-only 终态没有通往 applied 的边（表里没有就是唯一判据）
    const codeOf = (run: () => unknown): string => {
      try {
        run()
      } catch (error) {
        return (error as WorkpaperSyncContractError).code
      }
      throw new Error('[T69] 期望拒绝但没有拒绝')
    }
    expect(codeOf(() => transitionBridgeState('recovery_download_only', 'operation_observed', 'oo'))).toBe(
      'bridge_operation_context_required',
    )
    expect(
      codeOf(() =>
        transitionBridgeState('recovery_download_only', 'close_successor_applied', 'oo', {
          successorIntentId: UUID(960),
        }),
      ),
    ).toBe('bridge_transition_illegal')
  })

  it('[T69-I30] 立即失败⑤：fail-open 文案被禁 —— 真失败之后 destroy/reload 成功不得覆盖 error', async () => {
    const harness = makeHarness()
    await driveOpen(harness)
    respond('request_forcesave', () => acceptedWire())
    await harness.bridge.switchToHtml()

    // 一次真实的同步失败
    respond('get_operation', () => codedFailure(500, 'merge_engine_failed', '合并引擎失败'))
    await expect(harness.bridge.refreshOperation()).rejects.toThrow()
    await nextTick()
    expect(harness.status().kind).toBe('error')
    const errorText = harness.status().text

    // 之后 destroy 成功、DOM 重渲染、reload 钩子成功 —— 文案一律不得转成功
    await harness.wrapper.setProps({ descriptor: null })
    await flushPromises()
    await nextTick()
    expect(harness.status().kind).toBe('error')
    expect(harness.status().text).toBe(errorText)

    harness.bridge.notifyDirty(false)
    await nextTick()
    expect(harness.status().kind).toBe('error')

    // 宿主自己的一次成功销毁也不得清掉 hostError/桥 error
    harness.wrapper.unmount()
    expect(harness.bridge.lastError.value).not.toBeNull()
    expect(harness.bridge.lastError.value!.errorCode).toBe('merge_engine_failed')

    // 反事实臂：只有用户显式发起新尝试（beginAttempt）才允许清 —— 用 reset 证明它真会清，
    // 否则「粘住」这条判据无法与「永远不清」区分
    harness.bridge.reset()
    expect(harness.bridge.lastError.value).toBeNull()
    expect(harness.bridge.state.value).toBe('html_idle')
  })

  it('[T69-I31] 宿主侧真实失败（DocsAPI 载不到）必须变成可见 sticky error，而不是永久 loading', async () => {
    const harness = makeHarness({ docsApiThrows: true })
    respond('create_pending_mutation', () => pendingWire())
    respond('materialize', () => descriptorWire())
    const descriptor = await harness.bridge.switchToOnlyOffice()
    expect(harness.bridge.state.value).toBe('oo_loading')
    await harness.wrapper.setProps({ descriptor })
    await flushPromises()
    await nextTick()

    expect(harness.editors).toHaveLength(0)
    expect(harness.status().kind).toBe('error')
    expect(harness.bridge.lastError.value).not.toBeNull()
    expect(harness.wrapper.find('[data-testid="wp-sync-host-error"]').exists()).toBe(true)
    // 不再停留在 in-flight 集合里（永久 loading 的可观测反面）
    expect(harness.bridge.state.value).toBe('error')
    expect(harness.bridge.canLeave.value).toBe(true)
    const errorEmit = trace().filter((row) => row.kind === 'emit' && row.name === 'error')
    expect(errorEmit.length).toBeGreaterThanOrEqual(1)
    expect(errorEmit[0].detail.stage).toBe('load_docs_api')
  })

  it('[T69-I32] AC 11.5 的八个事件逐个有真实触发路径（不是「emit 声明里写了」）', async () => {
    // ── 主链路：ready / dirty / save-requested / incoming-durable / terminal
    const main = makeHarness()
    await driveOpen(main)
    main.fireStateChange(true)
    await nextTick()
    respond('request_forcesave', () => acceptedWire())
    const exposed = main.wrapper.vm as unknown as { forceSave: () => Promise<unknown> }
    await exposed.forceSave()
    expect(main.bridge.state.value).toBe('waiting_application')

    respond('get_operation', () =>
      operationWire({ state: 'waiting_application', durable_at: '2026-09-01T00:01:00Z' }),
    )
    await main.bridge.refreshOperation()
    await nextTick()
    expect(main.bridge.state.value).toBe('incoming_durable')

    respond('get_operation', () =>
      operationWire({
        state: 'applied',
        application_id: APPLICATION,
        durable_at: '2026-09-01T00:01:00Z',
        result_revision: 12,
      }),
    )
    await main.bridge.refreshOperation()
    await nextTick()
    expect(main.bridge.state.value).toBe('applied')

    // ── recovery-case：宿主 onError 路径（真实 DocsAPI 回调）
    const crashed = makeHarness()
    await driveOpen(crashed)
    respond('list_recovery_cases', () => recoveryListWire())
    await crashed.fireEditorError(1)
    expect(crashed.bridge.state.value).toBe('recovery_pending')

    // ── error：宿主侧真实失败
    const broken = makeHarness({ docsApiThrows: true })
    respond('create_pending_mutation', () => pendingWire())
    respond('materialize', () => descriptorWire())
    const descriptor = await broken.bridge.switchToOnlyOffice()
    await broken.wrapper.setProps({ descriptor })
    await flushPromises()
    await nextTick()

    const emitted = new Set(trace().filter((row) => row.kind === 'emit').map((row) => row.name))
    for (const name of [
      'ready',
      'dirty',
      'save-requested',
      'incoming-durable',
      'terminal',
      'recovery-case',
      'error',
    ]) {
      expect(emitted.has(name)).toBe(true)
    }
    // 第八个（applied/conflict）由 `terminal` 事件的 `state` 字段承载，逐项可辨
    const terminal = trace().find((row) => row.kind === 'emit' && row.name === 'terminal')!
    expect(terminal.detail.state).toBe('applied')
    expect(terminal.detail.revision).toBe(12)
    // incoming-durable 的 artifactSha256 是**已登记缺口**：只能为 null，不得拿 descriptor
    // 的摘要顶替（那是 materialize 出去的另一份）
    const durable = trace().find((row) => row.kind === 'emit' && row.name === 'incoming-durable')!
    expect(durable.detail.artifactSha256).toBeNull()
    expect(durable.detail.operationId).toBe(OPERATION)
  })

  it('[T69-I34] 判据面自身 fail-closed：未登记端点必须被拒绝，分类不出的 URL 必须显式 UNKNOWN', async () => {
    // 🔴 「判据的判据」。上面每条结论都建立在两个前提上：①任何被打到而**未显式登记**的端点
    // 会立刻可见地失败；②URL 分类器分不出来时显式报 UNKNOWN 而不是静默归进某个真实端点。
    // 这两条在正常路径上都走不到（每个被打到的端点都登记了、每个 URL 都能分类）⇒ 把它们
    // 整段改成静默成功时，其余 33 条判据一条都不会红（本轮变异实测过这条 GREEN）。
    // 故必须在这里主动走一遍它们。
    resetObservations()
    await expect(
      http.get(`/api/v1/projects/${PROJECT}/workpapers/${WP}/sync/entries/${ENTRY}/never-registered`),
    ).rejects.toThrow(/未登记的请求/)

    // 分类器：不认识的形状必须是 UNKNOWN；认识的必须命中那一个（两臂都断言，避免恒真）
    expect(OBS.classify('/api/v1/projects/p/workpapers/w/sync/entries/e/never-registered')).toBe(
      'UNKNOWN',
    )
    expect(OBS.classify('/api/v1/projects/p/workpapers/w/sync/entries/e/materialize')).toBe(
      'materialize',
    )
    // 那次被拒绝的调用仍然被观测到（否则「打错端点」连痕迹都没有）
    expect(netCalls().filter((call) => call.endpoint === 'UNKNOWN')).toHaveLength(1)

    // ③ 导出给门的观测带必须**真的是这次运行产生的**：四个场景各自非空且含真实 network 行。
    // 门用 Python 在这份带子上重算一遍顺序与三实体判据 —— 带子被清空时门侧全部失去输入，
    // 而前端这边一条都不会红（本轮变异实测过这条 GREEN）。故在这里正向断言一次。
    for (const scenario of [
      'descriptor_open',
      'recovery_claim',
      'recovery_download_only',
      'crash_recovery',
    ]) {
      const band = EXPORTED_TRACES[scenario]
      expect(band, scenario).toBeDefined()
      expect(band.length, scenario).toBeGreaterThan(0)
      expect(
        band.some((row) => row.kind === 'net'),
        scenario,
      ).toBe(true)
    }
  })
})
