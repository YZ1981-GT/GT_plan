/**
 * FormulaRefPicker：附注 / 报表行插入登记的引用写法；被截断的域不当成完整的（spec formula-fetch-and-wp-generation-defect-closure R3）。
 *
 * 原先一律拼 `NOTE(章节,'合计','期末')` / `REPORT(行次,'期末')`：附注登记的列名是表头原文（如「期末余额」）、
 * 利润表登记的是「本期 / 上期」⇒ 地址库有数之后从选择器插入的引用，保存时都判悬空。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { defineComponent, nextTick } from 'vue'

if (!(globalThis as any).ResizeObserver) {
  ;(globalThis as any).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
}

const { mockHttpGet, mockListSheets } = vi.hoisted(() => ({ mockHttpGet: vi.fn(), mockListSheets: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: mockHttpGet, post: vi.fn() } }))
vi.mock('@/services/acnr/useAcnr', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/acnr/useAcnr')>()
  return {
    ...actual,
    useAcnr: () => ({
      listSheets: mockListSheets,
      listCells: vi.fn().mockResolvedValue([]),
      resolveUri: vi.fn(),
      resolveFormula: vi.fn(),
      clearCache: vi.fn(),
    }),
  }
})

import ElementPlus, { ElTabs } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import FormulaRefPicker from '../FormulaRefPicker.vue'
import { useAddressRegistry } from '@/stores/addressRegistry'

const ElDialogStub = defineComponent({
  name: 'ElDialog',
  props: { modelValue: { type: Boolean, default: false } },
  template: '<div class="el-dialog-stub"><slot /><slot name="footer" /></div>',
})
const ElTableStub = defineComponent({
  name: 'ElTable',
  props: { data: { type: Array, default: () => [] } },
  emits: ['row-click'],
  template: '<div class="el-table-stub"><slot /></div>',
})
const ElSelectStub = defineComponent({
  name: 'ElSelect',
  props: { modelValue: { type: [String, Number], default: '' } },
  emits: ['update:modelValue', 'change'],
  template: '<div class="el-select-stub"><slot /></div>',
})
const STUBS = { ElDialog: ElDialogStub, ElTable: ElTableStub, ElSelect: ElSelectStub, ElOption: true, ElTableColumn: true }

function entry(over: Record<string, unknown>) {
  return { uri: '', source: '', path: '', cell: '', label: '', formula_ref: '', jump_route: '', ...over }
}

const NOTE_ENTRY = entry({
  uri: 'note://八、1/合计#期末余额', domain: 'note', note_section: '八、1', path: '合计', cell: '期末余额',
  label: '附注 > 货币资金 > 货币资金 > 合计 > 期末余额', formula_ref: "NOTE('八、1','合计','期末余额')",
})
const REPORT_ENTRIES = [
  entry({ domain: 'report', row_code: 'BS-002', cell: '期末', label: '资产负债表 > 货币资金 > 期末', formula_ref: "REPORT('BS-002','期末')" }),
  entry({ domain: 'report', row_code: 'BS-002', cell: '期初', label: '资产负债表 > 货币资金 > 期初', formula_ref: "REPORT('BS-002','期初')" }),
  entry({ domain: 'report', row_code: 'IS-001', cell: '本期', label: '利润表 > 营业收入 > 本期', formula_ref: "REPORT('IS-001','本期')" }),
  entry({ domain: 'report', row_code: 'IS-001', cell: '上期', label: '利润表 > 营业收入 > 上期', formula_ref: "REPORT('IS-001','上期')" }),
]

async function loadStore(items: unknown[], extra: Record<string, unknown> = {}) {
  mockHttpGet.mockResolvedValueOnce({ data: { items, total: items.length, returned: items.length, truncated: false, truncated_domains: [], ...extra } })
  const store = useAddressRegistry()
  await store.refresh('p1', 2025, 'soe')
  return store
}

function mountPicker(props: Record<string, unknown> = {}): VueWrapper {
  return mount(FormulaRefPicker, {
    props: { modelValue: true, reportRows: [], tbRows: [], noteRows: [], ...props },
    global: { plugins: [ElementPlus], stubs: STUBS },
  })
}

function tableWith(wrapper: VueWrapper, key: string) {
  return wrapper.findAllComponents(ElTableStub).find((t) => {
    const data = t.props('data') as any[]
    return data.length > 0 && key in data[0]
  })
}

async function pickAndInsert(wrapper: VueWrapper, table: VueWrapper<any>, row: unknown): Promise<string> {
  table.vm.$emit('row-click', row)
  await nextTick()
  await wrapper.findAll('button').find((b) => b.text().includes('插入'))!.trigger('click')
  return wrapper.emitted('insert')![0][0] as string
}

describe('FormulaRefPicker 插入登记的引用写法', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    mockHttpGet.mockReset()
    mockListSheets.mockReset()
    mockListSheets.mockResolvedValue([])
  })
  afterEach(() => useAddressRegistry().dispose())

  it('附注：插入地址库登记的 NOTE 写法（列名 = 表头原文），不再拼「期末」', async () => {
    await loadStore([NOTE_ENTRY])
    const wrapper = mountPicker()
    wrapper.findComponent(ElTabs).vm.$emit('update:modelValue', 'note')
    await flushPromises()
    const table = tableWith(wrapper, 'note_section')!
    expect(table.props('data')).toHaveLength(1)
    expect(await pickAndInsert(wrapper, table, NOTE_ENTRY)).toBe("NOTE('八、1','合计','期末余额')")
    wrapper.unmount()
  })

  it('报表：按期间列过滤（期末 ↔ 期末 / 本期），利润表行插入登记的「本期」写法', async () => {
    await loadStore(REPORT_ENTRIES)
    const wrapper = mountPicker()
    await flushPromises()
    const table = tableWith(wrapper, 'row_code')!
    const rows = table.props('data') as any[]
    expect(rows.map((r) => `${r.row_code}/${r.cell}`)).toEqual(['BS-002/期末', 'IS-001/本期'])
    expect(await pickAndInsert(wrapper, table, rows[1])).toBe("REPORT('IS-001','本期')")
    wrapper.unmount()
  })

  it('页面自带的行（没有登记写法）仍按选择拼写法', async () => {
    const wrapper = mountPicker({ reportRows: [{ row_code: 'BS-003', row_name: '应收票据' }] })
    await flushPromises()
    const table = tableWith(wrapper, 'row_code')!
    expect(await pickAndInsert(wrapper, table, { row_code: 'BS-003', row_name: '应收票据' })).toBe("REPORT('BS-003','期末')")
    wrapper.unmount()
  })

  it('附注域被加载上限截断：不用地址库的残缺列表，改用页面数据并提示', async () => {
    await loadStore([NOTE_ENTRY], { truncated: true, truncated_domains: ['note'], total: 60000 })
    const pageRows = [{ note_section: '八、2', section_title: '交易性金融资产' }]
    const wrapper = mountPicker({ noteRows: pageRows })
    wrapper.findComponent(ElTabs).vm.$emit('update:modelValue', 'note')
    await flushPromises()
    expect(tableWith(wrapper, 'note_section')!.props('data')).toEqual(pageRows)
    expect(wrapper.text()).toContain('附注只加载了一部分')
    wrapper.unmount()
  })

  it('只截断了辅助余额（选择器没有这个页签）：不提示', async () => {
    await loadStore([NOTE_ENTRY], { truncated: true, truncated_domains: ['aux'], total: 138669 })
    const wrapper = mountPicker()
    await flushPromises()
    expect(wrapper.text()).not.toContain('只加载了一部分')
    wrapper.unmount()
  })

  it('底稿域被截断：底稿页签回退旧地址库（ACNR 目录取不到）时才提示', async () => {
    await loadStore([NOTE_ENTRY], { truncated: true, truncated_domains: ['wp'], total: 60000 })
    const wrapper = mountPicker()
    await flushPromises()
    expect(wrapper.text()).not.toContain('只加载了一部分')
    wrapper.findComponent(ElTabs).vm.$emit('update:modelValue', 'wp')
    await flushPromises()
    expect(mockListSheets).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('底稿单元格只加载了一部分')
    wrapper.unmount()
  })

  it('底稿域被截断但 ACNR 目录可用：底稿页签不受影响，不提示', async () => {
    mockListSheets.mockResolvedValue([{ addr_id: 'D1/D1-1', parent_wp_code: 'D1', sheet_code: 'D1-1', sheet_name: '审定表' }])
    await loadStore([NOTE_ENTRY], { truncated: true, truncated_domains: ['wp'], total: 60000 })
    const wrapper = mountPicker()
    wrapper.findComponent(ElTabs).vm.$emit('update:modelValue', 'wp')
    await flushPromises()
    expect(mockListSheets).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).not.toContain('只加载了一部分')
    wrapper.unmount()
  })
})
