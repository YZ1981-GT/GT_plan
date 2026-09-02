// `WorkpaperSyncStatusBar.vue` 的**挂载判据**（DOM + 真实 emit）。
//
// spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 34
// Validates: Requirements 5.8, 11.2, 11.3, 11.6, 11.10, 11.11
// Properties: P46（26 个状态逐一可辨）/ P48（error 优先且粘住）
//
// ═══ 为什么必须是 mounted test ═══
//
// Vue 的两种静默失效——传不存在的 prop、声明了却零消费的绑定——在 Volar / vitest /
// get_diagnostics 三层全绿。本文件每一条都落在**渲染出来的 DOM** 与**真实 emit** 上，
// 桥用的是真的 `useWorkpaperSyncBridge()`（只注入 API stub），状态靠桥自己的公开动作推。
//
// ═══ 判据设计 ═══
//
// 1. **24 个可观测状态逐一挂载**：`data-state` / 头条文案 / 基调 / 等待语义四项同时断言，
//    并断言 24 条头条文案两两不同、无一含成功字样。
//    `materializing` / `forcesave_accepted` 结构上推不到（Task 32 的同步相邻中间态），
//    本文件**反向自证**它们推不到，而不是把它们豁免。
// 2. **Task 34 点名的 12 类形态用字面量断言**，不拿被测常量当期望值。
// 3. **三个 verdict 布尔各有归属**：retry 门两侧都驱动到；另两个作显式披露并断言逐字取值。
// 4. **正面判决**：声明的 prop / emit 集合逐字等于本文件真正驱动过的集合。
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import WorkpaperSyncStatusBar from '../WorkpaperSyncStatusBar.vue'
import { WP_BRIDGE_STATES, WP_BRIDGE_STATE_TEXT } from '../workpaperSyncBridgeMachine'
import type { WorkpaperSyncBridge } from '../useWorkpaperSyncBridge'
import {
  WP_SYNC_ACTION_HINT,
  WP_SYNC_STATE_TONE,
  WP_SYNC_TRACE_GAP_PLACEHOLDER,
  WP_SYNC_WAIT_KIND,
} from '../workpaperSyncPresentation'
import {
  DIGEST,
  OBSERVABLE_BRIDGE_STATES,
  UNOBSERVABLE_BRIDGE_STATES,
  UUID,
  driveTo,
  driveToSuccessorApplied,
  harness,
  openToWaitingApplication,
  recoveryCaseFixture,
  snapshot,
  stripComments,
} from './workpaperSyncUiHarness'

const EXERCISED_PROPS = new Set<string>()
const EXERCISED_EMITS = new Set<string>()
const LIVE: VueWrapper[] = []

interface BarProps {
  bridge: WorkpaperSyncBridge
  closeSuccessorIntentId?: string | null
}

