// spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 32
//
// 桥 composable 的**行为**判据：真的调了哪个端点、带了哪个 id、门控有没有开、
// 失败之后文案会不会被洗成成功。
//
// Validates: Requirements 3.1, 3.6, 3.7, 4.1, 4.2, 4.4, 4.5, 4.7, 4.8, 5.8, 11.6,
//            11.8, 11.10
//
// ═══ 判据设计 ═══
//
// * **不 mock 模块**，注入一个记录调用的 API stub：于是「桥到底把 requested 还是
//   canonical id 发出去了」这类接线错误可以逐参数断言。Vue 里传错字段是静默失效，
//   tsc/vitest/get_diagnostics 三层都查不出，只有真的看**发出的参数**才能证伪。
// * 每个门控都断言「关着的时候真的拒了」并断言 code；只断言「关着」不够 ——
//   `if (false)` 下「关着」依然成立。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  WP_BRIDGE_IN_FLIGHT_STATES,
  WP_BRIDGE_LOCAL_FAILURE_CODE,
  WP_BRIDGE_NON_DISCLOSURE_CODE,
  describeBridgeFailure,
  useWorkpaperSyncBridge,
  type WorkpaperSyncApiSurface,
} from '../useWorkpaperSyncBridge'
import { WP_BRIDGE_STATES, WP_BRIDGE_STATE_TEXT } from '../workpaperSyncBridgeMachine'
import { WorkpaperSyncContractError } from '../workpaperSyncDto'
import type {
  WorkpaperSyncDescriptorConfirmation,
  WorkpaperSyncEditorLaunchDescriptor,
  WorkpaperSyncOperationSnapshot,
  WorkpaperSyncRecoveryCase,
} from '../workpaperSyncDto'
import { ref } from 'vue'

const UUID = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const DIGEST = (n: number) => String(n).repeat(2).padEnd(64, 'abc123def0'.repeat(7)).slice(0, 64)
const PROJECT = UUID(101)
const WP = UUID(102)
const ENTRY = 'xlsx/d4/analysis/d4-tab-customer-price'

function descriptorFixture(
  over: Partial<WorkpaperSyncEditorLaunchDescriptor> = {},
): WorkpaperSyncEditorLaunchDescriptor {
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
    onlyofficeConfig: { document: { key: 'dockey-1' } },
    replayed: false,
    ...over,
  }
}

function confirmationFixture(
  over: Partial<WorkpaperSyncDescriptorConfirmation> = {},
): WorkpaperSyncDescriptorConfirmation {
  return {
    confirmationId: UUID(26),
    roomId: UUID(21),
    participantId: UUID(22),
    generation: 3,
    representationId: UUID(24),
    contentVersionId: UUID(23),
    roomState: 'active',
    replayed: false,
    forcesaveUnlocked: true,
    ...over,
  }
}

function snapshot(
  over: Partial<WorkpaperSyncOperationSnapshot> = {},
): WorkpaperSyncOperationSnapshot {
  return {
    requestedOperationId: UUID(30),
    canonicalOperationId: UUID(30),
    followedDuplicate: false,
    state: 'accepted',
    shape: 'pre_correlation',
    applicationId: null,
    duplicateOfOperationId: null,
    errorCode: null,
    errorStage: null,
    acceptedAt: null,
    applicationBoundAt: null,
    operationFinishedAt: null,
    resultRevision: null,
    conflictCount: null,
    logicalResultCode: null,
    definitionBundleId: null,
    definitionBundleSha256: null,
    authorityModelDefinitionSha256: null,
    durableAt: null,
    finishedAt: null,
    terminal: false,
    ...over,
  }
}

function recoveryCaseFixture(
  over: Partial<WorkpaperSyncRecoveryCase> = {},
): WorkpaperSyncRecoveryCase {
  return {
    caseId: UUID(40),
    reason: 'crash_close',
    state: 'unclaimed',
    operationId: null,
    applicationId: null,
    forcesaveRequestId: null,
    candidatePriorConfirmations: [
      {
        confirmationId: UUID(41),
        participantId: UUID(22),
        contentVersionId: UUID(23),
        confirmedAt: '2026-08-16T00:00:00Z',
      },
    ],
    actions: { claim: true, downloadOnly: true },
    ...over,
  }
}

class MemoryStorage {
  private readonly map = new Map<string, string>()
  get length(): number {
    return this.map.size
  }
  key(index: number): string | null {
    return [...this.map.keys()][index] ?? null
  }
  getItem(key: string): string | null {
    return this.map.has(key) ? (this.map.get(key) as string) : null
  }
  setItem(key: string, value: string): void {
    this.map.set(key, value)
  }
  removeItem(key: string): void {
    this.map.delete(key)
  }
  snapshot(): Record<string, string> {
    return Object.fromEntries([...this.map.entries()].sort())
  }
}

interface Harness {
  bridge: ReturnType<typeof useWorkpaperSyncBridge>
  api: { [K in keyof WorkpaperSyncApiSurface]: ReturnType<typeof vi.fn> }
  flushHtml: ReturnType<typeof vi.fn>
  reloadHtml: ReturnType<typeof vi.fn>
  storage: MemoryStorage
}

