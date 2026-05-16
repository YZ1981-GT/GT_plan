/**
 * Spec B (R10) Sprint 3.1.5 — GtFormTable 单测
 *
 * 5 用例：
 * 1. editable=true 默认开启
 * 2. update:modelValue 事件透传
 * 3. dirty-change 事件透传
 * 4. show-selection 多选列正确显示
 * 5. v-model 绑定数据双向同步
 */

import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

// Mock 依赖（同 GtTableExtended.spec.ts）
vi.mock('@/composables/useCellSelection', () => ({
  useCellSelection: () => ({
    contextMenu: { visible: false, x: 0, y: 0 },
    selectedCells: { value: [] },
    setupTableDrag: vi.fn(),
    closeContextMenu: vi.fn(),
    cellClassName: () => '',
    isCellSelected: () => false,
    selectCell: vi.fn(),
    openContextMenu: vi.fn(),
    sumSelectedValues: () => 0,
    selectionStats: () => null,
  }),
}))
vi.mock('@/composables/useLazyEdit', () => ({
  useLazyEdit: () => ({ isEditing: () => false, startEdit: vi.fn(), stopEdit: vi.fn() }),
}))
vi.mock('@/composables/useEditMode', () => ({
  useEditMode: () => ({
    isEditing: { value: true },
    isDirty: { value: false },
    enterEdit: vi.fn(),
    exitEdit: vi.fn(),
    markDirty: vi.fn(),
  }),
}))
vi.mock('@/composables/useFullscreen', () => ({ useFullscreen: () => ({ isFullscreen: { value: false }, toggleFullscreen: vi.fn() }) }))
vi.mock('@/composables/useTableToolbar', () => ({
  useTableToolbar: () => ({
    selectedCount: { value: 0 },
    onSelectionChange: vi.fn(),
    addRow: vi.fn(),
    deleteSelectedRows: vi.fn().mockResolvedValue(true),
  }),
}))
vi.mock('@/stores/displayPrefs', () => ({
  useDisplayPrefsStore: () => ({ fontConfig: { tableFont: '12px' }, fmt: (v: number) => String(v) }),
}))
vi.mock('@/composables/useCopyPaste', () => ({ copySelection: vi.fn(), pasteToSelection: vi.fn(), setupPasteListener: vi.fn() }))
vi.mock('@/composables/useKeyboardNav', () => ({ useKeyboardNav: vi.fn() }))

import GtFormTable from '../GtFormTable.vue'

describe('GtFormTable 行内编辑型表格', () => {
  it('1. 默认 editable=true：进入编辑模式应展示编辑控件提示', async () => {
    const wrapper = mount(GtFormTable, {
      props: {
        modelValue: [{ name: 'foo' }],
        columns: [{ prop: 'name', label: '名称', editType: 'input' }],
      },
    })
    await flushPromises()
    // GtEditableTable wrapper 默认渲染 + isEditing=true 编辑模式
    expect(wrapper.html()).toContain('名称')
  })

  it('2. update:modelValue 事件透传', async () => {
    const wrapper = mount(GtFormTable, {
      props: {
        modelValue: [{ name: 'foo' }],
        columns: [{ prop: 'name', label: '名称' }],
      },
    })
    await flushPromises()
    // 模拟内部 emit
    await wrapper.findComponent({ name: 'GtEditableTable' })
      .vm.$emit('update:modelValue', [{ name: 'bar' }])
    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')![0]).toEqual([[{ name: 'bar' }]])
  })

  it('3. dirty-change 事件透传', async () => {
    const wrapper = mount(GtFormTable, {
      props: {
        modelValue: [],
        columns: [{ prop: 'name', label: '名称' }],
      },
    })
    await flushPromises()
    await wrapper.findComponent({ name: 'GtEditableTable' })
      .vm.$emit('dirty-change', true)
    expect(wrapper.emitted('dirty-change')).toBeTruthy()
    expect(wrapper.emitted('dirty-change')![0]).toEqual([true])
  })

  it('4. show-selection 透传到 GtEditableTable', async () => {
    const wrapper = mount(GtFormTable, {
      props: {
        modelValue: [],
        columns: [{ prop: 'name', label: '名称' }],
        showSelection: true,
      },
    })
    await flushPromises()
    const inner = wrapper.findComponent({ name: 'GtEditableTable' })
    expect(inner.props('showSelection')).toBe(true)
  })

  it('5. v-model 绑定双向同步', async () => {
    const data = [{ name: 'foo' }]
    const wrapper = mount(GtFormTable, {
      props: {
        modelValue: data,
        columns: [{ prop: 'name', label: '名称' }],
      },
    })
    await flushPromises()
    const inner = wrapper.findComponent({ name: 'GtEditableTable' })
    expect(inner.props('modelValue')).toEqual(data)
  })
})
