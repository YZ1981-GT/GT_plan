/**
 * 未改动时点「结构化视图」必须**丝滑**返回：不发强制保存、不留 lease、不丢编辑。
 *
 * 🔴 2026-09-22 用户实测反馈的形态（截图）：一个字都没改就点「结构化视图」，界面弹出
 *   「文档没有检测到改动，本次无需保存（Command Service 返回码 4）。若确实改过，请在
 *     编辑器内先点一下单元格外的空白处让改动生效，再重新保存。」
 *   而人还留在 OO 里。
 *
 * 根因不是错误处理没做好，而是**这条路不存在**：`oo_editing` 的唯一自愿出边是
 * `forcesave_started`，想回表单就必须先发一次强制保存；OO 对未改动的文档必然返回
 * Command Service 码 4 ⇒ 必然落 `forcesave_frozen`。而 `createCloseIntent()`（服务端
 * 登记的 clean close 唯一入口）在全仓**零调用方**。
 *
 * 本文件锁三条：
 * 1. 未改动 ⇒ 走 clean close，**零次网络调用**，状态回 html_idle；
 * 2. 有改动 ⇒ 一律 refuse，绝不静默丢弃编辑（这条是数据安全，不是体验）；
 * 3. clean close **不得**发 `close-intents`。
 *
 * 第 3 条是被真库实测改过来的（本文件首版恰恰要求「必须发 close-intent」）：服务端的
 * close-intent 不是「我走了」，而是 close barrier 仲裁 —— 它把 participant 推成
 * `closing` 并提升一条 `kind=close_capture` 写请求，而未改动的文档永远等不到 OO 回调。
 * 实测 room `03bbcad8` 因此停在 `state=close_barrier` / participant `closing` /
 * capture `state=frozen`，该 room 此后再也进不去（确认成功后立刻「同步失败，请重试」）。
 * 而「留活 lease」并不是本改动引入的：真保存后返回 HTML 的现有成功路径同样不释放
 * participant（实测 `ee4021f6` / `3fc2be85` / `7c235d1a` 全是 room active + participant
 * active）。真正缺的「participant 主动离开」端点见 spec
 * `oo-single-pass-materialize-and-room-leave` Requirement 4。
 */
import { describe, expect, it, vi } from 'vitest'

import {
  WP_BRIDGE_EVENTS,
  transitionBridgeState,
} from '../workpaperSyncBridgeMachine'

