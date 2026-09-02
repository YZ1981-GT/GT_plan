// spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 35
//
// 刷新条与编辑器宿主的 **DOM 侧**判据：可见状态、显式动作、以及"接没接上"。
//
// Validates: Requirements 11.9, 11.10, 13.3, 13.4
//
// ═══ 为什么用真协调器 ═══
//
// 一个"形状像协调器"的 plain object 能让任何 DOM 判据通过，却抓不住"组件读错了字段"
// —— 而那正是 Vue 里最贵的静默失效（渲染空串 / 门控恒开）。所以这里构造**真的**
// `useWorkpaperContentRefresh()`，只注入 reload / isDirty / loadedRevision 三个钩子，
// 再用真实事件把它推到各个状态。
import { describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'

vi.mock('@/services/sse/projectEventStream', () => ({
  subscribeProjectEvent: vi.fn(() => ({ close: vi.fn() })),
}))

import WorkpaperSyncContentRefreshBanner from '../WorkpaperSyncContentRefreshBanner.vue'
import WorkpaperSyncEditorHost from '../WorkpaperSyncEditorHost.vue'
import {
  WP_CONTENT_REFRESH_ACTION_HINT,
  WP_CONTENT_REFRESH_STATUS_TEXT,
  WP_CONTENT_UPDATED_EVENT_NAME,
  useWorkpaperContentRefresh,
  type WorkpaperContentRefresh,
} from '../workpaperSyncContentRefresh'
import { descriptorFixture, harness as bridgeHarness, stripComments } from './workpaperSyncUiHarness'

const UUID = (n: number): string => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const DIGEST = (n: number): string =>
  String(n).repeat(2).padEnd(64, 'abc123def0'.repeat(7)).slice(0, 64)

const PROJECT = UUID(101)
const WP = UUID(102)

function payloadFixture(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    wp_id: WP,
    project_id: PROJECT,
    revision: 12,
    operation_id: UUID(30),
    source: 'onlyoffice',
    adapter_id: 'g7.disclosure.listed',
    file_sha256: DIGEST(1),
    entry_id: 'xlsx/g7/disclosure/g7-tab-disclosure-listed',
    content_version_id: UUID(23),
    content_revision_advanced: true,
    reason: 'content_commit',
    ...over,
  }
}

function sseEnvelope(payload = payloadFixture()): Record<string, unknown> {
  return {
    event_type: WP_CONTENT_UPDATED_EVENT_NAME,
    project_id: PROJECT,
    year: null,
    account_codes: null,
    entry_group_id: null,
    batch_id: null,
    extra: payload,
  }
}

interface Fixture {
  refresh: WorkpaperContentRefresh
  reload: ReturnType<typeof vi.fn>
  setDirty: (next: boolean) => void
}

function coordinator(
  options: { dirty?: boolean; loaded?: number | null; reload?: () => Promise<void> } = {},
): Fixture {
  let dirty = options.dirty === true
  const reload = vi.fn(options.reload ?? (async () => {}))
  const refresh = useWorkpaperContentRefresh({
    wpId: ref(WP),
    projectId: ref(PROJECT),
    loadedRevision: () => (options.loaded === undefined ? 11 : options.loaded),
    isDirty: () => dirty,
    reload: reload as unknown as (minimumRevision: number) => Promise<void>,
    subscribe: () => ({ close: vi.fn() }),
  })
  return { refresh, reload, setDirty: (next) => { dirty = next } }
}

function mountBanner(refresh: WorkpaperContentRefresh) {
  return mount(WorkpaperSyncContentRefreshBanner, { props: { refresh } })
}

// ═══════════════════════════════════════════════════════════════════════════
// A. 各状态的可见形态
// ═══════════════════════════════════════════════════════════════════════════

