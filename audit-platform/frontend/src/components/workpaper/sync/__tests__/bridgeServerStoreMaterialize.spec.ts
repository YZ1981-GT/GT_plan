/**
 * 桥的「服务端直取」接线判据（spec workpaper-sync-switch-performance P5 + 需求 1.3 计时）。
 *
 * store 型宿主的 flushHtml = 冲刷待存 + `readStoreProjection` 原样透传。桥在 flushHtml 外包窗口：
 *
 *   1. 宿主原样交回哨兵 ⇒ 只调 `materializeFromStore`（不下载投影、不上传 pending、不调 materialize）；
 *   2. 宿主加工过投影 ⇒ 哨兵不外流，不拦截重跑一次 flushHtml 走客户端路径；
 *   3. 宿主不读 store 投影 ⇒ 客户端路径，flushHtml 只跑一次；
 *   4. 服务端判非 store 型 ⇒ 回落客户端路径，且本桥实例不再尝试；
 *   5. `materialize_substrate_not_published` ⇒ 首版后整链重走（与客户端路径同一逻辑）；
 *   6. 其它失败按原分支失败，**不**回落（回落只会把真实原因换成第二次失败）。
 *
 * 宿主的 flushHtml 调的是**真** `readStoreProjection`（窗口拦截发生在 API 层），http 层 mock。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

const mockGet = vi.fn()
vi.mock('@/utils/http', () => ({
  default: { get: (...args: unknown[]) => mockGet(...args), post: vi.fn() },
}))

import { useWorkpaperSyncBridge, type WorkpaperSyncApiSurface } from '../useWorkpaperSyncBridge'
import { isServerStoreSentinel, readStoreProjection, withServerStoreFlush } from '../workpaperSyncApi'
import { SERVER_STORE_FALLBACK_CODES, SUBSTRATE_NOT_PUBLISHED_CODE } from '../workpaperSyncBridgeFailure'
import type { WorkpaperSyncEditorLaunchDescriptor } from '../workpaperSyncDto'

const UUID = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const DIGEST = 'a'.repeat(64)
const SCOPE = { projectId: UUID(101), wpId: UUID(102), entryId: 'xlsx/gt-d2-accounts-receivable' }

function descriptor(): WorkpaperSyncEditorLaunchDescriptor {
  const slot = { type: 'definition', sha256: DIGEST }
  return {
    operationId: UUID(20), roomId: UUID(21), participantId: UUID(22), docKey: 'dockey-1',
    generation: 1, serverAppliedRevision: 1, clientConfirmedBaseRevision: 1,
    contentVersionId: UUID(23), representationId: UUID(24), representationGeneration: 1,
    artifactSha256: DIGEST, writeFenceEpoch: 1, authorityModel: 'projection_contract',
    authorityModelDefinitionSha256: DIGEST, definitionBundleId: UUID(25), definitionBundleSha256: DIGEST,
    definitionBundleSlots: { template: slot, instrumentation: slot, contract: slot },
    documentType: 'xlsx', mode: 'edit', onlyofficeConfig: { document: { key: 'dockey-1' } },
    replayed: false,
  }
}

function wireError(status: number, errorCode: string, message: string) {
  return { response: { status, data: { code: status, message: { error_code: errorCode, message } } } }
}

const REAL_VALUES = { 'scalars/remark': { value: '甲' } }

beforeEach(() => {
  mockGet.mockReset()
  mockGet.mockResolvedValue({
    data: { expected_revision: 4, field_count: 1, row_count: 0, projection: { values: REAL_VALUES } },
  })
})

/** store 型宿主的 flushHtml（与 GtD2AccountsReceivable 等 30+ 宿主同形：冲刷 + 原样透传）。 */
function storeHost() {
  return vi.fn(async () => {
    const snap = await readStoreProjection(SCOPE)
    return { expectedRevision: snap.expectedRevision, projection: snap.projection, sheetKey: 'd22-managed' }
  })
}

