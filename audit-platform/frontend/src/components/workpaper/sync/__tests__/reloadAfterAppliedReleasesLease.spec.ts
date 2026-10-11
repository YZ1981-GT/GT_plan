/**
 * 回写落地后回表单必须释放 participant lease（R13b，2026-10-11 真栈实测）。
 *
 * `reloadAfterApplied()` 此前只清本地 descriptor：服务端 participant 一直 `active` 到
 * 4 小时后的 `expires_at`（重药安徽 room f01c6e40 在 applied + 回表单之后仍挂着一个
 * 「在线编辑者」）。`cleanCloseWithoutSaving.spec.ts` 文件头早就记下过同一现象
 * （「真保存后返回 HTML 的现有成功路径同样不释放 participant」），当时没有修。
 *
 * 本文件锁三条：
 * 1. 回表单恰发一次 leave，身份逐项来自 descriptor；
 * 2. 落地后又改过 ⇒ leave 照实送 `dirty=true`（服务端 dirty 门决定是否释放），不写死 false；
 * 3. leave 失败不阻断回表单、不记 lastError（它是 lease 释放，不是内容操作）。
 */
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import {
  useWorkpaperSyncBridge,
  type WorkpaperSyncApiSurface,
} from '../useWorkpaperSyncBridge'
import type { WorkpaperSyncOperationSnapshot } from '../workpaperSyncDto'

const UUID = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const DIGEST = (n: number) =>
  String(n).repeat(2).padEnd(64, 'abc123def0'.repeat(7)).slice(0, 64)

function applied(): WorkpaperSyncOperationSnapshot {
  return {
    requestedOperationId: UUID(30),
    canonicalOperationId: UUID(30),
    followedDuplicate: false,
    state: 'applied',
    shape: 'primary',
    applicationId: UUID(9),
    duplicateOfOperationId: null,
    errorCode: null,
    errorStage: null,
    acceptedAt: null,
    applicationBoundAt: null,
    operationFinishedAt: null,
    resultRevision: 12,
    conflictCount: null,
    logicalResultCode: 'applied',
    definitionBundleId: null,
    definitionBundleSha256: null,
    authorityModelDefinitionSha256: null,
    durableAt: '2026-10-11T00:00:00Z',
    finishedAt: '2026-10-11T00:00:05Z',
    applicationErrorCode: null,
    applicationErrorStage: null,
    applicationErrorMessage: null,
    terminal: true,
  }
}

const memoryStorage = (): Storage =>
  ({ length: 0, key: () => null, getItem: () => null, setItem: () => {}, removeItem: () => {}, clear: () => {} }) as Storage

function makeBridge(leaveRoom: ReturnType<typeof vi.fn>) {
  const api = {
    createPendingMutation: vi.fn(async () => ({
      pendingMutationToken: 'tok-1',
      expectedRevision: 11,
      payloadSha256: DIGEST(7),
      expiresAt: '2026-10-11T00:05:00Z',
      idempotencyKey: 'idem-1',
    })),
    materialize: vi.fn(async () => ({
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
      writeFenceEpoch: 1,
      authorityModel: 'projection_authoritative' as const,
      authorityModelDefinitionSha256: DIGEST(2),
      definitionBundleId: UUID(25),
      definitionBundleSha256: DIGEST(3),
      definitionBundleSlots: {},
      documentType: 'xlsx',
      mode: 'edit' as const,
      onlyofficeConfig: { document: { key: 'dockey-1', url: 'u', fileType: 'xlsx' } },
      replayed: false,
    })),
    confirmDescriptor: vi.fn(async () => ({
      roomId: UUID(21),
      participantId: UUID(22),
      generation: 3,
      docKey: 'dockey-1',
      writeFenceEpoch: 1,
      forcesaveUnlocked: true,
      serverAppliedRevision: 11,
      clientConfirmedBaseRevision: 10,
    })),
    requestForcesave: vi.fn(async () => ({
      forcesaveRequestId: UUID(29),
      operationId: UUID(30),
      requestSequence: 7,
      state: 'accepted' as const,
      pollAfterMs: 800,
      replayed: false,
      dispatchError: null,
    })),
    leaveRoom,
    getOperation: vi.fn(async () => applied()),
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
    storage: memoryStorage(),
    installBeforeUnload: false,
  })
  return { bridge, api, reloadHtml }
}

async function toApplied(h: ReturnType<typeof makeBridge>): Promise<void> {
  await h.bridge.switchToOnlyOffice()
  h.bridge.notifyEditorMounted()
  await h.bridge.notifyDocumentReady()
  h.bridge.notifyDirty(true)
  await h.bridge.switchToHtml()
  h.bridge.ingestOperationSnapshot(applied())
  expect(h.bridge.state.value).toBe('applied')
}

describe('落地后回表单释放 lease', () => {
  it('恰一次 leave，身份来自 descriptor', async () => {
    const leave = vi.fn(async () => ({ participant_id: UUID(22), state: 'left' }))
    const h = makeBridge(leave)
    await toApplied(h)
    h.bridge.notifyDirty(false)
    await h.bridge.reloadAfterApplied()
    expect(h.reloadHtml).toHaveBeenCalledWith(12)
    expect(h.bridge.mode.value).toBe('html')
    expect(leave).toHaveBeenCalledTimes(1)
    expect((leave.mock.calls[0] as unknown[])[1]).toEqual({
      roomId: UUID(21),
      participantId: UUID(22),
      dirty: false,
    })
    expect(h.bridge.leaveCallCount.value).toBe(1)
  })

  it('落地后又改过 ⇒ 照实送 dirty=true（不写死 false）', async () => {
    const leave = vi.fn(async () => ({ participant_id: UUID(22), state: 'left' }))
    const h = makeBridge(leave)
    await toApplied(h)
    h.bridge.notifyDirty(true)
    await h.bridge.reloadAfterApplied()
    expect(((leave.mock.calls[0] as unknown[])[1] as { dirty: boolean }).dirty).toBe(true)
  })

  it('leave 失败不阻断回表单，也不记 lastError', async () => {
    const leave = vi.fn(async () => {
      throw new Error('network down')
    })
    const h = makeBridge(leave)
    await toApplied(h)
    h.bridge.notifyDirty(false)
    await h.bridge.reloadAfterApplied()
    expect(h.bridge.mode.value).toBe('html')
    expect(h.bridge.state.value).toBe('html_idle')
    expect(h.bridge.lastError.value).toBeNull()
    expect(h.bridge.leaveCallCount.value).toBe(1)
  })

  it('重载失败 ⇒ 不 leave（人还在编辑器里，lease 不能先放掉）', async () => {
    const leave = vi.fn(async () => ({ participant_id: UUID(22), state: 'left' }))
    const h = makeBridge(leave)
    await toApplied(h)
    h.reloadHtml.mockRejectedValueOnce(new Error('表单重载失败'))
    await expect(h.bridge.reloadAfterApplied()).rejects.toBeTruthy()
    expect(leave).not.toHaveBeenCalled()
  })
})
