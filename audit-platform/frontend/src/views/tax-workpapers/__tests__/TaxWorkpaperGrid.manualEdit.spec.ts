/**
 * 税审底稿表格：账号「允许修改」关闭时整张表只读（spec citar-manual-edit-permission R2，2026-11-04 改为整表只读）。
 * 手填格、「需人工填写」格、取数格、公式格、预置数字都不可点、不出编辑框、不显示可点效果与「可修改」提示；
 * 数据来源的标记（手工修改、原公式值）照常显示。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TaxWorkpaperGrid from '../TaxWorkpaperGrid.vue'
import { taxCellHint } from '../taxCellHint'
import type { TaxWorkpaperCell } from '../taxWorkpaperSheets'

const ROWS: TaxWorkpaperCell[][] = [[
  { ref: 'D9', role: 'e' },
  { ref: 'D10', role: 'e' },
  { ref: 'F10', role: 'e' },
  { ref: 'G10', role: 'f' },
  { ref: 'H10', role: 'c', text: '25%' },
  { text: '项目' },
]]
const CELLS = {
  D9: { origin: 'rule' as const, status: 'manual' as const, rule: '人工判断' },
  D10: { origin: 'rule' as const, status: 'auto' as const, rule: '取数' },
  G10: { origin: 'input' as const, auto: { n: '1000' } },
}
const VALUES = { D10: { n: '1000' }, G10: { n: '5' } }

function mountGrid(manualEdit?: boolean) {
  return mount(TaxWorkpaperGrid, {
    props: { rows: ROWS, values: VALUES, cells: CELLS, drafts: {}, readonly: false, ...(manualEdit === undefined ? {} : { manualEdit }) },
  })
}

const editable = (w: ReturnType<typeof mountGrid>) =>
  w.findAll('td').map((td, i) => (td.classes().includes('tw-cell--editable') ? ROWS[0][i].ref : null)).filter(Boolean)

describe('TaxWorkpaperGrid — 允许修改', () => {
  it('缺省 / 允许：手填、取数、公式、预置值都可点', () => {
    expect(editable(mountGrid())).toEqual(['D9', 'D10', 'F10', 'G10', 'H10'])
    expect(editable(mountGrid(true))).toEqual(['D9', 'D10', 'F10', 'G10', 'H10'])
  })

  it('未开通：整张表只读，点哪格都不出编辑框，提示里没有「可修改」', async () => {
    const w = mountGrid(false)
    expect(editable(w)).toEqual([])
    for (const td of w.findAll('td')) await td.trigger('click')
    expect(w.find('input').exists()).toBe(false)
    // 原生 title 已去掉（提示改在悬浮来源卡片里，spec citar-cell-source-hover）
    expect(w.findAll('td').some(td => td.attributes('title'))).toBe(false)
    const hint = (i: number, manualEdit: boolean) =>
      taxCellHint({ cell: ROWS[0][i], meta: (CELLS as any)[ROWS[0][i].ref ?? ''], restored: false, manualEdit, readonly: false })
    const tips = ROWS[0].map((_, i) => hint(i, false) ?? '').join('\n')
    expect(tips).not.toContain('可修改')
    expect(tips).not.toContain('点击')
    // 数据来源标记照常：手工值带原公式值、手工修改底色
    expect(hint(3, false)).toContain('已手工修改，原公式值：')
    expect(w.findAll('td')[3].classes()).toContain('tw-cell--manual')
    // 允许时有「点击」提示
    expect(hint(3, true)).toContain('点击可改或恢复自动值')
    expect(hint(4, true)).toBe('样表预置值，点击可修改')
  })

  it('格子带来源键 {sheet}!{ref}，定位的格子高亮', () => {
    const w = mount(TaxWorkpaperGrid, {
      props: { rows: ROWS, values: VALUES, cells: CELLS, drafts: {}, readonly: false, sheet: '2-02', locatedRef: 'G10' },
    })
    const tds = w.findAll('td')
    expect(tds[0].attributes('data-src')).toBe('2-02!D9')
    expect(tds[5].attributes('data-src')).toBeUndefined()
    expect(tds[3].classes()).toContain('tw-cell--located')
    expect(tds[2].classes()).not.toContain('tw-cell--located')
  })
})
