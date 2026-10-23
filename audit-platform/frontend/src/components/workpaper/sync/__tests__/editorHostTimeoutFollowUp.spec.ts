// 追踪窗口到点 / 回写失败之后的出口（spec writeback-followup-issue-closure R3.5，承接 R3.4）。
//
// 修前：超时文案让用户点「重试回写」，而那个按钮此刻并不渲染（超时不是可重试裁决）；
// 回调后 apply 在协调器接手前失败（R3.4 现在会落到 operation 上）也只显示原因、不给重试。
// 判据：①超时后出现「刷新状态」，读到的快照只读展示、不喂回 sticky error 的桥；②读到
// 可重试的失败才出现「重试回写」，重试后再读一次显示结果；③新一次保存清掉上一次的结果。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ref } from 'vue'

import WorkpaperSyncEditorHost from '../WorkpaperSyncEditorHost.vue'
import { WP_SYNC_HOST_ERROR_TEXT, type WorkpaperSyncDocsApi } from '../workpaperSyncEditorHostRuntime'
import { useWorkpaperSyncBridge, type WorkpaperSyncApiSurface, type WorkpaperSyncBridge } from '../useWorkpaperSyncBridge'
import { WP_SYNC_OPERATION_STATES } from '../workpaperSyncContract.generated'
import type { WorkpaperSyncEditorLaunchDescriptor, WorkpaperSyncOperationSnapshot } from '../workpaperSyncDto'
import { describeOperationFollowUp, snapshotIsRetryable } from '../workpaperSyncOperationFollowUp'

const UUID = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const DIGEST = (n: number) => String(n).repeat(2).padEnd(64, 'abc123def0'.repeat(7)).slice(0, 64)

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

function snapshot(over: Partial<WorkpaperSyncOperationSnapshot> = {}): WorkpaperSyncOperationSnapshot {
  return {
    requestedOperationId: UUID(30), canonicalOperationId: UUID(30), followedDuplicate: false,
    state: 'accepted', shape: 'pre_correlation', applicationId: null, duplicateOfOperationId: null,
    errorCode: null, errorStage: null, applicationErrorCode: null, applicationErrorStage: null,
    applicationErrorMessage: null, acceptedAt: null, applicationBoundAt: null, operationFinishedAt: null,
    resultRevision: null, conflictCount: null, logicalResultCode: null, definitionBundleId: null,
    definitionBundleSha256: null, authorityModelDefinitionSha256: null, durableAt: null, finishedAt: null,
    terminal: false,
    ...over,
  }
}

const APPLIED = () =>
  snapshot({ state: 'applied', shape: 'primary', applicationId: UUID(9), resultRevision: 12, terminal: true })
/** 回调后 apply 在协调器接手前失败（R3.4：注册 / 绑定找不到 adapter）。 */
const FAILED = (message: string | null = null) =>
  snapshot({
    state: 'error', shape: 'primary', applicationId: UUID(9), errorCode: 'adapter_not_registered',
    errorStage: 'registry', applicationErrorCode: 'adapter_not_registered', applicationErrorMessage: message,
    terminal: true,
  })

let editors: Array<{ events: { onDocumentReady: () => void } }> = []
const LIVE: VueWrapper[] = []

function docsApiStub(): WorkpaperSyncDocsApi {
  return {
    DocEditor: class {
      constructor(_id: string, config: Record<string, unknown>) {
        editors.push({ events: config.events as { onDocumentReady: () => void } })
      }
    } as unknown as WorkpaperSyncDocsApi['DocEditor'],
  }
}

interface Harness {
  bridge: WorkpaperSyncBridge
  getOperation: ReturnType<typeof vi.fn>
  retryOperation: ReturnType<typeof vi.fn>
}

function harness(getOperation: ReturnType<typeof vi.fn>): Harness {
  const retryOperation = vi.fn(async () => ({ result: 'applied' }))
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
      forcesaveRequestId: UUID(29), operationId: UUID(30), requestSequence: 7, state: 'accepted' as const,
      pollAfterMs: 800, replayed: false, dispatchError: null,
    })),
    getOperation,
    retryOperation,
    leaveRoom: vi.fn(async () => ({})),
  }
  const bridge = useWorkpaperSyncBridge({
    entryId: ref('xlsx/gt-d2-accounts-receivable'), wpId: ref(UUID(102)), projectId: ref(UUID(101)),
    sheetKey: ref('D2-2'), capability: 'bidirectional',
    flushHtml: vi.fn(async () => ({ expectedRevision: 11, projection: { rows: [] } })),
    reloadHtml: vi.fn(async () => {}),
    api: api as unknown as WorkpaperSyncApiSurface,
    storage: null,
    installBeforeUnload: false,
  })
  return { bridge, getOperation, retryOperation }
}

