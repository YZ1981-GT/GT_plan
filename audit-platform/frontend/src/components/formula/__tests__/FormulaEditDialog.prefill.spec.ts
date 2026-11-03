/**
 * 公式编辑弹窗的「建议公式」预填（spec excel-style-table-editing 5.5 删公式管理行内编辑时发现）。
 *
 * 原状（可打红）：公式管理「应用建议」把建议公式写进行内编辑的三个缓冲（editFormula / editCategory /
 * editDescription）再打开本弹窗，而本弹窗只读 `row` ⇒ 提示「已预填建议公式到编辑弹窗」，弹窗里却是空的。
 * 现在由 `prefill` 传入：行还没有公式时带入，行已有公式时以行为准；预填不算未保存的修改。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, shallowMount } from '@vue/test-utils'
import ElementPlus from 'element-plus'

const { get, getNoteTree, listSheets } = vi.hoisted(() => ({
  get: vi.fn(), getNoteTree: vi.fn(), listSheets: vi.fn(),
}))
vi.mock('@/services/apiProxy', () => ({ api: { get } }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: {} }) }))
vi.mock('@/services/auditPlatformApi', () => ({ getDisclosureNoteTree: getNoteTree }))
vi.mock('@/services/acnr/useAcnr', () => ({ useAcnr: () => ({ listSheets, listCells: vi.fn(async () => []) }) }))
vi.mock('@/components/formula/FormulaDebugPanel.vue', () => ({ default: { template: '<div />' } }))

import FormulaEditDialog from '@/components/formula/FormulaEditDialog.vue'

type Prefill = { formula: string; category?: string; description?: string }

async function open(row: Record<string, unknown>, prefill?: Prefill | null) {
  const w = shallowMount(FormulaEditDialog, {
    props: { modelValue: false, row, prefill: prefill ?? null, projectId: 'p1', year: 2025 },
    global: { plugins: [ElementPlus], renderStubDefaultSlot: false },
  })
  await w.setProps({ modelValue: true })
  for (let i = 0; i < 4; i++) await flushPromises()
  return { w, s: (w.vm as any).$.setupState }
}

const dirtyEvents = (w: any): boolean[] => (w.emitted('dirty-change') || []).map((e: unknown[]) => e[0] as boolean)

describe('FormulaEditDialog 预填', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listSheets.mockResolvedValue([])
    get.mockResolvedValue({})
    getNoteTree.mockResolvedValue([])
  })

  it('行还没有公式：带入预填的公式与分类，不算未保存的修改', async () => {
    const { w, s } = await open(
      { row_code: 'BS-002', row_name: '货币资金', formula: '' },
      { formula: "TB('1001','期末余额')", category: 'logic_check' },
    )
    expect(s.formulas.map((f: any) => [f.expression, f.category, f.description])).toEqual([
      ["TB('1001','期末余额')", 'logic_check', ''],
    ])
    expect(dirtyEvents(w).at(-1)).toBe(false)
    w.unmount()
  })

  it('行已有公式：以行为准，预填不覆盖', async () => {
    const { w, s } = await open(
      { row_code: 'BS-002', row_name: '货币资金', formula: "TB('1002','期末余额')", formula_category: 'auto_calc' },
      { formula: "TB('1001','期末余额')", category: 'logic_check' },
    )
    expect(s.formulas.map((f: any) => [f.expression, f.category])).toEqual([["TB('1002','期末余额')", 'auto_calc']])
    w.unmount()
  })

  it('不传预填：空公式、默认自动运算（原行为）', async () => {
    const { w, s } = await open({ row_code: 'BS-002', row_name: '货币资金', formula: '' })
    expect(s.formulas.map((f: any) => [f.expression, f.category])).toEqual([['', 'auto_calc']])
    w.unmount()
  })
})
