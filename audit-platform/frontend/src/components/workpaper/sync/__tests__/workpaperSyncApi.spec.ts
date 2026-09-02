// spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 31
//
// API 层的**行为侧**判据：每条都真跑 client method、再检查实际发出的 URL / header / body。
// 「函数存在」「路径模板长得对」这类形态判据在 Task 28 已被证明会全绿而生产恒 404，
// 所以这里一律驱动真实调用。
//
// Validates: Requirements 3.1, 3.6, 3.7, 5.8, 11.4, 11.6
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mockGet = vi.fn()
const mockPost = vi.fn()
vi.mock('@/utils/http', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
  },
}))

import {
  WP_SYNC_IDEMPOTENT_ENDPOINTS,
  WP_SYNC_ROUTES,
} from '../workpaperSyncContract.generated'
import {
  CLAIM_REQUEST_ALLOWED_KEYS,
  WORKPAPER_SYNC_CLIENT_ENDPOINTS,
  buildClaimRequestBody,
  buildSyncEndpointUrl,
  buildSyncEntryPrefix,
  claimRecoveryCase,
  confirmDescriptor,
  createCloseIntent,
  createPendingMutation,
  downloadRecoveryArtifact,
  encodeEntryId,
  getOperation,
  getOperationConflicts,
  getOperationTimeline,
  getRecoveryCaseTimeline,
  listRecoveryCases,
  materialize,
  requestForcesave,
  resolveConflicts,
  retryOperation,
  rollbackVersion,
  terminateRecoveryDownloadOnly,
} from '../workpaperSyncApi'
import { WorkpaperSyncContractError, buildDescriptorConfirmPayload } from '../workpaperSyncDto'

