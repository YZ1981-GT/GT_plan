import { mount } from '@vue/test-utils'
import { defineComponent, h, nextTick, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  display: vi.fn(() => ({ fontConfig: { tableFont: '13px' } })),
  aging: vi.fn(() => ({ segments: ref([]) })),
  version: vi.fn(() => ({ openVersionHistory: vi.fn() })),
  review: vi.fn(() => ({ openReviewDialog: vi.fn() })),
  entry: vi.fn(),
  post: vi.fn(),
}))
vi.mock('@/stores/displayPrefs', () => ({ useDisplayPrefsStore: mocks.display }))
vi.mock('@/composables/useAgingConfig', () => ({ useAgingConfig: mocks.aging }))
vi.mock('../useWorkpaperVersionToolbar', () => ({ useWorkpaperVersionToolbar: mocks.version }))
vi.mock('../useWorkpaperReviewProvide', () => ({ useWorkpaperReviewProvide: mocks.review }))
vi.mock('../useWorkpaperEntryInjections', () => ({ useWorkpaperEntryInjections: mocks.entry }))
vi.mock('@/utils/http', () => ({ default: { post: mocks.post } }))

import {
  extractAiResponseText,
  normalizeAiContext,
  useWorkpaperScaffold,
  type WorkpaperRuntimeContext,
} from '../useWorkpaperScaffold'

const options = (suffix = '') => ({
  wpCode: ref(`J2${suffix}`), wpId: ref(`wp${suffix}`),
  projectId: ref(`project${suffix}`), year: ref(2026),
})

describe('useWorkpaperScaffold', () => {
  beforeEach(() => vi.clearAllMocks())

  it('normalizes every AI context value and unwraps compatible envelopes', () => {
    expect(normalizeAiContext({ n: 12, ok: false, nil: null, obj: { a: 1 } })).toEqual({
      n: '12', ok: 'false', nil: '', obj: '{"a":1}',
    })
    expect(extractAiResponseText({ data: { data: { content: '双层信封' } } })).toBe('双层信封')
    expect(extractAiResponseText({ text: '兼容文本' })).toBe('兼容文本')
  })

  it('reuses the ancestor runtime instead of initializing nested capabilities', () => {
    let parentRuntime: WorkpaperRuntimeContext | undefined
    let childRuntime: WorkpaperRuntimeContext | undefined
    const Child = defineComponent({ setup() { childRuntime = useWorkpaperScaffold(options('-child')); return () => h('span') } })
    const Parent = defineComponent({ setup() { parentRuntime = useWorkpaperScaffold(options()); return () => h(Child) } })

    const wrapper = mount(Parent)
    expect(childRuntime).toBe(parentRuntime)
    expect(mocks.display).toHaveBeenCalledTimes(1)
    expect(mocks.aging).toHaveBeenCalledTimes(1)
    expect(mocks.version).toHaveBeenCalledTimes(1)
    expect(mocks.review).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('sends string-only AI context and supports a doubly wrapped response', async () => {
    let runtime: WorkpaperRuntimeContext | undefined
    mocks.post.mockResolvedValue({ data: { data: { data: { content: '生成结果' } } } })
    const Host = defineComponent({ setup() { runtime = useWorkpaperScaffold(options()); return () => h('div') } })
    const wrapper = mount(Host)

    const result = await runtime!.generateAiText({
      section: 'audit-note', context: { amount: 100, valid: true, rows: [1, 2] }, existingContent: '原文',
    })
    expect(result).toBe('生成结果')
    expect(mocks.post).toHaveBeenCalledWith(
      '/api/workpapers/wp/ai/generate-text',
      expect.objectContaining({
        section: 'audit-note', existingContent: '原文',
        context: { amount: '100', valid: 'true', rows: '[1,2]' },
      }),
      expect.any(Object),
    )
    wrapper.unmount()
  })

  // ─── applicable-standards-runtime-and-sync-guard Property 1 / 2 ───────────

  it('exposes normalized applicableStandards for every input shape (Property 1)', async () => {
    const source = ref<unknown>(undefined)
    let runtime: WorkpaperRuntimeContext | undefined
    const Host = defineComponent({
      setup() {
        runtime = useWorkpaperScaffold({ ...options(), applicableStandards: source })
        return () => h('div')
      },
    })
    const wrapper = mount(Host)

    // 未传 / undefined → [] 而非 undefined（各循环「空 = 全部适用」宽松回退不变）
    expect(runtime!.applicableStandards.value).toEqual([])

    // render-config 到达后自动更新（响应式，不是一次性快照）
    source.value = ['soe_standalone', 'soe', 'standalone']
    await nextTick()
    expect(runtime!.applicableStandards.value).toEqual(['soe_standalone', 'soe', 'standalone'])

    // v2 对象（历史 I1~I6 下发形态）与逗号串都能归一
    source.value = { entity_type: 'listed', scope: 'standalone', stage: 'ipo' }
    await nextTick()
    expect(runtime!.applicableStandards.value).toEqual(['listed_standalone', 'listed', 'standalone'])

    source.value = 'soe, listed'
    await nextTick()
    expect(runtime!.applicableStandards.value).toEqual(['soe', 'listed'])

    wrapper.unmount()
  })

  it('nested scaffold shares the ancestor applicableStandards ref (Property 2)', () => {
    let parentRuntime: WorkpaperRuntimeContext | undefined
    let childRuntime: WorkpaperRuntimeContext | undefined
    const Child = defineComponent({
      setup() {
        childRuntime = useWorkpaperScaffold({
          ...options('-child'),
          applicableStandards: ['private'],
        })
        return () => h('span')
      },
    })
    const Parent = defineComponent({
      setup() {
        parentRuntime = useWorkpaperScaffold({
          ...options(),
          applicableStandards: ['soe_standalone'],
        })
        return () => h(Child)
      },
    })
    const wrapper = mount(Parent)

    expect(childRuntime!.applicableStandards).toBe(parentRuntime!.applicableStandards)
    expect(childRuntime!.applicableStandards.value).toEqual(['soe_standalone'])
    wrapper.unmount()
  })

  it('defers missing-context diagnostics until an async renderer context is ready', async () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const contextReady = ref(false)
    const Host = defineComponent({
      setup() {
        useWorkpaperScaffold({
          wpCode: ref(''),
          wpId: ref('wp-loading'),
          projectId: ref(''),
          year: ref(2026),
          contextReady,
        })
        return () => h('div')
      },
    })
    const wrapper = mount(Host)

    expect(errorSpy).not.toHaveBeenCalled()
    contextReady.value = true
    await nextTick()
    expect(errorSpy).toHaveBeenCalledWith(
      '[WorkpaperRuntime] 缺少必要上下文：wpCode, projectId',
    )

    wrapper.unmount()
    errorSpy.mockRestore()
  })
})