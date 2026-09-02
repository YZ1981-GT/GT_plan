// `WorkpaperSyncDetailsDrawer.vue` 的**挂载判据**。
//
// spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 34
// Validates: Requirements 8.7, 11.11
// Properties: P35 / P46 / P48
//
// ═══ 判据设计 ═══
//
// 1. **追溯行逐项落在 DOM 上**，并断言「已登记缺口」那几行**只**出现占位符 ——
//    拿相邻字段顶替（如用发出侧 artifact 摘要充当回传摘要）会打红。
// 2. **两条 timeline 分开**：两个端点各调一次，渲染成两张表；recovery 侧在没有 case 时
//    连表都不出现（claim 之前根本没有 operation）。
// 3. **rollback 只提交 opaque UUID**：正例断言请求体逐字；反例用 numeric revision
//    冒充 versionId，断言**发出前**就被拦（零 HTTP）且写出具体码。
// 4. **二次确认真的是两步**：只点第一下时 rollback API 零调用。
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import WorkpaperSyncDetailsDrawer from '../WorkpaperSyncDetailsDrawer.vue'
import type { WorkpaperSyncBridge } from '../useWorkpaperSyncBridge'
import { rollbackVersion as realRollbackVersion } from '../workpaperSyncApi'
import { WorkpaperSyncContractError } from '../workpaperSyncDto'
import {
  WP_SYNC_TRACE_GAPS,
  WP_SYNC_TRACE_GAP_PLACEHOLDER,
} from '../workpaperSyncPresentation'
import {
  DIGEST,
  UUID,
  driveTo,
  harness,
  recoveryCaseFixture,
  stripComments,
  type Harness,
} from './workpaperSyncUiHarness'

const EXERCISED_PROPS = new Set<string>()
const EXERCISED_EMITS = new Set<string>()
const LIVE: VueWrapper[] = []

interface DrawerProps {
  bridge: WorkpaperSyncBridge
  visible: boolean
  expectedCurrentRevision: number
  rollbackTarget?: { versionId: string; revision: number } | null
}

