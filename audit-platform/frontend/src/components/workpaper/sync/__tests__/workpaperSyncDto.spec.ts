// spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 31
//
// 前端 DTO 的行为侧判据。**每条都断言 refusal 的 `code`** 而不是「抛了就算过」：
// 两个分支共用一个 code 时先到的那条会把后到的遮成永远不可达（本 spec 的变异运行
// 已三次抓到这个形态），只断言「抛异常」分辨不出来。
//
// Validates: Requirements 3.7, 5.8, 11.2, 11.4, 11.11（Property 10 / 11 / 47 的前端侧）
import { describe, expect, it } from 'vitest'

import {
  WP_SYNC_DESCRIPTOR_CONFIRM_KEYS,
  WP_SYNC_DESCRIPTOR_FIELDS,
  WP_SYNC_OPERATION_STATES,
  WP_SYNC_OPERATION_TERMINAL_STATES,
  WP_SYNC_RECOVERY_CASE_STATES,
} from '../workpaperSyncContract.generated'
import {
  WorkpaperSyncContractError,
  assertUnwrappedOnce,
  buildDescriptorConfirmPayload,
  classifyOperationShape,
  classifySyncFailure,
  isOpaqueUuid,
  isSyncDigest,
  parseDescriptorConfirmation,
  parseEditorLaunchDescriptor,
  parseForcesaveAccepted,
  parseOperationSnapshot,
  parsePendingMutation,
  parseRecoveryCase,
  parseRecoveryClaim,
  parseRecoveryDownloadOnly,
  participantIdentityOfDescriptor,
  roomIdentityOfDescriptor,
} from '../workpaperSyncDto'

