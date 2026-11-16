/**
 * 共享持久化适配器 → AI 面板草稿源（spec chat-host-draft-overlay / Task 4）。
 *
 * 这一层是「HTML 底稿宿主的未保存内容」的唯一登记点：160+ 个宿主里已经统一走
 * `useChecklistPersistence` 的那些由本适配器一处 `publishHtmlDraftSource` 覆盖，
 * 不需要逐个改宿主。判据因此盯三件事：
 *
 * 1. **真源就是 `pending`**：`saveDebounced` / `save` 一写就进，落库成功才出 ——
 *    不另建 dirty 标记（否则两套标记迟早不一致）；
 * 2. **只报未保存的条目**：已落库的内容服务端自己读得到，重复纳入既浪费 token
 *    又让模型看到「同一格的两个值」；
 * 3. **逐字稳定**：同一份未保存状态两次取值必须相同（服务端按 sha256 判重）。
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn(), put: vi.fn() },
}))

import { api } from '@/services/apiProxy'
import { useChecklistPersistence } from '../useChecklistPersistence'
import {
  clearHtmlDraftSources,
  clearWorkpaperDraftAccessors,
  readHtmlDraft,
} from '../workpaperDraftOverlay'

const WP_ID = '11111111-1111-4111-8111-111111111111'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => { resolve = res })
  return { promise, resolve }
}

function mountPersistence() {
  const scope = effectScope()
  let persistence!: ReturnType<typeof useChecklistPersistence>
  scope.run(() => {
    persistence = useChecklistPersistence({ wpId: ref(WP_ID) })
  })
  return { persistence, scope }
}

afterEach(() => {
  vi.useRealTimers()
  vi.clearAllMocks()
  clearHtmlDraftSources()
  clearWorkpaperDraftAccessors()
})

describe('useChecklistPersistence — 向 AI 面板登记未保存草稿', () => {
  it('没有未保存修改时不报（hydrate 后干净）', () => {
    const { persistence, scope } = mountPersistence()
    persistence.hydrate([{ item_id: 'K1-1', remark: '100', conclusion: null, version: 'v1' }])
    expect(readHtmlDraft(WP_ID)).toEqual({ content: null, hasUnsaved: false })
    scope.stop()
  })

  it('改一格不保存 → 有草稿；保存成功 → 回到 null（任务验收判据）', async () => {
    vi.useFakeTimers()
    const hold = deferred<unknown>()
    vi.mocked(api.put).mockReturnValue(hold.promise as never)
    const { persistence, scope } = mountPersistence()
    persistence.hydrate([{ item_id: 'K1-1', remark: '100', conclusion: null, version: 'v1' }])

    // 改一处（防抖窗口内）
    persistence.saveDebounced('K1-1', { remark: '1200000' })
    const dirty = readHtmlDraft(WP_ID)
    expect(dirty.hasUnsaved).toBe(true)
    expect(dirty.content).toContain('1200000')
    expect(dirty.content).toContain('K1-1')

    // 落库成功 ⇒ pending 清空
    hold.resolve({
      data: [{ item_id: 'K1-1', remark: '1200000', conclusion: null, wp_ref: null, version: 'v2' }],
    })
    await vi.runAllTimersAsync()
    expect(readHtmlDraft(WP_ID)).toEqual({ content: null, hasUnsaved: false })
    scope.stop()
  })

  it('只报未保存的条目：已保存的格不进草稿（不重复纳入已落库内容）', async () => {
    vi.useFakeTimers()
    vi.mocked(api.put).mockResolvedValue({
      data: [{ item_id: 'K1-2', remark: '200', conclusion: null, wp_ref: null, version: 'v2' }],
    } as never)
    const { persistence, scope } = mountPersistence()
    persistence.hydrate([
      { item_id: 'K1-1', remark: '100', conclusion: null, version: 'v1' },
      { item_id: 'K1-2', remark: '200', conclusion: null, version: 'v1' },
    ])

    persistence.saveDebounced('K1-2', { remark: '200' })
    const draft = readHtmlDraft(WP_ID)
    expect(draft.hasUnsaved).toBe(true)
    // 只有被改过的那一条（K1-1 已落库且没改 ⇒ 不该出现）
    expect(draft.content).toContain('K1-2')
    expect(draft.content).not.toContain('K1-1')

    await vi.runAllTimersAsync()
    expect(readHtmlDraft(WP_ID).hasUnsaved).toBe(false)
    scope.stop()
  })

  it('同一份未保存状态两次取值逐字相同（服务端按 sha256 判重）', async () => {
    vi.useFakeTimers()
    const hold = deferred<unknown>()
    vi.mocked(api.put).mockReturnValue(hold.promise as never)
    const { persistence, scope } = mountPersistence()
    persistence.hydrate([
      { item_id: 'K1-9', remark: 'b', conclusion: null, version: 'v1' },
      { item_id: 'K1-1', remark: 'a', conclusion: null, version: 'v1' },
    ])

    // 故意逆序改，验证按 item_id 排序（Map 迭代顺序会跟着写入顺序变）
    persistence.saveDebounced('K1-9', { remark: 'b2' })
    persistence.saveDebounced('K1-1', { remark: 'a2' })
    const first = readHtmlDraft(WP_ID).content
    const second = readHtmlDraft(WP_ID).content
    expect(first).toBe(second)
    // 排序后 K1-1 在 K1-9 之前
    expect(first!.indexOf('K1-1')).toBeLessThan(first!.indexOf('K1-9'))

    hold.resolve({ data: [] })
    await vi.runAllTimersAsync()
    scope.stop()
  })

  it('保存失败时仍算未保存（不能把没落库的内容说成已保存）', async () => {
    vi.useFakeTimers()
    vi.mocked(api.put).mockRejectedValue({ response: { status: 500 } } as never)
    const { persistence, scope } = mountPersistence()
    persistence.hydrate([{ item_id: 'K1-1', remark: '100', conclusion: null, version: 'v1' }])

    persistence.saveDebounced('K1-1', { remark: '999' })
    await vi.runAllTimersAsync()
    expect(readHtmlDraft(WP_ID).hasUnsaved).toBe(true)
    expect(readHtmlDraft(WP_ID).content).toContain('999')
    scope.stop()
  })

  it('cancel 丢弃本地修改后回到「无未保存」', async () => {
    vi.useFakeTimers()
    const hold = deferred<unknown>()
    vi.mocked(api.put).mockReturnValue(hold.promise as never)
    const { persistence, scope } = mountPersistence()
    persistence.hydrate([{ item_id: 'K1-1', remark: '100', conclusion: null, version: 'v1' }])

    persistence.saveDebounced('K1-1', { remark: '777' })
    expect(readHtmlDraft(WP_ID).hasUnsaved).toBe(true)
    persistence.cancel('K1-1')
    expect(readHtmlDraft(WP_ID).hasUnsaved).toBe(false)
    hold.resolve({ data: [] })
    await vi.runAllTimersAsync()
    scope.stop()
  })

  it('scope 停止后注销草稿源（换底稿 / 离页不留悬挂登记）', () => {
    const { persistence, scope } = mountPersistence()
    persistence.hydrate([{ item_id: 'K1-1', remark: '100', conclusion: null, version: 'v1' }])
    persistence.saveDebounced('K1-1', { remark: '888' })
    expect(readHtmlDraft(WP_ID).hasUnsaved).toBe(true)
    scope.stop()
    expect(readHtmlDraft(WP_ID)).toEqual({ content: null, hasUnsaved: false })
  })
})
