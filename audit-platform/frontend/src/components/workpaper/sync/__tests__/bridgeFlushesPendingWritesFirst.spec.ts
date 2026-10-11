/**
 * 切「在线编辑」前桥必须先等子 Tab 的待写盘落库，再调宿主 flushHtml（R20，2026-10-11 真栈）。
 *
 * 和平药房 D2-2：改一格 → 2 秒内点在线编辑 ⇒ 网络序 GET store-projection 早于那次 PUT ⇒ OO 打开的
 * 是旧值，随后 OO 保存把旧值写回 store，HTML 那次编辑被静默覆盖。宿主 flushHtml 只管它自己那层
 * 防抖，子 Tab 私有的防抖它够不着 —— 所以等待点放在**桥**里，对所有宿主生效。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'

import { flushPendingWrites, registerPendingFlusher, trackPendingWrite } from '../pendingWrites'
import { useWorkpaperSyncBridge, type WorkpaperSyncApiSurface } from '../useWorkpaperSyncBridge'

const UUID = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const DIGEST = (n: number) => String(n).repeat(2).padEnd(64, 'abc123def0'.repeat(7)).slice(0, 64)

const memoryStorage = (): Storage =>
  ({ length: 0, key: () => null, getItem: () => null, setItem: () => {}, removeItem: () => {}, clear: () => {} }) as Storage

function makeBridge(order: string[]) {
  const api = {
    createPendingMutation: vi.fn(async () => {
      order.push('pending-mutation')
      return {
        pendingMutationToken: 'tok-1',
        expectedRevision: 11,
        payloadSha256: DIGEST(7),
        expiresAt: '2026-10-11T00:05:00Z',
        idempotencyKey: 'idem-1',
      }
    }),
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
  }
  const flushHtml = vi.fn(async () => {
    order.push('flushHtml')
    return { expectedRevision: 11, projection: { rows: [] } }
  })
  const bridge = useWorkpaperSyncBridge({
    entryId: ref('xlsx/gt-d2-accounts-receivable'),
    wpId: ref(UUID(102)),
    projectId: ref(UUID(101)),
    sheetKey: ref('d22-managed'),
    capability: 'bidirectional',
    flushHtml,
    reloadHtml: vi.fn(async () => {}),
    api: api as unknown as WorkpaperSyncApiSurface,
    storage: memoryStorage(),
    installBeforeUnload: false,
  })
  return { bridge, flushHtml, api }
}

const scopes: Array<ReturnType<typeof effectScope>> = []
afterEach(async () => {
  for (const scope of scopes.splice(0)) scope.stop()
  await flushPendingWrites()
})

describe('桥在 flushHtml 之前清空待写盘', () => {
  it('子 Tab 防抖里的编辑先落库（写完才 flushHtml），再进 pending mutation', async () => {
    const order: string[] = []
    let release!: () => void
    const write = new Promise<void>((resolve) => {
      release = resolve
    })
    const scope = effectScope()
    scopes.push(scope)
    scope.run(() =>
      registerPendingFlusher(() => {
        order.push('debounce-flushed')
        void trackPendingWrite(write.then(() => order.push('put-done')))
      }),
    )
    const h = makeBridge(order)
    const switching = h.bridge.switchToOnlyOffice()
    await Promise.resolve()
    await Promise.resolve()
    expect(order, '写还没落库就去读 store-projection = 读到旧值').toEqual(['debounce-flushed'])
    expect(h.flushHtml).not.toHaveBeenCalled()
    release()
    await switching
    expect(order).toEqual(['debounce-flushed', 'put-done', 'flushHtml', 'pending-mutation'])
  })

  it('没有待写盘时零等待：flushHtml 照常被调用一次', async () => {
    const order: string[] = []
    const h = makeBridge(order)
    await h.bridge.switchToOnlyOffice()
    expect(h.flushHtml).toHaveBeenCalledTimes(1)
    expect(order).toEqual(['flushHtml', 'pending-mutation'])
  })
})
