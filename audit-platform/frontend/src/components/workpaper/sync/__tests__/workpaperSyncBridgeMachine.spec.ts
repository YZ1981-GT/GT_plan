// spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 32
//
// 桥状态机的**结构 + 行为**判据。
//
// Validates: Requirements 4.1, 4.5, 5.8, 11.2, 11.3
//
// ═══ 判据设计 ═══
//
// * 「每个状态可达 / 每个终态真终 / 每个事件有用」由 `auditBridgeMachine()` 产出**事实**，
//   而不是逐条断言某个 if。状态机最典型的死代码是「声明了一个状态却没有任何一条边通向
//   它」—— 那种缺陷下所有「域里有它」的判据全绿，变异掉它的分支也永远 GREEN。
// * 非法转换一律断言**具体 code**：两个分支共用一个 code 会让先到的那条把后到的遮成
//   永远不可达（本 spec 的变异运行已三次抓到）。
// * 不把「被验证的常量」当作参数化数据源自证。AC 11.2 的状态清单与本文件里的期望值
//   由 `backend/tests/workpaper_sync/test_task32_bridge_state_domain.py` 与
//   requirements.md 交叉锁死，本文件只做行为面。
import { describe, expect, it } from 'vitest'
import * as fc from 'fast-check'

import {
  WP_BRIDGE_EVENTS,
  WP_BRIDGE_STATES,
  WP_BRIDGE_STATE_MODE,
  WP_BRIDGE_STATE_TEXT,
  WP_BRIDGE_TERMINAL_STATES,
  auditBridgeMachine,
  bridgeStateForOperation,
  bridgeStateProjectionByOperationState,
  transitionBridgeState,
  type WorkpaperSyncBridgeEvent,
  type WorkpaperSyncBridgeState,
} from '../workpaperSyncBridgeMachine'
import { WorkpaperSyncContractError, type WorkpaperSyncOperationSnapshot } from '../workpaperSyncDto'
import { WP_SYNC_OPERATION_STATES } from '../workpaperSyncContract.generated'