function harness(flushHtml: () => Promise<{ expectedRevision: number; projection: unknown }>, api: Record<string, unknown> = {}) {
  const full: Record<string, unknown> = {
    createPendingMutation: vi.fn(async () => ({
      pendingMutationToken: 'tok-1', expectedRevision: 4, payloadSha256: DIGEST,
      expiresAt: '2026-10-10T00:05:00Z', idempotencyKey: 'idem-1',
    })),
    materialize: vi.fn(async () => descriptor()),
    materializeFromStore: vi.fn(async () => ({ descriptor: descriptor(), fastPath: false, reuseVerdict: 'hit' })),
    withServerStoreFlush,
    confirmDescriptor: vi.fn(async () => ({
      roomId: UUID(21), participantId: UUID(22), generation: 1, docKey: 'dockey-1', writeFenceEpoch: 1,
      forcesaveUnlocked: true, serverAppliedRevision: 1, clientConfirmedBaseRevision: 1,
    })),
    leaveRoom: vi.fn(async () => ({ participant_id: UUID(22), state: 'left' })),
    ...api,
  }
  const bridge = useWorkpaperSyncBridge({
    entryId: ref(SCOPE.entryId), wpId: ref(SCOPE.wpId), projectId: ref(SCOPE.projectId),
    sheetKey: ref('fallback-sheet'), capability: 'bidirectional', flushHtml,
    reloadHtml: async () => {}, api: full as unknown as WorkpaperSyncApiSurface,
    storage: null, installBeforeUnload: false,
  })
  return { bridge, api: full as Record<string, ReturnType<typeof vi.fn>> }
}

/** 一次完整的「进在线编辑 → 就绪确认 → 不保存返回表单」。 */
async function roundTrip(bridge: ReturnType<typeof harness>['bridge']): Promise<void> {
  await bridge.switchToOnlyOffice()
  bridge.notifyEditorMounted()
  await bridge.notifyDocumentReady()
  await bridge.leaveWithoutSaving()
}

describe('store 型宿主原样透传 ⇒ 服务端直取', () => {
  it('只调 materializeFromStore：不下载投影、不建 pending、不调 materialize', async () => {
    const flushHtml = storeHost()
    const h = harness(flushHtml)

    const received = await h.bridge.switchToOnlyOffice()

    expect(received.roomId).toBe(UUID(21))
    expect(mockGet).not.toHaveBeenCalled()
    expect(flushHtml).toHaveBeenCalledTimes(1)
    expect(h.api.materializeFromStore).toHaveBeenCalledTimes(1)
    expect(h.api.materializeFromStore.mock.calls[0]).toEqual([
      SCOPE,
      { sheetKey: 'd22-managed', clientEditEpoch: undefined },
    ])
    expect(h.api.createPendingMutation).not.toHaveBeenCalled()
    expect(h.api.materialize).not.toHaveBeenCalled()
    // 状态机照原边推进，不加新状态。
    expect(h.bridge.state.value).toBe('oo_loading')
    expect(h.bridge.descriptor.value?.roomId).toBe(UUID(21))
    expect([...h.bridge.transitions.value]).toEqual([
      'flush_started', 'pending_mutation_created', 'descriptor_received', 'descriptor_accepted',
    ])
  })

  it.each([
    [false, 'server_store'],
    [true, 'server_store_fast'],
  ] as const)('fastPath=%s ⇒ 计时路径 %s；分段齐全且单调', async (fastPath, path) => {
    const h = harness(storeHost(), {
      materializeFromStore: vi.fn(async () => ({ descriptor: descriptor(), fastPath, reuseVerdict: 'hit' })),
    })

    await roundTrip(h.bridge)

    const timings = h.bridge.switchTimings.value
    expect(timings.path).toBe(path)
    const order = ['writes_flushed', 'html_flushed', 'materialized', 'mounted', 'ready', 'confirmed'] as const
    expect(Object.keys(timings.marks).sort()).toEqual([...order].sort())
    const values = order.map((stage) => timings.marks[stage] as number)
    expect(values.every((v, i) => i === 0 || v >= values[i - 1])).toBe(true)
    expect(timings.marks.pending_created).toBeUndefined()
  })
})

describe('宿主没有原样透传 ⇒ 客户端路径（哨兵不外流）', () => {
  it('宿主加工了投影：不拦截重跑一次 flushHtml，pending 拿到的是真投影', async () => {
    const flushHtml = vi.fn(async () => {
      const snap = await readStoreProjection(SCOPE)
      return { expectedRevision: snap.expectedRevision, projection: { ...snap.projection } }
    })
    const h = harness(flushHtml)

    await h.bridge.switchToOnlyOffice()

    expect(flushHtml).toHaveBeenCalledTimes(2)
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(h.api.materializeFromStore).not.toHaveBeenCalled()
    const projection = h.api.createPendingMutation.mock.calls[0][1].projection
    expect(isServerStoreSentinel(projection)).toBe(false)
    expect(projection).toEqual({ values: REAL_VALUES })
    expect(h.bridge.switchTimings.value.path).toBe('client')
    expect(h.bridge.switchTimings.value.marks.pending_created).toBeTypeOf('number')
  })

  it('宿主不读 store 投影：客户端路径，flushHtml 只跑一次', async () => {
    const own = { values: { 'x/1': { value: 1 } } }
    const flushHtml = vi.fn(async () => ({ expectedRevision: 2, projection: own }))
    const h = harness(flushHtml)

    await h.bridge.switchToOnlyOffice()

    expect(flushHtml).toHaveBeenCalledTimes(1)
    expect(h.api.materializeFromStore).not.toHaveBeenCalled()
    expect(h.api.createPendingMutation.mock.calls[0][1].projection).toBe(own)
  })

  it('API 面未提供直取能力（旧 stub）：客户端路径，行为不变', async () => {
    const flushHtml = storeHost()
    const h = harness(flushHtml, { materializeFromStore: undefined, withServerStoreFlush: undefined })

    await h.bridge.switchToOnlyOffice()

    expect(flushHtml).toHaveBeenCalledTimes(1)
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(h.api.createPendingMutation).toHaveBeenCalledTimes(1)
  })
})

