//
// `WorkpaperSyncEditorHost.vue` 的**挂载判据**（Task 31/32 明确留给 Task 33 的 DOM 侧）。
//
// spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 33
// Validates: Requirements 3.7, 4.8, 5.8, 11.4, 11.5, 11.6, 11.10, 11.12
// Properties: P11（DOM 半）/ P47 / P48（DOM 半）
//
// ═══ 为什么必须是 mounted test ═══
//
// Vue 的两种静默失效 —— **传不存在的 prop** 与 **声明了却零消费的绑定** —— 在
// Volar / vitest / get_diagnostics 三层全绿：前者渲染空、后者让门永远开着。
// AC 11.12 因此明文「仅 import、传不存在 prop 或调用不存在 expose API 均不得算接入」。
// 本文件的每一条都落在**渲染出来的 DOM** 与**真实 emit** 上，不扫符号名。
//
// ═══ 判据设计的四条 ═══
//
// 1. **顺序用一条真实调用序列锁死**：`materialize → DocEditor 构造 → confirm-descriptor`。
//    只断言「confirm 被调过」对「ready 之前就 confirm」全绿。
// 2. **门控要断言两侧**：确认前 disabled 且 `forceSave()` 抛出**具体码**；确认后 enabled。
//    只断言「disabled」时 `if (false)` 也成立。
// 3. **「没有第二份 config」用行为证**：全程 spy `fetch` / `XMLHttpRequest.open`，
//    断言零调用；再叠一条结构判据（两个宿主文件都不 import HTTP 面）。
// 4. **正面判决**：文件末尾断言「组件声明的每个 prop / 每个 emit 都被真的驱动过」——
//    声明一个没人传的 prop、或声明一个永不触发的 emit，都会打红（零消费方 = 死代码）。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { ref } from 'vue'

import WorkpaperSyncEditorHost from '../WorkpaperSyncEditorHost.vue'
import {
  WP_SYNC_DOCS_API_SCRIPT_PATH,
  WP_SYNC_HOST_ADDED_CONFIG_KEYS,
  WP_SYNC_HOST_ERROR_TEXT,
  buildDocEditorConfig,
  currentDocsApi,
  hostRefusal,
  loadDocsApi,
  readDocumentDirty,
  readEditorErrorCode,
  readEditorErrorMessage,
  type WorkpaperSyncDocsApi,
} from '../workpaperSyncEditorHostRuntime'
import {
  useWorkpaperSyncBridge,
  type WorkpaperSyncApiSurface,
  type WorkpaperSyncBridge,
} from '../useWorkpaperSyncBridge'
import { WP_BRIDGE_STATE_TEXT } from '../workpaperSyncBridgeMachine'
import {
  WP_CONTENT_UPDATED_EVENT_NAME,
  useWorkpaperContentRefresh,
  type WorkpaperContentRefresh,
} from '../workpaperSyncContentRefresh'
import { WP_SYNC_DESCRIPTOR_CONFIRM_KEYS } from '../workpaperSyncContract.generated'
import { WorkpaperSyncContractError } from '../workpaperSyncDto'
import type {
  WorkpaperSyncDescriptorConfirmation,
  WorkpaperSyncEditorLaunchDescriptor,
  WorkpaperSyncOperationSnapshot,
  WorkpaperSyncRecoveryCase,
} from '../workpaperSyncDto'

// ═══════════════════════════════════════════════════════════════════════════
// 0. fixtures（形态与 Task 31/32 判据里的一致）
// ═══════════════════════════════════════════════════════════════════════════

const UUID = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const DIGEST = (n: number) => String(n).repeat(2).padEnd(64, 'abc123def0'.repeat(7)).slice(0, 64)
const PROJECT = UUID(101)
const WP = UUID(102)
const ENTRY = 'xlsx/d4/analysis/d4-tab-customer-price'

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
  generation: 3,
  write_fence_epoch: 5,
})