function harness(
  overrides: Partial<Record<keyof WorkpaperSyncApiSurface, unknown>> = {},
  options: { capability?: 'bidirectional' | 'single_html' | 'single_onlyoffice' } = {},
): Harness {
  const storage = new MemoryStorage()
  const api = {
    createPendingMutation: vi.fn(async () => ({
      pendingMutationToken: 'tok-1',
      expectedRevision: 11,
      payloadSha256: DIGEST(7),
      expiresAt: '2026-08-16T00:05:00Z',
      idempotencyKey: 'idem-1',
    })),
    materialize: vi.fn(async () => descriptorFixture()),
    confirmDescriptor: vi.fn(async () => confirmationFixture()),
    requestForcesave: vi.fn(async () => ({
      forcesaveRequestId: UUID(29),
      operationId: UUID(30),
      requestSequence: 7,
      state: 'accepted' as const,
      pollAfterMs: 800,
      replayed: false,
      dispatchError: null,
    })),
    getOperation: vi.fn(async () => snapshot()),
    getOperationConflicts: vi.fn(async () => ({
      canonical_application_id: UUID(9),
      incoming_sequence: 7,
      groups: [],
    })),
    getOperationTimeline: vi.fn(async () => ({ operation_events: [] })),
    getRecoveryCaseTimeline: vi.fn(async () => ({ events: [] })),
    resolveConflicts: vi.fn(async () => ({ decision: 'applied' })),
    retryOperation: vi.fn(async () => ({ retried: true })),
    listRecoveryCases: vi.fn(async () => ({
      roomId: UUID(21),
      generation: 3,
      cases: [recoveryCaseFixture()],
    })),
    claimRecoveryCase: vi.fn(async () => ({
      caseId: UUID(40),
      forcesaveRequestId: UUID(42),
      operationId: UUID(43),
      applicationId: UUID(44),
      state: 'application_created' as const,
    })),
    terminateRecoveryDownloadOnly: vi.fn(async () => ({
      caseId: UUID(40),
      state: 'download_only' as const,
      downloadClaim: 'claim-1',
      expiresInSeconds: 300,
    })),
    downloadRecoveryArtifact: vi.fn(async () => ({
      caseId: UUID(40),
      artifactId: UUID(45),
      artifactSha256: DIGEST(8),
      documentType: 'xlsx',
      sizeBytes: 1024,
      relativePath: 'incoming/a.xlsx',
    })),
    rollbackVersion: vi.fn(async () => ({ revision_after: 12 })),
  }
  for (const [key, value] of Object.entries(overrides)) {
    ;(api as Record<string, unknown>)[key] = value
  }
  const flushHtml = vi.fn(async () => ({ expectedRevision: 11, projection: { rows: [] } }))
  const reloadHtml = vi.fn(async () => {})
  const bridge = useWorkpaperSyncBridge({
    entryId: ref(ENTRY),
    wpId: ref(WP),
    projectId: ref(PROJECT),
    sheetKey: ref('D4-1'),
    capability: options.capability ?? 'bidirectional',
    flushHtml,
    reloadHtml,
    api: api as unknown as WorkpaperSyncApiSurface,
    storage,
    installBeforeUnload: false,
  })
  return { bridge, api: api as Harness['api'], flushHtml, reloadHtml, storage }
}

/** 走到 `oo_editing`（materialize → mount → ready → confirm）。 */
async function openEditor(h: Harness): Promise<void> {
  await h.bridge.switchToOnlyOffice()
  h.bridge.notifyEditorMounted()
  await h.bridge.notifyDocumentReady()
}

async function expectRejection(fn: () => unknown, code: string): Promise<void> {
  let caught: unknown
  try {
    await fn()
  } catch (error) {
    caught = error
  }
  expect(caught, `期望拒绝 code=${code}`).toBeInstanceOf(WorkpaperSyncContractError)
  expect((caught as WorkpaperSyncContractError).code).toBe(code)
}

afterEach(() => {
  vi.restoreAllMocks()
})

// ═══════════════════════════════════════════════════════════════════════════
// A. HTML → OO：flush → 单次 commit → descriptor → mount → confirm
// ═══════════════════════════════════════════════════════════════════════════

describe('switchToOnlyOffice：消费 pending token，materialize 成功才 mount', () => {
  it('调用顺序固定，且 materialize 拿到的正是 flush 返回的 token', async () => {
    const h = harness()
    const descriptor = await h.bridge.switchToOnlyOffice()
    expect(h.flushHtml).toHaveBeenCalledTimes(1)
    expect(h.api.createPendingMutation).toHaveBeenCalledTimes(1)
    expect(h.api.materialize).toHaveBeenCalledTimes(1)
    const [scope, input] = h.api.materialize.mock.calls[0]
    expect(scope).toEqual({ projectId: PROJECT, wpId: WP, entryId: ENTRY })
    expect(input.pendingMutationToken).toBe('tok-1')
    expect(input.expectedRevision).toBe(11)
    expect(descriptor.roomId).toBe(UUID(21))
    // descriptor 到手但还没挂载：mount 计数为 0（挂载是宿主的事，Task 33）。
    expect(h.bridge.state.value).toBe('oo_loading')
    expect(h.bridge.mountCallCount.value).toBe(0)
  })

  it('flush 失败：停留 HTML，pending mutation 与 materialize 调用次数均为 0', async () => {
    const h = harness()
    h.flushHtml.mockRejectedValueOnce(new Error('本地 flush 失败'))
    await expect(h.bridge.switchToOnlyOffice()).rejects.toThrow('本地 flush 失败')
    expect(h.api.createPendingMutation).not.toHaveBeenCalled()
    expect(h.api.materialize).not.toHaveBeenCalled()
    expect(h.bridge.mode.value).toBe('html')
    expect(h.bridge.state.value).toBe('error')
  })

  it('pending token 过期（409）：停留 HTML 且 mode 不变', async () => {
    const h = harness({
      materialize: vi.fn(async () => {
        throw {
          response: {
            status: 409,
            data: { detail: { error_code: 'pending_mutation_token_expired', message: 'x' } },
          },
        }
      }),
    })
    await expect(h.bridge.switchToOnlyOffice()).rejects.toBeTruthy()
    expect(h.bridge.state.value).toBe('html_idle')
    expect(h.bridge.mode.value).toBe('html')
    expect(h.bridge.lastError.value?.errorCode).toBe('pending_mutation_token_expired')
  })

  it('bundle identity 陈旧（409 stale identity）：三门全关且停留 HTML', async () => {
    const h = harness({
      materialize: vi.fn(async () => {
        throw {
          response: {
            status: 409,
            data: {
              detail: { error_code: 'launch_descriptor_stale_identity', message: 'stale' },
            },
          },
        }
      }),
    })
    await expect(h.bridge.switchToOnlyOffice()).rejects.toBeTruthy()
    expect(h.bridge.state.value).toBe('html_idle')
    expect(h.bridge.mode.value).toBe('html')
    const verdict = h.bridge.lastError.value?.verdict
    expect(verdict?.canEnterEditing).toBe(false)
    expect(verdict?.retryableOperation).toBe(false)
    expect(verdict?.canForcesave).toBe(false)
  })

  it('capability 不支持 OO 时直接拒绝（不打任何端点）', async () => {
    const h = harness({}, { capability: 'single_html' })
    await expectRejection(() => h.bridge.switchToOnlyOffice(), 'bridge_mode_not_supported')
    expect(h.flushHtml).not.toHaveBeenCalled()
  })
})

