/**
 * 在线编辑回表单不得有死路（spec oo-return-to-form-dead-end-and-save-speed R1）。
 *
 * 🔴 真栈形态（2026-10-24 和平药房 2025 D2-2，room g12）：没改任何东西点「保存并回到表单模式」
 * ⇒ Command Service 返回码 4 ⇒ 桥落 `forcesave_frozen`、遮罩盖住编辑器、「同步中…」常亮；
 * 再点一次又是 4（库里两条 `cs_error=4`）；点「结构化视图」被 in-flight 门静默拒绝；
 * 唯一出口是刷新页面（弹「离开此网站」）。而后端契约对返回码 4 写的是「直接放行离开」。
 *
 * 本文件钉住五件事：
 * 1. 状态机：无改动放行边、冻结态的 clean close / reset、每个退出状态都接受 reset；
 * 2. 送达等待：最近一次 `onDocumentStateChange` 为 true 时先等 false 再发强制保存；
 * 3. 返回码 4：已送达 ⇒ 放行离开（恰一次 leave）；未送达 ⇒ 冻结且 dirty 保留；
 * 4. 冻结态不算同步进行中；error 态 clean close 先判边、零请求；
 * 5. 退出在线编辑：只在退出状态可用，尽力 leave + 重载表单 + 回 html_idle。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ref } from 'vue'

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return {
    ...actual,
    ElMessage: { info: vi.fn(), warning: vi.fn(), error: vi.fn(), success: vi.fn() },
    ElMessageBox: { confirm: vi.fn() },
  }
})

import { ElMessage, ElMessageBox } from 'element-plus'

import WorkpaperSyncEditorHost from '../WorkpaperSyncEditorHost.vue'
import {
  WP_BRIDGE_EXIT_STATES,
  WP_BRIDGE_FORCESAVE_READY_STATES,
  WP_BRIDGE_IN_FLIGHT_STATES,
  WP_BRIDGE_UNMASKED_STATES,
  useWorkpaperSyncBridge,
  type WorkpaperSyncApiSurface,
  type WorkpaperSyncBridge,
} from '../useWorkpaperSyncBridge'
import {
  WP_BRIDGE_EVENTS,
  WP_BRIDGE_STATES,
  WP_BRIDGE_STATE_MODE,
  canTransition,
  transitionBridgeState,
} from '../workpaperSyncBridgeMachine'
import { FORCESAVE_NO_CHANGES_LEFT_NOTICE, createDeliveryTracker } from '../bridgeForcesaveFlow'
import type { WorkpaperSyncDocEditorEvents, WorkpaperSyncDocsApi } from '../workpaperSyncEditorHostRuntime'
import type { WorkpaperSyncEditorLaunchDescriptor } from '../workpaperSyncDto'
import { WorkpaperSyncContractError } from '../workpaperSyncDto'

const UUID = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const DIGEST = (n: number) => String(n).repeat(2).padEnd(64, 'abc123def0'.repeat(7)).slice(0, 64)

function descriptorFixture(): WorkpaperSyncEditorLaunchDescriptor {
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
    onlyofficeConfig: {
      document: { key: 'dockey-1', fileType: 'xlsx', title: 'd2.xlsx', url: 'https://x/y.xlsx' },
      documentType: 'cell',
      editorConfig: { mode: 'edit', customization: { forcesave: false } },
    },
    replayed: false,
  }
}

function accepted(over: Record<string, unknown> = {}) {
  return {
    forcesaveRequestId: UUID(29),
    operationId: UUID(30),
    requestSequence: 7,
    state: 'accepted' as const,
    pollAfterMs: 800,
    replayed: false,
    dispatchError: null,
    csError: 0,
    csOutcome: 'accepted',
    callbackExpected: true,
    ...over,
  }
}

const NO_CHANGES = { csError: 4, csOutcome: 'no_changes', callbackExpected: false }
const OFFLINE = { csError: 1, csOutcome: 'doc_not_online', callbackExpected: false }

function makeBridge(over: Record<string, unknown> = {}, deliveryWaitMs = 30) {
  const api = {
    createPendingMutation: vi.fn(async () => ({
      pendingMutationToken: 'tok-1',
      expectedRevision: 11,
      payloadSha256: DIGEST(7),
      expiresAt: '2026-08-16T00:05:00Z',
      idempotencyKey: 'idem-1',
    })),
    materialize: vi.fn(async () => descriptorFixture()),
    confirmDescriptor: vi.fn(async () => ({
      confirmationId: UUID(26),
      roomId: UUID(21),
      participantId: UUID(22),
      generation: 3,
      representationId: UUID(24),
      contentVersionId: UUID(23),
      roomState: 'active',
      replayed: false,
      forcesaveUnlocked: true,
    })),
    requestForcesave: vi.fn(async () => accepted()),
    createCloseIntent: vi.fn(async () => ({})),
    leaveRoom: vi.fn(async () => ({ participant_id: UUID(22), state: 'left', replayed: false })),
    getOperation: vi.fn(async () => ({})),
    ...over,
  }
  const reloadHtml = vi.fn(async () => {})
  const bridge = useWorkpaperSyncBridge({
    entryId: ref('xlsx/gt-d2-accounts-receivable'),
    wpId: ref(UUID(102)),
    projectId: ref(UUID(101)),
    sheetKey: ref('d22-managed'),
    capability: 'bidirectional',
    flushHtml: vi.fn(async () => ({ expectedRevision: 11, projection: { rows: [] } })),
    reloadHtml,
    api: api as unknown as WorkpaperSyncApiSurface,
    storage: null,
    installBeforeUnload: false,
    deliveryWaitMs,
  })
  return { bridge, api, reloadHtml }
}

async function toEditing(h: ReturnType<typeof makeBridge>) {
  await h.bridge.switchToOnlyOffice()
  h.bridge.notifyEditorMounted()
  await h.bridge.notifyDocumentReady()
  expect(h.bridge.state.value).toBe('oo_editing')
}

const DETERMINISTIC = WP_BRIDGE_EVENTS.filter(
  (event) => event !== 'operation_observed' && event !== 'recovery_claim_succeeded',
)

// ═══════════════════════════════════════════════════════════════════════════
// 1. 状态机
// ═══════════════════════════════════════════════════════════════════════════

describe('状态机：无改动放行与退出边', () => {
  it('forcesave_requesting 接受 forcesave_no_changes 并回到 html_idle（mode=html）', () => {
    const next = transitionBridgeState('forcesave_requesting', 'forcesave_no_changes', 'oo')
    expect(next.to).toBe('html_idle')
    expect(next.mode).toBe('html')
  })

  it('只有 forcesave_requesting 接受 forcesave_no_changes', () => {
    for (const state of WP_BRIDGE_STATES) {
      expect(canTransition(state, 'forcesave_no_changes'), state).toBe(state === 'forcesave_requesting')
    }
  })

  it('冻结态接受 clean close 与 reset；clean close 仍只在 oo_editing / 冻结态合法', () => {
    expect(transitionBridgeState('forcesave_frozen', 'clean_close_completed', 'oo').to).toBe('html_idle')
    expect(transitionBridgeState('forcesave_frozen', 'reset', 'oo').to).toBe('html_idle')
    const accepting = WP_BRIDGE_STATES.filter((s) => canTransition(s, 'clean_close_completed'))
    expect([...accepting].sort()).toEqual(['forcesave_frozen', 'oo_editing'])
  })

  it('每个退出状态都接受 reset（按钮亮起后点了不得抛），且都是在线编辑侧的状态', () => {
    expect(WP_BRIDGE_EXIT_STATES.length).toBeGreaterThan(0)
    for (const state of WP_BRIDGE_EXIT_STATES) {
      expect(transitionBridgeState(state, 'reset', 'oo').to, state).toBe('html_idle')
      expect(['oo', 'inherit']).toContain(WP_BRIDGE_STATE_MODE[state])
    }
  })

  it('canTransition 与 transitionBridgeState 逐对一致（穷举确定性事件）', () => {
    for (const state of WP_BRIDGE_STATES) {
      for (const event of DETERMINISTIC) {
        let legal = true
        try {
          transitionBridgeState(state, event, 'oo', {
            requestedOperationId: UUID(30),
            successorIntentId: UUID(31),
          })
        } catch {
          legal = false
        }
        expect(canTransition(state, event), `${state} × ${event}`).toBe(legal)
      }
    }
  })

  it('冻结态不在 in-flight 集合、编辑器不遮罩、仍可重发强制保存', () => {
    expect(WP_BRIDGE_IN_FLIGHT_STATES).not.toContain('forcesave_frozen')
    expect(WP_BRIDGE_UNMASKED_STATES).toContain('forcesave_frozen')
    expect(WP_BRIDGE_FORCESAVE_READY_STATES).toContain('forcesave_frozen')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 2. 送达跟踪
// ═══════════════════════════════════════════════════════════════════════════

describe('送达跟踪', () => {
  it('从未编辑 / 最近一次为 false ⇒ 立即视为已送达', async () => {
    const tracker = createDeliveryTracker()
    await expect(tracker.waitDelivered(10_000)).resolves.toBe(true)
    tracker.note(true)
    tracker.note(false)
    await expect(tracker.waitDelivered(10_000)).resolves.toBe(true)
  })

  // 等待上限给到 60 s、只看 50 ms 内有没有结算：「靠超时兜底才结算」与「事件到达即结算」必须分得开。
  const settledWithin = <T,>(promise: Promise<T>, ms = 50) =>
    Promise.race([promise, new Promise<'pending'>((resolve) => setTimeout(() => resolve('pending'), ms))])

  it('最近一次为 true ⇒ 等到 false 才算送达（false 到达即结算）', async () => {
    const tracker = createDeliveryTracker()
    tracker.note(true)
    const waiting = tracker.waitDelivered(60_000)
    await expect(settledWithin(waiting)).resolves.toBe('pending')
    tracker.note(false)
    await expect(settledWithin(waiting)).resolves.toBe(true)
  })

  it('等到上限仍未送达 ⇒ false；会话重置 ⇒ 等待者立即以 false 结算', async () => {
    const tracker = createDeliveryTracker()
    tracker.note(true)
    await expect(tracker.waitDelivered(5)).resolves.toBe(false)
    const waiting = tracker.waitDelivered(60_000)
    tracker.reset()
    await expect(settledWithin(waiting)).resolves.toBe(false)
    expect(tracker.pending()).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 3. 桥：返回码 4 与送达等待
// ═══════════════════════════════════════════════════════════════════════════

describe('桥：返回码 4 按契约放行离开', () => {
  it('会话内没编辑过 ⇒ 放行：恰一次 leave（dirty=false）、回 html_idle、不记错误', async () => {
    const h = makeBridge({ requestForcesave: vi.fn(async () => accepted(NO_CHANGES)) })
    await toEditing(h)
    await h.bridge.switchToHtml()
    expect(h.bridge.state.value).toBe('html_idle')
    expect(h.bridge.mode.value).toBe('html')
    expect(h.bridge.lastError.value).toBeNull()
    expect(h.bridge.lastForcesaveOutcome.value).toBe('no_changes_left')
    expect(h.api.leaveRoom).toHaveBeenCalledTimes(1)
    expect((h.api.leaveRoom.mock.calls[0] as unknown[])[1]).toEqual({
      roomId: UUID(21),
      participantId: UUID(22),
      dirty: false,
    })
    expect(h.api.getOperation, '不会有回传就不该轮询').not.toHaveBeenCalled()
  })

  it('编辑已送达（true → false）⇒ 同样放行', async () => {
    const h = makeBridge({ requestForcesave: vi.fn(async () => accepted(NO_CHANGES)) })
    await toEditing(h)
    h.bridge.notifyDirty(true)
    h.bridge.notifyDirty(false)
    await h.bridge.switchToHtml()
    expect(h.bridge.state.value).toBe('html_idle')
    expect(h.bridge.dirty.value).toBe(false)
  })

  it('🔴 编辑未送达（只有 true）⇒ 等到上限后照发，返回码 4 不放行：冻结、dirty 保留、零次 leave', async () => {
    const h = makeBridge({ requestForcesave: vi.fn(async () => accepted(NO_CHANGES)) })
    await toEditing(h)
    h.bridge.notifyDirty(true)
    await h.bridge.switchToHtml()
    expect(h.api.requestForcesave).toHaveBeenCalledTimes(1)
    expect(h.bridge.state.value).toBe('forcesave_frozen')
    expect(h.bridge.dirty.value, '改动可能还在路上，不得当成已保存').toBe(true)
    expect(h.bridge.lastError.value?.errorCode).toBe('forcesave_no_changes_undelivered')
    expect(h.bridge.lastError.value?.message).toContain('改动还在发送')
    expect(h.api.leaveRoom).not.toHaveBeenCalled()
  })

  it('等送达期间不发命令；送达后才发', async () => {
    // 上限 60 s 远超用例超时：只有「false 到达即放行」才能在时限内走完。
    const h = makeBridge({}, 60_000)
    await toEditing(h)
    h.bridge.notifyDirty(true)
    const saving = h.bridge.switchToHtml()
    await flushPromises()
    expect(h.bridge.state.value).toBe('forcesave_requesting')
    expect(h.api.requestForcesave, '改动还没送到文档服务就发命令 ⇒ 返回码 4 不可信').not.toHaveBeenCalled()
    h.bridge.notifyDirty(false)
    await saving
    expect(h.api.requestForcesave).toHaveBeenCalledTimes(1)
    expect(h.bridge.state.value).toBe('waiting_application')
  })

  it('🔴 等送达期间编辑器出错 ⇒ 不再发强制保存命令（状态已被推走，出站只会再撞一次非法转换）', async () => {
    const h = makeBridge({}, 60_000)
    await toEditing(h)
    h.bridge.notifyDirty(true)
    const saving = h.bridge.switchToHtml()
    await flushPromises()
    h.bridge.notifyHostFailure('editor_runtime', new Error('boom'))
    expect(h.bridge.state.value).toBe('error')
    h.bridge.notifyDirty(false)
    await expect(saving).rejects.toMatchObject({ code: 'bridge_forcesave_superseded' })
    expect(h.api.requestForcesave).not.toHaveBeenCalled()
    expect(h.bridge.state.value).toBe('error')
  })

  it('会话不在线（返回码 1）⇒ 冻结、dirty 保留、文案指向「退出在线编辑」', async () => {
    const h = makeBridge({ requestForcesave: vi.fn(async () => accepted(OFFLINE)) })
    await toEditing(h)
    h.bridge.notifyDirty(true)
    h.bridge.notifyDirty(false)
    await h.bridge.switchToHtml()
    expect(h.bridge.state.value).toBe('forcesave_frozen')
    expect(h.bridge.dirty.value).toBe(true)
    expect(h.bridge.lastError.value?.message).toContain('退出在线编辑')
    expect(h.bridge.canExit.value).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 4. 冻结态 / error 态的离开
// ═══════════════════════════════════════════════════════════════════════════

describe('桥：冻结态可离开，error 态 clean close 先判边', () => {
  it('命令未受理（冻结）且未改动 ⇒ clean close 放行：恰一次 leave、回 html_idle', async () => {
    const h = makeBridge({ requestForcesave: vi.fn(async () => accepted({ dispatchError: 'cs_unreachable' })) })
    await toEditing(h)
    await h.bridge.switchToHtml()
    expect(h.bridge.state.value).toBe('forcesave_frozen')
    expect(h.bridge.canLeave.value, '冻结态没有东西在飞').toBe(true)
    await h.bridge.leaveWithoutSaving()
    expect(h.bridge.state.value).toBe('html_idle')
    expect(h.api.leaveRoom).toHaveBeenCalledTimes(1)
  })

  it('🔴 error 态 clean close 被拒且**零次** leave（原先先发 leave 再抛：人留在 OO、lease 已释放）', async () => {
    const h = makeBridge()
    await toEditing(h)
    h.bridge.notifyHostFailure('editor_runtime', new Error('boom'))
    expect(h.bridge.state.value).toBe('error')
    await expect(h.bridge.leaveWithoutSaving()).rejects.toThrow(WorkpaperSyncContractError)
    expect(h.api.leaveRoom).not.toHaveBeenCalled()
    expect(h.bridge.mode.value).toBe('oo')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 5. 退出在线编辑
// ═══════════════════════════════════════════════════════════════════════════

describe('桥：退出在线编辑', () => {
  it('error 态 ⇒ 尽力 leave（送真实 dirty）+ 重载表单 + 回 html_idle、清掉错误', async () => {
    const h = makeBridge()
    await toEditing(h)
    h.bridge.notifyDirty(true)
    h.bridge.notifyHostFailure('editor_runtime', new Error('boom'))
    expect(h.bridge.canExit.value).toBe(true)
    await h.bridge.exitOnlineEdit()
    expect(h.bridge.state.value).toBe('html_idle')
    expect(h.bridge.mode.value).toBe('html')
    expect(h.bridge.lastError.value).toBeNull()
    expect(h.api.leaveRoom).toHaveBeenCalledTimes(1)
    expect((h.api.leaveRoom.mock.calls[0] as unknown[])[1]).toMatchObject({ dirty: true })
    expect(h.reloadHtml).toHaveBeenCalledTimes(1)
  })

  it('leave 与重载都失败也照样退出', async () => {
    const h = makeBridge({
      requestForcesave: vi.fn(async () => accepted(OFFLINE)),
      leaveRoom: vi.fn(async () => { throw new Error('409') }),
    })
    h.reloadHtml.mockRejectedValueOnce(new Error('net'))
    await toEditing(h)
    await h.bridge.switchToHtml()
    expect(h.bridge.state.value).toBe('forcesave_frozen')
    await h.bridge.exitOnlineEdit()
    expect(h.bridge.state.value).toBe('html_idle')
  })

  it('HTML 侧失败（进入在线编辑前 materialize 失败，mode 仍是 html）⇒ 不提供「退出在线编辑」', async () => {
    const h = makeBridge({ materialize: vi.fn(async () => { throw new Error('500') }) })
    await expect(h.bridge.switchToOnlyOffice()).rejects.toThrow('500')
    expect(h.bridge.state.value).toBe('error')
    expect(h.bridge.mode.value).toBe('html')
    expect(h.bridge.canExit.value, '还没进在线编辑，没有可退出的会话').toBe(false)
  })

  it('不在退出状态（正常编辑中）⇒ 拒绝且不发任何请求', async () => {
    const h = makeBridge()
    await toEditing(h)
    expect(h.bridge.canExit.value).toBe(false)
    await expect(h.bridge.exitOnlineEdit()).rejects.toThrow(WorkpaperSyncContractError)
    expect(h.api.leaveRoom).not.toHaveBeenCalled()
    expect(h.reloadHtml).not.toHaveBeenCalled()
    expect(h.bridge.state.value).toBe('oo_editing')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 6. 宿主
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

async function mountEditing(bridge: WorkpaperSyncBridge): Promise<VueWrapper> {
  const wrapper = mount(WorkpaperSyncEditorHost, {
    props: { descriptor: null, bridge, docsApiLoader: async () => docsApiStub(), trackOperation: false } as never,
    attachTo: document.body,
  })
  LIVE.push(wrapper)
  const descriptor = await bridge.switchToOnlyOffice()
  await wrapper.setProps({ descriptor })
  await flushPromises()
  editors[editors.length - 1].events.onDocumentReady()
  await flushPromises()
  expect(bridge.state.value).toBe('oo_editing')
  return wrapper
}

const find = (wrapper: VueWrapper, id: string) => wrapper.find(`[data-testid="${id}"]`)

beforeEach(() => {
  editors = []
  vi.mocked(ElMessage.info).mockClear()
  vi.mocked(ElMessageBox.confirm).mockReset()
})

afterEach(() => {
  for (const wrapper of LIVE) wrapper.unmount()
  LIVE.length = 0
})

describe('宿主：按钮分流、遮罩与退出', () => {
  it('未改动点「保存并回到表单模式」⇒ 恰一次 leave、零次强制保存、回到表单', async () => {
    const h = makeBridge()
    const wrapper = await mountEditing(h.bridge)
    await find(wrapper, 'wp-sync-host-forcesave').trigger('click')
    await flushPromises()
    expect(h.api.requestForcesave).not.toHaveBeenCalled()
    expect(h.api.leaveRoom).toHaveBeenCalledTimes(1)
    expect(h.bridge.state.value).toBe('html_idle')
  })

  it('改过 ⇒ 强制保存；返回码 4（已送达）⇒ 放行离开并提示「已回到表单」', async () => {
    const h = makeBridge({ requestForcesave: vi.fn(async () => accepted(NO_CHANGES)) })
    const wrapper = await mountEditing(h.bridge)
    editors[editors.length - 1].events.onDocumentStateChange({ data: true })
    editors[editors.length - 1].events.onDocumentStateChange({ data: false })
    await find(wrapper, 'wp-sync-host-forcesave').trigger('click')
    await flushPromises()
    expect(h.api.requestForcesave).toHaveBeenCalledTimes(1)
    expect(h.bridge.state.value).toBe('html_idle')
    expect(ElMessage.info).toHaveBeenCalledWith(FORCESAVE_NO_CHANGES_LEFT_NOTICE)
  })

  it('冻结态：编辑器不遮罩、「退出在线编辑」出现', async () => {
    const h = makeBridge({ requestForcesave: vi.fn(async () => accepted(OFFLINE)) })
    const wrapper = await mountEditing(h.bridge)
    editors[editors.length - 1].events.onDocumentStateChange({ data: true })
    editors[editors.length - 1].events.onDocumentStateChange({ data: false })
    await find(wrapper, 'wp-sync-host-forcesave').trigger('click')
    await flushPromises()
    expect(h.bridge.state.value).toBe('forcesave_frozen')
    expect(find(wrapper, 'wp-sync-host-mask').exists(), '提示让用户在编辑器里操作，遮罩不得挡住').toBe(false)
    expect(find(wrapper, 'wp-sync-host-exit').exists()).toBe(true)
  })

  it('有改动时退出先确认：取消 ⇒ 留在编辑器；确认 ⇒ 回到表单', async () => {
    const h = makeBridge({ requestForcesave: vi.fn(async () => accepted(OFFLINE)) })
    const wrapper = await mountEditing(h.bridge)
    editors[editors.length - 1].events.onDocumentStateChange({ data: true })
    editors[editors.length - 1].events.onDocumentStateChange({ data: false })
    await find(wrapper, 'wp-sync-host-forcesave').trigger('click')
    await flushPromises()

    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await find(wrapper, 'wp-sync-host-exit').trigger('click')
    await flushPromises()
    expect(ElMessageBox.confirm).toHaveBeenCalledTimes(1)
    expect(h.bridge.state.value).toBe('forcesave_frozen')
    expect(h.api.leaveRoom).not.toHaveBeenCalled()

    vi.mocked(ElMessageBox.confirm).mockResolvedValueOnce('confirm' as never)
    await find(wrapper, 'wp-sync-host-exit').trigger('click')
    await flushPromises()
    expect(h.bridge.state.value).toBe('html_idle')
    expect(h.api.leaveRoom).toHaveBeenCalledTimes(1)
  })

  it('正常编辑中不显示「退出在线编辑」', async () => {
    const h = makeBridge()
    const wrapper = await mountEditing(h.bridge)
    expect(find(wrapper, 'wp-sync-host-exit').exists()).toBe(false)
  })
})
