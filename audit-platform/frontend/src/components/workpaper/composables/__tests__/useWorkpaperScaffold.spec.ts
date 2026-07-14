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