describe('刷新条的可见形态', () => {
  it('idle：显示"尚未收到"，无任何动作按钮', () => {
    const f = coordinator()
    const wrapper = mountBanner(f.refresh)
    expect(wrapper.get('[data-testid="wp-content-refresh"]').attributes('data-status')).toBe('idle')
    expect(wrapper.get('[data-testid="wp-content-refresh-badge"]').text()).toBe(
      WP_CONTENT_REFRESH_STATUS_TEXT.idle,
    )
    expect(wrapper.find('[data-testid="wp-content-refresh-accept"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="wp-content-refresh-retry"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="wp-content-refresh-hint"]').exists()).toBe(false)
  })

  it('synced：success 基调 + 已加载修订号可见', async () => {
    const f = coordinator()
    const wrapper = mountBanner(f.refresh)
    await f.refresh.handleEvent(sseEnvelope())
    await flushPromises()
    const root = wrapper.get('[data-testid="wp-content-refresh"]')
    expect(root.attributes('data-status')).toBe('synced')
    expect(root.attributes('data-kind')).toBe('success')
    expect(wrapper.get('[data-testid="wp-content-refresh-applied"]').text()).toContain('12')
    expect(wrapper.get('[data-testid="wp-content-refresh-pending"]').text()).toContain('—')
    expect(wrapper.get('[data-testid="wp-content-refresh-version"]').text()).toContain(UUID(23))
    expect(wrapper.get('[data-testid="wp-content-refresh-reason"]').text()).toContain(
      'content_commit',
    )
    expect(wrapper.find('[data-testid="wp-content-refresh-failure-code"]').exists()).toBe(false)
  })

  it('deferred_dirty：warning 基调 + 两个显式选择 + 提示逐字来自文案表', async () => {
    const f = coordinator({ dirty: true })
    const wrapper = mountBanner(f.refresh)
    await f.refresh.handleEvent(sseEnvelope(payloadFixture({ revision: 14 })))
    await flushPromises()
    const root = wrapper.get('[data-testid="wp-content-refresh"]')
    expect(root.attributes('data-status')).toBe('deferred_dirty')
    expect(root.attributes('data-kind')).toBe('warning')
    expect(wrapper.get('[data-testid="wp-content-refresh-hint"]').text()).toBe(
      WP_CONTENT_REFRESH_ACTION_HINT.deferred_dirty,
    )
    expect(wrapper.get('[data-testid="wp-content-refresh-pending"]').text()).toContain('14')
    expect(wrapper.find('[data-testid="wp-content-refresh-accept"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="wp-content-refresh-dismiss"]').exists()).toBe(true)
    // 🔴 dirty 暂缓**不是**加载失败，不得出现「重试加载」
    expect(wrapper.find('[data-testid="wp-content-refresh-retry"]').exists()).toBe(false)
    expect(f.reload).not.toHaveBeenCalled()
  })

  it('refresh_failed：error 基调 + 失败码可见 + 只出现「重试加载」', async () => {
    const f = coordinator({ reload: async () => { throw new Error('网络中断') } })
    const wrapper = mountBanner(f.refresh)
    await f.refresh.handleEvent(sseEnvelope())
    await flushPromises()
    const root = wrapper.get('[data-testid="wp-content-refresh"]')
    expect(root.attributes('data-status')).toBe('refresh_failed')
    expect(root.attributes('data-kind')).toBe('error')
    expect(wrapper.get('[data-testid="wp-content-refresh-failure-code"]').text()).toContain(
      'content_refresh_reload_failed',
    )
    expect(wrapper.get('[data-testid="wp-content-refresh-message"]').text()).toContain(
      '已提交的内容未受影响',
    )
    expect(wrapper.find('[data-testid="wp-content-refresh-retry"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="wp-content-refresh-accept"]').exists()).toBe(false)
  })

  it('event_rejected：可见但**不给**重试（重放坏事件只会再坏一次）', async () => {
    const f = coordinator()
    const wrapper = mountBanner(f.refresh)
    await f.refresh.handleEvent(sseEnvelope(payloadFixture({ content_version_id: null })))
    await flushPromises()
    const root = wrapper.get('[data-testid="wp-content-refresh"]')
    expect(root.attributes('data-status')).toBe('event_rejected')
    expect(root.attributes('data-kind')).toBe('error')
    expect(wrapper.get('[data-testid="wp-content-refresh-failure-code"]').text()).toContain(
      'content_event_precommit_shape',
    )
    expect(wrapper.find('[data-testid="wp-content-refresh-retry"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="wp-content-refresh-accept"]').exists()).toBe(false)
    expect(f.reload).not.toHaveBeenCalled()
  })

  it('refreshing：转圈可见，且此时一个动作按钮都不渲染（用户无事可做）', async () => {
    let release: () => void = () => {}
    const f = coordinator({
      dirty: true,
      reload: () => new Promise<void>((resolve) => { release = resolve }),
    })
    const wrapper = mountBanner(f.refresh)
    await f.refresh.handleEvent(sseEnvelope())
    await flushPromises()
    const accepting = f.refresh.acceptPending()
    await flushPromises()
    expect(wrapper.get('[data-testid="wp-content-refresh"]').attributes('data-status')).toBe(
      'refreshing',
    )
    expect(wrapper.find('[data-testid="wp-content-refresh-spinner"]').exists()).toBe(true)
    // 🔴 三个按钮全不在 DOM 里 —— 这是「加载中不可重复点」的**结构**判据。
    // 用 `:disabled` 表达会是一段永不为真的绑定（三个门都与 refreshing 互斥），
    // 而永不为真的绑定的守卫必然恒绿。
    for (const testid of [
      'wp-content-refresh-accept',
      'wp-content-refresh-dismiss',
      'wp-content-refresh-retry',
    ]) {
      expect(wrapper.find(`[data-testid="${testid}"]`).exists()).toBe(false)
    }
    expect(wrapper.find('[data-testid="wp-content-refresh-hint"]').exists()).toBe(false)
    release()
    await accepting
    await flushPromises()
    expect(wrapper.get('[data-testid="wp-content-refresh"]').attributes('data-status')).toBe(
      'synced',
    )
    expect(wrapper.find('[data-testid="wp-content-refresh-spinner"]').exists()).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// B. 动作真的接上了协调器（不是只 emit 了一个事件）
// ═══════════════════════════════════════════════════════════════════════════

describe('动作接线', () => {
  it('点「加载服务端最新版本」→ 真的调 reload，参数是待办 revision', async () => {
    const f = coordinator({ dirty: true })
    const wrapper = mountBanner(f.refresh)
    await f.refresh.handleEvent(sseEnvelope(payloadFixture({ revision: 15 })))
    await flushPromises()
    f.setDirty(false)
    await wrapper.get('[data-testid="wp-content-refresh-accept"]').trigger('click')
    await flushPromises()
    expect(f.reload).toHaveBeenCalledTimes(1)
    expect(f.reload).toHaveBeenCalledWith(15)
    expect(wrapper.emitted('refreshed')).toEqual([[{ status: 'synced', revision: 15 }]])
  })

  it('点「保留本地修改」→ 清待办、不调 reload、emit dismissed', async () => {
    const f = coordinator({ dirty: true })
    const wrapper = mountBanner(f.refresh)
    await f.refresh.handleEvent(sseEnvelope())
    await flushPromises()
    await wrapper.get('[data-testid="wp-content-refresh-dismiss"]').trigger('click')
    await flushPromises()
    expect(f.reload).not.toHaveBeenCalled()
    expect(wrapper.emitted('dismissed')).toEqual([[{ pendingRevision: 12 }]])
    expect(wrapper.get('[data-testid="wp-content-refresh"]').attributes('data-status')).toBe('idle')
  })

  it('点「重试加载」→ 第二次 reload 成功后落 synced', async () => {
    let attempts = 0
    const f = coordinator({
      reload: async () => {
        attempts += 1
        if (attempts === 1) throw new Error('网络中断')
      },
    })
    const wrapper = mountBanner(f.refresh)
    await f.refresh.handleEvent(sseEnvelope())
    await flushPromises()
    await wrapper.get('[data-testid="wp-content-refresh-retry"]').trigger('click')
    await flushPromises()
    expect(attempts).toBe(2)
    expect(wrapper.get('[data-testid="wp-content-refresh"]').attributes('data-status')).toBe(
      'synced',
    )
  })

  it('getPresentation 的每一项都逐字来自协调器或文案表', async () => {
    const f = coordinator({ dirty: true })
    const wrapper = mountBanner(f.refresh)
    await f.refresh.handleEvent(sseEnvelope(payloadFixture({ revision: 16 })))
    await flushPromises()
    const presentation = (
      wrapper.vm as unknown as { getPresentation: () => Record<string, unknown> }
    ).getPresentation()
    expect(presentation).toEqual({
      status: 'deferred_dirty',
      kind: 'warning',
      statusText: WP_CONTENT_REFRESH_STATUS_TEXT.deferred_dirty,
      message: WP_CONTENT_REFRESH_STATUS_TEXT.deferred_dirty,
      hint: WP_CONTENT_REFRESH_ACTION_HINT.deferred_dirty,
      appliedRevision: null,
      pendingRevision: 16,
      failureCode: '',
      acceptVisible: true,
      retryVisible: false,
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// C. 接进编辑器宿主（"接没接上"落在 DOM 上，不是 grep 符号名）
// ═══════════════════════════════════════════════════════════════════════════

describe('编辑器宿主集成', () => {
  function mountHost(contentRefresh: WorkpaperContentRefresh | null) {
    const h = bridgeHarness()
    return {
      h,
      wrapper: mount(WorkpaperSyncEditorHost, {
        props: {
          descriptor: null,
          bridge: h.bridge,
          docsApiLoader: null,
          ...(contentRefresh === null ? {} : { contentRefresh }),
        },
      }),
    }
  }

  it('传了协调器 ⇒ 刷新条真的渲染出来，且渲染的是它自己的状态', async () => {
    const f = coordinator({ dirty: true })
    const { wrapper } = mountHost(f.refresh)
    const banner = wrapper.get('[data-testid="wp-content-refresh"]')
    expect(banner.attributes('data-status')).toBe('idle')
    // 协调器状态推进后宿主里的那份 DOM 也跟着变 ⇒ 真的绑上了同一个实例
    await f.refresh.handleEvent(sseEnvelope())
    await flushPromises()
    expect(wrapper.get('[data-testid="wp-content-refresh"]').attributes('data-status')).toBe(
      'deferred_dirty',
    )
    expect(wrapper.find('[data-testid="wp-content-refresh-accept"]').exists()).toBe(true)
  })

  it('未传协调器 ⇒ 整条不渲染（single_html 等入口的正常形态）', () => {
    const { wrapper } = mountHost(null)
    expect(wrapper.find('[data-testid="wp-content-refresh"]').exists()).toBe(false)
    // 宿主自身其余部分不受影响
    expect(wrapper.find('[data-testid="wp-sync-host-status"]').exists()).toBe(true)
  })

  it('宿主的桥失败与刷新条的失败**互不覆盖**（两件事同时为真是常态）', async () => {
    const f = coordinator({ reload: async () => { throw new Error('网络中断') } })
    const { h, wrapper } = mountHost(f.refresh)
    h.bridge.notifyHostFailure('editor_runtime', new Error('内核异常'))
    await f.refresh.handleEvent(sseEnvelope())
    await flushPromises()
    // 桥侧仍是自己的失败文案
    expect(wrapper.get('[data-testid="wp-sync-host-status"]').attributes('data-kind')).toBe('error')
    expect(wrapper.get('[data-testid="wp-sync-host-status"]').text()).toContain('内核异常')
    // 刷新条侧是自己的失败码，没被桥的文案盖掉
    expect(wrapper.get('[data-testid="wp-content-refresh-failure-code"]').text()).toContain(
      'content_refresh_reload_failed',
    )
  })

  it('宿主与刷新条都不请求任何 config/端点（源码级：零 HTTP 面 import）', async () => {
    const fs = await import('node:fs')
    const path = await import('node:path')
    const dir = path.resolve(__dirname, '..')
    const banner = stripComments(
      fs.readFileSync(path.join(dir, 'WorkpaperSyncContentRefreshBanner.vue'), 'utf-8'),
    )
    const module = stripComments(
      fs.readFileSync(path.join(dir, 'workpaperSyncContentRefresh.ts'), 'utf-8'),
    )
    // 反向自检：剥注释没把 import 段一起剥掉
    expect(banner).toContain("from './workpaperSyncContentRefresh'")
    expect(module).toContain("from '@/services/sse/projectEventStream'")
    for (const source of [banner, module]) {
      for (const forbidden of [
        '@/utils/http',
        '@/services/apiProxy',
        './workpaperSyncApi',
        'fetch(',
      ]) {
        expect(source).not.toContain(forbidden)
      }
    }
  })

  it('descriptor 仍可正常挂载（新增可选 prop 没有改动既有挂载路径）', async () => {
    const f = coordinator()
    const h = bridgeHarness()
    const destroyEditor = vi.fn()
    const DocEditor = vi.fn(() => ({ destroyEditor }))
    const wrapper = mount(WorkpaperSyncEditorHost, {
      props: {
        descriptor: descriptorFixture(),
        bridge: h.bridge,
        docsApiLoader: async () => ({ DocEditor } as never),
        contentRefresh: f.refresh,
      },
    })
    // mode 仍是 html ⇒ 编辑器不挂载，但刷新条在
    expect(wrapper.find('[data-testid="wp-sync-host-editor"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="wp-content-refresh"]').exists()).toBe(true)
    await h.bridge.switchToOnlyOffice()
    await flushPromises()
    await flushPromises()
    expect(DocEditor).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-testid="wp-sync-host-editor"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="wp-content-refresh"]').exists()).toBe(true)
  })
})
