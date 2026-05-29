/**
 * GtBIndex.spec.ts — B 类底稿目录组件单元测试
 *
 * spec workpaper-html-renderer Task 5.3
 *
 * 验证：
 * 1. 编制信息从 project meta 自动填充（entity_name / period_end / preparer 等）
 * 2. project meta 缺失时友好降级（显示 '—' 占位）
 * 3. 索引导航行点击 GtIndexChip → emit jump-to-section
 * 4. "无需打印" toggle → 更新 row.no_print + 触发 debounce save
 * 5. 批量切换"无需打印"：所有选中行同步切换
 *
 * Validates: Requirements 3.3（B 类 148 sheet 编制信息自动填充 + 索引导航跳转）
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import GtBIndex, { type BIndexSchema } from '../GtBIndex.vue'

// Mock GtIndexChip - simple stub that emits click on click
vi.mock('@/components/workpaper/GtIndexChip.vue', () => ({
  default: {
    name: 'GtIndexChip',
    template:
      '<span class="gt-index-chip-mock" @click="$emit(\'click\', { ns: \'wp\', target: value, layer: 3 })">{{ value }}</span>',
    props: ['value', 'validate'],
    emits: ['click'],
  },
}))

const globalStubs = {
  'el-descriptions': {
    template: '<div class="el-descriptions"><slot /></div>',
    props: ['title', 'column', 'border', 'size'],
  },
  'el-descriptions-item': {
    template: '<div class="el-descriptions-item" :data-label="label"><slot /></div>',
    props: ['label', 'span'],
  },
  'el-table': {
    template: '<div class="el-table"><slot /></div>',
    props: ['data', 'border', 'rowKey'],
    emits: ['selection-change'],
    methods: {
      clearSelection() {
        // no-op stub for el-table.clearSelection
      },
    },
  },
  'el-table-column': {
    template:
      '<div class="el-table-column" :data-label="label" :data-prop="prop"><slot v-if="$slots.default" :row="firstRow" /></div>',
    props: ['type', 'label', 'prop', 'width', 'minWidth', 'align', 'resizable'],
    computed: {
      firstRow(): Record<string, any> {
        const self = this as any
        const data = self.$parent?.$attrs?.data || self.$parent?.data || []
        return Array.isArray(data) && data.length ? data[0] : {}
      },
    },
  },
  'el-button': {
    template:
      '<button class="el-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'disabled'],
    emits: ['click'],
  },
  'el-switch': {
    template:
      '<input type="checkbox" class="el-switch" :checked="modelValue" :disabled="disabled" @change="$emit(\'update:modelValue\', $event.target.checked); $emit(\'change\', $event.target.checked)" />',
    props: ['modelValue', 'disabled', 'size'],
    emits: ['update:modelValue', 'change'],
  },
}

function buildSchema(): BIndexSchema {
  return {
    component_type: 'b-index',
    preparation_info_fields: [
      { field: 'entity_name', label: '被审计单位' },
      { field: 'period_end', label: '截止日' },
      { field: 'preparer', label: '编制人' },
      { field: 'prep_date', label: '编制日期' },
      { field: 'reviewer', label: '复核人' },
      { field: 'review_date', label: '复核日期' },
      { field: 'accounting_period', label: '会计期间' },
    ],
    navigation_table: {
      columns: ['seq', 'content', 'index_ref', 'no_print'],
    },
  }
}

function buildHtmlData() {
  return {
    preparation_info: {
      entity_name: '宜宾大药房有限公司',
      period_end: '2025年12月31日',
      preparer: '张三',
      prep_date: '2026.1.10',
      reviewer: '李四',
      review_date: '2026.1.15',
      accounting_period: '2025年度',
    },
    navigation_rows: [
      { seq: 1, content: '应收账款审定表', index_ref: 'D2-1', no_print: false },
      { seq: 2, content: '应收账款实质性程序', index_ref: 'D2A', no_print: false },
      { seq: 3, content: '账龄分析表', index_ref: 'D2-9', no_print: true },
    ],
  }
}

describe('GtBIndex — 编制信息自动填充', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('preparation_info 完整时正确渲染各字段', () => {
    const wrapper = mount(GtBIndex, {
      props: {
        wpId: 'wp-001',
        sheetName: '底稿目录',
        schema: buildSchema(),
        htmlData: buildHtmlData(),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.preparationInfo.entity_name).toBe('宜宾大药房有限公司')
    expect(vm.preparationInfo.period_end).toBe('2025年12月31日')
    expect(vm.preparationInfo.preparer).toBe('张三')
    expect(vm.preparationInfo.reviewer).toBe('李四')
    expect(vm.preparationInfo.accounting_period).toBe('2025年度')
  })

  it('preparation_info 缺失时友好降级（显示 "—"）', () => {
    const wrapper = mount(GtBIndex, {
      props: {
        wpId: 'wp-001',
        sheetName: '底稿目录',
        schema: buildSchema(),
        // htmlData without preparation_info
        htmlData: { navigation_rows: [] } as any,
      },
      global: { stubs: globalStubs },
    })

    // Template renders `{{ preparationInfo.entity_name || '—' }}` so all items
    // should fall back to '—'. Verify the rendered HTML contains the placeholder.
    expect(wrapper.html()).toContain('—')
    const vm = wrapper.vm as any
    expect(vm.preparationInfo.entity_name).toBeUndefined()
    expect(vm.preparationInfo.period_end).toBeUndefined()
  })

  it('部分字段缺失时仅缺失字段降级（其他字段正常显示）', () => {
    const partial = {
      preparation_info: {
        entity_name: '宜宾大药房有限公司',
        // period_end missing
        preparer: '张三',
      },
      navigation_rows: [],
    }
    const wrapper = mount(GtBIndex, {
      props: {
        wpId: 'wp-001',
        sheetName: '底稿目录',
        schema: buildSchema(),
        htmlData: partial,
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.preparationInfo.entity_name).toBe('宜宾大药房有限公司')
    expect(vm.preparationInfo.preparer).toBe('张三')
    expect(vm.preparationInfo.period_end).toBeUndefined()
    // The placeholder '—' should be present for missing field
    expect(wrapper.html()).toContain('—')
  })

  it('preparation_info 字段为空字符串时降级到 "—"', () => {
    const data = {
      preparation_info: {
        entity_name: '',
        period_end: '',
        preparer: '',
      },
      navigation_rows: [],
    }
    const wrapper = mount(GtBIndex, {
      props: {
        wpId: 'wp-001',
        sheetName: '底稿目录',
        schema: buildSchema(),
        htmlData: data,
      },
      global: { stubs: globalStubs },
    })

    // Empty string is falsy, so the `||` operator falls back to '—'
    expect(wrapper.html()).toContain('—')
  })
})

describe('GtBIndex — 索引导航行跳转', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('handleIndexChipClick 触发 jump-to-section emit 携带索引值', async () => {
    const wrapper = mount(GtBIndex, {
      props: {
        wpId: 'wp-001',
        sheetName: '底稿目录',
        schema: buildSchema(),
        htmlData: buildHtmlData(),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.handleIndexChipClick('D2-1')
    await nextTick()

    const emitted = wrapper.emitted('jump-to-section')
    expect(emitted).toBeDefined()
    expect(emitted!.length).toBe(1)
    expect(emitted![0][0]).toBe('D2-1')
  })

  it('多次点击不同索引发出多个 jump-to-section 事件', async () => {
    const wrapper = mount(GtBIndex, {
      props: {
        wpId: 'wp-001',
        sheetName: '底稿目录',
        schema: buildSchema(),
        htmlData: buildHtmlData(),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.handleIndexChipClick('D2-1')
    vm.handleIndexChipClick('D2A')
    vm.handleIndexChipClick('D2-9')
    await nextTick()

    const emitted = wrapper.emitted('jump-to-section')
    expect(emitted).toBeDefined()
    expect(emitted!.length).toBe(3)
    expect(emitted!.map((e: any[]) => e[0])).toEqual(['D2-1', 'D2A', 'D2-9'])
  })

  it('navigationRows 初始化包含完整的索引数据', () => {
    const wrapper = mount(GtBIndex, {
      props: {
        wpId: 'wp-001',
        sheetName: '底稿目录',
        schema: buildSchema(),
        htmlData: buildHtmlData(),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.navigationRows.length).toBe(3)
    expect(vm.navigationRows[0].index_ref).toBe('D2-1')
    expect(vm.navigationRows[1].index_ref).toBe('D2A')
    expect(vm.navigationRows[2].no_print).toBe(true)
  })
})

describe('GtBIndex — "无需打印" 切换 + 保存', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('handleNoPrintChange 触发 debounce save', async () => {
    const wrapper = mount(GtBIndex, {
      props: {
        wpId: 'wp-001',
        sheetName: '底稿目录',
        schema: buildSchema(),
        htmlData: buildHtmlData(),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.navigationRows[0].no_print = true
    vm.handleNoPrintChange(vm.navigationRows[0])
    await nextTick()

    // Save not yet emitted (debounce 1.5s)
    expect(wrapper.emitted('save')).toBeUndefined()

    // Advance timer beyond debounce
    vi.advanceTimersByTime(1600)
    await nextTick()

    const emitted = wrapper.emitted('save')
    expect(emitted).toBeDefined()
    const payload = emitted![0][0] as any
    expect(payload.navigation_rows[0].no_print).toBe(true)
    expect(payload.preparation_info.entity_name).toBe('宜宾大药房有限公司')
  })

  it('readonly 模式不触发 save', async () => {
    const wrapper = mount(GtBIndex, {
      props: {
        wpId: 'wp-001',
        sheetName: '底稿目录',
        schema: buildSchema(),
        htmlData: buildHtmlData(),
        readonly: true,
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.navigationRows[0].no_print = true
    vm.handleNoPrintChange(vm.navigationRows[0])
    vi.advanceTimersByTime(1600)
    await nextTick()

    expect(wrapper.emitted('save')).toBeUndefined()
  })

  it('batchToggleNoPrint 批量更新所有选中行', async () => {
    const wrapper = mount(GtBIndex, {
      props: {
        wpId: 'wp-001',
        sheetName: '底稿目录',
        schema: buildSchema(),
        htmlData: buildHtmlData(),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    // Manually set selectedRows then trigger batch toggle
    vm.selectedRows = [vm.navigationRows[0], vm.navigationRows[1]]
    // Both currently have no_print=false, so batch toggle should set both to true
    vm.batchToggleNoPrint()
    await nextTick()

    expect(vm.navigationRows[0].no_print).toBe(true)
    expect(vm.navigationRows[1].no_print).toBe(true)
    // Selection cleared after batch action
    expect(vm.selectedRows.length).toBe(0)

    vi.advanceTimersByTime(1600)
    await nextTick()
    expect(wrapper.emitted('save')).toBeDefined()
  })

  it('handleSelectionChange 更新 selectedRows', async () => {
    const wrapper = mount(GtBIndex, {
      props: {
        wpId: 'wp-001',
        sheetName: '底稿目录',
        schema: buildSchema(),
        htmlData: buildHtmlData(),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    const selection = [vm.navigationRows[0], vm.navigationRows[2]]
    vm.handleSelectionChange(selection)
    await nextTick()

    expect(vm.selectedRows.length).toBe(2)
    expect(vm.selectedRows[0].seq).toBe(1)
    expect(vm.selectedRows[1].seq).toBe(3)
  })
})

describe('GtBIndex — htmlData 响应式同步', () => {
  it('props.htmlData 变化时重新初始化数据', async () => {
    const wrapper = mount(GtBIndex, {
      props: {
        wpId: 'wp-001',
        sheetName: '底稿目录',
        schema: buildSchema(),
        htmlData: buildHtmlData(),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.preparationInfo.entity_name).toBe('宜宾大药房有限公司')

    await wrapper.setProps({
      htmlData: {
        preparation_info: { entity_name: '新单位', period_end: '2026-12-31' },
        navigation_rows: [{ seq: 1, content: '新行', index_ref: 'X1', no_print: false }],
      },
    })
    await nextTick()

    expect(vm.preparationInfo.entity_name).toBe('新单位')
    expect(vm.navigationRows.length).toBe(1)
    expect(vm.navigationRows[0].index_ref).toBe('X1')
  })
})
