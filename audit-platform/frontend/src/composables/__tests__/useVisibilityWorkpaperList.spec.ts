// Feature: procedure-delegation-visibility-isolation — Task 12（组件 C16 Frontend）
//
// 验证前端可见性列表消费层（useVisibilityWorkpaperList）：
//  - 分页 envelope 消费（Req 11.6/11.13）
//  - 状态拆分 index_status / file_status（Req 12.4/12.5）
//  - 安全占位：404 → "资源不存在或不可访问" + 清缓存，不闪现（Req 12.7）
//  - nullable wp 禁用文件动作（Req 12.8/12.9）
//  - visibility_mode / 客户端身份仅 UX，不改变授权（Req 12.1–12.3 / Property 15）
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import * as fc from 'fast-check'
import { useVisibilityWorkpaperList } from '../useVisibilityWorkpaperList'
import type { WpListEnvelope, VisibilityWpItem } from '@/services/workpaperApi'

function mkItem(over: Partial<VisibilityWpItem> = {}): VisibilityWpItem {
  return {
    wp_index_id: 'wi-1', project_id: 'p1', wp_id: 'wp-1', wp_code: 'D2-1',
    wp_name: '应收账款审定表', audit_cycle: 'D', index_status: 'in_progress',
    file_status: 'draft', review_status: 'not_submitted', assigned_to: 'u1',
    reviewer: null, file_version: 1, file_path: '/x', source_type: 'template',
    prefill_stale: false, wp_generated: true, created_at: null, updated_at: null,
    ...over,
  }
}

function mkEnvelope(over: Partial<WpListEnvelope> = {}): WpListEnvelope {
  return {
    items: [mkItem()],
    total: 1,
    stats: { by_index_status: { in_progress: 1 }, by_file_status: { draft: 1 } },
    page: 1,
    page_size: 20,
    ...over,
  }
}

function notFoundError() {
  return { response: { status: 404, data: { detail: '资源不存在或不可访问' } } }
}

describe('useVisibilityWorkpaperList — 分页 envelope 消费', () => {
  beforeEach(() => vi.clearAllMocks())

  it('consumes {items,total,stats,page,page_size} envelope from server', async () => {
    const fetcher = vi.fn().mockResolvedValue(mkEnvelope({ total: 3, page: 2, page_size: 10 }))
    const list = useVisibilityWorkpaperList(fetcher, () => 'p1')
    await list.load()
    expect(list.items.value.length).toBe(1)
    expect(list.total.value).toBe(3)
    expect(list.page.value).toBe(2)
    expect(list.pageSize.value).toBe(10)
    expect(list.stats.value.by_index_status).toEqual({ in_progress: 1 })
    expect(list.stats.value.by_file_status).toEqual({ draft: 1 })
  })

  it('forwards page/page_size/sort/filters to the server fetcher (no client-side full filtering)', async () => {
    const fetcher = vi.fn().mockResolvedValue(mkEnvelope())
    const list = useVisibilityWorkpaperList(fetcher, () => 'p1', { pageSize: 50, sort: 'created_at', sortDir: 'desc' })
    await list.setFilter('audit_cycle', 'D')
    const [, params] = fetcher.mock.calls.at(-1)!
    expect(params.page).toBe(1)
    expect(params.page_size).toBe(50)
    expect(params.sort).toBe('created_at')
    expect(params.sort_dir).toBe('desc')
    expect(params.audit_cycle).toBe('D')
  })

  it('empty projectId does not call fetcher and clears cache', async () => {
    const fetcher = vi.fn()
    const list = useVisibilityWorkpaperList(fetcher, () => '')
    await list.load()
    expect(fetcher).not.toHaveBeenCalled()
    expect(list.items.value).toEqual([])
    expect(list.total.value).toBe(0)
  })
})

describe('useVisibilityWorkpaperList — 状态拆分（index/file）', () => {
  it('exposes index_status and file_status separately on items and stats', async () => {
    const fetcher = vi.fn().mockResolvedValue(mkEnvelope({
      items: [mkItem({ index_status: 'archived', file_status: 'reviewed' })],
      stats: { by_index_status: { archived: 1 }, by_file_status: { reviewed: 1 } },
    }))
    const list = useVisibilityWorkpaperList(fetcher, () => 'p1')
    await list.load()
    const it = list.items.value[0]
    expect(it.index_status).toBe('archived')
    expect(it.file_status).toBe('reviewed')
    // 两个维度分别是独立字典（不共用一个含义不明确的 status）
    expect(Object.keys(list.stats.value)).toEqual(['by_index_status', 'by_file_status'])
  })
})

