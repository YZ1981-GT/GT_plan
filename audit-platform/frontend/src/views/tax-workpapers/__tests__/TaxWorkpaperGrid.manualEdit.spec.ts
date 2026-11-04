/**
 * 税审底稿表格：账号「允许修改」关闭时的可点范围（spec citar-manual-edit-permission R2 / R3）。
 * 与后端 tax_workpaper_service.is_auto_cell 同一口径：公式格、样表预置数字、自动取数格只读；
 * 手填格与「需人工填写」的取数格照常可填。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TaxWorkpaperGrid from '../TaxWorkpaperGrid.vue'
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

  it('未开通：只剩手填格与「需人工填写」的取数格；点公式格不打开编辑框', async () => {
    const w = mountGrid(false)
    expect(editable(w)).toEqual(['D9', 'F10'])
    const tds = w.findAll('td')
    await tds[3].trigger('click')
    expect(w.find('input').exists()).toBe(false)
    expect(tds[3].attributes('title')).toContain('未开通「允许修改」')
    await tds[2].trigger('click')
    expect(w.find('input').exists()).toBe(true)
    expect(w.find('.tw-grid__restore').exists()).toBe(false)
  })
})
