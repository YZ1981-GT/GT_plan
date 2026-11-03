/**
 * G1 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①国企：离屏发出的两条载荷（八、2 / 八、3）与「组件里挂载 `useG1DisclosureSoe`（onMounted 首次初始化）→
 * `getSyncSnapshot` → `buildG1SoeSyncPayloads`」逐字节相同，两个章节逐条发送、逐章节回报 ②上市：与
 * `useG1DisclosureListed` → `buildG1ListedSubTableData` → `buildG1SyncPayload('listed')` 逐字节相同 ③只读 G1- 条目、离屏不写底稿
 * ④口径不适用回空 ⑤章节保护只挡被点名的章节 ⑥Tab 仍调同一组函数（静态接线）。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick, ref } from 'vue'
import { mount } from '@vue/test-utils'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), apiPut: vi.fn(), apiPost: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: h.apiPost, put: h.apiPut } }))

import { g1HeadlessProvider } from '../g1HeadlessDisclosure'
import { useG1DisclosureSoe } from '../useG1DisclosureSoe'
import { useG1DisclosureListed } from '../useG1DisclosureListed'
import { buildG1ListedSubTableData, buildG1SoeSyncPayloads, buildG1SyncPayload } from '../g1DisclosureSyncPayload'
import type { ChecklistResponse } from '../useF1FormData'

const ADJ_STORE = JSON.stringify({
  'cost-trading-debt': { closingUnadjusted: 100, openingUnadjusted: 80 },
  'fv-trading-debt': { closingUnadjusted: 10, openingUnadjusted: 5 },
  'cost-trading-derivative': { closingUnadjusted: 50, openingUnadjusted: 40 },
  'fv-trading-derivative': { closingUnadjusted: 2, openingUnadjusted: 1 },
  'cost-designated-debt': { closingUnadjusted: 20, openingUnadjusted: 15 },
})
const LISTED_STORE = JSON.stringify({
  version: 2,
  derivativeRows: [{ rowKey: 'deriv-interest', endAmount: 300, priorAmount: 100 }],
  fvRows: [{ rowKey: 'fv-trading', l1: 500, l2: 20, l3: 0 }],
  designatedReason: '指定以消除会计错配',
})
const RESPONSES: ChecklistResponse[] = [
  { item_id: 'G1-1-rows', remark: ADJ_STORE, conclusion: null },
  { item_id: 'G1-note-soe-note', remark: '国企附注审计说明', conclusion: null },
  { item_id: 'G1-note-listed-store', remark: LISTED_STORE, conclusion: null },
  { item_id: 'G1-note-listed-note', remark: '上市附注说明', conclusion: null },
  { item_id: 'G10-note-soe-rows', remark: '{"version":2,"trading":[],"derivative":[]}', conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-g1', wpCode: 'G1' }
const SOE = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }
const LISTED = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }

function g1Map(): Map<string, ChecklistResponse> {
  return new Map(RESPONSES.filter((r) => r.item_id.startsWith('G1-')).map((r) => [r.item_id, { ...r }]))
}

/** Tab 路径（国企）：组件里挂载同一个 composable（onMounted 做首次初始化）→ 同一个快照函数 → 同一个 builder */
async function soeTabPayloads() {
  let dis: ReturnType<typeof useG1DisclosureSoe> | null = null
  const Host = defineComponent({
    setup() {
      dis = useG1DisclosureSoe({ allResponses: ref(g1Map()), debouncedSave: () => {}, isReadonly: ref(false) })
      return () => null
    },
  })
  const wrapper = mount(Host)
  await nextTick()
  const payloads = buildG1SoeSyncPayloads('wp-g1', ['soe_standalone'], dis!.getSyncSnapshot())
  wrapper.unmount()
  return payloads
}

/** Tab 路径（上市）：G1TabDisclosureListed.syncToNotes 的同一组调用 */
async function listedTabPayload() {
  let dis: ReturnType<typeof useG1DisclosureListed> | null = null
  const Host = defineComponent({
    setup() {
      dis = useG1DisclosureListed({ allResponses: ref(g1Map()), debouncedSave: () => {}, isReadonly: ref(false) })
      return () => null
    },
  })
  const wrapper = mount(Host)
  await nextTick()
  const payload = buildG1SyncPayload('listed', 'wp-g1', ['listed_standalone'], buildG1ListedSubTableData(dis!.getSyncSnapshot()))
  wrapper.unmount()
  return payload
}

