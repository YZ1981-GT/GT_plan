/**
 * E1 宿主与公式推送的配套（spec chain-closure-phase2-formula-push-engine 任务 13 · 需求 4.4 / 4.5 / 4.7）
 *
 * - 后端独占键（试算平衡表数 / 审定合计 / 语义槽）不随 flushSave 回写 —— 公式推送是唯一写入方；
 * - 宿主审定合计与审定表 composable **同式**（含大厅已确认调整），且总是派生（不回放陈旧持久化值）；
 * - `formula.pushed` 只在本底稿的**源值**有写入时提示，「载入最新数据」只替换推送改过的条目。
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { ref } from 'vue'
import { e1AdjudicationSaveItemIds, isE1BackendOwnedKey } from '../e1BackendOwnedKeys'
import { e1AdjTotalKey, e1HostAdjTotalSeeds, e1HostAuditedTotals } from '../e1HostAuditedTotals'
import { e1PushNotice, e1PushedRows } from '../e1FormulaPushNotice'
import { useE1Adjudication } from '../useE1Adjudication'

const getterOf = (m: Record<string, string>) => (k: string) => m[k]

describe('后端独占键不回写', () => {
  it.each([
    'E1-adj-tb-amount-ending', 'E1-adj-tb-amount-opening',
    'E1-adj-total-1001', 'E1-adj-total-1002-opening', 'E1-adj-total-1012',
    'E1-adj-slot-finance_co', 'E1-adj-slot-accrued-opening', 'E1-adj-slot-digital',
  ])('%s 是后端独占键', (id) => {
    expect(isE1BackendOwnedKey(id)).toBe(true)
  })

  it.each([
    'E1-adj-cash-note', 'E1-adj-total-note', 'E1-adj-diff-note', 'E1-adj-overseas-ending-unadj',
    'E1-adj-total-1001-x', 'E1-adj-total-2202', 'E1-adj-slot-other', 'E1-cash-detail-rows',
  ])('%s 不是后端独占键（用户可编辑或非本族）', (id) => {
    expect(isE1BackendOwnedKey(id)).toBe(false)
  })

  it('保存集合 = E1-adj- 前缀 − 后端独占键', () => {
    expect(e1AdjudicationSaveItemIds([
      'E1-adj-cash-note', 'E1-adj-total-1001', 'E1-adj-tb-amount-ending', 'E1-adj-slot-digital',
      'E1-adj-total-note', 'E1-cash-detail-total-unaudited',
    ])).toEqual(['E1-adj-cash-note', 'E1-adj-total-note'])
  })
})

describe('真 composable：flushSave 不提交后端独占键', () => {
  it('编辑后卸载（触发 flushSave）：只提交用户可编辑键，审定合计 / 试算平衡表数 / 语义槽只在内存', async () => {
    const { defineComponent, h } = await import('vue')
    const { mount } = await import('@vue/test-utils')
    const map = ref(new Map<string, { item_id: string; conclusion: string | null; remark: string | null }>())
    for (const [k, v] of Object.entries({
      'E1-cash-detail-total-unaudited': '290',
      'E1-adj-tb-amount-ending': '606.73',
      'E1-adj-total-1001': '999',
      'E1-adj-slot-digital': '9',
    })) map.value.set(k, { item_id: k, conclusion: null, remark: v })
    const saved: Array<{ item_id: string }> = []
    const wrapper = mount(defineComponent({
      setup() {
        const api = useE1Adjudication({
          wpId: ref('wp-host'), projectId: ref('proj-host'), allResponses: map,
          saveImmediate: async () => {},
          debouncedSave: async (items: any[]) => { saved.push(...items) },
          isReadonly: ref(false),
        } as any)
        api.saveVarianceNote('cash', '盘点差异说明')
        return () => h('div')
      },
    }))
    wrapper.unmount()
    const ids = saved.map((i) => i.item_id)
    expect(ids).toContain('E1-adj-cash-note')
    expect(ids.filter(isE1BackendOwnedKey)).toEqual([])
    // 内存里照常同步（披露表 / 告警读它），只是不落库
    expect(map.value.get('E1-adj-total-1001')?.remark).toBe('290')
  })
})

describe('宿主审定合计与审定表 composable 同式', () => {
  const entries: Record<string, string> = {
    'E1-cash-detail-total-unaudited': '290',
    'E1-cash-detail-opening-unaudited': '203',
    'E1-bank-detail-principal-total-unaudited': '120',
    'E1-bank-detail-principal-opening-unaudited': '100',
    'E1-bank-detail-other-total-unaudited': '7',
    'E1-digital-total-unaudited': '2',
    'E1-adjustment-by-item-cash-ending': '-10.5',
    'E1-adjustment-by-item-digital-ending': '1',
    'E1-adjustment-by-item-other_mf-opening': '3',
    'E1-hall-adj-cash-ending': '100',
    'E1-hall-adj-other_mf-ending': '0.25',
  }

  it('含大厅已确认调整（仅期末三行）与数字货币调整', () => {
    const get = getterOf(entries)
    expect(e1HostAuditedTotals(get, 'ending')).toEqual({ '1001': 290 - 10.5 + 100, '1002': 120, '1012': 7 + 0.25 + 2 + 1 })
    expect(e1HostAuditedTotals(get, 'opening')).toEqual({ '1001': 203, '1002': 100, '1012': 3 })
  })

  it('与真 useE1Adjudication.syncAuditedTotals 逐键相等', async () => {
    const { defineComponent, h } = await import('vue')
    const { mount } = await import('@vue/test-utils')
    const map = ref(new Map(Object.entries(entries).map(([k, v]) => [k, { item_id: k, conclusion: null, remark: v }])))
    const wrapper = mount(defineComponent({
      setup() {
        useE1Adjudication({
          wpId: ref('wp'), projectId: ref('p'), allResponses: map,
          saveImmediate: async () => {}, debouncedSave: async () => {}, isReadonly: ref(false),
        } as any)
        return () => h('div')
      },
    }))
    for (const period of ['ending', 'opening'] as const) {
      for (const [code, value] of Object.entries(e1HostAuditedTotals(getterOf(entries), period))) {
        expect(Number(map.value.get(e1AdjTotalKey(code, period))?.remark), `${code}/${period}`).toBe(value)
      }
    }
    wrapper.unmount()
  })

  it('总是派生：已存在的陈旧审定合计被覆盖；全 0 且原本没有的键不种子', () => {
    const stale = { ...entries, 'E1-adj-total-1001': '1', 'E1-adj-total-1002-opening': '5' }
    const seeds = new Map(e1HostAdjTotalSeeds(getterOf(stale), (k) => k in stale))
    expect(seeds.get('E1-adj-total-1001')).toBe(String(290 - 10.5 + 100))
    expect(seeds.get('E1-adj-total-1002-opening')).toBe('100')
    const empty = new Map(e1HostAdjTotalSeeds(getterOf({}), () => false))
    expect(empty.size).toBe(0)
    // 原本存在、现在算出 0 ⇒ 写 0（不留陈旧值）
    const zeroed = new Map(e1HostAdjTotalSeeds(getterOf({ 'E1-adj-total-1001': '5' }), (k) => k === 'E1-adj-total-1001'))
    expect(zeroed.get('E1-adj-total-1001')).toBe('0')
  })
})

describe('formula.pushed 提示条', () => {
  const evt = (over: Record<string, unknown> = {}) => ({
    project_id: 'p', year: 2025, run_id: 'run-1', dry_run: false, wp_ids: ['wp-1'],
    stages: ['derived', 'source'], changed_items: ['E1-cash-detail-rows', 'E1-adj-tb-amount-ending'], ...over,
  })

  it('本底稿源值有写入 ⇒ 提示，条数 = 改过的条目数', () => {
    expect(e1PushNotice(evt(), 'wp-1')).toEqual({
      runId: 'run-1', count: 2, itemIds: ['E1-cash-detail-rows', 'E1-adj-tb-amount-ending'],
    })
  })

  it.each([
    ['别的底稿', evt({ wp_ids: ['wp-2'] })],
    ['只有派生值变化（前端本就实时同式计算）', evt({ stages: ['derived'] })],
    ['只有附注变化', evt({ stages: ['note'] })],
    ['试跑', evt({ dry_run: true })],
    ['没有改过的条目', evt({ changed_items: [] })],
    ['载荷异常', null],
  ])('%s ⇒ 不提示', (_name, e) => {
    expect(e1PushNotice(e, 'wp-1')).toBeNull()
  })

  it('载入最新数据只替换推送改过的条目（用户未保存的其它编辑不动）', () => {
    const server = [
      { item_id: 'E1-cash-detail-rows', remark: '[新]', conclusion: null },
      { item_id: 'E1-adj-cash-note', remark: '服务端旧备注', conclusion: null },
    ]
    expect(e1PushedRows(server, ['E1-cash-detail-rows'])).toEqual([server[0]])
  })
})

describe('宿主接线（源码级：纯函数之外只剩接线，防回退）', () => {
  const src = readFileSync(resolve(__dirname, '../../GtE1MonetaryFund.vue'), 'utf-8')

  it('审定合计种子与全局告警都走 e1HostAuditedTotals，不再内联 parseFloat 第二口径', () => {
    expect(src).toContain('e1HostAdjTotalSeeds(getRemark')
    expect(src).toContain("e1HostAuditedTotals(getRemark, 'ending')")
    expect(src).not.toMatch(/parseFloat\(allResponses\.value\.get/)
    expect(src).not.toMatch(/const _wb\b/)
  })

  it('现金合计汇率与 composable 同口径（外币待录入不按 1 计）', () => {
    expect(src).not.toMatch(/fxRate\)\s*\|\|\s*1/)
    expect(src).toContain('const fx = parseNum(r.fxRate)')
  })

  it('订阅 formula.pushed 且卸载时关闭；提示条中文', () => {
    expect(src).toMatch(/subscribeProjectEvent\(props\.projectId, 'formula\.pushed'/)
    expect(src).toContain('_pushSub.close()')
    expect(src).toContain('载入最新数据')
  })
})