describe('clean close：状态机边', () => {
  it('oo_editing 接受 clean_close_completed 并回到 html_idle', () => {
    const next = transitionBridgeState('oo_editing', 'clean_close_completed', 'oo', {})
    expect(next.to).toBe('html_idle')
    expect(next.terminal).toBe(false)
  })

  it('事件已登记在词表里（未登记事件会被 transition 直接拒）', () => {
    expect(WP_BRIDGE_EVENTS).toContain('clean_close_completed')
  })

  it('只有 oo_editing 接受它 —— 保存进行中的状态不得被 clean close 抄近路', () => {
    for (const state of [
      'forcesave_requesting',
      'forcesave_accepted',
      'waiting_application',
      'application_bound',
      'merging',
      'conflict',
    ] as const) {
      expect(
        () => transitionBridgeState(state, 'clean_close_completed', 'oo', {}),
        `${state} 居然接受 clean_close_completed —— 同步进行中离开会让 UI 与服务端脱钩`,
      ).toThrow()
    }
  })

  it('html 侧状态不接受它（HTML 模式下没有 room 可关）', () => {
    expect(() =>
      transitionBridgeState('html_idle', 'clean_close_completed', 'html', {}),
    ).toThrow()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 行为判据：用真实桥实例，断言「发了什么请求」而不是「状态看起来对」
// ═══════════════════════════════════════════════════════════════════════════

import { ref } from 'vue'

import {
  useWorkpaperSyncBridge,
  type WorkpaperSyncApiSurface,
} from '../useWorkpaperSyncBridge'
import { WorkpaperSyncContractError } from '../workpaperSyncDto'

const UUID = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const DIGEST = (n: number) =>
  String(n).repeat(2).padEnd(64, 'abc123def0'.repeat(7)).slice(0, 64)

function makeBridge(overrides: Record<string, unknown> = {}) {
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
    getOperation: vi.fn(async () => ({})),
    ...overrides,
  }
  const bridge = useWorkpaperSyncBridge({
    entryId: ref('xlsx/gt-d4-operating-revenue'),
    wpId: ref(UUID(102)),
    projectId: ref(UUID(101)),
    sheetKey: ref('d42-managed'),
    capability: 'bidirectional',
    flushHtml: vi.fn(async () => ({ expectedRevision: 11, projection: { rows: [] } })),
    reloadHtml: vi.fn(async () => {}),
    api: api as unknown as WorkpaperSyncApiSurface,
    storage: {
      getItem: () => null,
      setItem: () => {},
      removeItem: () => {},
    },
    installBeforeUnload: false,
  })
  return { bridge, api }
}

async function toOoEditing(h: ReturnType<typeof makeBridge>) {
  await h.bridge.switchToOnlyOffice()
  h.bridge.notifyEditorMounted()
  await h.bridge.notifyDocumentReady()
  expect(h.bridge.state.value).toBe('oo_editing')
}

describe('clean close：行为', () => {
  it('未改动 ⇒ 回 html_idle，且**一个请求都不发**', async () => {
    const h = makeBridge()
    await toOoEditing(h)
    expect(h.bridge.dirty.value).toBe(false)
    const callsBefore = Object.fromEntries(
      Object.entries(h.api).map(([name, fn]) => [name, (fn as { mock: { calls: unknown[] } }).mock.calls.length]),
    )

    await h.bridge.leaveWithoutSaving()

    expect(h.bridge.state.value).toBe('html_idle')
    expect(h.bridge.mode.value).toBe('html')
    expect(
      h.api.requestForcesave,
      '未改动却发了强制保存 —— 那正是 Command Service 返回码 4、界面弹红字的来源',
    ).not.toHaveBeenCalled()
    expect(
      h.api.createCloseIntent,
      'close-intent 是 close barrier 仲裁（提升 close_capture）—— 对未改动文档发它会把 '
        + 'room 锁在 close_barrier，实测该 room 此后再也进不去',
    ).not.toHaveBeenCalled()
    // 逐个 api 成员比调用次数：只断言这两个方法会漏掉「换个端点凑数」的实现。
    for (const [name, fn] of Object.entries(h.api)) {
      expect(
        (fn as { mock: { calls: unknown[] } }).mock.calls.length,
        `clean close 期间调了 ${name} —— 这条路径必须是纯本地转换`,
      ).toBe(callsBefore[name])
    }
  })

  it('🔴 有未保存改动 ⇒ 一律 refuse，且**不发**任何请求（绝不静默丢编辑）', async () => {
    const h = makeBridge()
    await toOoEditing(h)
    h.bridge.notifyDirty(true)
    expect(h.bridge.dirty.value).toBe(true)

    await expect(h.bridge.leaveWithoutSaving()).rejects.toThrow(WorkpaperSyncContractError)
    expect(h.api.createCloseIntent).not.toHaveBeenCalled()
    expect(h.bridge.state.value, '拒绝之后必须仍在 OO 里（编辑还在编辑器中）').toBe(
      'oo_editing',
    )
  })

  it('网络整体不可用时仍能回表单（这条路径不依赖任何服务端应答）', async () => {
    const boom = async () => {
      throw new Error('network down')
    }
    const h = makeBridge({
      createCloseIntent: vi.fn(boom),
      requestForcesave: vi.fn(boom),
      getOperation: vi.fn(boom),
    })
    await toOoEditing(h)

    await h.bridge.leaveWithoutSaving()

    expect(h.bridge.state.value, '未改动返回表单不该被任何服务端故障挡住').toBe('html_idle')
    expect(h.bridge.lastError.value, '纯本地转换不该凭空记一条失败').toBeNull()
  })

  it('离开后 descriptor 被清掉（不得留一个指向已离开 room 的 descriptor）', async () => {
    const h = makeBridge()
    await toOoEditing(h)
    expect(h.bridge.descriptor.value).not.toBeNull()

    await h.bridge.leaveWithoutSaving()

    expect(h.bridge.descriptor.value).toBeNull()
    expect(h.bridge.dirty.value).toBe(false)
  })

  it('HTML 模式下调用是空操作（不炸、也不乱发请求）', async () => {
    const h = makeBridge()
    expect(h.bridge.mode.value).toBe('html')
    await h.bridge.leaveWithoutSaving()
    expect(h.api.createCloseIntent).not.toHaveBeenCalled()
    expect(h.bridge.state.value).toBe('html_idle')
  })
})
