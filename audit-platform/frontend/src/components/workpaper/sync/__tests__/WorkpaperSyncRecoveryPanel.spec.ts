// `WorkpaperSyncRecoveryPanel.vue` 的**挂载判据**。
//
// spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 34
// Validates: Requirements 5.8, 10.6, 11.6, 11.11
// Properties: P46（recovery 三态与 operation 流分离）/ P48
//
// ═══ 判据设计 ═══
//
// 1. **list 之前什么都不显示**：候选、bundle 摘要、动作按钮全都不在 DOM 里。
//    只断言「按钮不可点」对「先画一张空表」全绿。
// 2. **claim 前三实体逐项「尚未创建」且没有任何普通重试入口**：既断言 DOM 缺失，
//    也断言源码里根本不出现 `retryOperation`（结构 + 行为双边）。
// 3. **claim 成功后三实体同时出现**，取自 recovery timeline，并与桥跟踪的原 operation
//    交叉核对；核对不上时可见失败而不是显示「已认领」。
// 4. **download-only 不含「回写完成」**：断言整块 DOM 文本。
// 5. **显式 scope 与桥实际 scope 交叉核对**：漂移时停用动作并说明。
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import WorkpaperSyncRecoveryPanel from '../WorkpaperSyncRecoveryPanel.vue'
import type { WorkpaperSyncBridge } from '../useWorkpaperSyncBridge'
import {
  WP_SYNC_RECOVERY_REASON_TEXT,
  WP_SYNC_RECOVERY_STATE_TEXT,
  type WorkpaperSyncClaimFence,
} from '../workpaperSyncPresentation'
import {
  DIGEST,
  ENTRY,
  PROJECT,
  UUID,
  WP,
  harness,
  recoveryCaseFixture,
  stripComments,
  type Harness,
} from './workpaperSyncUiHarness'

const EXERCISED_PROPS = new Set<string>()
const EXERCISED_EMITS = new Set<string>()
const LIVE: VueWrapper[] = []

const SCOPE = { projectId: PROJECT, wpId: WP, entryId: ENTRY }
const CLAIM_FENCE: WorkpaperSyncClaimFence = {
  participantId: UUID(22),
  expectedGeneration: 3,
  expectedWriteFence: 5,
  expectedDefinitionBundleSha256: DIGEST(3),
  expectedCurrentRevision: 11,
}

interface PanelProps {
  bridge: WorkpaperSyncBridge
  scope: { projectId: string; wpId: string; entryId: string }
  roomId: string
  generation: number
  claimFence?: WorkpaperSyncClaimFence | null
}

function mountPanel(props: PanelProps): VueWrapper {
  for (const key of Object.keys(props)) EXERCISED_PROPS.add(key)
  const wrapper = mount(WorkpaperSyncRecoveryPanel, {
    props: props as unknown as Record<string, unknown>,
    global: { plugins: [ElementPlus] },
    attachTo: document.body,
  })
  LIVE.push(wrapper)
  return wrapper
}

function makePanel(over: Partial<PanelProps> = {}): { wrapper: VueWrapper; h: Harness } {
  const h = (over.bridge ? { bridge: over.bridge } : harness()) as Harness
  const wrapper = mountPanel({
    bridge: h.bridge,
    scope: SCOPE,
    roomId: UUID(21),
    generation: 3,
    claimFence: CLAIM_FENCE,
    ...over,
  })
  return { wrapper, h }
}

function root(wrapper: VueWrapper) {
  return wrapper.get('[data-testid="wp-sync-recovery-panel"]')
}

function textOf(wrapper: VueWrapper, testid: string): string {
  const el = wrapper.find(`[data-testid="${testid}"]`)
  return el.exists() ? el.text() : ''
}

async function listOnce(wrapper: VueWrapper): Promise<void> {
  await wrapper.get('[data-testid="wp-sync-recovery-list"]').trigger('click')
  await flushPromises()
}

interface PanelApi {
  getRecoveryState: () => {
    listed: boolean
    caseCount: number
    scopeDrift: string | null
    bundleDigest: string
    claimResult: Record<string, unknown> | null
    downloadOnlyCaseId: string | null
    plainRetryOffered: boolean
  }
}