const DIGEST_A = 'a'.repeat(64)
const DIGEST_B = 'b'.repeat(64)
const UUID = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`

/** 断言：调用抛 `WorkpaperSyncContractError` 且 code 逐字相等。 */
function expectRefusal(run: () => unknown, code: string): void {
  let caught: unknown = null
  try {
    run()
  } catch (error) {
    caught = error
  }
  expect(caught, `期望抛 code=${code}，实际没抛`).toBeInstanceOf(WorkpaperSyncContractError)
  expect((caught as WorkpaperSyncContractError).code).toBe(code)
}

// ═══════════════════════════════════════════════════════════════════════════
// A. envelope 只解一次
// ═══════════════════════════════════════════════════════════════════════════

describe('envelope 解包边界', () => {
  it('已解包的载荷原样通过', () => {
    const payload = { case_id: UUID(1), state: 'unclaimed' }
    expect(assertUnwrappedOnce(payload, 'x')).toBe(payload)
  })

  it('仍是 {code,message,data} 的载荷 fail visible，而不是再解一层', () => {
    expectRefusal(
      () => assertUnwrappedOnce({ code: 0, message: 'ok', data: { case_id: UUID(1) } }, 'x'),
      'envelope_not_unwrapped',
    )
  })

  it('只带 code 或只带 data 的业务载荷不误判为 envelope', () => {
    expect(assertUnwrappedOnce({ code: 'per_entry_contract_required' }, 'x')).toBeTruthy()
    expect(assertUnwrappedOnce({ data: [1, 2] }, 'x')).toBeTruthy()
  })

  it('非对象载荷 fail visible', () => {
    expectRefusal(() => assertUnwrappedOnce(null, 'x'), 'wire_payload_not_object')
    expectRefusal(() => assertUnwrappedOnce([1], 'x'), 'wire_payload_not_object')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// B. digest / opaque id 判定
// ═══════════════════════════════════════════════════════════════════════════

describe('digest 与 opaque id 判定（与后端 is_digest 逐条对齐）', () => {
  it.each([
    ['64 位小写 hex', DIGEST_A, true],
    ['全零', '0'.repeat(64), false],
    ['大写 hex', 'A'.repeat(64), false],
    ['长度不足', 'a'.repeat(63), false],
    ['空串', '', false],
    ['非字符串', 12345, false],
  ])('isSyncDigest(%s)', (_label, value, expected) => {
    expect(isSyncDigest(value)).toBe(expected)
  })

  it.each([
    ['UUID', UUID(7), true],
    ['全零 UUID（事务前占位值）', UUID(0), false],
    ['numeric revision', '11', false],
    ['空串', '', false],
    ['短 hex', 'abcd', false],
  ])('isOpaqueUuid(%s)', (_label, value, expected) => {
    expect(isOpaqueUuid(value)).toBe(expected)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// C. pending mutation
// ═══════════════════════════════════════════════════════════════════════════

function pendingWire(over: Record<string, unknown> = {}) {
  return {
    pending_mutation_token: 'opaque-signed-token',
    expected_revision: 11,
    payload_sha256: DIGEST_A,
    expires_at: '2026-01-01T00:00:00+00:00',
    ...over,
  }
}

describe('pending mutation 回执', () => {
  it('四项齐备时解析成功，并逐项回传本次 Idempotency-Key', () => {
    const receipt = parsePendingMutation(pendingWire(), 'key-1')
    expect(receipt.pendingMutationToken).toBe('opaque-signed-token')
    expect(receipt.expectedRevision).toBe(11)
    expect(receipt.payloadSha256).toBe(DIGEST_A)
    expect(receipt.idempotencyKey).toBe('key-1')
  })

  it('payload digest 非法时 fail visible', () => {
    expectRefusal(
      () => parsePendingMutation(pendingWire({ payload_sha256: '0'.repeat(64) }), 'k'),
      'payload_digest_invalid',
    )
  })

  it('缺 token 时 fail visible', () => {
    expectRefusal(
      () => parsePendingMutation(pendingWire({ pending_mutation_token: '' }), 'k'),
      'wire_field_missing',
    )
  })

  it('回执刻意不含 revision 推进结果 —— flush 按定义不产生业务版本', () => {
    const receipt = parsePendingMutation(pendingWire(), 'k')
    expect(receipt).not.toHaveProperty('revision')
    expect(receipt).not.toHaveProperty('contentVersionId')
    expect(receipt).not.toHaveProperty('representationId')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// D. EditorLaunchDescriptor（Property 11 前半）
// ═══════════════════════════════════════════════════════════════════════════

function descriptorWire(over: Record<string, unknown> = {}) {
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
    ...over,
  }
}

describe('EditorLaunchDescriptor 解析', () => {
  it('字段齐备时解析成功并保留 onlyofficeConfig 原样', () => {
    const descriptor = parseEditorLaunchDescriptor(descriptorWire())
    expect(descriptor.roomId).toBe(UUID(2))
    expect(descriptor.representationGeneration).toBe(4)
    expect(descriptor.authorityModel).toBe('projection_contract')
    expect(descriptor.definitionBundleSlots.contract.sha256).toBe(DIGEST_B)
    expect(descriptor.onlyofficeConfig).toEqual({ document: { key: 'doc-key-1' } })
  })

  it('descriptor 刻意不含签名 document url —— URL 只能来自服务端下发的 config', () => {
    const descriptor = parseEditorLaunchDescriptor(descriptorWire())
    expect(descriptor).not.toHaveProperty('documentUrl')
    expect(descriptor).not.toHaveProperty('configUrl')
  })

  it.each(WP_SYNC_DESCRIPTOR_FIELDS.map((field) => [field]))(
    '缺字段 %s 时拒绝挂载',
    (field) => {
      const wire = descriptorWire() as Record<string, unknown>
      delete wire[field]
      expectRefusal(() => parseEditorLaunchDescriptor(wire), 'descriptor_field_missing')
    },
  )

  it('全零 UUID 是「尚未取得」的占位值，必须拒绝', () => {
    expectRefusal(
      () => parseEditorLaunchDescriptor(descriptorWire({ room_id: UUID(0) })),
      'descriptor_uuid_invalid',
    )
  })

  it('artifact digest 全零时拒绝', () => {
    expectRefusal(
      () => parseEditorLaunchDescriptor(descriptorWire({ artifact_sha256: '0'.repeat(64) })),
      'descriptor_digest_invalid',
    )
  })

  it.each([['generation'], ['representation_generation'], ['server_applied_revision'], ['write_fence_epoch']])(
    '%s 为 0 时拒绝（必须 >= 1）',
    (field) => {
      expectRefusal(
        () => parseEditorLaunchDescriptor(descriptorWire({ [field]: 0 })),
        'descriptor_generation_invalid',
      )
    },
  )

  it.each([['template'], ['instrumentation'], ['contract']])(
    '缺 typed slot %s 时拒绝（三个必须全在）',
    (slot) => {
      const slots = { ...(descriptorWire().definition_bundle_slots as Record<string, unknown>) }
      delete slots[slot]
      expectRefusal(
        () => parseEditorLaunchDescriptor(descriptorWire({ definition_bundle_slots: slots })),
        'descriptor_slot_missing',
      )
    },
  )

  it('slot 的 type 为空串时拒绝（不得以空串代替 typed null marker）', () => {
    const slots = {
      template: { type: '', sha256: DIGEST_B },
      instrumentation: { type: 'definition', sha256: DIGEST_B },
      contract: { type: 'definition', sha256: DIGEST_B },
    }
    expectRefusal(
      () => parseEditorLaunchDescriptor(descriptorWire({ definition_bundle_slots: slots })),
      'descriptor_slot_type_missing',
    )
  })

  it('空 onlyoffice_config 时拒绝 —— 空 config 会逼组件自行再请求一次', () => {
    expectRefusal(
      () => parseEditorLaunchDescriptor(descriptorWire({ onlyoffice_config: {} })),
      'descriptor_config_empty',
    )
  })

  it('未知 authority model fail visible', () => {
    expectRefusal(
      () => parseEditorLaunchDescriptor(descriptorWire({ authority_model: 'guess' })),
      'unknown_authority_model',
    )
  })

  it('room 身份不伪造 state；participant 投影只有 id', () => {
    const descriptor = parseEditorLaunchDescriptor(descriptorWire())
    expect(roomIdentityOfDescriptor(descriptor).state).toBeNull()
    expect(Object.keys(participantIdentityOfDescriptor(descriptor))).toEqual(['participantId'])
  })
})

describe('confirm-descriptor 回传体', () => {
  it('键集逐项等于服务端 confirm_payload() 的清单', () => {
    const descriptor = parseEditorLaunchDescriptor(descriptorWire())
    const payload = buildDescriptorConfirmPayload(descriptor)
    expect(Object.keys(payload).sort()).toEqual([...WP_SYNC_DESCRIPTOR_CONFIRM_KEYS].sort())
  })

  it('content_revision 回传的是 server_applied_revision，不是 client 基线', () => {
    const descriptor = parseEditorLaunchDescriptor(
      descriptorWire({ server_applied_revision: 12, client_confirmed_base_revision: 7 }),
    )
    expect(buildDescriptorConfirmPayload(descriptor).content_revision).toBe(12)
  })

  it('confirmation 的 room_state 走封闭域', () => {
    const wire = {
      confirmation_id: UUID(8),
      room_id: UUID(2),
      participant_id: UUID(3),
      generation: 3,
      representation_id: UUID(5),
      content_version_id: UUID(4),
      room_state: 'active',
      replayed: false,
      forcesave_unlocked: true,
    }
    expect(parseDescriptorConfirmation(wire).roomState).toBe('active')
    expectRefusal(
      () => parseDescriptorConfirmation({ ...wire, room_state: 'ready' }),
      'unknown_room_state',
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// E. forcesave 202
// ═══════════════════════════════════════════════════════════════════════════

describe('forcesave 202 不是完成凭证', () => {
  const wire = {
    forcesave_request_id: UUID(11),
    operation_id: UUID(12),
    request_sequence: 7,
    state: 'accepted',
    poll_after_ms: 500,
    replayed: false,
    dispatch_error: null,
  }

  it('accepted 时解析成功，dispatchError 为 null 才代表命令已受理', () => {
    const accepted = parseForcesaveAccepted(wire)
    expect(accepted.state).toBe('accepted')
    expect(accepted.dispatchError).toBeNull()
  })

  it('出站失败时保留 error_code，不得被读成已受理', () => {
    expect(parseForcesaveAccepted({ ...wire, dispatch_error: 'command_service_unreachable' }).dispatchError)
      .toBe('command_service_unreachable')
  })

  it('state 不是 accepted 时 fail visible', () => {
    expectRefusal(
      () => parseForcesaveAccepted({ ...wire, state: 'applied' }),
      'forcesave_state_unexpected',
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// F. operation 三态（Property 18 的前端投影）
// ═══════════════════════════════════════════════════════════════════════════

describe('operation shape 三态互斥且穷尽', () => {
  it('normal accepted 的两个 link 均为空', () => {
    expect(
      classifyOperationShape({
        applicationId: null,
        duplicateOfOperationId: null,
        state: 'accepted',
      }),
    ).toBe('pre_correlation')
  })

  it('correlation 后绑定 application ⇒ primary', () => {
    expect(
      classifyOperationShape({
        applicationId: UUID(20),
        duplicateOfOperationId: null,
        state: 'application_bound',
      }),
    ).toBe('primary')
  })

  it('terminal duplicate 直指 primary 且自身不绑定 application', () => {
    expect(
      classifyOperationShape({
        applicationId: null,
        duplicateOfOperationId: UUID(21),
        state: 'duplicate',
      }),
    ).toBe('duplicate')
  })

  it('同时带 application 与 duplicate 指针 ⇒ 拒绝', () => {
    expectRefusal(
      () =>
        classifyOperationShape({
          applicationId: UUID(20),
          duplicateOfOperationId: UUID(21),
          state: 'duplicate',
        }),
      'operation_shape_ambiguous',
    )
  })

  it('有 duplicate 指针但 state 不是 duplicate ⇒ 拒绝', () => {
    expectRefusal(
      () =>
        classifyOperationShape({
          applicationId: null,
          duplicateOfOperationId: UUID(21),
          state: 'applied',
        }),
      'duplicate_state_mismatch',
    )
  })

  it("state='duplicate' 但缺指针 ⇒ stranded shell，拒绝", () => {
    expectRefusal(
      () =>
        classifyOperationShape({
          applicationId: null,
          duplicateOfOperationId: null,
          state: 'duplicate',
        }),
      'stranded_duplicate_shell',
    )
  })
})

function operationWire(over: Record<string, unknown> = {}) {
  return {
    requested_operation_id: UUID(30),
    canonical_operation_id: UUID(30),
    followed_duplicate: false,
    state: 'accepted',
    application_id: null,
    duplicate_of_operation_id: null,
    error_code: null,
    error_stage: null,
    accepted_at: '2026-01-01T00:00:00+00:00',
    application_bound_at: null,
    operation_finished_at: null,
    result_revision: null,
    conflict_count: null,
    logical_result_code: null,
    definition_bundle_id: null,
    definition_bundle_sha256: null,
    authority_model_definition_sha256: null,
    durable_at: null,
    finished_at: null,
    ...over,
  }
}

describe('operation 快照解析', () => {
  it('pre-correlation shell 的 application 相关五项保持 null（不得投影成 0）', () => {
    const snapshot = parseOperationSnapshot(operationWire())
    expect(snapshot.shape).toBe('pre_correlation')
    expect(snapshot.applicationId).toBeNull()
    expect(snapshot.duplicateOfOperationId).toBeNull()
    expect(snapshot.resultRevision).toBeNull()
    expect(snapshot.conflictCount).toBeNull()
    expect(snapshot.terminal).toBe(false)
  })

  it('duplicate 的 requested/canonical 都保留，且指针直指 canonical primary', () => {
    const snapshot = parseOperationSnapshot(
      operationWire({
        requested_operation_id: UUID(31),
        canonical_operation_id: UUID(30),
        followed_duplicate: true,
        state: 'duplicate',
        duplicate_of_operation_id: UUID(30),
      }),
    )
    expect(snapshot.shape).toBe('duplicate')
    expect(snapshot.requestedOperationId).toBe(UUID(31))
    expect(snapshot.canonicalOperationId).toBe(UUID(30))
    expect(snapshot.terminal).toBe(true)
  })

  it('duplicate 指针不指向 canonical primary ⇒ 拒绝（禁链/环）', () => {
    expectRefusal(
      () =>
        parseOperationSnapshot(
          operationWire({
            requested_operation_id: UUID(31),
            canonical_operation_id: UUID(30),
            state: 'duplicate',
            duplicate_of_operation_id: UUID(32),
          }),
        ),
      'duplicate_not_direct_primary',
    )
  })

  it('非 duplicate 却把 requested canonicalize 成别的 id ⇒ 拒绝', () => {
    expectRefusal(
      () =>
        parseOperationSnapshot(
          operationWire({
            requested_operation_id: UUID(31),
            canonical_operation_id: UUID(30),
            state: 'applied',
            application_id: UUID(40),
          }),
        ),
      'non_duplicate_canonicalized',
    )
  })

  it('未知 operation state fail visible，不得兜底成 error', () => {
    expectRefusal(
      () => parseOperationSnapshot(operationWire({ state: 'almost_done' })),
      'unknown_operation_state',
    )
  })

  it('terminal 判定逐项来自生成的 terminal 集', () => {
    for (const state of WP_SYNC_OPERATION_STATES) {
      const isTerminal = (WP_SYNC_OPERATION_TERMINAL_STATES as readonly string[]).includes(state)
      // duplicate 需要配套指针，单独在上面覆盖。
      if (state === 'duplicate') continue
      const wire = operationWire({
        state,
        application_id: state === 'applied' || state === 'conflict' ? UUID(40) : null,
      })
      expect(parseOperationSnapshot(wire).terminal, state).toBe(isTerminal)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// G. recovery（AC 5.8 的三实体）
// ═══════════════════════════════════════════════════════════════════════════

function recoveryWire(over: Record<string, unknown> = {}) {
  return {
    case_id: UUID(50),
    reason: 'crash_close',
    state: 'unclaimed',
    operation_id: null,
    application_id: null,
    forcesave_request_id: null,
    candidate_prior_confirmations: [
      {
        confirmation_id: UUID(51),
        participant_id: UUID(3),
        content_version_id: UUID(4),
        confirmed_at: '2026-01-01T00:00:00+00:00',
      },
    ],
    actions: { claim: true, download_only: true },
    ...over,
  }
}

describe('recovery case 的三实体不变量', () => {
  it('claim 前三实体全空', () => {
    const parsed = parseRecoveryCase(recoveryWire())
    expect(parsed.operationId).toBeNull()
    expect(parsed.applicationId).toBeNull()
    expect(parsed.forcesaveRequestId).toBeNull()
    expect(parsed.candidatePriorConfirmations).toHaveLength(1)
  })

  it.each([
    ['operation_id', { operation_id: UUID(60) }],
    ['application_id', { application_id: UUID(61) }],
    ['forcesave_request_id', { forcesave_request_id: UUID(62) }],
  ])('unclaimed 却带 %s ⇒ 拒绝（伪造三实体会让 UI 显示普通重试）', (_label, over) => {
    expectRefusal(
      () => parseRecoveryCase(recoveryWire(over)),
      'recovery_case_premature_entities',
    )
  })

  it.each([['claiming'], ['download_only'], ['quarantined'], ['expired']])(
    'state=%s 时三实体同样必须全空',
    (state) => {
      expect(parseRecoveryCase(recoveryWire({ state })).operationId).toBeNull()
      expectRefusal(
        () => parseRecoveryCase(recoveryWire({ state, operation_id: UUID(60) })),
        'recovery_case_premature_entities',
      )
    },
  )

  it('application_created 时三实体必须同时具备', () => {
    const full = recoveryWire({
      state: 'application_created',
      operation_id: UUID(60),
      application_id: UUID(61),
      forcesave_request_id: UUID(62),
    })
    expect(parseRecoveryCase(full).applicationId).toBe(UUID(61))
    expectRefusal(
      () => parseRecoveryCase({ ...full, application_id: null }),
      'recovery_case_incomplete_entities',
    )
  })

  it('生成的 case 状态域每一个都有显式三实体裁决（新增状态不得默认放行）', () => {
    for (const state of WP_SYNC_RECOVERY_CASE_STATES) {
      const withEntities = state === 'application_created'
      const wire = recoveryWire({
        state,
        operation_id: withEntities ? UUID(60) : null,
        application_id: withEntities ? UUID(61) : null,
        forcesave_request_id: withEntities ? UUID(62) : null,
      })
      expect(() => parseRecoveryCase(wire), state).not.toThrow()
    }
  })

  it('未知 reason / state fail visible', () => {
    expectRefusal(() => parseRecoveryCase(recoveryWire({ reason: 'oops' })), 'unknown_recovery_reason')
    expectRefusal(
      () => parseRecoveryCase(recoveryWire({ state: 'claimed' })),
      'unknown_recovery_case_state',
    )
  })
})

describe('claim / download-only 的响应分型', () => {
  const claimWire = {
    case_id: UUID(50),
    forcesave_request_id: UUID(62),
    operation_id: UUID(60),
    application_id: UUID(61),
    state: 'application_created',
  }

  it('claim 成功是唯一可同时带 request/application/operation 的响应', () => {
    const claim = parseRecoveryClaim(claimWire)
    expect(claim.forcesaveRequestId).toBe(UUID(62))
    expect(claim.operationId).toBe(UUID(60))
    expect(claim.applicationId).toBe(UUID(61))
  })

  it('claim 响应缺 application_id ⇒ 拒绝（shell 停在 pre-correlation）', () => {
    expectRefusal(
      () => parseRecoveryClaim({ ...claimWire, application_id: null }),
      'recovery_claim_without_application',
    )
  })

  it.each([['operation_id'], ['forcesave_request_id']])(
    'claim 响应缺 %s ⇒ 拒绝',
    (field) => {
      expectRefusal(
        () => parseRecoveryClaim({ ...claimWire, [field]: null }),
        'wire_field_missing',
      )
    },
  )

  it('download-only 回执三实体全空且不含任何 applied 迹象', () => {
    const receipt = parseRecoveryDownloadOnly({
      case_id: UUID(50),
      state: 'download_only',
      download_claim: 'signed-claim',
      expires_in_seconds: 600,
    })
    expect(receipt.state).toBe('download_only')
    expect(receipt).not.toHaveProperty('operationId')
    expect(receipt).not.toHaveProperty('applicationId')
    expect(receipt).not.toHaveProperty('resultRevision')
  })

  it.each([
    ['operation_id', UUID(60)],
    ['application_id', UUID(61)],
    ['forcesave_request_id', UUID(62)],
    ['result_revision', 13],
    ['applied', true],
  ])('download-only 响应带 %s ⇒ 拒绝（伪造 applied）', (field, value) => {
    expectRefusal(
      () =>
        parseRecoveryDownloadOnly({
          case_id: UUID(50),
          state: 'download_only',
          download_claim: 'signed-claim',
          expires_in_seconds: 600,
          [field]: value,
        }),
      'download_only_fabricated_entities',
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// H. 失败分型：stale identity 的 409 不得转成 editing / retry / forcesave
// ═══════════════════════════════════════════════════════════════════════════

describe('stale descriptor / recovery identity 的 409 分型', () => {
  it.each([['launch_descriptor_stale_identity'], ['launch_descriptor_substrate_stale']])(
    '%s 三个门全部关闭',
    (errorCode) => {
      const verdict = classifySyncFailure({ httpStatus: 409, errorCode })
      expect(verdict.httpStatus).toBe(409)
      expect(verdict.canEnterEditing).toBe(false)
      expect(verdict.retryableOperation).toBe(false)
      expect(verdict.canForcesave).toBe(false)
      expect(verdict.unregistered).toBe(false)
    },
  )

  it('缺 httpStatus 时从生成的拒绝表补齐，仍是 409 且三门全关', () => {
    const verdict = classifySyncFailure({ errorCode: 'launch_descriptor_stale_identity' })
    expect(verdict.httpStatus).toBe(409)
    expect(verdict.retryableOperation).toBe(false)
  })

  it('500 类内部失败才可重试，但仍不得直接进入 editing / forcesave', () => {
    const verdict = classifySyncFailure({ errorCode: 'materialize_not_single_commit' })
    expect(verdict.httpStatus).toBe(500)
    expect(verdict.retryableOperation).toBe(true)
    expect(verdict.canEnterEditing).toBe(false)
    expect(verdict.canForcesave).toBe(false)
  })

  it('未登记 error_code 显式标 unregistered，不静默当普通失败', () => {
    const verdict = classifySyncFailure({ httpStatus: 409, errorCode: 'brand_new_code' })
    expect(verdict.unregistered).toBe(true)
    expect(verdict.retryableOperation).toBe(false)
  })

  it('缺 error_code 时 fail visible', () => {
    expectRefusal(() => classifySyncFailure({ httpStatus: 409 }), 'failure_error_code_missing')
  })
})
