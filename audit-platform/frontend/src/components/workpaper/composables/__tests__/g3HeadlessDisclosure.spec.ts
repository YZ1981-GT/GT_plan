/**
 * G3 披露表离屏同步 = 底稿披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 表格行 + 审计说明原在两个 Tab SFC 里内联读取，抽成 `useG3DisclosureState` 后 Tab 与离屏同步共用。判据：
 * ①挂载真实 Tab、点「同步至附注」发出的载荷 == 离屏载荷（上市 五、8 / 国企 八、9 各一条）②抽出的读取逻辑与原实现同口径
 * （无表格 / 坏 JSON / 空数组 ⇒ 一行空占位，缺 id 的行补 id）③只读 G3- 条目、离屏不写底稿 ④口径不适用回空 ⑤静态接线。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), apiPost: vi.fn(), apiPut: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))
vi.mock('@/services/apiProxy', () => ({ api: { get: vi.fn(), post: h.apiPost, put: h.apiPut } }))
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(() => Promise.resolve()) }),
  useRoute: () => ({ params: {}, query: {}, path: '/', name: 'wp' }),
}))
vi.mock('element-plus', async () => ({
  ...(await vi.importActual<Record<string, unknown>>('element-plus')),
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

import { g3HeadlessProvider } from '../g3HeadlessDisclosure'
import { loadG3ListedDisclosureRows, loadG3SoeDisclosureRows } from '../g3DisclosureTabState'
import G3TabDisclosureListed from '../../g3-dividend-receivable/G3TabDisclosureListed.vue'
import G3TabDisclosureSOE from '../../g3-dividend-receivable/G3TabDisclosureSOE.vue'
import type { ChecklistResponse } from '../useF1FormData'

const RESPONSES: ChecklistResponse[] = [
  {
    item_id: 'G3-disclosure-listed-table',
    conclusion: JSON.stringify([
      { id: 'dl-1', investeeName: '甲公司', openingBalance: 100, currentIncrease: 50, currentDecrease: 30, remark: '已宣告未发放' },
      { investeeName: '乙公司', openingBalance: 0, currentIncrease: 20, currentDecrease: 0 },
    ]),
    remark: null,
  },
  { item_id: 'G3-disclosure-listed-text', remark: '上市应收股利说明', conclusion: null },
  {
    item_id: 'G3-disclosure-soe-table',
    conclusion: JSON.stringify([{ id: 'ds-1', investeeName: '丙公司', openingBalance: 200, currentChange: -50, remark: '' }]),
    remark: null,
  },
  { item_id: 'G3-disclosure-soe-text', remark: '国企应收股利说明', conclusion: null },
  { item_id: 'G2-note-soe-note', remark: '别的底稿', conclusion: null },
]
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-g3', wpCode: 'G3' }
const SOE = { ...CTX, variant: 'soe' as const, applicableStandards: ['soe_standalone'] }
const LISTED = { ...CTX, variant: 'listed' as const, applicableStandards: ['listed_standalone'] }

const STUBS = {
  'el-button': { template: '<button class="el-button" @click="$emit(\'click\')"><slot /></button>', emits: ['click'] },
  'el-tag': { template: '<span><slot /></span>' },
  'el-alert': true,
  'el-table': true,
  'el-table-column': true,
  'el-input': true,
  'el-input-number': true,
  'el-icon': true,
  GtIndexChip: true,
  G3AuditTextCards: true,
  WpAmountInput: true,
}

/** Tab 路径：挂载真实 Tab，点「同步至附注」，取它发出的载荷 */
async function tabPayload(variant: 'soe' | 'listed') {
  const debouncedSave = vi.fn()
  const allResponses = new Map(RESPONSES.filter((r) => r.item_id.startsWith('G3-')).map((r) => [r.item_id, { ...r }]))
  const wrapper = mount(variant === 'soe' ? G3TabDisclosureSOE : G3TabDisclosureListed, {
    props: {
      wpId: 'wp-g3', projectId: 'p1', allResponses, isReadonly: false, debouncedSave,
      applicableStandards: variant === 'soe' ? ['soe_standalone'] : ['listed_standalone'],
    },
    global: { stubs: STUBS },
  })
  await nextTick()
  const before = h.apiPost.mock.calls.length
  const button = wrapper.findAll('button').find((b) => b.text().includes('同步至附注'))
  expect(button, '找不到「同步至附注」按钮').toBeDefined()
  await button!.trigger('click')
  await nextTick()
  expect(h.apiPost.mock.calls.length).toBe(before + 1)
  const [url, payload] = h.apiPost.mock.calls[before]
  expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
  expect(debouncedSave).not.toHaveBeenCalled()
  wrapper.unmount()
  return payload
}

