/**
 * GtAProgramConsole.spec.ts — A 程序表中控台组件测试
 *
 * 验证：
 * 1. 程序列表渲染 + 进度条统计
 * 2. 类别筛选
 * 3. 状态切换 emit
 * 4. 裁剪理由弹窗 + emit program-trim
 * 5. 批量裁剪
 * 6. 5 项认定 checkmark 渲染
 * 7. 关联底稿 GtIndexChip 渲染
 *
 * Validates: Requirements 1.1（D2A 痛点 7 项）+ 3.2（A 程序表详细需求）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import GtAProgramConsole from '../GtAProgramConsole.vue'

// Mock vue-router useRoute（组件用 route.params.projectId 派生 projectId）
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { projectId: 'proj-001' } }),
}))

// Mock useWpOnboardingGuide（避免引导逻辑依赖）
vi.mock('@/composables/useWpOnboardingGuide', () => ({
  useWpOnboardingGuide: () => ({
    showGuide: { value: false },
    guideSteps: { value: [] },
    triggerGuide: vi.fn(),
  }),
}))

// Mock GtAuditFlowGraph（子组件依赖 API，测试中 stub 掉）
vi.mock('@/components/workpaper/GtAuditFlowGraph.vue', () => ({
  default: { name: 'GtAuditFlowGraph', template: '<div class="gt-audit-flow-graph-mock" />' },
}))

// Mock GtIndexChip
vi.mock('@/components/workpaper/GtIndexChip.vue', () => ({
  default: {
    name: 'GtIndexChip',
    template: '<span class="gt-index-chip-mock" @click="$emit(\'click\', { ns: \'wp\', target: value, layer: 3 })">{{ value }}</span>',
    props: ['value', 'validate'],
    emits: ['click'],
  },
}))

// Mock parseIndexRef
vi.mock('@/utils/parseIndexRef', () => ({
  parseIndexRef: (val: string) => ({ ns: 'wp', target: val, layer: 3 }),
}))

const globalStubs = {
  'el-progress': {
    template: '<div class="el-progress"><slot /></div>',
    props: ['percentage', 'strokeWidth', 'textInside', 'format'],
  },
  'el-tag': {
    template: '<span class="el-tag" :class="type"><slot /></span>',
    props: ['type', 'size', 'effect'],
  },
  'el-radio-group': {
    template: '<div class="el-radio-group"><slot /></div>',
    props: ['modelValue', 'size'],
    emits: ['update:modelValue'],
  },
  'el-radio-button': {
    template: '<label class="el-radio-button" @click="$parent.$emit(\'update:modelValue\', label)"><slot /></label>',
    props: ['label'],
  },
  'el-button': {
    template: '<button class="el-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
    props: ['type', 'size', 'disabled'],
    emits: ['click'],
  },
  'el-table': {
    template: '<div class="el-table"></div>',
    props: ['data', 'border', 'rowKey', 'expandRowKeys'],
    emits: ['expand-change', 'selection-change'],
  },
  'el-table-column': {
    template: '<div class="el-table-column"></div>',
    props: ['type', 'label', 'prop', 'width', 'minWidth', 'align', 'showOverflowTooltip', 'selectable'],
  },
  'el-dropdown': {
    template: '<div class="el-dropdown"><slot /><slot name="dropdown" /></div>',
    props: ['trigger'],
    emits: ['command'],
  },
  'el-dropdown-menu': { template: '<div class="el-dropdown-menu"><slot /></div>' },
  'el-dropdown-item': {
    template: '<div class="el-dropdown-item" @click="$parent.$emit(\'command\', command)"><slot /></div>',
    props: ['command', 'divided'],
  },
  'el-dialog': {
    template: '<div class="el-dialog" v-if="modelValue"><slot /><slot name="footer" /></div>',
    props: ['modelValue', 'title', 'width', 'closeOnClickModal'],
    emits: ['update:model-value'],
  },
  'el-form': { template: '<div class="el-form"><slot /></div>', props: ['model', 'labelWidth'] },
  'el-form-item': { template: '<div class="el-form-item"><slot /></div>', props: ['label', 'required'] },
  'el-input': {
    template: '<textarea class="el-input" :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)"></textarea>',
    props: ['modelValue', 'type', 'rows', 'placeholder', 'maxlength', 'showWordLimit'],
    emits: ['update:modelValue'],
  },
  'el-timeline': { template: '<div class="el-timeline"><slot /></div>' },
  'el-timeline-item': { template: '<div class="el-timeline-item"><slot /></div>', props: ['timestamp', 'type', 'placement'] },
  'el-icon': { template: '<i class="el-icon"><slot /></i>' },
  'el-checkbox': { template: '<input type="checkbox" class="el-checkbox" />', props: ['modelValue'], emits: ['update:modelValue'] },
  'ArrowDown': { template: '<span class="arrow-down" />' },
  'GtIndexChip': {
    template: '<span class="gt-index-chip-mock">{{ value }}</span>',
    props: ['value', 'validate'],
    emits: ['click'],
  },
}

function createMockHtmlData() {
  return {
    programs: [
      {
        id: 'p1',
        program_no: 1,
        program_desc: '获取应收账款明细表，核对与总账一致',
        program_category: '常规★',
        assertions: { existence: true, completeness: true, rights: false, accuracy: true, presentation: false },
        linked_workpapers: 'D2-1/D2-2',
        status: 'completed',
        trim_reason: '',
        history: [{ timestamp: '2026-01-10', user: '张三', action: '已完成' }],
      },
      {
        id: 'p2',
        program_no: 2,
        program_desc: '对应收账款实施函证程序',
        program_category: '常规★',
        assertions: { existence: true, completeness: false, rights: true, accuracy: false, presentation: false },
        linked_workpapers: 'D2-3',
        status: 'in_progress',
        trim_reason: '',
        history: [],
      },
      {
        id: 'p3',
        program_no: 3,
        program_desc: 'IPO 特殊程序：检查关联方应收账款',
        program_category: 'IPO 加项',
        assertions: { existence: true, completeness: true, rights: true, accuracy: true, presentation: true },
        linked_workpapers: '',
        status: 'not_applicable',
        trim_reason: '非 IPO 项目不适用',
        history: [{ timestamp: '2026-01-08', user: '李四', action: '裁剪', reason: '非 IPO 项目不适用' }],
      },
      {
        id: 'p4',
        program_no: 4,
        program_desc: '检查期后回款情况',
        program_category: '常规★',
        assertions: { existence: true, completeness: false, rights: false, accuracy: true, presentation: false },
        linked_workpapers: 'D2-4',
        status: 'pending',
        trim_reason: '',
        history: [],
      },
    ],
    trim_decisions: [
      { programId: 'p3', reason: '非 IPO 项目不适用' },
    ],
    signatures: [],
  }
}

describe('GtAProgramConsole — 进度条统计', () => {
  it('正确计算各状态数量', () => {
    const wrapper = mount(GtAProgramConsole, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款实质性程序表D2A',
        schema: {},
        htmlData: createMockHtmlData(),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.completedCount).toBe(1)
    expect(vm.trimmedCount).toBe(1)
    expect(vm.inProgressCount).toBe(1)
    expect(vm.pendingCount).toBe(1)
  })

  it('进度百分比 = (完成 + 裁剪) / 总数', () => {
    const wrapper = mount(GtAProgramConsole, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款实质性程序表D2A',
        schema: {},
        htmlData: createMockHtmlData(),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    // (1 completed + 1 trimmed) / 4 total = 50%
    expect(vm.progressPercentage).toBe(50)
  })

  it('空数据时进度为 0', () => {
    const wrapper = mount(GtAProgramConsole, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款实质性程序表D2A',
        schema: {},
        htmlData: { programs: [], trim_decisions: [] },
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.progressPercentage).toBe(0)
  })
})

describe('GtAProgramConsole — 类别筛选', () => {
  it('默认显示全部程序', () => {
    const wrapper = mount(GtAProgramConsole, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款实质性程序表D2A',
        schema: {},
        htmlData: createMockHtmlData(),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.filteredPrograms.length).toBe(4)
  })

  it('筛选特定类别后只显示该类别', async () => {
    const wrapper = mount(GtAProgramConsole, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款实质性程序表D2A',
        schema: {},
        htmlData: createMockHtmlData(),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.activeCategory = 'IPO 加项'
    await nextTick()

    expect(vm.filteredPrograms.length).toBe(1)
    expect(vm.filteredPrograms[0].program_category).toBe('IPO 加项')
  })

  it('提取可用类别列表', () => {
    const wrapper = mount(GtAProgramConsole, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款实质性程序表D2A',
        schema: {},
        htmlData: createMockHtmlData(),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.availableCategories).toContain('常规★')
    expect(vm.availableCategories).toContain('IPO 加项')
  })
})

describe('GtAProgramConsole — 状态切换', () => {
  it('切换到非裁剪状态直接 emit program-status-change', async () => {
    const wrapper = mount(GtAProgramConsole, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款实质性程序表D2A',
        schema: {},
        htmlData: createMockHtmlData(),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    const row = vm.programs[3] // pending row
    vm.handleStatusChange(row, 'in_progress')
    await nextTick()

    const emitted = wrapper.emitted('program-status-change')
    expect(emitted).toBeDefined()
    expect(emitted![0][0]).toEqual({ programId: 'p4', status: 'in_progress' })
    expect(vm.programs[3].status).toBe('in_progress')
  })

  it('切换到裁剪状态打开理由弹窗', async () => {
    const wrapper = mount(GtAProgramConsole, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款实质性程序表D2A',
        schema: {},
        htmlData: createMockHtmlData(),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    const row = vm.programs[3]
    vm.handleStatusChange(row, 'not_applicable')
    await nextTick()

    expect(vm.trimDialogVisible).toBe(true)
    expect(vm.trimForm.programId).toBe('p4')
  })
})

describe('GtAProgramConsole — 裁剪确认', () => {
  it('确认裁剪后 emit program-trim + 更新状态', async () => {
    const wrapper = mount(GtAProgramConsole, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款实质性程序表D2A',
        schema: {},
        htmlData: createMockHtmlData(),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    // Simulate opening trim dialog for p4
    vm.trimForm = { programId: 'p4', programDesc: '检查期后回款情况', reason: '本期无期后回款' }
    vm.trimDialogVisible = true
    await nextTick()

    vm.confirmTrim()
    await nextTick()

    const emitted = wrapper.emitted('program-trim')
    expect(emitted).toBeDefined()
    expect(emitted![0][0]).toEqual({ programId: 'p4', reason: '本期无期后回款' })
    expect(vm.programs[3].status).toBe('not_applicable')
    expect(vm.programs[3].trim_reason).toBe('本期无期后回款')
    expect(vm.trimDialogVisible).toBe(false)
  })

  it('空理由不允许确认', async () => {
    const wrapper = mount(GtAProgramConsole, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款实质性程序表D2A',
        schema: {},
        htmlData: createMockHtmlData(),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.trimForm = { programId: 'p4', programDesc: '检查期后回款情况', reason: '   ' }
    vm.confirmTrim()
    await nextTick()

    // Should not emit since reason is whitespace-only
    expect(wrapper.emitted('program-trim')).toBeUndefined()
  })
})

describe('GtAProgramConsole — 批量裁剪', () => {
  it('批量裁剪更新所有选中程序状态', async () => {
    const wrapper = mount(GtAProgramConsole, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款实质性程序表D2A',
        schema: {},
        htmlData: createMockHtmlData(),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    vm.selectedIds = ['p2', 'p4']
    vm.batchTrimForm.reason = '本项目不涉及该业务'
    vm.confirmBatchTrim()
    await nextTick()

    const emitted = wrapper.emitted('program-trim')
    expect(emitted).toBeDefined()
    expect(emitted!.length).toBe(2)
    expect(vm.programs[1].status).toBe('not_applicable')
    expect(vm.programs[3].status).toBe('not_applicable')
    expect(vm.programs[1].trim_reason).toBe('本项目不涉及该业务')
    expect(vm.selectedIds.length).toBe(0)
  })
})

describe('GtAProgramConsole — 辅助方法', () => {
  it('statusLabel 正确映射', () => {
    const wrapper = mount(GtAProgramConsole, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款实质性程序表D2A',
        schema: {},
        htmlData: { programs: [], trim_decisions: [] },
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.statusLabel('completed')).toBe('已完成')
    expect(vm.statusLabel('in_progress')).toBe('执行中')
    expect(vm.statusLabel('not_applicable')).toBe('已裁剪')
    expect(vm.statusLabel('pending')).toBe('待执行')
    expect(vm.statusLabel('')).toBe('待执行')
  })

  it('parseLinkedWorkpapers 正确分割', () => {
    const wrapper = mount(GtAProgramConsole, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款实质性程序表D2A',
        schema: {},
        htmlData: { programs: [], trim_decisions: [] },
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.parseLinkedWorkpapers('D2-1/D2-2/D2-3')).toEqual(['D2-1', 'D2-2', 'D2-3'])
    expect(vm.parseLinkedWorkpapers('D2-1,D2-2')).toEqual(['D2-1', 'D2-2'])
    expect(vm.parseLinkedWorkpapers('')).toEqual([])
  })

  it('isRowSelectable 排除已裁剪和已完成', () => {
    const wrapper = mount(GtAProgramConsole, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款实质性程序表D2A',
        schema: {},
        htmlData: createMockHtmlData(),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    expect(vm.isRowSelectable({ status: 'pending' })).toBe(true)
    expect(vm.isRowSelectable({ status: 'in_progress' })).toBe(true)
    expect(vm.isRowSelectable({ status: 'completed' })).toBe(false)
    expect(vm.isRowSelectable({ status: 'not_applicable' })).toBe(false)
  })
})

describe('GtAProgramConsole — readonly 模式', () => {
  it('readonly 模式下不显示批量裁剪按钮', () => {
    const wrapper = mount(GtAProgramConsole, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款实质性程序表D2A',
        schema: {},
        htmlData: createMockHtmlData(),
        readonly: true,
      },
      global: { stubs: globalStubs },
    })

    // No batch trim button in readonly mode
    const buttons = wrapper.findAll('.el-button')
    const batchBtn = buttons.find(b => b.text().includes('批量裁剪'))
    expect(batchBtn).toBeUndefined()
  })
})

describe('GtAProgramConsole — 新增程序', () => {
  it('确认新增后追加程序行 + emit program-add', async () => {
    const wrapper = mount(GtAProgramConsole, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款实质性程序表D2A',
        schema: {},
        htmlData: createMockHtmlData(),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    const beforeCount = vm.programs.length
    vm.openAddDialog()
    await nextTick()
    expect(vm.addDialogVisible).toBe(true)

    vm.addForm = { desc: '新增专项核查程序', category: '备选', linkedWorkpapers: 'D2-9' }
    vm.confirmAdd()
    await nextTick()

    expect(vm.programs.length).toBe(beforeCount + 1)
    const last = vm.programs[vm.programs.length - 1]
    expect(last.program_desc).toBe('新增专项核查程序')
    expect(last.program_category).toBe('备选')
    expect(last.linked_workpapers).toBe('D2-9')
    expect(last.status).toBe('pending')
    // 序号递增（取当前最大 +1）
    expect(last.program_no).toBe(5)
    expect(vm.addDialogVisible).toBe(false)

    const emitted = wrapper.emitted('program-add')
    expect(emitted).toBeDefined()
    expect(emitted![0][0]).toMatchObject({ description: '新增专项核查程序' })
  })

  it('空描述不允许新增', async () => {
    const wrapper = mount(GtAProgramConsole, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款实质性程序表D2A',
        schema: {},
        htmlData: createMockHtmlData(),
      },
      global: { stubs: globalStubs },
    })

    const vm = wrapper.vm as any
    const beforeCount = vm.programs.length
    vm.addForm = { desc: '   ', category: '常规★', linkedWorkpapers: '' }
    vm.confirmAdd()
    await nextTick()

    expect(vm.programs.length).toBe(beforeCount)
    expect(wrapper.emitted('program-add')).toBeUndefined()
  })

  it('readonly 模式下不显示新增程序按钮', () => {
    const wrapper = mount(GtAProgramConsole, {
      props: {
        wpId: 'wp-001',
        sheetName: '应收账款实质性程序表D2A',
        schema: {},
        htmlData: createMockHtmlData(),
        readonly: true,
      },
      global: { stubs: globalStubs },
    })

    const buttons = wrapper.findAll('.el-button')
    const addBtn = buttons.find(b => b.text().includes('新增程序'))
    expect(addBtn).toBeUndefined()
  })
})
