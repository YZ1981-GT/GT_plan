/**
 * H5 披露表离屏同步 = 国企披露 Tab 同一套代码（spec note-pull-followup-closure R1）。
 *
 * 判据：①离屏请求体与「Tab 刚打开时的口径：buildH5SoeSummaryRows(null, 响应) → h5SoeLayerTotals + 已保存文本
 * → buildH5SyncPayload」逐字节相同 ②上市口径无附注落点、汇总全 0（Tab 提示「请先填写」不同步）都回空
 * ③Tab 的汇总 / 空表判断 / 层级合计 / 文本读取调的就是这几个共用函数，持久化键与共用常量同值（静态接线）
 * ④只读 H5- 条目、静默发出、不写底稿。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: h.get, post: h.post, put: h.put } }))

import { h5HeadlessProvider } from '../h5HeadlessDisclosure'
import {
  H5_SOE_TEXT_ITEM,
  buildH5SoeSummaryRows,
  h5SoeLayerTotals,
  h5SoeSummaryIsEmpty,
  readH5SoeDisclosureText,
} from '../h5SoeDisclosureForm'
import { buildH5SyncPayload, H5_SOE_SUBTABLE } from '../h5NoteSectionMap'

const RESPONSES = [
  { item_id: 'H5-1-cost-rows', remark: JSON.stringify([{ name: '探明矿区权益', audited: 8000 }, { name: '井及相关设施', audited: 2000 }]), conclusion: null },
  { item_id: 'H5-1-depletion-rows', remark: JSON.stringify([{ name: '探明矿区权益', audited: 1500 }]), conclusion: null },
  { item_id: H5_SOE_TEXT_ITEM, remark: '本期产能利用率 86%', conclusion: null },
  { item_id: 'H6-1-rows', remark: '[]', conclusion: null },
]
const OWN = new Map(RESPONSES.filter((r) => r.item_id.startsWith('H5-')).map((r) => [r.item_id, r]))
const CTX = { projectId: 'p1', year: 2025, wpId: 'wp-h5', wpCode: 'H5', applicableStandards: ['soe_standalone'] }
const WP = resolve(__dirname, '../..')

describe('h5HeadlessProvider', () => {
  beforeEach(() => {
    for (const fn of Object.values(h)) fn.mockReset()
    h.get.mockResolvedValue(RESPONSES)
    h.post.mockResolvedValue({ rows_synced: 16, push_kept: [] })
  })

  it('国企：载荷与 Tab 同一套函数逐字节相同，静默发出、不写底稿', async () => {
    const out = await h5HeadlessProvider({ ...CTX, variant: 'soe' })
    expect(out).toEqual({ sections: [{ section: '八、25', rows: 16, kept: 0 }] })
    expect(h.get).toHaveBeenCalledWith('/api/workpapers/wp-h5/checklist-responses', expect.anything())
    expect(h.put).not.toHaveBeenCalled()
    const [url, sent, cfg] = h.post.mock.calls[0]
    expect(url).toBe('/api/projects/p1/disclosure-notes/sync-from-workpaper')
    expect(cfg).toMatchObject({ _silent: true })
    const rows = buildH5SoeSummaryRows(null, OWN)
    const expected = buildH5SyncPayload({
      wpId: 'wp-h5', projectId: 'p1', year: 2025, layerTotals: h5SoeLayerTotals(rows), soeDisclosureText: readH5SoeDisclosureText(OWN),
    })
    expect(JSON.stringify(sent)).toBe(JSON.stringify(expected))
    const main = sent.sub_table_data[H5_SOE_SUBTABLE.main] as Array<{ label: string; end: number | null }>
    expect(main.find((r) => r.label === '一、原价合计')?.end).toBe(10000)
    expect(main.find((r) => r.label === '四、油气资产账面价值合计')?.end).toBe(8500)
    expect(JSON.stringify(sent.sub_table_data._note_texts)).toContain('产能利用率')
  })

  it('上市口径没有附注落点：不发请求、回空', async () => {
    expect(await h5HeadlessProvider({ ...CTX, variant: 'listed', applicableStandards: ['listed_standalone'] }))
      .toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('汇总全 0（Tab 提示「请先填写披露数据」不同步）：回空', async () => {
    h.get.mockResolvedValue([{ item_id: H5_SOE_TEXT_ITEM, remark: '仅文本', conclusion: null }])
    expect(h5SoeSummaryIsEmpty(buildH5SoeSummaryRows(null, new Map()))).toBe(true)
    expect(await h5HeadlessProvider({ ...CTX, variant: 'soe' })).toEqual({ sections: [] })
    expect(h.post).not.toHaveBeenCalled()
  })

  it('静态接线：国企 Tab 调同一组共用函数，持久化键与共用常量同值', () => {
    const tab = readFileSync(resolve(WP, 'h5/core/H5TabDisclosureSoe.vue'), 'utf-8')
    expect(tab).toContain('computed(() => buildH5SoeSummaryRows(adjudicatedData.value, props.allResponses))')
    expect(tab).toContain('if (h5SoeSummaryIsEmpty(rows))')
    expect(tab).toContain('layerTotals: h5SoeLayerTotals(rows)')
    expect(tab).toContain('readH5SoeDisclosureText(props.allResponses)')
    expect(/const H5_SOE_TEXT_ITEM = '([^']+)'/.exec(tab)?.[1]).toBe(H5_SOE_TEXT_ITEM)
  })
})
