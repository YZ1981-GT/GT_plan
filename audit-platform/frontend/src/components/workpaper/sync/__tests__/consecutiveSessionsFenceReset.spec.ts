/**
 * 同一页面里连续两轮在线编辑保存（R18，2026-10-11 真栈实测）。
 *
 * 第一轮：保存 → applied → 回表单。第二轮：再进在线编辑 → 再保存 ⇒ 服务端照常 applied，
 * 但界面卡在「在线编辑不可用」：`refresh_required 不允许经 operation 观测进入
 * application_bound`。根因：application fence（`canonicalApplicationId`）只在 `reset()` 里清，
 * 回表单的路不清 ⇒ 第二轮的 application 与上一轮「不同」⇒ 被判成 superseded/rebase。
 *
 * 本文件锁三条：
 * 1. 第二轮的 application_bound / applied 快照照常推进，最终能回表单；
 * 2. 第二轮开始时上一轮的 operation 观测面已作废；
 * 3. **同一轮内**换了 canonical application 仍判 rebase（修复不得把 fence 本身拆掉）。
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

function snapshot(
  operationId: string,
  applicationId: string,
  state: 'application_bound' | 'applied',
  resultRevision: number | null,
): WorkpaperSyncOperationSnapshot {
  return {
    requestedOperationId: operationId,
    canonicalOperationId: operationId,
    followedDuplicate: false,
    state,
    shape: 'primary',
    applicationId,
    duplicateOfOperationId: null,
    errorCode: null,
    errorStage: null,
    acceptedAt: null,
    applicationBoundAt: '2026-10-11T00:00:01Z',
    operationFinishedAt: state === 'applied' ? '2026-10-11T00:00:05Z' : null,
    resultRevision,
    conflictCount: null,
    logicalResultCode: state === 'applied' ? 'applied' : null,
    definitionBundleId: null,
    definitionBundleSha256: null,
    authorityModelDefinitionSha256: null,
    durableAt: '2026-10-11T00:00:00Z',
    finishedAt: state === 'applied' ? '2026-10-11T00:00:05Z' : null,
    applicationErrorCode: null,
    applicationErrorStage: null,
    applicationErrorMessage: null,
    terminal: state === 'applied',
  }
}

const memoryStorage = (): Storage =>
  ({ length: 0, key: () => null, getItem: () => null, setItem: () => {}, removeItem: () => {}, clear: () => {} }) as Storage

function makeBridge() {
  const forcesave = (operationId: string) => ({
    forcesaveRequestId: UUID(29),
    operationId,
    requestSequence: 1,
    state: 'accepted' as const,
    pollAfterMs: 800,
    replayed: false,
    dispatchError: null,
  })
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
    requestForcesave: vi
      .fn()
      .mockResolvedValueOnce(forcesave(UUID(30)))
      .mockResolvedValueOnce(forcesave(UUID(40))),
    leaveRoom: vi.fn(async () => ({ participant_id: UUID(22), state: 'left' })),
    getOperation: vi.fn(async () => snapshot(UUID(30), UUID(9), 'applied', 12)),
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

async function saveRound(h: ReturnType<typeof makeBridge>): Promise<void> {
  await h.bridge.switchToOnlyOffice()
  h.bridge.notifyEditorMounted()
  await h.bridge.notifyDocumentReady()
  h.bridge.notifyDirty(true)
  await h.bridge.switchToHtml()
}

describe('同一页面连续两轮在线编辑保存', () => {
  it('第二轮的新 application 照常推进到 applied 并回表单', async () => {
    const h = makeBridge()
    await saveRound(h)
    h.bridge.ingestOperationSnapshot(snapshot(UUID(30), UUID(9), 'applied', 12))
    h.bridge.notifyDirty(false)
    await h.bridge.reloadAfterApplied()
    expect(h.bridge.state.value).toBe('html_idle')

    await saveRound(h)
    expect(h.bridge.requestedOperationId.value).toBe(UUID(40))
    h.bridge.ingestOperationSnapshot(snapshot(UUID(40), UUID(19), 'application_bound', null))
    expect(h.bridge.state.value, '新一轮的 application 不是对上一轮的 rebase').toBe(
      'application_bound',
    )
    h.bridge.ingestOperationSnapshot(snapshot(UUID(40), UUID(19), 'applied', 13))
    expect(h.bridge.state.value).toBe('applied')
    h.bridge.notifyDirty(false)
    await h.bridge.reloadAfterApplied()
    expect(h.reloadHtml).toHaveBeenLastCalledWith(13)
    expect(h.bridge.mode.value).toBe('html')
    expect(h.api.leaveRoom).toHaveBeenCalledTimes(2)
  })

  it('新一轮开始时上一轮的 operation 观测面已作废', async () => {
    const h = makeBridge()
    await saveRound(h)
    h.bridge.ingestOperationSnapshot(snapshot(UUID(30), UUID(9), 'applied', 12))
    await h.bridge.reloadAfterApplied()
    expect(h.bridge.canonicalApplicationId.value).toBe(UUID(9))

    await h.bridge.switchToOnlyOffice()
    expect(h.bridge.canonicalApplicationId.value).toBeNull()
    expect(h.bridge.applicationEffectiveSequence.value).toBeNull()
    expect(h.bridge.requestedOperationId.value).toBeNull()
    expect(h.bridge.operation.value).toBeNull()
  })

  it('同一轮内换了 canonical application 仍判 rebase（fence 本身不能拆）', async () => {
    const h = makeBridge()
    await saveRound(h)
    h.bridge.ingestOperationSnapshot(snapshot(UUID(30), UUID(9), 'application_bound', null))
    expect(h.bridge.state.value).toBe('application_bound')
    const rebased = h.bridge.observeApplicationFence({
      applicationId: UUID(99),
      effectiveRequestSequence: 2,
    })
    expect(rebased.rebased).toBe(true)
    expect(h.bridge.state.value).toBe('refresh_required')
  })
})
