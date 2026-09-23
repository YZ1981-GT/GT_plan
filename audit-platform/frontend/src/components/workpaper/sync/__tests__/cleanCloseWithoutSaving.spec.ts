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
 * 1. 未改动 ⇒ 走 clean close，**恰一次 `leaveRoom`、零次 forcesave、零次 close-intent**，
 *    状态回 html_idle；
 * 2. 有改动 ⇒ 一律 refuse，绝不静默丢弃编辑（这条是数据安全，不是体验），且**一个请求都不发**；
 * 3. clean close **不得**发 `close-intents`。
 *
 * 第 3 条是被真库实测改过来的（本文件首版恰恰要求「必须发 close-intent」）：服务端的
 * close-intent 不是「我走了」，而是 close barrier 仲裁 —— 它把 participant 推成
 * `closing` 并提升一条 `kind=close_capture` 写请求，而未改动的文档永远等不到 OO 回调。
 * 实测 room `03bbcad8` 因此停在 `state=close_barrier` / participant `closing` /
 * capture `state=frozen`，该 room 此后再也进不去（确认成功后立刻「同步失败，请重试」）。
 *
 * 🔴 第 1 条在 2026-09-22 之后从**零请求**改成**恰一次 leave**（spec
 * `oo-single-pass-materialize-and-room-leave` AC 4.5 明文要求的判据更新）。原因不是
 * 「留活 lease」这个担心 —— 那个担心本身站不住：真保存后返回 HTML 的现有成功路径同样
 * 不释放 participant（实测 `ee4021f6` / `3fc2be85` / `7c235d1a` 全是 room active +
 * participant active）。原因是那条「participant 主动离开」的服务端路径此前**根本不存在**
 * （`ParticipantState.left` 在 `PARTICIPANT_EDGES` 里是合法终态，却全仓没有任何
 * service/端点会写它），现在它存在了：`POST …/rooms/{id}/participants/{id}/leave`，
 * 只把这一条 lease 落 `left`，不建 request、不推 barrier、不旋转 generation（AC 4.1 / P7）。
 *
 * 判据方向**没有被放宽**：本文件把三个数一起钉住（leave=1 / forcesave=0 / close-intent=0），
 * 比原来的「所有 api 成员调用次数都不变」更强 —— 原判据只要求「什么都别做」，改完之后
 * 它还得证明「做了对的那一件」。「换个端点凑数」仍被逐成员比次数挡着。
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
    leaveRoom: vi.fn(async () => ({
      participant_id: UUID(22),
      state: 'left',
      replayed: false,
      left_at: '2026-09-22T10:00:00+00:00',
      remaining_active_editors: 0,
      room_state: 'active',
    })),
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
  it('未改动 ⇒ 回 html_idle，且**恰一次 leave / 零次 forcesave / 零次 close-intent**', async () => {
    const h = makeBridge()
    await toOoEditing(h)
    expect(h.bridge.dirty.value).toBe(false)
    const callsBefore = Object.fromEntries(
      Object.entries(h.api).map(([name, fn]) => [name, (fn as { mock: { calls: unknown[] } }).mock.calls.length]),
    )

    await h.bridge.leaveWithoutSaving()

    expect(h.bridge.state.value).toBe('html_idle')
    expect(h.bridge.mode.value).toBe('html')
    // ① 恰一次 leave，且身份逐项来自 descriptor、`dirty` 显式送 false。
    expect(h.api.leaveRoom, 'clean close 必须真的释放这条 lease').toHaveBeenCalledTimes(1)
    expect(h.bridge.leaveCallCount.value).toBe(1)
    expect((h.api.leaveRoom as unknown as { mock: { calls: unknown[][] } }).mock.calls[0][1]).toEqual({
      roomId: UUID(21),
      participantId: UUID(22),
      dirty: false,
    })
    // ② 零次 forcesave。
    expect(
      h.api.requestForcesave,
      '未改动却发了强制保存 —— 那正是 Command Service 返回码 4、界面弹红字的来源',
    ).not.toHaveBeenCalled()
    expect(h.bridge.forcesaveCallCount.value).toBe(0)
    // ③ 零次 close-intent。
    expect(
      h.api.createCloseIntent,
      'close-intent 是 close barrier 仲裁（提升 close_capture）—— 对未改动文档发它会把 '
        + 'room 锁在 close_barrier，实测该 room 此后再也进不去',
    ).not.toHaveBeenCalled()
    // 逐个 api 成员比调用次数：只断言上面三个方法会漏掉「换个端点凑数」的实现。
    // `leaveRoom` 是唯一允许 +1 的成员，其余必须逐项不变。
    for (const [name, fn] of Object.entries(h.api)) {
      const expected = callsBefore[name] + (name === 'leaveRoom' ? 1 : 0)
      expect(
        (fn as { mock: { calls: unknown[] } }).mock.calls.length,
        `clean close 期间 ${name} 的调用次数不对 —— 这条路径只许发一次 leave`,
      ).toBe(expected)
    }
  })

  it('🔴 有未保存改动 ⇒ 一律 refuse，且**不发**任何请求（绝不静默丢编辑）', async () => {
    const h = makeBridge()
    await toOoEditing(h)
    h.bridge.notifyDirty(true)
    expect(h.bridge.dirty.value).toBe(true)

    await expect(h.bridge.leaveWithoutSaving()).rejects.toThrow(WorkpaperSyncContractError)
    expect(h.api.createCloseIntent).not.toHaveBeenCalled()
    expect(
      h.api.leaveRoom,
      '🔴 dirty 时**连 leave 都不许发**：前端这道门与服务端的 dirty 门同源（AC 4.4），'
        + '任一侧放宽都会让未落盘的编辑随 lease 一起被释放',
    ).not.toHaveBeenCalled()
    expect(h.bridge.leaveCallCount.value).toBe(0)
    expect(h.bridge.state.value, '拒绝之后必须仍在 OO 里（编辑还在编辑器中）').toBe(
      'oo_editing',
    )
  })

  it('leave 端点整体失败时仍能回表单（返回表单不依赖服务端应答）', async () => {
    const boom = async () => {
      throw new Error('network down')
    }
    const h = makeBridge({
      leaveRoom: vi.fn(boom),
      createCloseIntent: vi.fn(boom),
      requestForcesave: vi.fn(boom),
      getOperation: vi.fn(boom),
    })
    await toOoEditing(h)

    await h.bridge.leaveWithoutSaving()

    expect(h.bridge.state.value, '未改动返回表单不该被任何服务端故障挡住').toBe('html_idle')
    expect(
      h.bridge.lastError.value,
      'leave 失败只意味着这条 lease 退回「等 expires_at 自然过期」那个旧形态 —— '
        + '不是内容丢失，不得记成一条失败糊在页面上（那正是本 spec 起因的那种红字）',
    ).toBeNull()
    expect(h.bridge.leaveCallCount.value, '失败也要算「发过一次」').toBe(1)
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
    expect(
      h.api.leaveRoom,
      'HTML 模式下没有 room/participant 可离开 —— 发出去只会拿一个 404',
    ).not.toHaveBeenCalled()
    expect(h.bridge.state.value).toBe('html_idle')
  })

  it('🔴 恰一次：重复点「结构化视图」不会发第二次 leave（第二次是 HTML 模式空操作）', async () => {
    const h = makeBridge()
    await toOoEditing(h)

    await h.bridge.leaveWithoutSaving()
    await h.bridge.leaveWithoutSaving()

    expect(
      h.api.leaveRoom,
      '第二次调用时 mode 已是 html、descriptor 已清空 —— 再发一次就是拿陈旧身份打端点',
    ).toHaveBeenCalledTimes(1)
    expect(h.bridge.leaveCallCount.value).toBe(1)
  })
})
