/**
 * 离开在线编辑前让编辑器检查正在输入的单元格（spec oo-return-to-form-dead-end-and-save-speed R1.6）。
 *
 * 实测依据（OnlyOffice 9.4，2026-10-25）见 `editorLeaveConfirm.ts` 文件头：单元格输入中不发
 * `onDocumentStateChange`；`requestClose()` 无未保存内容时约 1 ms 回 `onRequestClose`，有则弹编辑器
 * 自己的确认、期间无事件；选「确定」先 true → false 再 `onRequestClose`。
 *
 * 钉住三层：
 * 1. 确认器：探测 / 提示中 / 晚到答复 / 平台兜底确认 / 会话结束；
 * 2. 桥的登记位：没登记同步放行、留下即拒绝且零请求、等待期间状态变了要再判门；
 * 3. 宿主：按钮、晚到「确定」后自动回表单、编辑器无答复时平台确认一定给出口。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ref } from 'vue'

vi.mock('element-plus', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return {
    ...actual,
    ElMessage: { info: vi.fn(), warning: vi.fn(), error: vi.fn(), success: vi.fn() },
    ElMessageBox: { confirm: vi.fn(), close: vi.fn() },
  }
})

import { ElMessage, ElMessageBox } from 'element-plus'

import WorkpaperSyncEditorHost from '../WorkpaperSyncEditorHost.vue'
import { useWorkpaperSyncBridge, type WorkpaperSyncApiSurface } from '../useWorkpaperSyncBridge'
import { BRIDGE_LEAVE_KEPT_CODE, isLeaveKeptRefusal } from '../bridgeLeave'
import {
  LEAVE_CONFIRM_PROBE_MS,
  LEAVE_EDITOR_PROMPT_NOTICE,
  createEditorLeaveConfirm,
  type EditorLeaveConfirmOptions,
} from '../editorLeaveConfirm'
import type { WorkpaperSyncDocEditorEvents, WorkpaperSyncDocsApi } from '../workpaperSyncEditorHostRuntime'
import type { WorkpaperSyncEditorLaunchDescriptor } from '../workpaperSyncDto'
import { WorkpaperSyncContractError } from '../workpaperSyncDto'

const UUID = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const DIGEST = (n: number) => String(n).repeat(2).padEnd(64, 'abc123def0'.repeat(7)).slice(0, 64)

// ═══════════════════════════════════════════════════════════════════════════
// 1. 确认器
// ═══════════════════════════════════════════════════════════════════════════

function confirmer(over: Partial<EditorLeaveConfirmOptions> = {}) {
  const editor = { requestClose: vi.fn() }
  const calls = {
    askDiscard: vi.fn(async () => true),
    dismissAsk: vi.fn(),
    onEditorPrompt: vi.fn(),
    onLateClose: vi.fn(),
  }
  const c = createEditorLeaveConfirm({
    editor: () => editor,
    probeMs: 50,
    ...calls,
    ...over,
  })
  return { c, editor, ...calls }
}

describe('确认器：探测', () => {
  it('没有编辑器 / 编辑器不支持 requestClose ⇒ 当场（同步）放行', () => {
    const none = confirmer({ editor: () => null })
    expect(none.c.confirm()).toBe('close')
    const old = confirmer({ editor: () => ({}) })
    expect(old.c.confirm()).toBe('close')
  })

  it('编辑器在时限内答复 ⇒ 放行，不提示、不问', async () => {
    const h = confirmer()
    h.editor.requestClose.mockImplementation(() => queueMicrotask(() => h.c.handleRequestClose()))
    await expect(h.c.confirm()).resolves.toBe('close')
    expect(h.editor.requestClose).toHaveBeenCalledTimes(1)
    expect(h.onEditorPrompt).not.toHaveBeenCalled()
    expect(h.askDiscard).not.toHaveBeenCalled()
    expect(h.c.prompting).toBe(false)
  })

  it('编辑器无答复 ⇒ 本次留下 + 一次指引，记住「提示中」；不弹平台确认', async () => {
    const h = confirmer()
    await expect(h.c.confirm()).resolves.toBe('stay')
    expect(h.onEditorPrompt).toHaveBeenCalledTimes(1)
    expect(h.askDiscard).not.toHaveBeenCalled()
    expect(h.c.prompting).toBe(true)
  })

  it('并发确认只发一次 requestClose、共用一个结论', async () => {
    const h = confirmer()
    const a = h.c.confirm()
    const b = h.c.confirm()
    expect(b).toBe(a)
    await a
    expect(h.editor.requestClose).toHaveBeenCalledTimes(1)
  })

  it('requestClose 抛错 ⇒ 视为已答复、放行（不得把人挡在编辑器里）', async () => {
    const h = confirmer()
    h.editor.requestClose.mockImplementation(() => {
      throw new Error('iframe gone')
    })
    await expect(h.c.confirm()).resolves.toBe('close')
  })

  it('不是我们发的 onRequestClose（未在探测、也不在提示中）不当作离开请求', () => {
    const h = confirmer()
    h.c.handleRequestClose()
    expect(h.onLateClose).not.toHaveBeenCalled()
  })
})

describe('确认器：提示中', () => {
  async function prompted() {
    const h = confirmer()
    await h.c.confirm()
    expect(h.c.prompting).toBe(true)
    return h
  }

  it('晚到的答复（用户在编辑器里选了「确定」）⇒ 交给宿主重走回表单，且只一次', async () => {
    const h = await prompted()
    h.c.handleRequestClose()
    h.c.handleRequestClose()
    expect(h.onLateClose).toHaveBeenCalledTimes(1)
    expect(h.c.prompting).toBe(false)
  })

  it('又点离开：先再探测；编辑器这次答复了 ⇒ 放行，不弹平台确认', async () => {
    const h = await prompted()
    h.editor.requestClose.mockImplementation(() => queueMicrotask(() => h.c.handleRequestClose()))
    await expect(h.c.confirm()).resolves.toBe('close')
    expect(h.askDiscard).not.toHaveBeenCalled()
    expect(h.c.prompting).toBe(false)
  })

  it('🔴 又点离开且编辑器仍无答复（可能已无响应）⇒ 平台确认兜底：放弃 ⇒ 放行', async () => {
    const h = await prompted()
    await expect(h.c.confirm()).resolves.toBe('close')
    expect(h.editor.requestClose).toHaveBeenCalledTimes(2)
    expect(h.askDiscard).toHaveBeenCalledTimes(1)
    expect(h.c.prompting).toBe(false)
  })

  it('平台确认里选继续编辑 ⇒ 留下，仍在提示中', async () => {
    const h = await prompted()
    h.askDiscard.mockResolvedValueOnce(false)
    await expect(h.c.confirm()).resolves.toBe('stay')
    expect(h.c.prompting).toBe(true)
  })

  it('平台确认期间编辑器先答复 ⇒ 关掉平台确认、本次留下，随后按晚到答复重走回表单', async () => {
    let resolveAsk: (v: boolean) => void = () => {}
    const h = await prompted()
    h.askDiscard.mockImplementationOnce(() => new Promise<boolean>((r) => { resolveAsk = r }))
    const verdict = h.c.confirm()
    await new Promise((r) => setTimeout(r, 80)) // 过了探测时限，平台确认已弹
    expect(h.askDiscard).toHaveBeenCalledTimes(1)
    h.c.handleRequestClose()
    await expect(verdict).resolves.toBe('stay')
    expect(h.dismissAsk).toHaveBeenCalledTimes(1)
    expect(h.onLateClose, '晚到答复在本次结论之后才重走').not.toHaveBeenCalled()
    await new Promise((r) => setTimeout(r, 0))
    expect(h.onLateClose).toHaveBeenCalledTimes(1)
    resolveAsk(true) // 平台确认被关掉后才回来的结论不再起作用
    await flushPromises()
    expect(h.onLateClose).toHaveBeenCalledTimes(1)
  })
})

describe('确认器：会话结束', () => {
  it('探测中会话结束 ⇒ 留下，不提示、不进入提示中', async () => {
    const h = confirmer({ probeMs: 10_000 })
    const verdict = h.c.confirm()
    h.c.reset()
    await expect(verdict).resolves.toBe('stay')
    expect(h.onEditorPrompt).not.toHaveBeenCalled()
    expect(h.c.prompting).toBe(false)
  })

  it('平台确认期间会话结束 ⇒ 关掉确认、留下，不重走回表单', async () => {
    const h = confirmer()
    await h.c.confirm()
    h.askDiscard.mockImplementationOnce(() => new Promise<boolean>(() => {}))
    const verdict = h.c.confirm()
    await new Promise((r) => setTimeout(r, 80))
    h.c.reset()
    await expect(verdict).resolves.toBe('stay')
    expect(h.dismissAsk).toHaveBeenCalledTimes(1)
    await new Promise((r) => setTimeout(r, 0))
    expect(h.onLateClose).not.toHaveBeenCalled()
  })

  it('提示中会话结束 ⇒ 之后的 onRequestClose 不再重走', async () => {
    const h = confirmer()
    await h.c.confirm()
    h.c.reset()
    h.c.handleRequestClose()
    expect(h.onLateClose).not.toHaveBeenCalled()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 2. 桥的登记位
// ═══════════════════════════════════════════════════════════════════════════

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

const NO_CHANGES = { csError: 4, csOutcome: 'no_changes', callbackExpected: false }

function makeBridge(over: Record<string, unknown> = {}) {
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
    requestForcesave: vi.fn(async () => ({
      forcesaveRequestId: UUID(29),
      operationId: UUID(30),
      requestSequence: 7,
      state: 'accepted' as const,
      pollAfterMs: 800,
      replayed: false,
      dispatchError: null,
      ...NO_CHANGES,
    })),
    createCloseIntent: vi.fn(async () => ({})),
    leaveRoom: vi.fn(async () => ({ participant_id: UUID(22), state: 'left', replayed: false })),
    getOperation: vi.fn(async () => ({})),
    ...over,
  }
  const bridge = useWorkpaperSyncBridge({
    entryId: ref('xlsx/gt-d2-accounts-receivable'),
    wpId: ref(UUID(102)),
    projectId: ref(UUID(101)),
    sheetKey: ref('d22-managed'),
    capability: 'bidirectional',
    flushHtml: vi.fn(async () => ({ expectedRevision: 11, projection: { rows: [] } })),
    reloadHtml: vi.fn(async () => {}),
    api: api as unknown as WorkpaperSyncApiSurface,
    storage: null,
    installBeforeUnload: false,
    deliveryWaitMs: 20,
  })
  return { bridge, api }
}

async function toEditing(h: ReturnType<typeof makeBridge>) {
  await h.bridge.switchToOnlyOffice()
  h.bridge.notifyEditorMounted()
  await h.bridge.notifyDocumentReady()
  expect(h.bridge.state.value).toBe('oo_editing')
}

describe('桥：离开前确认的登记位', () => {
  it('没登记 ⇒ clean close 与原来一样同步发出 leave（不多一跳异步）', async () => {
    const h = makeBridge()
    await toEditing(h)
    const leaving = h.bridge.leaveWithoutSaving()
    expect(h.api.leaveRoom, '调用当下就已发出').toHaveBeenCalledTimes(1)
    await leaving
    expect(h.bridge.state.value).toBe('html_idle')
  })

  it('确认器说留下 ⇒ 以 KEPT 码拒绝、零次 leave、仍在编辑', async () => {
    const h = makeBridge()
    await toEditing(h)
    h.bridge.setLeaveConfirmer(() => 'stay')
    let caught: unknown
    try {
      await h.bridge.leaveWithoutSaving()
    } catch (error) {
      caught = error
    }
    expect(caught).toBeInstanceOf(WorkpaperSyncContractError)
    expect((caught as WorkpaperSyncContractError).code).toBe(BRIDGE_LEAVE_KEPT_CODE)
    expect(isLeaveKeptRefusal(caught)).toBe(true)
    expect(h.api.leaveRoom).not.toHaveBeenCalled()
    expect(h.bridge.state.value).toBe('oo_editing')
  })

  it('异步放行 ⇒ 恰一次 leave', async () => {
    const h = makeBridge()
    await toEditing(h)
    h.bridge.setLeaveConfirmer(async () => 'close' as const)
    await h.bridge.leaveWithoutSaving()
    expect(h.api.leaveRoom).toHaveBeenCalledTimes(1)
    expect(h.bridge.state.value).toBe('html_idle')
  })

  it('🔴 等确认期间又编辑了 ⇒ 放行后再判一次门：拒绝且零次 leave', async () => {
    const h = makeBridge()
    await toEditing(h)
    let release: (v: 'close') => void = () => {}
    h.bridge.setLeaveConfirmer(() => new Promise((r) => { release = r }))
    const leaving = h.bridge.leaveWithoutSaving()
    h.bridge.notifyDirty(true)
    release('close')
    await expect(leaving).rejects.toThrow(WorkpaperSyncContractError)
    expect(h.api.leaveRoom).not.toHaveBeenCalled()
    expect(h.bridge.state.value).toBe('oo_editing')
  })

  it('注销只撤自己那一个', async () => {
    const h = makeBridge()
    await toEditing(h)
    const offA = h.bridge.setLeaveConfirmer(() => 'close')
    const offB = h.bridge.setLeaveConfirmer(() => 'stay')
    offA()
    await expect(h.bridge.leaveWithoutSaving()).rejects.toThrow(WorkpaperSyncContractError)
    offB()
    await h.bridge.leaveWithoutSaving()
    expect(h.api.leaveRoom).toHaveBeenCalledTimes(1)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 3. 宿主
// ═══════════════════════════════════════════════════════════════════════════

type EditorMode = 'answer' | 'silent'
let editorMode: EditorMode = 'answer'
let editors: Array<{ events: WorkpaperSyncDocEditorEvents; requestClose: ReturnType<typeof vi.fn> }> = []
const LIVE: VueWrapper[] = []

function docsApiStub(): WorkpaperSyncDocsApi {
  return {
    DocEditor: class {
      requestClose: ReturnType<typeof vi.fn>
      constructor(_id: string, config: Record<string, unknown>) {
        const events = config.events as WorkpaperSyncDocEditorEvents
        this.requestClose = vi.fn(() => {
          if (editorMode === 'answer') queueMicrotask(() => events.onRequestClose?.())
        })
        editors.push({ events, requestClose: this.requestClose })
      }
    } as unknown as WorkpaperSyncDocsApi['DocEditor'],
  }
}

const last = () => editors[editors.length - 1]
const find = (wrapper: VueWrapper, id: string) => wrapper.find(`[data-testid="${id}"]`)

async function mountEditing(bridge: ReturnType<typeof makeBridge>['bridge']): Promise<VueWrapper> {
  const wrapper = mount(WorkpaperSyncEditorHost, {
    props: { descriptor: null, bridge, docsApiLoader: async () => docsApiStub(), trackOperation: false } as never,
    attachTo: document.body,
  })
  LIVE.push(wrapper)
  const descriptor = await bridge.switchToOnlyOffice()
  await wrapper.setProps({ descriptor })
  await flushPromises()
  last().events.onDocumentReady()
  await flushPromises()
  expect(bridge.state.value).toBe('oo_editing')
  return wrapper
}

const waitProbe = () => new Promise((r) => setTimeout(r, LEAVE_CONFIRM_PROBE_MS + 60))

beforeEach(() => {
  editors = []
  editorMode = 'answer'
  vi.mocked(ElMessage.warning).mockClear()
  vi.mocked(ElMessage.info).mockClear()
  vi.mocked(ElMessageBox.confirm).mockReset()
  vi.mocked(ElMessageBox.close).mockClear()
})

afterEach(() => {
  for (const wrapper of LIVE) wrapper.unmount()
  LIVE.length = 0
})

describe('宿主：离开前让编辑器检查正在输入的单元格', () => {
  it('编辑器答复（没有正在输入的单元格）⇒ 恰一次 requestClose、一次 leave、回到表单', async () => {
    const h = makeBridge()
    const wrapper = await mountEditing(h.bridge)
    await find(wrapper, 'wp-sync-host-forcesave').trigger('click')
    await flushPromises()
    expect(last().requestClose).toHaveBeenCalledTimes(1)
    expect(h.api.leaveRoom).toHaveBeenCalledTimes(1)
    expect(h.bridge.state.value).toBe('html_idle')
  })

  it('编辑器在提示（单元格输入中）⇒ 留下、零次 leave、给指引、不显示失败', async () => {
    editorMode = 'silent'
    const h = makeBridge()
    const wrapper = await mountEditing(h.bridge)
    await find(wrapper, 'wp-sync-host-forcesave').trigger('click')
    await waitProbe()
    await flushPromises()
    expect(h.api.leaveRoom).not.toHaveBeenCalled()
    expect(h.bridge.state.value).toBe('oo_editing')
    expect(ElMessage.warning).toHaveBeenCalledWith(expect.objectContaining({ message: LEAVE_EDITOR_PROMPT_NOTICE }))
    expect(find(wrapper, 'wp-sync-host-error').exists(), '用户选择不是失败').toBe(false)
  }, 10_000)

  it('🔴 随后在编辑器里选「确定」（撤销 true→false + 答复）⇒ 自动回到表单：强制保存、返回码 4 放行', async () => {
    editorMode = 'silent'
    const h = makeBridge()
    const wrapper = await mountEditing(h.bridge)
    await find(wrapper, 'wp-sync-host-forcesave').trigger('click')
    await waitProbe()
    await flushPromises()
    expect(h.bridge.state.value).toBe('oo_editing')
    // OnlyOffice「确定」：撤销全部改动（随之 true → false），再答复 onRequestClose。
    last().events.onDocumentStateChange({ data: true })
    last().events.onDocumentStateChange({ data: false })
    last().events.onRequestClose?.()
    await flushPromises()
    await new Promise((r) => setTimeout(r, 50))
    await flushPromises()
    expect(h.api.requestForcesave, '撤销让 dirty 置真 ⇒ 走保存那条路').toHaveBeenCalledTimes(1)
    expect(h.bridge.state.value).toBe('html_idle')
    expect(ElMessage.info).toHaveBeenCalled()
  }, 10_000)

  it('🔴 编辑器一直无答复 ⇒ 第二次点击由平台确认兜底：选放弃 ⇒ 回到表单', async () => {
    editorMode = 'silent'
    vi.mocked(ElMessageBox.confirm).mockResolvedValue('confirm' as never)
    const h = makeBridge()
    const wrapper = await mountEditing(h.bridge)
    await find(wrapper, 'wp-sync-host-forcesave').trigger('click')
    await waitProbe()
    await flushPromises()
    expect(ElMessageBox.confirm).not.toHaveBeenCalled()
    await find(wrapper, 'wp-sync-host-forcesave').trigger('click')
    await waitProbe()
    await flushPromises()
    expect(ElMessageBox.confirm).toHaveBeenCalledTimes(1)
    expect(h.api.leaveRoom).toHaveBeenCalledTimes(1)
    expect(h.bridge.state.value).toBe('html_idle')
  }, 10_000)

  it('平台确认里选继续编辑 ⇒ 留下、零次 leave', async () => {
    editorMode = 'silent'
    vi.mocked(ElMessageBox.confirm).mockRejectedValue('cancel')
    const h = makeBridge()
    const wrapper = await mountEditing(h.bridge)
    for (let i = 0; i < 2; i += 1) {
      await find(wrapper, 'wp-sync-host-forcesave').trigger('click')
      await waitProbe()
      await flushPromises()
    }
    expect(ElMessageBox.confirm).toHaveBeenCalledTimes(1)
    expect(h.api.leaveRoom).not.toHaveBeenCalled()
    expect(h.bridge.state.value).toBe('oo_editing')
  }, 10_000)

  it('探测中编辑器被销毁 ⇒ 等待中的确认就地结算：不弹指引、不进入提示中', async () => {
    editorMode = 'silent'
    const h = makeBridge()
    const wrapper = await mountEditing(h.bridge)
    await find(wrapper, 'wp-sync-host-forcesave').trigger('click')
    await flushPromises()
    await wrapper.setProps({ descriptor: null }) // 宿主据此销毁编辑器
    await waitProbe()
    await flushPromises()
    expect(ElMessage.warning, '编辑器都没了，不该再说「编辑器里还有正在输入的单元格」').not.toHaveBeenCalled()
    expect(h.api.leaveRoom).not.toHaveBeenCalled()
  }, 10_000)

  it('宿主卸载后注销确认器（桥回到「没登记」的同步放行）', async () => {
    editorMode = 'silent'
    const h = makeBridge()
    // 卸载后编辑器已销毁，残留的确认器也只会当场放行 —— 行为上看不出来，直接数注销调用。
    const offs: Array<ReturnType<typeof vi.fn>> = []
    const register = h.bridge.setLeaveConfirmer
    ;(h.bridge as { setLeaveConfirmer: typeof register }).setLeaveConfirmer = (fn) => {
      const off = vi.fn(register(fn))
      offs.push(off)
      return off
    }
    const wrapper = await mountEditing(h.bridge)
    expect(offs).toHaveLength(1)
    wrapper.unmount()
    expect(offs[0], '卸载时必须注销自己登记的确认器').toHaveBeenCalledTimes(1)
    LIVE.splice(LIVE.indexOf(wrapper), 1)
    const leaving = h.bridge.leaveWithoutSaving()
    expect(h.api.leaveRoom).toHaveBeenCalledTimes(1)
    await leaving
  })
})