const DIGEST_A = 'a'.repeat(64)
const DIGEST_B = 'b'.repeat(64)
const UUID = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`

/** 真实的**四段** entry id（manifest 里最深的形态）。单段占位值证不出 `:path`。 */
const DEEP_ENTRY = 'xlsx/d4/analysis/d4-tab-customer-price'
const TWO_SEGMENT_ENTRY = 'xlsx/gt-d2-accounts-receivable'

const SCOPE = {
  projectId: UUID(101),
  wpId: UUID(102),
  entryId: DEEP_ENTRY,
} as const

function descriptorPayload() {
  const slot = { type: 'definition', sha256: DIGEST_B }
  return {
    operation_id: UUID(1),
    room_id: UUID(2),
    participant_id: UUID(3),
    doc_key: 'doc-key-1',
    generation: 3,
    server_applied_revision: 12,
    client_confirmed_base_revision: 12,
    content_version_id: UUID(4),
    representation_id: UUID(5),
    representation_generation: 4,
    artifact_sha256: DIGEST_A,
    write_fence_epoch: 9,
    authority_model: 'projection_contract',
    authority_model_definition_sha256: DIGEST_B,
    definition_bundle_id: UUID(6),
    definition_bundle_sha256: DIGEST_A,
    definition_bundle_slots: { template: slot, instrumentation: slot, contract: slot },
    document_type: 'xlsx',
    mode: 'edit',
    onlyoffice_config: { document: { key: 'doc-key-1' } },
    replayed: false,
  }
}

function expectRefusal(run: () => unknown, code: string): void {
  let caught: unknown = null
  try {
    run()
  } catch (error) {
    caught = error
  }
  expect(caught, `期望抛 code=${code}`).toBeInstanceOf(WorkpaperSyncContractError)
  expect((caught as WorkpaperSyncContractError).code).toBe(code)
}

async function expectAsyncRefusal(run: () => Promise<unknown>, code: string): Promise<void> {
  let caught: unknown = null
  try {
    await run()
  } catch (error) {
    caught = error
  }
  expect(caught, `期望抛 code=${code}`).toBeInstanceOf(WorkpaperSyncContractError)
  expect((caught as WorkpaperSyncContractError).code).toBe(code)
}

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  mockGet.mockResolvedValue({ data: {} })
  mockPost.mockResolvedValue({ data: {} })
})

// ═══════════════════════════════════════════════════════════════════════════
// A. 多段 entry_id 不得 percent-encode 其中的 `/`
// ═══════════════════════════════════════════════════════════════════════════

describe('多段 entry_id 的 URL 拼接', () => {
  it.each([
    ['two-segment', TWO_SEGMENT_ENTRY],
    ['four-segment', DEEP_ENTRY],
    ['docx', 'docx/gt-a10-bundle'],
  ])('%s：分隔符 `/` 原样进入 URL', (_label, entryId) => {
    const encoded = encodeEntryId(entryId)
    expect(encoded).toBe(entryId)
    expect(encoded).not.toContain('%2F')
    expect(encoded).not.toContain('%2f')
  })

  it('前缀里三段 scope 全在，且 entry 段保留斜杠', () => {
    const prefix = buildSyncEntryPrefix(SCOPE)
    expect(prefix).toBe(
      `/api/projects/${UUID(101)}/workpapers/${UUID(102)}/sync/entries/${DEEP_ENTRY}`,
    )
    // 段数 = 固定 7 段（api/projects/{pid}/workpapers/{wpid}/sync/entries）+ entry 的段数。
    // 写死 9 会在四段 entry 上假红；`%2F` 编码后会塌成 8 段，故这条判据能抓住两种漂移。
    const fixed = 7
    expect(prefix.split('/').filter(Boolean)).toHaveLength(
      fixed + DEEP_ENTRY.split('/').length,
    )
  })

  it('段内特殊字符仍被转义（逐段 encode）', () => {
    expect(encodeEntryId('xlsx/a b/c?d')).toBe('xlsx/a%20b/c%3Fd')
  })

  it.each([['前导斜杠', '/xlsx/a'], ['尾随斜杠', 'xlsx/a/'], ['空段', 'xlsx//a']])(
    '%s 的 entry_id 拒绝（会让路由解出的值不等于原值）',
    (_label, entryId) => {
      expectRefusal(() => encodeEntryId(entryId), 'entry_id_malformed')
    },
  )

  it('scope 缺段时拒绝', () => {
    expectRefusal(() => buildSyncEntryPrefix({ ...SCOPE, projectId: '' }), 'scope_segment_missing')
    expectRefusal(() => buildSyncEntryPrefix({ ...SCOPE, wpId: '  ' }), 'scope_segment_missing')
    expectRefusal(() => buildSyncEntryPrefix({ ...SCOPE, entryId: '' }), 'scope_segment_missing')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// B. 路由表与 client method 一一对应
// ═══════════════════════════════════════════════════════════════════════════

/** 每个 endpoint 的驱动器：真调 client method 一次。 */
const DRIVERS: Record<string, () => Promise<unknown>> = {
  create_pending_mutation: () =>
    createPendingMutation(SCOPE, {
      sheetKey: 's',
      expectedRevision: 11,
      projection: { fields: [] },
    }).catch(() => null),
  materialize: () =>
    materialize(SCOPE, {
      sheetKey: 's',
      expectedRevision: 11,
      pendingMutationToken: 'tok',
      projection: { fields: [] },
    }).catch(() => null),
  confirm_descriptor: () =>
    confirmDescriptor(SCOPE, {
      descriptor: { roomId: UUID(2) } as never,
      confirmPayload: { participant_id: UUID(3) },
    }).catch(() => null),
  request_forcesave: () =>
    requestForcesave(SCOPE, { roomId: UUID(2), participantId: UUID(3) }).catch(() => null),
  create_close_intent: () =>
    createCloseIntent(SCOPE, { roomId: UUID(2), participantId: UUID(3) }).catch(() => null),
  list_recovery_cases: () =>
    listRecoveryCases(SCOPE, { roomId: UUID(2), generation: 3 }).catch(() => null),
  claim_recovery_case: () =>
    claimRecoveryCase(SCOPE, {
      caseId: UUID(50),
      roomId: UUID(2),
      participantId: UUID(3),
      priorConfirmationId: UUID(51),
      expectedGeneration: 3,
      expectedWriteFence: 9,
      expectedDefinitionBundleSha256: DIGEST_A,
      expectedCurrentRevision: 12,
    }).catch(() => null),
  terminate_recovery_download_only: () =>
    terminateRecoveryDownloadOnly(SCOPE, UUID(50)).catch(() => null),
  download_recovery_artifact: () =>
    downloadRecoveryArtifact(SCOPE, { caseId: UUID(50), claim: 'signed' }).catch(() => null),
  get_operation: () => getOperation(SCOPE, UUID(30)).catch(() => null),
  get_operation_conflicts: () => getOperationConflicts(SCOPE, UUID(30)).catch(() => null),
  get_operation_timeline: () => getOperationTimeline(SCOPE, UUID(30)).catch(() => null),
  get_recovery_case_timeline: () => getRecoveryCaseTimeline(SCOPE, UUID(50)).catch(() => null),
  resolve_conflicts: () =>
    resolveConflicts(SCOPE, {
      operationId: UUID(30),
      expectedCurrentRevision: 12,
      roomGeneration: 3,
      clientEditEpoch: 5,
      canonicalApplicationId: UUID(40),
      applicationEffectiveRequestSequence: 8,
      roomLatestDurableApplicationId: UUID(40),
      roomLatestDurableSequence: 8,
      conflictSetDigest: DIGEST_A,
      resolutions: [{ conflictId: UUID(70), choice: 'incoming' }],
    }).catch(() => null),
  retry_operation: () => retryOperation(SCOPE, UUID(30)).catch(() => null),
  rollback_version: () =>
    rollbackVersion(SCOPE, {
      versionId: UUID(80),
      expectedCurrentRevision: 12,
      confirmed: true,
    }).catch(() => null),
}

describe('生成的路由表与 client 一一对应', () => {
  it('每条后端路由都有恰一个 client method（无孤立路由、无死 client）', () => {
    const routeEndpoints = WP_SYNC_ROUTES.map((route) => route.endpoint).sort()
    const clientEndpoints = Object.values(WORKPAPER_SYNC_CLIENT_ENDPOINTS).sort()
    expect(clientEndpoints).toEqual(routeEndpoints)
    expect(Object.keys(DRIVERS).sort()).toEqual(routeEndpoints)
  })

  it.each(WP_SYNC_ROUTES.map((route) => [route.endpoint, route.method, route.suffix]))(
    '%s 真实打到 %s + 生成的 suffix 模板',
    async (endpoint, method, _suffix) => {
      await DRIVERS[endpoint as string]()
      const calls = method === 'GET' ? mockGet.mock.calls : mockPost.mock.calls
      expect(calls.length, `${endpoint} 没有发出 ${method} 请求`).toBe(1)
      const url = calls[0][0] as string
      expect(url.startsWith(buildSyncEntryPrefix(SCOPE)), url).toBe(true)
      // 三段显式 scope 都在 URL 里。
      expect(url).toContain(SCOPE.projectId)
      expect(url).toContain(SCOPE.wpId)
      expect(url).toContain(SCOPE.entryId)
      // 没有未替换的占位符。
      expect(url).not.toMatch(/\{[a-z_]+\}/)
    },
  )
})

// ═══════════════════════════════════════════════════════════════════════════
// C. Idempotency-Key：服务端强制的七个端点必须真发出
// ═══════════════════════════════════════════════════════════════════════════

describe('Idempotency-Key 是必发 header（不是「约定」）', () => {
  it.each(WP_SYNC_IDEMPOTENT_ENDPOINTS.map((endpoint) => [endpoint]))(
    '%s 的请求带非空 Idempotency-Key',
    async (endpoint) => {
      await DRIVERS[endpoint]()
      const calls = [...mockGet.mock.calls, ...mockPost.mock.calls]
      expect(calls.length, `${endpoint} 没有发出请求`).toBe(1)
      const config = calls[0][calls[0].length - 1] as { headers?: Record<string, string> }
      const key = config?.headers?.['Idempotency-Key']
      expect(typeof key, `${endpoint} 缺 Idempotency-Key header`).toBe('string')
      expect(String(key).trim().length).toBeGreaterThan(0)
    },
  )

  it('调用点自带的 key 被逐字使用（重放同一 key 是协议能力）', async () => {
    mockPost.mockResolvedValue({
      data: {
        pending_mutation_token: 'tok',
        expected_revision: 11,
        payload_sha256: DIGEST_A,
        expires_at: '2026-01-01T00:00:00+00:00',
      },
    })
    const receipt = await createPendingMutation(SCOPE, {
      sheetKey: 's',
      expectedRevision: 11,
      projection: {},
      idempotencyKey: 'replay-me',
    })
    const config = mockPost.mock.calls[0][2] as { headers: Record<string, string> }
    expect(config.headers['Idempotency-Key']).toBe('replay-me')
    expect(receipt.idempotencyKey).toBe('replay-me')
  })

  it('生成表说必填而调用点给了空 key ⇒ 发出前就拒绝', async () => {
    await expectAsyncRefusal(
      () =>
        createPendingMutation(SCOPE, {
          sheetKey: 's',
          expectedRevision: 11,
          projection: {},
          idempotencyKey: '   ',
        }),
      'idempotency_key_required',
    )
    expect(mockPost).not.toHaveBeenCalled()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// D. envelope 只解一次
// ═══════════════════════════════════════════════════════════════════════════

describe('平台 envelope 只在 API 层解一次', () => {
  it('拦截器已解包的载荷原样交给 parser', async () => {
    mockPost.mockResolvedValue({
      data: {
        pending_mutation_token: 'tok',
        expected_revision: 11,
        payload_sha256: DIGEST_A,
        expires_at: '2026-01-01T00:00:00+00:00',
      },
    })
    const receipt = await createPendingMutation(SCOPE, {
      sheetKey: 's',
      expectedRevision: 11,
      projection: {},
    })
    expect(receipt.pendingMutationToken).toBe('tok')
  })

  it('载荷仍是 {code,message,data} 时 fail visible，不再解一层', async () => {
    mockPost.mockResolvedValue({
      data: { code: 0, message: 'ok', data: { pending_mutation_token: 'tok' } },
    })
    await expectAsyncRefusal(
      () =>
        createPendingMutation(SCOPE, {
          sheetKey: 's',
          expectedRevision: 11,
          projection: {},
        }),
      'envelope_not_unwrapped',
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// E. recovery client
// ═══════════════════════════════════════════════════════════════════════════

describe('recovery client 的显式 scope 与白名单 body', () => {
  it('list 必带 room_id + generation query', async () => {
    mockGet.mockResolvedValue({ data: { room_id: UUID(2), generation: 3, cases: [] } })
    await listRecoveryCases(SCOPE, { roomId: UUID(2), generation: 3 })
    const config = mockGet.mock.calls[0][1] as { params: Record<string, unknown> }
    expect(config.params.room_id).toBe(UUID(2))
    expect(config.params.generation).toBe(3)
  })

  it.each([
    ['缺 room_id', { roomId: '', generation: 3 }],
    ['generation 非整数', { roomId: UUID(2), generation: Number.NaN }],
  ])('%s ⇒ 发出前拒绝', async (_label, input) => {
    await expectAsyncRefusal(
      () => listRecoveryCases(SCOPE, input as { roomId: string; generation: number }),
      'recovery_list_scope_required',
    )
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('claim body 是白名单构造，不含任何 client 指定的 base', () => {
    const body = buildClaimRequestBody({
      caseId: UUID(50),
      roomId: UUID(2),
      participantId: UUID(3),
      priorConfirmationId: UUID(51),
      expectedGeneration: 3,
      expectedWriteFence: 9,
      expectedDefinitionBundleSha256: DIGEST_A,
      expectedCurrentRevision: 12,
    })
    expect(Object.keys(body).sort()).toEqual([...CLAIM_REQUEST_ALLOWED_KEYS].sort())
    for (const forbidden of [
      'client_confirmed_base_version_id',
      'base_version_id',
      'base_representation_id',
      'definition_bundle_slots',
      'contributor_snapshot_digest',
      'contributor_user_ids',
    ]) {
      expect(body, forbidden).not.toHaveProperty(forbidden)
    }
  })

  it('claim 的 case_id 走 route 段而不是 body', async () => {
    mockPost.mockResolvedValue({
      data: {
        case_id: UUID(50),
        forcesave_request_id: UUID(62),
        operation_id: UUID(60),
        application_id: UUID(61),
        state: 'application_created',
      },
    })
    await claimRecoveryCase(SCOPE, {
      caseId: UUID(50),
      roomId: UUID(2),
      participantId: UUID(3),
      priorConfirmationId: UUID(51),
      expectedGeneration: 3,
      expectedWriteFence: 9,
      expectedDefinitionBundleSha256: DIGEST_A,
      expectedCurrentRevision: 12,
    })
    const [url, body] = mockPost.mock.calls[0]
    expect(url).toContain(`/recovery-cases/${UUID(50)}/claim`)
    expect(body).not.toHaveProperty('case_id')
  })

  it('download-only 之后的下载必须带签发的 claim', async () => {
    await expectAsyncRefusal(
      () => downloadRecoveryArtifact(SCOPE, { caseId: UUID(50), claim: '' }),
      'download_claim_required',
    )
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('普通 retry 拒绝空 operation（claim 前三实体为空）', async () => {
    await expectAsyncRefusal(() => retryOperation(SCOPE, null), 'retry_requires_operation')
    await expectAsyncRefusal(() => retryOperation(SCOPE, '  '), 'retry_requires_operation')
    expect(mockPost).not.toHaveBeenCalled()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// F. rollback 只接受 opaque UUID
// ═══════════════════════════════════════════════════════════════════════════

describe('rollback 的 versionId 只能是 opaque immutable UUID', () => {
  it('UUID 时打到显式 entry scope 的 versions/{version_id}/rollback', async () => {
    await rollbackVersion(SCOPE, {
      versionId: UUID(80),
      expectedCurrentRevision: 12,
      confirmed: true,
    })
    const [url, body] = mockPost.mock.calls[0]
    expect(url).toBe(`${buildSyncEntryPrefix(SCOPE)}/versions/${UUID(80)}/rollback`)
    expect(body).toEqual({ expected_current_revision: 12, confirmed: true })
  })

  it.each([['numeric revision', '11'], ['revision 1', '1'], ['空串', ''], ['短 hex', 'abcd']])(
    '%s ⇒ 发出前拒绝拼 route',
    async (_label, versionId) => {
      await expectAsyncRefusal(
        () => rollbackVersion(SCOPE, { versionId, expectedCurrentRevision: 12, confirmed: true }),
        'version_id_not_opaque',
      )
      expect(mockPost).not.toHaveBeenCalled()
    },
  )

  it('未二次确认时拒绝', async () => {
    await expectAsyncRefusal(
      () =>
        rollbackVersion(SCOPE, {
          versionId: UUID(80),
          expectedCurrentRevision: 12,
          confirmed: false,
        }),
      'rollback_confirmation_required',
    )
    expect(mockPost).not.toHaveBeenCalled()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// G. descriptor 是唯一 config 来源
// ═══════════════════════════════════════════════════════════════════════════

describe('descriptor 是唯一 config 来源', () => {
  it('materialize 返回的 descriptor 直接可解析，无需第二次 config 请求', async () => {
    mockPost.mockResolvedValue({ data: descriptorPayload() })
    const descriptor = await materialize(SCOPE, {
      sheetKey: 's',
      expectedRevision: 11,
      pendingMutationToken: 'tok',
      projection: {},
    })
    expect(descriptor.onlyofficeConfig).toEqual({ document: { key: 'doc-key-1' } })
    expect(mockGet).not.toHaveBeenCalled()
    expect(mockPost).toHaveBeenCalledTimes(1)
  })

  it('confirm-descriptor 的 body 由 descriptor 自身构造，room 走 route 段', async () => {
    mockPost.mockResolvedValueOnce({ data: descriptorPayload() })
    const descriptor = await materialize(SCOPE, {
      sheetKey: 's',
      expectedRevision: 11,
      pendingMutationToken: 'tok',
      projection: {},
    })
    mockPost.mockResolvedValueOnce({
      data: {
        confirmation_id: UUID(8),
        room_id: UUID(2),
        participant_id: UUID(3),
        generation: 3,
        representation_id: UUID(5),
        content_version_id: UUID(4),
        room_state: 'active',
        replayed: false,
        forcesave_unlocked: true,
      },
    })
    const confirmation = await confirmDescriptor(SCOPE, {
      descriptor,
      confirmPayload: buildDescriptorConfirmPayload(descriptor),
    })
    const [url, body] = mockPost.mock.calls[1]
    expect(url).toBe(`${buildSyncEntryPrefix(SCOPE)}/rooms/${UUID(2)}/confirm-descriptor`)
    expect(body.doc_key).toBe('doc-key-1')
    expect(body.definition_bundle_sha256).toBe(DIGEST_A)
    expect(confirmation.forcesaveUnlocked).toBe(true)
  })

  it('flush 未成功（无 pending token）时不得 materialize', async () => {
    await expectAsyncRefusal(
      () =>
        materialize(SCOPE, {
          sheetKey: 's',
          expectedRevision: 11,
          pendingMutationToken: '  ',
          projection: {},
        }),
      'pending_mutation_token_required',
    )
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('forcesave 不接受 kind —— close_capture 只能由 room arbiter 提升', async () => {
    await requestForcesave(SCOPE, { roomId: UUID(2), participantId: UUID(3) }).catch(() => null)
    const body = mockPost.mock.calls[0][1] as Record<string, unknown>
    expect(body).not.toHaveProperty('kind')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// H. 反向自检：不得存在第二份 config 面或 callback 面
// ═══════════════════════════════════════════════════════════════════════════

describe('反向自检', () => {
  it('未登记 endpoint 名拒绝拼 URL', () => {
    expectRefusal(
      () => buildSyncEndpointUrl('fetch_onlyoffice_config', SCOPE),
      'endpoint_not_in_contract',
    )
  })

  it('生成的路由表里没有任何 callback / config 端点', () => {
    for (const route of WP_SYNC_ROUTES) {
      expect(route.suffix, route.endpoint).not.toContain('onlyoffice-callback')
      expect(route.suffix, route.endpoint).not.toContain('/config')
    }
  })

  it('占位符缺失或多余时拒绝', () => {
    expectRefusal(() => buildSyncEndpointUrl('get_operation', SCOPE), 'route_param_missing')
    expectRefusal(
      () => buildSyncEndpointUrl('materialize', SCOPE, { room_id: UUID(2) }),
      'route_param_unexpected',
    )
  })
})