async function openEditor(h: Harness, wrapper?: VueWrapper): Promise<VueWrapper> {
  const host = wrapper ?? mount(WorkpaperSyncEditorHost, {
    props: { descriptor: null, bridge: h.bridge, docsApiLoader: async () => docsApiStub() } as never,
    attachTo: document.body,
  })
  if (!wrapper) LIVE.push(host)
  const descriptor = await h.bridge.switchToOnlyOffice()
  await host.setProps({ descriptor })
  await flushPromises()
  editors[editors.length - 1].events.onDocumentReady()
  await flushPromises()
  expect(h.bridge.state.value).toBe('oo_editing')
  return host
}

async function saveAndTimeOut(h: Harness, wrapper: VueWrapper): Promise<void> {
  await (wrapper.vm as unknown as { forceSave: () => Promise<unknown> }).forceSave()
  await vi.advanceTimersByTimeAsync(190_000)
  expect(h.bridge.state.value).toBe('error')
}

const refreshButton = (w: VueWrapper) => w.find('[data-testid="wp-sync-host-refresh-status"]')
const retryButton = (w: VueWrapper) => w.find('[data-testid="wp-sync-host-retry"]')
const followUpText = (w: VueWrapper) => w.find('[data-testid="wp-sync-host-follow-up-text"]')

async function click(el: ReturnType<VueWrapper['find']>): Promise<void> {
  await el.trigger('click')
  await flushPromises()
}

beforeEach(() => {
  editors = []
  vi.useFakeTimers()
})

