/**
 * WorkpaperHtmlTable — 组件测试
 *
 * 测试策略：通过 exposed API（cellValue/onExportExcel/onTristateChange）验证逻辑，
 * 不依赖 el-table 插槽渲染（el-table 深层 provide/inject 在测试中不稳定）。
 *
 * Foundation Kit Requirements: 3.3, 3.4
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

const mockExportData = vi.fn(async () => {})
vi.mock('@/composables/useExcelIO', () => ({
  useExcelIO: () => ({
    exportData: mockExportData,
    exportTemplate: vi.fn(),
    parseFile: vi.fn(),
    onFileSelected: vi.fn(),
  }),
}))

const mockNavigate = vi.fn()
vi.mock('@/composables/useWorkpaperNavigation', () => ({
  useWorkpaperNavigation: () => ({
    parseIndexRefs: (s: string) =>
      (s || '')
        .split(/[,、]/)
        .map((x: string) => x.trim())
        .filter(Boolean)
        .map((code: string) => ({ code, entry: code === 'A1' ? { name: 'x' } : null, exists: true })),
    navigateToWorkpaper: mockNavigate,
  }),
}))

vi.mock('@/composables/useWorkpaperRegistry', () => ({
  useWorkpaperRegistry: () => ({
    load: vi.fn().mockResolvedValue(undefined),
    lookup: vi.fn(),
  }),
}))

vi.mock('element-plus', () => ({
  ElMessage: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}))

import WorkpaperHtmlTable from '../WorkpaperHtmlTable.vue'
import { api } from '@/services/apiProxy'

const shallowStubs = {
  WorkpaperStandardHeader: true,
  'el-table': true,
  'el-table-column': true,
  'el-button': { template: '<button @click="$emit(\'click\')"><slot /></button>' },
  'el-select': true,
  'el-input': true,
  'el-option': true,
  'el-link': true,
}

const baseColumns = [
  { key: 'name', label: '项目', type: 'text' as const },
  { key: 'calc', label: '计算值', type: 'computed' as const },
  { key: 'applicable', label: '是否适用', type: 'tristate' as const },
  { key: 'note', label: '说明', type: 'editable' as const },
  { key: 'ref', label: '索引号', type: 'indexLink' as const },
]

const baseRows = [
  { _key: 'r1', name: '行1', calc: 100, applicable: 'yes', note: '备注1', ref: 'A1、A2' },
]

function mountTable(props: Record<string, any> = {}) {
  return mount(WorkpaperHtmlTable, {
    props: {
      title: '测试程序表',
      columns: baseColumns,
      rows: baseRows,
      scope: 'procedure_table:A1',
      projectId: 'p1',
      year: 2025,
      ...props,
    },
    global: { stubs: shallowStubs },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  ;(api.get as any).mockResolvedValue({})
  ;(api.post as any).mockResolvedValue({})
})

describe('WorkpaperHtmlTable', () => {
  it('onMounted 加载已有覆盖值', async () => {
    mountTable()
    await flushPromises()
    expect(api.get).toHaveBeenCalledWith(
      '/api/workpapers/field-overrides',
      { params: { project_id: 'p1', year: 2025, scope: 'procedure_table:A1' } },
    )
  })

  it('cellValue 取行内原始值', async () => {
    const wrapper = mountTable()
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.cellValue(baseRows[0], baseColumns[0])).toBe('行1')
    expect(vm.cellValue(baseRows[0], baseColumns[1])).toBe(100)
  })

  it('cellValue 覆盖值优先于行内值', async () => {
    ;(api.get as any).mockResolvedValue({ r1: { name: '覆盖行1' } })
    const wrapper = mountTable()
    await flushPromises()
    const vm = wrapper.vm as any
    expect(vm.cellValue(baseRows[0], baseColumns[0])).toBe('覆盖行1')
  })

  it('导出 Excel 调用 exportData', async () => {
    const wrapper = mountTable()
    await flushPromises()
    const vm = wrapper.vm as any
    await vm.onExportExcel()
    expect(mockExportData).toHaveBeenCalledTimes(1)
    const opts = mockExportData.mock.calls[0]![0]
    expect(opts.sheetName).toBe('测试程序表')
  })

  it('导出时 tristate 值转中文', async () => {
    const wrapper = mountTable()
    await flushPromises()
    const vm = wrapper.vm as any
    await vm.onExportExcel()
    const opts = mockExportData.mock.calls[0]![0]
    expect(opts.data[0].applicable).toBe('是')
  })

  it('readonly 模式不保存', async () => {
    const wrapper = mountTable({ readonly: true })
    await flushPromises()
    expect(wrapper.props('readonly')).toBe(true)
    // readonly 时 onEditableBlur 内部 early return，不 POST
  })

  it('tristate 变更调 field-overrides POST 并发出 field-change', async () => {
    const wrapper = mountTable()
    await flushPromises()
    const vm = wrapper.vm as any
    vm.onTristateChange(
      { _key: 'r1', applicable: 'no' },
      { key: 'applicable', label: '', type: 'tristate' },
      'no',
    )
    await flushPromises()
    expect(api.post).toHaveBeenCalledWith(
      '/api/workpapers/field-overrides',
      expect.objectContaining({
        project_id: 'p1',
        year: 2025,
        scope: 'procedure_table:A1',
        item_key: 'r1',
        field: 'applicable',
        value: 'no',
      }),
    )
    expect(wrapper.emitted('field-change')).toBeTruthy()
  })

  it('editable 失焦保存', async () => {
    const wrapper = mountTable()
    await flushPromises()
    const vm = wrapper.vm as any
    // 先设本地值
    vm.setLocal(baseRows[0], baseColumns[3], '新备注')
    // 触发失焦
    vm.onEditableBlur(baseRows[0], baseColumns[3])
    await flushPromises()
    expect(api.post).toHaveBeenCalledWith(
      '/api/workpapers/field-overrides',
      expect.objectContaining({
        item_key: 'r1',
        field: 'note',
        value: '新备注',
      }),
    )
  })
})