function mountBar(props: BarProps): VueWrapper {
  for (const key of Object.keys(props)) EXERCISED_PROPS.add(key)
  const wrapper = mount(WorkpaperSyncStatusBar, {
    props: props as unknown as Record<string, unknown>,
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  LIVE.push(wrapper)
  return wrapper
}

function bar(wrapper: VueWrapper) {
  return wrapper.get('[data-testid="wp-sync-status-bar"]')
}

function textOf(wrapper: VueWrapper, testid: string): string {
  const el = wrapper.find(`[data-testid="${testid}"]`)
  return el.exists() ? el.text() : ''
}

interface BarApi {
  getPresentation: () => Record<string, unknown>
}

function barApi(wrapper: VueWrapper): BarApi {
  return wrapper.vm as unknown as BarApi
}

beforeEach(() => {
  LIVE.length = 0
})

afterEach(() => {
  for (const wrapper of LIVE) {
    for (const name of Object.keys(wrapper.emitted())) EXERCISED_EMITS.add(name)
    wrapper.unmount()
  }
  LIVE.length = 0
})

// ═══════════════════════════════════════════════════════════════════════════
// 1. 24 个可观测状态逐一可辨
// ═══════════════════════════════════════════════════════════════════════════

describe('每个可观测桥状态各渲染一份互不相同的中文状态', () => {
  it('24 个状态的 data-state / 头条文案 / 基调 / 等待语义四项同时正确，阶段标签两两不同', async () => {
    const stages = new Map<string, string>()
    // 驱动路径本身就带 sticky error 的状态：桥的 error 优先规则要求头条是失败原因，
    // 而不是状态文案。这两个是**真实行为**，不是判据的例外 —— 因此期望值按
    // 「桥是否记住了失败」分流，而不是把断言放宽成「包含即可」。
    const withStickyError = new Set(['forcesave_frozen', 'error'])
    for (const state of OBSERVABLE_BRIDGE_STATES) {
      const h = await driveTo(state)
      expect(h.bridge.state.value, `驱动 ${state} 失败`).toBe(state)
      const wrapper = mountBar({ bridge: h.bridge })
      await flushPromises()
      const root = bar(wrapper)
      expect(root.attributes('data-state'), state).toBe(state)

      const sticky = h.bridge.lastError.value
      expect(sticky !== null, `${state} 的 sticky error 预期`).toBe(withStickyError.has(state))
      const message = textOf(wrapper, 'wp-sync-status-message')
      const stage = textOf(wrapper, 'wp-sync-status-stage')
      if (sticky !== null) {
        expect(root.attributes('data-kind'), state).toBe('error')
        expect(message, state).toBe(sticky.message)
        expect(stage, state).toBe(`失败于：${WP_BRIDGE_STATE_TEXT[state]}`)
        expect(root.attributes('data-tone'), state).toBe('danger')
      } else {
        expect(message, state).toBe(WP_BRIDGE_STATE_TEXT[state])
        expect(stage, state).toBe(WP_BRIDGE_STATE_TEXT[state])
        expect(root.attributes('data-tone'), state).toBe(WP_SYNC_STATE_TONE[state])
      }
      expect(root.attributes('data-wait'), state).toBe(WP_SYNC_WAIT_KIND[state])
      // 转圈只在真的还在飞的时候出现
      expect(
        wrapper.find('[data-testid="wp-sync-status-spinner"]').exists(),
        state,
      ).toBe(WP_SYNC_WAIT_KIND[state] === 'progress')
      stages.set(state, stage)
      wrapper.unmount()
      LIVE.pop()
    }
    expect(stages.size).toBe(24)
    // 阶段标签是 DOM 上真正渲染出来的那一行；两两不同 ⇒ 24 个状态在界面上可辨
    expect(new Set(stages.values()).size).toBe(24)
    for (const [state, stage] of stages) {
      expect(stage, state).not.toContain('保存成功')
      expect(stage, state).not.toContain('同步成功')
    }
  })

  it('两个不可观测状态确有其事：驱动器拒绝为它们编路径（反向自证）', async () => {
    expect(UNOBSERVABLE_BRIDGE_STATES).toEqual(['materializing', 'forcesave_accepted'])
    expect(OBSERVABLE_BRIDGE_STATES.length + UNOBSERVABLE_BRIDGE_STATES.length).toBe(
      WP_BRIDGE_STATES.length,
    )
    for (const state of UNOBSERVABLE_BRIDGE_STATES) {
      await expect(driveTo(state)).rejects.toThrow(/同步相邻的中间态/)
    }
  })

  it('settled 状态一律带具体动作提示，progress 状态一律不带（不做无限等待）', async () => {
    for (const state of OBSERVABLE_BRIDGE_STATES) {
      const h = await driveTo(state)
      const wrapper = mountBar({ bridge: h.bridge })
      await flushPromises()
      const hint = textOf(wrapper, 'wp-sync-status-action-hint')
      expect(hint, state).toBe(WP_SYNC_ACTION_HINT[state])
      if (WP_SYNC_WAIT_KIND[state] === 'settled') {
        expect(hint.length, state).toBeGreaterThan(6)
      }
      wrapper.unmount()
      LIVE.pop()
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 2. Task 34 点名的形态（字面量断言）
// ═══════════════════════════════════════════════════════════════════════════

describe('Task 34 点名的九类同步形态各有独立中文文案', () => {
  it('request frozen（正在冻结保存请求）与 accepted 后的等待回传各说各话', async () => {
    const frozen = await driveTo('forcesave_requesting')
    const frozenBar = mountBar({ bridge: frozen.bridge })
    await flushPromises()
    expect(textOf(frozenBar, 'wp-sync-status-message')).toBe('正在冻结保存请求')

    const waiting = await driveTo('waiting_application')
    const waitingBar = mountBar({ bridge: waiting.bridge })
    await flushPromises()
    expect(textOf(waitingBar, 'wp-sync-status-message')).toBe(
      '已发送强制保存，等待 OnlyOffice 回传文件',
    )
  })

  it('命令未被受理（forcesave_frozen）与命令已受理不是同一句话', async () => {
    const h = await driveTo('forcesave_frozen')
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    // dispatch 失败被桥记成 sticky error ⇒ 头条是错误、阶段带「失败于：」前缀
    expect(bar(wrapper).attributes('data-kind')).toBe('error')
    expect(textOf(wrapper, 'wp-sync-status-stage')).toBe(
      '失败于：已冻结保存请求，强制保存命令未被受理',
    )
    expect(textOf(wrapper, 'wp-sync-status-message')).toContain('强制保存命令未被受理')
  })

  it('durable（文件已耐久）与 primary application-bound（已关联）分别可辨', async () => {
    const durable = await driveTo('incoming_durable')
    const durableBar = mountBar({ bridge: durable.bridge })
    await flushPromises()
    expect(textOf(durableBar, 'wp-sync-status-message')).toBe(
      'OO 文件已耐久保存，等待关联回写任务',
    )

    const bound = await driveTo('application_bound')
    const boundBar = mountBar({ bridge: bound.bridge })
    await flushPromises()
    expect(textOf(boundBar, 'wp-sync-status-message')).toBe('回写任务已关联，等待解析合并')
  })

  it('duplicate 同时显示 requested → canonical 两个 id，且是 settled 终态', async () => {
    const h = await driveTo('duplicate')
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    const fold = wrapper.get('[data-testid="wp-sync-status-duplicate"]')
    expect(fold.attributes('data-requested')).toBe(UUID(30))
    expect(fold.attributes('data-canonical')).toBe(UUID(31))
    expect(fold.text()).toContain(UUID(30))
    expect(fold.text()).toContain(UUID(31))
    expect(fold.text()).toContain('→')
    expect(bar(wrapper).attributes('data-wait')).toBe('settled')
    expect(wrapper.find('[data-testid="wp-sync-status-spinner"]').exists()).toBe(false)
  })

  it('primary 快照下不渲染 duplicate 折叠行（不给非 duplicate 编一个 canonical）', async () => {
    const h = await driveTo('application_bound')
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    expect(wrapper.find('[data-testid="wp-sync-status-duplicate"]').exists()).toBe(false)
  })

  it('applied / conflict / refresh_required 三种终局文案互不相同', async () => {
    const texts: string[] = []
    for (const state of ['applied', 'conflict', 'refresh_required'] as const) {
      const h = await driveTo(state)
      const wrapper = mountBar({ bridge: h.bridge })
      await flushPromises()
      texts.push(textOf(wrapper, 'wp-sync-status-message'))
      wrapper.unmount()
      LIVE.pop()
    }
    expect(texts).toEqual([
      '结构化回写完成',
      '发生冲突，需逐项裁决',
      '服务器已合并，需重载编辑器确认新基线',
    ])
  })

  it('recovery pending 明说尚未创建回写任务，且不提供普通重试', async () => {
    const h = await driveTo('recovery_pending')
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    expect(textOf(wrapper, 'wp-sync-status-message')).toBe('存在待认领的恢复项，尚未创建回写任务')
    expect(wrapper.find('[data-testid="wp-sync-status-retry"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="wp-sync-status-open-recovery"]').exists()).toBe(true)
  })

  it('download-only 终态不含「回写完成」，且不是成功基调', async () => {
    const h = await driveTo('recovery_download_only')
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    expect(bar(wrapper).text()).not.toContain('回写完成')
    expect(bar(wrapper).attributes('data-tone')).not.toBe('success')
    expect(bar(wrapper).attributes('data-wait')).toBe('settled')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 3. close 仲裁三种结局
// ═══════════════════════════════════════════════════════════════════════════

describe('close leader 失权后的三种结局在状态条上逐一可辨', () => {
  it('close_authorization_stale：显示失权 + 接任者进展，不渲染成保存成功', async () => {
    const h = await driveTo('close_authorization_stale')
    const wrapper = mountBar({ bridge: h.bridge, closeSuccessorIntentId: UUID(77) })
    await flushPromises()
    const block = wrapper.get('[data-testid="wp-sync-status-close-arbitration"]')
    expect(block.attributes('data-outcome')).toBe('awaiting_successor')
    expect(block.attributes('data-successor')).toBe(UUID(77))
    expect(block.text()).toContain('接任者')
    expect(block.text()).toContain(UUID(77))
    expect(bar(wrapper).text()).not.toContain('保存成功')
    expect(bar(wrapper).attributes('data-tone')).toBe('warning')
  })

  it('接任者未回传 id 时显示仍在仲裁，不编一个 id', async () => {
    const h = await driveTo('close_authorization_stale')
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    const block = wrapper.get('[data-testid="wp-sync-status-close-arbitration"]')
    expect(block.attributes('data-successor')).toBe('')
    expect(block.text()).toContain('尚未确定接任者')
  })

  it('合法 successor 完成后阶段标签归因于接任者（不与自己保存成功同态）', async () => {
    const h = await driveToSuccessorApplied(UUID(78))
    expect(h.bridge.state.value).toBe('applied')
    const wrapper = mountBar({ bridge: h.bridge, closeSuccessorIntentId: UUID(78) })
    await flushPromises()
    const block = wrapper.get('[data-testid="wp-sync-status-close-arbitration"]')
    expect(block.attributes('data-outcome')).toBe('successor_applied')
    expect(block.text()).toContain(UUID(78))
    expect(textOf(wrapper, 'wp-sync-status-stage')).toBe('接任者代为完成：结构化回写完成')
    // 自己保存完成时**没有**这个前缀 —— 两种情形必须可区分
    const own = await driveTo('applied')
    const ownBar = mountBar({ bridge: own.bridge })
    await flushPromises()
    expect(textOf(ownBar, 'wp-sync-status-stage')).toBe('结构化回写完成')
    expect(ownBar.find('[data-testid="wp-sync-status-close-arbitration"]').exists()).toBe(false)
  })

  it('close_recovery_required：显式说明无接任者需重新授权，settled 且有具体下一步', async () => {
    const h = await driveTo('close_recovery_required')
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    const block = wrapper.get('[data-testid="wp-sync-status-close-arbitration"]')
    expect(block.attributes('data-outcome')).toBe('no_successor')
    expect(block.text()).toContain('无合法接任者')
    expect(textOf(wrapper, 'wp-sync-status-message')).toBe(
      '无合法接任者，需重新授权后从恢复流程继续',
    )
    expect(textOf(wrapper, 'wp-sync-status-action-hint')).toContain('重新授权')
    expect(bar(wrapper).attributes('data-wait')).toBe('settled')
    expect(wrapper.find('[data-testid="wp-sync-status-spinner"]').exists()).toBe(false)
    expect(bar(wrapper).text()).not.toContain('保存成功')
    expect(bar(wrapper).attributes('data-tone')).toBe('danger')
  })

  it('从未发生 close 仲裁时不渲染仲裁行（不占版面、不误导）', async () => {
    const h = await driveTo('waiting_application')
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    expect(wrapper.find('[data-testid="wp-sync-status-close-arbitration"]').exists()).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 4. error 优先且粘住（Property 48）
// ═══════════════════════════════════════════════════════════════════════════

describe('一次真失败之后不被任何成功文案覆盖', () => {
  it('applied 之后 reload 失败 ⇒ 头条变成失败原因、阶段带失败前缀、无成功色', async () => {
    const h = harness()
    await openToWaitingApplication(h)
    h.bridge.ingestOperationSnapshot(
      snapshot({
        state: 'applied',
        shape: 'primary',
        applicationId: UUID(50),
        resultRevision: 12,
        durableAt: '2026-08-16T00:00:10Z',
      }),
    )
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    expect(bar(wrapper).attributes('data-tone')).toBe('success')
    expect(textOf(wrapper, 'wp-sync-status-message')).toBe('结构化回写完成')

    h.bridge.notifyHostFailure('reload', new Error('表单重载失败'))
    await flushPromises()
    expect(bar(wrapper).attributes('data-kind')).toBe('error')
    expect(bar(wrapper).attributes('data-tone')).toBe('danger')
    expect(textOf(wrapper, 'wp-sync-status-message')).toBe('表单重载失败')
    expect(textOf(wrapper, 'wp-sync-status-stage')).toContain('失败于：')
    expect(bar(wrapper).text()).not.toContain('同步成功')
  })

  it('终态（duplicate）上报失败时状态不动但失败仍然可见（sticky）', async () => {
    const h = await driveTo('duplicate')
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    h.bridge.notifyHostFailure('editor_runtime', new Error('内核异常'))
    await flushPromises()
    expect(bar(wrapper).attributes('data-state')).toBe('duplicate')
    expect(bar(wrapper).attributes('data-kind')).toBe('error')
    expect(textOf(wrapper, 'wp-sync-status-message')).toBe('内核异常')
  })

  it('用户显式发起新尝试才清掉 sticky error（不是随便一次成功就洗白）', async () => {
    const h = harness()
    h.bridge.notifyHostFailure('flush', new Error('本地保存失败'))
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    expect(bar(wrapper).attributes('data-kind')).toBe('error')
    h.bridge.reset()
    await flushPromises()
    expect(bar(wrapper).attributes('data-kind')).toBe('idle')
    expect(textOf(wrapper, 'wp-sync-status-message')).toBe('当前为表单模式')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 5. 三个 verdict 布尔各有归属
// ═══════════════════════════════════════════════════════════════════════════

describe('classifySyncFailure 的三个布尔各有一个消费方', () => {
  it('500 ⇒ retryable=true：重试按钮出现，点击真的 emit retry', async () => {
    const h = await driveTo('waiting_application')
    h.bridge.notifyHostFailure('get_operation', {
      response: { status: 500, data: 'boom' },
      message: '服务端错误',
    })
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    const gates = wrapper.get('[data-testid="wp-sync-status-gates"]')
    expect(gates.attributes('data-retryable')).toBe('true')
    const button = wrapper.get('[data-testid="wp-sync-status-retry"]')
    await button.trigger('click')
    expect(wrapper.emitted('retry')?.length).toBe(1)
  })

  it('409 stale identity ⇒ 三个布尔全 false：重试按钮消失，两条披露显示「禁止」', async () => {
    const h = await driveTo('waiting_application')
    h.bridge.notifyHostFailure('confirm_descriptor', {
      response: {
        status: 409,
        data: { detail: { error_code: 'launch_descriptor_stale_identity', message: '身份已过期' } },
      },
    })
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    const gates = wrapper.get('[data-testid="wp-sync-status-gates"]')
    expect(gates.attributes('data-error-code')).toBe('launch_descriptor_stale_identity')
    expect(gates.attributes('data-can-enter-editing')).toBe('false')
    expect(gates.attributes('data-retryable')).toBe('false')
    expect(gates.attributes('data-can-forcesave')).toBe('false')
    expect(textOf(wrapper, 'wp-sync-gate-editing')).toBe('返回编辑：禁止')
    expect(textOf(wrapper, 'wp-sync-gate-retry')).toBe('重试回写：禁止')
    expect(textOf(wrapper, 'wp-sync-gate-forcesave')).toBe('强制保存：禁止')
    expect(wrapper.find('[data-testid="wp-sync-status-retry"]').exists()).toBe(false)
  })

  it('没有失败时不渲染披露块（它是失败后的追溯，不是常驻装饰）', async () => {
    const h = await driveTo('oo_editing')
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    expect(wrapper.find('[data-testid="wp-sync-status-gates"]').exists()).toBe(false)
  })

  it('recovery 期间即便裁决可重试也不给普通重试（AC 5.8 末句）', async () => {
    // 🔴 必须让「recovery 态 + 非空 requested operation + 可重试裁决」三者**同时**成立。
    // 首轮写法是 `driveTo('recovery_pending')` + `notifyHostFailure`，那条路有两个坑：
    // ① `recovery_pending` 有 `sync_failed` 出边 ⇒ 上报失败后状态其实已经变成 `error`；
    // ② 那条路上 `requestedOperationId` 恒为 null ⇒ 关掉的是**另一道**门。
    // 于是本条对「recovery 排除」恒绿（变异 M30 实测 GREEN）。
    //
    // 可达路径：applied → 重载回 `html_idle`（桥**不**清 `requestedOperationId`）
    //          → 观测到 crash recovery case → claim 失败（回到 `recovery_pending` 且 error 粘住）
    const h = await driveTo('applied')
    await h.bridge.reloadAfterApplied()
    expect(h.bridge.state.value).toBe('html_idle')
    expect(h.bridge.requestedOperationId.value).toBe(UUID(30))

    h.bridge.notifyRecoveryCase(recoveryCaseFixture())
    expect(h.bridge.state.value).toBe('recovery_pending')
    h.api.claimRecoveryCase.mockImplementation(async () => {
      throw { response: { status: 500, data: 'boom' }, message: '服务端错误' }
    })
    await expect(
      h.bridge.claimRecoveryCase({
        caseId: UUID(40),
        roomId: UUID(21),
        participantId: UUID(22),
        priorConfirmationId: UUID(41),
        expectedGeneration: 3,
        expectedWriteFence: 5,
        expectedDefinitionBundleSha256: DIGEST(3),
        expectedCurrentRevision: 11,
      }),
    ).rejects.toBeTruthy()
    // claim 失败回到 pending，error 粘住，requested operation 仍在
    expect(h.bridge.state.value).toBe('recovery_pending')
    expect(h.bridge.requestedOperationId.value).toBe(UUID(30))

    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    expect(wrapper.get('[data-testid="wp-sync-status-gates"]').attributes('data-retryable')).toBe(
      'true',
    )
    expect(wrapper.find('[data-testid="wp-sync-status-retry"]').exists()).toBe(false)
    expect(barApi(wrapper).getPresentation().plainRetryVisible).toBe(false)
  })

  it('没有 requested operation 时也不给普通重试（crash 早于 forcesave）', async () => {
    const h = harness()
    h.bridge.notifyHostFailure('materialize', {
      response: { status: 503, data: 'boom' },
      message: '服务不可用',
    })
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    expect(h.bridge.requestedOperationId.value).toBeNull()
    expect(wrapper.get('[data-testid="wp-sync-status-gates"]').attributes('data-retryable')).toBe(
      'true',
    )
    expect(wrapper.find('[data-testid="wp-sync-status-retry"]').exists()).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 6. 追溯 chips（AC 11.11）
// ═══════════════════════════════════════════════════════════════════════════

describe('追溯 chips 逐项来自桥，缺读取面时显式留白', () => {
  it('applied 后展示 result revision / 代际 / 授权模型 / bundle 摘要 / effective 序号', async () => {
    const h = await driveTo('applied')
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    expect(textOf(wrapper, 'wp-sync-status-revision')).toBe('内容修订号（仅展示/乐观锁）：12')
    expect(textOf(wrapper, 'wp-sync-status-generation')).toBe('representation 代际：2')
    expect(textOf(wrapper, 'wp-sync-status-authority')).toBe('授权模型：projection_contract')
    expect(textOf(wrapper, 'wp-sync-status-bundle')).toContain(DIGEST(3).slice(0, 12))
    expect(textOf(wrapper, 'wp-sync-status-last-sync')).not.toContain(
      WP_SYNC_TRACE_GAP_PLACEHOLDER,
    )
  })

  it('修订号标签逐字声明「仅展示/乐观锁」（禁止被读成可拼 route 的资源键）', async () => {
    const h = await driveTo('applied')
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    expect(textOf(wrapper, 'wp-sync-status-revision')).toContain('仅展示/乐观锁')
  })

  it('还没有 descriptor / operation 时每个 chip 都是显式占位符，不是 0 或空白', async () => {
    const h = harness()
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    for (const testid of [
      'wp-sync-status-revision',
      'wp-sync-status-generation',
      'wp-sync-status-authority',
      'wp-sync-status-bundle',
      'wp-sync-status-sequence',
      'wp-sync-status-last-sync',
    ]) {
      expect(textOf(wrapper, testid), testid).toContain(WP_SYNC_TRACE_GAP_PLACEHOLDER)
    }
  })

  it('application 绑定后 effective 序号来自桥的 fold 观测面', async () => {
    const h = harness()
    await openToWaitingApplication(h)
    h.bridge.observeApplicationFence({ applicationId: UUID(50), effectiveRequestSequence: 9 })
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    expect(textOf(wrapper, 'wp-sync-status-sequence')).toBe('application effective 序号：9')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 7. 动作出口
// ═══════════════════════════════════════════════════════════════════════════

describe('四个动作出口各有真实触发路径', () => {
  it('conflict 状态才出现「打开冲突面板」，点击 emit openConflicts', async () => {
    const editing = await driveTo('oo_editing')
    const editingBar = mountBar({ bridge: editing.bridge })
    await flushPromises()
    expect(editingBar.find('[data-testid="wp-sync-status-open-conflicts"]').exists()).toBe(false)

    const h = await driveTo('conflict')
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    await wrapper.get('[data-testid="wp-sync-status-open-conflicts"]').trigger('click')
    expect(wrapper.emitted('openConflicts')?.length).toBe(1)
  })

  it('有恢复项时出现「打开恢复面板」，点击 emit openRecovery', async () => {
    const h = await driveTo('recovery_pending')
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    await wrapper.get('[data-testid="wp-sync-status-open-recovery"]').trigger('click')
    expect(wrapper.emitted('openRecovery')?.length).toBe(1)
  })

  it('「查看详情」常驻，点击 emit openDetails', async () => {
    const h = await driveTo('html_idle')
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    await wrapper.get('[data-testid="wp-sync-status-open-details"]').trigger('click')
    expect(wrapper.emitted('openDetails')?.length).toBe(1)
  })

  it('本条只显示状态、不自己发 HTTP：桥的 API stub 一次都没被调过', async () => {
    const h = await driveTo('conflict')
    const before = Object.fromEntries(
      Object.entries(h.api).map(([key, fn]) => [key, fn.mock.calls.length]),
    )
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    await wrapper.get('[data-testid="wp-sync-status-open-conflicts"]').trigger('click')
    await wrapper.get('[data-testid="wp-sync-status-open-details"]').trigger('click')
    await flushPromises()
    for (const [key, fn] of Object.entries(h.api)) {
      expect(fn.mock.calls.length, key).toBe(before[key])
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 8. 结构判据：金额与文案真源
// ═══════════════════════════════════════════════════════════════════════════

describe('结构判据', () => {
  const SRC = resolve(__dirname, '..')

  function source(name: string): string {
    return stripComments(readFileSync(resolve(SRC, name), 'utf-8'))
  }

  it('剥注释函数正反自证（剥过头会让下面两条恒真）', () => {
    const sample = "const a = 1 // c\n/* block */\n<!-- html -->\nconst b = 'https://x'"
    const stripped = stripComments(sample)
    expect(stripped).toContain('const a = 1')
    expect(stripped).toContain('const b')
    expect(stripped).toContain('https://x')
    expect(stripped).not.toContain('block')
    expect(stripped).not.toContain('html')
  })

  it('四个 UI 文件都不从 store 模块 import fmtAmount（那会让整页崩）', () => {
    const wrong = 'from ' + "'@/stores/" + 'displayPrefs' + "'"
    for (const name of [
      'WorkpaperSyncStatusBar.vue',
      'WorkpaperSyncConflictDialog.vue',
      'WorkpaperSyncRecoveryPanel.vue',
      'WorkpaperSyncDetailsDrawer.vue',
    ]) {
      const body = source(name)
      expect(body, name).toContain(wrong)
      // 允许 import 的只有 `useDisplayPrefsStore`，绝不能是 `fmtAmount`
      const named = /import\s*\{([^}]*)\}\s*from\s*'@\/stores\/displayPrefs'/.exec(body)
      expect(named, name).not.toBeNull()
      expect((named as RegExpExecArray)[1]).toContain('useDisplayPrefsStore')
      expect((named as RegExpExecArray)[1]).not.toContain('fmtAmount')
    }
  })

  it('四个 UI 文件都在 setup 顶层取 displayPrefs（写进函数体会静默失效）', () => {
    for (const name of [
      'WorkpaperSyncStatusBar.vue',
      'WorkpaperSyncConflictDialog.vue',
      'WorkpaperSyncRecoveryPanel.vue',
      'WorkpaperSyncDetailsDrawer.vue',
    ]) {
      const body = source(name)
      const line = 'const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()'
      expect(body, name).toContain(line)
      // 顶层 = 该行左侧没有缩进
      expect(body.split('\n').some((row) => row === line), name).toBe(true)
    }
  })

  it('状态条不自己拼状态文案：唯一文案来源是桥的 feedback 与状态表', () => {
    const body = source('WorkpaperSyncStatusBar.vue')
    expect(body).toContain('props.bridge.feedback.value')
    expect(body).toContain('WP_BRIDGE_STATE_TEXT[state.value]')
    // 不得出现任何自造的成功文案
    expect(body).not.toContain('同步成功')
    expect(body).not.toContain('保存成功')
  })

  it('状态条零 HTTP：不 import 任何请求面', () => {
    const body = source('WorkpaperSyncStatusBar.vue')
    for (const forbidden of ['@/utils/http', './workpaperSyncApi', 'axios']) {
      expect(body, forbidden).not.toContain(forbidden)
    }
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 9. 零消费方判决（必须放在文件末尾）
// ═══════════════════════════════════════════════════════════════════════════

describe('零消费方判决', () => {
  it('组件声明的 prop 集合逐字等于本文件真正驱动过的集合', () => {
    const declared = Object.keys(
      (WorkpaperSyncStatusBar as unknown as { props: Record<string, unknown> }).props,
    )
    expect(declared.length).toBeGreaterThan(0)
    expect([...EXERCISED_PROPS].sort()).toEqual(declared.sort())
  })

  it('组件声明的 emit 集合逐字等于本文件真正触发过的集合', () => {
    const declared = (WorkpaperSyncStatusBar as unknown as { emits: string[] }).emits
    expect(Array.isArray(declared)).toBe(true)
    expect(declared.length).toBeGreaterThan(0)
    // VTU 会把组件内 `trigger('click')` 出来的原生事件也记一笔；显式登记排除，
    // 排除表本身参与断言，多一个少一个都会红。
    const VTU_NATIVE_ARTEFACTS = ['click'] as const
    const triggered = [...EXERCISED_EMITS].filter(
      (name) => !(VTU_NATIVE_ARTEFACTS as readonly string[]).includes(name),
    )
    expect(
      [...EXERCISED_EMITS].filter((name) =>
        (VTU_NATIVE_ARTEFACTS as readonly string[]).includes(name),
      ),
    ).toEqual([...VTU_NATIVE_ARTEFACTS])
    expect(triggered.sort()).toEqual([...declared].sort())
  })

  it('defineExpose 的只读投影被真的调用过，且逐项与 DOM 一致', async () => {
    const h = await driveTo('duplicate')
    const wrapper = mountBar({ bridge: h.bridge })
    await flushPromises()
    const projection = barApi(wrapper).getPresentation()
    expect(projection.state).toBe('duplicate')
    expect(projection.waitKind).toBe('settled')
    expect(projection.message).toBe(bar(wrapper).find('[data-testid="wp-sync-status-message"]').text())
    expect(projection.stageText).toBe(textOf(wrapper, 'wp-sync-status-stage'))
    expect(projection.closeOutcome).toBe('not_applicable')
  })
})