function descriptorFixture(
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

function confirmationFixture(
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

function snapshot(
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
    ...over,
  }
}

function recoveryCaseFixture(
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
// 1. DocsAPI stub（真实回调可从外部触发）
// ═══════════════════════════════════════════════════════════════════════════

interface EditorEvents {
  onDocumentReady: () => void
  onDocumentStateChange: (event: unknown) => void
  onError: (event: unknown) => void
}

interface EditorStub {
  placeholderId: string
  config: Record<string, unknown>
  events: EditorEvents
  destroyCount: number
}

/** 真实调用序列：判据据此锁死 `materialize → mount → confirm` 的先后。 */
let callOrder: string[] = []
let editors: EditorStub[] = []

function docsApiStub(): WorkpaperSyncDocsApi {
  return {
    DocEditor: class {
      destroyEditor: () => void
      constructor(placeholderId: string, config: Record<string, unknown>) {
        callOrder.push('doc_editor')
        const stub: EditorStub = {
          placeholderId,
          config,
          events: config.events as EditorEvents,
          destroyCount: 0,
        }
        editors.push(stub)
        this.destroyEditor = () => {
          stub.destroyCount += 1
        }
      }
    } as unknown as WorkpaperSyncDocsApi['DocEditor'],
  }
}

function lastEditor(): EditorStub {
  const editor = editors[editors.length - 1]
  expect(editor, 'DocEditor 从未被构造 —— descriptor 没有真的挂载').toBeTruthy()
  return editor
}

// ═══════════════════════════════════════════════════════════════════════════
// 2. 桥 harness（注入 API stub，不 mock 模块）
// ═══════════════════════════════════════════════════════════════════════════

type ApiStubs = { [K in keyof WorkpaperSyncApiSurface]: ReturnType<typeof vi.fn> }

interface Harness {
  bridge: WorkpaperSyncBridge
  api: ApiStubs
}

function harness(overrides: Partial<Record<keyof WorkpaperSyncApiSurface, unknown>> = {}): Harness {
  const api = {
    createPendingMutation: vi.fn(async () => ({
      pendingMutationToken: 'tok-1',
      expectedRevision: 11,
      payloadSha256: DIGEST(7),
      expiresAt: '2026-08-16T00:05:00Z',
      idempotencyKey: 'idem-1',
    })),
    materialize: vi.fn(async () => {
      callOrder.push('materialize')
      return descriptorFixture()
    }),
    confirmDescriptor: vi.fn(async () => {
      callOrder.push('confirm_descriptor')
      return confirmationFixture()
    }),
    requestForcesave: vi.fn(async () => {
      callOrder.push('request_forcesave')
      return {
        forcesaveRequestId: UUID(29),
        operationId: UUID(30),
        requestSequence: 7,
        state: 'accepted' as const,
        pollAfterMs: 800,
        replayed: false,
        dispatchError: null,
      }
    }),
    getOperation: vi.fn(async () => snapshot()),
    getOperationConflicts: vi.fn(async () => ({
      canonical_application_id: UUID(9),
      incoming_sequence: 7,
      groups: [],
    })),
    getOperationTimeline: vi.fn(async () => ({ operation_events: [] })),
    getRecoveryCaseTimeline: vi.fn(async () => ({ events: [] })),
    resolveConflicts: vi.fn(async () => ({ decision: 'applied' })),
    retryOperation: vi.fn(async () => {
      callOrder.push('retry_operation')
      return { retried: true }
    }),
    listRecoveryCases: vi.fn(async () => {
      callOrder.push('list_recovery_cases')
      return { roomId: UUID(21), generation: 3, cases: [recoveryCaseFixture()] }
    }),
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
    rollbackVersion: vi.fn(async () => ({ revision_after: 12 })),
  }
  for (const [key, value] of Object.entries(overrides)) {
    ;(api as Record<string, unknown>)[key] = value
  }
  const bridge = useWorkpaperSyncBridge({
    entryId: ref(ENTRY),
    wpId: ref(WP),
    projectId: ref(PROJECT),
    sheetKey: ref('D4-1'),
    capability: 'bidirectional',
    flushHtml: vi.fn(async () => ({ expectedRevision: 11, projection: { rows: [] } })),
    reloadHtml: vi.fn(async () => {}),
    api: api as unknown as WorkpaperSyncApiSurface,
    storage: null,
    installBeforeUnload: false,
  })
  return { bridge, api: api as ApiStubs }
}

// ═══════════════════════════════════════════════════════════════════════════
// 3. 挂载 helper —— 顺带记录「哪些 prop / 哪些 emit 真的被驱动过」
// ═══════════════════════════════════════════════════════════════════════════

const EXERCISED_PROPS = new Set<string>()
const EXERCISED_EMITS = new Set<string>()
const LIVE: VueWrapper[] = []

type HostProps = {
  descriptor: WorkpaperSyncEditorLaunchDescriptor | null
  bridge: WorkpaperSyncBridge
  documentServerUrl?: string
  docsApiLoader?: (() => Promise<WorkpaperSyncDocsApi>) | null
  /** Task 35 追加：内容刷新协调器。给了才渲染刷新条。 */
  contentRefresh?: WorkpaperContentRefresh | null
}

function mountHost(props: HostProps): VueWrapper {
  for (const key of Object.keys(props)) EXERCISED_PROPS.add(key)
  const wrapper = mount(WorkpaperSyncEditorHost, {
    props: props as unknown as Record<string, unknown>,
    attachTo: document.body,
  })
  LIVE.push(wrapper)
  return wrapper
}

/** 桥走到 `oo_editing`：materialize → 传 descriptor → 真实 ready → confirm。 */
async function openEditor(
  h: Harness,
  over: Partial<HostProps> = {},
): Promise<{ wrapper: VueWrapper; descriptor: WorkpaperSyncEditorLaunchDescriptor }> {
  const wrapper = mountHost({
    descriptor: null,
    bridge: h.bridge,
    docsApiLoader: async () => docsApiStub(),
    ...over,
  })
  const descriptor = await h.bridge.switchToOnlyOffice()
  await wrapper.setProps({ descriptor })
  await flushPromises()
  lastEditor().events.onDocumentReady()
  await flushPromises()
  return { wrapper, descriptor }
}

function status(wrapper: VueWrapper): { kind: string; text: string } {
  const el = wrapper.get('[data-testid="wp-sync-host-status"]')
  return { kind: el.attributes('data-kind') ?? '', text: el.text() }
}

function saveButton(wrapper: VueWrapper) {
  return wrapper.find('[data-testid="wp-sync-host-forcesave"]')
}

function hostErrorText(wrapper: VueWrapper): string {
  const el = wrapper.find('[data-testid="wp-sync-host-error"]')
  return el.exists() ? el.text() : ''
}

interface HostApi {
  forceSave: () => Promise<{ operationId: string }>
  getSyncState: () => Record<string, unknown>
}

function hostApi(wrapper: VueWrapper): HostApi {
  return wrapper.vm as unknown as HostApi
}

/**
 * 剥掉 `<!-- -->` / `/* *\/` / `//` 三类注释。
 *
 * 🔴 结构判据必须剥注释：宿主的边界说明**逐字**写着「不 import `@/utils/http`」，
 * 不剥就等于把说明当成违规证据（首轮实测即假红）。剥完还要正反自检，
 * 否则「剥过头把整份源码剥空」会让判据恒真。
 */
function stripComments(source: string): string {
  return source
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/(^|[^:])\/\/[^\n]*/g, '$1')
}

async function expectRejection(fn: () => unknown, code: string): Promise<void> {
  let caught: unknown
  try {
    await fn()
  } catch (error) {
    caught = error
  }
  expect(caught, `期望拒绝 code=${code}`).toBeInstanceOf(WorkpaperSyncContractError)
  expect((caught as WorkpaperSyncContractError).code).toBe(code)
}

let fetchSpy: ReturnType<typeof vi.fn>
let xhrOpenSpy: ReturnType<typeof vi.spyOn>

beforeEach(() => {
  callOrder = []
  editors = []
  delete (window as unknown as { DocsAPI?: unknown }).DocsAPI
  // 「组件不得再请求一份 config」的**行为**判据：任何 HTTP 都会被这两个 spy 记下。
  fetchSpy = vi.fn(async () => new Response('{}'))
  ;(globalThis as unknown as { fetch: unknown }).fetch = fetchSpy
  xhrOpenSpy = vi.spyOn(XMLHttpRequest.prototype, 'open')
})

afterEach(() => {
  for (const wrapper of LIVE) {
    for (const name of Object.keys(wrapper.emitted())) EXERCISED_EMITS.add(name)
    wrapper.unmount()
  }
  LIVE.length = 0
  xhrOpenSpy.mockRestore()
  vi.restoreAllMocks()
  document.querySelectorAll('script').forEach((tag) => tag.remove())
})

// ═══════════════════════════════════════════════════════════════════════════
// 4. Property 11 的 DOM 半：descriptor → mount → ready → confirm → 可编辑
// ═══════════════════════════════════════════════════════════════════════════

describe('descriptor → DocEditor mount → onDocumentReady → confirm → oo_editing', () => {
  it('四步顺序被真实调用序列锁死，且每一步的 DOM 各不相同', async () => {
    const h = harness()
    const wrapper = mountHost({
      descriptor: null,
      bridge: h.bridge,
      docsApiLoader: async () => docsApiStub(),
    })

    // ── 第 0 步：没有 descriptor ⇒ 一个编辑器都不许创建
    expect(wrapper.find('[data-testid="wp-sync-host-editor"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="wp-sync-host-container"]').exists()).toBe(false)
    expect(editors).toHaveLength(0)
    expect(saveButton(wrapper).exists()).toBe(false)

    // ── 第 1 步：服务端给出 descriptor（materialize 先发生）
    const descriptor = await h.bridge.switchToOnlyOffice()
    expect(h.bridge.state.value).toBe('oo_loading')
    expect(h.bridge.mountCallCount.value).toBe(0)
    await wrapper.setProps({ descriptor })
    await flushPromises()

    // ── 第 2 步：DocEditor 真的被构造，且 placeholder id 对应真实 DOM 节点
    expect(editors).toHaveLength(1)
    const editor = lastEditor()
    const placeholder = document.getElementById(editor.placeholderId)
    expect(placeholder, 'DocEditor 拿到的容器 id 在 DOM 里找不到 —— 编辑器会静默降级').toBeTruthy()
    expect(placeholder?.getAttribute('data-testid')).toBe('wp-sync-host-container')
    expect(h.bridge.state.value).toBe('descriptor_mounted')
    expect(h.bridge.mountCallCount.value).toBe(1)

    // 确认尚未发生：遮罩在、保存钮 disabled
    expect(h.api.confirmDescriptor).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="wp-sync-host-mask"]').exists()).toBe(true)
    expect(saveButton(wrapper).attributes('disabled')).toBeDefined()
    expect(status(wrapper).text).toBe(WP_BRIDGE_STATE_TEXT.descriptor_mounted)

    // ── 第 3 步：DocsAPI 的**真实** onDocumentReady
    editor.events.onDocumentReady()
    await flushPromises()

    expect(h.api.confirmDescriptor).toHaveBeenCalledTimes(1)
    const [scope, confirmInput] = h.api.confirmDescriptor.mock.calls[0] as [
      Record<string, string>,
      { descriptor: WorkpaperSyncEditorLaunchDescriptor; confirmPayload: Record<string, unknown> },
    ]
    expect(scope).toEqual({ projectId: PROJECT, wpId: WP, entryId: ENTRY })
    expect(confirmInput.descriptor.docKey).toBe(descriptor.docKey)
    // 回传键集的真源是生成的契约常量，不在判据里手抄第二份
    expect(Object.keys(confirmInput.confirmPayload).sort()).toEqual(
      [...WP_SYNC_DESCRIPTOR_CONFIRM_KEYS].sort(),
    )
    expect(confirmInput.confirmPayload.doc_key).toBe(descriptor.docKey)
    expect(confirmInput.confirmPayload.participant_id).toBe(descriptor.participantId)

    // ── 第 4 步：确认成功之后才 editing / 才可保存
    expect(h.bridge.state.value).toBe('oo_editing')
    expect(wrapper.find('[data-testid="wp-sync-host-mask"]').exists()).toBe(false)
    expect(saveButton(wrapper).attributes('disabled')).toBeUndefined()

    // 顺序判据：materialize 在 mount 之前，confirm 在 mount 之后
    expect(callOrder).toEqual(['materialize', 'doc_editor', 'confirm_descriptor'])
    expect(wrapper.emitted('ready')).toEqual([
      [{ roomId: descriptor.roomId, participantId: descriptor.participantId }],
    ])
  })

  it('ready 不等于可保存：ready 已触发但 confirm 未返回时保存仍 fail visible', async () => {
    // 用一个持有者对象而不是 `let ... | null`：后者会被 TS 的控制流收窄成 `never`，
    // `npx tsc` 直接报 TS2349（vitest 走 esbuild 不做类型检查，看不出来）。
    const gate = { release: () => {} }
    const h = harness({
      confirmDescriptor: vi.fn(async () => {
        callOrder.push('confirm_descriptor')
        await new Promise<void>((resolve) => {
          gate.release = resolve
        })
        return confirmationFixture()
      }),
    })
    const wrapper = mountHost({
      descriptor: null,
      bridge: h.bridge,
      docsApiLoader: async () => docsApiStub(),
    })
    const descriptor = await h.bridge.switchToOnlyOffice()
    await wrapper.setProps({ descriptor })
    await flushPromises()
    lastEditor().events.onDocumentReady()
    await flushPromises()

    // ready 已 emit、confirm 已在飞行中，但状态仍是 confirming ⇒ 不得可保存
    expect(wrapper.emitted('ready')).toHaveLength(1)
    expect(h.bridge.state.value).toBe('confirming_descriptor')
    expect(h.bridge.canForcesave.value).toBe(false)
    expect(saveButton(wrapper).attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-testid="wp-sync-host-mask"]').exists()).toBe(true)

    // 程序化调用也必须拒 —— 且是具体码，不是「某个错误」
    await expectRejection(
      () => hostApi(wrapper).forceSave(),
      'editor_host_forcesave_before_confirmation',
    )
    await flushPromises()
    expect(h.api.requestForcesave).not.toHaveBeenCalled()
    expect(hostErrorText(wrapper)).toContain(
      WP_SYNC_HOST_ERROR_TEXT.editor_host_forcesave_before_confirmation,
    )
    // 早点击必须**只**是宿主可见，不得把正在飞行的合法确认打断成 error
    expect(h.bridge.state.value).toBe('confirming_descriptor')
    expect(h.bridge.lastError.value).toBeNull()

    gate.release()
    await flushPromises()
    expect(h.bridge.state.value).toBe('oo_editing')
    expect(saveButton(wrapper).attributes('disabled')).toBeUndefined()
  })

  it('只读 participant（forcesave_unlocked=false）确认后仍不得渲染可编辑编辑器', async () => {
    const h = harness({
      confirmDescriptor: vi.fn(async () => {
        callOrder.push('confirm_descriptor')
        return confirmationFixture({ forcesaveUnlocked: false })
      }),
    })
    const wrapper = mountHost({
      descriptor: null,
      bridge: h.bridge,
      docsApiLoader: async () => docsApiStub(),
    })
    const descriptor = await h.bridge.switchToOnlyOffice()
    await wrapper.setProps({ descriptor })
    await flushPromises()
    lastEditor().events.onDocumentReady()
    await flushPromises()

    // 桥把它当 stale identity ⇒ 回 HTML；宿主必须把编辑器一起收回
    expect(h.bridge.state.value).toBe('html_idle')
    expect(h.bridge.mode.value).toBe('html')
    expect(wrapper.find('[data-testid="wp-sync-host-editor"]').exists()).toBe(false)
    expect(saveButton(wrapper).exists()).toBe(false)
    expect(status(wrapper).kind).toBe('error')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 5. 「不再请求一份 config」（AC 11.4 / Property 47）
// ═══════════════════════════════════════════════════════════════════════════

describe('descriptor 是唯一 config 来源', () => {
  it('整个打开流程零 HTTP：DocEditor config 逐字来自 descriptor，只多容器三键', async () => {
    const h = harness()
    const { descriptor } = await openEditor(h)

    expect(fetchSpy).not.toHaveBeenCalled()
    expect(xhrOpenSpy).not.toHaveBeenCalled()

    const config = lastEditor().config
    const extra = Object.keys(config).filter(
      (key) => !Object.prototype.hasOwnProperty.call(descriptor.onlyofficeConfig, key),
    )
    // 等值而非包含：包含式判据对「偷偷补了 token / type / document.url」全绿
    expect(extra.sort()).toEqual([...WP_SYNC_HOST_ADDED_CONFIG_KEYS].sort())
    for (const key of Object.keys(descriptor.onlyofficeConfig)) {
      expect(config[key]).toEqual(
        (descriptor.onlyofficeConfig as Record<string, unknown>)[key],
      )
    }
    // 签名 URL 只能原样透传，宿主不得自己拼
    expect((config.document as Record<string, unknown>).url).toBe(
      (OO_CONFIG.document as { url: string }).url,
    )
  })

  it('宿主两个文件都不 import 任何 HTTP 面（结构侧交叉判据）', () => {
    const forbidden = [
      '@/utils/http',
      '@/services/apiProxy',
      './workpaperSyncApi',
      'onlyoffice-config',
      'axios',
    ]
    for (const rel of [
      '../WorkpaperSyncEditorHost.vue',
      '../workpaperSyncEditorHostRuntime.ts',
    ]) {
      const raw = readFileSync(resolve(__dirname, rel), 'utf-8')
      const code = stripComments(raw)
      // 反向自检：注释里**确实**提到了这些名字（宿主的边界说明就在注释里），
      // 不剥注释的话这条判据必然假红 —— 首轮实测就是这么红的。
      expect(raw.length).toBeGreaterThan(code.length)
      for (const needle of forbidden) {
        expect(code, `${rel} 的**代码**里出现了 ${needle}`).not.toContain(needle)
      }
    }
    // 正向自检：剥注释之后仍能看见真实 import ⇒ 剥得不过头
    expect(stripComments(readFileSync(resolve(__dirname, '../WorkpaperSyncEditorHost.vue'), 'utf-8')))
      .toContain("from './workpaperSyncEditorHostRuntime'")
    // 反向自检 2：合成一行真 import 必须被抓到（判据不是恒真）
    expect(stripComments("import http from '@/utils/http'\n")).toContain('@/utils/http')
  })

  it('config 打开了编辑器侧 forcesave 时拒绝挂载（AC 4.1 的孤儿 callback 源）', async () => {
    const h = harness()
    const wrapper = mountHost({
      descriptor: null,
      bridge: h.bridge,
      docsApiLoader: async () => docsApiStub(),
    })
    const good = await h.bridge.switchToOnlyOffice()
    const poisoned = descriptorFixture({
      onlyofficeConfig: {
        ...OO_CONFIG,
        editorConfig: { mode: 'edit', customization: { forcesave: true } },
      },
    })
    expect(good.docKey).toBe(poisoned.docKey)
    await wrapper.setProps({ descriptor: poisoned })
    await flushPromises()

    expect(editors).toHaveLength(0)
    expect(h.bridge.mountCallCount.value).toBe(0)
    expect(hostErrorText(wrapper)).toContain(
      WP_SYNC_HOST_ERROR_TEXT.editor_host_editor_side_forcesave_enabled,
    )
    // 失败必须进桥 ⇒ 不会永远停在「正在打开 OnlyOffice 编辑器」
    expect(h.bridge.state.value).toBe('error')
    expect(status(wrapper).kind).toBe('error')
  })

  it('buildDocEditorConfig 对缺 document 段的 config fail closed', () => {
    const bare = descriptorFixture({ onlyofficeConfig: { documentType: 'cell' } })
    let caught: unknown
    try {
      buildDocEditorConfig(bare, {
        onDocumentReady: () => {},
        onDocumentStateChange: () => {},
        onError: () => {},
      })
    } catch (error) {
      caught = error
    }
    expect(caught).toBeInstanceOf(WorkpaperSyncContractError)
    expect((caught as WorkpaperSyncContractError).code).toBe(
      'editor_host_config_document_missing',
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 6. 确认失败仍 editing / 失败被成功文案覆盖（Property 48 的 DOM 半）
// ═══════════════════════════════════════════════════════════════════════════

describe('确认失败不得留下一个还在编辑的编辑器', () => {
  function staleIdentity(): unknown {
    return {
      response: {
        status: 409,
        data: {
          detail: {
            error_code: 'launch_descriptor_stale_identity',
            message: '房间代际已推进，编辑器身份陈旧',
          },
        },
      },
    }
  }

  it('confirm 409 ⇒ 销毁编辑器、撤掉保存入口、状态条粘住失败', async () => {
    const h = harness({
      confirmDescriptor: vi.fn(async () => {
        callOrder.push('confirm_descriptor')
        throw staleIdentity()
      }),
    })
    const wrapper = mountHost({
      descriptor: null,
      bridge: h.bridge,
      docsApiLoader: async () => docsApiStub(),
    })
    const descriptor = await h.bridge.switchToOnlyOffice()
    await wrapper.setProps({ descriptor })
    await flushPromises()
    const editor = lastEditor()
    editor.events.onDocumentReady()
    await flushPromises()

    expect(h.bridge.state.value).toBe('html_idle')
    expect(h.bridge.mode.value).toBe('html')
    expect(editor.destroyCount).toBe(1)
    expect(wrapper.find('[data-testid="wp-sync-host-editor"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="wp-sync-host-container"]').exists()).toBe(false)
    expect(saveButton(wrapper).exists()).toBe(false)

    // Property 48：失败之后 mode 已回 html，但状态条不得显示「当前为表单模式」
    expect(status(wrapper).kind).toBe('error')
    expect(status(wrapper).text).toBe('房间代际已推进，编辑器身份陈旧')
    expect(status(wrapper).text).not.toBe(WP_BRIDGE_STATE_TEXT.html_idle)
    expect(wrapper.emitted('error')).toHaveLength(1)
    const [payload] = (wrapper.emitted('error') as unknown[][])[0] as [
      { stage: string; code: string },
    ]
    expect(payload.stage).toBe('confirm_descriptor')
    expect(payload.code).toBe('launch_descriptor_stale_identity')
  })

  it('确认失败后再卸载（销毁成功）也不得把状态条洗回成功文案', async () => {
    const h = harness({
      confirmDescriptor: vi.fn(async () => {
        callOrder.push('confirm_descriptor')
        throw staleIdentity()
      }),
    })
    const wrapper = mountHost({
      descriptor: null,
      bridge: h.bridge,
      docsApiLoader: async () => docsApiStub(),
    })
    const descriptor = await h.bridge.switchToOnlyOffice()
    await wrapper.setProps({ descriptor })
    await flushPromises()
    lastEditor().events.onDocumentReady()
    await flushPromises()
    // descriptor 撤走 = 宿主完成清理，清理成功不是同步成功
    await wrapper.setProps({ descriptor: null })
    await flushPromises()
    expect(status(wrapper).kind).toBe('error')
    expect(h.bridge.lastError.value?.errorCode).toBe('launch_descriptor_stale_identity')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 7. crash callback → recovery UI（不是普通 retry）
// ═══════════════════════════════════════════════════════════════════════════

describe('crash 回调进入恢复流程而非普通重试', () => {
  it('已确认房间内的编辑器异常 ⇒ 服务端列出恢复项 ⇒ 渲染恢复区、不渲染重试', async () => {
    const h = harness()
    const { wrapper, descriptor } = await openEditor(h)
    expect(h.bridge.state.value).toBe('oo_editing')

    lastEditor().events.onError({ data: { errorCode: -3, errorDescription: '编辑器连接中断' } })
    await flushPromises()

    // list 必须带显式 room/generation（AC 10.6）
    expect(h.api.listRecoveryCases).toHaveBeenCalledTimes(1)
    const [scope, room] = h.api.listRecoveryCases.mock.calls[0] as [
      Record<string, string>,
      { roomId: string; generation: number },
    ]
    expect(scope).toEqual({ projectId: PROJECT, wpId: WP, entryId: ENTRY })
    expect(room).toEqual({ roomId: descriptor.roomId, generation: descriptor.generation })

    expect(h.bridge.state.value).toBe('recovery_pending')
    const panel = wrapper.find('[data-testid="wp-sync-host-recovery"]')
    expect(panel.exists()).toBe(true)
    expect(panel.text()).toContain('编辑器异常中断')
    // 🔴 普通 operation 重试不得出现（AC 5.8 末句）
    expect(wrapper.find('[data-testid="wp-sync-host-retry"]').exists()).toBe(false)
    expect(h.api.retryOperation).not.toHaveBeenCalled()
  })

  it('claim 之前 recoveryCase 事件不得携带 operation id，三实体全空', async () => {
    const h = harness()
    const { wrapper } = await openEditor(h)
    lastEditor().events.onError({ data: -3 })
    await flushPromises()

    const emitted = wrapper.emitted('recoveryCase') as unknown[][]
    expect(emitted).toHaveLength(1)
    const payload = emitted[0][0] as Record<string, unknown>
    expect(Object.keys(payload).sort()).toEqual(['caseId', 'reason'])
    expect(payload.operationId).toBeUndefined()
    expect(h.bridge.operation.value).toBeNull()
    expect(h.bridge.requestedOperationId.value).toBeNull()
    expect(h.bridge.canonicalApplicationId.value).toBeNull()
  })

  it('服务端列不出可认领项 ⇒ 显式失败，既不渲染恢复区也不退化成重试', async () => {
    const h = harness({
      listRecoveryCases: vi.fn(async () => {
        callOrder.push('list_recovery_cases')
        return { roomId: UUID(21), generation: 3, cases: [] }
      }),
    })
    const { wrapper } = await openEditor(h)
    lastEditor().events.onError({ data: { errorCode: -3, errorDescription: '连接中断' } })
    await flushPromises()

    expect(wrapper.find('[data-testid="wp-sync-host-recovery"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="wp-sync-host-retry"]').exists()).toBe(false)
    expect(hostErrorText(wrapper)).toContain(
      WP_SYNC_HOST_ERROR_TEXT.editor_host_recovery_case_absent,
    )
    expect(h.bridge.state.value).toBe('error')
  })

  it('确认之前的编辑器异常不进恢复流程（转换表里没有那条出边）', async () => {
    const h = harness()
    const wrapper = mountHost({
      descriptor: null,
      bridge: h.bridge,
      docsApiLoader: async () => docsApiStub(),
    })
    const descriptor = await h.bridge.switchToOnlyOffice()
    await wrapper.setProps({ descriptor })
    await flushPromises()
    lastEditor().events.onError({ data: { errorCode: -4, errorDescription: '下载失败' } })
    await flushPromises()

    expect(h.api.listRecoveryCases).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="wp-sync-host-recovery"]').exists()).toBe(false)
    expect(hostErrorText(wrapper)).toContain(
      WP_SYNC_HOST_ERROR_TEXT.editor_host_recovery_before_confirmation,
    )
    expect(h.bridge.state.value).toBe('error')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 8. 可 await 的 forceSave / dirty / 终态事件（AC 11.5 的每个事件都要有真实触发）
// ═══════════════════════════════════════════════════════════════════════════

describe('暴露的 API 与七个事件各有真实触发路径', () => {
  it('forceSave() 真发 forcesave 并 emit saveRequested（带 requested operation id）', async () => {
    const h = harness()
    const { wrapper } = await openEditor(h)
    const result = await hostApi(wrapper).forceSave()
    await flushPromises()

    expect(h.api.requestForcesave).toHaveBeenCalledTimes(1)
    const [, input] = h.api.requestForcesave.mock.calls[0] as [
      unknown,
      { roomId: string; participantId: string; expectedWriteFenceEpoch: number },
    ]
    expect(input).toEqual({ roomId: UUID(21), participantId: UUID(22), expectedWriteFenceEpoch: 5 })
    expect(result.operationId).toBe(UUID(30))
    expect(wrapper.emitted('saveRequested')).toEqual([[{ operationId: UUID(30) }]])
    expect(h.bridge.state.value).toBe('waiting_application')
    expect(callOrder).toEqual([
      'materialize',
      'doc_editor',
      'confirm_descriptor',
      'request_forcesave',
    ])
  })

  it('点击保存按钮走同一条路径（按钮不是装饰）', async () => {
    const h = harness()
    const { wrapper } = await openEditor(h)
    await saveButton(wrapper).trigger('click')
    await flushPromises()
    expect(h.api.requestForcesave).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('saveRequested')).toHaveLength(1)
  })

  it('onDocumentStateChange 真实触发 dirty，并让离开被阻断（AC 4.8）', async () => {
    const h = harness()
    const { wrapper } = await openEditor(h)
    expect(h.bridge.canLeave.value).toBe(true)

    lastEditor().events.onDocumentStateChange({ data: true })
    await flushPromises()
    expect(h.bridge.dirty.value).toBe(true)
    expect(h.bridge.canLeave.value).toBe(false)
    expect(h.bridge.leaveBlockReason.value).toBe('编辑器仍有未保存的修改')

    lastEditor().events.onDocumentStateChange({ data: false })
    await flushPromises()
    expect(h.bridge.dirty.value).toBe(false)
    expect(wrapper.emitted('dirty')).toEqual([[{ dirty: true }], [{ dirty: false }]])
  })

  it('incomingDurable / terminal 由桥的真实状态推进触发，且不伪造 incoming 摘要', async () => {
    const h = harness()
    const { wrapper, descriptor } = await openEditor(h)
    await hostApi(wrapper).forceSave()
    await flushPromises()

    h.bridge.ingestOperationSnapshot(
      snapshot({ state: 'accepted', shape: 'pre_correlation', durableAt: '2026-08-16T01:00:00Z' }),
    )
    await flushPromises()
    expect(h.bridge.state.value).toBe('incoming_durable')
    const durable = wrapper.emitted('incomingDurable') as unknown[][]
    expect(durable).toHaveLength(1)
    const durablePayload = durable[0][0] as { operationId: string; artifactSha256: string | null }
    expect(durablePayload.operationId).toBe(UUID(30))
    // 已登记缺口：operation 投影没有 incoming artifact digest ⇒ 只能是 null，
    // 绝不能拿 descriptor 的（materialize 出去的那份）摘要顶替
    expect(durablePayload.artifactSha256).toBeNull()
    expect(durablePayload.artifactSha256).not.toBe(descriptor.artifactSha256)

    h.bridge.ingestOperationSnapshot(
      snapshot({
        state: 'applied',
        shape: 'primary',
        applicationId: UUID(50),
        resultRevision: 12,
        durableAt: '2026-08-16T01:00:00Z',
        finishedAt: '2026-08-16T01:00:05Z',
        terminal: true,
      }),
    )
    await flushPromises()
    expect(h.bridge.state.value).toBe('applied')
    expect(wrapper.emitted('terminal')).toEqual([
      [{ operationId: UUID(30), state: 'applied', revision: 12 }],
    ])
    expect(status(wrapper).kind).toBe('success')
    expect(status(wrapper).text).toBe(WP_BRIDGE_STATE_TEXT.applied)
  })

  it('conflict 终态与 applied 终态可分辨（不得都显示成完成）', async () => {
    const h = harness()
    const { wrapper } = await openEditor(h)
    await hostApi(wrapper).forceSave()
    await flushPromises()
    h.bridge.ingestOperationSnapshot(
      snapshot({
        state: 'conflict',
        shape: 'primary',
        applicationId: UUID(50),
        conflictCount: 3,
        resultRevision: null,
        terminal: false,
      }),
    )
    await flushPromises()
    expect(h.bridge.state.value).toBe('conflict')
    expect(wrapper.emitted('terminal')).toEqual([
      [{ operationId: UUID(30), state: 'conflict', revision: null }],
    ])
    expect(status(wrapper).text).toBe(WP_BRIDGE_STATE_TEXT.conflict)
    expect(status(wrapper).text).not.toBe(WP_BRIDGE_STATE_TEXT.applied)
  })

  it('getSyncState() 逐项来自桥，不自己维护第二份状态', async () => {
    const h = harness()
    const { wrapper } = await openEditor(h)
    const before = hostApi(wrapper).getSyncState()
    expect(before).toMatchObject({
      mode: 'oo',
      state: 'oo_editing',
      dirty: false,
      editorMounted: true,
      editing: true,
      canForcesave: true,
      requestedOperationId: null,
      hostErrorCode: null,
    })
    expect(before.recoveryCaseIds).toEqual([])

    await hostApi(wrapper).forceSave()
    await flushPromises()
    const after = hostApi(wrapper).getSyncState()
    expect(after).toMatchObject({
      state: 'waiting_application',
      requestedOperationId: UUID(30),
      canForcesave: false,
    })
    expect((after.feedback as { message: string }).message).toBe(
      WP_BRIDGE_STATE_TEXT.waiting_application,
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 9. 重挂（refresh-required 新代际）与 DocsAPI 载入
// ═══════════════════════════════════════════════════════════════════════════

describe('重挂与 DocsAPI 载入', () => {
  it('新代际重开：旧编辑器被销毁、新 descriptor 重新挂载并重新 confirm', async () => {
    // 唯一**可达**的重开序列：一次身份失败把 mode 打回 html，再重新 materialize。
    // （`refresh_required --descriptor_received--> rematerializing` 这条声明边目前
    // 没有公开触发口，见本文件末尾登记的三条不可达边。）
    let generation = 3
    const h = harness({
      materialize: vi.fn(async () => {
        callOrder.push('materialize')
        return descriptorFixture({ generation, docKey: `dockey-${generation}` })
      }),
      confirmDescriptor: vi.fn(async () => {
        callOrder.push('confirm_descriptor')
        if (generation === 3) {
          throw {
            response: {
              status: 409,
              data: {
                detail: {
                  error_code: 'launch_descriptor_stale_identity',
                  message: '房间代际已推进',
                },
              },
            },
          }
        }
        return confirmationFixture({ generation })
      }),
    })
    const wrapper = mountHost({
      descriptor: null,
      bridge: h.bridge,
      docsApiLoader: async () => docsApiStub(),
    })
    const stale = await h.bridge.switchToOnlyOffice()
    await wrapper.setProps({ descriptor: stale })
    await flushPromises()
    const first = lastEditor()
    first.events.onDocumentReady()
    await flushPromises()
    expect(h.bridge.mode.value).toBe('html')
    expect(first.destroyCount).toBe(1)
    expect(h.bridge.mountCallCount.value).toBe(1)

    generation = 4
    const fresh = await h.bridge.switchToOnlyOffice()
    expect(fresh.generation).toBe(4)
    await wrapper.setProps({ descriptor: fresh })
    await flushPromises()
    expect(editors).toHaveLength(2)
    expect(lastEditor().placeholderId).not.toBe(first.placeholderId)
    expect(document.getElementById(lastEditor().placeholderId)).toBeTruthy()
    expect(h.bridge.mountCallCount.value).toBe(2)

    lastEditor().events.onDocumentReady()
    await flushPromises()
    expect(h.api.confirmDescriptor).toHaveBeenCalledTimes(2)
    expect(h.bridge.state.value).toBe('oo_editing')
    expect(status(wrapper).kind).not.toBe('error')
  })

  it('同一 descriptor 重复下发不重复挂载（幂等）', async () => {
    const h = harness()
    const { wrapper, descriptor } = await openEditor(h)
    await wrapper.setProps({ descriptor: { ...descriptor } })
    await flushPromises()
    expect(editors).toHaveLength(1)
    expect(h.bridge.mountCallCount.value).toBe(1)
  })

  it('在编辑中被换掉 descriptor 身份 ⇒ 显式失败，不静默替换编辑器', async () => {
    // 桥的转换表里 `oo_editing` 没有 `editor_mounted` 出边 —— 合法重开只能经
    // `refresh_required → rematerializing → oo_loading`，而那条链目前没有公开触发口
    // （已登记的三条不可达边之一）。所以「编辑中换 descriptor」必须显式炸出来，
    // 而不是悄悄换掉一个用户正在编辑的 iframe。
    const h = harness()
    const { wrapper, descriptor } = await openEditor(h)
    await wrapper.setProps({
      // 只差 representation 代际：挂载身份必须把它算进去，否则这次替换会被吞掉
      descriptor: { ...descriptor, representationGeneration: 3 },
    })
    await flushPromises()

    expect(editors).toHaveLength(2)
    expect(h.bridge.mountCallCount.value).toBe(2)
    expect(h.bridge.state.value).toBe('error')
    expect(status(wrapper).kind).toBe('error')
    expect(hostErrorText(wrapper)).toContain('oo_editing')
  })

  it('未注入 loader 时按 documentServerUrl 载入 api.js（不是第二份 config）', async () => {
    const h = harness()
    const appended: string[] = []
    const realCreate = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = realCreate(tag) as HTMLElement
      if (tag === 'script') {
        appended.push('script')
        setTimeout(() => {
          ;(window as unknown as { DocsAPI?: unknown }).DocsAPI = docsApiStub()
          ;(el as HTMLScriptElement).onload?.(new Event('load'))
        }, 0)
      }
      return el
    })

    const wrapper = mountHost({
      descriptor: null,
      bridge: h.bridge,
      documentServerUrl: 'http://onlyoffice.internal:8080/',
      docsApiLoader: null,
    })
    const descriptor = await h.bridge.switchToOnlyOffice()
    await wrapper.setProps({ descriptor })
    await flushPromises()
    await new Promise((r) => setTimeout(r, 5))
    await flushPromises()

    expect(appended).toHaveLength(1)
    const tag = document.head.querySelector('script') as HTMLScriptElement | null
    expect(tag?.src).toBe(`http://onlyoffice.internal:8080${WP_SYNC_DOCS_API_SCRIPT_PATH}`)
    expect(editors).toHaveLength(1)
    expect(h.bridge.state.value).toBe('descriptor_mounted')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('prop 未给时回落部署期环境变量（`VITE_ONLYOFFICE_URL`）', async () => {
    vi.stubEnv('VITE_ONLYOFFICE_URL', 'http://oo-from-env:8080')
    const h = harness()
    const realCreate = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = realCreate(tag) as HTMLElement
      if (tag === 'script') {
        setTimeout(() => {
          ;(window as unknown as { DocsAPI?: unknown }).DocsAPI = docsApiStub()
          ;(el as HTMLScriptElement).onload?.(new Event('load'))
        }, 0)
      }
      return el
    })
    const wrapper = mountHost({ descriptor: null, bridge: h.bridge, docsApiLoader: null })
    const descriptor = await h.bridge.switchToOnlyOffice()
    await wrapper.setProps({ descriptor })
    await flushPromises()
    await new Promise((r) => setTimeout(r, 5))
    await flushPromises()
    const tag = document.head.querySelector('script') as HTMLScriptElement | null
    expect(tag?.src).toBe(`http://oo-from-env:8080${WP_SYNC_DOCS_API_SCRIPT_PATH}`)
    expect(editors).toHaveLength(1)
    vi.unstubAllEnvs()
  })

  it('没有服务地址也没有 loader ⇒ 显式失败，不停在「正在打开」', async () => {
    // 环境变量在本仓库的 `.env` 里是有值的，必须显式清掉才能测「什么都没配」。
    vi.stubEnv('VITE_ONLYOFFICE_URL', '')
    const h = harness()
    const wrapper = mountHost({
      descriptor: null,
      bridge: h.bridge,
      documentServerUrl: '',
      docsApiLoader: null,
    })
    const descriptor = await h.bridge.switchToOnlyOffice()
    await wrapper.setProps({ descriptor })
    await flushPromises()

    expect(editors).toHaveLength(0)
    expect(h.bridge.mountCallCount.value).toBe(0)
    expect(h.bridge.state.value).toBe('error')
    expect(status(wrapper).kind).toBe('error')
    expect(status(wrapper).text).not.toBe(WP_BRIDGE_STATE_TEXT.oo_loading)
    expect(hostErrorText(wrapper)).toContain(
      WP_SYNC_HOST_ERROR_TEXT.editor_host_document_server_url_missing,
    )
    vi.unstubAllEnvs()
  })

  it('DocEditor 构造抛错 ⇒ 不得上报「已挂载」，且失败可见', async () => {
    const h = harness()
    const wrapper = mountHost({
      descriptor: null,
      bridge: h.bridge,
      docsApiLoader: async () => ({
        DocEditor: class {
          constructor() {
            throw new Error('DocEditor boom')
          }
        } as unknown as WorkpaperSyncDocsApi['DocEditor'],
      }),
    })
    const descriptor = await h.bridge.switchToOnlyOffice()
    await wrapper.setProps({ descriptor })
    await flushPromises()

    // 构造失败却上报挂载 = 伪造挂载：桥会以为编辑器在，实际什么都没有
    expect(h.bridge.mountCallCount.value).toBe(0)
    expect(h.bridge.state.value).toBe('error')
    expect(status(wrapper).kind).toBe('error')
    expect(hostErrorText(wrapper)).toContain('DocEditor boom')
  })

  it('宿主上报口在终态下不抛，且仍然记住失败（sticky）', async () => {
    const h = harness()
    h.bridge.notifyRecoveryCase(recoveryCaseFixture())
    await h.bridge.terminateRecoveryDownloadOnly(UUID(40))
    expect(h.bridge.state.value).toBe('recovery_download_only')
    const described = h.bridge.notifyHostFailure('load_docs_api', new Error('内核不可用'))
    expect(described.errorCode).toBe('sync_step_failed_without_server_code')
    // 终态没有 `sync_failed` 出边 ⇒ 状态不动，但失败必须被记住
    expect(h.bridge.state.value).toBe('recovery_download_only')
    expect(h.bridge.lastError.value?.message).toBe('内核不可用')
    expect(h.bridge.feedback.value.kind).toBe('error')
  })

  it('loadDocsApi 在 window.DocsAPI 已可用时直接复用，不再插脚本', async () => {
    ;(window as unknown as { DocsAPI?: unknown }).DocsAPI = docsApiStub()
    const api = await loadDocsApi('')
    expect(typeof api.DocEditor).toBe('function')
    expect(currentDocsApi()).not.toBeNull()
    expect(document.head.querySelector('script')).toBeNull()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 10. 纯函数层的取码归一
// ═══════════════════════════════════════════════════════════════════════════

describe('编辑器回调取码归一', () => {
  it.each([
    [{ data: { errorCode: -3, errorDescription: '转换失败' } }, 'editor_error_-3', '转换失败'],
    [{ data: -20 }, 'editor_error_-20', 'editor_error_-20'],
    [{ data: 'connection_lost' }, 'editor_error_connection_lost', 'editor_error_connection_lost'],
    [{}, 'editor_error_unknown', 'editor_error_unknown'],
    [undefined, 'editor_error_unknown', 'editor_error_unknown'],
  ])('%o → 码 %s / 文案 %s', (event, code, message) => {
    expect(readEditorErrorCode(event)).toBe(code)
    expect(readEditorErrorMessage(event)).toBe(message)
  })

  it('dirty 只认 data===true（undefined / 字符串都不算脏）', () => {
    expect(readDocumentDirty({ data: true })).toBe(true)
    expect(readDocumentDirty({ data: false })).toBe(false)
    expect(readDocumentDirty({ data: 'true' })).toBe(false)
    expect(readDocumentDirty(undefined)).toBe(false)
  })

  it('未登记的宿主失败码被换成显式的「码未登记」，不显示裸标识符', () => {
    const refusal = hostRefusal('editor_host_never_registered')
    expect(refusal.code).toBe('editor_host_error_code_unregistered')
    expect(refusal.message).toContain('editor_host_never_registered')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 10.5 Task 35：内容刷新协调器接进宿主（真驱动，不是补一个 prop 名）
// ═══════════════════════════════════════════════════════════════════════════

describe('内容刷新协调器（Task 35）', () => {
  function coordinator(dirty: boolean): {
    refresh: WorkpaperContentRefresh
    reload: ReturnType<typeof vi.fn>
  } {
    const reload = vi.fn(async () => {})
    const refresh = useWorkpaperContentRefresh({
      wpId: ref(WP),
      projectId: ref(PROJECT),
      loadedRevision: () => 11,
      isDirty: () => dirty,
      reload: reload as unknown as (minimumRevision: number) => Promise<void>,
      subscribe: () => ({ close: vi.fn() }),
    })
    return { refresh, reload }
  }

  function contentEvent(revision: number): Record<string, unknown> {
    return {
      event_type: WP_CONTENT_UPDATED_EVENT_NAME,
      project_id: PROJECT,
      year: null,
      extra: {
        wp_id: WP,
        project_id: PROJECT,
        revision,
        operation_id: UUID(30),
        source: 'onlyoffice',
        adapter_id: 'd4.analysis.customer-price',
        file_sha256: DIGEST(1),
        entry_id: ENTRY,
        content_version_id: UUID(23),
        content_revision_advanced: true,
        reason: 'content_commit',
      },
    }
  }

  it('传了协调器 ⇒ 刷新条渲染，且状态随真实事件推进', async () => {
    const h = harness()
    const { refresh, reload } = coordinator(true)
    const wrapper = mountHost({
      descriptor: null,
      bridge: h.bridge,
      docsApiLoader: async () => docsApiStub(),
      contentRefresh: refresh,
    })
    expect(wrapper.get('[data-testid="wp-content-refresh"]').attributes('data-status')).toBe('idle')
    await refresh.handleEvent(contentEvent(12))
    await flushPromises()
    // dirty ⇒ 暂缓、**不**静默覆盖，且给出显式选择
    expect(wrapper.get('[data-testid="wp-content-refresh"]').attributes('data-status')).toBe(
      'deferred_dirty',
    )
    expect(reload).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="wp-content-refresh-accept"]').exists()).toBe(true)
  })

  it('未传协调器 ⇒ 整条不渲染，宿主其余部分不受影响', () => {
    const h = harness()
    const wrapper = mountHost({
      descriptor: null,
      bridge: h.bridge,
      docsApiLoader: async () => docsApiStub(),
    })
    expect(wrapper.find('[data-testid="wp-content-refresh"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="wp-sync-host-status"]').exists()).toBe(true)
  })

  it('桥的失败与刷新条的失败互不覆盖（AC 11.10 的两条独立可见面）', async () => {
    const h = harness()
    const reload = vi.fn(async () => {
      throw new Error('网络中断')
    })
    const refresh = useWorkpaperContentRefresh({
      wpId: ref(WP),
      projectId: ref(PROJECT),
      loadedRevision: () => 11,
      isDirty: () => false,
      reload: reload as unknown as (minimumRevision: number) => Promise<void>,
      subscribe: () => ({ close: vi.fn() }),
    })
    const wrapper = mountHost({
      descriptor: null,
      bridge: h.bridge,
      docsApiLoader: async () => docsApiStub(),
      contentRefresh: refresh,
    })
    h.bridge.notifyHostFailure('editor_runtime', new Error('内核异常'))
    await refresh.handleEvent(contentEvent(12))
    await flushPromises()
    expect(status(wrapper).kind).toBe('error')
    expect(status(wrapper).text).toContain('内核异常')
    expect(wrapper.get('[data-testid="wp-content-refresh-failure-code"]').text()).toContain(
      'content_refresh_reload_failed',
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 11. 正面判决：声明的每个 prop / emit 都被真的驱动过
// ═══════════════════════════════════════════════════════════════════════════

describe('零消费方判决（本组必须放在文件末尾）', () => {
  it('组件声明的 prop 集合逐字等于本文件真正驱动过的集合', () => {
    const declared = Object.keys(
      (WorkpaperSyncEditorHost as unknown as { props: Record<string, unknown> }).props,
    )
    expect(declared.length).toBeGreaterThan(0)
    // 等值：多声明一个没人传的 prop（死 prop）或漏驱动一个 prop 都打红
    expect([...EXERCISED_PROPS].sort()).toEqual(declared.sort())
  })

  it('组件声明的 emit 集合逐字等于本文件真正触发过的集合', () => {
    const declared = (WorkpaperSyncEditorHost as unknown as { emits: string[] }).emits
    expect(Array.isArray(declared)).toBe(true)
    expect(declared.length).toBeGreaterThan(0)
    // VTU 的 `emitted()` 会把在组件内 `trigger()` 出来的**原生** DOM 事件也记一笔
    // （本文件点了保存按钮 ⇒ 多出一个 `click`）。它不是组件声明的 emit，
    // 显式登记排除；排除表本身参与断言，多一个少一个都会红。
    const VTU_NATIVE_ARTEFACTS = ['click'] as const
    const triggered = [...EXERCISED_EMITS].filter(
      (name) => !(VTU_NATIVE_ARTEFACTS as readonly string[]).includes(name),
    )
    expect([...EXERCISED_EMITS].filter((n) =>
      (VTU_NATIVE_ARTEFACTS as readonly string[]).includes(n),
    )).toEqual([...VTU_NATIVE_ARTEFACTS])
    // 等值：声明一个永不触发的 emit（design 里的 `fallback` 就是这种）会打红
    expect(triggered.sort()).toEqual([...declared].sort())
  })

  it('defineExpose 的两个 API 都被真的调用过（不是只声明）', () => {
    const h = harness()
    const wrapper = mountHost({
      descriptor: null,
      bridge: h.bridge,
      docsApiLoader: async () => docsApiStub(),
    })
    const api = hostApi(wrapper)
    expect(typeof api.forceSave).toBe('function')
    expect(typeof api.getSyncState).toBe('function')
    expect(api.getSyncState()).toMatchObject({ mode: 'html', editorMounted: false })
  })
})