afterEach(() => {
  for (const wrapper of LIVE) wrapper.unmount()
  LIVE.length = 0
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('追踪窗口到点之后：「刷新状态」', () => {
  it('超时文案点名的按钮此刻真的渲染；「重试回写」不先许诺', async () => {
    const h = harness(vi.fn(async () => snapshot()))
    const wrapper = await openEditor(h)
    await saveAndTimeOut(h, wrapper)
    expect(WP_SYNC_HOST_ERROR_TEXT.editor_host_operation_tracking_timeout).toContain('「刷新状态」')
    expect(refreshButton(wrapper).text()).toBe('刷新状态')
    expect(retryButton(wrapper).exists()).toBe(false)
    expect(followUpText(wrapper).exists()).toBe(false)
  })

  it('刷新到已落地 ⇒ 说明已完成；快照只读，不喂回桥，也不恢复自动轮询', async () => {
    const h = harness(vi.fn(async () => snapshot()))
    const wrapper = await openEditor(h)
    await saveAndTimeOut(h, wrapper)
    h.getOperation.mockResolvedValueOnce(APPLIED())
    const before = h.getOperation.mock.calls.length
    await click(refreshButton(wrapper))
    expect(h.getOperation.mock.calls.length).toBe(before + 1)
    expect(followUpText(wrapper).attributes('data-state')).toBe('applied')
    expect(followUpText(wrapper).text()).toContain('服务器已完成回写（第 12 版）')
    expect(retryButton(wrapper).exists()).toBe(false)
    expect(h.bridge.state.value, '桥是 sticky error，快照不得喂回去').toBe('error')
    const settled = h.getOperation.mock.calls.length
    await vi.advanceTimersByTimeAsync(30_000)
    expect(h.getOperation.mock.calls.length).toBe(settled)
  })

  it('刷新到仍在处理 ⇒ 让用户稍后再刷新，按钮可再点', async () => {
    const h = harness(vi.fn(async () => snapshot()))
    const wrapper = await openEditor(h)
    await saveAndTimeOut(h, wrapper)
    h.getOperation.mockResolvedValueOnce(snapshot({ state: 'merging', shape: 'primary', applicationId: UUID(9) }))
    await click(refreshButton(wrapper))
    expect(followUpText(wrapper).text()).toContain('服务器正在回写这次保存')
    expect(refreshButton(wrapper).attributes('disabled')).toBeUndefined()
  })

  it('取快照本身失败 ⇒ 中文说明，按钮恢复可点', async () => {
    const h = harness(vi.fn(async () => snapshot()))
    const wrapper = await openEditor(h)
    await saveAndTimeOut(h, wrapper)
    h.getOperation.mockRejectedValueOnce(new Error('network down'))
    await click(refreshButton(wrapper))
    expect(followUpText(wrapper).attributes('data-state')).toBe('unavailable')
    expect(followUpText(wrapper).text()).toContain('暂时取不到服务器上的回写状态')
    expect(refreshButton(wrapper).attributes('disabled')).toBeUndefined()
  })

  it('刷新进行中按钮禁用，连点只发一次', async () => {
    const h = harness(vi.fn(async () => snapshot()))
    const wrapper = await openEditor(h)
    await saveAndTimeOut(h, wrapper)
    let release: (value: WorkpaperSyncOperationSnapshot) => void = () => undefined
    h.getOperation.mockImplementationOnce(() => new Promise((resolve) => { release = resolve }))
    const before = h.getOperation.mock.calls.length
    await refreshButton(wrapper).trigger('click')
    await refreshButton(wrapper).trigger('click')
    expect(refreshButton(wrapper).attributes('disabled')).toBeDefined()
    expect(refreshButton(wrapper).text()).toBe('正在刷新…')
    expect(h.getOperation.mock.calls.length).toBe(before + 1)
    release(APPLIED())
    await flushPromises()
    expect(refreshButton(wrapper).text()).toBe('刷新状态')
  })
})

describe('回写失败落在 operation 上 ⇒ 可以重试', () => {
  it('超时后刷新到可重试的失败 ⇒ 出现「重试回写」；重试后再读一次并显示结果', async () => {
    const h = harness(vi.fn(async () => snapshot()))
    const wrapper = await openEditor(h)
    await saveAndTimeOut(h, wrapper)
    h.getOperation.mockResolvedValueOnce(FAILED('找不到这张底稿的回写配置'))
    await click(refreshButton(wrapper))
    expect(followUpText(wrapper).text()).toContain('回写失败：找不到这张底稿的回写配置')
    expect(followUpText(wrapper).text()).toContain('「重试回写」')
    expect(retryButton(wrapper).exists()).toBe(true)

    h.getOperation.mockResolvedValueOnce(APPLIED())
    await click(retryButton(wrapper))
    expect(h.retryOperation).toHaveBeenCalledTimes(1)
    expect(followUpText(wrapper).attributes('data-state')).toBe('applied')
    expect(retryButton(wrapper).exists(), '已落地就不能再重试').toBe(false)
  })

  it('追踪中直接读到失败（协调器接手前失败，R3.4）⇒ 不必等超时就能重试', async () => {
    const getOperation = vi.fn<() => Promise<WorkpaperSyncOperationSnapshot>>()
      .mockResolvedValueOnce(snapshot())
      .mockResolvedValue(FAILED())
    const h = harness(getOperation)
    const wrapper = await openEditor(h)
    await (wrapper.vm as unknown as { forceSave: () => Promise<unknown> }).forceSave()
    await vi.advanceTimersByTimeAsync(2_000)
    expect(h.bridge.state.value).toBe('error')
    expect(h.bridge.lastError.value?.verdict.retryableOperation, '桥只负责摆出原因').toBe(false)
    expect(retryButton(wrapper).exists()).toBe(true)
    expect(refreshButton(wrapper).exists(), '没超时、没重试之前不出现').toBe(false)

    getOperation.mockResolvedValue(APPLIED())
    await click(retryButton(wrapper))
    expect(h.retryOperation).toHaveBeenCalledTimes(1)
    expect(followUpText(wrapper).text()).toContain('服务器已完成回写')
    expect(refreshButton(wrapper).exists(), '重试之后由用户按需再刷新').toBe(true)
  })

  it('失败但没关联回写任务（incoming 未 durable）⇒ 不给重试', async () => {
    const h = harness(vi.fn(async () => snapshot()))
    const wrapper = await openEditor(h)
    await saveAndTimeOut(h, wrapper)
    h.getOperation.mockResolvedValueOnce(
      snapshot({ state: 'error', shape: 'pre_correlation', errorCode: 'callback_download_failed', terminal: true }),
    )
    await click(refreshButton(wrapper))
    expect(followUpText(wrapper).text()).toContain('错误码 callback_download_failed')
    expect(followUpText(wrapper).text()).not.toContain('重试回写')
    expect(retryButton(wrapper).exists()).toBe(false)
  })

  it('重试请求本身失败 ⇒ 记成宿主失败，不去读快照', async () => {
    const h = harness(vi.fn(async () => snapshot()))
    const wrapper = await openEditor(h)
    await saveAndTimeOut(h, wrapper)
    h.getOperation.mockResolvedValueOnce(FAILED())
    await click(refreshButton(wrapper))
    h.retryOperation.mockRejectedValueOnce(Object.assign(new Error('busy'), { response: { status: 409 } }))
    const before = h.getOperation.mock.calls.length
    await click(retryButton(wrapper))
    expect(h.getOperation.mock.calls.length).toBe(before)
    expect(wrapper.find('[data-testid="wp-sync-host-error"]').attributes('data-code')).toBeTruthy()
  })
})

describe('新一次保存清掉上一次的结果', () => {
  it('回表单再进来重新保存（同一个 operation 号）⇒ 旧的「刷新状态」与重试入口不残留', async () => {
    const h = harness(vi.fn(async () => snapshot()))
    const wrapper = await openEditor(h)
    await saveAndTimeOut(h, wrapper)
    h.getOperation.mockResolvedValueOnce(FAILED())
    await click(refreshButton(wrapper))
    expect(retryButton(wrapper).exists()).toBe(true)

    h.bridge.reset()
    await wrapper.setProps({ descriptor: null })
    await flushPromises()
    await openEditor(h, wrapper)
    h.getOperation.mockImplementation(() => new Promise(() => undefined)) // 新一轮还没读到快照
    await (wrapper.vm as unknown as { forceSave: () => Promise<unknown> }).forceSave()
    await flushPromises()
    expect(h.bridge.requestedOperationId.value).toBe(UUID(30))
    expect(refreshButton(wrapper).exists()).toBe(false)
    expect(retryButton(wrapper).exists()).toBe(false)
    expect(followUpText(wrapper).exists()).toBe(false)
  })
})

describe('快照 → 中文说明（穷尽 operation 状态）', () => {
  it('每个后端状态都有中文说明，且不落到「未知状态」', () => {
    for (const state of WP_SYNC_OPERATION_STATES) {
      const view = describeOperationFollowUp(snapshot({ state }))
      expect(view.state, state).toBe(state)
      expect(view.message, state).toMatch(/[\u4e00-\u9fa5]/)
      expect(view.message, state).not.toContain('未知状态')
    }
  })

  it('只有已关联回写任务的 primary 失败才可重试', () => {
    expect(snapshotIsRetryable(FAILED())).toBe(true)
    expect(snapshotIsRetryable(snapshot({ state: 'error', shape: 'primary', applicationId: null }))).toBe(false)
    expect(snapshotIsRetryable(snapshot({ state: 'error', shape: 'pre_correlation' }))).toBe(false)
    expect(snapshotIsRetryable(snapshot({ state: 'conflict', shape: 'primary', applicationId: UUID(9) }))).toBe(false)
    expect(snapshotIsRetryable(APPLIED())).toBe(false)
  })

  it('原因优先用后端中文措辞，没有登记时给错误码，都没有时说原因未知', () => {
    expect(describeOperationFollowUp(FAILED('金额列只能填数字')).message).toContain('回写失败：金额列只能填数字')
    expect(describeOperationFollowUp(FAILED()).message).toContain('回写失败：错误码 adapter_not_registered')
    expect(describeOperationFollowUp(snapshot({ state: 'error' })).message).toContain('回写失败：原因未知')
  })

  it('冲突数与版本号进说明', () => {
    expect(describeOperationFollowUp(snapshot({ state: 'conflict', conflictCount: 3 })).message).toContain(' 3 处冲突')
    expect(describeOperationFollowUp(snapshot({ state: 'refresh_required', resultRevision: 8 })).message)
      .toContain('（第 8 版）')
  })
})
