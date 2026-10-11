/**
 * D2：HTML 里改的格，2 秒内切「在线编辑」也必须先落库（R20，2026-10-11 和平药房 D2-2 真栈实测）。
 *
 * 真栈形态：表格编辑模式改「公司代码」→ 立刻点在线编辑 ⇒ 网络序 GET store-projection 早于那次
 * PUT（`useD2Detail` 的私有 2s 防抖还没到点）⇒ OO 打开的是旧值；防抖随后照常落库，OO 保存回来
 * 再把旧值 / 清空写回 store ⇒ HTML 那次编辑被静默覆盖。
 *
 * 本文件锁：
 * 1. 行为：防抖窗口内 `flushPendingWrites()` 立即发出那次保存、并等到宿主那次写入落地；之后防抖
 *    不会再重复保存一次；
 * 2. 结构：D2 每个「私有防抖 + 写盘」的子 composable 都登记了 flusher（唯一豁免须可证伪）；
 *    宿主注入给子 Tab 的保存函数经 `trackPendingWrite` 追踪在途。
 */
import { readFileSync, readdirSync } from 'node:fs'
import { resolve } from 'node:path'

import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, provide, ref } from 'vue'

vi.mock('@/composables/useAgingConfig', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/composables/useAgingConfig')>()
  return { ...actual, useAgingConfig: () => ({ segments: ref([]), bands: ref([]) }) }
})

const { useD2Detail } = await import('../composables/useD2Detail')
const { D2_SAVE_ITEMS_KEY } = await import('../composables/d2InjectionKeys')
const { _pendingWriteCounts, flushPendingWrites, trackPendingWrite } = await import('../sync/pendingWrites')

const COMPOSABLES = resolve(__dirname, '../composables')
const HOST = resolve(__dirname, '../GtD2AccountsReceivable.vue')

function mountDetail(save: (items: Array<{ item_id: string; remark: string | null }>) => Promise<void>) {
  let api!: ReturnType<typeof useD2Detail>
  const Child = defineComponent({
    setup() {
      api = useD2Detail({
        wpId: ref('wp-1'),
        projectId: ref('proj-1'),
        allResponses: ref(
          new Map([
            ['D2-detail-rows', {
              item_id: 'D2-detail-rows',
              conclusion: null,
              remark: JSON.stringify([{ rowId: 'dr-1', seq: 1, customerName: '甲公司', companyCode: '' }]),
            }],
          ]),
        ),
        isReadonly: ref(false),
        relatedParties: ref([]),
      })
      return () => null
    },
  })
  const Parent = defineComponent({
    setup() {
      provide(D2_SAVE_ITEMS_KEY, save as never)
      return () => h(Child)
    },
  })
  const wrapper = mount(Parent)
  return { wrapper, api: () => api }
}

afterEach(async () => {
  vi.useRealTimers()
  await flushPendingWrites()
})

describe('D2-2 明细：防抖窗口内切在线编辑', () => {
  it('flushPendingWrites 立即发出那次保存，并等到宿主写入落地', async () => {
    vi.useFakeTimers()
    let release!: () => void
    const landed = new Promise<void>((done) => {
      release = done
    })
    const saved: string[] = []
    // 宿主 d2SaveItems 的形态：经 trackPendingWrite 登记在途写入
    const save = vi.fn((items: Array<{ item_id: string; remark: string | null }>) => {
      saved.push(items.map((i) => i.remark ?? '').join(''))
      return trackPendingWrite(landed)
    })
    const { wrapper, api } = mountDetail(save)
    api().updateCell('dr-1', 'companyCode', 'HP-HTML-2')
    expect(save, '防抖窗口内尚未保存（这正是会被 store-projection 抢跑的窗口）').not.toHaveBeenCalled()

    let flushed = false
    const done = flushPendingWrites().then(() => {
      flushed = true
    })
    expect(save).toHaveBeenCalledTimes(1)
    expect(saved[0]).toContain('"companyCode":"HP-HTML-2"')
    await Promise.resolve()
    expect(flushed, '写入未落地就放行 = 宿主照样读到旧 store').toBe(false)
    release()
    await done
    expect(flushed).toBe(true)

    vi.advanceTimersByTime(3000)
    expect(save, '已 flush 的防抖不得再保存第二次').toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('登记随组件 scope 注销（卸载后不留悬挂的 flusher）', async () => {
    const before = _pendingWriteCounts().flushers
    const { wrapper } = mountDetail(vi.fn(async () => {}))
    expect(_pendingWriteCounts().flushers).toBe(before + 1)
    wrapper.unmount()
    expect(_pendingWriteCounts().flushers).toBe(before)
  })
})

// ─── 结构判据 ─────────────────────────────────────────────────────────────────

/** 私有防抖：`xxxTimer = setTimeout(() => { ... CALL() ... })`，返回定时器里调用的函数名。 */
function debounceCallees(source: string): string[] {
  const out: string[] = []
  const re = /\w*[Tt]imer\s*=\s*setTimeout\(\s*\(\)\s*=>\s*\{([^}]*)\}/g
  for (const m of source.matchAll(re)) {
    for (const call of m[1].matchAll(/(\w+)\(/g)) out.push(call[1])
  }
  return out
}

/** 只重算、不写盘的防抖（豁免须可证伪：定时器里的调用一个都不能像写盘）。 */
const NON_WRITING_DEBOUNCE: Record<string, string> = {
  'useD2VcAuditSummary.ts': '防抖只调 recompute() 重算统计指标，写盘走另一条即时 saveToResponses',
}

describe('D2 子 composable 的私有防抖全部登记', () => {
  const files = readdirSync(COMPOSABLES).filter((f) => /^useD2.*\.ts$/.test(f))
  const withDebounce = files.filter((f) => debounceCallees(readFileSync(resolve(COMPOSABLES, f), 'utf-8')).length > 0)

  it('分母非空（扫描器没失锚）', () => {
    expect(withDebounce.length).toBeGreaterThanOrEqual(14)
  })

  it.each(withDebounce)('%s', (file) => {
    const source = readFileSync(resolve(COMPOSABLES, file), 'utf-8')
    if (file in NON_WRITING_DEBOUNCE) {
      const callees = debounceCallees(source)
      expect(callees.filter((c) => /save|flush|persist|dispatch/i.test(c)), NON_WRITING_DEBOUNCE[file]).toEqual([])
      return
    }
    expect(source, '私有防抖未登记 ⇒ 2 秒内切在线编辑会丢这次编辑').toMatch(/\bregisterPendingFlusher\(/)
  })

  it('豁免表没有失效条目', () => {
    for (const file of Object.keys(NON_WRITING_DEBOUNCE)) expect(withDebounce).toContain(file)
  })

  it('宿主注入给子 Tab 的保存函数追踪在途写入', () => {
    const host = readFileSync(HOST, 'utf-8')
    const body = host.slice(host.indexOf('async function d2SaveItems('), host.indexOf('provide(D2_SAVE_ITEMS_KEY'))
    expect(body).toMatch(/await trackPendingWrite\(formData\.saveItemsFromEvent\(items\)\)/)
  })
})
