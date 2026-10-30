/**
 * 采纳成功发 `ai-content:adopted`（spec ai-content-pending-target-label）。
 *
 * 待确认横幅 AiContentPendingBanner 监听这个事件重拉计数；2026-10-21 起横幅的用例就在等这个事件，
 * 但两个采纳实现（usePlatformAiChat / useDocAiChat）从没发过 ⇒ 采纳后横幅停在旧计数。
 * 这里钉住：成功才发、带宿主项目；失败 / 没有项目不发。
 */
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({ token: 'test-token', user: { id: 'user-1' } }),
}))

import { buildWorkpaperHost, type AiHostRequest } from '../useAiHostContext'
import { useDocAiChat } from '../useDocAiChat'
import { usePlatformAiChat } from '../usePlatformAiChat'
import { eventBus } from '@/utils/eventBus'

const PROJECT = '11111111-1111-4111-8111-111111111111'
const WP = '22222222-2222-4222-8222-222222222222'
const MSG = '33333333-3333-4333-8333-333333333333'

const mockFetch = vi.fn()

function host(): AiHostRequest {
  return buildWorkpaperHost({ wpId: WP, projectId: PROJECT, auditYear: 2025 })
}

type Adopt = (id: string) => Promise<{ success: boolean }>

/** usePlatformAiChat 里有 onBeforeUnmount，放进一个组件里调用 */
function platformAdopt(): Adopt {
  let adopt: Adopt | null = null
  mount(defineComponent({
    setup() {
      adopt = usePlatformAiChat({ host: host() }).adoptContent
      return () => h('div')
    },
  }))
  return adopt!
}

function docAdopt(): Adopt {
  localStorage.setItem(
    `doc_ai_chat_workpaper_${WP}`,
    JSON.stringify([{ id: MSG, role: 'assistant', text: 'AI 起草', citations: [] }]),
  )
  return useDocAiChat({ host: host() }).adoptContent
}

describe.each([
  ['usePlatformAiChat', platformAdopt],
  ['useDocAiChat', docAdopt],
])('%s.adoptContent → ai-content:adopted', (_name, make) => {
  const heard: unknown[] = []
  const listener = (p: unknown) => heard.push(p)

  beforeEach(() => {
    setActivePinia(createPinia())
    heard.length = 0
    mockFetch.mockReset()
    vi.stubGlobal('fetch', mockFetch)
    eventBus.on('ai-content:adopted', listener)
  })

  afterEach(() => {
    eventBus.off('ai-content:adopted', listener)
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('采纳成功：发一次，带宿主项目', async () => {
    mockFetch.mockResolvedValue({ ok: true, json: async () => ({}) })
    const result = await make()(MSG)
    expect(result.success).toBe(true)
    expect(mockFetch).toHaveBeenCalledWith('/api/ai-chat/adopt', expect.objectContaining({ method: 'POST' }))
    expect(heard).toEqual([{ projectId: PROJECT }])
  })

  it('采纳失败：不发', async () => {
    mockFetch.mockResolvedValue({ ok: false, status: 409, json: async () => ({ detail: { code: 'x' } }) })
    const result = await make()(MSG)
    expect(result.success).toBe(false)
    expect(heard).toEqual([])
  })
})
