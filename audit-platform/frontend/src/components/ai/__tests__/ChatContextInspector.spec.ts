/**
 * ChatContextInspector — Task 15 vitest 守卫
 *
 * 验证：
 * 1. (Property 12) manifest 各 decision 状态正确渲染
 * 2. (Req 5.7) manifest 展示 included/trimmed/denied/unavailable + version + stale
 * 3. (Req 5.9) jump_route 点击触发 router.push（目标页面再次鉴权）
 * 4. trimmed 项目可见（非隐藏）
 * 5. 预算 bar 正确计算
 *
 * Feature: dsh-agent-panel-integration / Task 15
 * Validates: Requirements 5.7, 5.9
 * Properties: 12, 13
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import type { ContextManifestItem } from '@/components/ai/ChatContextInspector.vue'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockPush = vi.fn()
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockPush }),
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 'test-token' }),
}))

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeManifest(overrides: Partial<ContextManifestItem>[] = []): ContextManifestItem[] {
  const defaults: ContextManifestItem[] = [
    {
      source_type: 'workpaper',
      source_id: 'wp1',
      label: '审定表 D2-1',
      decision: 'included',
      reason_code: null,
      token_estimate: 500,
      version: '3',
      is_stale: false,
      jump_route: '/workpaper/wp1',
    },
    {
      source_type: 'note',
      source_id: 'n1',
      label: '应收账款附注',
      decision: 'trimmed',
      reason_code: 'budget_exceeded',
      token_estimate: 300,
      version: '2',
      is_stale: false,
      jump_route: '/note/n1',
    },
    {
      source_type: 'knowledge_doc',
      source_id: 'kd1',
      label: '审计准则汇编',
      decision: 'denied',
      reason_code: 'access_denied',
      token_estimate: 0,
      version: null,
      is_stale: false,
      jump_route: '/knowledge/kd1',
    },
    {
      source_type: 'address',
      source_id: 'addr1',
      label: '应收账款/坏账准备',
      decision: 'unavailable',
      reason_code: 'embedding_unavailable',
      token_estimate: 0,
      version: '1',
      is_stale: true,
      jump_route: null,
    },
  ]
  return defaults.map((d, i) => ({ ...d, ...(overrides[i] || {}) }))
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ChatContextInspector', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockPush.mockReset()
  })

  it('Req 5.7: renders all four decision states', async () => {
    const ChatContextInspector = (await import('@/components/ai/ChatContextInspector.vue')).default

    const wrapper = mount(ChatContextInspector, {
      props: { manifest: makeManifest(), tokenBudget: 2000 },
      global: { plugins: [createPinia()] },
    })

    // 展开面板
    await wrapper.find('button').trigger('click')

    const items = wrapper.findAll('.chat-context-inspector__item')
    expect(items.length).toBe(4)

    // 验证各 decision class
    expect(items[0].classes()).toContain('is-included')
    expect(items[1].classes()).toContain('is-trimmed')
    expect(items[2].classes()).toContain('is-denied')
    expect(items[3].classes()).toContain('is-unavailable')
  })

  it('Req 5.7: trimmed item is visible (not hidden)', async () => {
    const ChatContextInspector = (await import('@/components/ai/ChatContextInspector.vue')).default

    const wrapper = mount(ChatContextInspector, {
      props: { manifest: makeManifest() },
      global: { plugins: [createPinia()] },
    })

    await wrapper.find('button').trigger('click')

    const trimmedItem = wrapper.find('.chat-context-inspector__item.is-trimmed')
    expect(trimmedItem.exists()).toBe(true)
    expect(trimmedItem.isVisible()).toBe(true)
    expect(trimmedItem.text()).toContain('应收账款附注')
  })

  it('Req 5.7: displays version and stale tag', async () => {
    const ChatContextInspector = (await import('@/components/ai/ChatContextInspector.vue')).default

    const wrapper = mount(ChatContextInspector, {
      props: { manifest: makeManifest() },
      global: { plugins: [createPinia()] },
    })

    await wrapper.find('button').trigger('click')

    // 第1项有 version 但非 stale
    const firstItem = wrapper.findAll('.chat-context-inspector__item')[0]
    expect(firstItem.text()).toContain('v3')
    expect(firstItem.text()).not.toContain('已过期')

    // 第4项有 stale tag
    const staleItem = wrapper.findAll('.chat-context-inspector__item')[3]
    expect(staleItem.text()).toContain('已过期')
  })

  it('Req 5.7: reason_code is displayed for non-included items', async () => {
    const ChatContextInspector = (await import('@/components/ai/ChatContextInspector.vue')).default

    const wrapper = mount(ChatContextInspector, {
      props: { manifest: makeManifest() },
      global: { plugins: [createPinia()] },
    })

    await wrapper.find('button').trigger('click')

    // trimmed: budget_exceeded
    const trimmedItem = wrapper.findAll('.chat-context-inspector__item')[1]
    expect(trimmedItem.text()).toContain('Token 预算不足')

    // denied: access_denied
    const deniedItem = wrapper.findAll('.chat-context-inspector__item')[2]
    expect(deniedItem.text()).toContain('无访问权限')

    // unavailable: embedding_unavailable
    const unavailableItem = wrapper.findAll('.chat-context-inspector__item')[3]
    expect(unavailableItem.text()).toContain('语义服务不可用')
  })

  it('Req 5.9: jump_route click calls router.push', async () => {
    const ChatContextInspector = (await import('@/components/ai/ChatContextInspector.vue')).default

    const wrapper = mount(ChatContextInspector, {
      props: { manifest: makeManifest() },
      global: { plugins: [createPinia()] },
    })

    await wrapper.find('button').trigger('click')

    // 第1项有 jump_route
    const jumpBtn = wrapper.findAll('.chat-context-inspector__jump')[0]
    expect(jumpBtn.exists()).toBe(true)
    await jumpBtn.trigger('click')

    expect(mockPush).toHaveBeenCalledWith('/workpaper/wp1')
  })

  it('Req 5.9: no jump button when jump_route is null', async () => {
    const ChatContextInspector = (await import('@/components/ai/ChatContextInspector.vue')).default

    const wrapper = mount(ChatContextInspector, {
      props: { manifest: makeManifest() },
      global: { plugins: [createPinia()] },
    })

    await wrapper.find('button').trigger('click')

    // 第4项 jump_route=null，不应有跳转按钮
    const items = wrapper.findAll('.chat-context-inspector__item')
    const lastItem = items[3]
    expect(lastItem.find('.chat-context-inspector__jump').exists()).toBe(false)
  })

  it('Property 12: budget bar calculates correctly', async () => {
    const ChatContextInspector = (await import('@/components/ai/ChatContextInspector.vue')).default

    const wrapper = mount(ChatContextInspector, {
      props: { manifest: makeManifest(), tokenBudget: 2000 },
      global: { plugins: [createPinia()] },
    })

    await wrapper.find('button').trigger('click')

    // included(500) + trimmed(300) = 800 / 2000 = 40%
    const budgetBar = wrapper.find('.chat-context-inspector__budget')
    expect(budgetBar.exists()).toBe(true)
    expect(budgetBar.text()).toContain('800')
    expect(budgetBar.text()).toContain('2000')

    const fill = wrapper.find('.chat-context-inspector__budget-fill')
    expect(fill.attributes('style')).toContain('40%')
  })

  it('summary shows correct counts', async () => {
    const ChatContextInspector = (await import('@/components/ai/ChatContextInspector.vue')).default

    const wrapper = mount(ChatContextInspector, {
      props: { manifest: makeManifest() },
      global: { plugins: [createPinia()] },
    })

    // 摘要在折叠状态也可见
    expect(wrapper.text()).toContain('1 项纳入')
    expect(wrapper.text()).toContain('1 项裁剪')
    expect(wrapper.text()).toContain('1 项拒绝')
    expect(wrapper.text()).toContain('1 项不可用')
  })

  it('empty manifest shows placeholder', async () => {
    const ChatContextInspector = (await import('@/components/ai/ChatContextInspector.vue')).default

    const wrapper = mount(ChatContextInspector, {
      props: { manifest: [] },
      global: { plugins: [createPinia()] },
    })

    await wrapper.find('button').trigger('click')

    expect(wrapper.text()).toContain('暂无上下文信息')
  })

  it('a11y: toggle button has aria-expanded', async () => {
    const ChatContextInspector = (await import('@/components/ai/ChatContextInspector.vue')).default

    const wrapper = mount(ChatContextInspector, {
      props: { manifest: makeManifest() },
      global: { plugins: [createPinia()] },
    })

    const toggle = wrapper.find('button')
    expect(toggle.attributes('aria-expanded')).toBe('false')

    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('true')
  })
})
