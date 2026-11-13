/**
 * 桥的「首次打开自动首版」判据（spec d2-online-edit-platform-closure R7.5）。
 *
 * 平台此前只给每个 entry 的一张 canary 底稿发过首版 representation，其余企业点「在线编辑」
 * 恒得 `materialize_substrate_not_published`。桥的约定：
 *
 *   1. 只认这**一个**码：materialize 返回它 ⇒ 状态经 `identity_rejected` 退回 html_idle，
 *      调一次 `ensureFirstPublication`，成功后**整条链路**（flush → pending → materialize）重走；
 *   2. 只重走**一次**：第二轮仍失败按普通失败处理，绝不无限重试；
 *   3. 首版失败 ⇒ 不进编辑器，服务端中文原因留在 `lastError`（sticky）；
 *   4. 其它码一概不触发首版（防止把 409 陈旧身份之类的失败洗成「再发一版」）。
 *
 * 错误形态一律用平台**真实信封** `{code, message:{error_code, message}}`
 * （见 `bridgeFailureRealEnvelope.spec.ts` 的说明：mock `detail` 是生产上不存在的形状）。
 */
import { describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'

import {
  SUBSTRATE_NOT_PUBLISHED_CODE,
  useWorkpaperSyncBridge,
  type WorkpaperSyncApiSurface,
} from '../useWorkpaperSyncBridge'
import { WP_SYNC_REJECTION_STATUS, WP_SYNC_ROUTES } from '../workpaperSyncContract.generated'
import { registerPendingFlusher } from '../pendingWrites'
import type { WorkpaperSyncEditorLaunchDescriptor } from '../workpaperSyncDto'

const UUID = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const DIGEST = 'a'.repeat(64)
const SCOPE = { projectId: UUID(101), wpId: UUID(102), entryId: 'xlsx/gt-d2-accounts-receivable' }

function descriptor(): WorkpaperSyncEditorLaunchDescriptor {
  const slot = { type: 'definition', sha256: DIGEST }
  return {
    operationId: UUID(20),
    roomId: UUID(21),
    participantId: UUID(22),
    docKey: 'dockey-1',
    generation: 1,
    serverAppliedRevision: 1,
    clientConfirmedBaseRevision: 1,
    contentVersionId: UUID(23),
    representationId: UUID(24),
    representationGeneration: 1,
    artifactSha256: DIGEST,
    writeFenceEpoch: 1,
    authorityModel: 'projection_contract',
    authorityModelDefinitionSha256: DIGEST,
    definitionBundleId: UUID(25),
    definitionBundleSha256: DIGEST,
    definitionBundleSlots: { template: slot, instrumentation: slot, contract: slot },
    documentType: 'xlsx',
    mode: 'edit',
    onlyofficeConfig: { document: { key: 'dockey-1' } },
    replayed: false,
  }
}

/** 平台真实错误信封（`error_handler.http_exception_handler`）。 */
function wireError(status: number, errorCode: string, message: string) {
  return { response: { status, data: { code: status, message: { error_code: errorCode, message } } } }
}

const NOT_PUBLISHED = () => wireError(422, SUBSTRATE_NOT_PUBLISHED_CODE, '该底稿尚无已发布版本')

function readinessWithoutFirstPublication() {
  return {
    entry_id: SCOPE.entryId,
    effective_entry_id: SCOPE.entryId,
    capability: 'bidirectional' as const,
    adjudication_state: 'terminal' as const,
    allowed_modes: ['html'] as const,
    can_claim_bidirectional: false,
    runtime: {
      ready: false,
      adapter_id: null,
      authority_model: null,
      definition_bundle_id: null,
      definition_bundle_sha256: null,
      typed_slots_complete: false,
      typed_slots: [],
      representation_id: null,
      representation_generation: null,
    },
    acceptance: {
      state: 'missing' as const,
      stale: false,
      run_id: null,
      required_scenario_set_digest: null,
    },
    reason: {
      code: 'REPRESENTATION_MISSING',
      message: '当前底稿尚未发布可用于在线编辑的版本。',
      next_action: '先完成该底稿的首版 representation 发布，再重新检查。',
    },
  }
}

function harness(
  api: Partial<Record<keyof WorkpaperSyncApiSurface, unknown>>,
  options: { onFirstPublication?: () => void | Promise<void> } = {},
) {
  let revision = 0
  const full = {
    createPendingMutation: vi.fn(async () => ({
      pendingMutationToken: `tok-${revision}`,
      expectedRevision: revision,
      payloadSha256: DIGEST,
      expiresAt: '2026-10-10T00:05:00Z',
      idempotencyKey: `idem-${revision}`,
    })),
    materialize: vi.fn(async () => descriptor()),
    ...api,
  } as Record<string, unknown>
  // flush 每次读一次「当前 revision」：首版之后 revision 前进，重走必须拿到新值。
  const flushHtml = vi.fn(async () => ({ expectedRevision: revision, projection: { values: {} } }))
  const bridge = useWorkpaperSyncBridge({
    entryId: ref(SCOPE.entryId),
    wpId: ref(SCOPE.wpId),
    projectId: ref(SCOPE.projectId),
    sheetKey: ref('D2-2'),
    capability: 'bidirectional',
    flushHtml,
    reloadHtml: async () => {},
    onFirstPublication: options.onFirstPublication,
    api: full as unknown as WorkpaperSyncApiSurface,
    storage: null,
    installBeforeUnload: false,
  })
  return {
    bridge,
    api: full as Record<string, ReturnType<typeof vi.fn>>,
    flushHtml,
    bumpRevision: () => {
      revision += 1
    },
  }
}

describe('readiness 报首版缺失时允许进入首版重试链', () => {
  it('先冲刷 HTML 防抖，再发布首版，最后按新 revision 只跑一轮 materialize', async () => {
    let h!: ReturnType<typeof harness>
    const ensureFirstPublication = vi.fn(async () => {
      h.bumpRevision()
      return {
        status: 'published' as const,
        representationId: UUID(24),
        representationGeneration: 1,
        contentRevision: 1,
      }
    })
    const onFirstPublication = vi.fn(async () => {})
    const materialize = vi.fn(async () => descriptor())
    const readEntrySyncReadiness = vi.fn(async () => readinessWithoutFirstPublication())
    const pendingFlush = vi.fn(async () => {})
    const scope = effectScope()
    scope.run(() => registerPendingFlusher(pendingFlush))
    try {
      h = harness(
        { readEntrySyncReadiness, ensureFirstPublication, materialize },
        { onFirstPublication },
      )

      const received = await h.bridge.switchToOnlyOffice()

      expect(received.roomId).toBe(UUID(21))
      expect(readEntrySyncReadiness).toHaveBeenCalledTimes(1)
      expect(ensureFirstPublication).toHaveBeenCalledTimes(1)
      expect(onFirstPublication).toHaveBeenCalledTimes(1)
      // 首版前冲刷一次，重走时 no-op flusher 再被调用一次；真实组件第二次不会重发 PUT。
      expect(pendingFlush).toHaveBeenCalledTimes(2)
      expect(h.flushHtml).toHaveBeenCalledTimes(1)
      expect(h.api.createPendingMutation).toHaveBeenCalledTimes(1)
      expect(materialize).toHaveBeenCalledTimes(1)
      expect(pendingFlush.mock.invocationCallOrder[0]).toBeLessThan(
        ensureFirstPublication.mock.invocationCallOrder[0],
      )
      expect(ensureFirstPublication.mock.invocationCallOrder[0]).toBeLessThan(
        h.flushHtml.mock.invocationCallOrder[0],
      )
      expect(materialize.mock.calls[0][1].expectedRevision).toBe(1)
      expect(h.bridge.state.value).toBe('oo_loading')
    } finally {
      scope.stop()
    }
  })
})

describe('materialize 报 substrate_not_published ⇒ 发一次首版并整链重走', () => {
  it('首版成功：flush/pending/materialize 各两次、首版恰一次，第二轮用新 revision 并进 oo_loading', async () => {
    let h!: ReturnType<typeof harness>
    const ensureFirstPublication = vi.fn(async (_scope: typeof SCOPE) => {
      h.bumpRevision()
      return {
        status: 'published' as const,
        representationId: UUID(24),
        representationGeneration: 1,
        contentRevision: 1,
      }
    })
    const materialize = vi
      .fn()
      .mockRejectedValueOnce(NOT_PUBLISHED())
      .mockResolvedValueOnce(descriptor())
    h = harness({ materialize, ensureFirstPublication })

    const received = await h.bridge.switchToOnlyOffice()

    expect(received.roomId).toBe(UUID(21))
    expect(ensureFirstPublication).toHaveBeenCalledTimes(1)
    expect(ensureFirstPublication.mock.calls[0][0]).toEqual(SCOPE)
    expect(h.flushHtml).toHaveBeenCalledTimes(2)
    expect(h.api.createPendingMutation).toHaveBeenCalledTimes(2)
    expect(materialize).toHaveBeenCalledTimes(2)
    // 第二轮必须拿首版之后的 revision 与新 token（旧 token 冻结的是首版之前的 revision）。
    expect(materialize.mock.calls[0][1].expectedRevision).toBe(0)
    expect(materialize.mock.calls[1][1].expectedRevision).toBe(1)
    expect(materialize.mock.calls[1][1].pendingMutationToken).toBe('tok-1')
    expect(h.bridge.state.value).toBe('oo_loading')
    expect(h.bridge.lastError.value).toBeNull()
    // 状态轨迹：首轮经 identity_rejected 退回 html_idle，第二轮重新 flush_started。
    const events = [...h.bridge.transitions.value]
    expect(events.filter((e) => e === 'flush_started')).toHaveLength(2)
    expect(events).toContain('identity_rejected')
  })

  it('重走仍报同一码：首版只调一次、materialize 只两次，按普通失败落 error（不无限重试）', async () => {
    const ensureFirstPublication = vi.fn(async () => {
      // 🔴 死循环保险：「只重走一次」被破坏时，这里让失败**收敛成红**而不是把测试进程
      //    卡进无穷微任务循环（mock 全是已决 promise ⇒ 计时器永不触发，testTimeout 也救不了）。
      if (ensureFirstPublication.mock.calls.length > 2) {
        throw new Error('首版被调了第 3 次 —— 桥在无限重试')
      }
      return {
        status: 'already_published' as const,
        representationId: UUID(24),
        representationGeneration: 1,
        contentRevision: 1,
      }
    })
    const materialize = vi.fn(async () => {
      throw NOT_PUBLISHED()
    })
    const h = harness({ materialize, ensureFirstPublication })

    await expect(h.bridge.switchToOnlyOffice()).rejects.toBeTruthy()

    expect(ensureFirstPublication).toHaveBeenCalledTimes(1)
    expect(materialize).toHaveBeenCalledTimes(2)
    expect(h.bridge.state.value).toBe('error')
    expect(h.bridge.lastError.value?.errorCode).toBe(SUBSTRATE_NOT_PUBLISHED_CODE)
  })

  it('首版失败：不重走、不进编辑器，服务端中文原因留在 lastError', async () => {
    const ensureFirstPublication = vi.fn(async () => {
      throw wireError(
        422,
        'store_payload_empty_and_not_publishable',
        '请先在结构化视图录入内容后再进入在线编辑',
      )
    })
    const materialize = vi.fn(async () => {
      throw NOT_PUBLISHED()
    })
    const h = harness({ materialize, ensureFirstPublication })

    await expect(h.bridge.switchToOnlyOffice()).rejects.toBeTruthy()

    expect(materialize).toHaveBeenCalledTimes(1)
    expect(h.flushHtml).toHaveBeenCalledTimes(1)
    expect(h.bridge.state.value).toBe('error')
    expect(h.bridge.lastError.value?.stage).toBe('first_publication')
    expect(h.bridge.lastError.value?.errorCode).toBe('store_payload_empty_and_not_publishable')
    expect(h.bridge.lastError.value?.message).toContain('录入内容')
  })
})

describe('只有这一个码触发首版', () => {
  it.each([
    ['409 陈旧 substrate', wireError(409, 'launch_descriptor_substrate_stale', '请重新 flush')],
    ['409 room 不可写', wireError(409, 'room_not_writable', 'room 处于 refresh-required')],
    ['422 契约缺失', wireError(422, 'per_entry_contract_required', '缺契约')],
  ])('%s：不调首版，按原分支失败', async (_label, error) => {
    const ensureFirstPublication = vi.fn()
    const materialize = vi.fn(async () => {
      throw error
    })
    const h = harness({ materialize, ensureFirstPublication })

    await expect(h.bridge.switchToOnlyOffice()).rejects.toBeTruthy()

    expect(ensureFirstPublication).not.toHaveBeenCalled()
    expect(materialize).toHaveBeenCalledTimes(1)
  })

  it('API 面未提供首版能力（旧 stub）：原样失败，不调 undefined', async () => {
    const materialize = vi.fn(async () => {
      throw NOT_PUBLISHED()
    })
    const h = harness({ materialize })

    await expect(h.bridge.switchToOnlyOffice()).rejects.toBeTruthy()

    expect(materialize).toHaveBeenCalledTimes(1)
    expect(h.bridge.lastError.value?.errorCode).toBe(SUBSTRATE_NOT_PUBLISHED_CODE)
  })
})

describe('触发码与端点都钉在生成的契约上（后端改名即红）', () => {
  it('触发码是后端拒绝码表里的 422', () => {
    expect(WP_SYNC_REJECTION_STATUS[SUBSTRATE_NOT_PUBLISHED_CODE]).toBe(422)
  })

  it('首版端点在生成的路由表里，且是 POST', () => {
    const route = WP_SYNC_ROUTES.find((r) => r.endpoint === 'ensure_first_publication')
    expect(route?.method).toBe('POST')
    expect(route?.suffix).toBe('/first-publication')
  })

  it('room_not_writable 映射为 409（不再是 500 + 自动重试三次）', () => {
    expect(WP_SYNC_REJECTION_STATUS.room_not_writable).toBe(409)
  })
})

/**
 * 带 readiness 预检的完整链路。上面的用例都不注入 `readEntrySyncReadiness`，预检被跳过 ——
 * 正是这个盲区让「尚无首版 ⇒ 预检拒绝 ⇒ 首版永远发不出来」的死锁漏过了测试。
 */
describe('readiness 报尚无首版 ⇒ 预检放行，按需首版后进入编辑器', () => {
  function readiness(code: string, ready = false) {
    return {
      entry_id: SCOPE.entryId,
      effective_entry_id: SCOPE.entryId,
      capability: 'bidirectional' as const,
      adjudication_state: 'terminal' as const,
      allowed_modes: ['html', 'oo'] as const,
      can_claim_bidirectional: false,
      runtime: { ready },
      acceptance: { state: 'missing', stale: false, run_id: null, required_scenario_set_digest: null },
      reason: { code, message: '原因', next_action: '下一步' },
    }
  }

  it('REPRESENTATION_MISSING：不拒绝，先发首版恰一次再 materialize 一次，最终进 oo_loading', async () => {
    let h!: ReturnType<typeof harness>
    const ensureFirstPublication = vi.fn(async () => {
      h.bumpRevision()
      return { status: 'published' as const, representationId: UUID(24), representationGeneration: 1, contentRevision: 1 }
    })
    // 预检已知尚无首版 ⇒ 桥先发首版再 materialize（不再靠 materialize 报 substrate_not_published 触发）
    const materialize = vi.fn().mockResolvedValue(descriptor())
    const readEntrySyncReadiness = vi.fn(async () => readiness('REPRESENTATION_MISSING'))
    h = harness({ materialize, ensureFirstPublication, readEntrySyncReadiness })

    const received = await h.bridge.switchToOnlyOffice()

    expect(received.roomId).toBe(UUID(21))
    expect(readEntrySyncReadiness).toHaveBeenCalledTimes(1)
    expect(ensureFirstPublication).toHaveBeenCalledTimes(1)
    expect(materialize).toHaveBeenCalledTimes(1)
    expect(h.bridge.state.value).toBe('oo_loading')
  })

  it('其余未就绪原因照旧拒绝：零写请求、不发首版', async () => {
    const ensureFirstPublication = vi.fn()
    const materialize = vi.fn()
    const readEntrySyncReadiness = vi.fn(async () => readiness('ADAPTER_NOT_READY'))
    const h = harness({ materialize, ensureFirstPublication, readEntrySyncReadiness })

    await expect(h.bridge.switchToOnlyOffice()).rejects.toMatchObject({ code: 'bridge_runtime_not_ready' })
    expect(h.api.createPendingMutation).not.toHaveBeenCalled()
    expect(materialize).not.toHaveBeenCalled()
    expect(ensureFirstPublication).not.toHaveBeenCalled()
  })
})

/**
 * 尚无首版时 adapter 注册不上，服务端在 **pending-mutations** 这一步就回报
 * substrate_not_published（还到不了 materialize）。原先只有 materialize 失败才触发首版 ⇒
 * 这一步的失败直接落 error，首版永远发不出来。
 */
describe('pending-mutations 报 substrate_not_published ⇒ 同样发一次首版并整链重走', () => {
  it('首版恰一次，第二轮 pending 用新 revision，最终进 oo_loading', async () => {
    let h!: ReturnType<typeof harness>
    const ensureFirstPublication = vi.fn(async () => {
      h.bumpRevision()
      return { status: 'published' as const, representationId: UUID(24), representationGeneration: 1, contentRevision: 1 }
    })
    let pendingCalls = 0
    const createPendingMutation = vi.fn(async (_scope: unknown, body: { expectedRevision: number }) => {
      pendingCalls += 1
      if (pendingCalls === 1) throw NOT_PUBLISHED()
      return {
        pendingMutationToken: `tok-${body.expectedRevision}`,
        expectedRevision: body.expectedRevision,
        payloadSha256: DIGEST,
        expiresAt: '2026-10-10T00:05:00Z',
        idempotencyKey: `idem-${body.expectedRevision}`,
      }
    })
    const materialize = vi.fn(async () => descriptor())
    h = harness({ createPendingMutation, materialize, ensureFirstPublication })

    const received = await h.bridge.switchToOnlyOffice()

    expect(received.roomId).toBe(UUID(21))
    expect(ensureFirstPublication).toHaveBeenCalledTimes(1)
    expect(createPendingMutation).toHaveBeenCalledTimes(2)
    expect(createPendingMutation.mock.calls[1][1].expectedRevision).toBe(1)
    expect(materialize).toHaveBeenCalledTimes(1)
    expect(h.bridge.state.value).toBe('oo_loading')
  })

  it('pending-mutations 的其它失败不触发首版', async () => {
    const ensureFirstPublication = vi.fn()
    const createPendingMutation = vi.fn(async () => {
      throw wireError(409, 'pending_mutation_token_expired', 'token 过期')
    })
    const h = harness({ createPendingMutation, ensureFirstPublication })

    await expect(h.bridge.switchToOnlyOffice()).rejects.toBeTruthy()
    expect(ensureFirstPublication).not.toHaveBeenCalled()
  })
})
