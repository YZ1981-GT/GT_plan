/**
 * 离屏同步框架（spec note-pull-followup-closure R1.1 / R1.2）：取数方式、effectScope 生命周期、prepare 先于 build、多章节
 * 逐条发送并逐条回报、章节保护、单条失败隔离、响应里的跳过 / 整节人工覆盖 / 推送保持，离屏不弹提示。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref, watch } from 'vue'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), prime: vi.fn(), msg: vi.fn(), box: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post } }))
vi.mock('@/composables/useAgingConfig', () => ({ primeAgingConfig: h.prime }))
vi.mock('element-plus', () => ({ ElMessage: Object.assign(h.msg, { success: h.msg, error: h.msg, warning: h.msg }), ElMessageBox: { confirm: h.box } }))

import { defineHeadlessProvider, loadRenderConfig, postHeadlessSyncPayload } from '../headlessFramework'

const CTX = { projectId: 'p1', year: 2025, variant: 'soe' as const, wpId: 'wp1', wpCode: 'X1', applicableStandards: ['soe_standalone'] }
const RESPONSES = [{ item_id: 'X1-a', remark: '5', conclusion: null }, { item_id: 'Y1-b', remark: '9', conclusion: null }]

beforeEach(() => {
  for (const fn of Object.values(h)) fn.mockReset()
  h.get.mockImplementation(async (url: string) => (url.endsWith('/render-config') ? { data: { sheets: [{ name: 's1' }] } } : RESPONSES))
  h.post.mockImplementation(async (_url: string, body: any) => ({ data: { section_id: body.section_id, rows_synced: 2 } }))
})

describe('defineHeadlessProvider', () => {
  it('按声明取数：本底稿前缀的回复、渲染配置、账龄预取；setup 在作用域内、prepare 先于 build；作用域随后停止', async () => {
    const order: string[] = []
    let inst: { v: { value: number }; fired: { n: number } } | null = null
    const provider = defineHeadlessProvider({
      prefix: 'X1-',
      needs: { aging: true, renderConfig: true },
      setup: ({ responses, renderConfig }) => {
        order.push(`setup:${[...responses.keys()].join(',')}:${renderConfig?.sheets?.[0]?.name}`)
        const v = ref(0)
        const fired = { n: 0 }
        watch(v, () => { fired.n++ }, { flush: 'sync' })
        inst = { v, fired }
        return inst
      },
      prepare: async (inst) => { order.push('prepare'); inst.v.value = 1 },
      build: (inst, { ctx }) => {
        order.push(`build:${inst.v.value}`)
        return [{ section_id: '八、1', wp_id: ctx.wpId }, null as any, { section_id: '八、2', wp_id: ctx.wpId }]
      },
    })
    const out = await provider(CTX)
    expect(order).toEqual(['setup:X1-a:s1', 'prepare', 'build:1'])
    expect(h.prime).toHaveBeenCalledWith('p1')
    expect(out).toEqual({ sections: [{ section: '八、1', rows: 2, kept: 0 }, { section: '八、2', rows: 2, kept: 0 }] })
    expect(h.post.mock.calls.map((c) => [c[0], c[1].section_id, c[2]])).toEqual([
      ['/api/projects/p1/disclosure-notes/sync-from-workpaper', '八、1', { _silent: true }],
      ['/api/projects/p1/disclosure-notes/sync-from-workpaper', '八、2', { _silent: true }],
    ])
    // 作用域结束后 composable 里的侦听器随之停止（离屏实例不残留副作用）
    expect(inst!.fired.n).toBe(1)
    inst!.v.value = 99
    expect(inst!.fired.n).toBe(1)
    expect(h.msg).not.toHaveBeenCalled()
    expect(h.box).not.toHaveBeenCalled()
  })

  it('不声明的取数不发：没有 renderConfig / 账龄需求时只取回复', async () => {
    const provider = defineHeadlessProvider({ prefix: ['X1-', 'Y1-'], setup: ({ responses }) => ({ keys: [...responses.keys()] }),
      build: (inst) => ({ section_id: inst.keys.join('|') }) })
    const out = await provider(CTX)
    expect(out.sections[0].section).toBe('X1-a|Y1-b')
    expect(h.get).toHaveBeenCalledTimes(1)
    expect(h.prime).not.toHaveBeenCalled()
  })

  it('章节保护：判定不为 null 的章节不发，原因原样回报（空串 = 静默跳过）', async () => {
    const provider = defineHeadlessProvider({ prefix: 'X1-', setup: () => ({}),
      build: () => [{ section_id: '八、1' }, { section_id: '八、2' }, { section_id: '八、3' }] })
    const guard = (s: string) => (s === '八、1' ? '已有人工填写' : s === '八、2' ? '' : null)
    const out = await provider({ ...CTX, sectionGuard: guard })
    expect(out.sections).toEqual([
      { section: '八、1', rows: 0, skipped: '已有人工填写' },
      { section: '八、2', rows: 0, skipped: '' },
      { section: '八、3', rows: 2, kept: 0 },
    ])
    expect(h.post).toHaveBeenCalledTimes(1)
  })

  it('单条发送失败只记这一章节；自定义发送替代缺省发送', async () => {
    h.post.mockRejectedValueOnce({ response: { data: { detail: '附注未同步：项目没有审计年度' } } })
    const failing = defineHeadlessProvider({ prefix: 'X1-', setup: () => ({}), build: () => [{ section_id: '八、1' }, { section_id: '八、2' }] })
    expect((await failing(CTX)).sections).toEqual([
      { section: '八、1', rows: 0, error: '附注未同步：项目没有审计年度' },
      { section: '八、2', rows: 2, kept: 0 },
    ])
    const custom = vi.fn(async (_i: unknown, p: any) => ({ section: p.section_id, rows: 7 }))
    const viaBatch = defineHeadlessProvider({ prefix: 'X1-', setup: () => ({ tag: 1 }), build: () => ({ section_id: '八、9' }), post: custom })
    expect((await viaBatch(CTX)).sections).toEqual([{ section: '八、9', rows: 7 }])
    expect(custom.mock.calls[0][0]).toEqual({ tag: 1 })
    expect(h.post).toHaveBeenCalledTimes(2)
  })

  it('builder 回空 = 本口径没有章节；setup 回空 = 实例化失败（抛错，由调用方记失败）', async () => {
    expect(await defineHeadlessProvider({ prefix: 'X1-', setup: () => ({}), build: () => null })(CTX)).toEqual({ sections: [] })
    await expect(defineHeadlessProvider({ prefix: 'X1-', setup: () => undefined, build: () => null })(CTX))
      .rejects.toThrow('X1 披露表离屏实例化失败')
  })
})

describe('postHeadlessSyncPayload / loadRenderConfig', () => {
  it('响应：章节不适用 / 整节人工覆盖 = 跳过并写明；推送保持的格数随结果回报', async () => {
    h.post.mockResolvedValueOnce({ data: { section_id: '九、1', skipped: true, reason: 'section_not_applicable_to_report_scope' } })
    expect((await postHeadlessSyncPayload('p1', { section_id: '九、1' })).skipped).toContain('不适用于本项目口径')
    h.post.mockResolvedValueOnce({ data: { section_id: '八、5', blocked_by_manual_override: true, rows_synced: 0 } })
    expect((await postHeadlessSyncPayload('p1', { section_id: '八、5' })).skipped).toBe('附注 八、5 标记了整节人工覆盖，未写入')
    h.post.mockResolvedValueOnce({ data: { section_id: '八、5', rows_synced: 4, push_kept: [{}, {}] } })
    expect(await postHeadlessSyncPayload('p1', { section_id: '八、5' })).toEqual({ section: '八、5', rows: 4, kept: 2 })
  })

  it('渲染配置取不到回 null（provider 按 Tab 加载失败的同一兜底）', async () => {
    h.get.mockRejectedValueOnce(new Error('404'))
    expect(await loadRenderConfig('wp1')).toBeNull()
    expect(h.get.mock.calls[0]).toEqual(['/api/workpapers/wp1/render-config', { _silent: true }])
  })
})
