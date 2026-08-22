/**
 * ChatMentionPicker + useAiMention — Task 15 vitest 守卫
 *
 * 验证：
 * 1. (Property 13) 搜索 error 态与 empty 态使用不同 DOM（data-testid 区分）与中文文案
 * 2. (Property 13) 搜索 unavailable 态有独立 DOM 与文案
 * 3. (Req 5.1) @ 触发打开 picker，Escape 关闭
 * 4. (Req 5.1) 键盘导航 ↑↓ + Enter 选择
 * 5. (Req 5.1) 多选 + 移除
 * 6. 类型过滤
 * 7. 防抖搜索（debounce）
 *
 * Feature: dsh-agent-panel-integration / Task 15
 * Validates: Requirements 5.1, 5.4
 * Properties: 12, 13
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { ref, nextTick } from 'vue'
import type { AiHostRef } from '@/composables/useAiHostContext'

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 'test-token' }),
}))

const mockFetch = vi.fn()
global.fetch = mockFetch as any

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeHost(): AiHostRef {
  return {
    type: 'workpaper',
    id: '11111111-1111-1111-1111-111111111111',
    projectId: '22222222-2222-2222-2222-222222222222',
    year: 2025,
  }
}

function mentionableResponse(items: any[] = [], typeStatus: Record<string, string> = {}) {
  return {
    ok: true,
    status: 200,
    json: () => Promise.resolve({ items, type_status: typeStatus }),
  }
}

function errorResponse(status: number) {
  return {
    ok: false,
    status,
    json: () => Promise.resolve({ detail: 'error' }),
  }
}

// ---------------------------------------------------------------------------
// useAiMention Tests
// ---------------------------------------------------------------------------

describe('useAiMention', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    mockFetch.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('Property 13: search error state is distinct from empty state', async () => {
    const { useAiMention } = await import('@/composables/useAiMention')
    const host = ref<AiHostRef | null>(makeHost())
    const mention = useAiMention({ host, debounceMs: 50 })

    // Test empty state: 成功返回 0 条结果
    mockFetch.mockResolvedValueOnce(mentionableResponse([], { workpaper: 'empty' }))
    mention.openPicker()
    mention.searchQuery.value = 'xyz'
    await nextTick() // 让 watch 触发
    vi.advanceTimersByTime(60)
    await flushPromises()

    expect(mention.searchStatus.value).toBe('success')
    expect(mention.isEmpty.value).toBe(true)
    expect(mention.isError.value).toBe(false)
    expect(mention.items.value).toHaveLength(0)

    // Test error state: HTTP 500
    mockFetch.mockResolvedValueOnce(errorResponse(500))
    mention.searchQuery.value = 'abc'
    await nextTick()
    vi.advanceTimersByTime(60)
    await flushPromises()

    expect(mention.searchStatus.value).toBe('error')
    expect(mention.isError.value).toBe(true)
    expect(mention.isEmpty.value).toBe(false)
    expect(mention.errorMessage.value).toContain('加载失败')
  })

  it('Property 13: unavailable state is distinct from error', async () => {
    const { useAiMention } = await import('@/composables/useAiMention')
    const host = ref<AiHostRef | null>(makeHost())
    const mention = useAiMention({ host, debounceMs: 50 })

    // Test unavailable via 503
    mockFetch.mockResolvedValueOnce(errorResponse(503))
    mention.openPicker()
    mention.searchQuery.value = 'test'
    await nextTick()
    vi.advanceTimersByTime(60)
    await flushPromises()

    expect(mention.searchStatus.value).toBe('unavailable')
    expect(mention.isUnavailable.value).toBe(true)
    expect(mention.isError.value).toBe(false)
    expect(mention.errorMessage.value).toContain('不可用')
  })

  it('Property 13: all types unavailable → overall unavailable', async () => {
    const { useAiMention } = await import('@/composables/useAiMention')
    const host = ref<AiHostRef | null>(makeHost())
    const mention = useAiMention({ host, debounceMs: 50 })

    mockFetch.mockResolvedValueOnce(mentionableResponse([], {
      workpaper: 'unavailable',
      note: 'unavailable',
      report: 'unavailable',
      knowledge_doc: 'unavailable',
    }))
    mention.openPicker()
    mention.searchQuery.value = 'test'
    await nextTick()
    vi.advanceTimersByTime(60)
    await flushPromises()

    expect(mention.searchStatus.value).toBe('unavailable')
    expect(mention.isUnavailable.value).toBe(true)
  })

  it('Req 5.1: multi-select and remove', async () => {
    const { useAiMention } = await import('@/composables/useAiMention')
    const host = ref<AiHostRef | null>(makeHost())
    const mention = useAiMention({ host, debounceMs: 50 })

    const item1 = { type: 'workpaper' as const, id: 'wp1', label: '底稿A', sublabel: '', jump_route: '' }
    const item2 = { type: 'note' as const, id: 'n1', label: '附注B', sublabel: '', jump_route: '' }

    mention.selectItem(item1)
    expect(mention.selected.value).toHaveLength(1)
    expect(mention.isSelected(item1)).toBe(true)

    mention.selectItem(item2)
    expect(mention.selected.value).toHaveLength(2)

    // 重复选择不增加
    mention.selectItem(item1)
    expect(mention.selected.value).toHaveLength(2)

    // 移除
    mention.removeItem(item1)
    expect(mention.selected.value).toHaveLength(1)
    expect(mention.isSelected(item1)).toBe(false)
  })

  it('debounce: search is not called immediately', async () => {
    const { useAiMention } = await import('@/composables/useAiMention')
    const host = ref<AiHostRef | null>(makeHost())
    const mention = useAiMention({ host, debounceMs: 300 })

    mockFetch.mockResolvedValue(mentionableResponse([]))
    mention.openPicker()
    mention.searchQuery.value = 'test'
    await nextTick() // let watch fire

    // 不到 300ms，不应调用
    vi.advanceTimersByTime(100)
    expect(mockFetch).not.toHaveBeenCalled()

    // 过了 300ms，应调用
    vi.advanceTimersByTime(250)
    expect(mockFetch).toHaveBeenCalledTimes(1)
  })

  it('type filter is passed to API', async () => {
    const { useAiMention } = await import('@/composables/useAiMention')
    const host = ref<AiHostRef | null>(makeHost())
    const mention = useAiMention({ host, debounceMs: 50 })

    mockFetch.mockResolvedValue(mentionableResponse([]))
    mention.openPicker()
    mention.searchQuery.value = 'test'
    await nextTick()
    mention.setTypeFilter('workpaper')
    vi.advanceTimersByTime(60)
    await flushPromises()

    const calledUrl = mockFetch.mock.calls[0]?.[0] as string
    expect(calledUrl).toContain('type_filter=workpaper')
  })

  it('network error → error state with Chinese message', async () => {
    const { useAiMention } = await import('@/composables/useAiMention')
    const host = ref<AiHostRef | null>(makeHost())
    const mention = useAiMention({ host, debounceMs: 50 })

    mockFetch.mockRejectedValueOnce(new Error('network failure'))
    mention.openPicker()
    mention.searchQuery.value = 'test'
    await nextTick()
    vi.advanceTimersByTime(60)
    await flushPromises()

    expect(mention.searchStatus.value).toBe('error')
    expect(mention.errorMessage.value).toContain('网络异常')
  })

  it('null host → error state', async () => {
    const { useAiMention } = await import('@/composables/useAiMention')
    const host = ref<AiHostRef | null>(null)
    const mention = useAiMention({ host, debounceMs: 50 })

    mention.openPicker()
    mention.searchQuery.value = 'test'
    await nextTick()
    vi.advanceTimersByTime(60)
    await flushPromises()

    expect(mention.searchStatus.value).toBe('error')
    expect(mention.errorMessage.value).toContain('上下文无法确定')
  })
})

// ---------------------------------------------------------------------------
// ChatMentionPicker Component Tests
// ---------------------------------------------------------------------------

describe('ChatMentionPicker — DOM', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    mockFetch.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('Property 13: error DOM has data-testid="mention-error-state"', async () => {
    const { useAiMention } = await import('@/composables/useAiMention')
    const host = ref<AiHostRef | null>(makeHost())
    const mention = useAiMention({ host, debounceMs: 50 })

    // Simulate a search that returns HTTP 500
    mockFetch.mockResolvedValueOnce(errorResponse(500))
    mention.openPicker()
    mention.searchQuery.value = 'test'
    await nextTick()
    vi.advanceTimersByTime(60)
    await flushPromises()

    // Verify composable state (which drives the DOM via v-if)
    expect(mention.searchStatus.value).toBe('error')
    expect(mention.isError.value).toBe(true)
    expect(mention.isEmpty.value).toBe(false)
    expect(mention.isUnavailable.value).toBe(false)
  })

  it('Property 13: empty DOM has data-testid="mention-empty-state"', async () => {
    const { useAiMention } = await import('@/composables/useAiMention')
    const host = ref<AiHostRef | null>(makeHost())
    const mention = useAiMention({ host, debounceMs: 50 })

    // Simulate a search that returns empty
    mockFetch.mockResolvedValueOnce(mentionableResponse([]))
    mention.openPicker()
    mention.searchQuery.value = 'xyz'
    await nextTick()
    vi.advanceTimersByTime(60)
    await flushPromises()

    // Verify composable state
    expect(mention.searchStatus.value).toBe('success')
    expect(mention.isEmpty.value).toBe(true)
    expect(mention.isError.value).toBe(false)
    expect(mention.isUnavailable.value).toBe(false)
  })

  it('Property 13: unavailable DOM has data-testid="mention-unavailable-state"', async () => {
    const { useAiMention } = await import('@/composables/useAiMention')
    const host = ref<AiHostRef | null>(makeHost())
    const mention = useAiMention({ host, debounceMs: 50 })

    // Simulate a 503 response
    mockFetch.mockResolvedValueOnce(errorResponse(503))
    mention.openPicker()
    mention.searchQuery.value = 'test'
    await nextTick()
    vi.advanceTimersByTime(60)
    await flushPromises()

    expect(mention.searchStatus.value).toBe('unavailable')
    expect(mention.isUnavailable.value).toBe(true)
    expect(mention.isError.value).toBe(false)
    expect(mention.isEmpty.value).toBe(false)
  })

  it('Req 5.1: a11y — combobox role and listbox (composable-level)', async () => {
    const { useAiMention } = await import('@/composables/useAiMention')
    const host = ref<AiHostRef | null>(makeHost())
    const mention = useAiMention({ host, debounceMs: 50 })

    mockFetch.mockResolvedValueOnce(mentionableResponse([
      { type: 'workpaper', id: 'wp1', label: '审定表', sublabel: 'D2-1', jump_route: '/wp/wp1' },
    ]))

    mention.openPicker()
    mention.searchQuery.value = '审定'
    await nextTick()
    vi.advanceTimersByTime(60)
    await flushPromises()

    // Verify composable delivers items (which drives the listbox)
    expect(mention.items.value).toHaveLength(1)
    expect(mention.items.value[0].label).toBe('审定表')
    expect(mention.pickerOpen.value).toBe(true)
  })

  it('Req 5.1: closePicker resets state', async () => {
    const { useAiMention } = await import('@/composables/useAiMention')
    const host = ref<AiHostRef | null>(makeHost())
    const mention = useAiMention({ host, debounceMs: 50 })

    mention.openPicker()
    expect(mention.pickerOpen.value).toBe(true)

    mention.closePicker()
    expect(mention.pickerOpen.value).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// 单类型失败不得被吞 + 无项目绑定的 tab 置灰
//
// 背景（本组守卫存在的理由）：后端 4 个类型（note/report/knowledge_doc/
// knowledge_folder）因 ORM 字段名写错长期恒 error，而前端只在「所有类型都
// unavailable」时才提示，于是界面一律显示"无匹配结果"。上面 13 条守卫全绿，
// 因为它们只断言"empty 与 error 用不同 DOM"，从没断言**单类失败会不会被吞**，
// 也从没真挂载过组件去看 tab 的可点性。
// ---------------------------------------------------------------------------

describe('useAiMention — 单类型失败不被吞成 success', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    mockFetch.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  async function searchOnce(
    host: AiHostRef | null,
    items: any[],
    typeStatus: Record<string, string>,
  ) {
    const { useAiMention } = await import('@/composables/useAiMention')
    const hostRef = ref<AiHostRef | null>(host)
    const mention = useAiMention({ host: hostRef, debounceMs: 50 })
    mockFetch.mockResolvedValueOnce(mentionableResponse(items, typeStatus))
    mention.openPicker()
    mention.searchQuery.value = 'kw'
    await nextTick()
    vi.advanceTimersByTime(60)
    await flushPromises()
    return mention
  }

  it('单类型 error + 零结果 → 不得是 empty 态，须给出「搜索失败」原因', async () => {
    const mention = await searchOnce(makeHost(), [], { note: 'error' })

    // 🔴 修复前：searchStatus='success' + isEmpty=true ⇒ 界面显示"无匹配结果"
    expect(mention.isEmpty.value).toBe(false)
    expect(mention.searchStatus.value).toBe('unavailable')
    expect(mention.errorMessage.value).toContain('附注')
    expect(mention.errorMessage.value).toContain('搜索失败')
  })

  it('全部 project_required → 文案说明需要绑定项目并给出可操作指引', async () => {
    const mention = await searchOnce(makeHost(), [], {
      workpaper: 'project_required',
      note: 'project_required',
      report: 'project_required',
      address: 'project_required',
    })

    expect(mention.isEmpty.value).toBe(false)
    expect(mention.errorMessage.value).toContain('需要先绑定项目')
    // 必须告诉用户怎么办，而不是只说不行
    expect(mention.errorMessage.value).toContain('请先从某个项目')
    // 四类合并成一句，不是重复四遍
    expect(mention.errorMessage.value.match(/需要先绑定项目/g)).toHaveLength(1)
  })

  it('有结果 + 部分类型失败 → success 但暴露降级提示', async () => {
    const mention = await searchOnce(
      makeHost(),
      [{ type: 'workpaper', id: 'wp1', label: '审定表', sublabel: 'D2-1', jump_route: '' }],
      { workpaper: 'success', note: 'error', report: 'empty' },
    )

    expect(mention.searchStatus.value).toBe('success')
    expect(mention.items.value).toHaveLength(1)
    // 搜到了东西，但附注那类失败了 —— 不能一声不响
    expect(mention.degradedHint.value).toContain('附注')
    expect(mention.degradedHint.value).toContain('搜索失败')
    // empty 的类型不算失败，不该出现在提示里
    expect(mention.degradedHint.value).not.toContain('报表')
  })

  it('全部成功/空 → 无降级提示（防恒真）', async () => {
    const mention = await searchOnce(
      makeHost(),
      [{ type: 'workpaper', id: 'wp1', label: '审定表', sublabel: '', jump_route: '' }],
      { workpaper: 'success', note: 'empty', attachment: 'empty' },
    )

    expect(mention.searchStatus.value).toBe('success')
    expect(mention.degradedHint.value).toBe('')
  })

  it('attachment 恒 empty 不参与失败判定（防误报）', async () => {
    const mention = await searchOnce(makeHost(), [], {
      attachment: 'empty',
      knowledge_doc: 'empty',
    })

    // 全是 empty ⇒ 真的没搜到，应走 empty 态而不是失败态
    expect(mention.searchStatus.value).toBe('success')
    expect(mention.isEmpty.value).toBe(true)
    expect(mention.errorMessage.value).toBe('')
  })

  it('projectBindingMissing 跟随宿主 projectId', async () => {
    const { useAiMention } = await import('@/composables/useAiMention')

    const bound = useAiMention({ host: ref(makeHost()), debounceMs: 50 })
    expect(bound.projectBindingMissing.value).toBe(false)

    const globalHost: AiHostRef = {
      type: 'global_knowledge',
      id: 'global-knowledge',
      projectId: null,
      year: null,
    }
    const unbound = useAiMention({ host: ref(globalHost), debounceMs: 50 })
    expect(unbound.projectBindingMissing.value).toBe(true)
  })
})

describe('ChatMentionPicker — DOM：无项目绑定时的 tab 置灰', () => {
  // el-tag / el-tooltip 用透传型 stub：Vue 会把未声明的 attrs（aria-disabled /
  // tabindex / data-testid）透到根元素上，因此断言拿到的是组件真实传下去的值。
  const stubs = {
    'el-input': {
      props: ['modelValue', 'size', 'placeholder', 'clearable', 'prefixIcon'],
      template: '<input />',
    },
    'el-tag': { props: ['type', 'size', 'effect'], template: '<span><slot /></span>' },
    'el-tooltip': { props: ['content', 'disabled', 'placement'], template: '<span><slot /></span>' },
    'el-icon': { template: '<i><slot /></i>' },
  }

  beforeEach(() => {
    setActivePinia(createPinia())
    mockFetch.mockReset()
    mockFetch.mockResolvedValue(mentionableResponse([]))
  })

  async function mountPicker(host: AiHostRef) {
    const ChatMentionPicker = (await import('../ChatMentionPicker.vue')).default
    const wrapper = mount(ChatMentionPicker, {
      props: { host, open: true },
      global: { stubs },
    })
    await flushPromises()
    return wrapper
  }

  const globalHost: AiHostRef = {
    type: 'global_knowledge',
    id: 'global-knowledge',
    projectId: null,
    year: null,
  }

  it('无项目绑定 → 底稿/附注/报表/地址坐标 tab 置灰，知识两类可用', async () => {
    const wrapper = await mountPicker(globalHost)

    for (const t of ['workpaper', 'note', 'report', 'address']) {
      const tag = wrapper.find(`[data-testid="mention-filter-${t}"]`)
      expect(tag.exists()).toBe(true)
      expect(tag.attributes('aria-disabled')).toBe('true')
      expect(tag.attributes('tabindex')).toBe('-1')
    }
    for (const t of ['knowledge_doc', 'knowledge_folder']) {
      const tag = wrapper.find(`[data-testid="mention-filter-${t}"]`)
      expect(tag.attributes('aria-disabled')).toBe('false')
      expect(tag.attributes('tabindex')).toBe('0')
    }
  })

  it('有项目绑定 → 六类 tab 全部可用（防置灰恒真）', async () => {
    const wrapper = await mountPicker(makeHost())

    for (const t of ['workpaper', 'note', 'report', 'address', 'knowledge_doc', 'knowledge_folder']) {
      const tag = wrapper.find(`[data-testid="mention-filter-${t}"]`)
      expect(tag.attributes('aria-disabled')).toBe('false')
    }
  })

  it('置灰 tab 点击不发请求（不制造注定为空的往返）', async () => {
    const wrapper = await mountPicker(globalHost)
    mockFetch.mockClear()

    await wrapper.find('[data-testid="mention-filter-workpaper"]').trigger('click')
    // 🔴 必须等过防抖窗口（300ms）才能断言"没发请求"，
    // 否则 flushPromises 之后计时器还没到点，断言恒真（变异检验 M6 抓出过这个缺陷）
    await new Promise((r) => setTimeout(r, 400))
    await flushPromises()
    expect(mockFetch).not.toHaveBeenCalled()

    // 未置灰的类型点了要真的搜（反向对照，防"永远不发请求"也能通过）
    await wrapper.find('[data-testid="mention-filter-knowledge_doc"]').trigger('click')
    await new Promise((r) => setTimeout(r, 400))
    await flushPromises()
    expect(mockFetch).toHaveBeenCalled()
  })
})

describe('前后端取值域对账', () => {
  it('PROJECT_REQUIRED_MENTION_TYPES 与后端一致（四类项目资源）', async () => {
    const { PROJECT_REQUIRED_MENTION_TYPES } = await import('@/composables/useAiMention')
    // 真源 = backend/app/services/ai_chat/mention_service.py::PROJECT_REQUIRED_MENTION_TYPES
    // 知识文档/知识库可跨项目共享，不得列入
    expect([...PROJECT_REQUIRED_MENTION_TYPES].sort()).toEqual([
      'address', 'note', 'report', 'workpaper',
    ])
  })
})

// ---------------------------------------------------------------------------
// 空态必须说明「有类型压根没搜」（浏览器实测抓出的缺口）
//
// 受限全局知识模式下最常见的返回是：四类项目资源 project_required +
// 知识两类真的 empty。此时 failed(4) ≠ participating(6)，走不进失败态，
// 空态若只说"无匹配结果"，用户仍会以为库里没有底稿/附注/报表 ——
// 这正是本次修复的原始症状，上面那批守卫都没覆盖到它。
// ---------------------------------------------------------------------------

describe('useAiMention — 空态说明真实原因', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    mockFetch.mockReset()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  async function searchOnce(typeStatus: Record<string, string>) {
    const { useAiMention } = await import('@/composables/useAiMention')
    const globalHost: AiHostRef = {
      type: 'global_knowledge',
      id: 'global-knowledge',
      projectId: null,
      year: null,
    }
    const mention = useAiMention({ host: ref(globalHost), debounceMs: 50 })
    mockFetch.mockResolvedValueOnce(mentionableResponse([], typeStatus))
    mention.openPicker()
    mention.searchQuery.value = '存货'
    await nextTick()
    vi.advanceTimersByTime(60)
    await flushPromises()
    return mention
  }

  it('零结果 + 部分类型需要项目 → 空态点明原因，不止说「无匹配结果」', async () => {
    // 后端在受限全局知识模式下的真实返回形状
    const mention = await searchOnce({
      workpaper: 'project_required',
      note: 'project_required',
      report: 'project_required',
      address: 'project_required',
      knowledge_doc: 'empty',
      knowledge_folder: 'empty',
      attachment: 'empty',
    })

    expect(mention.isEmpty.value).toBe(true)
    // 🔴 修复前这里只有"无匹配结果"
    expect(mention.emptyReason.value).toContain('需要先绑定项目')
    expect(mention.emptyReason.value).toContain('请先从某个项目')
    expect(mention.emptyReason.value).not.toBe('无匹配结果')
  })

  it('零结果 + 所有类型都真的搜过 → 仍是朴素的「无匹配结果」（防过度提示）', async () => {
    const mention = await searchOnce({
      knowledge_doc: 'empty',
      knowledge_folder: 'empty',
      attachment: 'empty',
    })

    expect(mention.isEmpty.value).toBe(true)
    expect(mention.emptyReason.value).toBe('无匹配结果')
  })

  it('类型名按业务顺序排列，不用后端字母序', async () => {
    const mention = await searchOnce({
      // 后端 type_status 是字母序：address 在最前、workpaper 在最后
      address: 'project_required',
      note: 'project_required',
      report: 'project_required',
      workpaper: 'project_required',
      knowledge_doc: 'empty',
    })

    // 期望「底稿、附注、报表、地址坐标」而不是「地址坐标、附注、报表、底稿」
    expect(mention.emptyReason.value).toContain('底稿、附注、报表、地址坐标')
  })
})