describe('useVisibilityWorkpaperList — 安全占位（External_Not_Found）', () => {
  it('404 sets unified placeholder and clears cached items/names (no flash)', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(mkEnvelope({ items: [mkItem({ wp_name: '机密底稿名' })], total: 1 }))
      .mockRejectedValueOnce(notFoundError())
    const list = useVisibilityWorkpaperList(fetcher, () => 'p1')
    // 首次加载有缓存
    await list.load()
    expect(list.items.value.length).toBe(1)
    // 再次加载被拒绝 → 缓存必须清空，绝不保留旧名称
    await list.load()
    expect(list.hasNotFound.value).toBe(true)
    expect(list.notFoundMessage.value).toBe('资源不存在或不可访问')
    expect(list.items.value).toEqual([])
    expect(list.total.value).toBe(0)
    expect(list.stats.value).toEqual({ by_index_status: {}, by_file_status: {} })
    // 不得透出内部原因
    expect(list.notFoundMessage.value).not.toMatch(/not_found|cross_project|out_of_scope|denied/)
  })

  it('non-404 errors are re-thrown (handled by caller) and still clear cache', async () => {
    const fetcher = vi.fn().mockRejectedValue({ response: { status: 500 } })
    const list = useVisibilityWorkpaperList(fetcher, () => 'p1')
    await expect(list.load()).rejects.toBeTruthy()
    expect(list.items.value).toEqual([])
    expect(list.notFoundMessage.value).toBe('')
  })
})

describe('useVisibilityWorkpaperList — nullable wp 禁用文件动作', () => {
  it('canOpen is false for wp_generated=false (底稿尚未生成)', async () => {
    const fetcher = vi.fn().mockResolvedValue(mkEnvelope({
      items: [mkItem({ wp_id: null, wp_generated: false, file_status: null })],
    }))
    const list = useVisibilityWorkpaperList(fetcher, () => 'p1')
    await list.load()
    expect(list.canOpen(list.items.value[0])).toBe(false)
    expect(list.NOT_GENERATED_LABEL).toBe('底稿尚未生成')
  })

  it('canOpen is true only when wp_generated=true and wp_id present', async () => {
    const list = useVisibilityWorkpaperList(vi.fn(), () => 'p1')
    expect(list.canOpen(mkItem({ wp_generated: true, wp_id: 'wp-9' }))).toBe(true)
    expect(list.canOpen(mkItem({ wp_generated: true, wp_id: null as any }))).toBe(false)
    expect(list.canOpen(mkItem({ wp_generated: false, wp_id: 'wp-9' }))).toBe(false)
  })
})

describe('useVisibilityWorkpaperList — visibility_mode 仅 UX 不授权', () => {
  it('visibility_mode is forwarded only as a UX param and never gates the request', async () => {
    const fetcher = vi.fn().mockResolvedValue(mkEnvelope())
    const list = useVisibilityWorkpaperList(fetcher, () => 'p1')
    await list.load({ visibilityMode: 'my-delegated' })
    const [, params] = fetcher.mock.calls.at(-1)!
    expect(params.visibility_mode).toBe('my-delegated')
    // 结果始终来自服务端 envelope（前端不因 visibility_mode 增删可见项）
    expect(list.items.value.length).toBe(1)

    // 不传 visibility_mode 时不应携带该参数（授权与之无关）
    fetcher.mockClear()
    await list.load()
    const [, params2] = fetcher.mock.calls.at(-1)!
    expect(params2.visibility_mode).toBeUndefined()
  })
})