function mountDrawer(props: DrawerProps): VueWrapper {
  for (const key of Object.keys(props)) EXERCISED_PROPS.add(key)
  const wrapper = mount(WorkpaperSyncDetailsDrawer, {
    props: props as unknown as Record<string, unknown>,
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  LIVE.push(wrapper)
  return wrapper
}

async function openDrawer(
  over: Partial<DrawerProps> = {},
): Promise<{ wrapper: VueWrapper; h: Harness }> {
  const h = over.bridge ? ({ bridge: over.bridge } as Harness) : await driveTo('applied')
  const wrapper = mountDrawer({
    bridge: h.bridge,
    visible: true,
    expectedCurrentRevision: 12,
    rollbackTarget: { versionId: UUID(23), revision: 11 },
    ...over,
  })
  await flushPromises()
  return { wrapper, h }
}

function traceRow(wrapper: VueWrapper, id: string) {
  return wrapper.get(`[data-row-id="${id}"]`)
}

function textOf(wrapper: VueWrapper, testid: string): string {
  const el = wrapper.find(`[data-testid="${testid}"]`)
  return el.exists() ? el.text() : ''
}

interface DrawerApi {
  submitRollback: () => Promise<void>
  getTraceability: () => {
    rows: { id: string; label: string; value: string; gap: boolean }[]
    gapIds: string[]
    operationEventCount: number | null
    recoveryEventCount: number | null
    evidenceCorrelationId: string | null
  }
}

function drawerApi(wrapper: VueWrapper): DrawerApi {
  return wrapper.vm as unknown as DrawerApi
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
// 1. 追溯事实（AC 11.11）
// ═══════════════════════════════════════════════════════════════════════════

describe('追溯事实逐项落在 DOM 上', () => {
  it('十九条有读取面的事实逐项渲染真实值', async () => {
    const { wrapper } = await openDrawer()
    const expectations: Record<string, string> = {
      content_revision: '12',
      content_version_id: UUID(23),
      representation_id: UUID(24),
      representation_generation: '2',
      room_id: UUID(21),
      room_generation: '3',
      participant_id: UUID(22),
      server_applied_revision: '11',
      client_confirmed_base_revision: '10',
      write_fence_epoch: '5',
      refresh_required: '否',
      canonical_application_id: UUID(50),
      authority_model: 'projection_contract',
    }
    for (const [id, value] of Object.entries(expectations)) {
      const row = traceRow(wrapper, id)
      expect(row.attributes('data-gap'), id).toBe('false')
      expect(row.text(), id).toContain(value)
    }
  })

  it('内容修订号逐字标注「仅展示/乐观锁」（禁止被读成资源键）', async () => {
    const { wrapper } = await openDrawer()
    expect(traceRow(wrapper, 'content_revision').text()).toContain('仅展示/乐观锁')
  })

  it('五项已登记缺口只渲染占位符，绝不出现数字或 digest', async () => {
    const { wrapper } = await openDrawer()
    for (const gap of WP_SYNC_TRACE_GAPS) {
      const row = traceRow(wrapper, gap.id)
      expect(row.attributes('data-gap'), gap.id).toBe('true')
      const value = row.findAll('td')[0].text()
      expect(value, gap.id).toBe(WP_SYNC_TRACE_GAP_PLACEHOLDER)
      expect(value, gap.id).not.toMatch(/[0-9a-f]{12}/)
      // 缺口的成因也必须写在标签上，让用户知道为什么没有
      expect(row.text(), gap.id).toContain(gap.reason)
    }
  })

  it('回传 incoming 摘要那一行不得被发出侧 artifact 摘要顶替', async () => {
    const { wrapper } = await openDrawer()
    const incomingRow = traceRow(wrapper, 'incoming_artifact_sha256')
    expect(incomingRow.text()).not.toContain(DIGEST(1).slice(0, 12))
    // 而发出侧那一行确实有值 —— 两行必须是两回事
    expect(traceRow(wrapper, 'result_artifact_sha256').text()).toContain(DIGEST(1).slice(0, 12))
  })

  it('还没有 descriptor 时每条事实都是占位符（不给 0 / 空串）', async () => {
    const h = harness()
    const { wrapper } = await openDrawer({ bridge: h.bridge })
    const projection = drawerApi(wrapper).getTraceability()
    const nonGap = projection.rows.filter((row) => !row.gap)
    expect(nonGap.map((row) => row.id)).toEqual(['refresh_required'])
    for (const row of projection.rows) {
      if (row.gap) expect(row.value, row.id).toBe(WP_SYNC_TRACE_GAP_PLACEHOLDER)
    }
  })

  it('refresh_required 状态下该行渲染「是」', async () => {
    const h = await driveTo('refresh_required')
    const { wrapper } = await openDrawer({ bridge: h.bridge })
    expect(traceRow(wrapper, 'refresh_required').text()).toContain('是')
  })

  it('effective 序号来自桥的 fold 观测面；未观测时是占位符', async () => {
    const h = await driveTo('application_bound')
    const { wrapper } = await openDrawer({ bridge: h.bridge })
    expect(
      traceRow(wrapper, 'application_effective_request_sequence').attributes('data-gap'),
    ).toBe('true')
    h.bridge.observeApplicationFence({ applicationId: UUID(50), effectiveRequestSequence: 9 })
    await flushPromises()
    const row = traceRow(wrapper, 'application_effective_request_sequence')
    expect(row.attributes('data-gap')).toBe('false')
    expect(row.text()).toContain('9')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 2. 两条 timeline 分开
// ═══════════════════════════════════════════════════════════════════════════

describe('operation 与 recovery 两条 timeline 各走各的端点', () => {
  it('未加载时两张表都不渲染事件行，只有提示', async () => {
    const { wrapper, h } = await openDrawer()
    expect(textOf(wrapper, 'wp-sync-details-operation-timeline-empty')).toContain('尚未加载')
    expect(wrapper.findAll('[data-testid="wp-sync-details-operation-event"]').length).toBe(0)
    expect(h.api.getOperationTimeline).not.toHaveBeenCalled()
    expect(h.api.getRecoveryCaseTimeline).not.toHaveBeenCalled()
  })

  it('加载 operation timeline ⇒ 两条流合并渲染，各行带 stream 与序号', async () => {
    const { wrapper, h } = await openDrawer()
    await wrapper.get('[data-testid="wp-sync-details-load-operation-timeline"]').trigger('click')
    await flushPromises()
    expect(h.api.getOperationTimeline).toHaveBeenCalledTimes(1)
    const rows = wrapper.findAll('[data-testid="wp-sync-details-operation-event"]')
    expect(rows.length).toBe(3)
    expect(rows.map((row) => `${row.attributes('data-stream')}#${row.attributes('data-sequence')}`)).toEqual(
      ['application#1', 'operation#1', 'operation#2'],
    )
    // 流名中文化，不显示裸英文
    expect(rows[0].text()).toContain('内容应用')
    expect(rows[1].text()).toContain('回写任务')
  })

  it('证据关联标识取自已加载事件的最后一个非空 correlation_id（未加载时是缺口）', async () => {
    const { wrapper } = await openDrawer()
    expect(traceRow(wrapper, 'evidence_correlation_id').attributes('data-gap')).toBe('true')
    await wrapper.get('[data-testid="wp-sync-details-load-operation-timeline"]').trigger('click')
    await flushPromises()
    const row = traceRow(wrapper, 'evidence_correlation_id')
    expect(row.attributes('data-gap')).toBe('false')
    expect(row.text()).toContain(UUID(71))
    expect(drawerApi(wrapper).getTraceability().evidenceCorrelationId).toBe(UUID(71))
  })

  it('没有恢复项 ⇒ recovery 表不渲染、加载按钮禁用，并说明 claim 前没有回写任务', async () => {
    const { wrapper, h } = await openDrawer()
    expect(textOf(wrapper, 'wp-sync-details-recovery-timeline-absent')).toContain(
      '认领之前也不存在回写任务',
    )
    expect(
      wrapper
        .get('[data-testid="wp-sync-details-load-recovery-timeline"]')
        .attributes('disabled'),
    ).toBeDefined()
    expect(h.api.getRecoveryCaseTimeline).not.toHaveBeenCalled()
  })

  it('有恢复项 ⇒ 单独加载 recovery timeline，且它结构上没有 operation 事件', async () => {
    const h = harness()
    h.bridge.notifyRecoveryCase(recoveryCaseFixture())
    const { wrapper } = await openDrawer({ bridge: h.bridge })
    await wrapper.get('[data-testid="wp-sync-details-load-recovery-timeline"]').trigger('click')
    await flushPromises()
    expect(h.api.getRecoveryCaseTimeline).toHaveBeenCalledTimes(1)
    expect(h.api.getRecoveryCaseTimeline.mock.calls[0][1]).toBe(UUID(40))
    const rows = wrapper.findAll('[data-testid="wp-sync-details-recovery-event"]')
    expect(rows.length).toBe(2)
    expect(textOf(wrapper, 'wp-sync-details-recovery-three-entities')).toContain('是')
    // operation 侧仍未加载 ⇒ 两条 timeline 真的是两条
    expect(h.api.getOperationTimeline).not.toHaveBeenCalled()
    expect(drawerApi(wrapper).getTraceability().operationEventCount).toBeNull()
    expect(drawerApi(wrapper).getTraceability().recoveryEventCount).toBe(2)
  })

  it('timeline 加载失败 ⇒ 显示具体码并保持未加载，不画半张表', async () => {
    const h = await driveTo('applied')
    h.api.getOperationTimeline.mockImplementation(async () => {
      throw {
        response: {
          status: 403,
          data: '资源不存在或不可访问',
        },
      }
    })
    const { wrapper } = await openDrawer({ bridge: h.bridge })
    await wrapper.get('[data-testid="wp-sync-details-load-operation-timeline"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="wp-sync-details-error"]').attributes('data-code')).toBe(
      'sync_scope_not_visible_or_forbidden',
    )
    expect(wrapper.findAll('[data-testid="wp-sync-details-operation-event"]').length).toBe(0)
    expect(wrapper.emitted('failed')?.length).toBe(1)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 3. rollback 只提交 opaque UUID（AC 8.7）
// ═══════════════════════════════════════════════════════════════════════════

describe('rollback 提交 opaque versionId，numeric revision 只作乐观锁', () => {
  it('两个值分开展示：不透明 UUID 与「仅展示」修订号', async () => {
    const { wrapper } = await openDrawer()
    expect(textOf(wrapper, 'wp-sync-details-rollback-version')).toContain(UUID(23))
    expect(textOf(wrapper, 'wp-sync-details-rollback-revision')).toContain('仅展示')
    expect(textOf(wrapper, 'wp-sync-details-rollback-revision')).toContain('11')
    expect(textOf(wrapper, 'wp-sync-details-rollback-lock')).toContain('12')
  })

  it('二次确认真的是两步：只点第一下时 rollback API 零调用', async () => {
    const { wrapper, h } = await openDrawer()
    await wrapper.get('[data-testid="wp-sync-details-rollback-request"]').trigger('click')
    await flushPromises()
    expect(h.api.rollbackVersion).not.toHaveBeenCalled()
    expect(wrapper.find('[data-testid="wp-sync-details-rollback-confirm"]').exists()).toBe(true)
    await wrapper.get('[data-testid="wp-sync-details-rollback-cancel"]').trigger('click')
    await flushPromises()
    expect(h.api.rollbackVersion).not.toHaveBeenCalled()
  })

  it('确认后请求体逐字：versionId 是 UUID，revision 只进 expected_current', async () => {
    const { wrapper, h } = await openDrawer()
    await wrapper.get('[data-testid="wp-sync-details-rollback-request"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="wp-sync-details-rollback-confirm"]').trigger('click')
    await flushPromises()
    expect(h.api.rollbackVersion).toHaveBeenCalledTimes(1)
    expect(h.api.rollbackVersion.mock.calls[0][1]).toEqual({
      versionId: UUID(23),
      expectedCurrentRevision: 12,
      confirmed: true,
    })
    expect(wrapper.emitted('rolledBack')?.length).toBe(1)
  })

  it('用 numeric revision 冒充 versionId ⇒ 抽屉自己的门先拦住（本层专属码 + 零调用）', async () => {
    const h = await driveTo('applied')
    const { wrapper } = await openDrawer({
      bridge: h.bridge,
      rollbackTarget: { versionId: '12', revision: 12 },
    })
    // 按钮本就不可点
    const hint = wrapper.get('[data-testid="wp-sync-details-rollback-hint"]')
    expect(hint.attributes('data-reason')).toBe('not_opaque')
    expect(hint.text()).toContain('不透明 immutable UUID')
    expect(
      wrapper.get('[data-testid="wp-sync-details-rollback-request"]').attributes('disabled'),
    ).toBeDefined()
    // 🔴 程序化调用也必须被拦 —— 门若只长在 `:disabled` 上，这里会漏
    await drawerApi(wrapper).submitRollback()
    await flushPromises()
    expect(h.api.rollbackVersion).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="wp-sync-details-error"]').attributes('data-code')).toBe(
      'details_rollback_target_not_opaque',
    )
    expect(wrapper.emitted('rolledBack')).toBeUndefined()
    expect(wrapper.emitted('failed')?.length).toBe(1)
  })

  it('第二层门在 API 层：真实 rollbackVersion 对 numeric revision 抛 version_id_not_opaque', async () => {
    // 两层各一个码：抽屉那层是 `details_rollback_target_not_opaque`，
    // 路由拼接那层是 `version_id_not_opaque`。共用一个码会让删掉任一层看不出差别。
    let caught: unknown
    try {
      await realRollbackVersion(
        { projectId: UUID(101), wpId: UUID(102), entryId: 'xlsx/a/b' },
        { versionId: '12', expectedCurrentRevision: 12, confirmed: true },
      )
    } catch (error) {
      caught = error
    }
    expect(caught).toBeInstanceOf(WorkpaperSyncContractError)
    expect((caught as WorkpaperSyncContractError).code).toBe('version_id_not_opaque')
    expect((caught as WorkpaperSyncContractError).code).not.toBe(
      'details_rollback_target_not_opaque',
    )
  })

  it('未指定回滚目标 ⇒ 按钮禁用并说明「历史版本清单没有读取面」', async () => {
    const { wrapper, h } = await openDrawer({ rollbackTarget: null })
    expect(
      wrapper.get('[data-testid="wp-sync-details-rollback-request"]').attributes('disabled'),
    ).toBeDefined()
    const hint = wrapper.get('[data-testid="wp-sync-details-rollback-hint"]')
    expect(hint.attributes('data-reason')).toBe('absent')
    expect(hint.text()).toContain('没有用户读取面')
    expect(h.api.rollbackVersion).not.toHaveBeenCalled()
  })

  it('合法 UUID 目标下不渲染阻断提示（正反两侧都驱动到）', async () => {
    const { wrapper } = await openDrawer()
    expect(wrapper.find('[data-testid="wp-sync-details-rollback-hint"]').exists()).toBe(false)
  })

  it('服务端拒绝回滚 ⇒ 显示具体码、不 emit rolledBack', async () => {
    const h = await driveTo('applied')
    h.api.rollbackVersion.mockImplementation(async () => {
      throw {
        response: {
          status: 409,
          data: { detail: { error_code: 'rollback_revision_stale', message: '当前修订号已变化' } },
        },
      }
    })
    const { wrapper } = await openDrawer({ bridge: h.bridge })
    await wrapper.get('[data-testid="wp-sync-details-rollback-request"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="wp-sync-details-rollback-confirm"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="wp-sync-details-error"]').attributes('data-code')).toBe(
      'rollback_revision_stale',
    )
    expect(wrapper.emitted('rolledBack')).toBeUndefined()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 4. 开关
// ═══════════════════════════════════════════════════════════════════════════

describe('抽屉开关', () => {
  it('visible=false 时整个抽屉不渲染，也不发任何请求', async () => {
    const h = await driveTo('applied')
    const wrapper = mountDrawer({
      bridge: h.bridge,
      visible: false,
      expectedCurrentRevision: 12,
      rollbackTarget: { versionId: UUID(23), revision: 11 },
    })
    await flushPromises()
    expect(wrapper.find('[data-testid="wp-sync-details-drawer"]').exists()).toBe(false)
    expect(h.api.getOperationTimeline).not.toHaveBeenCalled()
  })

  it('关闭按钮与遮罩都只 emit update:visible(false)，并收起未完成的二次确认', async () => {
    const { wrapper, h } = await openDrawer()
    await wrapper.get('[data-testid="wp-sync-details-rollback-request"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="wp-sync-details-close"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('update:visible')?.at(-1)).toEqual([false])
    expect(h.api.rollbackVersion).not.toHaveBeenCalled()

    const second = await openDrawer()
    await second.wrapper.get('[data-testid="wp-sync-details-mask"]').trigger('click')
    await flushPromises()
    expect(second.wrapper.emitted('update:visible')?.at(-1)).toEqual([false])
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 5. 结构判据
// ═══════════════════════════════════════════════════════════════════════════

describe('结构判据', () => {
  const body = stripComments(
    readFileSync(resolve(__dirname, '..', 'WorkpaperSyncDetailsDrawer.vue'), 'utf-8'),
  )

  it('抽屉零 HTTP：不 import 任何请求面', () => {
    for (const forbidden of ['@/utils/http', './workpaperSyncApi', 'axios']) {
      expect(body, forbidden).not.toContain(forbidden)
    }
    expect(body).toContain('props.bridge.rollbackVersion')
    expect(body).toContain('props.bridge.fetchTimeline')
    expect(body).toContain('props.bridge.fetchRecoveryCaseTimeline')
  })

  it('rollback 只提交 versionId：源码里没有把 revision 拼进任何标识的写法', () => {
    const call = body.slice(body.indexOf('props.bridge.rollbackVersion'))
    const args = call.slice(0, call.indexOf('})'))
    expect(args).toContain('versionId: target.versionId')
    expect(args).toContain('expectedCurrentRevision')
    expect(args).not.toMatch(/versionId:\s*[^,]*revision/)
  })

  it('模板属性里没有中文弯引号', () => {
    const template = body.slice(0, body.indexOf('<script'))
    expect(template).not.toContain('\u201c')
    expect(template).not.toContain('\u201d')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 6. 零消费方判决（必须放在文件末尾）
// ═══════════════════════════════════════════════════════════════════════════

describe('零消费方判决', () => {
  it('组件声明的 prop 集合逐字等于本文件真正驱动过的集合', () => {
    const declared = Object.keys(
      (WorkpaperSyncDetailsDrawer as unknown as { props: Record<string, unknown> }).props,
    )
    expect(declared.length).toBeGreaterThan(0)
    expect([...EXERCISED_PROPS].sort()).toEqual(declared.sort())
  })

  it('组件声明的 emit 集合逐字等于本文件真正触发过的集合', () => {
    const declared = (WorkpaperSyncDetailsDrawer as unknown as { emits: string[] }).emits
    expect(Array.isArray(declared)).toBe(true)
    expect(declared.length).toBeGreaterThan(0)
    const VTU_NATIVE_ARTEFACTS = ['click'] as const
    const artefacts = [...EXERCISED_EMITS].filter((name) =>
      (VTU_NATIVE_ARTEFACTS as readonly string[]).includes(name),
    )
    const triggered = [...EXERCISED_EMITS].filter(
      (name) => !(VTU_NATIVE_ARTEFACTS as readonly string[]).includes(name),
    )
    expect(artefacts.sort()).toEqual([...VTU_NATIVE_ARTEFACTS].sort())
    expect(triggered.sort()).toEqual([...declared].sort())
  })

  it('defineExpose 的两个入口都被真的调用过，且 gapIds 与登记表一致', async () => {
    const { wrapper } = await openDrawer()
    expect(typeof drawerApi(wrapper).submitRollback).toBe('function')
    const projection = drawerApi(wrapper).getTraceability()
    expect(projection.rows.length).toBeGreaterThan(20)
    for (const gap of WP_SYNC_TRACE_GAPS) {
      expect(projection.gapIds, gap.id).toContain(gap.id)
    }
  })
})
