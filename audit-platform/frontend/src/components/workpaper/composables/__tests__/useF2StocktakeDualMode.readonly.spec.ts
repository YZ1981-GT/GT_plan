/**
 * 监盘 Word 双向同步只读时不做（spec workpaper-multi-window-lock-gaps R3.5）。
 *
 * 切在线编辑前把结构化数据写进 Word、切回时从 Word 写回结构化，都是写操作：只读窗口（编辑锁在别的窗口 / 无编辑权）
 * 原先照发，后端 423 后弹「结构化写入 Word 失败」。只读时不发，在线编辑照常打开（后端按锁给只读配置）。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'

const { post, warning } = vi.hoisted(() => ({ post: vi.fn(), warning: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { post: (...a: unknown[]) => post(...a) } }))
vi.mock('element-plus', () => ({ ElMessage: { warning: (...a: unknown[]) => warning(...a) }, ElMessageBox: { confirm: vi.fn() } }))

import { useF2StocktakeDualMode } from '../useF2StocktakeDualMode'

function setup(readonly: boolean) {
  let api!: ReturnType<typeof useF2StocktakeDualMode>
  const flushPending = vi.fn(async () => {})
  const reloadAll = vi.fn(async () => {})
  mount(defineComponent({
    setup() {
      api = useF2StocktakeDualMode({
        wpId: ref('wp-f2'), projectId: ref('p1'), sheetCode: ref('F2-22'),
        flushPending, reloadAll, readonly: ref(readonly),
      })
      return () => h('div')
    },
  }))
  return { api: () => api, flushPending, reloadAll }
}

beforeEach(() => {
  localStorage.clear()
  post.mockReset().mockResolvedValue({ data: {} })
  warning.mockReset()
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ data: { healthy: true } }) })))
})

afterEach(() => vi.unstubAllGlobals())

describe('useF2StocktakeDualMode 只读', () => {
  it('只读：切在线编辑 / 切回都不发 Word 同步，模式照常切换', async () => {
    const t = setup(true)
    await flushPromises()
    await t.api().switchMode('onlyoffice')
    expect(t.api().currentMode.value).toBe('onlyoffice')
    await t.api().switchMode('html')
    expect(t.api().currentMode.value).toBe('html')
    expect(post).not.toHaveBeenCalled()
    expect(warning).not.toHaveBeenCalled()
    expect(t.reloadAll).toHaveBeenCalledTimes(1)
  })

  it('可编辑：照旧切过去写 Word、切回写回结构化（阴性对照）', async () => {
    const t = setup(false)
    await flushPromises()
    await t.api().switchMode('onlyoffice')
    await t.api().switchMode('html')
    expect(post.mock.calls.map((c) => c[0])).toEqual([
      '/api/workpapers/wp-f2/f2-st/plan-sync-to-oo',
      '/api/workpapers/wp-f2/f2-st/plan-sync-from-oo',
    ])
  })
})