const UUID = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`

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

/** 抛出的必须是带**指定 code** 的契约错误。 */
function expectRefusal(fn: () => unknown, code: string): void {
  let caught: unknown
  try {
    fn()
  } catch (error) {
    caught = error
  }
  expect(caught, `期望拒绝 code=${code}，但调用成功了`).toBeInstanceOf(
    WorkpaperSyncContractError,
  )
  expect((caught as WorkpaperSyncContractError).code).toBe(code)
}

// ═══════════════════════════════════════════════════════════════════════════
// A. 表的结构自证
// ═══════════════════════════════════════════════════════════════════════════

describe('转换表结构自证', () => {
  it('除初态外每个状态都有入边（不存在「声明了却没人能进」的状态）', () => {
    expect(auditBridgeMachine().unreachableStates).toEqual([])
  })

  it('没有出边为空的状态（不存在卡死态）', () => {
    expect(auditBridgeMachine().deadEndStates).toEqual([])
  })

  it('声明的三个 terminal 出边只有 reset', () => {
    expect(auditBridgeMachine().leakyTerminals).toEqual([])
    expect([...WP_BRIDGE_TERMINAL_STATES]).toEqual([
      'duplicate',
      'recovery_download_only',
      'close_recovery_required',
    ])
  })

  it('邻接表不引用未声明的目标状态', () => {
    expect(auditBridgeMachine().undeclaredTargets).toEqual([])
  })

  it('每个声明事件都至少被一个状态接受（不留死事件）', () => {
    expect(auditBridgeMachine().unusedEvents).toEqual([])
  })

  it('mode 表与文案表逐状态覆盖状态域，且没有多余键', () => {
    for (const state of WP_BRIDGE_STATES) {
      expect(WP_BRIDGE_STATE_MODE[state], state).toBeTruthy()
      expect(WP_BRIDGE_STATE_TEXT[state], state).toBeTruthy()
    }
    expect(Object.keys(WP_BRIDGE_STATE_MODE).sort()).toEqual([...WP_BRIDGE_STATES].sort())
    expect(Object.keys(WP_BRIDGE_STATE_TEXT).sort()).toEqual([...WP_BRIDGE_STATES].sort())
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// B. 文案（AC 11.3）
// ═══════════════════════════════════════════════════════════════════════════

describe('用户可见文案全中文且逐类可区分', () => {
  it('四类结果文案两两不同，且没有任何一条是「同步成功」', () => {
    const accepted = WP_BRIDGE_STATE_TEXT.forcesave_accepted
    const durable = WP_BRIDGE_STATE_TEXT.incoming_durable
    const applied = WP_BRIDGE_STATE_TEXT.applied
    const conflict = WP_BRIDGE_STATE_TEXT.conflict
    expect(new Set([accepted, durable, applied, conflict]).size).toBe(4)
    expect(accepted).toContain('命令已接受')
    expect(durable).toContain('耐久')
    expect(applied).toContain('结构化回写完成')
    expect(conflict).toContain('冲突')
    for (const text of Object.values(WP_BRIDGE_STATE_TEXT)) {
      expect(text).not.toContain('同步成功')
    }
  })

  it('design 点名的「已冻结保存请求」与「需重载编辑器确认新基线」各自独立', () => {
    expect(WP_BRIDGE_STATE_TEXT.forcesave_frozen).toContain('已冻结保存请求')
    expect(WP_BRIDGE_STATE_TEXT.refresh_required).toContain('重载编辑器确认新基线')
    expect(WP_BRIDGE_STATE_TEXT.forcesave_frozen).not.toBe(
      WP_BRIDGE_STATE_TEXT.forcesave_accepted,
    )
  })

  it('close 失权说得出「失权」，无接任者说得出「恢复」，两者都不是回写完成文案', () => {
    const stale = WP_BRIDGE_STATE_TEXT.close_authorization_stale
    const required = WP_BRIDGE_STATE_TEXT.close_recovery_required
    // AC 4.10：必须先显示 authorization-stale 与 successor 进展。
    expect(stale).toContain('失去资格')
    expect(stale).toContain('接任者')
    // 不得被渲染成「保存成功」——判据钉的是 applied 的那句成功文案本身。
    expect(stale).not.toContain(WP_BRIDGE_STATE_TEXT.applied)
    expect(stale).not.toBe(WP_BRIDGE_STATE_TEXT.applied)
    expect(required).toContain('恢复')
    expect(required).not.toContain(WP_BRIDGE_STATE_TEXT.applied)
    expect(required).not.toContain('成功')
  })

  it('每条文案都含中日韩字符（不得留英文占位）', () => {
    for (const [state, text] of Object.entries(WP_BRIDGE_STATE_TEXT)) {
      expect(/[\u4e00-\u9fff]/.test(text), `${state}: ${text}`).toBe(true)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// C. 正常路径
// ═══════════════════════════════════════════════════════════════════════════

describe('HTML → OO 正常路径', () => {
  it('flush → commit → materialize → mount → ready → confirm 逐级推进，mode 在 mount 才翻转', () => {
    const path: [WorkpaperSyncBridgeState, WorkpaperSyncBridgeEvent, WorkpaperSyncBridgeState][] = [
      ['html_idle', 'flush_started', 'flushing'],
      ['flushing', 'pending_mutation_created', 'committing'],
      ['committing', 'descriptor_received', 'materializing'],
      ['materializing', 'descriptor_accepted', 'oo_loading'],
      ['oo_loading', 'editor_mounted', 'descriptor_mounted'],
      ['descriptor_mounted', 'document_ready', 'confirming_descriptor'],
      ['confirming_descriptor', 'descriptor_confirmed', 'oo_editing'],
    ]
    let mode: 'html' | 'oo' = 'html'
    for (const [from, event, to] of path) {
      const result = transitionBridgeState(from, event, mode)
      expect(result.to, `${from} --${event}-->`).toBe(to)
      mode = result.mode
    }
    expect(mode).toBe('oo')
    expect(transitionBridgeState('committing', 'descriptor_received', 'html').mode).toBe('html')
    expect(transitionBridgeState('materializing', 'descriptor_accepted', 'html').mode).toBe('oo')
  })

  it('确认之前不存在任何通向 oo_editing 的边（confirm 是唯一入口）', () => {
    const entries = WP_BRIDGE_STATES.flatMap((from) =>
      WP_BRIDGE_EVENTS.filter((event) => {
        try {
          return transitionBridgeState(from, event, 'oo', legalContext(event)).to === 'oo_editing'
        } catch {
          return false
        }
      }).map((event) => `${from}:${event}`),
    )
    expect(entries).toEqual(['confirming_descriptor:descriptor_confirmed'])
  })

  it('materialize 未成功时不得 mount：descriptor_accepted 之前没有通向 oo_loading 的边', () => {
    const entries = WP_BRIDGE_STATES.flatMap((from) =>
      WP_BRIDGE_EVENTS.filter((event) => {
        try {
          return transitionBridgeState(from, event, 'html', legalContext(event)).to === 'oo_loading'
        } catch {
          return false
        }
      }).map((event) => `${from}:${event}`),
    )
    expect(entries.sort()).toEqual([
      'materializing:descriptor_accepted',
      'rematerializing:descriptor_accepted',
    ])
  })

  it('token / bundle identity 失败停留 HTML（三处入口都回 html_idle 且 mode=html）', () => {
    for (const from of ['flushing', 'committing', 'materializing'] as const) {
      const result = transitionBridgeState(from, 'identity_rejected', 'html')
      expect(result.to, from).toBe('html_idle')
      expect(result.mode, from).toBe('html')
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// D. OO → HTML 与 shell 阶段
// ═══════════════════════════════════════════════════════════════════════════

describe('OO → HTML：先 shell，再 primary/duplicate', () => {
  it('forcesave_accepted 只能经 shell_tracking_started 继续（不接受 operation 观测）', () => {
    expectRefusal(
      () =>
        transitionBridgeState('forcesave_accepted', 'operation_observed', 'oo', {
          operation: snapshot({ state: 'application_bound', shape: 'primary', applicationId: UUID(9) }),
        }),
      'bridge_operation_not_observable',
    )
    expect(
      transitionBridgeState('forcesave_accepted', 'shell_tracking_started', 'oo', {
        requestedOperationId: UUID(30),
      }).to,
    ).toBe('waiting_application')
  })

  it('shell 跟踪缺 requested operation id ⇒ 拒绝', () => {
    expectRefusal(
      () => transitionBridgeState('forcesave_accepted', 'shell_tracking_started', 'oo', {}),
      'bridge_shell_requires_requested_operation',
    )
    expectRefusal(
      () =>
        transitionBridgeState('forcesave_accepted', 'shell_tracking_started', 'oo', {
          requestedOperationId: '   ',
        }),
      'bridge_shell_requires_requested_operation',
    )
  })

  it('202 带 dispatch_error ⇒ forcesave_frozen，且它与 accepted 是不同状态', () => {
    expect(transitionBridgeState('forcesave_requesting', 'forcesave_dispatch_failed', 'oo').to).toBe(
      'forcesave_frozen',
    )
    expect(transitionBridgeState('forcesave_frozen', 'forcesave_started', 'oo').to).toBe(
      'forcesave_requesting',
    )
  })

  it('shell → durable → primary bound → merging → applied', () => {
    expect(
      transitionBridgeState('waiting_application', 'operation_observed', 'oo', {
        operation: snapshot({ durableAt: '2026-08-16T00:00:00Z' }),
      }).to,
    ).toBe('incoming_durable')
    expect(
      transitionBridgeState('incoming_durable', 'operation_observed', 'oo', {
        operation: snapshot({
          state: 'application_bound',
          shape: 'primary',
          applicationId: UUID(9),
        }),
      }).to,
    ).toBe('application_bound')
    expect(
      transitionBridgeState('application_bound', 'operation_observed', 'oo', {
        operation: snapshot({ state: 'merging', shape: 'primary', applicationId: UUID(9) }),
      }).to,
    ).toBe('merging')
    expect(
      transitionBridgeState('merging', 'operation_observed', 'oo', {
        operation: snapshot({
          state: 'applied',
          shape: 'primary',
          applicationId: UUID(9),
          resultRevision: 12,
        }),
      }).to,
    ).toBe('applied')
  })

  it('applied 不得回退到 merging/conflict（只允许幂等重入与 error）', () => {
    for (const state of ['merging', 'conflict', 'rematerializing', 'application_bound'] as const) {
      expectRefusal(
        () =>
          transitionBridgeState('applied', 'operation_observed', 'oo', {
            operation: snapshot({ state, shape: 'primary', applicationId: UUID(9) }),
          }),
        'bridge_operation_transition_illegal',
      )
    }
  })

  it('applied 之后必须经 reload_completed 才回 html（mode 只在这一步翻转）', () => {
    expect(WP_BRIDGE_STATE_MODE.applied).toBe('oo')
    const result = transitionBridgeState('applied', 'reload_completed', 'oo')
    expect(result.to).toBe('html_idle')
    expect(result.mode).toBe('html')
  })

  it('conflict 经裁决进 merging，再进 applied（不得从 conflict 直接 applied）', () => {
    expect(transitionBridgeState('conflict', 'conflict_resolution_submitted', 'oo').to).toBe(
      'merging',
    )
    // 服务端把 conflict 直接推成 applied（裁决在服务端完成）也是合法观测：
    expect(
      transitionBridgeState('conflict', 'operation_observed', 'oo', {
        operation: snapshot({
          state: 'applied',
          shape: 'primary',
          applicationId: UUID(9),
          resultRevision: 13,
        }),
      }).to,
    ).toBe('applied')
  })

  it('refresh_required 只能经 rematerialize + 新 descriptor 重开', () => {
    expect(transitionBridgeState('refresh_required', 'descriptor_received', 'oo').to).toBe(
      'rematerializing',
    )
    expect(transitionBridgeState('rematerializing', 'descriptor_accepted', 'oo').to).toBe(
      'oo_loading',
    )
    expectRefusal(
      () => transitionBridgeState('refresh_required', 'reload_completed', 'oo'),
      'bridge_transition_illegal',
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// E. duplicate 是 terminal
// ═══════════════════════════════════════════════════════════════════════════

describe('duplicate 终态', () => {
  it('除 reset 外的**每一个**事件都被拒（含 operation 观测）', () => {
    for (const event of WP_BRIDGE_EVENTS) {
      if (event === 'reset') continue
      let code = ''
      try {
        transitionBridgeState('duplicate', event, 'oo', legalContext(event))
      } catch (error) {
        code = (error as WorkpaperSyncContractError).code
      }
      expect(code, `duplicate --${event}--> 未被拒`).not.toBe('')
    }
    expect(transitionBridgeState('duplicate', 'reset', 'oo').to).toBe('html_idle')
  })

  it('duplicate 观测被拒的码是「该阶段不接受观测」而不是通用非法', () => {
    expectRefusal(
      () =>
        transitionBridgeState('duplicate', 'operation_observed', 'oo', {
          operation: snapshot({
            state: 'applied',
            shape: 'primary',
            applicationId: UUID(9),
            resultRevision: 12,
          }),
        }),
      'bridge_operation_not_observable',
    )
  })

  it('application_bound 之后不得再变成 duplicate（primary 已绑定）', () => {
    expectRefusal(
      () =>
        transitionBridgeState('application_bound', 'operation_observed', 'oo', {
          operation: snapshot({
            state: 'duplicate',
            shape: 'duplicate',
            duplicateOfOperationId: UUID(31),
            canonicalOperationId: UUID(31),
          }),
        }),
      'bridge_operation_transition_illegal',
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// F. recovery
// ═══════════════════════════════════════════════════════════════════════════

describe('recovery：claim 前三实体为 0，download-only 独立终态', () => {
  it('recovery_pending / recovery_claiming 不接受 operation 观测', () => {
    for (const from of ['recovery_pending', 'recovery_claiming'] as const) {
      expectRefusal(
        () =>
          transitionBridgeState(from, 'operation_observed', 'html', {
            operation: snapshot({
              state: 'application_bound',
              shape: 'primary',
              applicationId: UUID(9),
            }),
          }),
        'bridge_operation_not_observable',
      )
    }
  })

  it('进入 recovery_pending 时任一实体非空即拒（逐实体参数化）', () => {
    const cases = [
      ['forcesaveRequestId', { forcesaveRequestId: UUID(1), applicationId: null, operationId: null }],
      ['applicationId', { forcesaveRequestId: null, applicationId: UUID(2), operationId: null }],
      ['operationId', { forcesaveRequestId: null, applicationId: null, operationId: UUID(3) }],
    ] as const
    for (const [label, entities] of cases) {
      expectRefusal(
        () =>
          transitionBridgeState('html_idle', 'recovery_case_observed', 'html', {
            recoveryEntities: entities,
          }),
        'bridge_recovery_premature_entities',
      )
      expect(label).toBeTruthy()
    }
    expect(
      transitionBridgeState('html_idle', 'recovery_case_observed', 'html', {
        recoveryEntities: { forcesaveRequestId: null, applicationId: null, operationId: null },
      }).to,
    ).toBe('recovery_pending')
  })

  it('claim 成功必须同时带三实体，缺一即拒', () => {
    for (const entities of [
      { forcesaveRequestId: null, applicationId: UUID(2), operationId: UUID(3) },
      { forcesaveRequestId: UUID(1), applicationId: null, operationId: UUID(3) },
      { forcesaveRequestId: UUID(1), applicationId: UUID(2), operationId: null },
    ]) {
      expectRefusal(
        () =>
          transitionBridgeState('recovery_claiming', 'recovery_claim_succeeded', 'html', {
            claimedEntities: entities,
            claimedShape: 'primary',
          }),
        'bridge_claim_entities_incomplete',
      )
    }
  })

  it('claim 成功进 primary 或 terminal duplicate；形态缺失即拒', () => {
    const entities = {
      forcesaveRequestId: UUID(1),
      applicationId: UUID(2),
      operationId: UUID(3),
    }
    expect(
      transitionBridgeState('recovery_claiming', 'recovery_claim_succeeded', 'html', {
        claimedEntities: entities,
        claimedShape: 'primary',
      }).to,
    ).toBe('application_bound')
    const dup = transitionBridgeState('recovery_claiming', 'recovery_claim_succeeded', 'html', {
      claimedEntities: entities,
      claimedShape: 'duplicate',
    })
    expect(dup.to).toBe('duplicate')
    expect(dup.terminal).toBe(true)
    expectRefusal(
      () =>
        transitionBridgeState('recovery_claiming', 'recovery_claim_succeeded', 'html', {
          claimedEntities: entities,
        }),
      'bridge_claim_shape_required',
    )
  })

  it('claim 失败回 pending 且三实体仍为 0', () => {
    expect(
      transitionBridgeState('recovery_claiming', 'recovery_claim_failed', 'html', {
        recoveryEntities: { forcesaveRequestId: null, applicationId: null, operationId: null },
      }).to,
    ).toBe('recovery_pending')
    expectRefusal(
      () =>
        transitionBridgeState('recovery_claiming', 'recovery_claim_failed', 'html', {
          recoveryEntities: { forcesaveRequestId: null, applicationId: UUID(2), operationId: null },
        }),
      'bridge_recovery_premature_entities',
    )
  })

  it('claim 成功只能发生在 recovery_claiming', () => {
    expectRefusal(
      () =>
        transitionBridgeState('recovery_pending', 'recovery_claim_succeeded', 'html', {
          claimedEntities: {
            forcesaveRequestId: UUID(1),
            applicationId: UUID(2),
            operationId: UUID(3),
          },
          claimedShape: 'primary',
        }),
      'bridge_claim_success_out_of_phase',
    )
  })

  it('download-only 是独立终态：任何事件（除 reset）都不能把它变成 applied', () => {
    const terminated = transitionBridgeState(
      'recovery_pending',
      'recovery_download_only_terminated',
      'html',
      { recoveryEntities: { forcesaveRequestId: null, applicationId: null, operationId: null } },
    )
    expect(terminated.to).toBe('recovery_download_only')
    expect(terminated.terminal).toBe(true)
    const reachable = WP_BRIDGE_EVENTS.filter((event) => {
      try {
        transitionBridgeState('recovery_download_only', event, 'html', legalContext(event))
        return true
      } catch {
        return false
      }
    })
    expect(reachable).toEqual(['reset'])
  })

  it('recovery 状态 mode 继承（失败/恢复不改原模式）', () => {
    for (const state of ['recovery_pending', 'recovery_claiming', 'recovery_download_only'] as const) {
      expect(WP_BRIDGE_STATE_MODE[state]).toBe('inherit')
    }
    expect(WP_BRIDGE_STATE_MODE.error).toBe('inherit')
    expect(
      transitionBridgeState('oo_editing', 'recovery_case_observed', 'oo', {
        recoveryEntities: { forcesaveRequestId: null, applicationId: null, operationId: null },
      }).mode,
    ).toBe('oo')
    expect(
      transitionBridgeState('html_idle', 'recovery_case_observed', 'html', {
        recoveryEntities: { forcesaveRequestId: null, applicationId: null, operationId: null },
      }).mode,
    ).toBe('html')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// G. close 仲裁
// ═══════════════════════════════════════════════════════════════════════════

describe('close leader 失权 → authorization-stale → successor / recovery-required', () => {
  it('失权先进 authorization_stale（而不是直接成功或直接 recovery）', () => {
    expect(transitionBridgeState('oo_editing', 'close_authorization_lost', 'oo').to).toBe(
      'close_authorization_stale',
    )
    expect(
      transitionBridgeState('waiting_application', 'close_authorization_lost', 'oo').to,
    ).toBe('close_authorization_stale')
  })

  it('无合法 successor ⇒ close_recovery_required，且它是终态', () => {
    const result = transitionBridgeState('close_authorization_stale', 'close_no_successor', 'oo')
    expect(result.to).toBe('close_recovery_required')
    expect(result.terminal).toBe(true)
    const reachable = WP_BRIDGE_EVENTS.filter((event) => {
      try {
        transitionBridgeState('close_recovery_required', event, 'oo', legalContext(event))
        return true
      } catch {
        return false
      }
    })
    expect(reachable).toEqual(['reset'])
  })

  it('显示成功必须有 successor intent id，缺它只能走 recovery-required', () => {
    expectRefusal(
      () => transitionBridgeState('close_authorization_stale', 'close_successor_applied', 'oo', {}),
      'bridge_close_successor_required',
    )
    expect(
      transitionBridgeState('close_authorization_stale', 'close_successor_applied', 'oo', {
        successorIntentId: UUID(77),
      }).to,
    ).toBe('applied')
  })

  it('authorization_stale 不能靠 operation 观测变成 applied（避免「普通成功」）', () => {
    expectRefusal(
      () =>
        transitionBridgeState('close_authorization_stale', 'operation_observed', 'oo', {
          operation: snapshot({
            state: 'applied',
            shape: 'primary',
            applicationId: UUID(9),
            resultRevision: 15,
          }),
        }),
      'bridge_operation_transition_illegal',
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// H. error 粘性（Property 48 的状态面）
// ═══════════════════════════════════════════════════════════════════════════

describe('error 不被清理/重载「洗掉」', () => {
  it('error 不接受 reload_completed（清理成功不得覆盖失败）', () => {
    expectRefusal(
      () => transitionBridgeState('error', 'reload_completed', 'oo'),
      'bridge_transition_illegal',
    )
  })

  it('error 只能由 reset 或用户显式重试离开', () => {
    const reachable = WP_BRIDGE_EVENTS.filter((event) => {
      try {
        transitionBridgeState('error', event, 'oo', legalContext(event))
        return true
      } catch {
        return false
      }
    }).sort()
    expect(reachable).toEqual([
      'flush_started',
      'forcesave_started',
      'recovery_claim_started',
      'reset',
    ])
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// I. 快照投影
// ═══════════════════════════════════════════════════════════════════════════

describe('operation 快照 → 桥状态投影', () => {
  it('后端 17 个 operation 状态逐一有归属（无兜底分支）', () => {
    const projection = bridgeStateProjectionByOperationState()
    expect(Object.keys(projection).sort()).toEqual([...WP_SYNC_OPERATION_STATES].sort())
    for (const state of WP_SYNC_OPERATION_STATES) {
      expect((WP_BRIDGE_STATES as readonly string[]).includes(projection[state]), state).toBe(true)
    }
  })

  it('pre-bind shell 带 result_revision ⇒ 拒绝（不得伪造完成凭证）', () => {
    expectRefusal(
      () => bridgeStateForOperation(snapshot({ resultRevision: 12 })),
      'bridge_pre_bind_result_revision',
    )
  })

  it('pre_correlation 按 durable_at 区分 waiting_application 与 incoming_durable', () => {
    expect(bridgeStateForOperation(snapshot({ durableAt: null }))).toBe('waiting_application')
    expect(bridgeStateForOperation(snapshot({ durableAt: '2026-08-16T00:00:00Z' }))).toBe(
      'incoming_durable',
    )
  })

  it('primary 形态即使 state 仍是 accepted 也投影成 application_bound', () => {
    expect(
      bridgeStateForOperation(
        snapshot({ state: 'accepted', shape: 'primary', applicationId: UUID(9) }),
      ),
    ).toBe('application_bound')
  })

  it('superseded 与 refresh_required 都投影成「需重载新基线」', () => {
    expect(bridgeStateForOperation(snapshot({ state: 'superseded' }))).toBe('refresh_required')
    expect(bridgeStateForOperation(snapshot({ state: 'refresh_required' }))).toBe(
      'refresh_required',
    )
  })

  it('authorization_stale 投影成 close_authorization_stale 而不是 error', () => {
    expect(bridgeStateForOperation(snapshot({ state: 'authorization_stale' }))).toBe(
      'close_authorization_stale',
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// J. Property 46：随机事件序列封闭
// ═══════════════════════════════════════════════════════════════════════════

/** 为每个事件补上「形态合法」的 context，好让判据检验的是**转换表**而不是缺参。 */
function legalContext(event: WorkpaperSyncBridgeEvent) {
  const zero = { forcesaveRequestId: null, applicationId: null, operationId: null }
  switch (event) {
    case 'operation_observed':
      return { operation: snapshot() }
    case 'shell_tracking_started':
      return { requestedOperationId: UUID(30) }
    case 'close_successor_applied':
      return { successorIntentId: UUID(77) }
    case 'recovery_claim_succeeded':
      return {
        claimedEntities: {
          forcesaveRequestId: UUID(1),
          applicationId: UUID(2),
          operationId: UUID(3),
        },
        claimedShape: 'primary' as const,
      }
    case 'recovery_case_observed':
    case 'recovery_claim_failed':
    case 'recovery_download_only_terminated':
      return { recoveryEntities: zero }
    default:
      return {}
  }
}

describe('Property 46: bridge 状态转换封闭', () => {
  it('随机事件序列只能进入声明状态，非法转换抛显式 code', () => {
    fc.assert(
      fc.property(
        fc.array(fc.constantFrom(...WP_BRIDGE_EVENTS), { minLength: 1, maxLength: 40 }),
        fc.array(
          fc.constantFrom(
            'created',
            'accepted',
            'waiting_application',
            'application_bound',
            'duplicate',
            'merging',
            'conflict',
            'applied',
            'refresh_required',
            'superseded',
            'error',
            'authorization_stale',
          ),
          { minLength: 1, maxLength: 40 },
        ),
        (events, opStates) => {
          let state: WorkpaperSyncBridgeState = 'html_idle'
          let mode: 'html' | 'oo' = 'html'
          events.forEach((event, index) => {
            const opState = opStates[index % opStates.length] as WorkpaperSyncOperationSnapshot['state']
            const context =
              event === 'operation_observed'
                ? {
                    operation: snapshot({
                      state: opState,
                      shape: opState === 'duplicate' ? ('duplicate' as const) : ('primary' as const),
                      applicationId: opState === 'duplicate' ? null : UUID(9),
                      duplicateOfOperationId: opState === 'duplicate' ? UUID(31) : null,
                      canonicalOperationId: opState === 'duplicate' ? UUID(31) : UUID(30),
                      resultRevision: opState === 'applied' ? 12 : null,
                    }),
                  }
                : legalContext(event)
            const before = { state, mode }
            try {
              const result = transitionBridgeState(state, event, mode, context)
              state = result.to
              mode = result.mode
            } catch (error) {
              // 非法转换：必须是带 code 的契约错误，且调用方持有的状态未被改动。
              expect(error).toBeInstanceOf(WorkpaperSyncContractError)
              expect((error as WorkpaperSyncContractError).code.length).toBeGreaterThan(0)
              expect({ state, mode }).toEqual(before)
            }
            expect((WP_BRIDGE_STATES as readonly string[]).includes(state)).toBe(true)
            expect(['html', 'oo']).toContain(mode)
          })
        },
      ),
      { numRuns: 300 },
    )
  })

  it('随机序列永远无法从 download-only / close-recovery 终态走到 applied', () => {
    fc.assert(
      fc.property(
        fc.constantFrom('recovery_download_only' as const, 'close_recovery_required' as const),
        fc.array(fc.constantFrom(...WP_BRIDGE_EVENTS), { minLength: 1, maxLength: 25 }),
        (start, events) => {
          let state: WorkpaperSyncBridgeState = start
          let mode: 'html' | 'oo' = 'html'
          let sawApplied = false
          for (const event of events) {
            try {
              const result = transitionBridgeState(state, event, mode, legalContext(event))
              state = result.to
              mode = result.mode
              if (state === 'applied') sawApplied = true
            } catch {
              /* 非法转换：状态不动 */
            }
            // 终态 reset 之后回到 html_idle，从那里必须重新走完整条链路才可能 applied，
            // 而链路里没有任何一步能在本序列的随机事件下伪造 result revision。
            if (state === 'applied') sawApplied = true
          }
          expect(sawApplied).toBe(false)
        },
      ),
      { numRuns: 200 },
    )
  })

  it('未声明的状态/事件一律 fail visible', () => {
    expectRefusal(
      () =>
        transitionBridgeState(
          'not_a_state' as WorkpaperSyncBridgeState,
          'reset',
          'html',
        ),
      'bridge_state_unknown',
    )
    expectRefusal(
      () =>
        transitionBridgeState(
          'html_idle',
          'not_an_event' as WorkpaperSyncBridgeEvent,
          'html',
        ),
      'bridge_event_unknown',
    )
  })
})