describe('服务端拒绝时的分支', () => {
  it.each([...SERVER_STORE_FALLBACK_CODES])(
    '%s ⇒ 回落客户端路径；同一桥再次切换不再尝试直取',
    async (code) => {
      const flushHtml = storeHost()
      const materializeFromStore = vi.fn(async () => {
        throw wireError(422, code, '该条目不是 store 型')
      })
      const h = harness(flushHtml, { materializeFromStore })

      await roundTrip(h.bridge)
      expect(h.bridge.state.value).toBe('html_idle')
      expect(flushHtml).toHaveBeenCalledTimes(2) // 窗口内一次 + 不拦截重跑一次
      expect(h.api.createPendingMutation).toHaveBeenCalledTimes(1)
      expect(isServerStoreSentinel(h.api.createPendingMutation.mock.calls[0][1].projection)).toBe(false)
      expect(h.bridge.lastError.value).toBeNull()

      await h.bridge.switchToOnlyOffice()
      expect(materializeFromStore).toHaveBeenCalledTimes(1)
      expect(flushHtml).toHaveBeenCalledTimes(3)
      expect(h.api.createPendingMutation).toHaveBeenCalledTimes(2)
    },
  )

  it('substrate_not_published ⇒ 首版恰一次后整链重走（仍走直取）', async () => {
    const ensureFirstPublication = vi.fn(async () => ({
      status: 'published' as const, representationId: UUID(24), representationGeneration: 1, contentRevision: 1,
    }))
    const materializeFromStore = vi
      .fn()
      .mockRejectedValueOnce(wireError(422, SUBSTRATE_NOT_PUBLISHED_CODE, '该底稿尚无已发布版本'))
      .mockResolvedValueOnce({ descriptor: descriptor(), fastPath: false, reuseVerdict: 'hit' })
    const flushHtml = storeHost()
    const h = harness(flushHtml, { materializeFromStore, ensureFirstPublication })

    await h.bridge.switchToOnlyOffice()

    expect(ensureFirstPublication).toHaveBeenCalledTimes(1)
    expect(materializeFromStore).toHaveBeenCalledTimes(2)
    expect(flushHtml).toHaveBeenCalledTimes(2)
    expect(h.api.createPendingMutation).not.toHaveBeenCalled()
    expect(h.bridge.state.value).toBe('oo_loading')
    expect([...h.bridge.transitions.value].filter((e) => e === 'flush_started')).toHaveLength(2)
  })

  it.each([
    ['409 room 不可写', wireError(409, 'room_not_writable', 'room 处于 refresh-required')],
    ['422 契约缺失', wireError(422, 'per_entry_contract_required', '缺契约')],
    ['500 未登记失败', wireError(500, 'some_new_materialize_failure', '服务端错误')],
  ])('%s：不回落、不首版，按原分支失败', async (_label, error) => {
    const ensureFirstPublication = vi.fn()
    const flushHtml = storeHost()
    const h = harness(flushHtml, {
      materializeFromStore: vi.fn(async () => {
        throw error
      }),
      ensureFirstPublication,
    })

    await expect(h.bridge.switchToOnlyOffice()).rejects.toBeTruthy()

    expect(flushHtml).toHaveBeenCalledTimes(1)
    expect(h.api.createPendingMutation).not.toHaveBeenCalled()
    expect(ensureFirstPublication).not.toHaveBeenCalled()
    expect(h.bridge.lastError.value?.stage).toBe('materialize')
    expect(h.bridge.lastError.value?.errorCode).toBe(error.response.data.message.error_code)
  })

  it('请求被去重层取消：干净退回 html_idle，不留 sticky error', async () => {
    const h = harness(storeHost(), {
      materializeFromStore: vi.fn(async () => {
        throw { code: 'ERR_CANCELED', name: 'CanceledError', message: 'canceled' }
      }),
    })

    await expect(h.bridge.switchToOnlyOffice()).rejects.toBeTruthy()

    expect(h.bridge.state.value).toBe('html_idle')
    expect(h.bridge.lastError.value).toBeNull()
  })
})