function panelApi(wrapper: VueWrapper): PanelApi {
  return wrapper.vm as unknown as PanelApi
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
// 1. list 之前什么都不显示
// ═══════════════════════════════════════════════════════════════════════════

describe('authorization-first list 是唯一可见性门', () => {
  it('未查询时候选 / bundle 摘要 / 动作按钮全不在 DOM 里', () => {
    const h = harness()
    const { wrapper } = makePanel({ bridge: h.bridge })
    expect(root(wrapper).attributes('data-listed')).toBe('false')
    expect(wrapper.find('[data-testid="wp-sync-recovery-case"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="wp-sync-recovery-candidate"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="wp-sync-recovery-bundle"]').exists()).toBe(false)
    expect(wrapper.find(`[data-testid="wp-sync-recovery-claim-${UUID(40)}"]`).exists()).toBe(false)
    expect(textOf(wrapper, 'wp-sync-recovery-not-listed')).toContain('服务端授权列出后才显示')
    expect(h.api.listRecoveryCases).not.toHaveBeenCalled()
  })

  it('显式 project/wp/entry 与 room/代际逐项披露（AC 10.6）', () => {
    const { wrapper } = makePanel()
    expect(textOf(wrapper, 'wp-sync-recovery-scope-project')).toContain(PROJECT)
    expect(textOf(wrapper, 'wp-sync-recovery-scope-wp')).toContain(WP)
    expect(textOf(wrapper, 'wp-sync-recovery-scope-entry')).toContain(ENTRY)
    expect(textOf(wrapper, 'wp-sync-recovery-scope-room')).toContain(UUID(21))
    expect(textOf(wrapper, 'wp-sync-recovery-scope-generation')).toContain('3')
  })

  it('查询时 room/代际逐字随请求发出（不靠 descriptor 兜底）', async () => {
    const { wrapper, h } = makePanel()
    await listOnce(wrapper)
    expect(h.api.listRecoveryCases).toHaveBeenCalledTimes(1)
    const [scope, room] = h.api.listRecoveryCases.mock.calls[0] as [
      Record<string, unknown>,
      Record<string, unknown>,
    ]
    expect(scope).toEqual({ projectId: PROJECT, wpId: WP, entryId: ENTRY })
    expect(room).toEqual({ roomId: UUID(21), generation: 3 })
    expect(root(wrapper).attributes('data-listed')).toBe('true')
    expect(wrapper.emitted('listed')?.[0]).toEqual([{ count: 1 }])
  })

  it('list 失败 ⇒ 仍然是未列出状态并显示具体码，不画半张表', async () => {
    const h = harness()
    h.api.listRecoveryCases.mockImplementation(async () => {
      throw { response: { status: 404, data: '资源不存在或不可访问' } }
    })
    const { wrapper } = makePanel({ bridge: h.bridge })
    await listOnce(wrapper)
    expect(root(wrapper).attributes('data-listed')).toBe('false')
    const error = wrapper.get('[data-testid="wp-sync-recovery-error"]')
    expect(error.attributes('data-code')).toBe('sync_scope_not_visible_or_forbidden')
    expect(wrapper.find('[data-testid="wp-sync-recovery-case"]').exists()).toBe(false)
    expect(wrapper.emitted('failed')?.length).toBe(1)
  })

  it('列出后没有 case ⇒ 明说没有，不留空白', async () => {
    const h = harness()
    h.api.listRecoveryCases.mockImplementation(async () => ({
      roomId: UUID(21),
      generation: 3,
      cases: [],
    }))
    const { wrapper } = makePanel({ bridge: h.bridge })
    await listOnce(wrapper)
    expect(textOf(wrapper, 'wp-sync-recovery-empty')).toContain('没有可处理的恢复项')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 2. claim 之前：三实体全空、无普通重试
// ═══════════════════════════════════════════════════════════════════════════

describe('claim 之前三实体全空且不提供普通重试', () => {
  it('三实体逐项渲染「尚未创建」，data-entities-present=0', async () => {
    const { wrapper } = makePanel()
    await listOnce(wrapper)
    const item = wrapper.get('[data-testid="wp-sync-recovery-case"]')
    expect(item.attributes('data-entities-present')).toBe('0')
    expect(textOf(wrapper, 'wp-sync-recovery-entity-forcesave_request_id')).toContain('尚未创建')
    expect(textOf(wrapper, 'wp-sync-recovery-entity-application_id')).toContain('尚未创建')
    expect(textOf(wrapper, 'wp-sync-recovery-entity-operation_id')).toContain('尚未创建')
  })

  it('DOM 里没有任何「重试」入口，且投影里 plainRetryOffered 恒 false', async () => {
    const { wrapper } = makePanel()
    await listOnce(wrapper)
    expect(root(wrapper).text()).not.toContain('重试回写')
    expect(panelApi(wrapper).getRecoveryState().plainRetryOffered).toBe(false)
  })

  it('原因与状态都中文化（不显示裸英文枚举）', async () => {
    const { wrapper } = makePanel()
    await listOnce(wrapper)
    expect(textOf(wrapper, 'wp-sync-recovery-case-reason')).toBe(
      WP_SYNC_RECOVERY_REASON_TEXT.crash_close,
    )
    expect(textOf(wrapper, 'wp-sync-recovery-case-state')).toBe(
      WP_SYNC_RECOVERY_STATE_TEXT.unclaimed,
    )
  })

  it('候选 prior confirmation 与宿主提供的 bundle 摘要都渲染出来', async () => {
    const { wrapper } = makePanel()
    await listOnce(wrapper)
    const candidate = wrapper.get('[data-testid="wp-sync-recovery-candidate"]')
    expect(candidate.attributes('data-confirmation-id')).toBe(UUID(41))
    expect(candidate.text()).toContain(UUID(22))
    expect(candidate.text()).toContain(UUID(23))
    expect(textOf(wrapper, 'wp-sync-recovery-bundle-digest')).toContain(DIGEST(3).slice(0, 12))
    expect(textOf(wrapper, 'wp-sync-recovery-fence')).toContain('3 / 5')
  })

  it('宿主没给冻结身份 ⇒ 摘要显示「未提供」、claim 禁用、阻断原因逐条渲染', async () => {
    const { wrapper } = makePanel({ claimFence: null })
    await listOnce(wrapper)
    expect(textOf(wrapper, 'wp-sync-recovery-bundle-digest')).toContain('未提供')
    const reasons = wrapper
      .findAll('[data-testid="wp-sync-recovery-blocking-reason"]')
      .map((el) => el.text())
    expect(reasons.length).toBe(1)
    expect(reasons[0]).toContain('definition bundle')
    // 🔴 必须**先选好候选确认**再断言禁用：否则关掉门的其实是「未选候选」那一道，
    // 「阻断原因也参与门控」这条恒绿（变异 M52 实测 GREEN）。
    await wrapper.get(`[data-testid="wp-sync-recovery-pick-${UUID(41)}"]`).setValue(true)
    await flushPromises()
    expect(
      wrapper.get(`[data-testid="wp-sync-recovery-claim-${UUID(40)}"]`).attributes('disabled'),
    ).toBeDefined()
  })

  it('阻断原因存在时即便已选候选也不许认领（点击后 claim API 零调用）', async () => {
    const { wrapper, h } = makePanel({ claimFence: null })
    await listOnce(wrapper)
    await wrapper.get(`[data-testid="wp-sync-recovery-pick-${UUID(41)}"]`).setValue(true)
    await flushPromises()
    await wrapper.get(`[data-testid="wp-sync-recovery-claim-${UUID(40)}"]`).trigger('click')
    await flushPromises()
    expect(h.api.claimRecoveryCase).not.toHaveBeenCalled()
  })

  it('没有候选确认 ⇒ 明说没有合法基线且 claim 禁用', async () => {
    const h = harness()
    h.api.listRecoveryCases.mockImplementation(async () => ({
      roomId: UUID(21),
      generation: 3,
      cases: [recoveryCaseFixture({ candidatePriorConfirmations: [] })],
    }))
    const { wrapper } = makePanel({ bridge: h.bridge })
    await listOnce(wrapper)
    expect(textOf(wrapper, 'wp-sync-recovery-no-candidate')).toContain('没有可作合法基线')
    expect(
      wrapper.get(`[data-testid="wp-sync-recovery-claim-${UUID(40)}"]`).attributes('disabled'),
    ).toBeDefined()
  })

  it('服务端关掉两个动作 ⇒ 两个按钮都不渲染，并给出中文阻断原因', async () => {
    const h = harness()
    h.api.listRecoveryCases.mockImplementation(async () => ({
      roomId: UUID(21),
      generation: 3,
      cases: [
        recoveryCaseFixture({
          state: 'expired',
          actions: { claim: false, downloadOnly: false },
        }),
      ],
    }))
    const { wrapper } = makePanel({ bridge: h.bridge })
    await listOnce(wrapper)
    expect(wrapper.find(`[data-testid="wp-sync-recovery-claim-${UUID(40)}"]`).exists()).toBe(false)
    expect(
      wrapper.find(`[data-testid="wp-sync-recovery-download-only-${UUID(40)}"]`).exists(),
    ).toBe(false)
    expect(
      wrapper.findAll('[data-testid="wp-sync-recovery-blocking-reason"]').map((el) => el.text()),
    ).toContainEqual(expect.stringContaining(WP_SYNC_RECOVERY_STATE_TEXT.expired))
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 3. claim 成功：三实体同时出现且跟踪原 operation
// ═══════════════════════════════════════════════════════════════════════════

describe('authorization-first claim 成功后三实体同时出现', () => {
  async function claimOnce(wrapper: VueWrapper): Promise<void> {
    await listOnce(wrapper)
    await wrapper.get(`[data-testid="wp-sync-recovery-pick-${UUID(41)}"]`).setValue(true)
    await flushPromises()
    await wrapper.get(`[data-testid="wp-sync-recovery-claim-${UUID(40)}"]`).trigger('click')
    await flushPromises()
  }

  it('claim 请求体只带白名单字段，且逐项来自宿主给的冻结身份', async () => {
    const { wrapper, h } = makePanel()
    await claimOnce(wrapper)
    expect(h.api.claimRecoveryCase).toHaveBeenCalledTimes(1)
    expect(h.api.claimRecoveryCase.mock.calls[0][1]).toEqual({
      caseId: UUID(40),
      roomId: UUID(21),
      participantId: UUID(22),
      priorConfirmationId: UUID(41),
      expectedGeneration: 3,
      expectedWriteFence: 5,
      expectedDefinitionBundleSha256: DIGEST(3),
      expectedCurrentRevision: 11,
    })
  })

  it('成功后三实体同时渲染，并显式声明仍跟踪原回写任务', async () => {
    const { wrapper, h } = makePanel()
    await claimOnce(wrapper)
    const block = wrapper.get('[data-testid="wp-sync-recovery-claimed"]')
    expect(block.attributes('data-has-three-entities')).toBe('true')
    expect(textOf(wrapper, 'wp-sync-recovery-claimed-request')).toContain(UUID(42))
    expect(textOf(wrapper, 'wp-sync-recovery-claimed-application')).toContain(UUID(44))
    expect(textOf(wrapper, 'wp-sync-recovery-claimed-operation')).toContain(UUID(43))
    expect(textOf(wrapper, 'wp-sync-recovery-claimed-tracked')).toContain(UUID(43))
    expect(h.bridge.requestedOperationId.value).toBe(UUID(43))
    expect(wrapper.emitted('claimed')?.[0]).toEqual([{ caseId: UUID(40), operationId: UUID(43) }])
  })

  it('三实体取自 recovery case timeline（claim 回执没有 request id，不许猜）', async () => {
    const { wrapper, h } = makePanel()
    await claimOnce(wrapper)
    expect(h.api.getRecoveryCaseTimeline).toHaveBeenCalledTimes(1)
    expect(h.api.getRecoveryCaseTimeline.mock.calls[0][1]).toBe(UUID(40))
  })

  it('timeline 的 operation 与桥跟踪的不一致 ⇒ 可见失败，不显示「已认领」', async () => {
    const h = harness()
    h.api.getRecoveryCaseTimeline.mockImplementation(async () => ({
      case_id: UUID(40),
      state: 'application_created',
      reason: 'crash_close',
      claimed_operation_id: UUID(99),
      claimed_application_id: UUID(44),
      recovery_request_id: UUID(42),
      has_three_entities: true,
      events: [],
    }))
    const { wrapper } = makePanel({ bridge: h.bridge })
    await claimOnce(wrapper)
    const error = wrapper.get('[data-testid="wp-sync-recovery-error"]')
    expect(error.attributes('data-code')).toBe('recovery_claim_operation_drift')
    expect(wrapper.find('[data-testid="wp-sync-recovery-claimed"]').exists()).toBe(false)
    expect(wrapper.emitted('claimed')).toBeUndefined()
  })

  it('claim 被服务端拒绝 ⇒ 三实体仍全空、显示具体码、不进 operation 流程', async () => {
    const h = harness()
    h.api.claimRecoveryCase.mockImplementation(async () => {
      throw {
        response: {
          status: 409,
          data: {
            detail: { error_code: 'recovery_prior_confirmation_invalid', message: '候选基线不合法' },
          },
        },
      }
    })
    const { wrapper } = makePanel({ bridge: h.bridge })
    await claimOnce(wrapper)
    expect(wrapper.get('[data-testid="wp-sync-recovery-error"]').attributes('data-code')).toBe(
      'recovery_prior_confirmation_invalid',
    )
    expect(wrapper.find('[data-testid="wp-sync-recovery-claimed"]').exists()).toBe(false)
    expect(h.bridge.requestedOperationId.value).toBeNull()
    expect(h.bridge.state.value).toBe('recovery_pending')
    expect(root(wrapper).text()).not.toContain('重试回写')
  })

  it('没选候选就点 claim ⇒ 按钮本就禁用，claim API 零调用', async () => {
    const { wrapper, h } = makePanel()
    await listOnce(wrapper)
    const button = wrapper.get(`[data-testid="wp-sync-recovery-claim-${UUID(40)}"]`)
    expect(button.attributes('disabled')).toBeDefined()
    await button.trigger('click')
    await flushPromises()
    expect(h.api.claimRecoveryCase).not.toHaveBeenCalled()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 4. download-only 永不显示「回写完成」
// ═══════════════════════════════════════════════════════════════════════════

describe('download-only 只下载并终结', () => {
  async function downloadOnly(wrapper: VueWrapper): Promise<void> {
    await listOnce(wrapper)
    await wrapper
      .get(`[data-testid="wp-sync-recovery-download-only-${UUID(40)}"]`)
      .trigger('click')
    await flushPromises()
  }

  it('终结后显式声明未执行结构化回写，且整块 DOM 不含「回写完成」', async () => {
    const { wrapper, h } = makePanel()
    await downloadOnly(wrapper)
    expect(h.api.terminateRecoveryDownloadOnly).toHaveBeenCalledTimes(1)
    const note = textOf(wrapper, 'wp-sync-recovery-download-note')
    expect(note).toContain('未执行结构化回写')
    expect(note).toContain('三者均未创建')
    expect(root(wrapper).text()).not.toContain('回写完成')
    expect(wrapper.emitted('downloadOnly')?.[0]).toEqual([{ caseId: UUID(40) }])
  })

  it('下载动作带上服务端签发的短期 claim，并展示文件摘要与大小', async () => {
    const { wrapper, h } = makePanel()
    await downloadOnly(wrapper)
    await wrapper
      .get(`[data-testid="wp-sync-recovery-download-artifact-${UUID(40)}"]`)
      .trigger('click')
    await flushPromises()
    expect(h.api.downloadRecoveryArtifact).toHaveBeenCalledTimes(1)
    expect(h.api.downloadRecoveryArtifact.mock.calls[0][1]).toEqual({
      caseId: UUID(40),
      claim: 'claim-1',
    })
    const info = textOf(wrapper, 'wp-sync-recovery-download-artifact-info')
    expect(info).toContain(DIGEST(8).slice(0, 12))
    expect(info).toContain('1024 字节')
    expect(root(wrapper).text()).not.toContain('回写完成')
  })

  it('download-only 之后桥仍是独立终态，三实体不出现', async () => {
    const { wrapper, h } = makePanel()
    await downloadOnly(wrapper)
    expect(h.bridge.state.value).toBe('recovery_download_only')
    expect(wrapper.find('[data-testid="wp-sync-recovery-claimed"]').exists()).toBe(false)
    expect(panelApi(wrapper).getRecoveryState().claimResult).toBeNull()
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 5. scope 交叉核对
// ═══════════════════════════════════════════════════════════════════════════

describe('显式 scope 与桥实际 scope 交叉核对', () => {
  it('一致时不渲染漂移提示', () => {
    const { wrapper } = makePanel()
    expect(wrapper.find('[data-testid="wp-sync-recovery-scope-drift"]').exists()).toBe(false)
    expect(panelApi(wrapper).getRecoveryState().scopeDrift).toBeNull()
  })

  it('宿主传错底稿 id ⇒ 显式漂移提示 + 停用认领（不静默按错 scope 操作）', async () => {
    const { wrapper } = makePanel({ scope: { ...SCOPE, wpId: UUID(999) } })
    await listOnce(wrapper)
    const drift = wrapper.get('[data-testid="wp-sync-recovery-scope-drift"]')
    expect(drift.text()).toContain('底稿')
    expect(drift.text()).toContain(UUID(999))
    expect(
      wrapper.get(`[data-testid="wp-sync-recovery-claim-${UUID(40)}"]`).attributes('disabled'),
    ).toBeDefined()
  })

  it('宿主传错条目 id ⇒ 同样打红，且漂移原因排在阻断原因首位', async () => {
    const { wrapper } = makePanel({ scope: { ...SCOPE, entryId: 'xlsx/other/entry' } })
    await listOnce(wrapper)
    const reasons = wrapper
      .findAll('[data-testid="wp-sync-recovery-blocking-reason"]')
      .map((el) => el.text())
    expect(reasons[0]).toContain('条目')
    expect(reasons[0]).toContain('恢复动作已停用')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 6. 结构判据
// ═══════════════════════════════════════════════════════════════════════════

describe('结构判据', () => {
  const body = stripComments(
    readFileSync(resolve(__dirname, '..', 'WorkpaperSyncRecoveryPanel.vue'), 'utf-8'),
  )

  it('剥注释后源码里根本不出现 retryOperation（普通重试结构性不可达）', () => {
    expect(body).not.toContain('retryOperation')
    // 反向自检：剥注释确实没把整份源码剥空
    expect(body).toContain('claimRecoveryCase')
    expect(body).toContain('terminateRecoveryDownloadOnly')
  })

  it('面板零 HTTP：不 import 任何请求面', () => {
    for (const forbidden of ['@/utils/http', './workpaperSyncApi', 'axios']) {
      expect(body, forbidden).not.toContain(forbidden)
    }
  })

  it('源码里没有「回写完成」字样（download-only 分支不可能写出它）', () => {
    expect(body).not.toContain('回写完成')
  })

  it('模板属性里没有中文弯引号', () => {
    const template = body.slice(0, body.indexOf('<script'))
    expect(template).not.toContain('\u201c')
    expect(template).not.toContain('\u201d')
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// 7. 零消费方判决（必须放在文件末尾）
// ═══════════════════════════════════════════════════════════════════════════

describe('零消费方判决', () => {
  it('组件声明的 prop 集合逐字等于本文件真正驱动过的集合', () => {
    const declared = Object.keys(
      (WorkpaperSyncRecoveryPanel as unknown as { props: Record<string, unknown> }).props,
    )
    expect(declared.length).toBeGreaterThan(0)
    expect([...EXERCISED_PROPS].sort()).toEqual(declared.sort())
  })

  it('组件声明的 emit 集合逐字等于本文件真正触发过的集合', () => {
    const declared = (WorkpaperSyncRecoveryPanel as unknown as { emits: string[] }).emits
    expect(Array.isArray(declared)).toBe(true)
    expect(declared.length).toBeGreaterThan(0)
    // VTU 把组件内 `trigger()` / `setValue()` 出来的**原生** DOM 事件也记一笔
    // （点按钮 ⇒ click；单选框 setValue ⇒ input + change）。排除表本身参与断言。
    const VTU_NATIVE_ARTEFACTS = ['change', 'click', 'input'] as const
    const artefacts = [...EXERCISED_EMITS].filter((name) =>
      (VTU_NATIVE_ARTEFACTS as readonly string[]).includes(name),
    )
    const triggered = [...EXERCISED_EMITS].filter(
      (name) => !(VTU_NATIVE_ARTEFACTS as readonly string[]).includes(name),
    )
    expect(artefacts.sort()).toEqual([...VTU_NATIVE_ARTEFACTS].sort())
    expect(triggered.sort()).toEqual([...declared].sort())
  })

  it('defineExpose 的只读投影被真的调用过，且与 DOM 一致', async () => {
    const { wrapper } = makePanel()
    await listOnce(wrapper)
    const projection = panelApi(wrapper).getRecoveryState()
    expect(projection.listed).toBe(true)
    expect(projection.caseCount).toBe(1)
    expect(projection.bundleDigest).toBe(DIGEST(3))
    expect(String(projection.caseCount)).toBe(root(wrapper).attributes('data-case-count'))
  })
})