describe('onDocumentReady 之后 await confirm-descriptor', () => {
  it('confirm 之前不进 oo_editing、不可 forcesave', async () => {
    const h = harness()
    await h.bridge.switchToOnlyOffice()
    h.bridge.notifyEditorMounted()
    expect(h.bridge.state.value).toBe('descriptor_mounted')
    expect(h.bridge.canForcesave.value).toBe(false)
    await expectRejection(() => h.bridge.switchToHtml(), 'bridge_forcesave_before_confirmation')
    expect(h.api.requestForcesave).not.toHaveBeenCalled()
  })

  it('confirm 成功后才 oo_editing + 可 forcesave，且回传体逐项来自同一 descriptor', async () => {
    const h = harness()
    await openEditor(h)
    expect(h.bridge.state.value).toBe('oo_editing')
    expect(h.bridge.canForcesave.value).toBe(true)
    const [, input] = h.api.confirmDescriptor.mock.calls[0]
    expect(input.descriptor.roomId).toBe(UUID(21))
    expect(Object.keys(input.confirmPayload).sort()).toEqual([
      'artifact_sha256',
      'authority_model_definition_sha256',
      'content_revision',
      'definition_bundle_id',
      'definition_bundle_sha256',
      'doc_key',
      'generation',
      'participant_id',
      'representation_id',
      'write_fence_epoch',
    ])
    expect(input.confirmPayload.content_revision).toBe(11)
    expect(input.confirmPayload.write_fence_epoch).toBe(5)
  })

  it('confirm 返回 forcesave_unlocked=false ⇒ 不进 editing（已确认但不可写）', async () => {
    const h = harness({
      confirmDescriptor: vi.fn(async () => confirmationFixture({ forcesaveUnlocked: false })),
    })
    await h.bridge.switchToOnlyOffice()
    h.bridge.notifyEditorMounted()
    await expect(h.bridge.notifyDocumentReady()).rejects.toBeTruthy()
    expect(h.bridge.state.value).not.toBe('oo_editing')
    expect(h.bridge.canForcesave.value).toBe(false)
  })

  it('confirm 409：不得转 editing，停留 HTML 侧', async () => {
    const h = harness({
      confirmDescriptor: vi.fn(async () => {
        throw {
          response: {
            status: 409,
            data: {
              detail: { error_code: 'launch_descriptor_substrate_stale', message: 'stale' },
            },
          },
        }
      }),
    })
    await h.bridge.switchToOnlyOffice()
    h.bridge.notifyEditorMounted()
    await expect(h.bridge.notifyDocumentReady()).rejects.toBeTruthy()
    expect(h.bridge.state.value).toBe('html_idle')
    expect(h.bridge.canForcesave.value).toBe(false)
  })

  it('descriptor 还没到就上报 ready ⇒ 拒绝（descriptor 是唯一 config 来源）', async () => {
    const h = harness()
    await expectRejection(() => h.bridge.notifyDocumentReady(), 'bridge_ready_without_descriptor')
    expect(h.api.confirmDescriptor).not.toHaveBeenCalled()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// B. OO → HTML：等 terminal
// ═══════════════════════════════════════════════════════════════════════════

describe('switchToHtml：先冻结 request，再跟踪两 link 均空的 shell', () => {
  it('202 之后进入 shell 跟踪，requested operation id 来自回执', async () => {
    const h = harness()
    await openEditor(h)
    await h.bridge.switchToHtml()
    expect(h.bridge.state.value).toBe('waiting_application')
    expect(h.bridge.requestedOperationId.value).toBe(UUID(30))
    const [, input] = h.api.requestForcesave.mock.calls[0]
    expect(input.roomId).toBe(UUID(21))
    expect(input.participantId).toBe(UUID(22))
    expect(input.expectedWriteFenceEpoch).toBe(5)
    // 客户端不得指定 kind（close_capture 只能由 room arbiter 提升）。
    expect(input).not.toHaveProperty('kind')
  })

  it('202 带 dispatch_error ⇒ 保持 OO 的 forcesave_frozen 且可重试', async () => {
    const h = harness({
      requestForcesave: vi.fn(async () => ({
        forcesaveRequestId: UUID(29),
        operationId: UUID(30),
        requestSequence: 7,
        state: 'accepted' as const,
        pollAfterMs: 800,
        replayed: false,
        dispatchError: 'command_service_unavailable',
      })),
    })
    await openEditor(h)
    await h.bridge.switchToHtml()
    expect(h.bridge.state.value).toBe('forcesave_frozen')
    expect(h.bridge.mode.value).toBe('oo')
    expect(h.bridge.feedback.value.kind).toBe('error')
    expect(WP_BRIDGE_STATE_TEXT.forcesave_frozen).toContain('已冻结保存请求')
  })

  it('shell → durable → bound → applied，reload 用的最小 revision 等于 result revision', async () => {
    const h = harness()
    await openEditor(h)
    await h.bridge.switchToHtml()
    h.bridge.ingestOperationSnapshot(snapshot({ durableAt: '2026-08-16T00:00:00Z' }))
    expect(h.bridge.state.value).toBe('incoming_durable')
    h.bridge.ingestOperationSnapshot(
      snapshot({ state: 'application_bound', shape: 'primary', applicationId: UUID(9) }),
    )
    expect(h.bridge.state.value).toBe('application_bound')
    h.bridge.ingestOperationSnapshot(
      snapshot({
        state: 'applied',
        shape: 'primary',
        applicationId: UUID(9),
        resultRevision: 12,
      }),
    )
    expect(h.bridge.state.value).toBe('applied')
    expect(h.bridge.mode.value).toBe('oo')
    await h.bridge.reloadAfterApplied()
    expect(h.reloadHtml).toHaveBeenCalledWith(12)
    expect(h.bridge.mode.value).toBe('html')
    expect(h.bridge.state.value).toBe('html_idle')
  })

  it('applied 但快照缺 result_revision ⇒ 拒绝重载（不得伪造完成凭证）', async () => {
    const h = harness()
    await openEditor(h)
    await h.bridge.switchToHtml()
    h.bridge.ingestOperationSnapshot(
      snapshot({
        state: 'applied',
        shape: 'primary',
        applicationId: UUID(9),
        resultRevision: null,
      }),
    )
    expect(h.bridge.state.value).toBe('applied')
    await expectRejection(
      () => h.bridge.reloadAfterApplied(),
      'bridge_reload_without_result_revision',
    )
    expect(h.reloadHtml).not.toHaveBeenCalled()
  })

  it('未到 applied 不得 reload（Property 12：未收到终态不得切 HTML）', async () => {
    const h = harness()
    await openEditor(h)
    await h.bridge.switchToHtml()
    await expectRejection(() => h.bridge.reloadAfterApplied(), 'bridge_reload_before_applied')
    expect(h.reloadHtml).not.toHaveBeenCalled()
    expect(h.bridge.mode.value).toBe('oo')
  })

  it('跟错一条 operation ⇒ 拒绝（必须沿同一 requested operation）', async () => {
    const h = harness()
    await openEditor(h)
    await h.bridge.switchToHtml()
    expect(() =>
      h.bridge.ingestOperationSnapshot(
        snapshot({ requestedOperationId: UUID(77), canonicalOperationId: UUID(77) }),
      ),
    ).toThrow(WorkpaperSyncContractError)
    expect(h.bridge.state.value).toBe('waiting_application')
  })

  it('非法转换不改 mode（Property 46 后半，实测两个 ref 都没动）', async () => {
    const h = harness()
    await openEditor(h)
    await h.bridge.switchToHtml()
    h.bridge.ingestOperationSnapshot(
      snapshot({
        state: 'applied',
        shape: 'primary',
        applicationId: UUID(9),
        resultRevision: 12,
      }),
    )
    const before = { state: h.bridge.state.value, mode: h.bridge.mode.value }
    expect(() =>
      h.bridge.ingestOperationSnapshot(
        snapshot({ state: 'merging', shape: 'primary', applicationId: UUID(9) }),
      ),
    ).toThrow(WorkpaperSyncContractError)
    expect({ state: h.bridge.state.value, mode: h.bridge.mode.value }).toEqual(before)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// C. duplicate：requested 授权 → canonicalize → 不新建
// ═══════════════════════════════════════════════════════════════════════════

describe('duplicate 的 GET/timeline/conflicts/retry/resolve 都按 requested id 发起', () => {
  async function duplicateHarness(): Promise<Harness> {
    const h = harness()
    await openEditor(h)
    await h.bridge.switchToHtml()
    h.bridge.ingestOperationSnapshot(
      snapshot({
        state: 'duplicate',
        shape: 'duplicate',
        duplicateOfOperationId: UUID(31),
        canonicalOperationId: UUID(31),
      }),
    )
    expect(h.bridge.state.value).toBe('duplicate')
    return h
  }

  it('进入 duplicate 后 requested 与 canonical 两个 id 都保留', async () => {
    const h = await duplicateHarness()
    expect(h.bridge.requestedOperationId.value).toBe(UUID(30))
    expect(h.bridge.operation.value?.canonicalOperationId).toBe(UUID(31))
    expect(h.bridge.operation.value?.requestedOperationId).toBe(UUID(30))
  })

  it('五条调用逐一带 requested id（不是 canonical id）', async () => {
    const h = await duplicateHarness()
    h.api.getOperation.mockResolvedValue(
      snapshot({
        state: 'duplicate',
        shape: 'duplicate',
        duplicateOfOperationId: UUID(31),
        canonicalOperationId: UUID(31),
      }),
    )
    await h.bridge.refreshOperation()
    await h.bridge.fetchTimeline()
    await h.bridge.fetchConflicts()
    await h.bridge.retryOperation()
    await h.bridge.resolveConflicts({
      fence: {
        canonicalApplicationId: UUID(9),
        applicationEffectiveRequestSequence: 7,
        roomLatestDurableApplicationId: UUID(9),
        roomLatestDurableSequence: 7,
        conflictSetDigest: DIGEST(9),
        expectedCurrentRevision: 11,
        roomGeneration: 3,
        clientEditEpoch: 1,
      },
      resolutions: [{ conflictId: UUID(50), choice: 'incoming' }],
    })
    expect(h.api.getOperation.mock.calls[0][1]).toBe(UUID(30))
    expect(h.api.getOperationTimeline.mock.calls[0][1]).toBe(UUID(30))
    expect(h.api.getOperationConflicts.mock.calls[0][1]).toBe(UUID(30))
    expect(h.api.retryOperation.mock.calls[0][1]).toBe(UUID(30))
    expect(h.api.resolveConflicts.mock.calls[0][1].operationId).toBe(UUID(30))
  })

  it('duplicate 是 terminal：后续读取只更新投影，状态不动', async () => {
    const h = await duplicateHarness()
    h.api.getOperation.mockResolvedValue(
      snapshot({
        state: 'duplicate',
        shape: 'duplicate',
        duplicateOfOperationId: UUID(31),
        canonicalOperationId: UUID(31),
        durableAt: '2026-08-16T01:00:00Z',
      }),
    )
    await h.bridge.refreshOperation()
    expect(h.bridge.state.value).toBe('duplicate')
    expect(h.bridge.operation.value?.durableAt).toBe('2026-08-16T01:00:00Z')
  })

  it('canonical primary 换了一个 id ⇒ 拒绝（不得新建 operation）', async () => {
    const h = await duplicateHarness()
    h.api.getOperation.mockResolvedValue(
      snapshot({
        state: 'duplicate',
        shape: 'duplicate',
        duplicateOfOperationId: UUID(88),
        canonicalOperationId: UUID(88),
      }),
    )
    await expectRejection(() => h.bridge.refreshOperation(), 'bridge_duplicate_recanonicalized')
  })

  it('resolve 的 room fence 缺项 ⇒ 拒绝，不替调用方编造', async () => {
    const h = await duplicateHarness()
    await expectRejection(
      () =>
        h.bridge.resolveConflicts({
          fence: {
            canonicalApplicationId: UUID(9),
            applicationEffectiveRequestSequence: 7,
            roomLatestDurableApplicationId: '',
            roomLatestDurableSequence: 7,
            conflictSetDigest: DIGEST(9),
            expectedCurrentRevision: 11,
            roomGeneration: 3,
            clientEditEpoch: 1,
          },
          resolutions: [],
        }),
      'bridge_resolve_fence_incomplete',
    )
    expect(h.api.resolveConflicts).not.toHaveBeenCalled()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// D. same-application fold vs 不同 canonical application
// ═══════════════════════════════════════════════════════════════════════════

describe('same-app 更高 sequence 只 fold，不同 canonical application 才 rebase', () => {
  it('同一 application 的更高 sequence：只更新 effective sequence，状态不变', async () => {
    const h = harness()
    await openEditor(h)
    await h.bridge.switchToHtml()
    h.bridge.ingestOperationSnapshot(
      snapshot({ state: 'conflict', shape: 'primary', applicationId: UUID(9) }),
    )
    expect(h.bridge.state.value).toBe('conflict')
    h.api.getOperationConflicts.mockResolvedValueOnce({
      canonical_application_id: UUID(9),
      incoming_sequence: 7,
      groups: [],
    })
    await h.bridge.fetchConflicts()
    expect(h.bridge.applicationEffectiveSequence.value).toBe(7)
    h.api.getOperationConflicts.mockResolvedValueOnce({
      canonical_application_id: UUID(9),
      incoming_sequence: 9,
      groups: [],
    })
    await h.bridge.fetchConflicts()
    expect(h.bridge.applicationEffectiveSequence.value).toBe(9)
    expect(h.bridge.state.value).toBe('conflict')
  })

  it('sequence 单调 fold：更低的 sequence 不把它拉回去', async () => {
    const h = harness()
    await openEditor(h)
    await h.bridge.switchToHtml()
    h.bridge.observeApplicationFence({ applicationId: UUID(9), effectiveRequestSequence: 9 })
    const result = h.bridge.observeApplicationFence({
      applicationId: UUID(9),
      effectiveRequestSequence: 4,
    })
    expect(h.bridge.applicationEffectiveSequence.value).toBe(9)
    expect(result.folded).toBe(false)
    expect(result.rebased).toBe(false)
  })

  it('不同 canonical application ⇒ 进 refresh_required（需重载新基线）', async () => {
    const h = harness()
    await openEditor(h)
    await h.bridge.switchToHtml()
    h.bridge.ingestOperationSnapshot(
      snapshot({ state: 'conflict', shape: 'primary', applicationId: UUID(9) }),
    )
    const result = h.bridge.observeApplicationFence({
      applicationId: UUID(99),
      effectiveRequestSequence: 12,
    })
    expect(result.rebased).toBe(true)
    expect(h.bridge.state.value).toBe('refresh_required')
    expect(h.bridge.canonicalApplicationId.value).toBe(UUID(99))
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// E. recovery：authorization-first
// ═══════════════════════════════════════════════════════════════════════════

describe('recovery：list / claim / download-only 都显式带 project/wp/entry', () => {
  it('list 带显式 scope 与 room/generation，且进入 recovery_pending 时三实体为 0', async () => {
    const h = harness()
    const cases = await h.bridge.listRecoveryCases({ roomId: UUID(21), generation: 3 })
    const [scope, input] = h.api.listRecoveryCases.mock.calls[0]
    expect(scope).toEqual({ projectId: PROJECT, wpId: WP, entryId: ENTRY })
    expect(input).toEqual({ roomId: UUID(21), generation: 3 })
    expect(h.bridge.state.value).toBe('recovery_pending')
    expect(cases[0].operationId).toBeNull()
    expect(cases[0].applicationId).toBeNull()
    expect(cases[0].forcesaveRequestId).toBeNull()
  })

  it('list 缺 room/generation 且无 descriptor ⇒ 拒绝，不打端点', async () => {
    const h = harness()
    await expectRejection(
      () => h.bridge.listRecoveryCases(),
      'bridge_recovery_room_scope_required',
    )
    expect(h.api.listRecoveryCases).not.toHaveBeenCalled()
  })

  it('recovery_pending 下普通 retry 被拒（三实体为 0，无 operation 可重试）', async () => {
    const h = harness()
    await h.bridge.listRecoveryCases({ roomId: UUID(21), generation: 3 })
    await expectRejection(() => h.bridge.retryOperation(), 'bridge_no_requested_operation')
    expect(h.api.retryOperation).not.toHaveBeenCalled()
  })

  const CLAIM_INPUT = {
    caseId: UUID(40),
    roomId: UUID(21),
    participantId: UUID(22),
    priorConfirmationId: UUID(41),
    expectedGeneration: 3,
    expectedWriteFence: 5,
    expectedDefinitionBundleSha256: DIGEST(3),
    expectedCurrentRevision: 11,
  }

  it('claim 成功后才同时关联三实体并进入 primary 终态', async () => {
    const h = harness()
    h.api.getOperation.mockResolvedValue(
      snapshot({
        requestedOperationId: UUID(43),
        canonicalOperationId: UUID(43),
        state: 'application_bound',
        shape: 'primary',
        applicationId: UUID(44),
      }),
    )
    await h.bridge.listRecoveryCases({ roomId: UUID(21), generation: 3 })
    await h.bridge.claimRecoveryCase(CLAIM_INPUT)
    expect(h.bridge.state.value).toBe('application_bound')
    expect(h.bridge.requestedOperationId.value).toBe(UUID(43))
    expect(h.bridge.canonicalApplicationId.value).toBe(UUID(44))
    const [scope] = h.api.claimRecoveryCase.mock.calls[0]
    expect(scope).toEqual({ projectId: PROJECT, wpId: WP, entryId: ENTRY })
  })

  it('claim 命中既有 application ⇒ 进 terminal duplicate（不得默认成 primary）', async () => {
    const h = harness()
    h.api.getOperation.mockResolvedValue(
      snapshot({
        requestedOperationId: UUID(43),
        canonicalOperationId: UUID(31),
        state: 'duplicate',
        shape: 'duplicate',
        duplicateOfOperationId: UUID(31),
      }),
    )
    await h.bridge.listRecoveryCases({ roomId: UUID(21), generation: 3 })
    await h.bridge.claimRecoveryCase(CLAIM_INPUT)
    // 形态取自**服务端读回来的 operation**，而不是一个写死的默认值：
    // claim 的 202 响应体没有 shape，写死 'primary' 会把 duplicate 显示成 primary。
    expect(h.api.getOperation).toHaveBeenCalledWith(
      { projectId: PROJECT, wpId: WP, entryId: ENTRY },
      UUID(43),
    )
    expect(h.bridge.state.value).toBe('duplicate')
    expect(h.bridge.operation.value?.canonicalOperationId).toBe(UUID(31))
  })

  it('claim 后 operation 仍是两 link 均空的 shell ⇒ fail visible（不猜终态）', async () => {
    const h = harness()
    h.api.getOperation.mockResolvedValue(
      snapshot({ requestedOperationId: UUID(43), canonicalOperationId: UUID(43) }),
    )
    await h.bridge.listRecoveryCases({ roomId: UUID(21), generation: 3 })
    await expectRejection(
      () => h.bridge.claimRecoveryCase(CLAIM_INPUT),
      'bridge_claim_landed_pre_correlation',
    )
    expect(h.bridge.state.value).toBe('recovery_claiming')
  })

  it('claim 失败 ⇒ 回 recovery_pending，三实体仍为 0，不进 operation 流程', async () => {
    const h = harness({
      claimRecoveryCase: vi.fn(async () => {
        throw {
          response: {
            status: 409,
            data: { detail: { error_code: 'recovery_prior_confirmation_stale', message: 'x' } },
          },
        }
      }),
    })
    await h.bridge.listRecoveryCases({ roomId: UUID(21), generation: 3 })
    await expect(h.bridge.claimRecoveryCase(CLAIM_INPUT)).rejects.toBeTruthy()
    expect(h.bridge.state.value).toBe('recovery_pending')
    expect(h.bridge.requestedOperationId.value).toBeNull()
    expect(h.bridge.canonicalApplicationId.value).toBeNull()
  })

  it('prior confirmation 不在候选内 / bundle digest 非法 / fence 形态非法 ⇒ 发出前拒绝', async () => {
    const h = harness()
    await h.bridge.listRecoveryCases({ roomId: UUID(21), generation: 3 })
    const base = CLAIM_INPUT
    await expectRejection(
      () => h.bridge.claimRecoveryCase({ ...base, priorConfirmationId: UUID(999) }),
      'bridge_claim_prior_confirmation_not_candidate',
    )
    await expectRejection(
      () => h.bridge.claimRecoveryCase({ ...base, expectedDefinitionBundleSha256: '0'.repeat(64) }),
      'bridge_claim_bundle_digest_invalid',
    )
    await expectRejection(
      () => h.bridge.claimRecoveryCase({ ...base, expectedGeneration: 0 }),
      'bridge_claim_fence_invalid',
    )
    await expectRejection(
      () => h.bridge.claimRecoveryCase({ ...base, caseId: UUID(777) }),
      'bridge_claim_case_unknown',
    )
    expect(h.api.claimRecoveryCase).not.toHaveBeenCalled()
  })

  it('download-only 走独立终态，三实体为 0，之后不能变 applied', async () => {
    const h = harness()
    await h.bridge.listRecoveryCases({ roomId: UUID(21), generation: 3 })
    const claim = await h.bridge.terminateRecoveryDownloadOnly(UUID(40))
    expect(claim).toBe('claim-1')
    expect(h.bridge.state.value).toBe('recovery_download_only')
    // 下载 artifact 不改状态，也不产生 operation。
    await h.bridge.downloadRecoveryArtifact({ caseId: UUID(40), claim })
    expect(h.bridge.state.value).toBe('recovery_download_only')
    expect(h.bridge.requestedOperationId.value).toBeNull()
    expect(h.api.downloadRecoveryArtifact.mock.calls[0][1]).toEqual({
      caseId: UUID(40),
      claim: 'claim-1',
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// F. close 仲裁
// ═══════════════════════════════════════════════════════════════════════════

describe('close leader 失权：先 stale/successor 进展，无 successor 才 recovery-required', () => {
  it('失权后不是永久 loading、也不是普通成功', async () => {
    const h = harness()
    await openEditor(h)
    await h.bridge.switchToHtml()
    h.bridge.notifyCloseAuthorizationLost()
    expect(h.bridge.state.value).toBe('close_authorization_stale')
    expect(h.bridge.feedback.value.kind).toBe('progress')
    expect(h.bridge.feedback.value.message).toContain('失去资格')
  })

  it('合法 successor 完成 ⇒ applied；缺 successor id ⇒ 拒绝', async () => {
    const h = harness()
    await openEditor(h)
    await h.bridge.switchToHtml()
    h.bridge.notifyCloseAuthorizationLost()
    expect(() => h.bridge.notifyCloseSuccessorApplied('')).toThrow(WorkpaperSyncContractError)
    expect(h.bridge.state.value).toBe('close_authorization_stale')
    h.bridge.notifyCloseSuccessorApplied(UUID(77))
    expect(h.bridge.state.value).toBe('applied')
  })

  it('无 successor ⇒ close_recovery_required，文案不是成功', async () => {
    const h = harness()
    await openEditor(h)
    await h.bridge.switchToHtml()
    h.bridge.notifyCloseAuthorizationLost()
    h.bridge.notifyCloseNoSuccessor()
    expect(h.bridge.state.value).toBe('close_recovery_required')
    expect(h.bridge.feedback.value.kind).toBe('progress')
    expect(h.bridge.feedback.value.message).not.toContain('成功')
    expect(h.bridge.feedback.value.message).toContain('恢复')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// G. Property 48：失败不被成功文案覆盖
// ═══════════════════════════════════════════════════════════════════════════

describe('Property 48: 同步失败不被成功文案覆盖', () => {
  it('reload 失败后，后续 destroy/迁移成功都不改回成功文案', async () => {
    const h = harness()
    await openEditor(h)
    await h.bridge.switchToHtml()
    h.bridge.ingestOperationSnapshot(
      snapshot({
        state: 'applied',
        shape: 'primary',
        applicationId: UUID(9),
        resultRevision: 12,
      }),
    )
    expect(h.bridge.feedback.value.kind).toBe('success')
    h.reloadHtml.mockRejectedValueOnce(new Error('重载失败'))
    await expect(h.bridge.reloadAfterApplied()).rejects.toThrow('重载失败')
    expect(h.bridge.feedback.value.kind).toBe('error')
    // 后续「清理成功」不得洗掉 error。
    h.bridge.destroy()
    h.bridge.migrateMode()
    h.bridge.notifyDirty(false)
    expect(h.bridge.feedback.value.kind).toBe('error')
    expect(h.bridge.lastError.value?.stage).toBe('reload')
  })

  it('error 状态下重载被拒（转换表没有这条边）', async () => {
    const h = harness()
    await openEditor(h)
    await h.bridge.switchToHtml()
    h.bridge.ingestOperationSnapshot(
      snapshot({
        state: 'applied',
        shape: 'primary',
        applicationId: UUID(9),
        resultRevision: 12,
      }),
    )
    h.reloadHtml.mockRejectedValueOnce(new Error('x'))
    await expect(h.bridge.reloadAfterApplied()).rejects.toBeTruthy()
    expect(h.bridge.state.value).toBe('error')
    await expectRejection(() => h.bridge.reloadAfterApplied(), 'bridge_reload_before_applied')
  })

  it('只有用户显式发起的新尝试才清掉 sticky error', async () => {
    const h = harness()
    h.flushHtml.mockRejectedValueOnce(new Error('flush 失败'))
    await expect(h.bridge.switchToOnlyOffice()).rejects.toBeTruthy()
    expect(h.bridge.lastError.value).not.toBeNull()
    await h.bridge.switchToOnlyOffice()
    expect(h.bridge.lastError.value).toBeNull()
    expect(h.bridge.feedback.value.kind).not.toBe('error')
  })

  it('reset 之后回到 html_idle 并清空错误', async () => {
    const h = harness()
    await openEditor(h)
    await h.bridge.switchToHtml()
    h.bridge.ingestOperationSnapshot(
      snapshot({
        state: 'duplicate',
        shape: 'duplicate',
        duplicateOfOperationId: UUID(31),
        canonicalOperationId: UUID(31),
      }),
    )
    h.bridge.reset()
    expect(h.bridge.state.value).toBe('html_idle')
    expect(h.bridge.mode.value).toBe('html')
    expect(h.bridge.lastError.value).toBeNull()
    expect(h.bridge.requestedOperationId.value).toBeNull()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// H. scope / 授权失败不泄露存在性
// ═══════════════════════════════════════════════════════════════════════════

describe('scope 或授权失败可诊断但不泄露存在性', () => {
  it('统一 404（纯字符串 detail）合成唯一非泄露码，消息不含对象 id', async () => {
    const h = harness({
      getOperation: vi.fn(async () => {
        throw { response: { status: 404, data: { detail: '资源不存在或不可访问' } } }
      }),
    })
    await openEditor(h)
    await h.bridge.switchToHtml()
    await expect(h.bridge.refreshOperation()).rejects.toBeTruthy()
    const error = h.bridge.lastError.value
    expect(error?.errorCode).toBe(WP_BRIDGE_NON_DISCLOSURE_CODE)
    expect(error?.httpStatus).toBe(404)
    expect(error?.message).not.toContain(UUID(30))
    expect(error?.message).not.toContain('不存在')
    expect(error?.verdict.retryableOperation).toBe(false)
  })

  it('403 与 404 归一成同一个码（两者不可区分）', () => {
    const forbidden = describeBridgeFailure('probe', { response: { status: 403, data: {} } })
    const missing = describeBridgeFailure('probe', { response: { status: 404, data: {} } })
    expect(forbidden.errorCode).toBe(missing.errorCode)
    expect(forbidden.message).toBe(missing.message)
    expect(forbidden.httpStatus).not.toBe(missing.httpStatus)
  })

  it('带 error_code 的 403 保留业务码（区分「工作流锁定」与「无权限」）', () => {
    const described = describeBridgeFailure('probe', {
      response: {
        status: 403,
        data: { detail: { error_code: 'workflow_locked', message: '流程已锁定' } },
      },
    })
    expect(described.errorCode).toBe('workflow_locked')
    expect(described.message).toBe('流程已锁定')
  })

  it('未登记的 error_code 显式标 unregistered（不兜底成普通失败）', () => {
    const described = describeBridgeFailure('probe', {
      response: {
        status: 500,
        data: { detail: { error_code: 'brand_new_code', message: 'x' } },
      },
    })
    expect(described.verdict.unregistered).toBe(true)
    expect(described.verdict.retryableOperation).toBe(true)
  })

  it('三个分桶用三个互不相同的码（本地/传输 ≠ scope 授权 ≠ 服务端业务码）', () => {
    const local = describeBridgeFailure('probe', new Error('断网了'))
    const scope = describeBridgeFailure('probe', { response: { status: 404, data: {} } })
    const business = describeBridgeFailure('probe', {
      response: {
        status: 409,
        data: { detail: { error_code: 'launch_descriptor_stale_identity', message: 'x' } },
      },
    })
    expect(new Set([local.errorCode, scope.errorCode, business.errorCode]).size).toBe(3)
    expect(local.errorCode).toBe(WP_BRIDGE_LOCAL_FAILURE_CODE)
    expect(local.message).toBe('断网了')
    // 无响应 = 本地/网络：AC 4.4 要求保持原模式并允许重试。
    expect(local.verdict.retryableOperation).toBe(true)
    expect(local.verdict.canEnterEditing).toBe(false)
    expect(local.verdict.canForcesave).toBe(false)
    // scope/授权：三门全关，且不可重试。
    expect(scope.verdict.retryableOperation).toBe(false)
    // 陈旧 identity：三门全关。
    expect(business.staleIdentity).toBe(true)
    expect(business.verdict.retryableOperation).toBe(false)
  })

  it('5xx 纯文本可重试，4xx 纯文本不可重试（都归到本地/传输桶）', () => {
    const server = describeBridgeFailure('probe', {
      response: { status: 500, data: { detail: '内部错误' } },
    })
    const client = describeBridgeFailure('probe', {
      response: { status: 422, data: { detail: '参数不合法' } },
    })
    expect(server.errorCode).toBe(WP_BRIDGE_LOCAL_FAILURE_CODE)
    expect(server.verdict.retryableOperation).toBe(true)
    expect(client.errorCode).toBe(WP_BRIDGE_LOCAL_FAILURE_CODE)
    expect(client.verdict.retryableOperation).toBe(false)
  })

  it('本地钩子抛的普通 Error 被原样抛出，且 lastError 真的被记住', async () => {
    const h = harness()
    const boom = new Error('本地 flush 崩了')
    h.flushHtml.mockRejectedValueOnce(boom)
    await expect(h.bridge.switchToOnlyOffice()).rejects.toBe(boom)
    expect(h.bridge.lastError.value?.errorCode).toBe(WP_BRIDGE_LOCAL_FAILURE_CODE)
    expect(h.bridge.lastError.value?.stage).toBe('flush')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// I. rollback
// ═══════════════════════════════════════════════════════════════════════════

describe('rollback 只接受 opaque UUID', () => {
  it('opaque UUID 透传到端点', async () => {
    const h = harness()
    await h.bridge.rollbackVersion({
      versionId: UUID(60),
      expectedCurrentRevision: 11,
      confirmed: true,
    })
    const [scope, input] = h.api.rollbackVersion.mock.calls[0]
    expect(scope).toEqual({ projectId: PROJECT, wpId: WP, entryId: ENTRY })
    expect(input.versionId).toBe(UUID(60))
  })

  it('numeric revision 不得拼 route（API 层单点拒绝，桥不复制第二份判断）', async () => {
    const bridge = useWorkpaperSyncBridge({
      entryId: ref(ENTRY),
      wpId: ref(WP),
      projectId: ref(PROJECT),
      capability: 'bidirectional',
      flushHtml: async () => ({ expectedRevision: 1, projection: {} }),
      reloadHtml: async () => {},
      storage: null,
      installBeforeUnload: false,
    })
    await expectRejection(
      () => bridge.rollbackVersion({ versionId: '12', expectedCurrentRevision: 11, confirmed: true }),
      'version_id_not_opaque',
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// J. beforeunload / route leave
// ═══════════════════════════════════════════════════════════════════════════

describe('beforeunload / route leave 阻断 dirty 与 in-flight', () => {
  let installed: ReturnType<typeof useWorkpaperSyncBridge> | null = null

  beforeEach(() => {
    installed = null
  })

  afterEach(() => {
    installed?.destroy()
  })

  function installedHarness(): {
    bridge: ReturnType<typeof useWorkpaperSyncBridge>
    api: Harness['api']
    fire: () => boolean
  } {
    const base = harness()
    const bridge = useWorkpaperSyncBridge({
      entryId: ref(ENTRY),
      wpId: ref(WP),
      projectId: ref(PROJECT),
      sheetKey: ref('D4-1'),
      capability: 'bidirectional',
      flushHtml: async () => ({ expectedRevision: 11, projection: {} }),
      reloadHtml: async () => {},
      api: base.api as unknown as WorkpaperSyncApiSurface,
      storage: new MemoryStorage(),
      installBeforeUnload: true,
    })
    installed = bridge
    return {
      bridge,
      api: base.api,
      fire: () => {
        const event = new Event('beforeunload', { cancelable: true })
        window.dispatchEvent(event)
        return event.defaultPrevented
      },
    }
  }

  it('idle 时不拦（否则打开页面就走不掉）', () => {
    const h = installedHarness()
    expect(h.bridge.beforeUnloadInstalled.value).toBe(true)
    expect(h.bridge.canLeave.value).toBe(true)
    expect(h.fire()).toBe(false)
  })

  it('dirty 时真的 preventDefault（同一个已注册的 handler）', () => {
    const h = installedHarness()
    h.bridge.notifyDirty(true)
    expect(h.bridge.canLeave.value).toBe(false)
    expect(h.bridge.leaveBlockReason.value).toContain('未保存')
    expect(h.fire()).toBe(true)
  })

  it('forcesave accepted / waiting callback 期间阻断', async () => {
    const h = installedHarness()
    await h.bridge.switchToOnlyOffice()
    h.bridge.notifyEditorMounted()
    await h.bridge.notifyDocumentReady()
    await h.bridge.switchToHtml()
    expect(h.bridge.state.value).toBe('waiting_application')
    expect(h.bridge.canLeave.value).toBe(false)
    expect(h.bridge.routeLeaveGuard()).toBe(false)
    expect(h.fire()).toBe(true)
  })

  it('applied 但还没重载时仍阻断（否则用户下次看到旧 revision）', async () => {
    const h = installedHarness()
    await h.bridge.switchToOnlyOffice()
    h.bridge.notifyEditorMounted()
    await h.bridge.notifyDocumentReady()
    await h.bridge.switchToHtml()
    h.bridge.ingestOperationSnapshot(
      snapshot({
        state: 'applied',
        shape: 'primary',
        applicationId: UUID(9),
        resultRevision: 12,
      }),
    )
    expect(h.bridge.canLeave.value).toBe(false)
    expect(h.fire()).toBe(true)
  })

  it('destroy 之后 handler 被摘掉（不再拦别的页面）', () => {
    const h = installedHarness()
    h.bridge.notifyDirty(true)
    expect(h.fire()).toBe(true)
    h.bridge.destroy()
    expect(h.bridge.beforeUnloadInstalled.value).toBe(false)
    expect(h.fire()).toBe(false)
  })

  it('in-flight 集合覆盖全部「还在动」的状态，且不含 oo_editing/html_idle/终态', () => {
    const settled = WP_BRIDGE_STATES.filter((s) => !WP_BRIDGE_IN_FLIGHT_STATES.includes(s))
    expect([...settled].sort()).toEqual(
      [
        'close_authorization_stale',
        'close_recovery_required',
        'duplicate',
        'error',
        'html_idle',
        'oo_editing',
        'recovery_download_only',
        'recovery_pending',
      ].sort(),
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// K. localStorage 迁移接线
// ═══════════════════════════════════════════════════════════════════════════

describe('桥是 localStorage 键的唯一拥有者', () => {
  it('迁移用的是按 entry/wp/sheet 的统一键', async () => {
    const h = harness()
    h.storage.setItem(`h4-dual-mode:${WP}`, 'onlyoffice')
    const result = h.bridge.migrateMode()
    expect(result.mode).toBe('oo')
    expect(h.bridge.modeStorageKey.value).toBe(
      `workpaper-sync-mode:${ENTRY}:${WP}:D4-1`,
    )
    expect(h.storage.snapshot()).toEqual({ [h.bridge.modeStorageKey.value]: 'oo' })
  })

  it('capability 不支持存量值时回落，不打开不支持模式', () => {
    const h = harness({}, { capability: 'single_html' })
    h.storage.setItem(`h4-dual-mode:${WP}`, 'onlyoffice')
    const result = h.bridge.migrateMode()
    expect(result.mode).toBe('html')
    expect(result.fallbackApplied).toBe(true)
    expect(h.bridge.migration.value?.fallbackReason).toBe(
      'capability_does_not_support_stored_mode',
    )
  })
})