describe('g1HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockImplementation(async (_url: string, body: { section_id: string }) => (
      body.section_id === '八、2' ? { rows_synced: 8, push_kept: [{ table: '交易性金融资产' }] } : { rows_synced: 2 }
    ))
  })

  it('国企：两个章节逐条发送、逐章节回报，载荷与 Tab 逐字节相同，不写底稿', async () => {
    const out = await g1HeadlessProvider(SOE)
    expect(out).toEqual({ sections: [{ section: '八、2', rows: 8, kept: 1 }, { section: '八、3', rows: 2, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-g1/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    expect(h.post).toHaveBeenCalledTimes(2)
    for (const [url, , cfg] of h.post.mock.calls) {
      expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
      expect(cfg).toMatchObject({ _silent: true })
    }
    const sent = h.post.mock.calls.map((c) => c[1])
    const tab = await soeTabPayloads()
    expect(JSON.stringify(sent)).toBe(JSON.stringify(tab))
    // 夹具有真实数据：交易性按 G1-1 审定表灌数，衍生插入审定汇总行
    const trading = sent[0].sub_table_data['交易性金融资产'] as Array<{ label: string; end_fair_value: number }>
    expect(trading.find((r) => r.label === '其中：债务工具投资')?.end_fair_value).toBe(110)
    const deriv = sent[1].sub_table_data['衍生金融资产'] as Array<{ label: string; end_balance: number }>
    expect(deriv[0]).toMatchObject({ label: '衍生金融资产（审定汇总）', end_balance: 52 })
    expect(sent[0].sub_table_data._note_texts).toContainEqual({ section: 'soe-audit-note', text: '国企附注审计说明' })
  })

  it('上市：五、2 一条载荷，与 Tab 逐字节相同', async () => {
    const out = await g1HeadlessProvider(LISTED)
    expect(h.post).toHaveBeenCalledTimes(1)
    const sent = h.post.mock.calls[0][1]
    expect(sent.section_id).toBe('五、2')
    expect(out).toEqual({ sections: [{ section: '五、2', rows: 2, kept: 0 }] })
    expect(JSON.stringify(sent)).toBe(JSON.stringify(await listedTabPayload()))
    expect(sent.sub_table_data['衍生金融资产']).toContainEqual({ 项目: '利率衍生工具', 期末余额: 300, 上年年末余额: 100 })
    expect(sent.sub_table_data['指定理由']).toEqual([{ 说明: '指定以消除会计错配' }])
    expect(h.put).not.toHaveBeenCalled()
  })

  it('口径不适用：国企页在上市项目、上市页在国企项目都回空', async () => {
    expect(await g1HeadlessProvider({ ...SOE, applicableStandards: ['listed_standalone'] })).toEqual({ sections: [] })
    expect(await g1HeadlessProvider({ ...LISTED, applicableStandards: ['soe_standalone'] })).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('章节保护只挡被点名的章节，另一个章节照常写', async () => {
    const out = await g1HeadlessProvider({
      ...SOE,
      sectionGuard: (section) => (section === '八、3' ? '附注 八、3 已有 2 格人工填写' : null),
    })
    expect(h.post).toHaveBeenCalledTimes(1)
    expect(h.post.mock.calls[0][1].section_id).toBe('八、2')
    expect(out.sections).toEqual([
      { section: '八、2', rows: 8, kept: 1 },
      { section: '八、3', rows: 0, skipped: '附注 八、3 已有 2 格人工填写' },
    ])
  })

  it('一个章节发送失败不影响另一个章节', async () => {
    h.post.mockImplementation(async (_url: string, body: { section_id: string }) => {
      if (body.section_id === '八、2') throw Object.assign(new Error('x'), { response: { data: { detail: '章节锁定' } } })
      return { rows_synced: 2 }
    })
    const out = await g1HeadlessProvider(SOE)
    expect(out.sections).toEqual([
      { section: '八、2', rows: 0, error: '章节锁定' },
      { section: '八、3', rows: 2, kept: 0 },
    ])
  })

  it('静态接线：两个 Tab 仍调同一个 composable / 快照函数 / builder', () => {
    const dir = resolve(__dirname, '../../g1-trading-financial-assets/core')
    const soe = readFileSync(resolve(dir, 'G1TabDisclosureSOE.vue'), 'utf-8')
    expect(soe).toMatch(/useG1DisclosureSoe\(\{/)
    expect(soe).toMatch(/buildG1SoeSyncPayloads\(\s*props\.wpId \|\| '',\s*props\.applicableStandards,\s*dis\.getSyncSnapshot\(\),?\s*\)/)
    const listed = readFileSync(resolve(dir, 'G1TabDisclosureListed.vue'), 'utf-8')
    expect(listed).toMatch(/useG1DisclosureListed\(\{/)
    expect(listed).toMatch(/buildG1SyncPayload\(\s*'listed',[\s\S]{0,120}buildG1ListedSubTableData\(getSyncSnapshot\(\)\)/)
  })
})