describe('useVisibilityWorkpaperList — 客户端身份/角色不授权（Property 15）', () => {
  it('never forwards client role/identity as gating params; results come only from server', async () => {
    const fetcher = vi.fn().mockResolvedValue(mkEnvelope())
    const list = useVisibilityWorkpaperList(fetcher, () => 'p1')
    await list.load({ visibilityMode: 'my-delegated' })
    const [, params] = fetcher.mock.calls.at(-1)!
    // 前端只发已登记的分页/排序/过滤/UX 参数，绝不发角色/身份作为授权依据
    expect(params).not.toHaveProperty('role')
    expect(params).not.toHaveProperty('user_id')
    expect(params).not.toHaveProperty('is_admin')
    expect(params).not.toHaveProperty('user_class')
    expect(params).not.toHaveProperty('identity')
    // 只应包含服务端契约允许的键
    const allowed = new Set([
      'page', 'page_size', 'sort', 'sort_dir', 'visibility_mode',
      'audit_cycle', 'index_status', 'file_status', 'assigned_to',
    ])
    for (const k of Object.keys(params)) expect(allowed.has(k)).toBe(true)
  })

  it('two identical envelopes yield identical visible sets regardless of any client-side hint', async () => {
    // 无论客户端传何种 visibility_mode（UX 提示），可见集完全由服务端 envelope 决定
    const env = mkEnvelope({ items: [mkItem({ wp_index_id: 'wi-x' })], total: 1 })
    const fetcher = vi.fn().mockResolvedValue(env)
    const a = useVisibilityWorkpaperList(fetcher, () => 'p1')
    const b = useVisibilityWorkpaperList(fetcher, () => 'p1')
    await a.load({ visibilityMode: 'all' })
    await b.load({ visibilityMode: 'my-delegated' })
    expect(a.items.value.map(i => i.wp_index_id)).toEqual(b.items.value.map(i => i.wp_index_id))
    expect(a.total.value).toBe(b.total.value)
  })
})

// ── fast-check：分页 envelope 与状态拆分不变量（property-based）──
describe('useVisibilityWorkpaperList — fast-check 属性', () => {
  it('property: whatever server returns is exactly what the composable exposes (no client filtering)', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.record({
          n: fc.integer({ min: 0, max: 8 }),
          total: fc.integer({ min: 0, max: 500 }),
          page: fc.integer({ min: 1, max: 20 }),
          pageSize: fc.integer({ min: 1, max: 100 }),
          nullableFlags: fc.array(fc.boolean(), { maxLength: 8 }),
        }),
        async ({ n, total, page, pageSize, nullableFlags }) => {
          const items = Array.from({ length: n }, (_, i) => {
            const gen = nullableFlags[i] ?? true
            return mkItem({
              wp_index_id: `wi-${i}`,
              wp_id: gen ? `wp-${i}` : null,
              wp_generated: gen,
              file_status: gen ? 'draft' : null,
            })
          })
          const fetcher = vi.fn().mockResolvedValue({
            items, total, page, page_size: pageSize,
            stats: { by_index_status: { in_progress: n }, by_file_status: { draft: n } },
          } as WpListEnvelope)
          const list = useVisibilityWorkpaperList(fetcher, () => 'p1')
          await list.load()
          // 前端不增不减：暴露的列表长度 == 服务端返回长度
          expect(list.items.value.length).toBe(n)
          expect(list.total.value).toBe(total)
          expect(list.page.value).toBe(page)
          expect(list.pageSize.value).toBe(pageSize)
          // nullable wp 一律不可打开（Req 12.9）
          for (const it of list.items.value) {
            expect(list.canOpen(it)).toBe(it.wp_generated === true && !!it.wp_id)
          }
          // 状态永远拆成两个字典
          expect(list.stats.value).toHaveProperty('by_index_status')
          expect(list.stats.value).toHaveProperty('by_file_status')
        },
      ),
      { numRuns: 40 },
    )
  })

  it('property: rejection always yields the same placeholder and empty cache (unenumerable)', async () => {
    await fc.assert(
      fc.asyncProperty(fc.constantFrom(404), async (status) => {
        const fetcher = vi.fn().mockRejectedValue({ response: { status } })
        const list = useVisibilityWorkpaperList(fetcher, () => 'p1')
        await list.load()
        expect(list.notFoundMessage.value).toBe('资源不存在或不可访问')
        expect(list.items.value).toEqual([])
        expect(list.total.value).toBe(0)
      }),
      { numRuns: 10 },
    )
  })
})
