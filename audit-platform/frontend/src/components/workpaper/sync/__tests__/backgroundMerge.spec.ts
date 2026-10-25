/**
 * 先回表单、后台合并（spec oo-return-to-form-dead-end-and-save-speed R4）。
 *
 * 钉住五件事：
 * 1. 状态机：只有文件已耐久的四态能转后台合并；合并中只收落地 / 失败；失败后只收重试与关闭；两态都是
 *    表单模式、进不了在线编辑、不在 in-flight 集合里（关页不阻断）。
 * 2. 伴生模块：落地 ⇒ 按结果 revision 重载 → 释放 lease → 回 html_idle → 注销；冲突 / 出错 / 失权 /
 *    超时 / 重载失败 ⇒ 失败态 + 中文原因、lease 不放；重试 / 刷新 / 关闭三个出口；卸载停追踪且迟到的
 *    快照不再起作用。
 * 3. 桥：`continueInBackground()` 后追踪归桥（经桥的 api 通道），合并中拒绝再进在线编辑。
 * 4. 宿主：点了保存、文件耐久、之后没再编辑 ⇒ 停自己的追踪、交给桥；编辑过 / 直接落地不交；交接时
 *    宿主追踪器在飞的那一读回来后不再投递。
 * 5. 登记与持久化：合并中拒写、失败或注销后照常写；旧登记注销不误删新登记。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ref } from 'vue'

vi.mock('@/services/apiProxy', () => ({ api: { put: vi.fn(), get: vi.fn() } }))

import { api as proxyApi } from '@/services/apiProxy'
import WorkpaperSyncEditorHost from '../WorkpaperSyncEditorHost.vue'
import WorkpaperBackgroundMergeBanner from '../WorkpaperBackgroundMergeBanner.vue'
import { useChecklistPersistence } from '@/composables/workpaper/useChecklistPersistence'
import {
  BACKGROUND_MERGE_DEADLINE_MS,
  BACKGROUND_MERGE_TEXT,
  backgroundMergeVerdict,
  createBackgroundMerge,
} from '../bridgeBackgroundMerge'
import {
  BACKGROUND_MERGE_WRITE_REFUSED_MESSAGE,
  backgroundMergeOf,
  clearBackgroundMerges,
  isBackgroundMerging,
  registerBackgroundMerge,
} from '../backgroundMergeRegistry'
import {
  WP_BRIDGE_BACKGROUND_MERGE_SOURCE_STATES,
  WP_BRIDGE_BACKGROUND_MERGE_STATES,
  WP_BRIDGE_EXIT_STATES,
  WP_BRIDGE_IN_FLIGHT_STATES,
} from '../bridgeStateSets'
import { useWorkpaperSyncBridge, type WorkpaperSyncApiSurface } from '../useWorkpaperSyncBridge'
import {
  WP_BRIDGE_EVENTS,
  WP_BRIDGE_STATES,
  WP_BRIDGE_STATE_MODE,
  canTransition,
  transitionBridgeState,
  type WorkpaperSyncBridgeEvent,
  type WorkpaperSyncBridgeState,
} from '../workpaperSyncBridgeMachine'
import type { WorkpaperSyncDocEditorEvents, WorkpaperSyncDocsApi } from '../workpaperSyncEditorHostRuntime'
import type { WorkpaperSyncEditorLaunchDescriptor, WorkpaperSyncOperationSnapshot } from '../workpaperSyncDto'
import { WorkpaperSyncOperationTracker, type WorkpaperSyncTrackerOptions } from '../workpaperSyncOperationTracker'

const UUID = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const DIGEST = (n: number) => String(n).repeat(2).padEnd(64, 'abc123def0'.repeat(7)).slice(0, 64)
const OP = UUID(30)
const WP = UUID(102)
const SCOPE = { projectId: UUID(101), wpId: WP, entryId: 'xlsx/gt-d2-accounts-receivable' }

function snapshot(over: Partial<WorkpaperSyncOperationSnapshot> = {}): WorkpaperSyncOperationSnapshot {
  return {
    requestedOperationId: OP, canonicalOperationId: OP, followedDuplicate: false,
    state: 'merging', shape: 'primary', applicationId: UUID(9), duplicateOfOperationId: null,
    errorCode: null, errorStage: null, acceptedAt: null, applicationBoundAt: null,
    applicationErrorCode: null, applicationErrorStage: null, applicationErrorMessage: null,
    operationFinishedAt: null, resultRevision: null, conflictCount: null, logicalResultCode: null,
    definitionBundleId: null, definitionBundleSha256: null, authorityModelDefinitionSha256: null,
    durableAt: '2026-10-25T00:00:00Z', finishedAt: null, terminal: false,
    ...over,
  }
}
const APPLIED = (revision = 12) =>
  snapshot({ state: 'applied', resultRevision: revision, terminal: true, finishedAt: '2026-10-25T00:00:09Z' })

const EVENTS_WITH_CONTEXT = new Set<WorkpaperSyncBridgeEvent>(['operation_observed', 'recovery_claim_succeeded'])

beforeEach(() => clearBackgroundMerges())

// ═══════════════════════════════════════════════════════════════════════════
// 1. 状态机
// ═══════════════════════════════════════════════════════════════════════════

describe('状态机：后台合并两态', () => {
  const accepted = (state: WorkpaperSyncBridgeState) =>
    WP_BRIDGE_EVENTS.filter((event) => !EVENTS_WITH_CONTEXT.has(event) && canTransition(state, event)).sort()

  it('只有文件已耐久的四态（与失败后的重试）能转后台合并；等回传 / 编辑中 / 冻结都不能', () => {
    const from = WP_BRIDGE_STATES.filter((state) => canTransition(state, 'background_merge_started'))
    expect([...from].sort()).toEqual([...WP_BRIDGE_BACKGROUND_MERGE_SOURCE_STATES, 'background_merge_failed'].sort())
    for (const state of WP_BRIDGE_BACKGROUND_MERGE_SOURCE_STATES) {
      const t = transitionBridgeState(state, 'background_merge_started', 'oo')
      expect([t.to, t.mode], state).toEqual(['merging_in_background', 'html'])
    }
  })

  it('合并中只收落地与失败；失败后只收重试 / 刷新与关闭', () => {
    expect(accepted('merging_in_background')).toEqual(['background_merge_failed', 'reload_completed'])
    expect(accepted('background_merge_failed')).toEqual(['background_merge_started', 'reset'])
    expect(transitionBridgeState('merging_in_background', 'reload_completed', 'html').to).toBe('html_idle')
    expect(transitionBridgeState('background_merge_failed', 'reset', 'html').to).toBe('html_idle')
  })

  it('两态都是表单模式，都进不了在线编辑，都不阻断关页，也不显示编辑器的退出按钮', () => {
    for (const state of WP_BRIDGE_BACKGROUND_MERGE_STATES) {
      expect(WP_BRIDGE_STATE_MODE[state], state).toBe('html')
      expect(canTransition(state, 'flush_started'), state).toBe(false)
      expect(canTransition(state, 'forcesave_started'), state).toBe(false)
      expect(WP_BRIDGE_IN_FLIGHT_STATES.includes(state), state).toBe(false)
      expect(WP_BRIDGE_EXIT_STATES.includes(state), state).toBe(false)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 2. 伴生模块
// ═══════════════════════════════════════════════════════════════════════════

class FakeTracker {
  started = 0
  stopped = 0
  constructor(readonly options: WorkpaperSyncTrackerOptions) {}
  async start(): Promise<void> {
    this.started += 1
  }
  stop(): void {
    this.stopped += 1
  }
  deliver(value: WorkpaperSyncOperationSnapshot): void {
    this.options.onSnapshot(value)
  }
  deadline(): void {
    this.options.onDeadline?.(BACKGROUND_MERGE_DEADLINE_MS)
  }
}

function companion(initial: WorkpaperSyncBridgeState = 'merging', over: Record<string, unknown> = {}) {
  const state = ref<WorkpaperSyncBridgeState>(initial)
  const calls: string[] = []
  const trackers: FakeTracker[] = []
  const reloadHtml = vi.fn(async (revision: number) => {
    calls.push(`reload:${revision}`)
  })
  const finishSession = vi.fn(async () => {
    calls.push('finish')
  })
  const retry = vi.fn(async () => {
    calls.push('retry')
    return { retried: true }
  })
  const apply = (event: WorkpaperSyncBridgeEvent) => {
    const mode = WP_BRIDGE_STATE_MODE[state.value]
    state.value = transitionBridgeState(state.value, event, mode === 'inherit' ? 'html' : mode).to
    calls.push(event)
  }
  const merge = createBackgroundMerge({
    wpId: () => WP,
    scope: () => SCOPE,
    operationId: () => OP,
    pollAfterMs: () => 500,
    state: () => state.value,
    apply,
    fetchSnapshot: vi.fn(),
    observe: vi.fn(),
    retry,
    reloadHtml,
    finishSession,
    trackerFactory: (options) => {
      const tracker = new FakeTracker(options)
      trackers.push(tracker)
      return tracker
    },
    ...over,
  })
  return { state, calls, trackers, reloadHtml, finishSession, retry, merge, last: () => trackers[trackers.length - 1] }
}

describe('伴生模块：落地与失败', () => {
  it('转后台：登记为合并中、由桥起追踪（同一 operation、180 s 窗口、后端给的节奏）', () => {
    const c = companion()
    c.merge.continueInBackground()
    expect(c.state.value).toBe('merging_in_background')
    expect(isBackgroundMerging(WP)).toBe(true)
    expect(backgroundMergeOf(WP)?.message).toBe(BACKGROUND_MERGE_TEXT.merging)
    expect(c.trackers).toHaveLength(1)
    expect(c.last().started).toBe(1)
    expect(c.last().options).toMatchObject({ operationId: OP, deadlineMs: 180_000, pollIntervalMs: 500 })
  })

  it('没落地的快照只等；落地 ⇒ 先按结果 revision 重载、再释放 lease、再回表单并注销', async () => {
    const c = companion()
    c.merge.continueInBackground()
    c.last().deliver(snapshot({ state: 'rematerializing' }))
    c.last().deliver(snapshot({ state: 'applying' })) // 投影成 applied，但还没有结果 revision
    await flushPromises()
    expect(c.reloadHtml).not.toHaveBeenCalled()
    c.last().deliver(APPLIED(12))
    await flushPromises()
    expect(c.calls.slice(-3)).toEqual(['reload:12', 'finish', 'reload_completed'])
    expect(c.state.value).toBe('html_idle')
    expect(backgroundMergeOf(WP)).toBeNull()
    expect(c.last().stopped).toBeGreaterThan(0)
  })

  it('冲突 ⇒ 失败态 + 中文原因；不重载、不放 lease、表单解除只读、不能重试', async () => {
    const c = companion()
    c.merge.continueInBackground()
    c.last().deliver(snapshot({ state: 'conflict', conflictCount: 2, terminal: true }))
    await flushPromises()
    expect(c.state.value).toBe('background_merge_failed')
    expect(backgroundMergeOf(WP)).toMatchObject({ status: 'failed', message: BACKGROUND_MERGE_TEXT.conflict, canRetry: false })
    expect(isBackgroundMerging(WP), '失败后表单必须能用').toBe(false)
    expect(c.reloadHtml).not.toHaveBeenCalled()
    expect(c.finishSession, 'lease 留到用户关闭提示').not.toHaveBeenCalled()
  })

  it('出错 ⇒ 带后端原因、可重试；重试 ⇒ 服务端重新合并、回到合并中、换一个追踪器', async () => {
    const c = companion()
    c.merge.continueInBackground()
    c.last().deliver(snapshot({ state: 'error', terminal: true, applicationErrorMessage: '金额列填了文本' }))
    await flushPromises()
    const entry = backgroundMergeOf(WP)
    expect(entry).toMatchObject({ status: 'failed', canRetry: true })
    expect(entry?.message).toContain('金额列填了文本')
    await entry?.retry()
    expect(c.retry).toHaveBeenCalledTimes(1)
    expect(c.state.value).toBe('merging_in_background')
    expect(backgroundMergeOf(WP)?.status).toBe('merging')
    expect(c.trackers).toHaveLength(2)
    c.last().deliver(APPLIED(13))
    await flushPromises()
    expect(c.reloadHtml).toHaveBeenCalledWith(13)
    expect(c.state.value).toBe('html_idle')
  })

  it('失权 / 等超时各给自己的原因；刷新状态重新追踪', async () => {
    const stale = companion()
    stale.merge.continueInBackground()
    stale.last().deliver(snapshot({ state: 'authorization_stale', terminal: true }))
    await flushPromises()
    expect(backgroundMergeOf(WP)?.message).toBe(BACKGROUND_MERGE_TEXT.authorization)
    clearBackgroundMerges()

    const slow = companion()
    slow.merge.continueInBackground()
    slow.last().deadline()
    expect(slow.state.value).toBe('background_merge_failed')
    expect(backgroundMergeOf(WP)?.message).toBe(BACKGROUND_MERGE_TEXT.timeout)
    await backgroundMergeOf(WP)?.refresh()
    expect(slow.state.value).toBe('merging_in_background')
    expect(slow.trackers).toHaveLength(2)
  })

  it('落地但表单重载失败 ⇒ 失败态、lease 不放；刷新后再落地即完成', async () => {
    const c = companion()
    c.reloadHtml.mockRejectedValueOnce(new Error('network'))
    c.merge.continueInBackground()
    c.last().deliver(APPLIED(12))
    await flushPromises()
    expect(c.state.value).toBe('background_merge_failed')
    expect(backgroundMergeOf(WP)?.message).toBe(BACKGROUND_MERGE_TEXT.reloadFailed)
    expect(c.finishSession).not.toHaveBeenCalled()
    await backgroundMergeOf(WP)?.refresh()
    c.last().deliver(APPLIED(12))
    await flushPromises()
    expect(c.state.value).toBe('html_idle')
    expect(c.finishSession).toHaveBeenCalledTimes(1)
  })

  it('关闭提示 ⇒ 释放 lease、回表单、注销', async () => {
    const c = companion()
    c.merge.continueInBackground()
    c.last().deliver(snapshot({ state: 'conflict', terminal: true }))
    await flushPromises()
    await backgroundMergeOf(WP)?.dismiss()
    expect(c.calls.slice(-2)).toEqual(['finish', 'reset'])
    expect(c.state.value).toBe('html_idle')
    expect(backgroundMergeOf(WP)).toBeNull()
  })

  it('刷新状态换了追踪器后，旧追踪器迟到的快照 / 到点都不打断新一轮', async () => {
    const c = companion()
    c.merge.continueInBackground()
    const first = c.last()
    first.deadline()
    expect(c.state.value).toBe('background_merge_failed')
    await backgroundMergeOf(WP)?.refresh()
    expect(c.state.value).toBe('merging_in_background')
    first.deadline()
    first.deliver(snapshot({ state: 'conflict', terminal: true }))
    await flushPromises()
    expect(c.state.value, '旧追踪器不再起作用').toBe('merging_in_background')
    expect(backgroundMergeOf(WP)?.status).toBe('merging')
    c.last().deliver(APPLIED(12))
    await flushPromises()
    expect(c.state.value).toBe('html_idle')
  })

  it('卸载 ⇒ 停追踪、注销、不改状态；被停掉的追踪器迟到的快照不再起作用', async () => {
    const c = companion()
    c.merge.continueInBackground()
    const tracker = c.last()
    c.merge.dispose()
    expect(tracker.stopped).toBeGreaterThan(0)
    expect(backgroundMergeOf(WP)).toBeNull()
    tracker.deliver(APPLIED(12))
    tracker.deadline()
    await flushPromises()
    expect(c.reloadHtml).not.toHaveBeenCalled()
    expect(c.state.value).toBe('merging_in_background')
  })

  it('文件还没在服务端耐久时拒绝转后台（关编辑器可能丢改动），不登记、不追踪', () => {
    for (const state of ['waiting_application', 'oo_editing', 'forcesave_frozen', 'applied'] as const) {
      const c = companion(state)
      expect(() => c.merge.continueInBackground(), state).toThrow(/文件还没在服务端耐久/)
      expect(c.trackers, state).toHaveLength(0)
      expect(backgroundMergeOf(WP), state).toBeNull()
    }
  })
})

describe('快照 → 后台合并结论（纯函数）', () => {
  it.each([
    [{ state: 'applied', resultRevision: 7 }, 'landed'],
    [{ state: 'applying', resultRevision: null }, 'wait'],
    [{ state: 'refresh_required' }, 'landed'],
    [{ state: 'superseded' }, 'landed'],
    [{ state: 'duplicate', shape: 'duplicate', duplicateOfOperationId: UUID(31) }, 'landed'],
    [{ state: 'conflict' }, 'failed'],
    [{ state: 'authorization_stale' }, 'failed'],
    [{ state: 'error' }, 'failed'],
    [{ state: 'rejected' }, 'failed'],
    [{ state: 'merging' }, 'wait'],
    [{ state: 'extracting' }, 'wait'],
    [{ state: 'rematerializing' }, 'wait'],
    [{ state: 'application_bound' }, 'wait'],
  ] as const)('%o ⇒ %s', (over, kind) => {
    expect(backgroundMergeVerdict(snapshot(over as Partial<WorkpaperSyncOperationSnapshot>)).kind).toBe(kind)
  })

  it('落地 revision 取快照的结果 revision；需重载 / 折叠没有结果 revision 时按最新加载（0）', () => {
    expect(backgroundMergeVerdict(APPLIED(7))).toMatchObject({ kind: 'landed', revision: 7 })
    expect(backgroundMergeVerdict(snapshot({ state: 'refresh_required' }))).toMatchObject({ revision: 0 })
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 3. 桥
// ═══════════════════════════════════════════════════════════════════════════

function descriptorFixture(): WorkpaperSyncEditorLaunchDescriptor {
  return {
    operationId: UUID(20), roomId: UUID(21), participantId: UUID(22), docKey: 'dockey-1', generation: 3,
    serverAppliedRevision: 11, clientConfirmedBaseRevision: 10, contentVersionId: UUID(23),
    representationId: UUID(24), representationGeneration: 2, artifactSha256: DIGEST(1), writeFenceEpoch: 5,
    authorityModel: 'projection_contract', authorityModelDefinitionSha256: DIGEST(2),
    definitionBundleId: UUID(25), definitionBundleSha256: DIGEST(3),
    definitionBundleSlots: {
      template: { type: 'excel_template', sha256: DIGEST(4) },
      instrumentation: { type: 'excel_instrumentation', sha256: DIGEST(5) },
      contract: { type: 'sync_contract', sha256: DIGEST(6) },
    },
    documentType: 'xlsx', mode: 'edit',
    onlyofficeConfig: {
      document: { key: 'dockey-1', fileType: 'xlsx', title: 'd2.xlsx', url: 'https://x/y.xlsx' },
      documentType: 'cell',
      editorConfig: { mode: 'edit', customization: { forcesave: false } },
    },
    replayed: false,
  }
}

function makeBridge(getOperation: (...args: unknown[]) => Promise<WorkpaperSyncOperationSnapshot>) {
  const api = {
    createPendingMutation: vi.fn(async () => ({
      pendingMutationToken: 'tok-1', expectedRevision: 11, payloadSha256: DIGEST(7),
      expiresAt: '2026-08-16T00:05:00Z', idempotencyKey: 'idem-1',
    })),
    materialize: vi.fn(async () => descriptorFixture()),
    confirmDescriptor: vi.fn(async () => ({
      confirmationId: UUID(26), roomId: UUID(21), participantId: UUID(22), generation: 3,
      representationId: UUID(24), contentVersionId: UUID(23), roomState: 'active', replayed: false,
      forcesaveUnlocked: true,
    })),
    requestForcesave: vi.fn(async () => ({
      forcesaveRequestId: UUID(29), operationId: OP, requestSequence: 7, state: 'accepted' as const,
      pollAfterMs: 50, replayed: false, dispatchError: null, csError: 0, csOutcome: 'accepted',
      callbackExpected: true,
    })),
    createCloseIntent: vi.fn(async () => ({})),
    leaveRoom: vi.fn(async () => ({ participant_id: UUID(22), state: 'left', replayed: false })),
    getOperation: vi.fn(getOperation),
    retryOperation: vi.fn(async () => ({ retried: true })),
  }
  const reloadHtml = vi.fn(async () => {})
  const bridge = useWorkpaperSyncBridge({
    entryId: ref(SCOPE.entryId), wpId: ref(WP), projectId: ref(SCOPE.projectId), sheetKey: ref('d22-managed'),
    capability: 'bidirectional',
    flushHtml: vi.fn(async () => ({ expectedRevision: 11, projection: { rows: [] } })),
    reloadHtml,
    api: api as unknown as WorkpaperSyncApiSurface,
    storage: null,
    installBeforeUnload: false,
    deliveryWaitMs: 30,
  })
  return { bridge, api, reloadHtml }
}

async function toMerging(h: ReturnType<typeof makeBridge>) {
  await h.bridge.switchToOnlyOffice()
  h.bridge.notifyEditorMounted()
  await h.bridge.notifyDocumentReady()
  h.bridge.notifyDirty(true)
  h.bridge.notifyDirty(false)
  await h.bridge.switchToHtml()
  expect(h.bridge.state.value).toBe('waiting_application')
  h.bridge.ingestOperationSnapshot(snapshot({ state: 'merging' }))
  expect(h.bridge.state.value).toBe('merging')
}

describe('桥：后台阶段追踪归桥', () => {
  it('转后台后表单模式；桥自己经 api 读到落地 ⇒ 按结果 revision 重载、恰一次 leave、回表单', async () => {
    const h = makeBridge(async () => APPLIED(12))
    await toMerging(h)
    h.bridge.continueInBackground()
    expect(h.bridge.state.value).toBe('merging_in_background')
    expect(h.bridge.mode.value).toBe('html')
    expect(h.bridge.leaveBlockReason.value, '后台合并不阻断关页').toBeNull()
    await flushPromises()
    expect(h.api.getOperation).toHaveBeenCalled()
    expect(h.reloadHtml).toHaveBeenCalledWith(12)
    expect(h.api.leaveRoom).toHaveBeenCalledTimes(1)
    expect(h.bridge.state.value).toBe('html_idle')
    expect(isBackgroundMerging(WP)).toBe(false)
    expect(h.bridge.operation.value?.resultRevision, '桥的 operation 投影随后台快照更新').toBe(12)
  })

  it('合并中再进在线编辑 ⇒ 中文拒绝、不发任何请求', async () => {
    const h = makeBridge(async () => snapshot({ state: 'merging' }))
    await toMerging(h)
    h.bridge.continueInBackground()
    await flushPromises()
    const calls = h.api.createPendingMutation.mock.calls.length
    await expect(h.bridge.switchToOnlyOffice()).rejects.toMatchObject({
      code: 'bridge_background_merge_in_progress',
    })
    await expect(h.bridge.switchToOnlyOffice()).rejects.toThrow(/正在合并在线编辑的改动/)
    expect(h.api.createPendingMutation.mock.calls.length).toBe(calls)
  })

  it('桥销毁 ⇒ 停追踪、注销（服务端照常完成）', async () => {
    const h = makeBridge(async () => snapshot({ state: 'merging' }))
    await toMerging(h)
    h.bridge.continueInBackground()
    await flushPromises()
    expect(isBackgroundMerging(WP)).toBe(true)
    h.bridge.destroy()
    expect(isBackgroundMerging(WP)).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 4. 宿主
// ═══════════════════════════════════════════════════════════════════════════

let editors: Array<{ events: WorkpaperSyncDocEditorEvents }> = []
const LIVE: VueWrapper[] = []

function docsApiStub(): WorkpaperSyncDocsApi {
  return {
    DocEditor: class {
      constructor(_id: string, config: Record<string, unknown>) {
        editors.push({ events: config.events as WorkpaperSyncDocEditorEvents })
      }
    } as unknown as WorkpaperSyncDocsApi['DocEditor'],
  }
}

async function mountEditing(h: ReturnType<typeof makeBridge>): Promise<VueWrapper> {
  const wrapper = mount(WorkpaperSyncEditorHost, {
    props: { descriptor: null, bridge: h.bridge, docsApiLoader: async () => docsApiStub(), trackOperation: true } as never,
    attachTo: document.body,
  })
  LIVE.push(wrapper)
  const descriptor = await h.bridge.switchToOnlyOffice()
  await wrapper.setProps({ descriptor })
  await flushPromises()
  editors[editors.length - 1].events.onDocumentReady()
  await flushPromises()
  expect(h.bridge.state.value).toBe('oo_editing')
  return wrapper
}

afterEach(() => {
  for (const wrapper of LIVE) wrapper.unmount()
  LIVE.length = 0
  editors = []
})

describe('宿主：文件耐久后交给后台合并', () => {
  it('点了保存、宿主追踪读到文件已耐久 ⇒ 停自己的追踪、交给桥，桥落地后回表单', async () => {
    const replies = [snapshot({ state: 'merging' }), APPLIED(12)]
    const h = makeBridge(async () => replies.shift() ?? APPLIED(12))
    const wrapper = await mountEditing(h)
    editors[editors.length - 1].events.onDocumentStateChange({ data: true })
    editors[editors.length - 1].events.onDocumentStateChange({ data: false })
    await wrapper.find('[data-testid="wp-sync-host-forcesave"]').trigger('click')
    await flushPromises()
    await flushPromises()
    expect(h.reloadHtml).toHaveBeenCalledWith(12)
    expect(h.bridge.state.value).toBe('html_idle')
    expect(h.api.leaveRoom).toHaveBeenCalledTimes(1)
    expect(h.bridge.transitions.value).toContain('background_merge_started')
    // 轮询下限 250 ms：等过一个周期，宿主与桥两个追踪器若还有一个在跑必然再读一次。
    const pollsAtLanding = h.api.getOperation.mock.calls.length
    await new Promise((resolve) => setTimeout(resolve, 400))
    await flushPromises()
    expect(h.api.getOperation.mock.calls.length, '落地后两个追踪器都已停').toBe(pollsAtLanding)
    expect(h.bridge.lastError.value).toBeNull()
  })

  it('保存命令受理之后编辑器里又有新改动 ⇒ 不交给后台（人还在编辑）', async () => {
    let release: (value: WorkpaperSyncOperationSnapshot) => void = () => {}
    const first = new Promise<WorkpaperSyncOperationSnapshot>((resolve) => {
      release = resolve
    })
    const h = makeBridge(() => first)
    const wrapper = await mountEditing(h)
    editors[editors.length - 1].events.onDocumentStateChange({ data: true })
    editors[editors.length - 1].events.onDocumentStateChange({ data: false })
    await wrapper.find('[data-testid="wp-sync-host-forcesave"]').trigger('click')
    await flushPromises()
    expect(h.bridge.state.value, '命令已受理、在等回传').toBe('waiting_application')
    editors[editors.length - 1].events.onDocumentStateChange({ data: true }) // 受理之后又改
    expect(h.bridge.dirty.value).toBe(true)
    release(snapshot({ state: 'merging' }))
    await flushPromises()
    expect(h.bridge.state.value).toBe('merging')
    expect(h.bridge.transitions.value).not.toContain('background_merge_started')
  })

  it('不是宿主发起的保存（业务组件直接调桥的 switchToHtml）⇒ 文件耐久后也不转后台', async () => {
    const h = makeBridge(async () => snapshot({ state: 'merging' }))
    await mountEditing(h)
    h.bridge.notifyDirty(true)
    h.bridge.notifyDirty(false)
    await h.bridge.switchToHtml()
    expect(h.bridge.state.value).toBe('waiting_application')
    h.bridge.ingestOperationSnapshot(snapshot({ state: 'merging' }))
    await flushPromises()
    expect(h.bridge.state.value).toBe('merging')
    expect(h.bridge.transitions.value).not.toContain('background_merge_started')
  })

  it('交接时宿主追踪器还有一读在飞 ⇒ 它回来后不再投递（不把旧快照推进已转后台的状态机）', async () => {
    let release: (value: WorkpaperSyncOperationSnapshot) => void = () => {}
    const onSnapshot = vi.fn()
    const tracker = new WorkpaperSyncOperationTracker({
      scope: SCOPE,
      operationId: OP,
      onSnapshot,
      subscribe: () => ({ close: () => {} }),
      poll: () =>
        new Promise<WorkpaperSyncOperationSnapshot>((resolve) => {
          release = resolve
        }),
    })
    const started = tracker.start()
    tracker.stop()
    release(APPLIED(12))
    await started
    expect(onSnapshot).not.toHaveBeenCalled()
    expect(tracker.pollCount, '那一读确实发出去了').toBe(1)
  })

  it('第一份快照就落地 ⇒ 不经后台，走原来的回表单路径', async () => {
    const h = makeBridge(async () => APPLIED(12))
    const wrapper = await mountEditing(h)
    editors[editors.length - 1].events.onDocumentStateChange({ data: true })
    editors[editors.length - 1].events.onDocumentStateChange({ data: false })
    await wrapper.find('[data-testid="wp-sync-host-forcesave"]').trigger('click')
    await flushPromises()
    expect(h.bridge.transitions.value).not.toContain('background_merge_started')
    expect(h.bridge.state.value).toBe('applied')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 5. 登记与持久化
// ═══════════════════════════════════════════════════════════════════════════

describe('登记与持久化拒写', () => {
  const entry = (status: 'merging' | 'failed') => ({
    wpId: WP, status, message: 'x', canRetry: false,
    retry: async () => {}, refresh: async () => {}, dismiss: async () => {},
  })

  it('合并中被拒的写入随即丢弃：合并结束后整体 flush 也不会把旧值补写回去（不盖掉合并结果）', async () => {
    const put = vi.mocked(proxyApi.put)
    put.mockReset()
    put.mockResolvedValue({ item_id: 'D2-1-x', remark: 'v', conclusion: null } as never)
    const persistence = useChecklistPersistence({ wpId: ref(WP), projectId: ref(SCOPE.projectId) })
    const registration = registerBackgroundMerge(entry('merging'))
    await expect(persistence.save('D2-1-x', { remark: '旧值' })).rejects.toThrow(BACKGROUND_MERGE_WRITE_REFUSED_MESSAGE)
    registration.unregister()
    await persistence.flush()
    expect(put).not.toHaveBeenCalled()
  })

  it('横幅：合并中只有说明；失败后三个出口各调登记里的回调，不能重试时不给「重试回写」', async () => {
    const stubs = {
      ElAlert: { props: ['type'], template: '<div class="alert" :data-type="type"><slot name="title" /><slot /></div>' },
      ElButton: { template: '<button @click="$emit(\'click\')"><slot /></button>' },
    }
    const calls: string[] = []
    const registration = registerBackgroundMerge({
      ...entry('merging'),
      message: BACKGROUND_MERGE_TEXT.merging,
      retry: async () => void calls.push('retry'),
      refresh: async () => void calls.push('refresh'),
      dismiss: async () => void calls.push('dismiss'),
    })
    const wrapper = mount(WorkpaperBackgroundMergeBanner, { props: { wpId: WP }, global: { stubs } })
    LIVE.push(wrapper)
    expect(wrapper.find('.alert').attributes('data-type')).toBe('info')
    expect(wrapper.text()).toContain(BACKGROUND_MERGE_TEXT.merging)
    expect(wrapper.findAll('button')).toHaveLength(0)

    registration.entry.status = 'failed'
    registration.entry.message = BACKGROUND_MERGE_TEXT.conflict
    await flushPromises()
    expect(wrapper.find('.alert').attributes('data-type')).toBe('warning')
    expect(wrapper.text()).toContain(BACKGROUND_MERGE_TEXT.conflict)
    expect(wrapper.findAll('button').map((b) => b.text())).toEqual(['刷新状态', '关闭提示'])

    registration.entry.canRetry = true
    await flushPromises()
    const buttons = () => wrapper.findAll('button')
    expect(buttons().map((b) => b.text())).toEqual(['重试回写', '刷新状态', '关闭提示'])
    for (const index of [0, 1, 2]) {
      await buttons()[index].trigger('click')
      await flushPromises()
    }
    expect(calls).toEqual(['retry', 'refresh', 'dismiss'])

    registration.unregister()
    await flushPromises()
    expect(wrapper.find('.alert').exists()).toBe(false)
  })

  it('旧登记注销不误删同一底稿的新登记', () => {
    const first = registerBackgroundMerge(entry('merging'))
    const second = registerBackgroundMerge(entry('merging'))
    first.unregister()
    expect(backgroundMergeOf(WP)).toStrictEqual(second.entry)
    second.unregister()
    expect(backgroundMergeOf(WP)).toBeNull()
  })

  it('合并中拒写且不发请求；失败态 / 注销后照常写', async () => {
    const put = vi.mocked(proxyApi.put)
    put.mockReset()
    put.mockResolvedValue({ item_id: 'D2-1-x', remark: 'v', conclusion: null } as never)
    const persistence = useChecklistPersistence({ wpId: ref(WP), projectId: ref(SCOPE.projectId) })
    const registration = registerBackgroundMerge(entry('merging'))
    await expect(persistence.save('D2-1-x', { remark: 'v' })).rejects.toThrow(BACKGROUND_MERGE_WRITE_REFUSED_MESSAGE)
    expect(put).not.toHaveBeenCalled()
    expect(persistence.stateOf('D2-1-x').lastError).toBe(BACKGROUND_MERGE_WRITE_REFUSED_MESSAGE)
    registration.entry.status = 'failed'
    await persistence.save('D2-1-x', { remark: 'v' })
    expect(put).toHaveBeenCalledTimes(1)
    registration.unregister()
    await persistence.save('D2-1-x', { remark: 'w' })
    expect(put).toHaveBeenCalledTimes(2)
  })
})
