/**
 * 会话内编辑的 dirty 必须「粘住」，直到强制保存被受理 / CS 回 no_changes（且改动已送达）/ 会话结束。
 *
 * spec: d2-skeleton-slot-reuse-and-writeback-speed · R4；oo-return-to-form-dead-end-and-save-speed · R1.2 / R1.3
 *
 * 真栈实测（重药安徽 D2-2，2026-10-23）：OnlyOffice 每次编辑后约 1 秒内就发
 * `onDocumentStateChange` true→false（false 只表示「改动已发给文档服务」）。旧实现照单全收，
 * 用户改完停一秒点「结构化视图」⇒ 宿主看到 dirty=false 走 clean close，网络里只有一次
 * `…/leave`、没有 forcesave；随后文档服务的 status 2 回调被平台拒收（`state=rejected`），
 * 编辑丢失，下次打开 OO 还弹「该文件已从服务器备份副本打开」。
 */
import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { useWorkpaperSyncBridge, type WorkpaperSyncApiSurface } from '../useWorkpaperSyncBridge'
import { WorkpaperSyncContractError } from '../workpaperSyncDto'

const UUID = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const DIGEST = (n: number) => String(n).repeat(2).padEnd(64, 'abc123def0'.repeat(7)).slice(0, 64)

// 送达等待上限压到 20 ms：「只有 true 没有 false」的用例要等满上限（spec oo-return-to-form-dead-end-and-save-speed R1.2）。
function makeBridge(overrides: Record<string, unknown> = {}, deliveryWaitMs = 20) {
  const api = {
    createPendingMutation: vi.fn(async () => ({
      pendingMutationToken: 'tok-1',
      expectedRevision: 11,
      payloadSha256: DIGEST(7),
      expiresAt: '2026-08-16T00:05:00Z',
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
    createCloseIntent: vi.fn(async () => ({ intent_id: UUID(31), kind: 'clean_close' })),
    leaveRoom: vi.fn(async () => ({ participant_id: UUID(22), state: 'left', replayed: false })),
    getOperation: vi.fn(async () => ({})),
    ...overrides,
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
    storage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    installBeforeUnload: false,
    deliveryWaitMs,
  })
  return { bridge, api }
}

async function toOoEditing(h: ReturnType<typeof makeBridge>) {
  await h.bridge.switchToOnlyOffice()
  h.bridge.notifyEditorMounted()
  await h.bridge.notifyDocumentReady()
  expect(h.bridge.state.value).toBe('oo_editing')
}

describe('会话内编辑的 dirty 粘住', () => {
  it('OO 的 true→false 之后仍算未保存：clean close 被拒、零次 leave', async () => {
    const h = makeBridge()
    await toOoEditing(h)
    h.bridge.notifyDirty(true)
    h.bridge.notifyDirty(false) // 实测：编辑后约 1 秒内 OO 就发 false
    expect(h.bridge.dirty.value).toBe(true)
    expect(h.bridge.canLeave.value).toBe(false)
    await expect(h.bridge.leaveWithoutSaving()).rejects.toThrow(WorkpaperSyncContractError)
    expect(h.api.leaveRoom, '有编辑时不得只发 leave —— 那正是编辑丢失的路径').not.toHaveBeenCalled()
    expect(h.bridge.state.value).toBe('oo_editing')
  })

  it('没编辑过就一直是干净的（不把未改动的离开变成强制保存）', async () => {
    const h = makeBridge()
    await toOoEditing(h)
    h.bridge.notifyDirty(false)
    expect(h.bridge.dirty.value).toBe(false)
    await h.bridge.leaveWithoutSaving()
    expect(h.api.leaveRoom).toHaveBeenCalledTimes(1)
    expect(h.api.requestForcesave).not.toHaveBeenCalled()
  })

  it('强制保存命令被受理 ⇒ 清零；之后再改又置真', async () => {
    const h = makeBridge()
    await toOoEditing(h)
    h.bridge.notifyDirty(true)
    h.bridge.notifyDirty(false)
    await h.bridge.switchToHtml()
    expect(h.api.requestForcesave).toHaveBeenCalledTimes(1)
    expect(h.bridge.state.value).toBe('waiting_application')
    expect(h.bridge.dirty.value, '这份快照已含此前全部编辑').toBe(false)
    h.bridge.notifyDirty(true)
    expect(h.bridge.dirty.value, '保存请求之后又改过').toBe(true)
  })

  const terminal = (csOutcome: string, csError: number) =>
    vi.fn(async () => ({
      forcesaveRequestId: UUID(29),
      operationId: UUID(30),
      requestSequence: 7,
      state: 'accepted' as const,
      pollAfterMs: 800,
      replayed: false,
      dispatchError: null,
      callbackExpected: false,
      csOutcome,
      csError,
    }))

  // 🔴 判据改过（spec oo-return-to-form-dead-end-and-save-speed R1.2 / R1.3）：原先「CS 回 no_changes ⇒
  // 清零、留在冻结态」。现在 no_changes 只有在改动已确认送达文档服务（最近一次为 false）时才可信：
  // 可信 ⇒ 按契约放行离开（清零、回表单）；不可信 ⇒ 改动可能还在路上，冻结且保持未保存。
  it('CS 回 no_changes 且改动已送达 ⇒ 清零并放行回表单（恰一次 leave）', async () => {
    const h = makeBridge({ requestForcesave: terminal('no_changes', 4) })
    await toOoEditing(h)
    h.bridge.notifyDirty(true)
    h.bridge.notifyDirty(false)
    await h.bridge.switchToHtml()
    expect(h.bridge.state.value).toBe('html_idle')
    expect(h.bridge.dirty.value).toBe(false)
    expect(h.api.leaveRoom).toHaveBeenCalledTimes(1)
  })

  it('CS 回 no_changes 但改动未送达（只有 true）⇒ 冻结、保持未保存、零次 leave', async () => {
    const h = makeBridge({ requestForcesave: terminal('no_changes', 4) })
    await toOoEditing(h)
    h.bridge.notifyDirty(true)
    await h.bridge.switchToHtml()
    expect(h.bridge.state.value).toBe('forcesave_frozen')
    expect(h.bridge.dirty.value, '改动可能还在发往文档服务的路上').toBe(true)
    expect(h.api.leaveRoom).not.toHaveBeenCalled()
  })

  it('其它无回调结局（会话不在线）保持未保存', async () => {
    const h = makeBridge({ requestForcesave: terminal('doc_not_online', 1) })
    await toOoEditing(h)
    h.bridge.notifyDirty(true)
    h.bridge.notifyDirty(false)
    await h.bridge.switchToHtml()
    expect(h.bridge.state.value).toBe('forcesave_frozen')
    expect(h.bridge.dirty.value, '会话不在线 ≠ 没有改动').toBe(true)
  })
})