describe('g3HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 3, push_kept: [] })
    h.apiPost.mockResolvedValue({ rows_synced: 3 })
  })

  it('上市：离屏载荷与真实 Tab 点「同步至附注」发出的逐字节相同，不写底稿', async () => {
    const out = await g3HeadlessProvider(LISTED)
    expect(out).toEqual({ sections: [{ section: '五、8', rows: 3, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-g3/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    expect(h.apiPut).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    expect(JSON.stringify(sent)).toBe(JSON.stringify(await tabPayload('listed')))
    const rows = sent.sub_table_data['应收股利'] as Array<{ label: string; end_balance: number }>
    expect(rows.map((r) => [r.label, r.end_balance])).toEqual([['甲公司', 120], ['乙公司', 20], ['小计', 140]])
    expect(sent.sub_table_data._note_texts).toEqual([{ section: 'listed-audit-note', text: '上市应收股利说明' }])
  })

  it('国企：离屏载荷与真实 Tab 逐字节相同', async () => {
    const out = await g3HeadlessProvider(SOE)
    expect(out).toEqual({ sections: [{ section: '八、9', rows: 3, kept: 0 }] })
    const sent = h.post.mock.calls[0][1]
    expect(JSON.stringify(sent)).toBe(JSON.stringify(await tabPayload('soe')))
    expect(sent.sub_table_data['应收股利'][0]).toMatchObject({ label: '丙公司', end_balance: 150, current_change: -50 })
  })

  it('口径不适用回空，不发请求', async () => {
    expect(await g3HeadlessProvider({ ...SOE, applicableStandards: ['listed_standalone'] })).toEqual({ sections: [] })
    expect(await g3HeadlessProvider({ ...LISTED, applicableStandards: ['soe_standalone'] })).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('抽出的表格读取与原实现同口径：无表格 / 坏 JSON / 空数组 ⇒ 一行空占位，缺 id 的行补 id', () => {
    for (const raw of [null, undefined, '', '{坏', '[]', '{"a":1}']) {
      const listed = loadG3ListedDisclosureRows(raw)
      expect(listed).toHaveLength(1)
      expect(listed[0]).toMatchObject({ investeeName: '', openingBalance: 0, currentIncrease: 0, currentDecrease: 0, remark: '' })
      expect(listed[0].id).toMatch(/^dl-/)
      const soe = loadG3SoeDisclosureRows(raw)
      expect(soe).toHaveLength(1)
      expect(soe[0]).toMatchObject({ investeeName: '', openingBalance: 0, currentChange: 0, remark: '' })
      expect(soe[0].id).toMatch(/^ds-/)
    }
    const rows = loadG3ListedDisclosureRows('[{"investeeName":"甲","openingBalance":5},{"id":"keep","investeeName":"乙"}]')
    expect(rows[0]).toMatchObject({ investeeName: '甲', openingBalance: 5, currentIncrease: 0, remark: '' })
    expect(rows[0].id).toMatch(/^dl-/)
    expect(rows[1].id).toBe('keep')
  })

  it('静态接线：两个 Tab 用同一个状态 composable 与 builder，不再内联读取', () => {
    const dir = resolve(__dirname, '../../g3-dividend-receivable')
    for (const [file, variant, build] of [
      ['G3TabDisclosureListed.vue', 'listed', 'buildG3ListedSyncPayloads'],
      ['G3TabDisclosureSOE.vue', 'soe', 'buildG3SoeSyncPayloads'],
    ]) {
      const src = readFileSync(resolve(dir, file), 'utf-8')
      expect(src, file).toContain(`useG3DisclosureState('${variant}', toRef(props, 'allResponses'))`)
      expect(src, file).toMatch(new RegExp(`${build}\\(\\s*props\\.wpId,\\s*props\\.applicableStandards,\\s*tableRows\\.value,\\s*noteText\\.value,?\\s*\\)`))
      expect(src, file).not.toMatch(/function loadTableRows|JSON\.parse\(raw\)/)
    }
  })
})
