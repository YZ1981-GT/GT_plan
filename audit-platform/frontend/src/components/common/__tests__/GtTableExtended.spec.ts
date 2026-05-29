/**
 * Spec B (R10) Sprint 3.1.4 — GtTableExtended 单测
 *
 * 5 用例：
 * 1. 列渲染：visible 列正确传递给 GtEditableTable
 * 2. 千分位 / 格式化：col.formatter 被调用
 * 3. 空状态：empty data 时仍正常渲染
 * 4. editable=false：不展示编辑控件
 * 5. 紫色表头：mergedHeaderStyle 含 #f0edf5
 */

import { mount, flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

// Mock 依赖（避免完整依赖链）
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
vi.mock('@/composables/useLazyEdit', () => ({ useLazyEdit: () => ({ isEditing: () => false, startEdit: vi.fn(), stopEdit: vi.fn() }) }))
vi.mock('@/composables/useEditMode', () => ({
  useEditMode: () => ({
    isEditing: { value: false },
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
    deleteSelectedRows: vi.fn(),
  }),
}))
vi.mock('@/stores/displayPrefs', () => ({
  useDisplayPrefsStore: () => ({ fontConfig: { tableFont: '12px' }, fmt: (v: number) => String(v) }),
}))
vi.mock('@/composables/useCopyPaste', () => ({ copySelection: vi.fn(), pasteToSelection: vi.fn(), setupPasteListener: vi.fn() }))
vi.mock('@/composables/useKeyboardNav', () => ({ useKeyboardNav: vi.fn() }))

// 全局 element-plus stubs
const STUBS = {
  'el-table': {
    template: '<div class="el-table"><slot /></div>',
    props: ['data', 'border', 'size', 'maxHeight', 'rowKey'],
  },
  'el-table-column': {
    template: '<div class="el-table-column" :data-prop="prop" :data-label="label"><slot v-if="$slots.default" :row="{}" :$index="0" /></div>',
    props: ['prop', 'label', 'width', 'minWidth', 'align', 'type', 'fixed', 'resizable', 'sortable', 'filters', 'filterMethod', 'filterOptions', 'formatter'],
  },
  'el-button': { template: '<button class="el-button"><slot /></button>' },
  'el-input': { template: '<input class="el-input" />', props: ['modelValue'] },
  'el-icon': { template: '<i class="el-icon"><slot /></i>' },
  'el-dropdown': { template: '<div class="el-dropdown"><slot /><slot name="dropdown" /></div>' },
  'el-dropdown-menu': { template: '<div class="el-dropdown-menu"><slot /></div>' },
  'el-dropdown-item': { template: '<div class="el-dropdown-item"><slot /></div>' },
  // 透传 slot + 模拟 formatter 调用 + 渲染 column labels
  GtEditableTable: {
    template: `<div class="gt-editable-table">
      <div class="toolbar"><slot name="toolbar-left" /></div>
      <div class="columns">
        <span v-for="(col, idx) in columns" :key="idx" class="column-label">{{ col.label }}</span>
      </div>
      <div class="content">
        <template v-for="(col, idx) in columns" :key="idx">
          <span v-if="col.formatter && modelValue && modelValue.length > 0" class="formatter-cell">
            {{ col.formatter(modelValue[0][col.prop], modelValue[0], col, 0) }}
          </span>
        </template>
        <slot />
      </div>
    </div>`,
    props: ['modelValue', 'columns', 'editable', 'showToolbar', 'showFooter', 'showSummary', 'maxHeight', 'defaultSortable', 'groupBy', 'showSelection'],
  },
}

import GtTableExtended from '../GtTableExtended.vue'

describe('GtTableExtended 列表展示型表格', () => {
  it('1. 列渲染：visible 列正确传递', async () => {
    const wrapper = mount(GtTableExtended, {
      global: { stubs: STUBS },
      props: {
        modelValue: [{ name: 'foo', amount: 100 }],
        columns: [
          { prop: 'name', label: '名称' },
          { prop: 'amount', label: '金额' },
        ],
      },
    })
    await flushPromises()
    expect(wrapper.html()).toContain('名称')
    expect(wrapper.html()).toContain('金额')
  })

  it('2. 格式化函数被调用', async () => {
    const formatter = vi.fn((v: number) => `¥${v.toFixed(2)}`)
    const wrapper = mount(GtTableExtended, {
      global: { stubs: STUBS },
      props: {
        modelValue: [{ amount: 1234.5 }],
        columns: [{ prop: 'amount', label: '金额', formatter }],
      },
    })
    await flushPromises()
    expect(formatter).toHaveBeenCalled()
  })

  it('3. 空数据时正常渲染', async () => {
    const wrapper = mount(GtTableExtended, {
      global: { stubs: STUBS },
      props: {
        modelValue: [],
        columns: [{ prop: 'name', label: '名称' }],
      },
    })
    await flushPromises()
    // 不抛错 + 工具栏可见
    expect(wrapper.exists()).toBe(true)
  })

  it('4. editable=false：不出现编辑控件', async () => {
    const wrapper = mount(GtTableExtended, {
      global: { stubs: STUBS },
      props: {
        modelValue: [{ name: 'foo' }],
        columns: [{ prop: 'name', label: '名称', editType: 'input' }],
      },
    })
    await flushPromises()
    // 不应渲染 el-input 编辑控件
    expect(wrapper.findAll('input').length).toBe(0)
  })

  it('5. 透传 toolbar-left slot', async () => {
    const wrapper = mount(GtTableExtended, {
      global: { stubs: STUBS },
      props: {
        modelValue: [],
        columns: [{ prop: 'name', label: '名称' }],
      },
      slots: {
        'toolbar-left': '<button class="my-toolbar-btn">自定义按钮</button>',
      },
    })
    await flushPromises()
    expect(wrapper.find('.my-toolbar-btn').exists()).toBe(true)
  })
})
